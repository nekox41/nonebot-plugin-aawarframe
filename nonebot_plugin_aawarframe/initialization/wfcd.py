# 作用：下载固定版本 WFCD 目录，预处理完整物品和多语言资料供 SQLite 初始化。
# 编写日期：2026-11-14
# 作者：Aameow

import concurrent.futures
import gzip
import io
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

REVISION = "23804b64bc248069ce39adb9f52e9f546d8f343e"
CATEGORIES = "Arcanes Arch-Gun Arch-Melee Archwing Components Enemy Fish Gear Glyphs Honoria Melee Misc Mods Node Pets Primary Quests Railjack Relics Resources Secondary SentinelWeapons Sentinels Sigils Skins Warframes".split()
LANGUAGES = "de es fr it ja ko pl pt ru tc th tr uk zh".split()
ROOT = Path(__file__).resolve().parents[2]


def text_value(value):
    if isinstance(value, list):
        return "\n".join(str(part) for part in value)
    return str(value)


def prepare(revision=REVISION, cache=Path("/tmp/wfcd-grq-input"), output=None, stop=None):
    cache.mkdir(parents=True, exist_ok=True)
    paths = [f"{category}.json" for category in CATEGORIES] + [
        f"i18n/{lang}.json" for lang in LANGUAGES
    ]

    def download(name):
        if stop is not None and stop.is_set():
            raise TimeoutError("初始化已取消")
        target = cache / (name.replace("/", "_"))
        if not target.exists():
            request = Request(
                f"https://raw.githubusercontent.com/WFCD/warframe-items/{revision}/data/json/{name}",
                headers={
                    "User-Agent": "AAWarframe/0.15 (https://github.com/nekox41/nonebot-plugin-aawarframe)"
                },
            )
            for attempt in range(2):
                try:
                    with urlopen(request, timeout=15) as response:
                        raw = response.read()
                    json.loads(raw)
                    target.write_bytes(raw)
                    break
                except Exception:
                    if attempt == 1:
                        raise
                    time.sleep(attempt + 1)
        return name, json.loads(target.read_bytes())

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        data = dict(pool.map(download, paths))
    rows = {}
    for category in CATEGORIES:
        for row in data.pop(f"{category}.json"):
            key = row.get("uniqueName")
            if not key or not row.get("name"):
                raise ValueError("WFCD 物品缺少内部名称")
            rows[key] = {**rows.get(key, {}), **row}
    records = []
    locales = {"tc": "zh-hant", "zh": "zh-hans"}
    for key, row in sorted(rows.items()):
        names = {"en": row["name"]}
        texts = {"en": text_value(row["description"])} if row.get("description") else {}
        localized = {}
        for lang in LANGUAGES:
            entry = data[f"i18n/{lang}.json"].get(key, {})
            locale = locales.get(lang, lang)
            if entry.get("name"):
                names[locale] = entry["name"]
            if entry.get("description"):
                texts[locale] = text_value(entry["description"])
            extra = {k: v for k, v in entry.items() if k not in {"name", "description"}}
            if extra:
                localized[locale] = extra
        # 配方部件的原名可能只有“机体”，预先补上所属物品名称。
        parents = row.get("parentUniqueNames", [])
        aliases = []
        if row.get("category") == "Components" and parents:
            for lang, name in list(names.items()):
                qualified = []
                for parent in parents:
                    parent_row = rows.get(parent, {})
                    source_lang = next(
                        (code for code in LANGUAGES if locales.get(code, code) == lang), None
                    )
                    parent_name = (
                        data[f"i18n/{source_lang}.json"].get(parent, {}).get("name")
                        if source_lang
                        else parent_row.get("name")
                    )
                    if parent_name:
                        qualified.append(
                            name
                            if parent_name.casefold() in name.casefold()
                            else parent_name + (" " if lang == "en" else "") + name
                        )
                if qualified:
                    names[lang] = qualified[0]
                    aliases.extend(qualified[1:])
        records.append(
            {
                "id": key,
                "identifiers": {"game.ref": key},
                "names": names,
                "texts": texts,
                "aliases": list(dict.fromkeys(aliases)),
                "metadata": {**row, "i18n": localized},
            }
        )
    payload = {
        "version": 1,
        "domain": "Items",
        "revision": revision,
        "source": "https://github.com/WFCD/warframe-items",
        "license": "MIT",
        "resources": records,
    }
    output = output or ROOT / "nonebot_plugin_aawarframe/assets/grq/items.json.gz"
    with gzip.GzipFile(filename=str(output), mode="wb", mtime=0) as stream:
        with io.TextIOWrapper(stream, encoding="utf-8") as text:
            json.dump(payload, text, ensure_ascii=False, separators=(",", ":"))
    print(
        f"Prepared {len(records)} items, {len(LANGUAGES) + 1} languages, {output.stat().st_size} bytes"
    )
