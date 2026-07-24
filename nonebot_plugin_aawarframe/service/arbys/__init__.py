import json
from pathlib import Path
import time
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from ...common.browser_manager import html_to_pic, read_template
from datetime import datetime

asset = Path(__file__).parent.parent.parent / "assets"

def read_final_arbys() -> dict:
    with open(asset / "final_arbys.json", "r", encoding="utf-8") as f:
        final_arbys = json.load(f)
        f.close()
    return final_arbys

async def gen_current_arbys_img() -> Message:
    # 读取 final_arbys
    final_arbys = read_final_arbys()

    # 根据时间计算出当前的仲裁任务与下一次仲裁任务
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

    template = read_template("current_arbys")

    html = template.replace("{{DATA}}", data_json)
    img = await html_to_pic(html)
    return Message(MessageSegment.image(img))

async def gen_today_arbys_img() -> Message:
    """
    仲裁任务固定每小时一个，获取今天 00:00:00 时的时间戳为第一个，此后每 3600 秒一个，一直到 23:00:00
    :return:
    """
    final_arbys = read_final_arbys()

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
    template = read_template("today_arbys")
    img = await html_to_pic(template.replace("{{DATA}}", data_json))
    return Message(MessageSegment.image(img))

async def gen_s_arbys_img() -> Message:
    """
    筛选出 5 个即将到来的 S 级仲裁。
    :return:
    """
    # 读取数据
    final_arbys = read_final_arbys()

    # 获取当前时间戳，然后找到第一个比当前时间靠后的任务，随后开始筛选 S Tier
    s_list = []
    now = time.time()
    for ts, arby in final_arbys.items():
        if int(ts) < now:
            continue
        else:
            tier = arby.get("tier", "null")
            if tier == "S":
                s_list.append(arby)
                if len(s_list) == 5:
                    break
    template = read_template("s_arbys")
    data_json = json.dumps(s_list, ensure_ascii=False, indent=4)
    img = await html_to_pic(template.replace("{{DATA}}", data_json))
    return Message(MessageSegment.image(img))