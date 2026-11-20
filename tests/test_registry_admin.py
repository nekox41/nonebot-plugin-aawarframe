# 作用：验证统一物品目录、交易筛选、JSON 映射迁移和简化后的别名接口。
# 编写日期：2026-11-13
# 作者：Aameow

import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from nonebot_plugin_aawarframe.admin.server import create_app
from nonebot_plugin_aawarframe.grq import GameResourceQuery, configure_grq
from nonebot_plugin_aawarframe.models.common import Snapshot
from nonebot_plugin_aawarframe.models.wiki import OpenSearchResponse
from nonebot_plugin_aawarframe.services.wiki import WikiService

BURSTON = "/Lotus/Weapons/Tenno/Rifle/BurstRifle"


@pytest.fixture(scope="module")
def grq(tmp_path_factory, test_assets_root):
    from nonebot_plugin_aawarframe.localization.resources import configure_resources

    if test_assets_root is not None:
        configure_resources(test_assets_root)
    query = GameResourceQuery(tmp_path_factory.mktemp("unified") / "registry.sqlite3")
    yield query
    query.close()
    configure_grq(None)


def test_unified_items_and_shared_aliases(grq):
    assert "Market" not in grq.domains
    assert len(grq.domains["Items"].resources) >= 20000
    assert len(grq.market_index.resources) == 3893
    saryn = grq.search("Items", "Saryn").resource
    assert not saryn.metadata.get("market_tradable")
    grq.add_alias(saryn.id, "毒妈")
    assert grq.search("Items", "毒妈").resource.id == saryn.id
    product = grq.search_market("毒妈").resource
    assert product.identifiers["market.slug"] == "saryn_prime_set"
    assert product.metadata["market_tradable"]
    assert grq.get("Items", "saryn_prime_set", "market.slug").id == product.id
    burston = {grq.get("Items", item).names.get("en") for item in grq.item_family("burston")}
    assert {"Burston", "Burston Prime"} <= burston
    braton = {grq.get("Items", item).names.get("en", "").casefold()
              for item in grq.item_family("braton")}
    assert {"braton", "braton prime", "mk1-braton"} <= braton
    grq.add_alias(BURSTON, "统一武器别名")
    assert grq.search("Riven", "统一武器别名").resource.id == "burston"
    assert (
        grq.search_market("统一武器别名").resource.identifiers["market.slug"] == "burston_prime_set"
    )
    with pytest.raises(ValueError, match="其他物品"):
        grq.add_alias(BURSTON, "毒妈")
    grq.delete_alias(BURSTON, "统一武器别名")
    assert "统一武器别名" not in grq.market_index.names
    assert "统一武器别名" not in grq.domains["Riven"].names


async def test_wiki_preserves_base_item_and_unknown_input(grq):
    configure_grq(grq)
    provider = SimpleNamespace(
        search=AsyncMock(return_value=Snapshot(data=OpenSearchResponse.model_validate(["毒妈", ["毒妈"], ["简介"], ["https://warframe.huijiwiki.com/wiki/test"]]).to_result(), source="test"))
    )
    service = WikiService(provider)
    try:
        await service.search("毒妈")
        provider.search.assert_awaited_with("毒妈")
        await service.search("未知资料XYZ")
        provider.search.assert_awaited_with("未知资料XYZ")
    finally:
        service.close()


