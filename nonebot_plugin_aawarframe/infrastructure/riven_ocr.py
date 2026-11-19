# Desc: 限制图片下载和 OCR 队列，管理常驻识别子进程。
# Date: 2026-11-15
# Author: Aameow

import asyncio
import base64
import json
import logging
import sys
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from ..models.errors import UserInputError

LIMIT = 12 * 1024 * 1024


def image_segments(message):
    from nonebot.adapters.onebot.v11 import Message

    return [segment for segment in Message(message) if segment.type == "image"]


async def message_image(bot, event, http):
    images = image_segments(event.message)
    if not images:
        reply = event.reply
        original = getattr(event, "original_message", event.message)
        reply_id = reply.message_id if reply else next(
            (segment.data.get("id") for segment in original if segment.type == "reply"), None
        )
        if reply_id is not None:
            try:
                # 不依赖适配器的 Reply 模型校验，兼容缺少 real_id 等字段的返回。
                message = await bot.get_msg(message_id=int(reply_id))
                images = image_segments(message.get("message") or message.get("raw_message", ""))
            except Exception:
                logging.getLogger(__name__).debug("重新读取引用消息失败")
        if not images and reply:
            images = image_segments(reply.message)
    if len(images) != 1:
        raise UserInputError("请在“分析”后附上一张紫卡图片，或引用一张图片。")
    segment = images[0].data
    urls = []
    # 引用的他人图片可能只保留 file 标识，或携带已失效的临时链接。
    if segment.get("file") and not segment["file"].startswith("base64://"):
        try:
            info = await bot.get_image(file=segment["file"])
            if info.get("url"):
                urls.append(info["url"])
        except Exception:
            logging.getLogger(__name__).debug("刷新图片地址失败，使用消息中的地址")
    urls.extend(value for value in (segment.get("url"), segment.get("file")) if value and value not in urls)
    for url in urls:
        if url.startswith("base64://"):
            if len(url) > LIMIT * 4 // 3 + 20:
                raise UserInputError("图片超过 12 MB，请裁剪后发送。")
            try:
                return base64.b64decode(url[9:], validate=True)
            except ValueError:
                continue
        try:
            data = await download_image(url, http)
            if data:
                return data
        except httpx.HTTPError:
            continue
    raise UserInputError("无法读取这张图片，请重新上传后分析。")


async def download_image(url, http):
    for _ in range(4):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme not in {"http", "https"} or not any(host == domain or host.endswith("." + domain) for domain in ("qq.com", "qq.com.cn", "qpic.cn")) or parts.username or parts.password or parts.port not in {None, 80, 443}:
            return None
        async with http.client.stream("GET", url, follow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > LIMIT:
                    raise UserInputError("图片超过 12 MB，请裁剪后发送。")
            return bytes(data)
    return None


class RivenOCR:
    def __init__(self, python=None):
        self.python = python or sys.executable
        self.process = None
        self.lock = asyncio.Lock()
        self.pending = 0
        self.log_task = None
        self.errors = deque(maxlen=30)

    async def read(self):
        while True:
            line = await self.process.stdout.readline()
            if not line:
                await self.process.wait()
                if self.log_task:
                    await self.log_task
                raise RuntimeError("OCR 进程已退出：" + "\n".join(self.errors))
            if line.startswith(b"AAWARFRAME_OCR:"):
                return json.loads(line.split(b":", 1)[1])

    async def logs(self, stream):
        while line := await stream.readline():
            text = line.decode(errors="replace").rstrip()
            self.errors.append(text)
            logging.getLogger(__name__).debug("OCR: %s", text)

    async def start(self):
        if self.process is not None and self.process.returncode is None:
            return
        self.errors.clear()
        # 隔离脚本目录，避免同目录 http.py 遮蔽 Python 标准库。
        self.process = await asyncio.create_subprocess_exec(
            self.python, "-I", str(Path(__file__).with_name("ocr_worker.py")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=2 * 1024 * 1024,
        )
        self.log_task = asyncio.create_task(self.logs(self.process.stderr))
        if not (await asyncio.wait_for(self.read(), 300)).get("ready"):
            raise RuntimeError("OCR 初始化失败")

    async def recognize(self, image, analyze):
        if self.pending >= 8:
            raise UserInputError("分析队列已满，请稍后再发。")
        self.pending += 1
        try:
            async with self.lock:
                try:
                    await self.start()
                    for retry in (False, True):
                        payload = json.dumps({"image": base64.b64encode(image).decode(), "retry": retry})
                        self.process.stdin.write(payload.encode() + b"\n")
                        await self.process.stdin.drain()
                        result = await asyncio.wait_for(self.read(), 120)
                        if result.get("error"):
                            raise UserInputError("图片识别失败，请裁剪紫卡区域后重发。")
                        errors = []
                        for rows in result["passes"]:
                            try:
                                return analyze(rows)
                            except UserInputError as exc:
                                logging.getLogger(__name__).debug(
                                    "紫卡解析失败：%s；识别文字：%s", exc, [row["text"] for row in rows]
                                )
                                errors.append(exc)
                    raise errors[-1]
                except asyncio.CancelledError:
                    await self.close()
                    raise
                except UserInputError:
                    raise
                except Exception:
                    await self.close()
                    logging.getLogger(__name__).exception("紫卡 OCR 不可用")
                    raise UserInputError("识别服务暂不可用，请稍后重试。") from None
        finally:
            self.pending -= 1

    async def close(self):
        if self.process:
            if self.process.returncode is None:
                self.process.kill()
            await self.process.wait()
            self.process = None
        if self.log_task:
            self.log_task.cancel()
            await asyncio.gather(self.log_task, return_exceptions=True)
            self.log_task = None
