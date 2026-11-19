# 单包跨平台架构 (Issue #27)

- 唯一发行包：`nonebot-plugin-aawarframe`；唯一入口：`nonebot_plugin_aawarframe`。
- `core/nonebot_plugin_aawfcore` 是同一个 wheel 的内部业务包，不单独发布，也不需要部署内部 HTTP 服务。
- 命令通过 NoneBot2 `Bot`、`Event`、`on_message` 路由，保持管理台动态命令名称和 ACL。
- 文本使用 `bot.send`，媒体、引用、@和订阅主动消息保留最小化的适配器专用转换。未安装的适配器不会被导入。
- `pip install nonebot-plugin-aawarframe[qq]` 或 `[onebot]`，混合部署可用 `[qq,onebot]`。
- 原有数据库、消息 ID 作用域和通知确认语义不变；请先备份 `AAWARFRAME_CACHE_DIR`。
- 发布：在 GitHub 推送与 `pyproject.toml` 版本相同的 `vX.Y.Z` 标签，触发单包 OIDC 发布；PyPI Trusted Publisher 环境名称为 `aawarframe`。
- GitHub Actions 构建资源仍需访问上游源站，构建耗时主要由外部数据同步决定。

注意：仅覆盖 QQ 官方和 OneBot V11 的实际协议能力；NoneBot 抽象基类不保证其它适配器的富媒体及主动发送。
