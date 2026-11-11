# 作用：验证区域周期边界、独立查询、区域隔离与 WebP 渲染契约。
# 编写日期：2026-11-07
# 作者：Aameow

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.models.common import CycleDisplay, Snapshot
from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
from nonebot_plugin_aawarframe.services.cycles import build_cycle, build_plains
from nonebot_plugin_aawarframe.worldstate.parsers.cycles import (
    VALLIS_ANCHOR,
    cetus_cycle,
    duviri_cycle,
    vallis_cycle,
)

NOW = datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc)


def snapshot():
    return Snapshot(
        source="fixture",
        fetched_at=NOW,
        data={
            "SyndicateMissions": [
                {
                    "Tag": "CetusSyndicate",
                    "Activation": NOW.isoformat(),
                    "Expiry": (NOW + timedelta(minutes=150)).isoformat(),
                }
            ]
        },
    )


def test_cetus_switches_to_night_at_boundary():
    day, _ = cetus_cycle(snapshot().data, NOW + timedelta(minutes=99, seconds=59))
    night, _ = cetus_cycle(snapshot().data, NOW + timedelta(minutes=100))
    assert day.state == "白天" and night.state == "黑夜"
    assert day.expiry == NOW + timedelta(minutes=100)
    assert night.expiry == NOW + timedelta(minutes=150)


def test_vallis_and_duviri_wrap_at_cycle_boundaries():
    assert vallis_cycle(VALLIS_ANCHOR + timedelta(seconds=399)).state == "温暖"
    assert vallis_cycle(VALLIS_ANCHOR + timedelta(seconds=400)).state == "寒冷"
    assert vallis_cycle(VALLIS_ANCHOR + timedelta(seconds=1600)).state == "温暖"
    end = duviri_cycle(NOW).expiry
    assert duviri_cycle(end - timedelta(microseconds=1)).next_state == duviri_cycle(end).state
    assert duviri_cycle(end).expiry > end


@pytest.mark.parametrize("feature", ["cetus", "vallis", "cambion", "duviri"])
def test_single_query_matches_overview(feature):
    single = build_cycle(snapshot(), NOW, feature)
    overview = build_plains(snapshot(), NOW)
    assert single.cycle_items[0] in overview.cycle_items
    assert len(single.cycle_items) == 1
    if feature == "cetus":
        assert len(single.sections[0].rows) == 5
        assert single.sections[0].rows[0][1] == "11-07 09:40"


def test_missing_cetus_data_does_not_hide_other_regions():
    card = build_plains(Snapshot(data={}, source="fixture"), NOW)
    assert len(card.cycle_items) == 5
    assert [item.available for item in card.cycle_items] == [False, True, False, True, True]


def test_cycle_template_escapes_names_and_has_signature():
    card = build_cycle(snapshot(), NOW, "cetus")
    card.cycle_items[0] = CycleDisplay(name="<script>bad()</script>", state="白天", available=False)
    html = CardRenderer().html(card)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "By. Aameow" in html and "北京时间" in html
    assert "官方希图斯赏金结束时间推算" not in html


async def test_renderer_encodes_webp_at_qq_width(monkeypatch):
    import nonebot_plugin_htmlrender

    render = AsyncMock(return_value=b"png-fixture")
    monkeypatch.setattr(nonebot_plugin_htmlrender, "render_html", render)
    renderer = CardRenderer()
    encoder = AsyncMock(return_value=b"webp-fixture")
    monkeypatch.setattr(renderer, "_encode_webp", encoder)
    monkeypatch.setattr(
        renderer, "_fit_document", AsyncMock(side_effect=lambda document: (document, 600, 900))
    )
    try:
        images = await renderer.render(build_plains(snapshot(), NOW))
        assert images == [b"webp-fixture"]
        encoder.assert_awaited_once_with(b"png-fixture")
        assert render.await_args.kwargs["image_format"] == "png"
        assert render.await_args.kwargs["width"] == 600
        assert render.await_args.kwargs["height"] == 900
    finally:
        await renderer.close()
