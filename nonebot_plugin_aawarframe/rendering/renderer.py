import asyncio
from hashlib import sha256
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ..infrastructure.cache import AsyncTTLCache
from ..models.common import Card, Snapshot
from .viewmodels import paginate

ROOT = Path(__file__).parent


class CardRenderer:
    def __init__(self, concurrency: int = 2):
        self.environment = Environment(
            loader=FileSystemLoader(ROOT / "templates"),
            autoescape=select_autoescape(default=True),
            undefined=StrictUndefined,
        )
        self.css = (ROOT / "assets/css/base.css").read_text(encoding="utf-8")
        self.semaphore = asyncio.Semaphore(concurrency)
        self.cache = AsyncTTLCache[Snapshot](30, 0, max_entries=16)
        self.page_cache = AsyncTTLCache[Snapshot](86400, 0, max_entries=64)

    def html(self, card: Card, page: int | None = None, total: int | None = None) -> str:
        return self.environment.get_template("card.html").render(
            card=card, css=self.css, page=page or card.page_number or 1,
            total=total or card.total_pages or 1
        )

    async def render(self, card: Card) -> list[bytes]:
        # 显式分页的排行榜一次只渲染请求页，不再按通用字符预算拆页。
        pages = [card] if card.page_number is not None else paginate(card)
        images = []
        for index, page in enumerate(pages, 1):
            html = self.html(page, page.page_number or index, page.total_pages or len(pages))
            key = sha256(html.encode()).hexdigest()

            async def load(document=html):
                # 唯一截图入口；延迟导入使解析器与业务测试无需启动浏览器。
                from nonebot_plugin_htmlrender import render_html

                async with self.semaphore:
                    image = await render_html(
                        document,
                        width=900,
                        device_pixel_ratio=1,
                        image_format="png",
                        timeout_seconds=30,
                    )
                return Snapshot(data=bytes(image), source=key)

            cache = self.page_cache if card.page_number is not None else self.cache
            images.append((await cache.get(key, load)).data)
        return images

    async def close(self) -> None:
        await self.cache.close()
        await self.page_cache.close()
