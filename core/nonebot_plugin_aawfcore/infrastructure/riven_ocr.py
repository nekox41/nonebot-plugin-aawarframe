# Desc: 限制图片下载和 OCR 队列，管理常驻识别子进程。
# Date: 2026-11-15
# Author: Aameow

import asyncio
import base64
import json
import logging
import sys
from collections import deque
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path

from ..models.errors import UserInputError

LIMIT = 12 * 1024 * 1024
MAX_ANALYSES = 8
MAX_DOWNLOADS = 4
DOWNLOAD_TIMEOUT = 30


class RivenOCR:
    def __init__(self, python=None):
        self.python = python or sys.executable
        self.process = None
        self.lock = asyncio.Lock()
        self.pending = 0
        self.download_slots = asyncio.Semaphore(MAX_DOWNLOADS)
        self._admission_owner: ContextVar[asyncio.Task | None] = ContextVar(
            'aawf_ocr_admission_owner', default=None
        )
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

    @asynccontextmanager
    async def admission(self):
        """Reserve one slot BEFORE fetching media; nested calls in the same task reuse it.

        asyncio tasks inherit ContextVars, so ownership also checks current_task().
        The counter changes without awaits and is atomic within the event loop.
        """
        task = asyncio.current_task()
        if task is not None and self._admission_owner.get() is task:
            yield
            return
        if self.pending >= MAX_ANALYSES:
            raise UserInputError("分析队列已满，请稍后再发。")
        self.pending += 1
        token = self._admission_owner.set(task)
        try:
            yield
        finally:
            self._admission_owner.reset(token)
            self.pending -= 1

    async def recognize(self, image, analyze):
        async with self.admission():
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
