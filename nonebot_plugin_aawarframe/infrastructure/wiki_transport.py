# 作用：以异步 libcurl 传输维基请求，固定已验证的 HTTP/1.1 配置，不启动浏览器。
# 编写日期：2026-11-13
# 作者：Aameow

import httpx
from curl_cffi.const import CurlHttpVersion
from curl_cffi.requests import AsyncSession


class WikiCurlTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.session = AsyncSession(max_clients=1)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # 按实测可用的大小写及顺序发送，不携带浏览器 Cookie 或来源页验证参数。
        headers = {
            name: request.headers[name]
            for name in ("accept", "accept-encoding", "accept-language", "user-agent")
        }
        response = await self.session.request(
            request.method,
            str(request.url),
            headers=headers,
            impersonate="chrome",
            http_version=CurlHttpVersion.V1_1,
            default_headers=False,
            allow_redirects=False,
            discard_cookies=True,
            accept_encoding="gzip, deflate, br, zstd",
            timeout=request.extensions.get("timeout", {}).get("read") or 20,
        )
        # libcurl 已解压响应，移除传输编码信息，防止 HTTPX 再次解压。
        response_headers = {
            key: value for key, value in response.headers.items()
            if key.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
        }
        return httpx.Response(
            response.status_code,
            headers=response_headers,
            content=response.content,
            request=request,
            extensions={"http_version": b"HTTP/1.1"},
        )

    async def aclose(self) -> None:
        await self.session.close()
