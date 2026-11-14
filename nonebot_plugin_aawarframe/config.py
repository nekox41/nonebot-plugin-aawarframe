# Desc: 实现 nonebot_plugin_aawarframe 层的 config 功能。
# Date: 2026-11-14
# Author: Aameow

from pathlib import Path

from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr


class Config(BaseModel):
    aawarframe_cache_dir: Path = Path("data/aawarframe")
    aawarframe_worldstate_proxy: AnyHttpUrl | None = Field(default=None, repr=False)
    aawarframe_http_timeout: float = Field(default=12, gt=0, le=60)
    aawarframe_worldstate_ttl: float = Field(default=45, gt=0, le=180)
    aawarframe_market_ttl: float = Field(default=30, gt=0, le=90)
    aawarframe_theme: str = Field(default="default", pattern=r"^[a-zA-Z0-9_-]+$")
    aawarframe_render_concurrency: int = Field(default=2, ge=1, le=2)

    aawarframe_data_auto_update: bool = True

    aawarframe_admin_enabled: bool = False
    aawarframe_admin_host: str = "127.0.0.1"
    aawarframe_admin_port: int = Field(default=8443, ge=1024, le=65535)
    aawarframe_admin_password: SecretStr | None = Field(default=None, repr=False)
    aawarframe_admin_public_host: str | None = None
    aawarframe_admin_cert: Path | None = None
    aawarframe_admin_key: Path | None = None
