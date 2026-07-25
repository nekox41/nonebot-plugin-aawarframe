import json
from typing import List

from ...common import fetch_world_state
from ...common.browser_manager import html_to_pic, read_template
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"


def void_level_map(level: str) -> str:
    """
    输入虚空裂缝等级，返回中文名称
    :param level: VoidT1、VoidT2...
    :return:
    """
    void_map = {
        "VoidT1": "古纪",
        "VoidT2": "前纪",
        "VoidT3": "中纪",
        "VoidT4": "后纪",
        "VoidT5": "安魂",
        "VoidT6": "全能",
        "null": "错误"
    }
    return void_map[level]

async def gen_void_fissures_img(is_hard: bool) -> MessageSegment:
    """
    生成普通虚空裂缝的图片
    :return: 图片消息
    """
    # 获取世界信息
    world_state = await fetch_world_state()
    all_void_fissures = world_state.get("ActiveMissions", None)
    if not all_void_fissures or not isinstance(all_void_fissures, List):
        return MessageSegment.text("数据源错误，请联系管理员")

    # 读取地图数据，待会使用
    with open(ASSETS_DIR / "ExportRegions_zh.json", "r", encoding="utf-8") as f:
        nodes = json.load(f)

    vf_data = []
    # 遍历数组筛选指定裂缝
    for void_fissure in all_void_fissures:
        # 如果 is_hard 为 True 我们要筛选出

        if void_fissure.get("Hard", False) != is_hard:
            continue

        # 摘出数据
        node = nodes.get(void_fissure.get("Node", "null"), None)
        vf_data.append({
            "start": void_fissure["Activation"]["$date"]["$numberLong"],
            "end": void_fissure["Expiry"]["$date"]["$numberLong"],
            "region": node.get("systemName", "null"),
            "name": node.get("name", "null"),
            "type": node.get("missionName", "null"),
            "faction": node.get("faction", "null"),
            "modifier": void_level_map(void_fissure.get("Modifier", "null")),
        })

    template = read_template("void_fissures")
    if is_hard:
        title = "虚空裂缝（钢铁）"
    else:
        title = "虚空裂缝（普通）"
    template = template.replace("{{TITLE}}", title)
    template =template.replace("{{DATA}}", json.dumps(vf_data, ensure_ascii=False, indent=4))
    return MessageSegment.image(await html_to_pic(template))