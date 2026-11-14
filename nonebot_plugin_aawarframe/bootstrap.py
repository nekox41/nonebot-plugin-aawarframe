# Desc: 实现 nonebot_plugin_aawarframe 层的 bootstrap 功能。
# Date: 2026-11-14
# Author: Aameow

import asyncio
import logging

import httpx
from nonebot import get_driver, get_plugin_config

from .admin.control import Control
from .admin.server import AdminServer
from .config import Config
from .grq import GameResourceQuery, configure_grq
from .infrastructure.http import HttpClient
from .infrastructure.images import ItemImages
from .infrastructure.wiki_http import WikiHttpClient
from .initialization.pipeline import ensure_offline, initialize
from .providers.market import MarketProvider
from .providers.rivens import RivenProvider
from .providers.wiki import WikiProvider
from .providers.worldstate import WorldStateProvider
from .rendering.renderer import CardRenderer
from .services.arbitration import ArbitrationService
from .services.market import MarketService
from .services.rivens import RivenService
from .services.riven_values import RivenValuesService
from .services.wiki import WikiService
from .services.worldstate import WorldStateService
from .services.void_trader import VoidTraderService


class Runtime:
    def __init__(self, config: Config):
        ensure_offline(config.aawarframe_cache_dir)
        self.grq = GameResourceQuery(config.aawarframe_cache_dir / "registry.sqlite3")
        configure_grq(self.grq)
        self.arbitration = ArbitrationService(self.grq, config.aawarframe_cache_dir)
        self.control = Control(
            self.grq,
            {
                "http_timeout": config.aawarframe_http_timeout,
                "worldstate_ttl": config.aawarframe_worldstate_ttl,
                "market_ttl": config.aawarframe_market_ttl,
            },
        )
        self.admin = AdminServer(self, config) if config.aawarframe_admin_enabled else None
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
        self.images = ItemImages(self.http)
        self.market_provider = MarketProvider(
            self.http, config.aawarframe_cache_dir, config.aawarframe_market_ttl, images=self.images
        )
        self.riven_provider = RivenProvider(self.http, config.aawarframe_cache_dir)
        self.rivens = RivenService(self.riven_provider)
        self.riven_values = RivenValuesService()
        self.riven_task: asyncio.Task[None] | None = None
        self.world = WorldStateService(self.world_provider)
        self.trader = VoidTraderService(self.world_provider)
        self.market = MarketService(self.market_provider)
        self.wiki_http = WikiHttpClient(config.aawarframe_http_timeout)
        self.wiki_provider = WikiProvider(self.wiki_http)
        self.wiki = WikiService(self.wiki_provider)
        self.renderer = CardRenderer(config.aawarframe_render_concurrency, config.aawarframe_theme)
        self.control.apply = self.apply_options
        self.apply_options(self.control.settings.options)

    def apply_options(self, options):
        for http in {self.http, self.world_http, self.wiki_http}:
            http.client.timeout = httpx.Timeout(options.http_timeout)
        self.world_provider.cache.ttl = options.worldstate_ttl
        self.market_provider.cache.ttl = options.market_ttl
        self.wiki_provider.cache.ttl = options.wiki_ttl
        self.wiki_http.interval = options.wiki_interval

    def start(self) -> None:
        if self.admin and self.admin.task is None:
            try:
                self.admin.start()
            except Exception:
                logging.getLogger(__name__).exception("管理台启动失败")
        if self.riven_task is None or self.riven_task.done():
            self.riven_task = asyncio.create_task(self.riven_provider.run_daily())

    async def close(self) -> None:
        if self.admin:
            await self.admin.close()
        if self.riven_task is not None:
            self.riven_task.cancel()
            await asyncio.gather(self.riven_task, return_exceptions=True)
            self.riven_task = None
        await self.wiki_provider.close()
        await self.wiki_http.close()
        await self.renderer.close()
        await self.world_provider.close()
        await self.market_provider.close()
        await self.images.close()
        if self.world_http is not self.http:
            await self.world_http.close()
        await self.http.close()
        self.grq.close()
        configure_grq(None)


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
        # 资源准备失败时使用离线数据，再启动机器人运行时。
        config = get_plugin_config(Config)
        if config.aawarframe_data_auto_update:
            await initialize(config.aawarframe_cache_dir)
        get_runtime().start()

    @driver.on_shutdown
    async def shutdown():
        global _runtime
        if _runtime is not None:
            await _runtime.close()
            _runtime = None
