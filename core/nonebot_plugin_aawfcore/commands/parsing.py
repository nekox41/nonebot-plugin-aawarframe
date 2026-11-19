# Desc: 解析查询参数和紫卡词条修正。
# Date: 2026-11-15
# Author: Aameow

import re
import shlex

from ..grq import get_grq
from ..grq.normalizer import normalize_name
from ..localization.riven_attributes import match_attributes
from ..models.errors import UserInputError
from ..models.market import MarketQuery
from ..models.riven_market import RivenMarketQuery

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
    max_rank = name.startswith("满级") or name.endswith("满级")
    if name.startswith("满级"):
        name = name[2:].strip()
    if name.endswith("满级"):
        name = name[:-2].strip()
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


def parse_trend_query(text: str) -> MarketQuery:
    try:
        return parse_market_query(text)
    except UserInputError as exc:
        raise UserInputError(str(exc).replace("wm ", "趋势 ")) from exc


def parse_relic_query(text: str, command: str) -> str:
    query = text.strip()
    if not query or len(query) > 200:
        example = "阿利乌双枪p 枪机" if command == "部件" else "古纪A1"
        raise UserInputError(f"用法：{command} {example}，名称最长 200 字。")
    return query


def parse_wiki_query(text: str) -> str:
    query = text.strip()
    if not query:
        raise UserInputError("用法：wk 关键词，例如 wk 伯斯顿。")
    if len(query) > 200:
        raise UserInputError("Wiki 关键词过长（最多 200 字符）。")
    return query


def parse_riven_page(text: str) -> int:
    value = text.strip()
    if not value:
        return 1
    if len(value) > 6 or not value.isascii() or not value.isdigit() or int(value) < 1:
        raise UserInputError("用法：zk 2 或 zk已洗 2，可追加“热度”；页码必须是正整数。")
    return int(value)


def parse_riven_ranking(text: str) -> tuple[int, str]:
    tokens = text.split()
    if tokens.count("热度") > 1:
        raise UserInputError("用法：zk 3 热度 或 zk已洗 3 热度；默认按中位价排序。")
    sort_by = "popularity" if "热度" in tokens else "median"
    tokens = [token for token in tokens if token != "热度"]
    if len(tokens) > 1:
        raise UserInputError("用法：zk 3 热度 或 zk已洗 3 热度；默认按中位价排序。")
    return parse_riven_page(tokens[0] if tokens else ""), sort_by


def parse_riven_statistics_query(text: str) -> str:
    query = text.strip()
    if not query:
        raise UserInputError("用法：zk 武器名称，例如：zk 伯斯顿。")
    if len(query) > 200:
        raise UserInputError("武器名称过长（最多 200 字符）。")
    return query


def parse_riven_values(text: str) -> tuple[str, str]:
    text = text.strip()
    parts = text.rsplit(maxsplit=1)
    layout = "3+1"
    if parts and re.fullmatch(r"\d+\s*[+＋]\s*\d+", parts[-1]):
        layout = parts.pop().replace("＋", "+")
        text = parts[0] if parts else ""
    if layout not in {"2+0", "2+1", "3+0", "3+1"}:
        raise UserInputError("词条修正支持 2+0、2+1、3+0、3+1。")
    if not text or len(text) > 200:
        raise UserInputError("用法：数值 武器名 [2+0 / 2+1 / 3+0 / 3+1]，默认 3+1。")
    return text, layout


def parse_riven_market(text: str) -> RivenMarketQuery:
    usage = "用法：wmr 武器名 [正面词条] [负任意 / 负词条名]；发送“词条”查看名称与缩写。"
    guide = "词条无法识别，请发送“词条”查看名称与缩写映射。"
    if len(text) > 500:
        raise UserInputError("查询内容过长。" + usage)
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise UserInputError("武器名引号不完整。" + usage) from exc
    negative = None
    if len(tokens) > 1 and tokens[-1].startswith("负"):
        suffix = tokens.pop()[1:]
        if suffix == "任意":
            negative = "has"
        else:
            stats = match_attributes(suffix)
            if not stats or len(stats) != 1:
                raise UserInputError("负面请填写“负任意”或一个词条，例如“负变焦”。" + guide)
            negative = stats[0]
    if not tokens:
        raise UserInputError(usage)
    index = get_grq().domains["Riven"]
    # 优先保留完整武器名；未知词条不能被模糊武器匹配吞掉。
    exact = [
        i for i in range(1, len(tokens) + 1)
        if normalize_name(" ".join(tokens[:i])) in index.names
        or " ".join(tokens[:i]) in index.external
    ]
    boundary = max(exact) if exact else next(
        (i for i in range(1, len(tokens)) if match_attributes(" ".join(tokens[i:]))),
        len(tokens) if len(tokens) == 1 else None,
    )
    if boundary is None:
        raise UserInputError(guide)
    positives = match_attributes(" ".join(tokens[boundary:]))
    if positives is None or (boundary < len(tokens) and not positives):
        raise UserInputError(guide)
    if len(positives) > 3:
        raise UserInputError("最多指定 3 个正面词条。发送“词条”查看映射。")
    if len(set(positives)) != len(positives) or negative in positives:
        raise UserInputError("正负词条不能重复。")
    weapon = " ".join(tokens[:boundary])
    if len(weapon) > 200:
        raise UserInputError(usage)
    return RivenMarketQuery(weapon=weapon, positives=positives, negative=negative)


def parse_bounty_index(text: str, command: str = "地球") -> int | None:
    value = text.strip()
    if not value:
        return None
    if not value.isascii() or not value.isdigit() or len(value) > 2 or int(value) < 1:
        raise UserInputError(f"用法：{command} 查看概览，{command} 1 查看指定任务；编号须为正整数。")
    return int(value)
