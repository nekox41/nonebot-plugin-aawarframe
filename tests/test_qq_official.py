"""Issue #14: QQ 官方群/C2C/频道事件、OpenID、发送与图片查询。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

pytest.importorskip("nonebot.adapters.qq")

from nonebot.adapters.onebot.v11 import Message as OBMessage
from nonebot.adapters.onebot.v11 import MessageSegment as OBSegment
from nonebot.adapters.qq import Message as QQMessage
from nonebot.adapters.qq import MessageSegment as QQSegment

from nonebot_plugin_aawarframe.admin.control import ACL
from nonebot_plugin_aawarframe.commands import router
from nonebot_plugin_aawarframe.protocols.qq import (
    CHANNEL_PREFIX,
    GROUP_PREFIX,
    group_scope,
    is_qq_bot,
    message_image,
    qq_messages,
    send_reply,
    send_subscription,
)
from nonebot_plugin_aawarframe.subscriptions.service import SubscriptionService

QQ_BOT = "test-bot-app-id"
GROUP = "g_openid-example_1234"
MEMBER = "m_openid-example_4567"
CHANNEL = "channel_id-example_9"


def fake_qq_bot():
    return SimpleNamespace(
        type="QQ", self_id=QQ_BOT,
        send=AsyncMock(),
        send_to_group=AsyncMock(),
        send_to_channel=AsyncMock(),
    )


def fake_event(group=GROUP, user=MEMBER):
    return SimpleNamespace(
        group_openid=group,
        get_user_id=lambda: user,
        get_plaintext=lambda: "订阅 夜灵",
    )


def test_real_qq_official_group_event_model_and_command_route(monkeypatch):
    """使用官方适配器的真实事件模型，而不只是 SimpleNamespace。"""
    from nonebot.adapters.qq import GroupMessageCreateEvent

    event = GroupMessageCreateEvent.model_validate({
        "id": "official-message-id",
        "content": "订阅 夜灵",
        "timestamp": "2026-11-19T09:00:00+08:00",
        "author": {
            "id": "official-sender",
            "username": "player",
            "bot": False,
            "member_openid": MEMBER,
            "member_role": "member",
        },
        "group_id": "legacy-group-id",
        "group_openid": GROUP,
        "message_type": 0,
        "mentions": [],
        "attachments": [],
    })
    bot = fake_qq_bot()
    assert group_scope(bot, event) == (QQ_BOT, GROUP_PREFIX + GROUP, MEMBER)
    assert router.command_identity_from_event(event) == (MEMBER, GROUP_PREFIX + GROUP)
    assert event.get_plaintext() == "订阅 夜灵"


def test_official_openid_scope_and_separate_group_channel():
    bot = fake_qq_bot()
    event = fake_event()
    assert is_qq_bot(bot)
    assert group_scope(bot, event) == (
        QQ_BOT, GROUP_PREFIX + GROUP, MEMBER
    )
    assert router.command_identity_from_event(event) == (MEMBER, GROUP_PREFIX + GROUP)
    channel_event = SimpleNamespace(
        channel_id=CHANNEL, guild_id="guild-X", get_user_id=lambda: "guilduser"
    )
    assert group_scope(bot, channel_event) == (
        QQ_BOT, CHANNEL_PREFIX + CHANNEL, "guilduser"
    )
    assert group_scope(bot, SimpleNamespace(get_user_id=lambda: MEMBER)) is None
    assert router.command_identity_from_event(channel_event) == (
        "guilduser", CHANNEL_PREFIX + CHANNEL
    )
    assert ACL(allow_users=[MEMBER], allow_groups=[GROUP_PREFIX + GROUP]).permits(
        MEMBER, GROUP_PREFIX + GROUP
    )
    assert not ACL(deny_groups=[GROUP_PREFIX + GROUP]).permits(MEMBER, GROUP_PREFIX + GROUP)
    with pytest.raises(ValueError):
        ACL(allow_groups=["../invalid"])


def test_official_qq_outbound_text_local_image_and_multipage():
    msg = OBMessage([
        OBSegment.text("hello"),
        OBSegment.image(b"fake-png-1"),
        OBSegment.text("second"),
        OBSegment.image(b"fake-png-2"),
    ])
    pages = qq_messages(msg)
    assert len(pages) == 2
    assert [segment.type for segment in pages[0]] == ["text", "file_image", "text"]
    assert [segment.type for segment in pages[1]] == ["file_image"]
    assert pages[0][1].data["content"] == b"fake-png-1"
    assert pages[1][0].data["content"] == b"fake-png-2"
    assert isinstance(pages[0], QQMessage)

    mixed = OBMessage([OBSegment.at(MEMBER), OBSegment.text(" done")])
    output = qq_messages(mixed)[0]
    assert [part.type for part in output] == ["mention_user", "text"]
    assert output[0].data["user_id"] == MEMBER


@pytest.mark.asyncio
async def test_reply_uses_qq_bot_send_not_onebot_api():
    bot = fake_qq_bot()
    matcher = SimpleNamespace(finish=AsyncMock())
    original = OBMessage([OBSegment.text("查询完成")])
    await send_reply(bot, fake_event(), original, matcher)
    bot.send.assert_awaited_once()
    assert bot.send.await_args.args[1][0].type == "text"
    assert bot.send.await_args.args[1][0].data["text"] == "查询完成"
    matcher.finish.assert_awaited_once_with()
    assert not hasattr(bot, "send_group_msg")


@pytest.mark.asyncio
async def test_official_group_notification_uses_openid_and_file_image(tmp_path):
    bot = fake_qq_bot()
    delivery = SimpleNamespace(group_id=GROUP_PREFIX + GROUP, user_id=MEMBER)
    await send_subscription(bot, delivery, image=b"png", fallback="fallback")
    sent = bot.send_to_group.await_args.kwargs
    assert sent["group_openid"] == GROUP
    assert [seg.type for seg in sent["message"]] == [
        "mention_user", "text", "file_image"
    ]
    assert sent["message"][0].data["user_id"] == MEMBER
    assert sent["message"][-1].data["content"] == b"png"

    bot.send_to_group.reset_mock()
    delivery.group_id = CHANNEL_PREFIX + CHANNEL
    await send_subscription(bot, delivery, image=None, fallback="test")
    bot.send_to_group.assert_not_awaited()
    assert bot.send_to_channel.await_args.kwargs["channel_id"] == CHANNEL
    assert [seg.type for seg in bot.send_to_channel.await_args.kwargs["message"]] == [
        "text", "text"
    ]


@pytest.mark.asyncio
async def test_official_notification_scheduler_and_db_scope(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from nonebot_plugin_aawarframe.models.common import Snapshot
    from nonebot_plugin_aawarframe.models.worldstate import CycleState

    now = datetime.now(timezone.utc) + timedelta(minutes=30)
    cycle = CycleState(
        location="夜灵平野", state="白天", next_state="黑夜",
        expiry=now + timedelta(minutes=15), basis="test",
    )
    provider = SimpleNamespace(fetch=AsyncMock(return_value=Snapshot(
        data={"test": True}, source="test",
    )))
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.cetus_cycle",
        lambda data, stamp: (cycle, []),
    )
    bot = fake_qq_bot()
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.get_bots",
        lambda: {QQ_BOT: bot},
    )
    service = SubscriptionService(tmp_path, provider)
    try:
        service.store.subscribe(QQ_BOT, GROUP_PREFIX + GROUP, MEMBER)
        await service._tick(now)
        await service._tick(now)
        assert bot.send_to_group.await_count == 1
        assert bot.send_to_group.await_args.kwargs["group_openid"] == GROUP
        assert service.store.list_for(QQ_BOT, GROUP_PREFIX + GROUP, MEMBER)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_qq_official_attachment_and_reply_image():
    image = b"qq-image-payload"
    calls = []

    def serve(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=image)

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        http = SimpleNamespace(client=client)
        segment = QQSegment.image("https://gchat.qpic.cn/a/b")
        event = SimpleNamespace(
            get_message=lambda: QQMessage([segment]),
            get_reply_message=lambda: None,
        )
        assert await message_image(fake_qq_bot(), event, http) == image
        event = SimpleNamespace(
            get_message=lambda: QQMessage(QQSegment.text("分析")),
            get_reply_message=lambda: QQMessage([segment]),
        )
        assert await message_image(fake_qq_bot(), event, http) == image
        assert len(calls) == 2


@pytest.mark.asyncio
async def test_official_notification_failure_does_not_mark_sent(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from nonebot_plugin_aawarframe.models.common import Snapshot
    from nonebot_plugin_aawarframe.models.worldstate import CycleState

    now = datetime.now(timezone.utc) + timedelta(minutes=30)
    cycle = CycleState(
        location="夜灵平野", state="白天", next_state="黑夜",
        expiry=now + timedelta(minutes=15), basis="test"
    )
    provider = SimpleNamespace(fetch=AsyncMock(return_value=Snapshot(
        data={"test": True}, source="test"
    )))
    bot = fake_qq_bot()
    bot.send_to_group.side_effect = RuntimeError("QQ proactive permission denied")
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.get_bots",
        lambda: {QQ_BOT: bot},
    )
    monkeypatch.setattr(
        "nonebot_plugin_aawarframe.subscriptions.service.cetus_cycle",
        lambda data, stamp: (cycle, []),
    )
    service = SubscriptionService(tmp_path, provider)
    try:
        service.store.subscribe(QQ_BOT, GROUP_PREFIX + GROUP, MEMBER)
        await service._tick(now)
        assert bot.send_to_group.await_count == 1
        record = service.store.db.execute(
            "SELECT status,last_error FROM subscription_deliveries"
        ).fetchone()
        assert record["status"] != "sent"
        assert record["last_error"] is not None
    finally:
        await service.close()
