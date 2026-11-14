# 作用：定义七个固定 GRQ 资源域及业务数据归属。
# 编写日期：2026-11-13
# 作者：Aameow

from .models import Domain

DOMAINS = [
    Domain(
        name="Items",
        title="Items · 游戏物品",
        description="WFCD 完整物品资料、内部名称和多语言名称。",
    ),
    Domain(
        name="Market",
        title="Market · 市场商品",
        description="Market API 可交易商品，别名与对应物品及紫卡共享。",
        semantic_guard=True,
    ),
    Domain(
        name="Riven",
        title="Riven · 紫卡兼容",
        description="紫卡兼容武器、武器分类和共享别名。",
        semantic_guard=True,
    ),
    Domain(
        name="Node", title="Node · 星图节点", description="星图节点和任务信息映射。", fuzzy=False
    ),
    Domain(
        name="Desc",
        title="Desc · 描述映射",
        description="游戏描述、任务类型和派系文本。",
        searchable=False,
        fuzzy=False,
        aliases=False,
        mode="text",
    ),
    Domain(
        name="Misc",
        title="Misc · 杂项",
        description="已整理的任务池、据点和周轮换等业务数据。",
        fuzzy=False,
        aliases=False,
        mode="document",
    ),
    Domain(
        name="Droptable",
        title="Droptable · 奖励表",
        description="按任务、敌人、遗物及原始奖励表路径维护完整奖励与概率。",
        searchable=False,
        fuzzy=False,
        aliases=False,
        mode="document",
    ),
]
DOMAIN_NAMES = frozenset(d.name for d in DOMAINS)
DROP_FILES = {"drops.json", "bounty_drops.json", "challenge_bounty_drops.json"}
DESC_FILES = {"conquest_zh.json", "jobs.json", "mission_type.json", "faction_type.json"}


def file_domain(filename):
    if filename == "ExportRegions_zh.json":
        return "Node"
    if filename in DESC_FILES or filename in {"nightwave_zh.json", "weekly_names.json"}:
        return "Desc"
    if filename in DROP_FILES:
        return "Droptable"
    if filename == "riven_weapons.json":
        return "Riven"
    if filename == "wm_pitems.json":
        return "Market"
    return "Misc"


def misc_id(filename, path):
    stem = filename.removesuffix(".json")
    if stem.endswith("_bounty_tasks") and path[0] == "jobs":
        return f"bounty.tasks.{stem.split('_')[0]}:{path[-1]}"
    if stem.endswith("_bounty_locations") and path[0] == "locations":
        return f"bounty.locations.{stem.split('_')[0]}:{path[-1]}"
    return stem + ":" + "/".join(map(str, path))


def mapped_id(filename, key):
    domain = file_domain(filename)
    if domain in {"Desc", "Node"}:
        return key
    if domain == "Droptable":
        return key
    return misc_id(filename, [key])
