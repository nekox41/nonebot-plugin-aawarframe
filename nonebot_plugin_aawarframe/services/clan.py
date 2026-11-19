# 作用：展示本周与下周氏族奖励、积分门槛和双倍区域。
# 编写日期：2026-11-11
# 作者：Aameow

import re
from datetime import datetime

from ..localization.resolver import node_info
from ..models.common import Section, Snapshot, utcnow
from ..models.worldstate import VaultWeek
from ..worldstate.parsers.common import records
from .common import finish
from .weekly import item_name, weekly_card

ENDO_BUNDLE = "/Lotus/StoreItems/Upgrades/Mods/FusionBundles/UncommonFusionBundle"


def build_clan(snapshot: Snapshot, now: datetime | None = None):
    card = weekly_card(snapshot, "氏族每周奖励", now or utcnow())
    weeks, warnings = records(snapshot.data, "WeeklyVaultBonusRewards", VaultWeek)
    if warnings:
        card.notes.append("部分氏族奖励暂时无法显示。")
    for index, week in enumerate(sorted(weeks, key=lambda w: w.week)[:2]):
        region = node_info(week.region).get("systemName", item_name(week.region))
        section = Section(
            title=f"{'本周' if index == 0 else '下周'} · 双倍区域 {region}",
            columns=["奖励", "数量", "所需积分"],
        )
        for reward in week.rewards:
            count = reward.count
            name = item_name(reward.reward)
            credits = re.search(r"/Credits/(\d+)Credits$", reward.reward)
            if credits:
                name, count = "现金", count * int(credits.group(1))
            elif reward.reward == ENDO_BUNDLE:
                name, count = "Endo", count * 50
            section.rows.append(
                [
                    name,
                    f"{count:,}",
                    f"{reward.threshold:,}" if reward.threshold is not None else "—",
                ]
            )
        card.sections.append(section)
    if len(weeks) == 1:
        card.sections.append(Section(title="下周", notes=["下期奖励尚未公布。"]))
    return finish(card)
