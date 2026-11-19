# 作用：校验仲裁排期，统一星图节点信息及仲裁初始属性。
# 编写日期：2026-11-14
# 作者：Aameow

import re


def parse_schedule(text):
    rows = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if (
            len(parts) != 2
            or not parts[0].isdigit()
            or not re.fullmatch(r"[A-Za-z]+Node\d+", parts[1])
        ):
            raise ValueError("仲裁时间表应为：Unix 秒时间戳,节点")
        stamp = int(parts[0])
        if stamp % 3600 or stamp in rows:
            raise ValueError("仲裁时间戳必须唯一且为整点")
        rows[stamp] = parts[1]
    result = sorted(rows.items())
    if not result or any(b[0] - a[0] != 3600 for a, b in zip(result, result[1:])):
        raise ValueError("仲裁时间表为空或存在缺失时段")
    return result


def prepare_nodes(existing, regions, schedule, tiers, descriptions):
    eligible = {node for _, node in schedule}
    result = {}
    for key in sorted(existing.keys() | regions.keys()):
        old, raw = existing.get(key, {}), regions.get(key, {})
        mission = raw.get("missionType") or old.get("missionType")
        faction = raw.get("faction", old.get("faction"))
        result[key] = {
            "name": old.get("name") or raw.get("name", key).rsplit("/", 1)[-1],
            "systemName": old.get("systemName") or raw.get("systemName", "").rsplit("/", 1)[-1],
            "missionType": mission,
            "missionName": descriptions["mission_types"].get(
                mission, old.get("missionName") or mission or "未知"
            ),
            "faction": faction,
            "factionName": descriptions["factions"].get(
                faction, old.get("factionName") or faction or "无派系"
            ),
            "arbitration": {"grade": tiers.get(key, "F"), "vitus_per_minute": 0}
            if key in eligible
            else None,
        }
    missing = eligible - result.keys()
    if missing:
        raise ValueError("仲裁节点资料缺失：" + ",".join(sorted(missing)))
    return result
