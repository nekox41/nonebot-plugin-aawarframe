# 作用：通过异步 HTTP 队列查询维基，每秒最多发送一次请求。
# 编写日期：2026-11-13
# 作者：Aameow

import asyncio
from importlib.metadata import version
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..models.errors import WikiChallengeError
from .http import retry_after
from .wiki_transport import WikiCurlTransport

WIKI_HEADERS = {
    "User-Agent": (
        f"AAWarframe/{version('nonebot-plugin-aawarframe')} "
        "(https://github.com/nekox41/nonebot-plugin-aawarframe) "
        f"curl-cffi/{version('curl-cffi')}"
    ),
    "Accept": "*/*",
    "Accept-Language": "zh-CN",
    "Accept-Encoding": "gzip, deflate, br, zstd",
}


class WikiHttpClient:
    def __init__(self, timeout: float = 20, *, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(
            timeout=timeout,
            transport=WikiCurlTransport(),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )
        self.queue: asyncio.Queue[tuple[str, dict, asyncio.Future]] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._next_request = 0.0
        self._closed = False

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != "warframe.huijiwiki.com" or parsed.path != "/api.php":
            raise ValueError("Wiki HTTP 客户端只接受本站 API 地址")
        if self._closed:
            raise RuntimeError("Wiki 请求队列已关闭")
        safe_headers = {k: v for k, v in (headers or {}).items() if k.lower() in {"accept", "accept-language"}}
        future = asyncio.get_running_loop().create_future()
        self.queue.put_nowait((url, safe_headers, future))
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="aawarframe-wiki-queue")
        return await future

    async def _run(self) -> None:
        while True:
            url, headers, future = await self.queue.get()
            try:
                if future.cancelled():
                    continue
                # 仅跟随本站跳转，每一跳都计入速率，不让 HTTP→HTTPS 绕过限速。
                current_url = url
                for redirect in range(4):
                    while self._next_request > monotonic():
                        await asyncio.sleep(self._next_request - monotonic())
                    if future.cancelled():
                        break
                    self._next_request = monotonic() + 1.0
                    request = self.client.build_request("GET", current_url, headers={**WIKI_HEADERS, **headers})
                    request.headers.pop("Cookie", None)
                    response = await self.client.send(request, follow_redirects=False)
                    if not response.is_redirect:
                        break
                    target = response.next_request
                    if target is None or redirect == 3:
                        raise RuntimeError("Wiki API 跳转次数过多或缺少跳转地址")
                    parsed = urlsplit(str(target.url))
                    if (parsed.scheme not in {"http", "https"}
                            or parsed.netloc != "warframe.huijiwiki.com" or parsed.path != "/api.php"):
                        raise RuntimeError("Wiki API 跳转到了非本站地址")
                    if current_url.startswith("https:") and parsed.scheme != "https":
                        raise RuntimeError("Wiki API 请求不能从 HTTPS 降级")
                    current_url = str(target.url)
                if future.cancelled():
                    continue
                if response.status_code in {429, 503}:
                    self._next_request = max(
                        self._next_request,
                        monotonic() + retry_after(response.headers.get("Retry-After"), 1),
                    )
                if response.status_code == 403 or response.headers.get("cf-mitigated") == "challenge":
                    raise WikiChallengeError("Wiki API 暂时要求浏览器验证")
                response.raise_for_status()
                result = response.json()
                if not future.done():
                    future.set_result(result)
            except asyncio.CancelledError:
                future.cancel()
                raise
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            finally:
                self.queue.task_done()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        while not self.queue.empty():
            _, _, future = self.queue.get_nowait()
            future.cancel()
            self.queue.task_done()
        await self.client.aclose()
