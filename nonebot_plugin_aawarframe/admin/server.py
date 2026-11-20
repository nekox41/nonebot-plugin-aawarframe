# 作用：提供带口令认证的 HTTP 管理 API 和网页管理台。
# 编写日期：2026-11-13
# 作者：Aameow

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from collections import OrderedDict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from jinja2 import TemplateSyntaxError
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


class EditorInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content: str = Field(max_length=1_000_000)
    revision: str = Field(min_length=64, max_length=64)


class PreviewInput(BaseModel):
    template: str = Field(min_length=1, max_length=80)


class PreviewSelectionInput(BaseModel):
    feature: str = Field(min_length=1, max_length=80)
    template_version: str = Field(default="", max_length=240)
    css_version: str = Field(default="", max_length=240)


class EditorVersionInput(BaseModel):
    kind: Literal["html", "css"]
    feature: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    content: str = Field(max_length=1_000_000)


EDITOR_TEMPLATES = {
    "arbitration.html", "archimedea.html", "attributes.html", "base.html",
    "bounties.html", "bounty_rewards.html", "card.html", "challenge_bounties.html",
    "commands.html", "fissures.html", "market.html", "nightwave.html",
    "operations.html", "relics.html", "riven_analysis.html", "riven_market.html",
    "riven_values.html", "trend.html", "void_trader.html", "weekly.html",
}
EDITOR_CSS = {
    "base.css", "trader.css", "riven_values.css", "riven_market.css",
    "trend.css", "relics.css", "riven_analysis.css", "themes/default.css",
}
PREVIEW_CATALOG = [
    ("card", "通用信息卡片", "card.html", "基础信息、表格和说明"),
    ("cycles", "环境周期", "card.html", "地球、夜灵平原等周期状态"),
    ("fissures", "虚空裂缝", "fissures.html", "裂缝等级、任务与剩余时间"),
    ("arbitration", "仲裁排期", "arbitration.html", "当前仲裁和后续轮换"),
    ("market", "Market 挂单", "market.html", "在线卖家与买家列表"),
    ("sortie", "突击任务", "operations.html", "阶段任务与特殊条件"),
    ("archon", "执刑官猎杀", "operations.html", "执刑官弱点与阶段任务"),
    ("invasions", "入侵任务", "operations.html", "阵营进度与任务奖励"),
    ("parts", "Prime 部件来源", "relics.html", "部件对应的遗物来源"),
    ("relics", "遗物奖励", "relics.html", "遗物奖励概率和白金价格"),
    ("trend", "成交趋势", "trend.html", "成交量与价格变化"),
    ("riven_analysis", "紫卡分析", "riven_analysis.html", "词条评估与分析结果"),
    ("attributes", "紫卡词条表", "attributes.html", "词条缩写和名称"),
    ("commands", "命令列表", "commands.html", "可用命令速查"),
    ("riven_market", "紫卡市场", "riven_market.html", "紫卡挂单和筛选条件"),
    ("riven_values", "紫卡数值", "riven_values.html", "武器家族词条数值"),
    ("void_trader", "虚空商人", "void_trader.html", "货单和杜卡德价格"),
    ("weekly", "每周轮换", "weekly.html", "每周奖励与轮换表"),
    ("nightwave", "午夜电波", "nightwave.html", "挑战任务与声望"),
    ("archimedea", "深层科研", "archimedea.html", "偏差与精英风险"),
    ("bounties", "普通赏金", "bounties.html", "赏金等级与声望"),
    ("challenge_bounties", "挑战赏金", "challenge_bounties.html", "任务目标与奖励"),
]


def _feature_ids() -> set[str]:
    return {item[0] for item in PREVIEW_CATALOG}


