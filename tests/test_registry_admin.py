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


@pytest.mark.parametrize("template", [
    "card", "cycles", "fissures", "arbitration", "market", "sortie", "archon", "invasions",
    "parts", "relics",
    "trend", "riven_analysis", "attributes", "commands", "riven_market", "riven_values",
    "void_trader", "weekly", "nightwave", "archimedea", "bounties", "challenge_bounties",
])
def test_preview_catalog_cards_are_valid(template):
    from nonebot_plugin_aawarframe.admin.server import _preview_card

    card = _preview_card(template)
    assert card.title
    assert card.source == "AAWarframe · WebUI 预览"


async def test_preview_api_renders_local_sample_without_upstream_requests(grq):
    renderer = SimpleNamespace(
        render=AsyncMock(return_value=[b"webp-preview"]),
        metrics={},
    )
    app = create_app(SimpleNamespace(grq=grq, renderer=renderer), "long-test-password-12345")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        client.headers["Authorization"] = "Bearer long-test-password-12345"
        response = await client.post("/api/previews", json={"template": "sortie"})
        assert response.status_code == 200
        assert response.json()["images"] == ["d2VicHAtcHJldmlldw=="]
        renderer.render.assert_awaited_once()


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
