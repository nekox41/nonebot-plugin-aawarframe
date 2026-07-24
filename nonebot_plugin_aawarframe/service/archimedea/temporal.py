# 时光科研模块
# 描述：生成时光科研（CT_HEX）数据图片
# 作者：aa
# 2026年7月22日

from pathlib import Path

from nonebot.adapters.onebot.v11 import MessageSegment

from .data_processor import extract_conquests, render_archimedea_panel, transform_to_archimedea_data
from ...common.browser_manager import html_to_pic
from ...common.data_fetcher import fetch_world_state

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "assets" / "templates"


async def gen_temporal_img() -> MessageSegment:
    """生成时光科研图片（CT_HEX）"""
    raw = await fetch_world_state()
    conquests = extract_conquests(raw)
    target = next((c for c in conquests if c.get("Type") == "CT_HEX"), None)
    if not target:
        return MessageSegment.text("未找到时光科研数据")
    data = transform_to_archimedea_data(target)
    html = render_archimedea_panel(data, str(_TEMPLATE_DIR / "archimedea.html"))
    img_bytes = await html_to_pic(html)
    return MessageSegment.image(img_bytes)
