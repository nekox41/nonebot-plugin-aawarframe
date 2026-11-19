# AAWarframe 单仓库、多发行包

核心项目 `nonebot-plugin-aawarframe` 安装在 `nonebot_plugin_aawarframe`，不依赖任何特定协议适配器。业务逻辑、初始化、图片渲染、缓存和 SQLite 数据都只维护一份，默认写在 `data/aawarframe/`。

| 安装发行包 | NoneBot 插件入口 | 额外依赖 |
| --- | --- | --- |
| `nonebot-plugin-aawfqq` | `nonebot_plugin_aawfqq` | `nonebot-adapter-qq` |
| `nonebot-plugin-aawfonebot` | `nonebot_plugin_aawfonebot` | `nonebot-adapter-onebot` |

两个入口都通过 `nonebot.require("nonebot_plugin_aawarframe")` 加载同一核心，不复制缓存/数据，也不会各启动一份调度器。不需要同时安装两个入口。未来 OOPZ 可新增 `distributions/oopz/`，不应以空壳发布。

在仓库中分别执行 `python -m build distributions/qq` 和 `python -m build distributions/onebot` 可以生成独立 wheel/sdist，版本号可各自管理；正式发布前还需配置两项独立 PyPI Trusted Publishing 记录和发布授权。

源码直装的测试方式：先安装核心 `pip install -e .`，再在对应子目录执行 `pip install -e distributions/qq` 或 `pip install -e distributions/onebot`。若两个入口都安装，核心的 NoneBot 插件只初始化一次，但需要在 NoneBot 注册所需协议适配器。

**重要**：发行包依赖不会自动改变用户自己写的 `bot.py`。如果 `bot.py` 硬导入未安装的 `nonebot.adapters.onebot.v11`，请删除该导入与对应 `register_adapter`，QQ-only 环境只能注册 `nonebot.adapters.qq`。
