import json
from pathlib import Path
import time
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from ...common.browser_manager import html_to_pic
from datetime import datetime

asset = Path(__file__).parent.parent.parent / "assets"

async def gen_current_arbys_img() -> Message:
    # 第一件事先获取数据
    # 读取 final_arbys
    with open(asset / "final_arbys.json", "r", encoding="utf-8") as f:
        final_arbys = json.load(f)

    now = time.time()
    current_arby = None
    next_arby = None
    for key, arby in final_arbys.items():
        if int(key) <= now:
            current_arby = arby
        else:
            next_arby = arby
            break

    data_json = json.dumps({"current": current_arby, "next": next_arby}, ensure_ascii=False, indent=4)

    with open(asset / "templates" / "current_arbys.html", "r" , encoding="utf-8") as fp:
        template = fp.read()

    html = template.replace("{{DATA}}", data_json)
    img = await html_to_pic(html)
    return Message(MessageSegment.image(img))

async def gen_today_arbys_img() -> Message:
    """
    仲裁任务固定每小时一个，获取今天 00:00:00 时的时间戳为第一个，此后每 3600 秒一个，一直到 23:00:00
    :return:
    """
    with open(asset / "final_arbys.json", "r", encoding="utf-8") as f:
        final_arbys = json.load(f)

    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    start_ts = int(today_start.timestamp())

    today_list = []
    for hour in range(24):
        ts = start_ts + hour * 3600
        key = str(ts)
        if key in final_arbys:
            arby = final_arbys[key]
            today_list.append(arby)

    data_json = json.dumps(today_list, ensure_ascii=False, indent=4)
    with open(asset / "templates" / "today_arbys.html", "r", encoding="utf-8") as fp:
        template = fp.read()
    img = await html_to_pic(template.replace("{{DATA}}", data_json))
    return Message(MessageSegment.image(img))