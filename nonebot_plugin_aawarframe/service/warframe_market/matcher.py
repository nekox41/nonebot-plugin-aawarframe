import json
from pathlib import Path
from typing import Optional
from rapidfuzz import process, fuzz
import re

# 加载别名映射（模块级别，只加载一次）
WM_PITEMS_PATH = Path(__file__).parent.parent.parent / "assets" / "wm_pitems.json"

with open(WM_PITEMS_PATH, "r", encoding="utf-8") as f:
    ITEM_MAP = json.load(f)

# 通用清洗函数：只保留中文字符、英文字母、数字，英文统一转小写
def clean_text(text: str) -> str:
    return re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '', text).lower()

def match_slug(user_input: str) -> Optional[str]:
    """
    模糊匹配用户输入，返回对应的 slug
    """
    cleaned = clean_text(user_input)

    if not cleaned:
        return None

    # 1. 完全匹配
    if cleaned in ITEM_MAP:
        return ITEM_MAP[cleaned]

    # 2. rapidfuzz 模糊匹配
    result = process.extractOne(
        cleaned,
        ITEM_MAP.keys(),
        scorer=fuzz.WRatio,
        score_cutoff=70
    )

    if result:
        return ITEM_MAP[result[0]]

    return None
