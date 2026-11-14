# 作用：将 Market API 的完整可交易目录预处理为 SQLite 初始化快照。
# 编写日期：2026-11-14
# 作者：Aameow

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def prepare(input_path=None, output=None):
    if input_path:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    else:
        request = Request(
            "https://api.warframe.market/v2/items",
            headers={
                "Language": "zh-hans",
                "Platform": "pc",
                "User-Agent": "AAWarframe/0.15 (https://github.com/nekox41/nonebot-plugin-aawarframe)",
            },
        )
        with urlopen(request, timeout=15) as response:
            raw = json.load(response)
    items = raw["data"]
    if not items or len({item["id"] for item in items}) != len(items):
        raise ValueError("Market 目录为空或标识重复")
    records = []
    for item in items:
        if not item.get("tradable", True):
            continue
        records.append(
            {
                "id": item["slug"],
                "identifiers": {
                    "market.slug": item["slug"],
                    "market.item_id": item["id"],
                    **({"game.ref": item["gameRef"]} if item.get("gameRef") else {}),
                },
                "names": {
                    lang: locale["name"]
                    for lang, locale in item["i18n"].items()
                    if locale.get("name")
                },
                "metadata": {**item, "tradable": True},
            }
        )
    payload = {
        "domain": "Market",
        "version": 1,
        "source": "https://api.warframe.market/v2/items",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "resources": records,
    }
    output = output or Path(__file__).resolve().parents[1] / "assets/grq/market.json.gz"
    with gzip.open(output, "wt", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
    print("Prepared", len(records), "Market items,", output.stat().st_size, "bytes")
