# 作用：验证突击、执刑官和入侵的有效期、中文显示、进度及命令回复。
# 编写日期：2026-11-13
# 作者：Aameow

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.models.common import DataStatus, Snapshot
from nonebot_plugin_aawarframe.rendering.renderer import CardRenderer
from nonebot_plugin_aawarframe.rendering.viewmodels import paginate
from nonebot_plugin_aawarframe.services.operations import build_invasions, build_sortie
from nonebot_plugin_aawarframe.services.worldstate import WorldStateService


def recorded():
    snapshot = Snapshot.model_validate_json(
        (Path(__file__).parent / 'fixtures/operations-recorded.json').read_text()
    )
    return snapshot, datetime.fromtimestamp(snapshot.data['Time'], timezone.utc)


def test_sortie_preserves_stage_order_modifiers_and_valid_cycle():
    snapshot, now = recorded()
    card = build_sortie(snapshot, now)
    assert card.status == DataStatus.OK and not card.notes
    board = card.operation_board
    assert [task.number for task in board.tasks] == [1, 2, 3]
    assert [task.mission for task in board.tasks] == ['清巢', '挖掘', '间谍']
    assert '火焰' in board.tasks[0].modifier and board.tasks[2].modifier == '电磁异常'
    assert board.faction == '感染者' and board.expiry > now
    assert build_sortie(snapshot, board.expiry).status == DataStatus.EMPTY
    assert build_sortie(snapshot, now - timedelta(days=2)).status == DataStatus.EMPTY
    html = CardRenderer().html(card)
    assert 'operation-task' in html and '电磁异常' in html


@pytest.mark.parametrize('boss,shard,tone', [
    ('SORTIE_BOSS_AMAR', '深红执刑官源力石', 'red'),
    ('SORTIE_BOSS_BOREAL', '蔚蓝执刑官源力石', 'blue'),
    ('SORTIE_BOSS_NIRA', '琥珀执刑官源力石', 'gold'),
])
def test_archon_shard_is_selected_from_boss(boss, shard, tone):
    snapshot, now = recorded()
    snapshot.data['LiteSorties'][0]['Boss'] = boss
    card = build_sortie(snapshot, now, archon=True)
    assert len(card.operation_board.tasks) == 3
    assert card.operation_board.reward == shard and card.operation_board.tone == tone
    assert 'Tau' not in card.operation_board.reward
    assert not any(task.modifier for task in card.operation_board.tasks)
    assert build_sortie(snapshot, card.operation_board.expiry, archon=True).status == DataStatus.EMPTY


def test_invasion_factions_rewards_and_progress_are_correct():
    snapshot, now = recorded()
    card = build_invasions(snapshot, now)
    items = card.operation_board.invasions
    assert len(items) == 4 and not card.notes
    ordinary = next(item for item in items if item.node == 'Enceladus')
    assert ordinary.attacker == 'Corpus' and ordinary.defender == 'Grineer'
    assert ordinary.attacker_percent == pytest.approx((1 + 22869 / 49000) * 50)
    assert ordinary.attacker_rewards == ['电磁力场装置 ×3']
    assert ordinary.defender_rewards == ['爆燃喷射器 ×3']
    infected = next(item for item in items if item.node == 'Cerberus')
    assert infected.infestation and not infected.attacker_rewards
    assert infected.attacker_percent == pytest.approx((1 - 36744 / 45000) * 100)
    assert infected.defender_percent == pytest.approx(36744 / 45000 * 100)
    assert '清除' in CardRenderer().html(card)


def test_bad_stage_keeps_other_stage_numbers_and_bad_invasion_does_not_drop_all_data():
    snapshot, now = recorded()
    del snapshot.data['Sorties'][0]['Variants'][1]['node']
    card = build_sortie(snapshot, now)
    assert [task.number for task in card.operation_board.tasks] == [1, 3] and card.notes
    snapshot.data['Invasions'][0]['Goal'] = 0
    card = build_invasions(snapshot, now)
    assert len(card.operation_board.invasions) == 3 and card.notes


def test_invasion_empty_future_entries_and_progress_clamping():
    snapshot, now = recorded()
    for item in snapshot.data['Invasions']:
        item['Completed'] = True
    empty = build_invasions(snapshot, now)
    assert empty.status == DataStatus.EMPTY
    assert "当前暂无入侵任务" in CardRenderer().html(empty)
    first = snapshot.data['Invasions'][0]
    first['Completed'] = False
    first['Count'] = first['Goal'] * 2
    item = build_invasions(snapshot, now).operation_board.invasions[0]
    assert item.attacker_percent == 100 and item.defender_percent == 0
    first['Activation'] = (now + timedelta(hours=1)).isoformat()
    assert build_invasions(snapshot, now).status == DataStatus.EMPTY


def test_many_invasions_paginate_without_losing_entries():
    snapshot, now = recorded()
    card = build_invasions(snapshot, now)
    item = card.operation_board.invasions[0]
    card.operation_board.invasions = [item.model_copy(update={'node': str(i)}) for i in range(21)]
    pages = paginate(card)
    assert [len(page.operation_board.invasions) for page in pages] == [20, 1]
    assert [item.node for page in pages for item in page.operation_board.invasions] == list(map(str, range(21)))
    assert 'invasion-columns--two' in CardRenderer().html(pages[0])


@pytest.mark.parametrize('feature', ['sortie', 'archon', 'invasions'])
async def test_service_routes_and_commands_render_images(feature, monkeypatch):
    snapshot, now = recorded()
    monkeypatch.setattr('nonebot_plugin_aawarframe.services.worldstate.utcnow', lambda: now)
    service = WorldStateService(SimpleNamespace(fetch=AsyncMock(return_value=snapshot)))
    card = await service.query(feature)
    assert card.operation_board and card.status == DataStatus.OK
    runtime = SimpleNamespace(world=service, renderer=SimpleNamespace(render=AsyncMock(return_value=[b'webp'])))
    monkeypatch.setattr(router, 'get_runtime', lambda: runtime)
    message = await router.dispatch(feature)
    assert [segment.type for segment in message] == ['image']
    registered = []
    monkeypatch.setattr(router, 'register', lambda *args: registered.append(args))
    router.setup()
    for command, name in [('突击', 'sortie'), ('执刑官', 'archon'), ('入侵', 'invasions')]:
        assert (command, set(), name) in registered
