from pathlib import Path

from pydantic import AnyHttpUrl, BaseModel, Field


class Config(BaseModel):
    aawarframe_cache_dir: Path = Path("data/aawarframe")
    aawarframe_worldstate_proxy: AnyHttpUrl | None = Field(default=None, repr=False)
    aawarframe_http_timeout: float = Field(default=12, gt=0, le=60)
    aawarframe_worldstate_ttl: float = Field(default=45, gt=0, le=180)
    aawarframe_market_ttl: float = Field(default=30, gt=0, le=90)
    aawarframe_render_concurrency: int = Field(default=2, ge=1, le=2)