def test_json_mappings_and_queries_use_no_sql(grq):
    queries = []
    grq.db.set_trace_callback(queries.append)
    table = "/Lotus/Types/Game/MissionDecks/DeimosMissionRewards/TierATableARewards"
    assert len(grq.mapping("bounty_drops.json")[table]) == 4
    assert grq.get("Node", "SolNode1")
    assert grq.mapping("earth_bounty_locations.json")["locations"][0]["Jobs"][0]["name"]
    assert grq.get("Riven", "boar").metadata["weapon_type"] == "shotgun"
    grq.search_market("毒妈")
    grq.search("Items", "伯斯顿")
    grq.db.set_trace_callback(None)
    assert queries == []
    tables = {r[0] for r in grq.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {
        "item_catalog", "item_aliases", "item_overrides", "catalog_meta", "settings",
        "items", "aliases", "market_products", "market_aliases",
    }


async def test_alias_api_and_removed_admin_endpoints(grq):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=create_app(SimpleNamespace(grq=grq), "long-test-password-12345")
        ),
        base_url="https://test",
    ) as client:
        assert (await client.get("/api/aliases")).status_code == 401
        client.headers["Authorization"] = "Bearer long-test-password-12345"
        result = (await client.get("/api/items", params={"q": "伯斯顿"})).json()
        assert any(r["id"] == BURSTON for r in result["items"])
        payload = {"item_id": BURSTON, "alias": "页面选择物品别名"}
        assert (await client.post("/api/aliases", json=payload)).status_code == 200
        assert any(
            r["alias"] == payload["alias"]
            for r in (await client.get("/api/aliases")).json()["items"]
        )
        assert (await client.request("DELETE", "/api/aliases", json=payload)).status_code == 200
        dashboard = (await client.get("/api/status")).json()
        assert dashboard["ok"] and dashboard["resource_count"] >= 20000
        assert dashboard["alias_count"] >= 0
        assert any(item["name"] == "Market" for item in dashboard["resources"])
        assert (await client.get("/api/previews")).json()["items"]
        assert (await client.post("/api/previews", json={"template": "unknown"})).status_code == 404
        for endpoint in ("domains", "resources", "settings", "review", "export"):
            assert (await client.get("/api/" + endpoint)).status_code == 404
        policy = (await client.get("/")).headers["content-security-policy"]
        assert "img-src 'self' data:" in policy


