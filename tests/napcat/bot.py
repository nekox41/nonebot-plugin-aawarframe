# 作用：提供 bot 测试与联调支持。
# 编写日期：2026-11-07
# 作者：Aameow

"""仅供指定私聊和测试群使用的真实 NapCat 联调入口。"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import nonebot
from dotenv import dotenv_values
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, MessageEvent
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor

HERE = Path(__file__).resolve().parent


def record(event: str, **details) -> None:
    entry = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **details}
    line = json.dumps(entry, ensure_ascii=False)
    print(line, flush=True)
    with (HERE / "runtime" / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send-smoke", action="store_true", help="连接后向测试 QQ 发送帮助和市场卡片一次"
    )
    parser.add_argument(
        "--send-worldstate", action="store_true", help="连接后向测试 QQ 发送真实平原卡片一次"
    )
    args = parser.parse_args()
    settings = {**dotenv_values(HERE / ".env"), **os.environ}
    token = settings.get("NAPCAT_TOKEN")
    if not token:
        parser.error("请在 tests/napcat/.env 设置 NAPCAT_TOKEN")
    user_id = int(settings.get("TEST_QQ", "10000"))
    group_id = int(settings.get("TEST_GROUP", "10000"))
    if settings.get("FONTCONFIG_FILE"):
        os.environ.setdefault("FONTCONFIG_FILE", settings["FONTCONFIG_FILE"])
    runtime_dir = HERE / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    nonebot.init(
        driver="~websockets",
        log_level="WARNING",
        command_start={"/", ""},
        onebot_v11_ws_urls={settings.get("NAPCAT_WS_URL", "ws://127.0.0.1:8088/")},
        onebot_v11_access_token=token,
        api_timeout=40,
        aawarframe_cache_dir=runtime_dir / "data",
        aawarframe_worldstate_proxy=settings.get("AAWARFRAME_WORLDSTATE_PROXY") or None,
        localstore_cache_dir=runtime_dir / "cache",
        localstore_config_dir=runtime_dir / "config",
        localstore_data_dir=runtime_dir / "localstore",
        render={
            "provider": "playwright",
            "startup": "off",
            "provider_config": {
                "storage_path": settings.get(
                    "PLAYWRIGHT_BROWSERS_PATH", "/tmp/aawarframe-browsers"
                ),
                "skip_browser_install": True,
            },
        },
    )
    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)

    @event_preprocessor
    async def restrict_test_scope(event: Event):
        if not isinstance(event, MessageEvent):
            raise IgnoredException("仅处理联调消息")
        if isinstance(event, GroupMessageEvent):
            allowed = event.group_id == group_id
        else:
            allowed = event.user_id == user_id
        if not allowed:
            raise IgnoredException("不属于允许的联调会话")
        record(
            "received",
            message_id=event.message_id,
            scope="group" if isinstance(event, GroupMessageEvent) else "private",
        )

    # 让 NoneBot 的模块查找器直接发现源码，而非通过可编辑安装的后置查找器。
    sys.path.insert(0, str(HERE.parents[1]))
    if nonebot.load_plugin("nonebot_plugin_aawarframe") is None:
        raise RuntimeError("无法加载待测试插件")
    from nonebot_plugin_aawarframe.commands.router import dispatch

    sent_smoke = False

    @driver.on_bot_connect
    async def connected(bot: Bot):
        nonlocal sent_smoke
        record("connected", bot_id=bot.self_id)
        if not (args.send_smoke or args.send_worldstate) or sent_smoke:
            return
        sent_smoke = True
        queries = [("help", ""), ("market", "满级 膛线")] if args.send_smoke else []
        if args.send_worldstate:
            queries.append(("cetus", ""))
        for feature, arguments in queries:
            try:
                message = await dispatch(feature, arguments)
                result = await bot.send_private_msg(user_id=user_id, message=message)
                record(
                    "smoke_sent",
                    feature=feature,
                    image_count=len(message["image"]),
                    message_id=result.get("message_id"),
                )
            except Exception as exc:
                # 不输出请求数据，避免日志包含令牌或图片 base64。
                record("smoke_failed", feature=feature, error_type=type(exc).__name__)

    @driver.on_bot_disconnect
    async def disconnected(bot: Bot):
        record("disconnected", bot_id=bot.self_id)

    @Bot.on_called_api
    async def called_api(bot: Bot, exception: Exception | None, api: str, data: dict, result):
        if api not in {"send_msg", "send_private_msg", "send_group_msg"}:
            return
        record(
            "send_result",
            api=api,
            ok=exception is None,
            message_id=result.get("message_id") if isinstance(result, dict) else None,
            error_type=type(exception).__name__ if exception else None,
        )

    record("starting", private_user=user_id, test_group=group_id)
    nonebot.run()


if __name__ == "__main__":
    main()
