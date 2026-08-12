# 深层科研模块
# 描述：生成深层科研（CT_LAB）数据图片
# 作者：aa
# 2026年7月22日

from pathlib import Path

from nonebot.adapters.onebot.v11 import MessageSegment

from .data_processor import extract_conquests, render_archimedea_panel, transform_to_archimedea_data
from nonebot_plugin_htmlrender import render_html
from ...common import fetch_world_state

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "assets" / "templates"


async def gen_deep_img() -> MessageSegment:
    """生成深层科研图片（CT_LAB）"""
    raw = await fetch_world_state()
    conquests = extract_conquests(raw)
    target = next((c for c in conquests if c.get("Type") == "CT_LAB"), None)
    if not target:
        return MessageSegment.text("未找到深层科研数据")
    data = transform_to_archimedea_data(target)
    html = render_archimedea_panel(data, str(_TEMPLATE_DIR / "archimedea.html"))
    img = await render_html(html)
    return MessageSegment.image(bytes(img))
