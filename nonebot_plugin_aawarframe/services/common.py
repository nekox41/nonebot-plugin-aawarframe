# 作用：实现 services 层的 common 功能。
# 编写日期：2026-11-07
# 作者：Aameow

from ..models.common import Card, DataStatus, Snapshot


def card_for(snapshot: Snapshot, title: str) -> Card:
    return Card(
        title=title, source=snapshot.source, fetched_at=snapshot.fetched_at, stale=snapshot.stale
    )


def finish(card: Card) -> Card:
    if not card.sections or not any(section.rows for section in card.sections):
        card.status = DataStatus.EMPTY
        card.notes.append("当前没有可用数据。")
    return card