def _editor_paths(name: str, override_dir: Path):
    templates = Path(__file__).parents[1] / "rendering" / "templates"
    styles = Path(__file__).parents[1] / "rendering" / "assets" / "css"
    if name.startswith("templates/") and name.removeprefix("templates/") in EDITOR_TEMPLATES:
        relative = name.removeprefix("templates/")
        return templates / relative, override_dir / "templates" / relative
    if name.startswith("css/") and name.removeprefix("css/") in EDITOR_CSS:
        relative = name.removeprefix("css/")
        return styles / relative, override_dir / "css" / relative
    match = re.fullmatch(r"(templates|css)/versions/([a-z0-9_-]+)/([a-z0-9_-]+)\.(html|css)", name)
    if match:
        kind, feature, filename, extension = match.groups()
        if feature not in _feature_ids() or (kind == "templates") != (extension == "html"):
            raise HTTPException(404, "找不到此模板或样式文件")
        version = override_dir / kind / "versions" / feature / f"{filename}.{extension}"
        return version, version
    raise HTTPException(404, "找不到此模板或样式文件")


def _file_revision(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _version_items(override_dir: Path, kind: str, feature: str) -> list[dict[str, str]]:
    extension = "html" if kind == "templates" else "css"
    root = override_dir / kind / "versions" / feature
    if not root.is_dir():
        return []
    return [
        {
            "id": f"versions/{feature}/{path.name}",
            "title": path.stem,
        }
        for path in sorted(root.glob(f"*.{extension}"))
        if path.is_file()
    ]


def _sample_fields(feature: str) -> list[dict[str, str]]:
    sample = _preview_card(feature).model_dump(mode="json")
    fields: list[dict[str, str]] = []

    def visit(path: str, value, depth: int = 0):
        example = json.dumps(value, ensure_ascii=False, default=str)
        if len(example) > 100:
            example = example[:97] + "..."
        fields.append({
            "path": path,
            "placeholder": "{{ " + path + " }}",
            "example": example,
        })
        if depth >= 3:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                visit(f"{path}.{key}", child, depth + 1)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            for key, child in value[0].items():
                visit(f"{path}[0].{key}", child, depth + 1)

    for key, value in sample.items():
        visit("card." + key, value)
    for key, value in (("page", 1), ("total", 1), ("trend_charts", [])):
        fields.append({
            "path": key,
            "placeholder": "{{ " + key + " }}",
            "example": json.dumps(value, ensure_ascii=False),
        })
    return fields


def _preview_card(template: str):
    from ..models.arbitration import ArbitrationBoard, ArbitrationEntry
    from ..models.bounties import BountyDisplay
    from ..models.common import Card, CycleDisplay, FissureDisplay, Section
    from ..models.market import MarketBoard
    from ..models.operations import InvasionDisplay, OperationBoard, OperationTask
    from ..models.relics import PartRelics, PartsBoard, RelicBoard, RelicReference, RelicReward
    from ..models.riven_market import RivenListing, RivenMarketBoard
    from ..models.riven_values import RivenAttribute, RivenValuesBoard
    from ..models.trend import TrendBoard, TrendPeriod, TrendPoint
    from ..models.void_trader import TraderBoard, TraderGroup, TraderItem

    now = datetime.now(timezone.utc)
    base = {
        "title": "Warframe · 示例预览",
        "source": "AAWarframe · WebUI 预览",
        "fetched_at": now,
        "sections": [
            Section(
                title="示例信息",
                columns=["项目", "内容"],
                rows=[["数据状态", "正常"], ["更新时间", "刚刚"]],
                notes=["这是本地生成的示例，不会触发外部数据请求。"],
            )
        ],
    }
    if template == "cycles":
        base["cycle_items"] = [
            CycleDisplay(name="夜灵平原", state="白天", next_state="黑夜",
                         remaining="18 分钟", remaining_short="18:00",
                         expiry=now + timedelta(minutes=18), tone="day"),
            CycleDisplay(name="金星", state="温暖", next_state="寒冷",
                         remaining="22 分钟", remaining_short="22:00",
                         expiry=now + timedelta(minutes=22), tone="warm"),
        ]
    elif template == "fissures":
        base.update(title="虚空裂缝", fissure_mode="normal", item_total=1,
                    fissure_items=[FissureDisplay(
                        tier="古纪", tier_key="VoidT1", node="防御 · 泰亚",
                        planet="地球", mission="防御", faction="Grineer",
                        remaining="24 分钟", remaining_short="24:00",
                        expiry=now + timedelta(minutes=24))])
    elif template == "arbitration":
        base["arbitration_board"] = ArbitrationBoard(current=True, entries=[
            ArbitrationEntry(node_id="SolNode1", node="泰亚", planet="地球",
                             mission="防御", faction="Grineer", time=now,
                             remaining="42:00", label="当前", grade="S",
                             vitus_per_minute=2.5)])
    elif template == "market":
        base["market_board"] = MarketBoard(name="圣装战甲部件",
                                            description="PC / 跨平台在线挂单")
    elif template in {"sortie", "archon", "invasions"}:
        tasks = [
            OperationTask(number=1, mission="生存", node="卡吕普索",
                          planet="土星", modifier="敌人护盾增强"),
            OperationTask(number=2, mission="防御", node="泰亚", planet="地球"),
            OperationTask(number=3, mission="间谍", node="阿马尔", planet="木星"),
        ]
        if template == "invasions":
            base["operation_board"] = OperationBoard(
                kind="invasions",
                invasions=[InvasionDisplay(
                    node="塞德娜 · 卡律布狄斯", planet="塞德娜",
                    attacker="Grineer", defender="Corpus",
                    attacker_percent=62.5, defender_percent=37.5,
                    attacker_rewards=["Forma 蓝图"], defender_rewards=["Orokin 电池"],
                )],
            )
        else:
            base["operation_board"] = OperationBoard(
                kind=template,
                boss="夜灵水力使" if template == "archon" else "突击指挥官",
                faction="Grineer",
                reward="琥珀执刑官源力石" if template == "archon" else "",
                tone="gold" if template == "archon" else "",
                tasks=tasks,
            )
    elif template == "parts":
        base["parts_board"] = PartsBoard(parts=[
            PartRelics(name="圣装武器部件", quantity=1, relics=[
                RelicReference(name="Lith A1", rarity="rare", vaulted=False),
                RelicReference(name="Meso B7", rarity="uncommon", vaulted=True),
            ])
        ])
    elif template == "relics":
        base["relic_board"] = RelicBoard(
            name="Lith A1", vaulted=False,
            rewards=[
                RelicReward(ref="Lith A1", name="圣装战甲蓝图",
                            chances=[25.33, 23.33, 20, 16.67], price=8.5),
                RelicReward(ref="Lith A1", name="圣装武器部件",
                            chances=[25.33, 23.33, 20, 16.67], price=14),
            ])
    elif template == "trend":
        base["trend_board"] = TrendBoard(name="圣装部件", periods=[
            TrendPeriod(title="近 7 天", volume=128, average=14.6, points=[
                TrendPoint(time=now - timedelta(days=1), volume=12, price=13.5),
                TrendPoint(time=now, volume=18, price=15.2),
            ])])
    elif template == "riven_analysis":
        base.update(title="紫卡分析 · 示例武器", analysis_mode=True,
                    sections=[Section(title="词条评估",
                                      columns=["词条", "数值", "基准", "评级"],
                                      rows=[["暴击几率", "+120%", "+100%", "S"],
                                            ["多重射击", "+90%", "+100%", "A"]])])
    elif template == "attributes":
        base["attribute_rows"] = [("CC", "暴击几率"), ("CD", "暴击伤害"),
                                  ("MS", "多重射击")]
    elif template == "commands":
        base["command_names"] = ["平原", "裂缝", "突击", "仲裁", "wm", "遗物", "紫卡分析"]
    elif template == "riven_market":
        base["riven_market_board"] = RivenMarketBoard(
            weapon="示例武器", positive_filter="暴击几率 · 多重射击",
            negative_filter="无负面",
            listings=[RivenListing(
                seller="Tenno", status="游戏中", price=120, price_type="固定价格",
                rank=8, mastery=16, rolls=3,
                positives=["暴击几率 +120%", "多重射击 +90%"], negatives=[])])
    elif template == "riven_values":
        base["riven_values_board"] = RivenValuesBoard(
            layout="2", name="伯斯顿", weapon_class="步枪",
            variants=["伯斯顿", "伯斯顿 Prime"],
            ordinary=[RivenAttribute(name="暴击几率", positive="+90%", negative="—")])
    elif template == "void_trader":
        base["trader_board"] = TraderBoard(
            location="中继站 · 示例货单", time=now + timedelta(days=2),
            groups=[TraderGroup(name="武器与装备",
                                items=[TraderItem(name="圣装武器部件",
                                                  ducats=100, credits=50000)])])
    elif template == "weekly":
        base.update(title="每周轮换", weekly_mode=True,
                    sections=[Section(title="本周奖励", columns=["项目", "奖励", "状态"],
                                      rows=[["钢铁之路", "装饰品", "可领取"],
                                            ["灵化武器", "进化材料", "轮换中"]],
                                      highlighted_rows=[0])])
    elif template == "nightwave":
        base.update(title="午夜电波", nightwave_mode=True,
                    sections=[Section(title="本周挑战",
                                      rows=[["完成 3 次任务", "完成任意任务目标",
                                             "4500", "6 天", "每周"]])])
    elif template == "archimedea":
        base.update(title="深层科研", archimedea_mode=True,
                    archimedea_activation=now - timedelta(days=2),
                    archimedea_expiry=now + timedelta(days=5),
                    archimedea_remaining="5 天",
                    sections=[Section(title="偏差条件", rows=[
                        ["偏差", "敌人护甲提升", "敌人获得额外护甲。"],
                        ["精英风险", "能量限制", "能量补给效率降低。"]])])
    elif template in {"bounties", "challenge_bounties"}:
        base.update(
            title="赏金任务", bounty_mode=template == "bounties",
            bounty_challenge_mode=template == "challenge_bounties",
            bounty_region="夜灵平原 · 希图斯", bounty_currency="基础声望",
            bounty_remaining="42 分钟", bounty_expiry=now + timedelta(minutes=42),
            bounty_items=[BountyDisplay(
                index=1, name="高风险赏金", kind="常规", min_level=20,
                max_level=40, stages=5, standing=1000, mastery=0, rotation="A",
                node="地球", mission="解放营地", faction="Grineer",
                objectives=["清理敌人", "保护目标"])])
    elif template == "base":
        base["title"] = "卡片基础模板"
    return Card(**base)


def create_app(runtime, token: str, override_dir: Path | None = None):
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
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
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
    selections = {"templates": {}, "css": {}}

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

    @app.get("/api/status", dependencies=auth)
    async def status():
        domains = []
        total_resources = 0
        for name, domain in getattr(grq, "domains", {}).items():
            resources = getattr(domain, "resources", {})
            count = len(resources)
            enabled = sum(1 for item in resources.values() if getattr(item, "enabled", True))
            total_resources += count
            domains.append({"name": name, "title": getattr(domain, "title", name),
                            "count": count, "enabled": enabled})
        market_index = getattr(grq, "market_index", None)
        if market_index is not None:
            market_resources = getattr(market_index, "resources", {})
            market_count = len(market_resources)
            market_enabled = sum(
                1 for item in market_resources.values() if getattr(item, "enabled", True)
            )
            domains.append({
                "name": "Market", "title": "可交易物品",
                "count": market_count, "enabled": market_enabled,
            })
            total_resources += market_count
        aliases_count = len(await asyncio.to_thread(grq.list_aliases))
        subscriptions = getattr(runtime, "subscriptions", None)
        store = getattr(subscriptions, "store", None)
        subscription_count = len(await asyncio.to_thread(store.all_active)) if store else 0
        control_settings = getattr(getattr(runtime, "control", None), "settings", None)
        command_items = getattr(control_settings, "commands", [])
        enabled_commands = sum(1 for item in command_items if getattr(item, "enabled", False))
        protocols = {}
        bot_count = 0
        try:
            from nonebot import get_bots, get_driver
            driver = get_driver()
            registered = getattr(driver, "_adapters", {})
            adapter_values = registered.values() if isinstance(registered, dict) else registered
            for adapter in adapter_values:
                getter = getattr(adapter, "get_name", None)
                label = getter() if callable(getter) else type(adapter).__name__
                protocols[str(label)] = {"name": str(label), "enabled": True, "bots": 0}
            bots = get_bots()
            bot_count = len(bots)
            for bot in bots.values():
                adapter = getattr(bot, "adapter", None)
                getter = getattr(adapter, "get_name", None)
                label = getter() if callable(getter) else str(getattr(bot, "type", "未知协议"))
                protocols.setdefault(label, {"name": label, "enabled": True, "bots": 0})
                protocols[label]["bots"] += 1
        except Exception:
            logger.debug("读取 NoneBot 协议信息失败", exc_info=True)
        renderer = getattr(runtime, "renderer", None)
        metrics = dict(getattr(renderer, "metrics", {})) if renderer else {}
        return {
            "ok": True, "protocols": list(protocols.values()), "bot_count": bot_count,
            "resources": domains, "resource_count": total_resources,
            "alias_count": aliases_count, "subscription_count": subscription_count,
            "command_count": len(command_items), "enabled_command_count": enabled_commands,
            "renderer": metrics,
        }

    @app.get("/api/previews", dependencies=auth)
    async def previews():
        items = []
        for key, title, template, description in PREVIEW_CATALOG:
            item = {"id": key, "title": title, "template": template, "description": description}
            if override_dir is not None:
                item["template_versions"] = [
                    {"id": "", "title": "内置模板 · " + template},
                    *_version_items(override_dir, "templates", key),
                ]
                item["css_versions"] = [
                    {"id": "", "title": "默认样式"},
                    *_version_items(override_dir, "css", key),
                ]
            item["selected_template"] = selections["templates"].get(key, "")
            item["selected_css"] = selections["css"].get(key, "")
            items.append(item)
        return {"items": items}

    @app.post("/api/previews", dependencies=auth)
    async def render_preview(payload: PreviewInput):
        if payload.template not in {item[0] for item in PREVIEW_CATALOG}:
            raise HTTPException(404, "找不到此预览项目")
        if not getattr(runtime, "renderer", None):
            raise HTTPException(503, "图片渲染器尚未启动")
        try:
            images = await runtime.renderer.render(_preview_card(payload.template))
        except Exception as exc:
            logger.exception("管理台图片预览失败：%s", payload.template)
            raise HTTPException(503, "预览渲染失败：" + str(exc)[:160]) from exc
        if not images:
            raise HTTPException(503, "渲染器没有返回图片")
        return {"template": payload.template,
                "images": [base64.b64encode(image).decode("ascii") for image in images],
                "media_type": "image/webp"}

    if override_dir is not None:
        override_dir.mkdir(parents=True, exist_ok=True)
        selection_file = override_dir / "selections.json"
        if selection_file.is_file():
            try:
                loaded = json.loads(selection_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for key in ("templates", "css"):
                        if isinstance(loaded.get(key), dict):
                            selections[key] = loaded[key]
            except (OSError, ValueError):
                logger.warning("管理台模板选择配置无法读取，将使用默认模板。")
        for key in ("templates", "css"):
            selections[key] = {
                feature: value
                for feature, value in selections[key].items()
                if feature in _feature_ids() and isinstance(value, str)
            }
        for feature in _feature_ids():
            valid_templates = {
                item["id"] for item in _version_items(override_dir, "templates", feature)
            }
            valid_css = {
                item["id"] for item in _version_items(override_dir, "css", feature)
            }
            if selections["templates"].get(feature, "") not in valid_templates | {""}:
                selections["templates"].pop(feature, None)
            if selections["css"].get(feature, "") not in valid_css | {""}:
                selections["css"].pop(feature, None)
        if getattr(runtime, "renderer", None):
            runtime.renderer.configure_admin_overrides(override_dir)
            runtime.renderer.configure_admin_selections(
                selections["templates"], selections["css"]
            )

        @app.get("/api/previews/selection", dependencies=auth)
        async def preview_selections():
            return selections

        @app.put("/api/previews/selection", dependencies=auth)
        async def save_preview_selection(payload: PreviewSelectionInput):
            if payload.feature not in _feature_ids():
                raise HTTPException(404, "找不到此预览功能")
            template_versions = {item["id"] for item in _version_items(override_dir, "templates", payload.feature)}
            css_versions = {item["id"] for item in _version_items(override_dir, "css", payload.feature)}
            if payload.template_version and payload.template_version not in template_versions:
                raise HTTPException(404, "找不到所选模板版本")
            if payload.css_version and payload.css_version not in css_versions:
                raise HTTPException(404, "找不到所选 CSS 版本")
            selections["templates"][payload.feature] = payload.template_version
            selections["css"][payload.feature] = payload.css_version
            temporary = selection_file.with_name(selection_file.name + ".tmp")
            temporary.write_text(json.dumps(selections, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(selection_file)
            runtime.renderer.configure_admin_selections(
                selections["templates"], selections["css"]
            )
            return {"ok": True, "template_version": payload.template_version,
                    "css_version": payload.css_version}

        @app.get("/api/editor/schema", dependencies=auth)
        async def editor_schema(feature: str):
            if feature not in _feature_ids():
                raise HTTPException(404, "找不到此功能")
            return {"feature": feature, "fields": _sample_fields(feature)}

        @app.get("/api/editor/files", dependencies=auth)
        async def editor_files():
            result = []
            for name in sorted(EDITOR_TEMPLATES):
                relative = "templates/" + name
                source, override = _editor_paths(relative, override_dir)
                content = override.read_text(encoding="utf-8") if override.is_file() else source.read_text(encoding="utf-8")
                result.append({"name": relative, "kind": "html",
                               "overridden": override.is_file(), "revision": _file_revision(content)})
            for name in sorted(EDITOR_CSS):
                relative = "css/" + name
                source, override = _editor_paths(relative, override_dir)
                content = override.read_text(encoding="utf-8") if override.is_file() else source.read_text(encoding="utf-8")
                result.append({"name": relative, "kind": "css",
                               "overridden": override.is_file(), "revision": _file_revision(content)})
            for kind, extension in (("templates", "html"), ("css", "css")):
                root = override_dir / kind / "versions"
                if root.is_dir():
                    for path in sorted(root.glob(f"*/*.{extension}")):
                        relative = path.relative_to(override_dir).as_posix()
                        content = path.read_text(encoding="utf-8")
                        result.append({
                            "name": relative,
                            "kind": "html" if kind == "templates" else "css",
                            "overridden": True,
                            "version": True,
                            "revision": _file_revision(content),
                        })
            return {"items": result}

        @app.get("/api/editor/file", dependencies=auth)
        async def editor_file(name: str):
            source, override = _editor_paths(name, override_dir)
            selected = override if override.is_file() else source
            content = selected.read_text(encoding="utf-8")
            return {"name": name, "content": content,
                    "revision": _file_revision(content), "overridden": override.is_file()}

        @app.put("/api/editor/file", dependencies=auth)
        async def save_editor_file(payload: EditorInput):
            if "/versions/" in payload.name:
                raise HTTPException(409, "已保存的版本不可覆盖，请使用“另存为新版本”。")
            source, override = _editor_paths(payload.name, override_dir)
            current_path = override if override.is_file() else source
            current_content = current_path.read_text(encoding="utf-8")
            if not hmac.compare_digest(_file_revision(current_content), payload.revision):
                raise HTTPException(409, "文件已在其他位置更新，请重新载入后再保存。")
            if "\x00" in payload.content:
                raise HTTPException(400, "文件内容包含无效字符")
            if payload.name.startswith("templates/"):
                try:
                    runtime.renderer.environment.from_string(payload.content)
                except TemplateSyntaxError as exc:
                    raise HTTPException(422, f"Jinja 模板语法错误：{exc.message}") from exc
            override.parent.mkdir(parents=True, exist_ok=True)
            temporary = override.with_name(override.name + ".tmp")
            temporary.write_text(payload.content, encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(override)
            runtime.renderer.configure_admin_overrides(override_dir)
            return {"ok": True, "revision": _file_revision(payload.content), "overridden": True}

        @app.delete("/api/editor/file", dependencies=auth)
        async def reset_editor_file(name: str):
            if "/versions/" in name:
                raise HTTPException(409, "版本文件不可删除，以保留历史模板。")
            _, override = _editor_paths(name, override_dir)
            if override.exists():
                override.unlink()
            runtime.renderer.configure_admin_overrides(override_dir)
            runtime.renderer.configure_admin_selections(
                selections["templates"], selections["css"]
            )
            return {"ok": True, "overridden": False}

        @app.post("/api/editor/versions", dependencies=auth)
        async def create_editor_version(payload: EditorVersionInput):
            if payload.feature not in _feature_ids():
                raise HTTPException(404, "找不到此功能")
            if "\x00" in payload.content:
                raise HTTPException(400, "文件内容包含无效字符")
            slug = re.sub(r"[^a-z0-9_-]+", "-", payload.name.casefold()).strip("-_")[:48]
            if not slug:
                slug = "custom"
            kind = "templates" if payload.kind == "html" else "css"
            extension = payload.kind
            directory = override_dir / kind / "versions" / payload.feature
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"{slug}.{extension}"
            suffix = 2
            while target.exists():
                target = directory / f"{slug}-{suffix}.{extension}"
                suffix += 1
            if payload.kind == "html":
                try:
                    runtime.renderer.environment.from_string(payload.content)
                except TemplateSyntaxError as exc:
                    raise HTTPException(422, f"Jinja 模板语法错误：{exc.message}") from exc
            temporary = target.with_name(target.name + ".tmp")
            temporary.write_text(payload.content, encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(target)
            runtime.renderer.configure_admin_overrides(override_dir)
            runtime.renderer.configure_admin_selections(
                selections["templates"], selections["css"]
            )
            relative = target.relative_to(override_dir).as_posix()
            return {"ok": True, "name": kind + "/" + relative.removeprefix(kind + "/"),
                    "revision": _file_revision(payload.content)}

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
        app = create_app(self.runtime, token, directory / "overrides")
        self.server = EmbeddedServer(
            uvicorn.Config(
                app,
                host=config.aawarframe_admin_host,
                port=config.aawarframe_admin_port,
                access_log=True,
                proxy_headers=False,
                log_config=None,
                log_level=None,
                timeout_graceful_shutdown=5,
            )
        )
        self.task = asyncio.create_task(self._serve(), name="aawarframe-admin")
        self.task.add_done_callback(self._done)
        logger.info("管理台 HTTP 端口 %s；口令文件：%s", config.aawarframe_admin_port, token_file)

    async def _serve(self):
        try:
            await self.server.serve()
        except SystemExit as exc:
            # 管理端口冲突不应终止机器人主进程。
            raise RuntimeError("管理台未能启动，请检查端口和监听地址") from exc

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
