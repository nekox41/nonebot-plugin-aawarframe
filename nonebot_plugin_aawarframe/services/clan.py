from ..localization.resolver import node_info, translate
from ..models.common import Section, Snapshot
from ..models.worldstate import VaultWeek
from ..worldstate.parsers.common import records
from .common import card_for, finish

ENDO_BUNDLE = "/Lotus/StoreItems/Upgrades/Mods/FusionBundles/UncommonFusionBundle"


def build_clan(snapshot: Snapshot):
    card = card_for(snapshot, "氏族每周奖励")
    weeks, card.notes = records(snapshot.data, "WeeklyVaultBonusRewards", VaultWeek)
    for index, week in enumerate(sorted(weeks, key=lambda w: w.week)[:2]):
        region = node_info(week.region).get("systemName", translate(week.region))
        section = Section(
            title=f"{'本周' if index == 0 else '下周'} · 双倍区域 {region}",
            columns=["奖励", "数量"],
        )
        for reward in week.rewards:
            is_endo = reward.reward == ENDO_BUNDLE
            section.rows.append(
                [
                    "Endo" if is_endo else translate(reward.reward),
                    str(reward.count * (50 if is_endo else 1)),
                ]
            )
        card.sections.append(section)
    return finish(card)
