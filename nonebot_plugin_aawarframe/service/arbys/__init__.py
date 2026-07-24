import json
from pathlib import Path
import time
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from ...common.browser_manager import html_to_pic

asset = Path(__file__).parent.parent.parent / "assets"

async def gen_current_arbys_img() -> Message:
    # 第一件事先获取数据
    # 读取 arbys.txt 获取仲裁表
    arbys_list = []
    with open(asset / "arbys.txt", "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            node_time = int(parts[0].strip())
            node = parts[1].strip()
            arbys_list.append((node_time, node))

    arbys_list.sort(key=lambda x: x[0])

    # 获取星图节点
    with open(asset / "ExportRegions_zh.json", "r", encoding="utf-8") as fp:
        regions = json.load(fp)

    now = time.time()
    current_key = None
    current_t = 0
    next_key = None
    for nt, key in arbys_list:
        if nt <= now:
            current_key = key
            current_t = int(nt)
        else:
            next_key = key
            break
    if current_key is None:
        return Message(MessageSegment.text("未获取到正确节点"))

    current = regions.get(current_key)
    next = regions.get(next_key)
    if current is None:
        return Message(MessageSegment.text("未找到节点对应信息"))

    data = {
      "current": {
        "name": current.get("name", "null"),
        "map": current.get("systemName", "null"),
        "type": current.get("missionName", "null"),
        "faction": current.get("faction", "null"),
        "tier": current.get("tier", "null"),
        "start": current_t,
        "end": current_t + 3600
      },
      "next": {
        "name": next.get("name", "null"),
        "map": next.get("systemName", "null"),
        "type": next.get("missionName", "null"),
        "faction": next.get("faction", "null"),
        "tier": next.get("tier", "null"),
        "start": current_t + 3600,
        "end": current_t + 7200
      }
    }
    data_json = json.dumps(data, ensure_ascii=False, indent=4)

    with open(asset / "templates" / "current_arbys.html", "r" , encoding="utf-8") as fp:
        template = fp.read()

    html = template.replace("{{DATA}}", data_json)
    img = await html_to_pic(html)
    return Message(MessageSegment.image(img))