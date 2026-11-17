"""QQ 群订阅：单一调度器、去重事件、图片提醒与其他订阅状态。"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from nonebot import get_bots
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from ..commands.parsing import parse_riven_market
from ..localization.riven_attributes import allowed, attributes
from ..localization.rivens import resolve_riven_weapon
from ..models.common import Card, Section
from ..models.errors import UserInputError
from ..models.riven_market import RivenMarketQuery
from ..providers.worldstate import WorldStateProvider
from ..rendering.viewmodels import fallback_text
from ..worldstate.parsers.cycles import cetus_cycle
from .rules import (
    CETUS_LEAD_MINUTES,
    next_cetus_occurrence,
    parse_rule,
)
from .sources import arbitration_events, fissure_events
from .store import Subscription, SubscriptionStore
from .targets import aya_events, efficient_bounty_events, market_rank_events, riven_events

logger = logging.getLogger(__name__)
UTC = timezone.utc
BEIJING = timezone(timedelta(hours=8))
MARKET_INTERVAL = timedelta(minutes=1)
RIVEN_INTERVAL = timedelta(minutes=3)


class SubscriptionService:
    def __init__(
        self, cache_dir: Path, provider: WorldStateProvider,
        *, arbitration=None, market=None, riven_market=None, renderer=None,
    ):
        self.provider = provider
        self.arbitration = arbitration
        self.market = market
        self.riven_market = riven_market
        self.renderer = renderer
        self.store = SubscriptionStore(cache_dir / "subscriptions.sqlite3")
        self.task: asyncio.Task[None] | None = None
        self._market_checked: dict[tuple, datetime] = {}


    async def handle(
        self, feature: str, arguments: str, scope: tuple[str, str, str] | None
    ) -> str:
        if scope is None:
            raise UserInputError("订阅提醒暂时只支持在 QQ 群中使用。")
        bot_id, group_id, user_id = scope
        if feature == "subscribe":
            try:
                spec = parse_rule(arguments)
                rule = spec.rule
                if spec.kind == "market_user":
                    if self.market is None:
                        raise ValueError("Market 数据源暂不可用。")
                    user = rule["user"]
                    endpoint = "userId" if (
                        len(user) == 24 and all(c in "0123456789abcdef" for c in user.lower())
                    ) else "user"
                    profile = await self.market.provider.request(
                        "/" + endpoint + "/" + quote(user, safe="")
                    )
                    if not isinstance(profile, dict) or not profile.get("slug"):
                        raise ValueError("未找到此 Warframe Market 用户。")
                    rule = {
                        "user": profile["slug"],
                        "name": profile.get("ingameName", profile["slug"]),
                    }
                if spec.kind == "riven":
                    if self.riven_market is None:
                        raise ValueError("紫卡 Market 数据源暂不可用。")
                    query = parse_riven_market(rule["query"])
                    if not query.positives and query.negative is None:
                        raise ValueError("紫卡订阅必须指定至少一个词条。")
                    weapon = resolve_riven_weapon(query.weapon)
                    kind = weapon.metadata.get("weapon_type") or weapon.metadata.get(
                        "rivenType"
                    )
                    catalog = attributes()
                    for slug in query.positives:
                        if not allowed(catalog[slug], kind, True):
                            raise ValueError("该武器不支持正面词条：" + slug)
                    if query.negative not in {None, "has"} and not allowed(
                        catalog[query.negative], kind, False
                    ):
                        raise ValueError("该武器不支持负面词条：" + query.negative)
                    rule = {
                        "weapon": weapon.name(),
                        "slug": weapon.metadata.get("slug") or weapon.id,
                        "positives": sorted(query.positives),
                        "negative": query.negative,
                        "price": rule["price"],
                    }
                subscription, created = self.store.subscribe(
                    bot_id, group_id, user_id, spec.kind, rule
                )
            except UserInputError:
                raise
            except ValueError as exc:
                raise UserInputError(str(exc)) from exc
            prefix = "订阅成功" if created else "该订阅已存在"
            message = f"{prefix}（编号 {subscription.id}）：{subscription.label}。"
            if spec.kind == "cetus_night":
                try:
                    snapshot = await self.provider.fetch()
                    if not snapshot.stale:
                        now = datetime.now(UTC)
                        cycle, _ = cetus_cycle(snapshot.data, now)
                        occurrence = next_cetus_occurrence(
                            cycle, now, subscription.created_at
                        )
                        message += (
                            "\n预计下次提醒：北京时间 "
                            f"{occurrence.due_at.astimezone(BEIJING):%m-%d %H:%M}。"
                        )
                except Exception:
                    logger.warning("夜灵订阅保存成功，但无法计算提醒时间", exc_info=True)
                    message += "\n暂时无法取得最新周期，后台会自动重试。"
            elif spec.kind == "arbitration":
                message += "\n所有 S 级仲裁将在开始前固定 15 分钟提醒。"
            elif spec.kind == "market_user":
                message += "\n用户处于 ingame 状态时，每分钟检查卖单排名，失去最低价位置时提醒。"
            else:
                message += "\n首次检查建立基线；之后发现新的符合条件事件才提醒。"
            return message
        if feature == "list_subscriptions":
            if arguments.strip():
                raise UserInputError("用法：我的订阅")
            subscriptions = self.store.list_for(bot_id, group_id, user_id)
            if not subscriptions:
                return "你在本群暂无订阅。"
            statuses = self.store.statuses_for(bot_id, group_id, user_id)
            lines = ["你在本群的订阅："]
            lines.extend(
                f"#{sub.id} {sub.label} — {statuses.get(sub.id, '等待检查')}"
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
            self.store.recover(datetime.now(UTC))
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

    async def _world_tick(self, subscriptions: list[Subscription], now: datetime) -> None:
        relevant = [s for s in subscriptions if s.kind in {"cetus_night", "fissure", "bounty", "aya"}]
        if not relevant:
            return
        try:
            snapshot = await self.provider.fetch()
            if snapshot.stale:
                raise ValueError("官方世界状态仍是过期缓存")
        except Exception:
            logger.warning("世界状态获取失败，跳过本轮订阅事件", exc_info=True)
            for sub in relevant:
                self.store.set_status(sub.id, "世界状态暂不可用")
            return
        for sub in relevant:
            try:
                if sub.kind == "cetus_night":
                    cycle, _ = cetus_cycle(snapshot.data, now)
                    occurrence = next_cetus_occurrence(cycle, now, sub.created_at)
                    self.store.enqueue(
                        sub.id, occurrence.key, occurrence.due_at, occurrence.event_at,
                        "夜灵平野即将进入黑夜",
                        f"预计北京时间 {occurrence.event_at.astimezone(BEIJING):%m-%d %H:%M} "
                        f"进入黑夜 · 提前 {CETUS_LEAD_MINUTES} 分钟提醒",
                    )
                    self.store.set_status(
                        sub.id, f"目前{cycle.state} · 下次黑夜 "
                        f"{occurrence.event_at.astimezone(BEIJING):%m-%d %H:%M}",
                    )
                else:
                    if sub.kind == "fissure":
                        events, status = fissure_events(snapshot.data, now, sub.rule)
                    elif sub.kind == "bounty":
                        if sub.rule.get("region") not in {"扎里曼", "圣所", "1999"}:
                            self.store.set_status(sub.id, "旧版赏金规则已停用，请取消并重订")
                            continue
                        events, status = efficient_bounty_events(snapshot, now, sub.rule)
                    else:
                        events, status = aya_events(snapshot, now)
                    self.store.observe(sub.id, events, now)
                    self.store.set_status(sub.id, status)
            except Exception:
                logger.exception("订阅 #%s 世界状态解析失败", sub.id)
                self.store.set_status(sub.id, "数据解析暂不可用")

    def _arbitration_tick(self, subscriptions: list[Subscription], now: datetime) -> None:
        if not self.arbitration:
            return
        for sub in subscriptions:
            if sub.kind != "arbitration":
                continue
            try:
                events, status = arbitration_events(
                    self.arbitration.schedule, self.arbitration.nodes,
                    now, sub.created_at, sub.rule,
                    stats=self.arbitration.stats_for,
                )
                for event in events:
                    self.store.enqueue(
                        sub.id, event.key, event.due_at, event.event_at,
                        event.title, event.detail,
                    )
                self.store.set_status(sub.id, status)
            except Exception:
                logger.exception("仲裁排期匹配失败：订阅 #%s", sub.id)
                self.store.set_status(sub.id, "仲裁排期暂不可用")

    async def _market_tick(self, subscriptions: list[Subscription], now: datetime) -> None:
        """每个 Market 用户每分钟一次；所有自身卖单与同品类在线竞争者比较。"""
        if self.market is not None:
            grouped: dict[str, list[Subscription]] = {}
            for sub in subscriptions:
                if sub.kind == "market_user":
                    grouped.setdefault(sub.rule["user"], []).append(sub)
                elif sub.kind == "market":
                    self.store.set_status(sub.id, "旧版规则已停用，请取消后使用：订阅 wm 用户ID")
            for user, group in grouped.items():
                key = ("user", user)
                if now - self._market_checked.get(
                    key, now - MARKET_INTERVAL
                ) < MARKET_INTERVAL:
                    continue
                self._market_checked[key] = now
                try:
                    profile = await self.market.provider.request(
                        "/user/" + quote(user, safe="")
                    )
                    if not isinstance(profile, dict):
                        raise ValueError("Market 用户数据结构异常")
                    if profile.get("status") != "ingame":
                        for sub in group:
                            self.store.set_status(sub.id, "玩家未处于游戏中，暂停检查")
                        continue
                    orders = await self.market.provider.request(
                        "/orders/user/" + quote(user, safe="")
                    )
                    if not isinstance(orders, list):
                        raise ValueError("Market 用户订单数据结构异常")
                    own = [o for o in orders if isinstance(o, dict) and
                           o.get("type") == "sell" and o.get("visible")]
                    item_ids = {
                        o.get("itemId") for o in own if isinstance(o.get("itemId"), str)
                    }
                    market_orders = {}
                    for item_id in sorted(item_ids):
                        listings = await self.market.provider.request(
                            "/orders/itemId/" + quote(item_id, safe="")
                        )
                        if not isinstance(listings, list):
                            raise ValueError("Market 物品订单数据结构异常")
                        market_orders[item_id] = listings
                    labels = {}
                    try:
                        catalog = await self.market.provider.catalog()
                        labels = {
                            i.id: i.name() for i in catalog.data if i.id in item_ids
                        }
                    except Exception:
                        logger.debug("Market 物品名称映射不可用，使用 ID", exc_info=True)
                    events, status = market_rank_events(
                        own, market_orders, now, labels=labels
                    )
                    for sub in group:
                        self.store.observe_changes(
                            sub.id, events, now, notify_initial=True
                        )
                        self.store.set_status(sub.id, status)
                except Exception:
                    logger.warning("Market 用户排名检查失败：%s", user, exc_info=True)
                    for sub in group:
                        self.store.set_status(sub.id, "Market 用户检查暂不可用")

        if self.riven_market is None:
            return
        rivens: dict[tuple, list[Subscription]] = {}
        for sub in subscriptions:
            if sub.kind != "riven":
                continue
            rule = sub.rule
            key = (
                rule["slug"], tuple(rule["positives"]), rule.get("negative")
            )
            rivens.setdefault(key, []).append(sub)
        for key, group in rivens.items():
            clock = ("riven", *key)
            if now - self._market_checked.get(
                clock, now - RIVEN_INTERVAL
            ) < RIVEN_INTERVAL:
                continue
            self._market_checked[clock] = now
            slug, positives, negative = key
            query = RivenMarketQuery(
                weapon=slug, positives=list(positives), negative=negative
            )
            try:
                snapshot = await self.riven_market.provider.search(slug, query)
                if snapshot.stale:
                    raise ValueError("Market 紫卡搜索为过期缓存")
                for sub in group:
                    events, status = riven_events(snapshot.data, now, sub.rule)
                    self.store.observe(sub.id, events, now)
                    self.store.set_status(sub.id, status)
            except Exception:
                logger.warning("紫卡条件订阅失败：%s", key, exc_info=True)
                for sub in group:
                    self.store.set_status(sub.id, "紫卡市场暂不可用")

    def _notification_card(self, delivery, now: datetime) -> Card:
        subscriptions = self.store.list_for(
            delivery.bot_id, delivery.group_id, delivery.user_id
        )
        statuses = self.store.statuses_for(
            delivery.bot_id, delivery.group_id, delivery.user_id
        )
        others = [
            [f"#{sub.id} {sub.label}", statuses.get(sub.id, "等待检查")]
            for sub in subscriptions if sub.id != delivery.subscription_id
        ]
        card = Card(
            title=delivery.title or "夜灵平野即将进入黑夜",
            source="AAWarframe · 订阅提醒",
            fetched_at=now,
            sections=[
                Section(
                    title="本次触发",
                    columns=["事件", "当前信息"],
                    rows=[[delivery.title or "夜灵平野黑夜",
                           delivery.detail or (
                               "预计北京时间 "
                               f"{delivery.event_at.astimezone(BEIJING):%m-%d %H:%M} "
                               "进入黑夜 · 提前15分钟"
                           )]],
                    highlighted_rows=[0],
                ),
                Section(
                    title=f"你的其他订阅（{len(others)}）",
                    columns=["订阅项目", "当前状态"],
                    rows=others[:9],
                    notes=[] if others else ["当前没有其他订阅。"],
                ),
            ],
        )
        # 一张图片完整展示所有订阅，避免默认卡片自动分页。
        card.page_number = card.total_pages = 1
        return card

    async def _send(self, bot, delivery, now: datetime) -> None:
        card = self._notification_card(delivery, now)
        message = Message([MessageSegment.at(delivery.user_id)])
        if self.renderer is not None:
            try:
                images = await self.renderer.render(card)
                if not images:
                    raise ValueError("卡片渲染结果为空")
                message += MessageSegment.image(images[0])
            except Exception:
                logger.exception("订阅图片生成失败，回退为文本")
                message += MessageSegment.text("\n" + fallback_text(card))
        else:
            # 无浏览器的测试环境；正式运行时 Runtime 注入 CardRenderer。
            message += MessageSegment.text("\n" + fallback_text(card))
        await asyncio.wait_for(
            bot.send_group_msg(group_id=int(delivery.group_id), message=message),
            timeout=20,
        )

    async def _tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        subscriptions = self.store.all_active()
        if not subscriptions:
            return
        self._arbitration_tick(subscriptions, now)
        await self._world_tick(subscriptions, now)
        await self._market_tick(subscriptions, now)
        self.store.expire(now)
        bots = get_bots()
        for delivery in self.store.claim_due(now, set(bots)):
            if not self.store.has_subscription(delivery.subscription_id):
                continue
            bot = bots.get(delivery.bot_id)
            if bot is None:
                self.store.mark_failed(delivery.id, delivery.attempts, now, "bot_disconnected")
                continue
            try:
                await self._send(bot, delivery, now)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "订阅通知发送失败：订阅 %s，尝试 %s",
                    delivery.subscription_id, delivery.attempts, exc_info=True,
                )
                self.store.mark_failed(
                    delivery.id, delivery.attempts, datetime.now(UTC),
                    type(exc).__name__,
                )
            else:
                self.store.mark_sent(delivery.id, datetime.now(UTC))

    async def close(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        self.store.close()
