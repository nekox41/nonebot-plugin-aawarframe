# NapCat 实际联调

此目录提供独立的 Python 3.12 / NoneBot2 正向 WebSocket 测试入口；不会修改生产配置。

## 安装

在仓库根目录执行：

```bash
python3.12 -m venv tests/napcat/.venv
tests/napcat/.venv/bin/python -m pip install -e '.[dev]' 'nonebot2[websockets]>=2.5.0'
cp tests/napcat/.env.example tests/napcat/.env
```

在 `.env` 填写 Token、测试 QQ 和测试群号。可选设置 `AAWARFRAME_WORLDSTATE_PROXY`，仅代理官方世界状态，不改变市场或 NapCat 的连接。该文件已被 Git 忽略。浏览器和中文字体的安装方式见仓库 README；`PLAYWRIGHT_BROWSERS_PATH` 必须与实际安装目录相同。

## 运行

```bash
tests/napcat/.venv/bin/python tests/napcat/bot.py
# 连接后额外向指定 QQ 发送两张真实卡片（帮助、满级膛线）：
tests/napcat/.venv/bin/python tests/napcat/bot.py --send-smoke
# 验证官方世界状态获取、渲染与发送：
tests/napcat/.venv/bin/python tests/napcat/bot.py --send-worldstate
```

只响应 `TEST_QQ` 的私聊和 `TEST_GROUP` 的群消息，支持 `wm 满级膛线`、`裂缝` 等已有命令。其他会话会被忽略。按 Ctrl+C 关闭连接和共享资源。

运行事件写入 `runtime/events.jsonl`，只记录连接状态、消息 ID 和发送结果，不记录聊天正文、Token 或图片内容。数据快照和缓存也位于被忽略的 `runtime/`。自动化测试不会启动此入口或连接 NapCat。
