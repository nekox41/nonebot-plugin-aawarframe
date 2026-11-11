# 作用：通过 htmlrender 渲染并缓存 WebP 查询卡片。
# 编写日期：2026-11-07
# 作者：Aameow

import asyncio
import base64
from datetime import timedelta, timezone
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
        self.environment.filters["beijing"] = lambda value: value.astimezone(
            timezone(timedelta(hours=8))
        )
        self.css = (ROOT / "assets/css/base.css").read_text(encoding="utf-8")
        self.semaphore = asyncio.Semaphore(concurrency)
        self.cache = AsyncTTLCache[Snapshot](30, 0, max_entries=16)
        self.page_cache = AsyncTTLCache[Snapshot](86400, 0, max_entries=64)

    def html(self, card: Card, page: int | None = None, total: int | None = None) -> str:
        if card.weekly_mode:
            template = "weekly.html"
        elif card.nightwave_mode:
            template = "nightwave.html"
        elif card.archimedea_mode:
            template = "archimedea.html"
        elif card.bounty_challenge_mode:
            template = "challenge_bounties.html"
        elif card.bounty_mode:
            template = "bounties.html"
        elif card.fissure_mode:
            template = "fissures.html"
        else:
            template = "card.html"
        return self.environment.get_template(template).render(
            card=card,
            css=self.css,
            page=page or card.page_number or 1,
            total=total or card.total_pages or 1,
        )

    async def render(self, card: Card) -> list[bytes]:
        # 显式分页和专用卡片各渲染一张图片，保留任务顺序与完整信息。
        single_page = (
            card.page_number is not None
            or card.cycle_items
            or card.bounty_mode
            or card.archimedea_mode
            or card.nightwave_mode
            or card.weekly_mode
        )
        pages = [card] if single_page else paginate(card)
        images = []
        for index, page in enumerate(pages, 1):
            html = self.html(page, page.page_number or index, page.total_pages or len(pages))
            key = sha256(html.encode()).hexdigest()

            compact = bool(
                page.fissure_mode
                or page.cycle_items
                or page.bounty_mode
                or page.archimedea_mode
                or page.nightwave_mode
                or page.weekly_mode
            )

            async def load(document=html, fixed=compact):
                # 唯一截图入口；延迟导入使解析器与业务测试无需启动浏览器。
                from nonebot_plugin_htmlrender import render_html

                async with self.semaphore:
                    width, height = 800, None
                    if fixed:
                        document, width, height = await self._fit_document(document)
                    image = await render_html(
                        document,
                        width=width,
                        height=height,
                        device_pixel_ratio=1,
                        image_format="png",
                        timeout_seconds=30,
                    )
                    webp = await self._encode_webp(bytes(image))
                return Snapshot(data=webp, source=key)

            cache = self.page_cache if card.page_number is not None else self.cache
            images.append((await cache.get(key, load)).data)
        return images

    async def _fit_document(self, document: str) -> tuple[str, int, int]:
        """优先保持字号和单行字段，按内容扩展画布，最长边不超过 2000。"""
        from nonebot_plugin_htmlrender import get_default_application

        async with get_default_application().extensions.playwright.page() as page:
            await page.set_viewport_size({"width": 2000, "height": 2000})
            await page.set_content(document, wait_until="domcontentloaded")
            await page.evaluate("document.fonts.ready")
            dimensions = await page.evaluate("""() => {
                const root = document.documentElement;
                const body = document.body;
                const content = document.querySelector('.card__content');
                const fissure = body.classList.contains('fissure-page');
                const bounty = body.classList.contains('bounty-page');
                const research = body.classList.contains('archimedea-page');
                const nightwave = body.classList.contains('nightwave-page');
                const weekly = body.classList.contains('weekly-page');
                const singleCycle = document.querySelectorAll('.cycle').length === 1;
                const maximum = weekly || nightwave ? 30 : research ? 28 : fissure ? 28 : (bounty ? 28 : (singleCycle ? 44 : 36));
                const textWidth = element => {
                    if (!element) return 0;
                    const range = document.createRange();
                    range.selectNodeContents(element);
                    return range.getBoundingClientRect().width;
                };
                for (let font = maximum; font >= 12; font--) {
                    root.style.setProperty('--data-font', font + 'px');
                    let needed = 600;
                    if (weekly) {
                        needed = document.querySelector('th:nth-child(6)') ? 1500 : 1000;
                    } else if (nightwave || research) {
                        needed = 1000;
                    } else if (fissure) {
                        const measure = container => ['task', 'location', 'time'].map(name =>
                            Math.max(0, ...[...container.querySelectorAll('.fissure__' + name)]
                                .map(cell => Math.max(...[...cell.children].map(textWidth)))))
                            .reduce((a, b) => a + b, 0) + 36;
                        const panels = [...document.querySelectorAll('.fissure-panel')];
                        if (panels.length) {
                            // 两栏分别测量，再取相同宽度，保持左右齐整且字段不换行。
                            needed = Math.max(960, Math.max(...panels.map(measure)) * 2 + 88);
                            const extras = document.querySelector('.fissure-extras');
                            if (extras) needed = Math.max(needed, measure(extras) + 60);
                        } else {
                            needed = Math.max(needed, measure(content) + 60);
                        }
                    } else if (bounty) {
                        needed = 720;
                        for (const table of document.querySelectorAll('table')) {
                            const rows = [...table.rows];
                            const count = Math.max(0, ...rows.map(row => row.cells.length));
                            let width = 64;
                            for (let column = 0; column < count; column++) {
                                width += Math.max(0, ...rows.map(row => textWidth(row.cells[column]))) + 24;
                            }
                            needed = Math.max(needed, width);
                        }
                        for (const row of document.querySelectorAll('.bounty-refresh')) {
                            const width = [...row.children].reduce((sum, child) => sum + textWidth(child), 0);
                            needed = Math.max(needed, width + 84);
                        }
                        for (const row of document.querySelectorAll('.bounty-location')) {
                            const cells = row.querySelectorAll('strong, span');
                            const width = [...cells].reduce((sum, cell) => sum + textWidth(cell), 0);
                            needed = Math.max(needed, width + 114);
                        }
                        for (const row of document.querySelectorAll('.hub-bounty-top, .hub-bounty-meta')) {
                            const width = [...row.children].reduce((sum, child) => sum + textWidth(child), 0);
                            needed = Math.max(needed, width + 104);
                        }
                        for (const row of document.querySelectorAll('.hub-bounty-objective')) {
                            needed = Math.max(needed, textWidth(row) + 92);
                        }
                        for (const row of document.querySelectorAll('.bounty-detail > h2, .bounty-detail > .bounty-meta')) {
                            needed = Math.max(needed, textWidth(row) + 64);
                        }
                    } else {
                        for (const cycle of document.querySelectorAll('.cycle')) {
                            for (const selector of ['.cycle__top', '.cycle__body']) {
                                const row = cycle.querySelector(selector);
                                const width = [...row.children].reduce((sum, child) => sum + textWidth(child), 0);
                                needed = Math.max(needed, width + 132);
                            }
                        }
                        for (const table of document.querySelectorAll('table')) {
                            const rows = [...table.rows];
                            const count = Math.max(0, ...rows.map(row => row.cells.length));
                            let width = 64;
                            for (let column = 0; column < count; column++) {
                                width += Math.max(0, ...rows.map(row => textWidth(row.cells[column]))) + 20;
                            }
                            needed = Math.max(needed, width);
                        }
                    }
                    const width = Math.ceil(needed);
                    if (width > 2000) continue;
                    body.style.width = width + 'px';
                    const height = Math.ceil(body.getBoundingClientRect().height);
                    const bounds = content.getBoundingClientRect();
                    const fields = [...content.querySelectorAll('strong, h2, td, th, time, .cycle__next, .fissure span, .task-chip, .stage-pool-label, .bounty-meta, .bounty-location span, .hub-bounty-objective, .hub-bounty-top span, .hub-bounty-meta span, .research-modifier p, .research-modifier-name, .research-period, .nightwave-task__body p, .nightwave-task__meta > span')];
                    const fits = fields.every(element => {
                        const r = element.getBoundingClientRect();
                        return r.right <= bounds.right + 1 && r.left >= bounds.left - 1 &&
                            element.scrollWidth <= r.width + 1;
                    });
                    if (height <= 2000 && fits) {
                        root.dataset.fitFont = String(font);
                        root.dataset.fitWidth = String(width);
                        root.dataset.fitHeight = String(height);
                        return {width, height};
                    }
                }
                throw new Error('Card content exceeds 2000px canvas capacity');
            }""")
            return await page.content(), dimensions["width"], dimensions["height"]

    async def _encode_webp(self, image: bytes) -> bytes:
        # htmlrender 0.8 只接受 PNG/JPEG，借用其 Chromium 编码 WebP，不依赖 Pillow。
        from nonebot_plugin_htmlrender import get_default_application

        async with get_default_application().extensions.playwright.page() as page:
            encoded = await page.evaluate(
                """async (payload) => {
                    const image = new Image();
                    image.src = 'data:image/png;base64,' + payload;
                    await image.decode();
                    const canvas = document.createElement('canvas');
                    const scale = Math.min(1, 2000 / image.naturalWidth, 2000 / image.naturalHeight);
                    canvas.width = Math.max(1, Math.floor(image.naturalWidth * scale));
                    canvas.height = Math.max(1, Math.floor(image.naturalHeight * scale));
                    canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
                    const result = canvas.toDataURL('image/webp', 0.94);
                    if (!result.startsWith('data:image/webp;base64,')) {
                        throw new Error('WebP encoding is not supported');
                    }
                    return result.split(',')[1];
                }""",
                base64.b64encode(image).decode("ascii"),
            )
        return base64.b64decode(encoded, validate=True)

    async def close(self) -> None:
        await self.cache.close()
        await self.page_cache.close()
