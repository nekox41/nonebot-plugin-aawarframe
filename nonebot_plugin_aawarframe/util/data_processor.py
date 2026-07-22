import json
from pathlib import Path
from typing import Any, Dict, List, Union
from nonebot.log import logger

# ---------- 加载映射文件 ----------
_ASSETS_DIR = Path(__file__).parent.parent / "assets"

def _load_json(filename: str) -> Dict:
    path = _ASSETS_DIR / filename
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

FACTION_MAP = _load_json("faction_type.json")        # 如 {"FC_SCALDRA": "炽蛇军"}
MISSION_TYPE_MAP = _load_json("mission_type.json")  # 如 {"MT_DEFENSE": "防御"}
CONQUEST_ZH = _load_json("conquest_zh.json")        # 所有字符串翻译
VARIABLES_MAP = _load_json("variables.json")

def _get_translation(key: str) -> str:
    """从 conquest_zh.json 获取翻译，若不存在则返回原 key"""
    return CONQUEST_ZH.get(key, key)

# ---------- 核心转换函数 ----------
def transform_to_archimedea_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将原始 Conquest 数据（包含 Type, Missions, Variables）转换为前端所需格式
    """
    conquest_type = raw_data.get("Type", "")
    if not conquest_type:
        return {}

    # 根据类型选择前缀
    if conquest_type == "CT_LAB":
        type_prefix = "/Lotus/Language/Conquest/MissionVariant_LabConquest_"
    else:  # CT_HEX 或其它
        type_prefix = "/Lotus/Language/Conquest/MissionVariant_HexConquest_"

    pm_prefix = "/Lotus/Language/Conquest/PersonalMod_"
    risk_prefix = "/Lotus/Language/Conquest/Condition_"

    # ---------- 处理 Missions ----------
    missions = []
    for mission in raw_data.get("Missions", []):
        # 转换 faction 和 missionType
        faction_key = mission.get("faction", "")
        faction_zh = FACTION_MAP.get(faction_key, faction_key)

        mission_type_key = mission.get("missionType", "")
        mission_type_zh = MISSION_TYPE_MAP.get(mission_type_key, mission_type_key)

        # 寻找 CD_HARD 难度的配置（若没有则尝试 CD_NORMAL）
        difficulties = mission.get("difficulties", [])
        hard_diff = None
        for diff in difficulties:
            if diff.get("type") == "CD_HARD":
                hard_diff = diff
                break
        if hard_diff is None:
            # 没有 CD_HARD，尝试 CD_NORMAL
            for diff in difficulties:
                if diff.get("type") == "CD_NORMAL":
                    hard_diff = diff
                    break
        if hard_diff is None:
            # 若仍没有则跳过该任务
            continue

        # 构建条件列表
        conditions = []

        # a) deviation 作为一个条件
        deviation = hard_diff.get("deviation")
        if deviation:
            name_key = type_prefix + deviation
            desc_key = name_key + "_Desc"
            conditions.append({
                "name": _get_translation(name_key),
                "desc": _get_translation(desc_key)
            })

        # b) risks 中的每个风险作为一个条件
        for risk in hard_diff.get("risks", []):
            name_key = risk_prefix + risk
            desc_key = name_key + "_Desc"
            conditions.append({
                "name": _get_translation(name_key),
                "desc": _get_translation(desc_key)
            })

        missions.append({
            "faction": faction_zh,
            "missionType": mission_type_zh,
            "difficulties": conditions
        })

    # ---------- 处理 Variables（先转换 UI 名称为内部名称）----------
    variables = []
    for ui_name in raw_data.get("Variables", []):
        # 根据 UI 名称查找内部名称
        internal_name = VARIABLES_MAP.get(ui_name)  # 若找不到则为 None
        if internal_name is None:
            # 如果映射中找不到，保留原样（或者记录日志，或者直接跳过）
            # 这里我们保留原样并用它拼接（可能失败）
            internal_name = ui_name
        # 拼接前缀
        name_key = pm_prefix + internal_name
        desc_key = name_key + "_Desc"
        variables.append({
            "name": _get_translation(name_key),
            "desc": _get_translation(desc_key)
        })

    return {
        "Missions": missions,
        "Variables": variables
    }

def extract_conquests(raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从 World State 中提取 Conquests （科研数据）
    :param raw_data: World State 数据
    :return: 两个科研的数据，可以通过 Type 来区分时光和深层。CT_LAB 为深层，CT_HEX 为时光。
    """
    conquests = raw_data.get("Conquests", [])
    if not conquests:
        logger.warning("未找到科研数据。")

    return conquests


def render_archimedea_panel(data: Union[Dict, str], template_path: str = "archimedea.html") -> str:
    """
    将任务数据填充到HTML模板中，返回完整的HTML字符串。
    参数与之前一致。
    """
    # 如果传入的是JSON字符串，先解析为字典
    if isinstance(data, str):
        data = json.loads(data)

    # 构建左侧任务区域的HTML行
    missions_rows = []
    for mission in data.get("Missions", []):
        mission_type = mission.get("missionType", "未知任务")
        faction = mission.get("faction", "")
        difficulties = mission.get("difficulties", [])

        title_content = mission_type
        if faction:
            title_content += f' <span class="faction-tag">{faction}</span>'

        missions_rows.append(f'<tr class="task-title-row"><td colspan="2">{title_content}</td></tr>')

        for diff in difficulties:
            cond_name = diff.get("name", "")
            cond_desc = diff.get("desc", "")
            missions_rows.append(
                f'<tr>'
                f'<td class="cond-name">{cond_name}</td>'
                f'<td class="cond-desc">{cond_desc}</td>'
                f'</tr>'
            )

    # 构建右侧变量区域的HTML行
    variables_rows = []
    for var in data.get("Variables", []):
        var_name = var.get("name", "")
        var_desc = var.get("desc", "")
        variables_rows.append(f'<tr class="factor-title-row"><td colspan="2">{var_name}</td></tr>')
        variables_rows.append(f'<tr class="factor-desc-row"><td colspan="2">{var_desc}</td></tr>')

    # 读取模板文件（注意路径）
    template_path = Path(template_path)  # 确保是Path对象
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    html_output = template.replace("{{MISSIONS_ROWS}}", "\n".join(missions_rows))
    html_output = html_output.replace("{{VARIABLES_ROWS}}", "\n".join(variables_rows))

    return html_output
