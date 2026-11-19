# 作用：提供带口令认证的 HTTPS 管理 API 和网页管理台。
# 编写日期：2026-11-13
# 作者：Aameow

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import ssl
import subprocess
from collections import OrderedDict, deque
from contextlib import contextmanager
from ipaddress import ip_address
from pathlib import Path
from time import monotonic
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


class AliasInput(BaseModel):
    item_id: str
    alias: str = Field(min_length=1, max_length=120)


class ArbitrationInput(BaseModel):
    node_id: str
    grade: Literal["S", "A", "B", "C", "D", "F"]
    vitus_per_minute: float = Field(ge=0, allow_inf_nan=False)


def create_app(runtime, token: str):
    grq = runtime.grq
    digest = hashlib.sha256(token.encode()).digest()
    failures = OrderedDict()

    async def authenticate(request: Request):
        address = request.client.host if request.client else "unknown"
        now = monotonic()
        attempts = failures.setdefault(address, deque())
        failures.move_to_end(address)
        while len(failures) > 2048:
            failures.popitem(last=False)
        while attempts and now - attempts[0] > 60:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(429, "登录尝试过多，请一分钟后重试")
        value = request.headers.get("authorization", "")
        supplied = value[7:] if value.startswith("Bearer ") else ""
        if not hmac.compare_digest(hashlib.sha256(supplied.encode()).digest(), digest):
            attempts.append(now)
            raise HTTPException(401, "登录口令不正确")
        failures.pop(address, None)
        # Bearer 认证不使用 Cookie；同时拒绝跨站浏览器提交。
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "不允许跨站请求")

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def protect(request, call_next):
        limit = 2_000_000
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > limit):
            return JSONResponse({"detail": "请求内容过大"}, 413)
        # 同时限制没有 Content-Length 的分块上传。
        if request.method in {"POST", "PUT", "PATCH"}:
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    return JSONResponse({"detail": "请求内容过大"}, 413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/")
    async def home():
        return FileResponse(STATIC / "index.html")

    @app.get("/app.js")
    async def javascript():
        return FileResponse(STATIC / "app.js", media_type="text/javascript")

    @app.get("/style.css")
    async def stylesheet():
        return FileResponse(STATIC / "style.css", media_type="text/css")

    auth = [Depends(authenticate)]

    @app.get("/api/session", dependencies=auth)
    async def session():
        return {"ok": True}

    @app.get("/api/items", dependencies=auth)
    async def items(q: str = ""):
        if len(q) > 200:
            raise HTTPException(400, "查询内容过长")
        if not q.strip():
            return {"items": []}
        index = grq.domains["Items"]
        result = grq.search("Items", q)
        selected = {r.id: r for r in result.candidates}
        key = q.casefold()
        for resource in index.resources.values():
            if len(selected) >= 30:
                break
            if (
                resource.enabled
                and key
                in " ".join([resource.id, *resource.names.values(), *resource.aliases]).casefold()
            ):
                selected.setdefault(resource.id, resource)
        return {
            "items": [
                {
                    "id": r.id,
                    "name": r.name(),
                    "name_en": r.names.get("en", ""),
                    "tradable": r.metadata.get("market_tradable", False),
                    "market_slug": r.identifiers.get("market.slug"),
                }
                for r in selected.values()
                if r.enabled
            ]
        }

    @app.get("/api/aliases", dependencies=auth)
    async def aliases():
        return {"items": await asyncio.to_thread(grq.list_aliases)}

    @app.post("/api/aliases", dependencies=auth)
    async def add_alias(payload: AliasInput):
        await asyncio.to_thread(grq.add_alias, payload.item_id, payload.alias)
        return {"ok": True}

    @app.delete("/api/aliases", dependencies=auth)
    async def delete_alias(payload: AliasInput):
        await asyncio.to_thread(grq.delete_alias, payload.item_id, payload.alias)
        return {"ok": True}

    @app.get("/api/arbitration/nodes", dependencies=auth)
    async def arbitration_nodes():
        return {"items": runtime.arbitration.list_nodes()}

    @app.put("/api/arbitration/nodes", dependencies=auth)
    async def save_arbitration(payload: ArbitrationInput):
        await asyncio.to_thread(runtime.arbitration.save_node, **payload.model_dump())
        runtime.renderer.cache.entries.clear()
        return {"ok": True}

    return app


class EmbeddedServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # 进程信号由 NoneBot 主服务器处理。
        yield


class AdminServer:
    def __init__(self, runtime, config):
        self.runtime, self.config = runtime, config
        self.server = None
        self.task = None

    def start(self):
        config = self.config
        directory = config.aawarframe_cache_dir / "admin"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        token_file = directory / "password"
        if config.aawarframe_admin_password:
            token = config.aawarframe_admin_password.get_secret_value()
        else:
            if not token_file.exists():
                fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as stream:
                    stream.write(secrets.token_urlsafe(32) + "\n")
            token_file.chmod(0o600)
            token = token_file.read_text().strip()
        if len(token) < 16:
            raise ValueError("管理口令至少需要 16 个字符")
        cert = config.aawarframe_admin_cert or directory / "cert.pem"
        key = config.aawarframe_admin_key or directory / "key.pem"
        if bool(config.aawarframe_admin_cert) != bool(config.aawarframe_admin_key):
            raise ValueError("必须同时配置管理台证书和私钥")
        if not config.aawarframe_admin_cert and not (cert.exists() and key.exists()):
            host = config.aawarframe_admin_public_host or "localhost"
            try:
                ip_address(host)
                san = "IP:" + host
            except ValueError:
                if not all(c.isalnum() or c in "-." for c in host):
                    raise ValueError("管理台域名无效") from None
                san = "DNS:" + host
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(key),
                    "-out",
                    str(cert),
                    "-days",
                    "365",
                    "-subj",
                    "/CN=" + host,
                    "-addext",
                    "subjectAltName=" + san,
                ],
                check=True,
                capture_output=True,
                timeout=20,
            )
            key.chmod(0o600)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        app = create_app(self.runtime, token)
        self.server = EmbeddedServer(
            uvicorn.Config(
                app,
                host=config.aawarframe_admin_host,
                port=config.aawarframe_admin_port,
                ssl_certfile=str(cert),
                ssl_keyfile=str(key),
                access_log=True,
                proxy_headers=False,
                log_config=None,
                log_level=None,
                timeout_graceful_shutdown=5,
            )
        )
        self.task = asyncio.create_task(self._serve(), name="aawarframe-admin")
        self.task.add_done_callback(self._done)
        logger.info("管理台 HTTPS 端口 %s；口令文件：%s", config.aawarframe_admin_port, token_file)

    async def _serve(self):
        try:
            await self.server.serve()
        except SystemExit as exc:
            # 管理端口冲突不应终止机器人主进程。
            raise RuntimeError("管理台未能启动，请检查端口和证书") from exc

    def _done(self, task):
        if not task.cancelled() and task.exception():
            logger.error("管理台运行失败", exc_info=task.exception())

    async def close(self):
        if self.server:
            self.server.should_exit = True
        if self.task:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 8)
            except TimeoutError:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
