# Desc: 实现 rendering 层的 viewmodels 功能。
# Date: 2026-11-15
# Author: Aameow

from ..models.common import Card, Section
from ..replies import replies
from ..models.wiki import WikiSearchResult


def paginate(card: Card, *, max_rows: int = 12, max_characters: int = 1000) -> list[Card]:
    if card.parts_board:
        pages, parts, cost = [], [], 0

        def flush():
            page = card.model_copy(update={"parts_board": card.parts_board.model_copy(update={"parts": list(parts)})})
            pages.append(page)

        for part in card.parts_board.parts:
            chunks = [part.relics[i:i + 48] for i in range(0, len(part.relics), 48)] or [[]]
            for chunk in chunks:
                size = len(chunk) + 6
                if parts and cost + size > 64:
                    flush()
                    parts, cost = [], 0
                parts.append(part.model_copy(update={"relics": chunk}))
                cost += size
        if parts:
            flush()
        return pages or [card]
    if card.relic_board:
        return [card]
    if card.trend_board or card.attribute_rows or card.command_names or card.riven_market_board or card.riven_values_board:
        return [card]
    if card.trader_board:
        return [card]
    if card.operation_board:
        items = card.operation_board.invasions
        if len(items) <= 20:
            return [card.model_copy(deep=True)]
        pages = []
        for start in range(0, len(items), 20):
            page = card.model_copy(deep=True)
            page.operation_board.invasions = page.operation_board.invasions[start : start + 20]
            pages.append(page)
        return pages
    if (
        card.arbitration_board
        or card.market_board
        or card.fissure_mode
        or card.bounty_mode
        or card.archimedea_mode
        or card.nightwave_mode
        or card.weekly_mode
    ):
        # 专用卡片使用紧凑排版，在一张自适应高度的图片中保留所有任务。
        return [card.model_copy(deep=True)]
    pages = []
    current = card.model_copy(update={"sections": []}, deep=True)
    count = size = 0
    for section in card.sections:
        if not section.rows:
            if count >= max_rows:
                pages.append(current)
                current = card.model_copy(update={"sections": []}, deep=True)
                count = size = 0
            current.sections.append(section.model_copy(deep=True))
            count += 1
            continue
        chunk = Section(title=section.title, columns=section.columns, notes=section.notes)
        for row in section.rows:
            row_size = sum(len(cell) for cell in row)
            if count and (count >= max_rows or size + row_size > max_characters):
                if chunk.rows:
                    current.sections.append(chunk)
                pages.append(current)
                current = card.model_copy(update={"sections": []}, deep=True)
                chunk = Section(title=section.title, columns=section.columns, notes=section.notes)
                count = size = 0
            chunk.rows.append(row)
            count += 1
            size += row_size
        if chunk.rows:
            current.sections.append(chunk)
    if current.sections or not pages:
        pages.append(current)
    return pages


def fallback_text(card: Card, limit: int = 1800) -> str:
    text = replies.localize(card.text())
    if len(text) <= limit:
        return text
    body, source, timestamp = text.rsplit("\n", 2)
    notice = replies.text("FALLBACK_TOO_LONG")
    budget = max(0, limit - len(source) - len(timestamp) - len(notice) - 4)
    excerpt = body[:budget]
    if "\n" in excerpt:
        excerpt = excerpt.rsplit("\n", 1)[0]
    return "\n".join([excerpt, notice, source, timestamp])


def wiki_text(result: WikiSearchResult) -> str:
    if not result.entries:
        return replies.text("WIKI_NOT_FOUND", QUERY=result.query)
    return replies.localize("\n\n".join(
        f"{entry.title}\n{entry.description}\n{entry.url}" for entry in result.entries
    ))
