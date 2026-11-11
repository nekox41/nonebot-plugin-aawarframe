# 作用：验证裂缝分类、分页及任务卡片的安全展示。
# 编写日期：2026-11-07
# 作者：Aameow

from datetime import datetime, timedelta, timezone

import pytest

from nonebot_plugin_aawarframe.models.common import Snapshot
from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
from nonebot_plugin_aawarframe.rendering.viewmodels import paginate
from nonebot_plugin_aawarframe.services.fissures import build_fissures

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)


def mission(index, *, hard=False, seconds=600):
    return {
        "Node": f"UnknownNode{index}",
        "Modifier": f"VoidT{index % 6 + 1}",
        "Hard": hard,
        "Activation": NOW.isoformat(),
        "Expiry": (NOW + timedelta(seconds=seconds)).isoformat(),
    }


def test_normal_and_steel_are_separate_and_expired_tasks_are_hidden():
    snapshot = Snapshot(
        source="fixture",
        data={
            "ActiveMissions": [
                mission(0),
                mission(1, hard=True, seconds=300),
                mission(2, seconds=0),
                {**mission(3), "Activation": (NOW + timedelta(seconds=1)).isoformat()},
            ]
        },
    )
    normal = build_fissures(snapshot, NOW)
    steel = build_fissures(snapshot, NOW, hard=True)
    assert [item.node for item in normal.fissure_items] == ["UnknownNode0"]
    assert steel.fissure_items[0].urgent
    assert steel.fissure_mode == "steel" and normal.fissure_mode == "normal"


@pytest.mark.parametrize("count", [12, 24, 36])
def test_single_image_preserves_all_tasks_and_totals(count):
    snapshot = Snapshot(
        source="fixture", data={"ActiveMissions": [mission(i) for i in range(count)]}
    )
    card = build_fissures(snapshot, NOW)
    pages = paginate(card)
    assert [len(page.fissure_items) for page in pages] == [count]
    assert all(page.item_total == count for page in pages)
    assert [item for page in pages for item in page.fissure_items] == card.fissure_items


def test_empty_and_external_text_are_rendered_safely():
    renderer = CardRenderer()
    card = build_fissures(Snapshot(source="fixture", data={"ActiveMissions": []}), NOW)
    assert "当前暂无任务" in renderer.html(card)
    card = build_fissures(Snapshot(source="fixture", data={"ActiveMissions": [mission(0)]}), NOW)
    card.fissure_items[0].node = "<script>bad()</script>"
    html = renderer.html(card)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "By. Aameow" in html and "北京时间" in html


@pytest.mark.parametrize("hard", [False, True])
def test_two_columns_have_requested_tier_order(hard):
    from html.parser import HTMLParser

    class Groups(HTMLParser):
        def __init__(self):
            super().__init__()
            self.side = None
            self.tiers = {"left": [], "right": []}

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if "data-side" in values:
                self.side = values["data-side"]
            if tag == "h2" and self.side:
                self.tiers[self.side].append(values["class"].split("fissure-tier--")[-1])

    card = build_fissures(
        Snapshot(
            source="fixture", data={"ActiveMissions": [mission(i, hard=hard) for i in range(6)]}
        ),
        NOW,
        hard=hard,
    )
    parser = Groups()
    parser.feed(CardRenderer().html(card))
    assert parser.tiers == {
        "left": ["VoidT1", "VoidT2", "VoidT3"],
        "right": ["VoidT4", "VoidT6", "VoidT5"],
    }


def test_railjack_has_lith_meso_left_and_neo_axi_right():
    from nonebot_plugin_aawarframe.services.fissures import build_void_storms

    storms = []
    for i in range(4):
        raw = mission(i)
        raw["ActiveMissionTier"] = raw.pop("Modifier")
        storms.append(raw)
    card = build_void_storms(Snapshot(source="fixture", data={"VoidStorms": storms}), NOW)
    html = CardRenderer().html(card)
    left, right = html.split('data-side="right"', 1)
    assert "古纪" in left and "前纪" in left
    assert "中纪" not in left and "后纪" not in left
    assert right.index("中纪") < right.index("后纪")
    assert "UnknownNode0" in html
