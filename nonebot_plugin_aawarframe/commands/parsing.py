import shlex

from ..models.errors import UserInputError
from ..models.market import MarketQuery

USAGE = "用法：wm 物品名 / wm 满级物品名；可选 --rank 等级、--subtype 子类型。物品名允许空格。"


def parse_market_query(text: str) -> MarketQuery:
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise UserInputError("物品名引号不完整。" + USAGE) from exc
    names = []
    options = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            if token not in {"--rank", "--subtype"} or token in options:
                raise UserInputError("未知或重复选项。" + USAGE)
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
                raise UserInputError("选项缺少值。" + USAGE)
            options[token] = tokens[index + 1]
            index += 2
        else:
            names.append(token)
            index += 1
    name = " ".join(names).strip()
    max_rank = name.startswith("满级")
    if max_rank:
        name = name[2:].strip()
    if not name:
        raise UserInputError(USAGE)
    rank = None
    if "--rank" in options:
        if max_rank or not options["--rank"].isascii() or not options["--rank"].isdigit():
            raise UserInputError("等级须为非负整数，且不能与满级同时使用。")
        rank = int(options["--rank"])
    if len(name) > 200:
        raise UserInputError("物品名称过长（最多 200 字符）。")
    return MarketQuery(name=name, max_rank=max_rank, rank=rank, subtype=options.get("--subtype"))


def parse_wiki_query(text: str) -> str:
    query = text.strip()
    if not query:
        raise UserInputError("用法：wk 关键词（别名 wiki），例如 wk 伯斯顿。")
    if len(query) > 200:
        raise UserInputError("Wiki 关键词过长（最多 200 字符）。")
    return query


def parse_riven_page(text: str) -> int:
    value = text.strip()
    if not value:
        return 1
    if len(value) > 6 or not value.isascii() or not value.isdigit() or int(value) < 1:
        raise UserInputError("用法：紫卡排行2 或 已洗紫卡排行2，可追加“热度”；页码必须是正整数。")
    return int(value)


def parse_riven_ranking(text: str) -> tuple[int, str]:
    tokens = text.split()
    if tokens.count("热度") > 1:
        raise UserInputError("用法：紫卡排行3 热度 或 已洗紫卡排行3 热度；默认按中位价排序。")
    sort_by = "popularity" if "热度" in tokens else "median"
    tokens = [token for token in tokens if token != "热度"]
    if len(tokens) > 1:
        raise UserInputError("用法：紫卡排行3 热度 或 已洗紫卡排行3 热度；默认按中位价排序。")
    return parse_riven_page(tokens[0] if tokens else ""), sort_by


def parse_riven_statistics_query(text: str) -> str:
    query = text.strip()
    if not query:
        raise UserInputError("用法：紫卡统计 武器名称，例如：紫卡统计 伯斯顿。")
    if len(query) > 200:
        raise UserInputError("武器名称过长（最多 200 字符）。")
    return query
