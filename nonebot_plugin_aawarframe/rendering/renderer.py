# Desc: 通过 htmlrender 渲染并缓存 WebP 查询卡片。
# Date: 2026-11-19
# Author: Aameow

import asyncio
import base64
import json
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import ceil
from pathlib import Path
from time import monotonic, perf_counter

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ..infrastructure.cache import AsyncTTLCache
from ..models.common import Card, Snapshot, utcnow
from .charts import trend_chart
from .viewmodels import paginate

ROOT = Path(__file__).parent
RENDER_CACHE_VERSION = 2
VOLATILE_FIELDS = {
    "fetched_at",
    "render_cache_until",
    "remaining",
    "remaining_short",
    "archimedea_remaining",
    "bounty_remaining",
}


def _stable_value(value):
    if isinstance(value, dict):
        return {
            key: _stable_value(item)
            for key, item in value.items()
            if key not in VOLATILE_FIELDS
        }
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    return value


class CardRenderer:
    def __init__(
        self,
        concurrency: int = 2,
        theme: str = "default",
        *,
        now_provider: Callable[[], datetime] = utcnow,
        cache_clock: Callable[[], float] = monotonic,
    ):
        self.template_override_dir: Path | None = None
        self.environment = Environment(
            loader=FileSystemLoader(ROOT / "templates"),
            autoescape=select_autoescape(default=True),
            undefined=StrictUndefined,
        )
        self.environment.filters["beijing"] = lambda value: value.astimezone(
            timezone(timedelta(hours=8))
        )
        styles = ROOT / "assets/css"
        selected = styles / "themes" / (theme + ".css")
        if selected.resolve().parent != (styles / "themes").resolve() or not selected.is_file():
            raise ValueError("未知卡片主题：" + theme)
        self.theme = theme
        self._css_files = [
            "base.css", "trader.css", "riven_values.css", "riven_market.css",
            "trend.css", "relics.css", "riven_analysis.css", f"themes/{theme}.css",
        ]
        self._load_css()
        self.asset_fingerprint = self._asset_fingerprint()
        self.now_provider = now_provider
        self.semaphore = asyncio.Semaphore(concurrency)
        self.cache = AsyncTTLCache[Snapshot](30, 0, max_entries=16, clock=cache_clock)
        self.page_cache = AsyncTTLCache[Snapshot](86400, 0, max_entries=64, clock=cache_clock)
        self.render_count = 0
        self.active_renders = 0
        self.max_concurrent_renders = 0
        self.render_durations: deque[float] = deque(maxlen=512)

    def _load_css(self) -> None:
        styles = ROOT / "assets/css"
        override = self.template_override_dir / "css" if self.template_override_dir else None
        parts = []
        for name in self._css_files:
            candidate = override / name if override else None
            if candidate is None or not candidate.is_file():
                candidate = styles / name
            parts.append(candidate.read_text(encoding="utf-8"))
        self.css = "\n".join(parts)

    def configure_admin_overrides(self, directory: Path) -> None:
        """Enable persisted admin template/CSS overrides and invalidate render caches."""
        self.template_override_dir = Path(directory)
        template_dir = self.template_override_dir / "templates"
        self.environment.loader = ChoiceLoader(
            [FileSystemLoader(template_dir), FileSystemLoader(ROOT / "templates")]
        )
        self.environment.cache.clear()
        self._load_css()
        self.asset_fingerprint = self._asset_fingerprint()
        self.cache.entries.clear()
        self.page_cache.entries.clear()

    def _asset_fingerprint(self) -> str:
        digest = sha256()
        digest.update(str(RENDER_CACHE_VERSION).encode())
        digest.update(self.theme.encode())
        digest.update(self.css.encode())
        roots = [ROOT / "templates"]
        if self.template_override_dir:
            roots.insert(0, self.template_override_dir / "templates")
        for root in roots:
            if root.exists():
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        digest.update(path.relative_to(root).as_posix().encode())
                        digest.update(path.read_bytes())
        return digest.hexdigest()

    @property
    def metrics(self) -> dict[str, float | int]:
        caches = (self.cache, self.page_cache)
        hits = sum(cache.hits for cache in caches)
        misses = sum(cache.misses for cache in caches)
        durations = sorted(self.render_durations)
        count = len(durations)
        return {
            "cache_hits": hits,
            "cache_misses": misses,
            "cache_coalesced": sum(cache.coalesced for cache in caches),
            "cache_hit_rate": hits / (hits + misses) if hits + misses else 0.0,
            "render_count": self.render_count,
            "average_render_seconds": sum(durations) / count if count else 0.0,
            "p95_render_seconds": durations[max(0, ceil(count * 0.95) - 1)] if count else 0.0,
            "max_concurrent_renders": self.max_concurrent_renders,
        }

    def _template_name(self, card: Card) -> str:
        if card.analysis_mode:
            return "riven_analysis.html"
        if card.parts_board or card.relic_board:
            return "relics.html"
        if card.trend_board:
            return "trend.html"
        if card.attribute_rows:
            return "attributes.html"
        if card.command_names:
            return "commands.html"
        if card.riven_market_board:
            return "riven_market.html"
        if card.riven_values_board:
            return "riven_values.html"
        if card.trader_board:
            return "void_trader.html"
        if card.arbitration_board:
            return "arbitration.html"
        if card.market_board:
            return "market.html"
        if card.operation_board:
            return "operations.html"
        if card.weekly_mode:
            return "weekly.html"
        if card.nightwave_mode:
            return "nightwave.html"
        if card.archimedea_mode:
            return "archimedea.html"
        if card.bounty_challenge_mode:
            return "challenge_bounties.html"
        if card.bounty_mode:
            return "bounties.html"
        if card.fissure_mode:
            return "fissures.html"
        return "card.html"

    def html(self, card: Card, page: int | None = None, total: int | None = None) -> str:
        template = self._template_name(card)
        document = self.environment.get_template(template).render(
            card=card,
            page=page or card.page_number or 1,
            total=total or card.total_pages or 1,
            trend_charts=[
                (period, trend_chart(period)) for period in card.trend_board.periods
            ] if card.trend_board else [],
        )
        return document.replace("</head>", "<style>" + self.css + "</style></head>", 1)

    def _deadlines(self, card: Card) -> list[tuple[str, datetime]]:
        deadlines: list[tuple[str, datetime]] = []
        deadlines.extend(
            (f"cycle:{index}", item.expiry)
            for index, item in enumerate(card.cycle_items)
            if item.available
        )
        deadlines.extend(
            (f"fissure:{index}", item.expiry)
            for index, item in enumerate(card.fissure_items)
        )
        if card.rotation_expiry:
            deadlines.append(("rotation", card.rotation_expiry))
        if card.archimedea_expiry:
            deadlines.append(("archimedea", card.archimedea_expiry))
        if card.bounty_expiry:
            deadlines.append(("bounty", card.bounty_expiry))
        if card.operation_board and card.operation_board.expiry:
            deadlines.append(("operation", card.operation_board.expiry))
        if (
            card.arbitration_board
            and card.arbitration_board.current
            and card.arbitration_board.entries
        ):
            deadlines.append(
                ("arbitration", card.arbitration_board.entries[0].time + timedelta(hours=1))
            )
        if card.render_cache_until:
            deadlines.append(("transition", card.render_cache_until))
        return deadlines

    def _cache_key(self, card: Card, page: int, total: int, now: datetime) -> str:
        data = _stable_value(
            card.model_dump(
                mode="json",
                exclude={"fetched_at", "render_cache_until"},
            )
        )
        buckets = []
        for name, deadline in self._deadlines(card):
            if name in {"rotation", "transition"}:
                continue
            seconds = max(0, ceil((deadline - now).total_seconds()))
            buckets.append((name, ceil(seconds / 10)))
        payload = {
            "renderer": self.asset_fingerprint,
            "template": self._template_name(card),
            "page": page,
            "total": total,
            "fetched_at_minute": int(card.fetched_at.timestamp() // 60),
            "time_buckets": buckets,
            "card": data,
        }
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def _cache_ttl(self, cache: AsyncTTLCache, card: Card, now: datetime) -> float:
        deadlines = [deadline for _, deadline in self._deadlines(card)]
        if any(deadline <= now for deadline in deadlines):
            return 0.0
        future = [(deadline - now).total_seconds() for deadline in deadlines]
        return min(cache.ttl, min(future)) if future else cache.ttl

    async def render(self, card: Card) -> list[bytes]:
        # 显式分页和专用卡片各渲染一张图片，保留任务顺序与完整信息。
        single_page = (
            card.analysis_mode
            or card.relic_board
            or card.trend_board
            or card.attribute_rows
            or card.command_names
            or card.riven_market_board
            or card.riven_values_board
            or card.page_number is not None
            or card.cycle_items
            or card.bounty_mode
            or card.archimedea_mode
            or card.nightwave_mode
            or card.weekly_mode
            or card.market_board
            or card.arbitration_board
            or card.trader_board
        )
        pages = [card] if single_page else paginate(card)
        images = []
        for index, page in enumerate(pages, 1):
            page_number = page.page_number or index
            total_pages = page.total_pages or len(pages)
            html = self.html(page, page_number, total_pages)
            now = self.now_provider()
            key = self._cache_key(page, page_number, total_pages, now)

            compact = bool(
                page.analysis_mode
                or page.parts_board
                or page.relic_board
                or page.trend_board
                or page.attribute_rows
                or page.command_names
                or page.riven_market_board
                or page.riven_values_board
                or page.operation_board
                or page.fissure_mode
                or page.cycle_items
                or page.bounty_mode
                or page.archimedea_mode
                or page.nightwave_mode
                or page.weekly_mode
                or page.market_board
                or page.arbitration_board
                or page.trader_board
            )

            async def load(document=html, fixed=compact, cache_key=key):
                started = perf_counter()
                async with self.semaphore:
                    self.active_renders += 1
                    self.max_concurrent_renders = max(
                        self.max_concurrent_renders, self.active_renders
                    )
                    try:
                        # 唯一截图入口；延迟导入使解析器与业务测试无需启动浏览器。
                        from nonebot_plugin_htmlrender import render_html

                        width, height = 800, None
                        if fixed:
                            document, width, height = await self._fit_document(document)
                            # htmlrender 的 ViewportConfig 要求整数；内容测量会产生小数像素。
                            width, height = int(ceil(width)), int(ceil(height))
                        image = await render_html(
                            document,
                            width=width,
                            height=height,
                            device_pixel_ratio=1,
                            image_format="png",
                            timeout_seconds=30,
                        )
                        webp = await self._encode_webp(bytes(image))
                        return Snapshot(data=webp, source=cache_key)
                    finally:
                        self.active_renders -= 1
                        self.render_count += 1
                        self.render_durations.append(perf_counter() - started)

            cache = self.page_cache if card.page_number is not None else self.cache
            images.append(
                (
                    await cache.get(
                        key,
                        load,
                        ttl=lambda: self._cache_ttl(cache, page, self.now_provider()),
                    )
                ).data
            )
        return images

    async def _fit_document(self, document: str) -> tuple[str, int, int]:
        """优先保持字号和单行字段，按内容扩展画布，最长边不超过 2000。"""
        from nonebot_plugin_htmlrender import get_default_application

        async with get_default_application().extensions.playwright.page() as page:
            await page.set_viewport_size({"width": 2000, "height": 2000})
            await page.set_content(document, wait_until="domcontentloaded")
            await page.evaluate("document.fonts.ready")
            await page.evaluate("Promise.all([...document.images].map(image => image.decode().catch(() => {})))")
            dimensions = await page.evaluate("""() => {
                const root = document.documentElement;
                const body = document.body;
                const content = document.querySelector('.card__content');
                const fissure = body.classList.contains('fissure-page');
                const bounty = body.classList.contains('bounty-page');
                const research = body.classList.contains('archimedea-page');
                const nightwave = body.classList.contains('nightwave-page');
                const weekly = body.classList.contains('weekly-page');
                const operation = body.classList.contains('operation-page');
                const market = body.classList.contains('market-page');
                const arbitration = body.classList.contains('arbitration-page');
                const trader = body.classList.contains('trader-page');
                const riven = body.classList.contains('riven-values-page');
                const commands = body.classList.contains('commands-page');
                const attributeTable = body.classList.contains('attributes-page');
                const trend = body.classList.contains('trend-page');
                const relic = body.classList.contains('relic-page');
                const auctions = body.classList.contains('riven-market-page');
                const singleCycle = document.querySelectorAll('.cycle').length === 1;
                const maximum = relic ? 28 : attributeTable ? 32 : commands ? 36 : auctions ? 28 : riven ? 26 : trader ? 24 : arbitration ? 30 : market ? 32 : operation ? 30 : weekly || nightwave ? 30 : research ? 28 : fissure ? 28 : (bounty ? 28 : (singleCycle ? 44 : 36));
                const textWidth = element => {
                    if (!element) return 0;
                    const range = document.createRange();
                    range.selectNodeContents(element);
                    return range.getBoundingClientRect().width;
                };
                for (let font = maximum; font >= (trader ? 8 : 12); font--) {
                    root.style.setProperty('--data-font', font + 'px');
                    let needed = 600;
                    if (relic) {
                        needed = Math.max(900, textWidth(document.querySelector('h1')) + 70);
                        for (const heading of document.querySelectorAll('.part-heading')) needed = Math.max(needed, textWidth(heading) + 64);
                        for (const chip of document.querySelectorAll('.relic-chip')) {
                            const width = [...chip.children].reduce((sum, child) => sum + textWidth(child), 0) + 40;
                            needed = Math.max(needed, width * 3 + 80);
                        }
                        for (const table of document.querySelectorAll('.relic-rewards')) {
                            let width = 64;
                            for (let column = 0; column < table.rows[0].cells.length; column++) {
                                width += Math.max(...[...table.rows].map(row => textWidth(row.cells[column]))) + 20;
                            }
                            needed = Math.max(needed, width);
                        }
                    } else if (trend) {
                        needed = Math.max(1100, textWidth(document.querySelector('h1')) + 70);
                    } else if (commands) {
                        needed = Math.max(800, (Math.max(...[...document.querySelectorAll('.command-name')].map(textWidth)) + 32) * 4 + 92);
                    } else if (attributeTable) {
                        const widths = [...document.querySelectorAll('.attribute-table')].map(table =>
                            [0, 1].reduce((sum, column) => sum + Math.max(...[...table.rows].map(row => textWidth(row.cells[column]))) + 24, 0));
                        needed = Math.max(800, Math.max(...widths) * 2 + 80);
                    } else if (trader) {
                        for (const width of [1320, 1560, 1800, 1980]) {
                            root.style.setProperty('--trader-columns', String(Math.floor(width / 230)));
                            body.style.width = width + 'px';
                            const height = Math.ceil(body.getBoundingClientRect().height);
                            const fits = [...document.querySelectorAll('.trader-item')].every(item => item.scrollWidth <= item.clientWidth + 1);
                            if (height <= 2000 && fits) return {width, height};
                        }
                        continue;
                    } else if (auctions) {
                        let column = 420;
                        for (const row of document.querySelectorAll('.riven-listing-head, .riven-listing-price')) {
                            column = Math.max(column, [...row.children].reduce((sum, cell) => sum + textWidth(cell), 0) + 52);
                        }
                        for (const field of document.querySelectorAll('.riven-listing-meta, .riven-listing-stat')) {
                            column = Math.max(column, textWidth(field) + 40);
                        }
                        needed = Math.max(column * 2 + 80, textWidth(document.querySelector('.riven-market-filter')) + 60);
                    } else if (riven) {
                        let panelWidth = 650;
                        for (const table of document.querySelectorAll('.riven-values-table')) {
                            let width = 24;
                            for (let column = 0; column < table.rows[0].cells.length; column++) {
                                width += Math.max(...[...table.rows].filter(row => !row.classList.contains('riven-section')).map(row => textWidth(row.cells[column]))) + 18;
                            }
                            panelWidth = Math.max(panelWidth, width);
                        }
                        panelWidth = Math.max(panelWidth, textWidth(document.querySelector('.riven-values h2')) + textWidth(document.querySelector('.riven-layout')) + 46);
                        for (const name of document.querySelectorAll('.riven-family-name')) {
                            panelWidth = Math.max(panelWidth, textWidth(name) + 24);
                        }
                        needed = panelWidth + 56;
                    } else if (arbitration) {
                        const rows = [...document.querySelectorAll('.arbitration-row')];
                        needed = Math.max(800, ...rows.map(row => textWidth(row.querySelector('.arbitration-time')) + Math.max(textWidth(row.querySelector('.arbitration-node>strong')), textWidth(row.querySelector('.arbitration-details'))) + 100));
                    } else if (market) {
                        needed = 800;
                        for (const table of document.querySelectorAll('.market-orders')) {
                            const rows = [...table.rows];
                            let width = 80;
                            for (let column = 0; column < 5; column++) {
                                width += Math.max(...rows.map(row => textWidth(row.cells[column]))) + 28;
                            }
                            needed = Math.max(needed, width);
                        }
                    } else if (operation) {
                        needed = 720;
                        const invCards = [...document.querySelectorAll('.invasion-card')];
                        const invWidth = card => {
                            const head = [...card.querySelector('.invasion-head').children].reduce((sum, e) => sum + textWidth(e), 0);
                            const sides = [...card.querySelectorAll('.invasion-side')].map(side =>
                                Math.max(0, ...[...side.querySelectorAll('strong, .invasion-reward')].map(textWidth)));
                            return Math.max(head + 42, Math.max(0, ...sides) * 2 + 48);
                        };
                        if (invCards.length) {
                            const columns = document.querySelector('.invasion-columns--two') ? 2 : 1;
                            needed = Math.max(needed, Math.max(...invCards.map(invWidth)) * columns + 60 + (columns - 1) * 24);
                        }
                        for (const row of document.querySelectorAll('.operation-period, .operation-banner, .operation-task-head')) {
                            const width = [...row.children].reduce((sum, e) => sum + textWidth(e), 0);
                            needed = Math.max(needed, width + 100);
                        }
                        for (const row of document.querySelectorAll('.operation-condition')) {
                            needed = Math.max(needed, textWidth(row) + 84);
                        }
                    } else if (weekly) {
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
                                needed = Math.max(needed, width + 100);
                            }
                        }
                    }
                    const width = Math.ceil(Math.min(2000, Math.max(800, needed)));
                    body.style.width = width + 'px';
                    const height = Math.ceil(body.getBoundingClientRect().height);
                    const bounds = body.getBoundingClientRect();
                    const fields = [...document.querySelectorAll('.cycle__top, .cycle__body, .fissure__task, .fissure__location, .fissure__time, .arbitration-time, .arbitration-node, .market-order, .trader-item, .weekly-table td, .nightwave-task__body, .nightwave-task__meta, .operation-period span, .operation-condition, .invasion-head, .invasion-reward, .bounty-refresh span, .bounty-location, .hub-bounty-top, .hub-bounty-meta, .hub-bounty-objective, .research-modifier p, .research-modifier-name, .research-period, .nightwave-task__body p, .nightwave-task__meta > span, .operation-period span, .operation-condition, .operation-task-head span, .invasion-head span, .invasion-reward')];
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
            return await page.content(), int(ceil(dimensions["width"])), int(ceil(dimensions["height"]))

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
