# 作用：实现 rendering 层的 viewmodels 功能。
# 编写日期：2026-11-07
# 作者：Aameow

from ..models.common import Card, Section
from ..models.wiki import WikiSearchResult


def paginate(card: Card, *, max_rows: int = 12, max_characters: int = 1000) -> list[Card]:
    if (
        card.fissure_mode
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
    text = card.text()
    if len(text) <= limit:
        return text
    body, source, timestamp = text.rsplit("\n", 2)
    notice = "内容较长，仅显示部分结果；请稍后重新查询完整图片。"
    budget = max(0, limit - len(source) - len(timestamp) - len(notice) - 4)
    excerpt = body[:budget]
    if "\n" in excerpt:
        excerpt = excerpt.rsplit("\n", 1)[0]
    return "\n".join([excerpt, notice, source, timestamp])


def wiki_text(result: WikiSearchResult) -> str:
    if not result.entries:
        return f"未找到与“{result.query}”相关的 Wiki 条目。"
    return "\n\n".join(
        f"{entry.title}\n{entry.description}\n{entry.url}" for entry in result.entries
    )