def test_old_aliases_and_mapping_changes_are_preserved(grq, tmp_path):
    path = tmp_path / "registry.sqlite3"
    saryn = grq.search("Items", "Saryn").resource
    node = grq.get("Node", "SolNode1")
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE grq_resources(domain TEXT,id TEXT,source TEXT,payload TEXT,version TEXT,updated_at TEXT);
        CREATE TABLE grq_overrides(domain TEXT,id TEXT,patch TEXT,revision INTEGER);
        CREATE TABLE grq_aliases(domain TEXT,id TEXT,name TEXT,enabled INTEGER);
    """)
    db.executemany(
        "INSERT INTO grq_resources VALUES(?,?,?,?,?,?)",
        [
            ("Items", saryn.id, "wfcd", saryn.model_dump_json(), "old", "2026-11-13"),
            (
                "Node",
                node.id,
                "json:ExportRegions_zh.json",
                node.model_dump_json(),
                "old",
                "2026-11-13",
            ),
        ],
    )
    db.execute(
        "INSERT INTO grq_overrides VALUES(?,?,?,1)",
        ("Node", node.id, json.dumps({"names": {"zh-hans": "人工节点名称"}})),
    )
    db.execute("INSERT INTO grq_aliases VALUES(?,?,?,1)", ("Items", saryn.id, "迁移后的毒妈"))
    db.commit()
    db.close()
    query = GameResourceQuery(path)
    assert (
        query.search_market("迁移后的毒妈").resource.identifiers["market.slug"] == "saryn_prime_set"
    )
    assert query.get("Node", node.id).name() == "人工节点名称"
    assert (
        json.loads((tmp_path / "mappings/ExportRegions_zh.json").read_text())[node.id]["name"]
        == "人工节点名称"
    )
    assert path.with_name("registry.pre-unified-items.sqlite3").exists()
    query.close()


def test_preview_catalog_has_no_synthetic_data():
    from nonebot_plugin_aawarframe.admin.server import PREVIEW_CATALOG

    assert len(PREVIEW_CATALOG) == 22
    assert len({item[0] for item in PREVIEW_CATALOG}) == len(PREVIEW_CATALOG)


def test_admin_server_captures_complete_card_by_real_command(grq, tmp_path):
    from nonebot_plugin_aawarframe.admin.server import AdminServer
    from nonebot_plugin_aawarframe.models.common import Card, CycleDisplay
    from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer

    renderer = CardRenderer()
    runtime = SimpleNamespace(renderer=renderer)
    config = SimpleNamespace(aawarframe_cache_dir=tmp_path)
    admin = AdminServer(runtime, config)
    card = Card(
        title="真实平原总览",
        source="https://api.warframe.com/cdn/worldState.php",
        cycle_items=[
            CycleDisplay(name="夜灵平原", state="白天", next_state="黑夜", remaining="8 分钟")
        ],
    )
    admin.record_preview("plains", "", card)
    record = admin.preview_store.for_preview("cycles")
    assert record["feature"] == "plains"
    assert record["card"]["title"] == "真实平原总览"
    assert record["card"]["cycle_items"][0]["name"] == "夜灵平原"
    assert (tmp_path / "admin" / "preview-data.json").is_file()
    import asyncio
    asyncio.run(renderer.close())


async def test_preview_api_renders_persisted_real_command_card(grq, tmp_path):
    from nonebot_plugin_aawarframe.admin.preview_data import PreviewDataStore
    from nonebot_plugin_aawarframe.models.common import Card
    from nonebot_plugin_aawarframe.models.operations import OperationBoard

    renderer = SimpleNamespace(
        render=AsyncMock(return_value=[b"webp-preview"]),
        metrics={},
    )
    store = PreviewDataStore(tmp_path / "admin" / "preview-data.json")
    card = Card(
        title="真实突击数据",
        source="https://api.warframe.com/cdn/worldState.php",
        operation_board=OperationBoard(kind="sortie"),
    )
    store.record("sortie", "sortie", "", card)
    runtime = SimpleNamespace(grq=grq, renderer=renderer, admin=SimpleNamespace(preview_store=store))
    app = create_app(runtime, "long-test-password-12345")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        client.headers["Authorization"] = "Bearer long-test-password-12345"
        response = await client.post("/api/previews", json={"template": "sortie"})
        assert response.status_code == 200
        assert response.json()["images"] == ["d2VicC1wcmV2aWV3"]
        assert response.json()["data_feature"] == "sortie"
        rendered_card = renderer.render.await_args.args[0]
        assert rendered_card.title == "真实突击数据"
        renderer.render.assert_awaited_once()


async def test_preview_without_real_command_data_returns_conflict(grq, tmp_path):
    from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer

    renderer = CardRenderer()
    app = create_app(
        SimpleNamespace(grq=grq, renderer=renderer),
        "long-test-password-12345",
        tmp_path / "admin" / "overrides",
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = "Bearer long-test-password-12345"
        response = await client.post("/api/previews", json={"template": "sortie"})
        assert response.status_code == 409
        assert "真实命令数据" in response.json()["detail"]
    await renderer.close()


async def test_editor_persists_overrides_and_hot_reloads_renderer(grq, tmp_path):
    from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer

    renderer = CardRenderer()
    app = create_app(
        SimpleNamespace(grq=grq, renderer=renderer),
        "long-test-password-12345",
        tmp_path / "admin-overrides",
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        client.headers["Authorization"] = "Bearer long-test-password-12345"
        files = (await client.get("/api/editor/files")).json()["items"]
        assert any(item["name"] == "templates/card.html" for item in files)
        source = (await client.get("/api/editor/file", params={"name": "css/base.css"})).json()
        marker = "\\n/* webui-live-override */"
        changed = source["content"] + marker
        saved = await client.put(
            "/api/editor/file",
            json={"name": "css/base.css", "content": changed, "revision": source["revision"]},
        )
        assert saved.status_code == 200
        assert "webui-live-override" in renderer.css
        current = (await client.get("/api/editor/file", params={"name": "css/base.css"})).json()
        assert current["overridden"] and current["content"] == changed
        invalid = await client.put(
            "/api/editor/file",
            json={"name": "templates/card.html", "content": "{% if broken %}",
                  "revision": (await client.get("/api/editor/file", params={"name": "templates/card.html"})).json()["revision"]},
        )
        assert invalid.status_code == 422
        reset = await client.delete("/api/editor/file", params={"name": "css/base.css"})
        assert reset.status_code == 200
        assert "webui-live-override" not in renderer.css
    await renderer.close()


async def test_versioned_templates_and_css_use_real_card_snapshot(grq, tmp_path):
    from nonebot_plugin_aawarframe.admin.preview_data import PreviewDataStore
    from nonebot_plugin_aawarframe.models.common import Card, CycleDisplay
    from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer

    renderer = CardRenderer()
    admin_dir = tmp_path / "admin"
    override_dir = admin_dir / "overrides"
    store = PreviewDataStore(admin_dir / "preview-data.json")
    card = Card(
        title="真实平原周期",
        source="https://api.warframe.com/cdn/worldState.php",
        cycle_items=[
            CycleDisplay(
                name="夜灵平原",
                state="白天",
                next_state="黑夜",
                remaining="12 分钟",
                remaining_short="12:00",
            )
        ],
    )
    store.record("plains", "cycles", "", card)
    runtime = SimpleNamespace(grq=grq, renderer=renderer, admin=SimpleNamespace(preview_store=store))
    app = create_app(runtime, "long-test-password-12345", override_dir)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.headers["Authorization"] = "Bearer long-test-password-12345"
        schema_response = await client.get("/api/editor/schema", params={"feature": "cycles"})
        assert schema_response.status_code == 200
        schema = schema_response.json()
        assert schema["data_feature"] == "plains"
        assert any(field["path"] == "card.cycle_items[0].name" for field in schema["fields"])

        template = await client.post(
            "/api/editor/versions",
            json={
                "kind": "html",
                "feature": "cycles",
                "name": "Tenno layout",
                "content": (
                    "<html><head></head><body>"
                    "{{ card.cycle_items[0].name }}"
                    "</body></html>"
                ),
            },
        )
        assert template.status_code == 200
        template_name = template.json()["name"]
        assert template_name == "templates/versions/cycles/tenno-layout.html"

        css = await client.post(
            "/api/editor/versions",
            json={
                "kind": "css",
                "feature": "cycles",
                "name": "Soft colors",
                "content": ".cycle { color: rgb(12, 34, 56); }",
            },
        )
        assert css.status_code == 200
        css_name = css.json()["name"]
        assert css_name == "css/versions/cycles/soft-colors.css"

        selected = await client.put(
            "/api/previews/selection",
            json={
                "feature": "cycles",
                "template_version": template_name.removeprefix("templates/"),
                "css_version": css_name.removeprefix("css/"),
            },
        )
        assert selected.status_code == 200

        persisted = store.for_preview("cycles")
        restored_card = Card.model_validate(persisted["card"])
        assert renderer._template_name(restored_card) == "versions/cycles/tenno-layout.html"
        assert "rgb(12, 34, 56)" in renderer._css_for_card(restored_card)
        assert "夜灵平原" in renderer.html(restored_card)

        versions = (await client.get("/api/editor/files")).json()["items"]
        assert any(item["name"] == template_name and item["version"] for item in versions)
        assert any(item["name"] == css_name and item["version"] for item in versions)

        blocked = await client.put(
            "/api/editor/file",
            json={"name": template_name, "content": "changed", "revision": "0" * 64},
        )
        assert blocked.status_code == 409

        previews = (await client.get("/api/previews")).json()["items"]
        cycles = next(item for item in previews if item["id"] == "cycles")
        assert cycles["has_data"] is True
        assert cycles["data_feature"] == "plains"
        assert cycles["selected_template"] == "versions/cycles/tenno-layout.html"
        assert cycles["selected_css"] == "versions/cycles/soft-colors.css"

    restored_store = PreviewDataStore(admin_dir / "preview-data.json")
    restored_renderer = CardRenderer()
    restored_runtime = SimpleNamespace(
        grq=grq,
        renderer=restored_renderer,
        admin=SimpleNamespace(preview_store=restored_store),
    )
    create_app(restored_runtime, "long-test-password-12345", override_dir)
    restored_record = restored_store.for_preview("cycles")
    assert Card.model_validate(restored_record["card"]).title == "真实平原周期"
    assert restored_renderer._template_name(Card.model_validate(restored_record["card"])) == "versions/cycles/tenno-layout.html"
    assert "rgb(12, 34, 56)" in restored_renderer._css_for_card(Card.model_validate(restored_record["card"]))
    await restored_renderer.close()
    await renderer.close()


async def test_admin_server_uses_plain_http(grq, tmp_path, monkeypatch):
    import asyncio

    from nonebot_plugin_aawarframe.admin import server as admin_module
    from nonebot_plugin_aawarframe.admin.server import AdminServer

    class DummyServer:
        def __init__(self, config):
            self.config = config
            self.should_exit = False

        async def serve(self):
            while not self.should_exit:
                await asyncio.sleep(0)

    monkeypatch.setattr(admin_module, "EmbeddedServer", DummyServer)
    config = SimpleNamespace(
        aawarframe_cache_dir=tmp_path,
        aawarframe_admin_password=None,
        aawarframe_admin_host="127.0.0.1",
        aawarframe_admin_port=8087,
    )
    admin = AdminServer(SimpleNamespace(grq=grq, renderer=None), config)
    admin.start()
    assert admin.server.config.ssl_certfile is None
    assert admin.server.config.ssl_keyfile is None
    await admin.close()
