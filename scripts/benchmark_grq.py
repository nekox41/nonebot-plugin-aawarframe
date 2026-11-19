"""Repeatable Core GRQ startup/memory/query microbenchmark for release CI."""

import argparse
import json
import resource
import statistics
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--repetitions", type=int, default=50)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")

    import nonebot

    nonebot.init(driver="~none", render={"provider": "playwright", "startup": "off"})
    from nonebot_plugin_aawfcore.grq import GameResourceQuery
    from nonebot_plugin_aawfcore.initialization.pipeline import ensure_offline

    def bench(directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        ensure_offline(directory)
        start = time.perf_counter()
        grq = GameResourceQuery(directory / "registry.sqlite3")
        init_ms = (time.perf_counter() - start) * 1000
        results = {}
        for key, call in (
            ("items_exact", lambda: grq.search("Items", "伯斯顿")),
            ("market_fallback", lambda: grq.search_market("Saryn")),
            ("riven_exact", lambda: grq.search("Riven", "Burston")),
            ("riven_family", lambda: grq.item_family("burston")),
            ("item_get", lambda: grq.get("Items", "/Lotus/Weapons/Tenno/Rifle/BurstRifle")),
        ):
            timings = []
            for _ in range(args.repetitions):
                started = time.perf_counter()
                call()
                timings.append((time.perf_counter() - started) * 1000)
            results[key] = round(statistics.median(timings), 3)
        rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        count = grq.db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        unmatched = grq.db.execute("SELECT COUNT(*) FROM market_products").fetchone()[0]
        grq.close()
        return {
            "startup_ms": round(init_ms, 1),
            "peak_rss_mib": round(rss_kib / 1024, 1),
            "items": count,
            "unmatched_market_products": unmatched,
            "median_query_ms": results,
        }

    if args.data_dir:
        report = bench(args.data_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="aawf-benchmark-") as temporary:
            report = bench(Path(temporary))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
