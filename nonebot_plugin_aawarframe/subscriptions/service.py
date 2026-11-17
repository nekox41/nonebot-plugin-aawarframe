"""OneBot V11 群订阅命令与夜灵平野到点通知。"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nonebot import get_bots
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from ..models.errors import UserInputError
from ..providers.worldstate import WorldStateProvider
from ..worldstate.parsers.cycles import cetus_cycle
from .rules import CETUS_LEAD_MINUTES, next_cetus_occurrence, parse_cetus_rule
from .store import SubscriptionStore

logger = logging.getLogger(__name__)
BEIJING = timezone(timedelta(hours=8))


class SubscriptionService:
    def __init__(self, cache_dir: Path, provider: WorldStateProvider):
        self.provider = provider
        self.store = SubscriptionStore(cache_dir / "subscriptions.sqlite3")
        self.task: asyncio.Task[None] | None = None

    async def handle(
        self, feature: str, arguments: str, scope: tuple[str, str, str] | None
    ) -> str:
        if scope is None:
            raise UserInputError("订阅提醒暂时只支持在 QQ 群中使用。")
        bot_id, group_id, user_id = scope
        if feature == "subscribe":
            try:
                parse_cetus_rule(arguments)
                subscription, created = self.store.subscribe(bot_id, group_id, user_id)
            except ValueError as exc:
                raise UserInputError(str(exc)) from exc
            prefix = "订阅成功" if created else "该订阅已存在"
            message = (
                f"{prefix}（编号 {subscription.id}）："
                f"夜灵平野黑夜前 {CETUS_LEAD_MINUTES} 分钟提醒。"
            )
            try:
                snapshot = await self.provider.fetch()
                if not snapshot.stale:
                    now = datetime.now(timezone.utc)
                    cycle, _ = cetus_cycle(snapshot.data, now)
                    occurrence = next_cetus_occurrence(
                        cycle, now, subscription.created_at
                    )
                    local = occurrence.due_at.astimezone(BEIJING)
                    message += f"\n预计下次提醒：北京时间 {local:%m-%d %H:%M}。"
            except Exception:
                logger.warning("订阅已保存，但暂时无法计算预计提醒时间", exc_info=True)
                message += "\n暂时无法取得最新周期，后台会自动重试。"
            return message
        if feature == "list_subscriptions":
            if arguments.strip():
                raise UserInputError("用法：我的订阅")
            subscriptions = self.store.list_for(bot_id, group_id, user_id)
            if not subscriptions:
                return "你在本群暂无订阅。"
            lines = ["你在本群的订阅："]
            lines.extend(
                f"#{sub.id} 夜灵平野黑夜前 {CETUS_LEAD_MINUTES} 分钟提醒"
                for sub in subscriptions
            )
            lines.append("取消方式：取消订阅 <编号>")
            return "\n".join(lines)
        if feature == "unsubscribe":
            if not arguments.strip().isascii() or not arguments.strip().isdecimal():
                raise UserInputError("用法：取消订阅 <编号>")
            subscription_id = int(arguments.strip())
            if subscription_id <= 0 or not self.store.remove(
                subscription_id, bot_id, group_id, user_id
            ):
                raise UserInputError("未找到你在本群的该订阅。")
            return f"已取消订阅 #{subscription_id}。"
        raise UserInputError("未知订阅命令。")

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.store.recover(datetime.now(timezone.utc))
            self.task = asyncio.create_task(self._run(), name="aawarframe-subscriptions")

    async def _run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("订阅检查失败，将在下一轮重试")
            await asyncio.sleep(15)

    async def _tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        subscriptions = self.store.all_active()
        if not subscriptions:
            return
        snapshot = await self.provider.fetch()
        if snapshot.stale:
            logger.warning("官方世界状态为过期缓存，本轮不发送订阅消息")
            return
        cycle, _ = cetus_cycle(snapshot.data, now)
        for subscription in subscriptions:
            if subscription.kind != "cetus_night":
                continue
            occurrence = next_cetus_occurrence(
                cycle, now, subscription.created_at
            )
            self.store.enqueue(
                subscription.id, occurrence.key, occurrence.due_at, occurrence.event_at
            )
        self.store.expire(now)
        bots = get_bots()
        for delivery in self.store.claim_due(now, set(bots)):
            if not self.store.has_subscription(delivery.subscription_id):
                continue  # 取消订阅已通过外键级联删除对应的待发通知。
            bot = bots.get(delivery.bot_id)
            if bot is None:
                self.store.mark_failed(
                    delivery.id, delivery.attempts, now, "bot_disconnected"
                )
                continue
            local = delivery.event_at.astimezone(BEIJING)
            message = Message(
                [
                    MessageSegment.at(delivery.user_id),
                    MessageSegment.text(
                        f" 夜灵平野预计将在约 {CETUS_LEAD_MINUTES} 分钟后进入黑夜"
                        f"（北京时间 {local:%m-%d %H:%M}）。"
                    ),
                ]
            )
            try:
                await asyncio.wait_for(
                    bot.send_group_msg(group_id=int(delivery.group_id), message=message),
                    timeout=20,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "订阅通知发送失败：订阅 %s，尝试 %s",
                    delivery.subscription_id,
                    delivery.attempts,
                    exc_info=True,
                )
                self.store.mark_failed(
                    delivery.id, delivery.attempts, datetime.now(timezone.utc),
                    type(exc).__name__,
                )
            else:
                self.store.mark_sent(delivery.id, datetime.now(timezone.utc))

    async def close(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        self.store.close()
