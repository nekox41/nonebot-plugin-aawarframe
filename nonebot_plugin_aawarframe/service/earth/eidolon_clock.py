# 夜灵模块
# 描述：从 worldState 获取数据，生成夜灵平野昼夜时钟图片
# 作者：aa
# 2026年7月22日

from datetime import datetime, timezone, timedelta
from typing import Any

from jinja2 import Environment, select_autoescape

from nonebot_plugin_htmlrender import render_html, RenderedImage
from ...common import fetch_world_state, read_template


_CST = timezone(timedelta(hours=8))  # 中国标准时间 UTC+8

DAY_TIME_MS = 6_000_000       # 白天 100 分钟
NIGHT_TIME_MS = 3_000_000     # 黑夜 50 分钟
FULL_CYCLE_MS = DAY_TIME_MS + NIGHT_TIME_MS  # 完整昼夜循环 150 分钟

ORDINALS = ["第一个", "第二个", "第三个", "第四个", "第五个"]

_JINJA_ENV = Environment(
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _ms_to_hms(ms: int) -> str:
    """将毫秒转换为中文时间格式，零值单位不显示。"""
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
    """将毫秒时间戳转换为 HH:MM 24 小时制格式，北京时间 UTC+8。"""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=_CST)
    return dt.strftime("%H:%M")


def _ts_to_datetime_text(ts_ms: int) -> str:
    """将毫秒时间戳转换为页面展示用的北京时间文本。"""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=_CST)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _world_date_ms(value: dict[str, Any]) -> int:
    """解析 worldState 中的 MongoDB Date 结构。"""
    return int(value["$date"]["$numberLong"])


def _clamp_percent(value: float) -> float:
    """限制百分比在 0-100 之间，并保留 1 位小数。"""
    return round(max(0.0, min(100.0, value)), 1)


async def extract_data() -> dict[str, Any]:
    """提取生成夜灵平野时钟图片所需的数据。"""
    raw = await fetch_world_state()

    missions = raw.get("SyndicateMissions", [])
    cetus = next(
        (
            mission
            for mission in missions
            if mission.get("Tag") == "CetusSyndicate"
        ),
        None,
    )

    if not cetus:
        raise RuntimeError("worldState 中未找到 CetusSyndicate，无法生成夜灵平野时钟。")

    start_time = _world_date_ms(cetus["Activation"])

    raw_time = raw.get("Time")
    if raw_time is None:
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    else:
        current_time = int(raw_time) * 1000

    # 根据 Activation 作为昼夜循环起点，做循环归一化，避免数据轻微滞后导致判断错误。
    elapsed = max(current_time - start_time, 0)
    cycle_index = elapsed // FULL_CYCLE_MS
    cycle_start = start_time + cycle_index * FULL_CYCLE_MS
    phase_ms = current_time - cycle_start

    night_start = cycle_start + DAY_TIME_MS
    night_end = cycle_start + FULL_CYCLE_MS

    is_night = phase_ms >= DAY_TIME_MS

    if is_night:
        current_state = "黑夜"
        remaining_label = "黑夜结束"
        remaining_ms = night_end - current_time
        next_night = night_end + DAY_TIME_MS
        phase_elapsed = phase_ms - DAY_TIME_MS
        phase_total = NIGHT_TIME_MS
        state_icon = "☾"
        state_tag_class = "eidolon-tag-night"
        phase_name = "黑夜进行中"
    else:
        current_state = "白天"
        remaining_label = "黑夜到来"
        remaining_ms = night_start - current_time
        next_night = night_start
        phase_elapsed = phase_ms
        phase_total = DAY_TIME_MS
        state_icon = "☀"
        state_tag_class = "eidolon-tag-day"
        phase_name = "白天进行中"

    phase_progress = _clamp_percent(phase_elapsed / phase_total * 100)

    night_times: list[dict[str, str]] = []
    for i, ordinal in enumerate(ORDINALS):
        night_ts = next_night + i * FULL_CYCLE_MS
        night_times.append(
            {
                "ordinal": ordinal,
                "title": f"{ordinal}黑夜",
                "time": _ts_to_hhmm(night_ts),
            }
        )

    return {
        "is_night": is_night,
        "current_state": current_state,
        "remaining_label": remaining_label,
        "remaining_time": _ms_to_hms(remaining_ms),
        "state_icon": state_icon,
        "state_tag_class": state_tag_class,
        "phase_name": phase_name,
        "phase_progress": phase_progress,
        "night_times": night_times,
        "updated_at": _ts_to_datetime_text(current_time),
    }


async def render_eidolon_html() -> str:
    """渲染夜灵平野时钟 HTML。"""
    data = await extract_data()

    # 推荐内联 base.css，避免 render_html 无法解析相对路径 CSS。
    base_css = await read_template("base.css")
    template_text = await read_template("eidolon_clock.html")

    template = _JINJA_ENV.from_string(template_text)
    return template.render(
        **data,
        base_css=base_css,
    )


async def gen_eidolon_img() -> RenderedImage:
    """生成夜灵平野时钟图片。"""
    html = await render_eidolon_html()

    img = await render_html(html)

    return img
