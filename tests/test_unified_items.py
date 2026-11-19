"""Issue #9: verified identities, isolated offers and fixed Riven disposition."""

import sqlite3

from nonebot_plugin_aawfcore.grq.models import Resource
from nonebot_plugin_aawfcore.grq.storage import connect
from nonebot_plugin_aawfcore.grq.unified import load_catalog, persist_catalog, report_unmatched
from nonebot_plugin_aawfcore.services.riven_values import numerical_value

BASE = "/Lotus/Weapons/Tenno/Rifle/BurstRifle"
MK1 = "/Lotus/Weapons/Tenno/Rifle/MK1BurstRifle"
PRIME = "/Lotus/Weapons/Tenno/Rifle/BurstRiflePrime"


def weapon(key, name, slug=None):
    return Resource(
        id=key,
        names={"en": name, "zh-hans": name},
        identifiers={"game.ref": key, **({"market.slug": slug} if slug else {})},
        metadata={"category": "Primary", "market_tradable": bool(slug)},
    )


def test_variants_share_riven_key_without_disposition_metadata(tmp_path):
    db = connect(tmp_path / "registry.sqlite3")
    resources = {
        BASE: weapon(BASE, "Burston"),
        MK1: weapon(MK1, "MK1-Burston"),
        PRIME: weapon(PRIME, "Burston Prime", "burston_prime_set"),
        "market:unmapped_offer": Resource(
            id="market:unmapped_offer",
            names={"en": "Unknown offer"},
            identifiers={"market.slug": "unmapped_offer"},
            metadata={"market_tradable": True, "market_source_game_ref": "/Unknown"},
        ),
    }
    riven = Resource(
        id="burston",
        names={"en": "Burston"},
        identifiers={"game.ref": BASE},
    )
    persist_catalog(db, resources, [], {"burston": riven})
    rows = db.execute(
        "SELECT id,item_path,riven_key,wm_slug FROM items ORDER BY id"
    ).fetchall()
    assert len(rows) == 3
    assert {row["riven_key"] for row in rows} == {"burston"}
    assert {row["item_path"] for row in rows} == {BASE, MK1, PRIME}
    assert next(row["wm_slug"] for row in rows if row["id"] == PRIME) == "burston_prime_set"
    assert next(row["wm_slug"] for row in rows if row["id"] == BASE) is None
    assert set(load_catalog(db)) == set(resources)
    assert report_unmatched(db)["counts"] == {"unmatched_game_ref": 1}
    db.close()


def test_legacy_aliases_migrate_once_and_survive_refresh(tmp_path):
    db = connect(tmp_path / "registry.sqlite3")
    db.execute(
        "INSERT INTO item_aliases(item_id,name,key) VALUES(?,?,?)",
        (BASE, "伯斯顿昵称", "伯斯顿昵称"),
    )
    resource = {BASE: weapon(BASE, "Burston")}
    persist_catalog(db, resource, [], {})
    assert db.execute("SELECT COUNT(*) FROM aliases").fetchone()[0] == 1
    db.execute("DELETE FROM aliases")
    persist_catalog(db, resource, [], {})
    assert db.execute("SELECT COUNT(*) FROM aliases").fetchone()[0] == 0
    db.close()


def test_duplicate_market_slug_is_rejected_without_partial_insert(tmp_path):
    db = connect(tmp_path / "registry.sqlite3")
    resources = {
        BASE: weapon(BASE, "Burston", "shared_slug"),
        PRIME: weapon(PRIME, "Burston Prime", "shared_slug"),
    }
    try:
        persist_catalog(db, resources, [], {})
    except ValueError as exc:
        assert "市场商品" in str(exc)
    else:
        raise AssertionError("Expected duplicate market slug rejection")
    assert db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    db.close()


def test_fixed_riven_multiplier_is_compatible_with_1_2_disposition():
    attribute = {
        "coefficients": {"rifle": 1.0}, "unit": "flat", "inverse": False,
    }
    assert numerical_value(attribute, "rifle", 1.0, 1.2, quality=1) > 0
