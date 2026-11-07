from datetime import datetime

from ..localization.resolver import load_mapping
from ..models.common import Section, Snapshot
from ..models.worldstate import SyndicateJob, SyndicateMission
from ..worldstate.parsers.common import ParseError, records
from .common import card_for, finish

STAGES = {
    15: [0, 1, -1],
    30: [0, 1, -1],
    40: [0, 1, 1, -1],
    50: [0, 1, 1, 2, -1],
    60: [0, 1, 1, 2, -1],
    100: [0, 1, 1, 2, -1],
    70: [0, 1, 1, 2, -1],
}


def build_bounties(snapshot: Snapshot, now: datetime):
    card = card_for(snapshot, "希图斯赏金")
    missions, card.notes = records(snapshot.data, "SyndicateMissions", SyndicateMission)
    cetus = next(
        (m for m in missions if m.tag == "CetusSyndicate" and m.activation <= now < m.expiry), None
    )
    if cetus is None:
        return finish(card)
    jobs, warnings = records({"Jobs": cetus.jobs}, "Jobs", SyndicateJob)
    card.notes.extend(warnings)
    names, drops = load_mapping("jobs.json"), load_mapping("drops.json")
    for job in sorted(
        jobs, key=lambda j: list(STAGES).index(j.max_level) if j.max_level in STAGES else 99
    ):
        name = job.job_type.rsplit("/", 1)[-1]
        section = Section(
            title=f"{names.get(name + 'Title', job.job_type)} · 等级 {job.min_level}–{job.max_level}",
            columns=["阶段", "奖励", "数量", "概率"],
            notes=[names.get(name + "Desc", "")],
        )
        if job.max_level not in STAGES or job.rewards not in drops:
            section.notes.append("本地尚无此阶段或掉落表映射，奖励不可用。")
        else:
            try:
                for i, stage in enumerate(STAGES[job.max_level], 1):
                    for reward in drops[job.rewards][stage]:
                        section.rows.append(
                            [
                                str(i),
                                str(reward["name"]),
                                str(reward["itemCount"]),
                                f"{float(reward['probability']) * 100:.2f}%",
                            ]
                        )
            except (KeyError, TypeError, IndexError, ValueError) as exc:
                raise ParseError("赏金掉落表解析失败") from exc
        card.sections.append(section)
    return finish(card)
