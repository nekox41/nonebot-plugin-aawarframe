# 作用：实现 nonebot_plugin_aawarframe 层的 bootstrap 功能。
# 编写日期：2026-11-07
# 作者：Aameow

import asyncio

from nonebot import get_driver, get_plugin_config

from .config import Config
from .infrastructure.http import HttpClient
from .providers.market import MarketProvider
from .providers.rivens import RivenProvider
from .providers.worldstate import WorldStateProvider
from .rendering.renderer import CardRenderer
from .services.market import MarketService
from .services.rivens import RivenService
from .services.worldstate import WorldStateService


class Runtime:
    def __init__(self, config: Config):
        self.http = HttpClient(config.aawarframe_http_timeout)
        self.world_http = (
            HttpClient(
                config.aawarframe_http_timeout, proxy=str(config.aawarframe_worldstate_proxy)
            )
            if config.aawarframe_worldstate_proxy
            else self.http
        )
        self.world_provider = WorldStateProvider(
            self.world_http, config.aawarframe_cache_dir, config.aawarframe_worldstate_ttl
        )
        self.market_provider = MarketProvider(
            self.http, config.aawarframe_cache_dir, config.aawarframe_market_ttl
        )
        self.riven_provider = RivenProvider(self.http, config.aawarframe_cache_dir)
        self.rivens = RivenService(self.riven_provider)
        self.riven_task: asyncio.Task[None] | None = None
        self.world = WorldStateService(self.world_provider)
        self.market = MarketService(self.market_provider)
        self.renderer = CardRenderer(config.aawarframe_render_concurrency)

    def start(self) -> None:
        if self.riven_task is None or self.riven_task.done():
            self.riven_task = asyncio.create_task(self.riven_provider.run_daily())

    async def close(self) -> None:
        if self.riven_task is not None:
            self.riven_task.cancel()
            await asyncio.gather(self.riven_task, return_exceptions=True)
            self.riven_task = None
        await self.renderer.close()
        await self.world_provider.close()
        await self.market_provider.close()
        if self.world_http is not self.http:
            await self.world_http.close()
        await self.http.close()


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime(get_plugin_config(Config))
    return _runtime


def setup() -> None:
    driver = get_driver()

    @driver.on_startup
    async def startup():
        # 初始化无外部请求，上游故障不会阻止插件启动。
        get_runtime().start()

    @driver.on_shutdown
    async def shutdown():
        global _runtime
        if _runtime is not None:
            await _runtime.close()
            _runtime = None
