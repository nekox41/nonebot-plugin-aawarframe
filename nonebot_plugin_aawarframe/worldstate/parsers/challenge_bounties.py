# 作用：从轮换种子还原圣所、扎里曼和 1999 的任务、额外目标及同行角色。
# 编写日期：2026-11-10
# 作者：Aameow

from ..seeded_random import SeededRandom
from .common import ParseError

ALLY_PREFIX = "/Lotus/Types/Gameplay/1999Wf/ProtoframeAllies/"
EXCLUDED_ALLIES = {
    "SolNode856": "Arthur",
    "SolNode852": "Lettie",
    "SolNode851": "Amir",
    "SolNode850": "Eleanor",
    "SolNode853": "Aoi",
    "SolNode854": "Quincy",
}


def challenge_family(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    for suffix in ("Easy", "VeryHard", "Hard", "Challenge"):
        if suffix in name:
            return name[: name.index(suffix)]
    return name


def generate_challenge_bounties(
    manifest: dict, seed: int, agents: list[str] | None = None
) -> list[dict]:
    """遵循 wf.browse.oracle 的节点、角色、目标选取顺序，不修改缓存配置。"""
    random = SeededRandom(seed)
    nodes = list(manifest["ChallengeMissionNodes"])
    random.shuffle(nodes)
    lich_nodes = ["SolNode852", "SolNode850", "SolNode854"] if agents is not None else list(nodes)
    if agents is not None:
        agents = list(agents)
        if 0 < len(agents) < len(nodes):
            candidates = ["SolNode851", "SolNode852", "SolNode853", "SolNode854"]
            random.shuffle(candidates)
            for candidate in candidates:
                if len(agents) >= len(nodes):
                    break
                if candidate in nodes:
                    nodes.remove(candidate)
        random.shuffle(agents)
        for i in range(min(len(agents), len(nodes))):
            excluded = EXCLUDED_ALLIES.get(nodes[i])
            if excluded and agents[i] == ALLY_PREFIX + excluded + "AllyAgent":
                j = (i + 1) % len(agents)
                agents[i], agents[j] = agents[j], agents[i]

    faction = ("FC_GRINEER", "FC_CORPUS")[seed & 1]
    result, seen = [], set()
    for i, tier in enumerate(manifest["ChallengeMissionDifficultyTiers"]):
        bounty = {"node": nodes[i] if i < len(nodes) else random.choice(lich_nodes)}
        if agents is not None and i < len(nodes):
            bounty["ally"] = agents[i]
        fresh, repeated = [], []
        for entry in tier["challenges"]:
            if entry["Node"] not in ("", bounty["node"]):
                continue
            if entry["CheckFaction"] and entry["Faction"] != faction:
                continue
            for challenge in entry["challenges"]:
                (repeated if challenge_family(challenge) in seen else fresh).append(challenge)
        candidates = fresh or repeated
        if not candidates:
            raise ParseError("赏金节点没有匹配的额外目标")
        bounty["challenge"] = random.choice(candidates)
        seen.add(challenge_family(bounty["challenge"]))
        result.append(bounty)
    return result
