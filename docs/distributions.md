# AAWarframe 单仓库、多发行包

核心项目 `nonebot-plugin-aawarframe` 安装在 `nonebot_plugin_aawarframe`，不依赖任何特定协议适配器。业务逻辑、初始化、图片渲染、缓存和 SQLite 数据都只维护一份，默认写在 `data/aawarframe/`。

| 安装发行包 | NoneBot 插件入口 | 额外依赖 |
| --- | --- | --- |
| `nonebot-plugin-aawfqq` | `nonebot_plugin_aawfqq` | `nonebot-adapter-qq` |
| `nonebot-plugin-aawfonebot` | `nonebot_plugin_aawfonebot` | `nonebot-adapter-onebot` |

两个入口都通过 `nonebot.require("nonebot_plugin_aawarframe")` 加载同一核心，不复制缓存/数据，也不会各启动一份调度器。不需要同时安装两个入口。未来 OOPZ 可新增 `distributions/oopz/`，不应以空壳发布。

在仓库中分别执行 `python -m build distributions/qq` 和 `python -m build distributions/onebot` 可生成独立 wheel/sdist，版本号分别来自其子目录 `pyproject.toml`。发布工作流使用独立的 Git 标签：

- `qq-v0.1.0`：构建 `nonebot-plugin-aawfqq`，创建独立 GitHub Draft Release，并使用 `PYPI_API_TOKEN_QQ` 发布该发行包。
- `onebot-v0.1.0`：构建 `nonebot-plugin-aawfonebot`，创建独立 GitHub Draft Release，并使用 `PYPI_API_TOKEN_ONEBOT` 发布该发行包。
- 核心包保留 `v*` / `core-v*` 标签及原 `PYPI_API_TOKEN` 发布方式，不会被平台包的标签触发。

配置好两个独立 PyPI 项目及 GitHub secrets 后再创建正式标签；否则工作流不应作为生产发布入口。在 GitHub Actions 上手动执行 `Publish Protocol Packages` 可以**只构建**选定的发行包，不会上传 PyPI。

源码直装的测试方式：先安装核心 `pip install -e .`，再在对应子目录执行 `pip install distributions/qq` 或 `pip install distributions/onebot`。若两个入口都安装，核心的 NoneBot 插件只初始化一次，但需要在 NoneBot 注册所需协议适配器。

**重要**：发行包依赖不会自动改变用户自己写的 `bot.py`。如果 `bot.py` 硬导入未安装的 `nonebot.adapters.onebot.v11`，请删除该导入与对应 `register_adapter`，QQ-only 环境只能注册 `nonebot.adapters.qq`。
