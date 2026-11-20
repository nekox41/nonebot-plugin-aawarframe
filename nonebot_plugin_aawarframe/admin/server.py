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
from pathlib import Path
from time import monotonic
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from jinja2 import TemplateSyntaxError
from pydantic import BaseModel, Field

from ..models.common import Card
from ..rendering.preview_data import get_preview_card

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
    html_template: str = Field(min_length=1, max_length=240)
    theme: str = Field(min_length=1, max_length=120)


class EditorVersionInput(BaseModel):
    kind: Literal["html", "css"]
    feature: str = Field(default="global", min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    content: str = Field(max_length=1_000_000)


EDITOR_TEMPLATES = {
    "arbitration.html", "archimedea.html", "attributes.html", "bounties.html",
    "card.html", "challenge_bounties.html", "commands.html", "fissures.html",
    "market.html", "nightwave.html", "operations.html", "relics.html",
    "riven_analysis.html", "riven_market.html", "riven_values.html", "trend.html",
    "void_trader.html", "weekly.html",
}
EDITOR_CSS = {"default.css"}
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


def _rendering_roots():
    root = Path(__file__).parents[1] / "rendering"
    return root / "html", root / "css"


def _editor_paths(name: str, override_dir: Path):
    html_root, css_root = _rendering_roots()
    if name.startswith("html/"):
        relative = name.removeprefix("html/")
        if relative in EDITOR_TEMPLATES:
            return html_root / relative, override_dir / "html" / relative
        match = re.fullmatch(r"versions/([a-z0-9_-]+)/([\\w-]+)\\.html", relative)
        if match:
            feature, filename = match.groups()
            if feature not in _feature_ids():
                raise HTTPException(404, "找不到此 HTML 模板")
            path = override_dir / "html" / relative
            if path.is_file():
                return path, path
    if name.startswith("css/"):
        relative = name.removeprefix("css/")
        if re.fullmatch(r"[\\w-]+\\.css", relative):
            package = css_root / relative
            custom = override_dir / "css" / relative
            if package.is_file() or custom.is_file():
                return (package if package.is_file() else custom), custom
    raise HTTPException(404, "找不到此 HTML 模板或 CSS 主题")


def _html_options(override_dir: Path) -> list[dict[str, str]]:
    html_root, _ = _rendering_roots()
    names = {path.name for path in html_root.glob("*.html") if path.is_file()}
    custom_root = override_dir / "html"
    if custom_root.exists():
        names.update(path.relative_to(custom_root).as_posix() for path in custom_root.rglob("*.html") if path.is_file())
    return [{"id": name, "title": name} for name in sorted(names)]


def _theme_options(override_dir: Path) -> list[dict[str, str]]:
    _, css_root = _rendering_roots()
    names = {path.name for path in css_root.glob("*.css") if path.is_file()}
    custom_root = override_dir / "css"
    if custom_root.exists():
        names.update(path.name for path in custom_root.glob("*.css") if path.is_file())
    return [{"id": name, "title": name} for name in sorted(names)]


def _sample_fields(card: Card, renderer) -> list[dict[str, str]]:
    context = renderer.template_context(card)
    sample = {
        "card": card.model_dump(mode="json"),
        "page": context["page"],
        "total": context["total"],
        "trend_charts": [
            [period.model_dump(mode="json"), chart]
            for period, chart in context["trend_charts"]
        ],
    }
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
        if depth >= 6:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                visit(f"{path}.{key}", child, depth + 1)
        elif isinstance(value, list) and value:
            visit(f"{path}[0]", value[0], depth + 1)

    for key, value in sample.items():
        visit(key if key != "card" else "card", value)
    return fields

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
    selections = {"templates": {}, "theme": "default.css"}

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
        html_options = _html_options(override_dir) if override_dir is not None else [
            {"id": path.name, "title": path.name}
            for path in sorted((Path(__file__).parents[1] / "rendering" / "html").glob("*.html"))
        ]
        theme_options = _theme_options(override_dir) if override_dir is not None else [
            {"id": path.name, "title": path.name}
            for path in sorted((Path(__file__).parents[1] / "rendering" / "css").glob("*.css"))
        ]
        items = []
        for key, title, template, description in PREVIEW_CATALOG:
            items.append({
                "id": key,
                "title": title,
                "template": template,
                "description": description,
                "selected_template": selections["templates"].get(key, template),
                "has_data": True,
            })
        return {"items": items, "html_options": html_options, "theme_options": theme_options,
                "selected_theme": selections["theme"]}

    @app.post("/api/previews", dependencies=auth)
    async def render_preview(payload: PreviewInput):
        if payload.template not in _feature_ids():
            raise HTTPException(404, "找不到此预览项目")
        renderer = getattr(runtime, "renderer", None)
        if renderer is None:
            raise HTTPException(503, "图片渲染器尚未启动")
        try:
            card = get_preview_card(payload.template)
            raw_template = renderer.template_source(card)
            rendered_html = renderer.html(card)
            images = await renderer.render(card)
        except Exception as exc:
            logger.exception("管理台固定数据预览失败：%s", payload.template)
            raise HTTPException(503, "预览渲染失败：" + str(exc)[:160]) from exc
        if not images:
            raise HTTPException(503, "渲染器没有返回图片")
        return {
            "template": payload.template,
            "html_template": renderer._template_name(card),
            "theme": renderer.theme,
            "raw_template": raw_template,
            "rendered_html": rendered_html,
            "images": [base64.b64encode(image).decode("ascii") for image in images],
            "media_type": "image/webp",
        }

    if override_dir is not None:
        override_dir.mkdir(parents=True, exist_ok=True)
        selection_file = override_dir / "selections.json"
        if selection_file.is_file():
            try:
                loaded = json.loads(selection_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    templates = loaded.get("templates")
                    if isinstance(templates, dict):
                        selections["templates"] = templates
                    if isinstance(loaded.get("theme"), str):
                        selections["theme"] = loaded["theme"]
            except (OSError, ValueError):
                logger.warning("管理台 HTML/CSS 选择配置无法读取，将使用默认配置。")
        html_names = {item["id"] for item in _html_options(override_dir)}
        theme_names = {item["id"] for item in _theme_options(override_dir)}
        selections["templates"] = {
            feature: value for feature, value in selections["templates"].items()
            if feature in _feature_ids() and isinstance(value, str) and value in html_names
        }
        if selections["theme"] not in theme_names:
            selections["theme"] = "default.css"
        if getattr(runtime, "renderer", None):
            runtime.renderer.configure_admin_overrides(override_dir)
            runtime.renderer.configure_admin_selections(
                selections["templates"], selections["theme"]
            )

        def persist_selections():
            temporary = selection_file.with_name(selection_file.name + ".tmp")
            temporary.write_text(json.dumps(selections, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(selection_file)

        @app.get("/api/previews/selection", dependencies=auth)
        async def preview_selections():
            return selections

        @app.put("/api/previews/selection", dependencies=auth)
        async def save_preview_selection(payload: PreviewSelectionInput):
            if payload.feature not in _feature_ids():
                raise HTTPException(404, "找不到此预览功能")
            if payload.html_template not in {item["id"] for item in _html_options(override_dir)}:
                raise HTTPException(404, "找不到所选 HTML 模板")
            if payload.theme not in {item["id"] for item in _theme_options(override_dir)}:
                raise HTTPException(404, "找不到所选 CSS 主题")
            selections["templates"][payload.feature] = payload.html_template
            selections["theme"] = payload.theme
            persist_selections()
            runtime.renderer.configure_admin_selections(selections["templates"], selections["theme"])
            return {"ok": True, "feature": payload.feature,
                    "html_template": payload.html_template, "theme": payload.theme}

        @app.get("/api/editor/schema", dependencies=auth)
        async def editor_schema(feature: str):
            if feature not in _feature_ids():
                raise HTTPException(404, "找不到此功能")
            card = get_preview_card(feature)
            return {
                "feature": feature,
                "data_source": "rendering/preview_data.py",
                "fields": _sample_fields(card, runtime.renderer),
            }

        @app.get("/api/editor/files", dependencies=auth)
        async def editor_files():
            result = []
            for name in sorted(EDITOR_TEMPLATES):
                relative = "html/" + name
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
            custom_html = override_dir / "html" / "versions"
            if custom_html.is_dir():
                for path in sorted(custom_html.rglob("*.html")):
                    if path.is_file():
                        content = path.read_text(encoding="utf-8")
                        result.append({
                            "name": "html/" + path.relative_to(override_dir / "html").as_posix(),
                            "kind": "html", "overridden": True, "version": True,
                            "revision": _file_revision(content),
                        })
            custom_css = override_dir / "css"
            if custom_css.is_dir():
                for path in sorted(custom_css.glob("*.css")):
                    if path.is_file() and path.name not in EDITOR_CSS:
                        content = path.read_text(encoding="utf-8")
                        result.append({
                            "name": "css/" + path.name, "kind": "css",
                            "overridden": True, "theme": True,
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
                raise HTTPException(409, "已保存的 HTML 版本不可覆盖，请另存为新版本。")
            source, override = _editor_paths(payload.name, override_dir)
            current_path = override if override.is_file() else source
            current_content = current_path.read_text(encoding="utf-8")
            if not hmac.compare_digest(_file_revision(current_content), payload.revision):
                raise HTTPException(409, "文件已在其他位置更新，请重新载入后再保存。")
            if "\x00" in payload.content:
                raise HTTPException(400, "文件内容包含无效字符")
            if payload.name.startswith("html/"):
                if "{% extends" in payload.content or "{% block " in payload.content:
                    raise HTTPException(422, "HTML 模板必须是独立完整页面，不支持 extends/block 继承。")
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
            runtime.renderer.configure_admin_selections(selections["templates"], selections["theme"])
            return {"ok": True, "revision": _file_revision(payload.content), "overridden": True}

        @app.delete("/api/editor/file", dependencies=auth)
        async def delete_editor_file(name: str):
            source, override = _editor_paths(name, override_dir)
            if "/versions/" in name:
                if not override.is_file():
                    raise HTTPException(404, "自定义文件不存在")
                relative = override.relative_to(override_dir / ("html" if name.startswith("html/") else "css")).as_posix()
                override.unlink()
                if name.startswith("html/"):
                    for feature, selected in list(selections["templates"].items()):
                        if selected == relative:
                            selections["templates"].pop(feature, None)
                elif selections["theme"] == override.name:
                    selections["theme"] = "default.css"
            elif override.exists():
                override.unlink()
            else:
                raise HTTPException(409, "内置文件不能直接删除；只能删除自定义版本或恢复本地覆盖。")
            persist_selections()
            runtime.renderer.configure_admin_overrides(override_dir)
            runtime.renderer.configure_admin_selections(selections["templates"], selections["theme"])
            return {"ok": True, "deleted": True, "selections": selections}

        @app.post("/api/editor/versions", dependencies=auth)
        async def create_editor_version(payload: EditorVersionInput):
            if payload.kind == "html" and payload.feature not in _feature_ids():
                raise HTTPException(404, "找不到此功能")
            if "\x00" in payload.content:
                raise HTTPException(400, "文件内容包含无效字符")
            slug = re.sub(r"[^\w-]+", "-", payload.name.casefold()).strip("-_")[:48] or "custom"
            if payload.kind == "html":
                if "{% extends" in payload.content or "{% block " in payload.content:
                    raise HTTPException(422, "HTML 模板必须是独立完整页面，不支持 extends/block 继承。")
                if "<html" not in payload.content.casefold():
                    raise HTTPException(422, "HTML 模板必须包含完整的 html 文档结构。")
                try:
                    runtime.renderer.environment.from_string(payload.content)
                except TemplateSyntaxError as exc:
                    raise HTTPException(422, f"Jinja 模板语法错误：{exc.message}") from exc
                directory = override_dir / "html" / "versions" / payload.feature
                extension = "html"
            else:
                directory = override_dir / "css"
                extension = "css"
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"{slug}.{extension}"
            suffix = 2
            while target.exists():
                target = directory / f"{slug}-{suffix}.{extension}"
                suffix += 1
            temporary = target.with_name(target.name + ".tmp")
            temporary.write_text(payload.content, encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(target)
            runtime.renderer.configure_admin_overrides(override_dir)
            runtime.renderer.configure_admin_selections(selections["templates"], selections["theme"])
            relative = target.relative_to(override_dir).as_posix()
            return {"ok": True, "name": relative, "revision": _file_revision(payload.content)}


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
    def record_preview(self, feature: str, arguments: str, card: Card) -> None:
        """Kept as a no-op compatibility hook; WebUI previews use fixed source fixtures."""
        return

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
