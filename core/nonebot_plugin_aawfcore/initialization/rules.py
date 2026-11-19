# 作用：预处理紫卡分类、跨域别名对应和按来源组织的完整奖励表。
# 编写日期：2026-11-14
# 作者：Aameow

import gzip
import json
from collections import defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "nonebot_plugin_aawarframe/assets/grq"


def read(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def dump(name, payload):
    with gzip.open(OUT / name, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def download(url, path):
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    with urlopen(
        Request(
            url,
            headers={
                "User-Agent": "AAWarframe/0.15 (https://github.com/nekox41/nonebot-plugin-aawarframe)"
            },
        ),
        timeout=15,
    ) as response:
        return json.load(response)


def main(riven_input=None, drops_input=None, output=None):
    global OUT
    if output is not None:
        OUT = output
    items = read(OUT / "items.json.gz")["resources"]
    by_ref = {r["id"].casefold(): r for r in items}
    by_name = defaultdict(list)
    for r in items:
        by_name[r["names"].get("en", "").casefold()].append(r)

    def item_for(name):
        hits = by_name.get(name.casefold(), [])
        return hits[0] if len(hits) == 1 else None

    rows = download("https://api.warframe.market/v2/riven/weapons", riven_input)["data"]
    rivens = []
    labels = {
        "rifle": "步枪",
        "pistol": "手枪",
        "shotgun": "霰弹枪",
        "melee": "近战",
        "zaw": "组合近战",
        "kitgun": "组合枪",
        "archgun": "重型武器",
        "archmelee": "Archwing 近战",
        "companion": "同伴武器",
        "unknown": "未分类",
    }
    for row in rows:
        item = by_ref.get(row.get("gameRef", "").casefold()) or item_for(row["i18n"]["en"]["name"])
        kind = row["rivenType"]
        group = row.get("group", "")
        if group in {"archgun", "archmelee"}:
            kind = group
        if item and item["metadata"].get("category") == "SentinelWeapons":
            kind = "companion"
        if item and item["metadata"].get("type") == "Arch-Gun":
            kind = "archgun"
        if item and item["metadata"].get("type") == "Arch-Melee":
            kind = "archmelee"
        tags = list(
            dict.fromkeys(
                [
                    kind,
                    group,
                    *(
                        [item["metadata"].get("type", "").casefold().replace(" ", "_")]
                        if item
                        else []
                    ),
                ]
            )
        )
        rivens.append(
            {
                "id": row["slug"],
                "identifiers": {
                    "riven.compatibility": row["i18n"]["en"]["name"],
                    "market.riven_id": row["id"],
                    **({"game.ref": row["gameRef"]} if row.get("gameRef") else {}),
                },
                "names": item["names"]
                if item
                else {lang: v["name"] for lang, v in row["i18n"].items()},
                "metadata": {
                    **row,
                    "weapon_type": kind,
                    "weapon_type_label": labels.get(kind, kind),
                    "weapon_class": item["metadata"].get("type") if item else None,
                    "tags": tags,
                },
            }
        )
    dump(
        "riven.json.gz",
        {
            "domain": "Riven",
            "version": 1,
            "source": "https://api.warframe.market/v2/riven/weapons",
            "resources": rivens,
        },
    )
    from ..grq.links import generate_links
    from ..grq.models import Resource

    links = generate_links(
        {r["id"]: Resource(**r) for r in items},
        {r["id"]: Resource(**r) for r in read(OUT / "market.json.gz")["resources"]},
        {r["id"]: Resource(**r) for r in rivens},
    )
    dump("alias-links.json.gz", {"version": 1, "links": links})
    official = download(
        "https://raw.githubusercontent.com/WFCD/warframe-drop-data/main/data/all.json",
        drops_input,
    )
    tables = {}

    def reward(raw):
        name = raw.get("itemName") or raw.get("modName") or raw.get("item") or raw.get("name")
        if not name:
            raise ValueError("奖励缺少名称")
        item = item_for(name)
        return {
            "item_id": item["id"] if item else None,
            "name": item["names"].get("zh-hans", name) if item else name,
            "name_en": name,
            "quantity": raw.get("itemCount", raw.get("quantity", 1)),
            "probability": float(raw["chance"]) / 100 if raw.get("chance") is not None else None,
            "rarity": raw.get("rarity"),
            **({"stage": raw["stage"]} if raw.get("stage") else {}),
        }

    def add(key, title, rotations, kind, extra=None):
        if isinstance(rotations, list):
            grouped = defaultdict(list)
            for row in rotations:
                grouped[row.get("rotation", "default")].append(row)
            rotations = grouped
        blocks = []
        for rotation, entries in rotations.items():
            stage_groups = defaultdict(list)
            for entry in entries:
                stage_groups[entry.get("stage", "")].append(entry)
            for stage, rows in stage_groups.items():
                if rows:
                    blocks.append(
                        {
                            "id": str(rotation) + (":" + stage if stage else ""),
                            "label": str(rotation) + (" · " + stage if stage else ""),
                            "rewards": [reward(row) for row in rows],
                        }
                    )
        if blocks:
            tables[key] = {
                "id": key,
                "names": {"en": title, "zh-hans": title},
                "identifiers": {"drop.source": key},
                "metadata": {
                    "kind": kind,
                    "rotations": blocks,
                    "provenance": "https://www.warframe.com/droptables",
                    **(extra or {}),
                },
            }

    for planet, nodes in official["missionRewards"].items():
        for node, data in nodes.items():
            add(
                "mission:" + planet + "/" + node,
                planet + " / " + node,
                data["rewards"],
                "mission",
                {"game_mode": data.get("gameMode")},
            )
    for row in official["relics"]:
        number = row.get("relicName") or ("source-" + row["_id"])
        key = "relic:" + row["tier"] + " " + number
        title = row["tier"] + " " + (row.get("relicName") or "未提供编号") + " Relic"
        existing = tables.get(key, {}).get("metadata", {}).get("rotations", [])
        add(key, title, {row["state"]: row["rewards"]}, "relic")
        tables[key]["metadata"]["rotations"] = existing + tables[key]["metadata"]["rotations"]
    for section, keyfield in [("transientRewards", "objectiveName"), ("keyRewards", "keyName")]:
        for row in official[section]:
            add(section + ":" + row[keyfield], row[keyfield], row["rewards"], section)
    add("sortie:daily", "突击奖励", official["sortieRewards"], "sortie")
    for section in [
        "cetusBountyRewards",
        "solarisBountyRewards",
        "deimosRewards",
        "zarimanRewards",
        "entratiLabRewards",
        "hexRewards",
    ]:
        for row in official.get(section, []):
            add(section + ":" + row["bountyLevel"], row["bountyLevel"], row["rewards"], "bounty")
    for section, keyfield, entries, chance in [
        ("enemyModTables", "enemyName", "mods", "enemyModDropChance"),
        ("enemyBlueprintTables", "enemyName", "items", "enemyItemDropChance"),
        ("resourceByAvatar", "source", "items", None),
        ("sigilByAvatar", "source", "items", None),
        ("additionalItemByAvatar", "source", "items", None),
    ]:
        for row in official.get(section, []):
            extra = (
                {"drop_probability": float(row[chance]) / 100}
                if chance and row.get(chance) is not None
                else {}
            )
            add(section + ":" + row[keyfield], row[keyfield], row[entries], section, extra)
    # 供应商库存不属于随机掉落表，不混入奖励表。
    dump(
        "droptables.json.gz",
        {
            "domain": "Droptable",
            "version": 1,
            "source": "https://www.warframe.com/droptables",
            "resources": list(tables.values()),
        },
    )
    print(
        "Prepared",
        len(rivens),
        "classified Rivens,",
        len(links),
        "alias links,",
        len(tables),
        "drop tables",
    )
