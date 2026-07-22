# 夜灵模块
# 描述：从 worldState 获取数据，生成夜晚图片
# 作者：aa
# 2026年7月22日

from datetime import datetime, timezone, timedelta
from pathlib import Path

from nonebot.adapters.onebot.v11 import MessageSegment

from ...util.browser_manager import html_to_pic
from ...util.data_fetcher import fetch_world_state


_CST = timezone(timedelta(hours=8))  # 中国标准时间 UTC+8


def _ms_to_hms(ms: int) -> str:
    """将毫秒转换为中文时间格式，零值单位不显示"""
    total_seconds = max(ms // 1000, 0)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours:02d}小时")
    if minutes > 0:
        parts.append(f"{minutes:02d}分")
    parts.append(f"{seconds:02d}秒")
    return "".join(parts)


def _ts_to_hhmm(ts_ms: int) -> str:
    """将毫秒时间戳转换为 HH:MM 24小时制格式（北京时间 UTC+8）"""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=_CST)
    return dt.strftime("%H:%M")


async def extract_data() -> dict[str, object]:
    """提取生成夜灵时钟图片所需要的数据返回"""
    result: dict[str, object] = {}
    raw = await fetch_world_state()
    all_mission = raw.get("SyndicateMissions", [])
    cetus: dict = {}
    for mission in all_mission:
        if mission.get("Tag", "") == "CetusSyndicate":
            cetus.update(mission)
        else:
            continue

    # 我们需要输出 当前状态、剩余时间、以及接下来的黑夜时间
    # 判断当前状态需要的数据 赏金结束时间 当前时间 白天持续时间 黑夜持续时间
    # 赏金结束时间是毫秒
    day_time = 6000000   # 白天 100 分钟
    night_time = 3000000  # 黑夜 50 分钟
    full_cycle = day_time + night_time  # 完整昼夜循环 150 分钟

    start_time = int(cetus["Activation"]["$date"]["$numberLong"])
    end_time = int(cetus["Expiry"]["$date"]["$numberLong"])
    night_start = start_time + day_time
    current_time = int(raw.get("Time", 0)) * 1000

    # 如果当前时间还没到夜晚开始时间，证明是白天
    if current_time >= night_start:
        result["Current"] = "夜晚"
    else:
        result["Current"] = "白天"

    # 我们需要计算出当前状态的剩余时间
    # 如果当前是白天，那么就是当前时间到夜晚开始时间
    # 如果当前是夜晚，那么就是当前时间到赏金结束时间
    if result["Current"] == "夜晚":
        result["ToEnd"] = _ms_to_hms(end_time - current_time)
    else:
        result["ToEnd"] = _ms_to_hms(night_start - current_time)

    # 下一次夜晚到来的时间，如果当前状态是白天，那么就是night_start
    # 如果当前状态是黑夜，就是当前这个循环结束之后加上day_time，也就是下一次循环中的night_start
    if result["Current"] == "白天":
        next_night = night_start
    else:
        next_night = end_time + day_time

    # 以00:00 24小时制的格式字符串存储，计算出下一次之后再计算出接下来4个，
    # 总共5个夜晚到来的时间，然后以列表形式存到result里面
    night_times: list[str] = []
    for i in range(5):
        night_ts = next_night + i * full_cycle
        night_times.append(_ts_to_hhmm(night_ts))
    result["NightTimes"] = night_times

    return result


_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "assets" / "templates"


async def gen_eidolon_img() -> MessageSegment:
    """生成夜灵平原时钟图片"""
    data = await extract_data()

    # 构建夜晚时间行 HTML
    night_rows = "\n".join(
        f'    <tr>\n        <td class="time">{t}</td>\n    </tr>'
        for t in data["NightTimes"]
    )

    # 读取模板文件
    template_path = _TEMPLATE_DIR /  "eidolon_clock.html"
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # 填充模板占位符
    html = template.replace("{{CURRENT_STATE}}", data["Current"])
    html = html.replace("{{REMAINING_TIME}}", data["ToEnd"])
    html = html.replace("{{NIGHT_TIMES_ROWS}}", night_rows)

    # 生成图片（CSS 已内联，无需 base_url）
    img_bytes = await html_to_pic(html)

    return MessageSegment.image(img_bytes)