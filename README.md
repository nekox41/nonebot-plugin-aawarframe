<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="./imgs/logo.png" width="180" height="180" alt="aawarframeLogo"></a>
  <br>
  <p><img src="./imgs/logo.svg" width="240" alt="aawarframeLogo"></p>
</div>

<div align="center">

# nonebot-plugin-aawarframe

_✨ Aa 的 Warframe 助手，用于查询游戏状态。 ✨_


<a href="./LICENSE">
    <img src="https://img.shields.io/github/license/nekox41/nonebot-plugin-aawarframe.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-aawarframe">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-aawarframe.svg" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="python">

</div>

## 介绍

用于 NoneBot2 + NapCat / OneBot V11 的国际服 Warframe 查询插件。世界状态直接解析 DE 官方 PC 原始数据，市场仅使用 Warframe.market API v2；图片生成失败时自动回退文本。

## 安装与运行

需要 **Python 3.12**。在已有 NoneBot2 项目中安装：

```bash
nb plugin install nonebot-plugin-aawarframe
# 或
python -m pip install nonebot-plugin-aawarframe
```

使用包管理器安装后，在宿主的 `[tool.nonebot]` 中添加：

```toml
plugins = ["nonebot_plugin_aawarframe"]
```

本仓库不包含独立 Bot 入口；请在已配置 OneBot V11 的宿主中运行。

### Playwright 与中文字体

```bash
PLAYWRIGHT_BROWSERS_PATH=/your/browser/path python -m playwright install --with-deps chromium
```

服务器需安装中文字体，否则卡片可能显示方框。Ubuntu 可执行 `sudo apt-get install -y fonts-noto-cjk fontconfig && fc-cache -f`，然后重启机器人与浏览器。模板优先使用 Linux 字体族名 `Noto Sans CJK SC`。Windows 可使用系统中文字体；在 PowerShell 中用 `$Env:PLAYWRIGHT_BROWSERS_PATH="C:/your/browser/path"` 设置安装路径。

宿主 `.env` 配置示例（将浏览器目录改为实际绝对路径）：

```dotenv
RENDER='{"provider":"playwright","startup":"off","provider_config":{"storage_path":"/your/browser/path","skip_browser_install":true}}'
AAWARFRAME_CACHE_DIR=data/aawarframe
AAWARFRAME_HTTP_TIMEOUT=12
# 可选：仅官方 WorldState 使用的 HTTP/HTTPS 代理；默认直连
# AAWARFRAME_WORLDSTATE_PROXY=http://your-proxy-host:3128
AAWARFRAME_WORLDSTATE_TTL=45
AAWARFRAME_MARKET_TTL=30
AAWARFRAME_RENDER_CONCURRENCY=2
```

`startup=off` 避免启动时探测或安装浏览器；渲染资源未就绪时查询仍可回退文本。模板和 CSS 随包发布，不再启动下载，也无需为模板配置本地资源白名单。静态资源不访问 CDN。

## 命令

按宿主 `COMMAND_START` 配置使用命令前缀（例如 `/裂缝`）。物品名可含空格，所有选项显式校验。

| 命令 | 功能 |
| --- | --- |
| `help` / `wf help` | 帮助卡片 |
| `平原` | 夜灵平野、福尔图娜、魔胎之境、双衍王境、地球的状态与切换时间 |
| `夜灵` | 单独查询夜灵平野昼夜、未来五次黑夜；时间使用 UTC |
| `时光科研` / `时光` | 本周时光科研 |
| `深层科研` / `深层` | 本周深层科研 |
| `裂缝` / `裂隙` | 当前普通裂缝 |
| `钢铁裂缝` / `钢铁裂隙` | 当前钢铁裂缝 |
| `希图斯` | 赏金阶段与奖励概率 |
| `九重天` / `九重天裂缝` | 九重天虚空裂缝（官方 `VoidStorms`） |
| `氏族奖励` | 本周和下周氏族奖励 |
| `紫卡排行` / `紫卡排行2` | 仅未洗，按中位价降序，第 1 / 2 页，每页 10 条 |
| `已洗紫卡排行` / `已洗紫卡排行2` | 仅已洗，按中位价降序，第 1 / 2 页，每页 10 条 |
| `紫卡排行 热度` / `紫卡排行3 热度` | 未洗按热度降序，第 1 / 3 页 |
| `已洗紫卡排行 热度` / `已洗紫卡排行3 热度` | 已洗按热度降序，第 1 / 3 页 |
| `紫卡统计 伯斯顿` | 查询指定武器已洗、未洗的周统计，支持中文和英文名称 |
| `wm 物品名` | 在线买卖挂单，默认展示 0 级（有等级时） |
| `wm 满级物品名` | 满级在线挂单 |
| `wm 物品名 --rank 5` | 指定等级 |
| `wm 物品名 --subtype blueprint` | 指定物品支持的子类型 |
| `仲裁` / `今日仲裁` / `高效仲裁` | 保留入口，返回暂不可用说明 |

市场默认 PC / Crossplay，显示在线状态、等级、库存、每次交易数量和价格，提供最低卖单的私聊指令。**挂单价格不是成交价格**。原 v1 成交统计已停用；v2 成交统计未接入时明确显示不可用。仲裁不再使用本地预测排期，也不调用第三方排期 API。

## 数据与可靠性

- 所有世界状态命令共用 45 秒快照；上游失败时仅允许使用获取后 180 秒以内的旧快照，并标记“过期缓存”。原始快照保存为 `data/aawarframe/worldstate-latest.json`，方便排查字段变化。
- 市场订单缓存 30 秒，故障回退最长到获取后 90 秒；缓存区分物品、等级、子类型、平台和 Crossplay。
- 同键并发合并；市场请求不超过每秒 2 次，429 遵守 `Retry-After`，超长等待直接降级并保留限流冷却时间。
- 物品目录持久化并每小时检测版本，本地目录故障回退最多一天。中文名称优先本地映射与目录名称；模糊搜索使用最小编辑距离，未知标识保留原值。
- 单个模块解析失败不影响其他查询。卡片附来源和 UTC 获取时间，长表格分页，截图并发最多 2。

## 开发

```bash
python -m pip install -e '.[dev]'
ruff check nonebot_plugin_aawarframe tests
ruff format --check nonebot_plugin_aawarframe tests
python -m pytest -q
python -m build
```

目录按职责分层：`commands/` 处理参数与消息；`providers/` 获取原始数据；`worldstate/parsers/` 和 `models/` 校验字段；`localization/` 解析本地名称；`services/` 筛选、排序并生成卡片数据；`rendering/` 是唯一截图入口；`infrastructure/` 管理 HTTP、缓存、限流和持久化。

自动化测试使用 `tests/fixtures/` 中人工构造及官方接口录制的固定样本与 HTTP/渲染替身，不访问实时 API，也不要求 Chromium。改动模板时还应在安装中文字体和 Chromium 的环境验证真实 PNG、分页及文本回退。样本覆盖不能替代实际 QQ / NapCat 联调。

架构约束见 [AGENTS.md](AGENTS.md)。当前所有图片仅使用统一的基础表格模板，主题和视觉样式留待功能完成后设计。接口参考：[Market v2](https://docs.warframe.market/docs/intro/)、[htmlrender 0.8](https://kexue-z.github.io/nonebot-plugin-htmlrender/0.8.1/start/)。

真实 NapCat WebSocket 联调入口、隔离配置及运行方式见 [tests/napcat/README.md](tests/napcat/README.md)。

**Wiki 功能已停用。** 灰机 Wiki 的 Cloudflare / 出口 IP 访问限制使服务器无法稳定获取 API 数据，当前部署环境无法实现可靠的 Wiki 查询。因此不再注册 `wk` / `wiki` 命令，也不再启动 Wiki 浏览器页面；其他查询功能不受影响。


紫卡排行直接获取 [DE 官方 PC 每周紫卡交易数据](https://www-static.warframe.com/repos/weeklyRivensPC.json)，兼容该文件的 JSON5 格式。默认仅展示未洗紫卡，按中位价降序；`已洗紫卡排行` 单独展示已洗紫卡，同样按中位价降序。两种命令均可添加 `热度` 按相对热度降序，例如 `紫卡排行3 热度`、`已洗紫卡排行3 热度`，热度相同时按中位价降序。两份榜单分别分页，仅保留热度 ≥ 5 的记录，武器名后以括号标注已洗/未洗，显示中位价、均价及相对热度（非成交笔数）；缺失中位价的记录不使用均价替代。`紫卡排行` 默认第一页，`紫卡排行2` 或 `紫卡排行 2` 返回第二页；越界或非正整数页码会提示用法。

插件启动后在后台同步，之后每天 UTC 00:00 刷新；本地持久化缓存当天有效，重启不会重复获取。失败时每 15 分钟重试，可明确标注并回退到最近 7 天内的缓存。缓存文件为 `data/aawarframe/weekly-rivens-pc.json`（可由 `AAWARFRAME_CACHE_DIR` 改变目录）。榜单每页固定 10 条，图片按内容与数据获取时间缓存，异常时回退文本。源数据为按周发布的历史实际成交统计，不代表特定属性紫卡的当前报价。


紫卡名称本地化使用随包发布的 Market v2 紫卡武器中英目录（`assets/riven_weapons.json`），优先于普通交易物品别名。未收录名称保留原文。`紫卡统计 伯斯顿`、`紫卡统计 Burston` 可查询指定武器本周的均价、中位价、标准差及相对热度，同时列出全部已洗与未洗记录，不按热度筛选，不受排行的循环状态筛选影响。允许最小编辑距离模糊匹配；匹配不唯一时提示完整名称，不合并不同武器的数据。没有记录时明确提示，不以 0 填充缺失统计。

平原周期在本地计算，不调用第三方解析 API。夜灵平野和魔胎之境使用官方希图斯赏金结束时间；福尔图娜、双衍王境、地球使用固定周期，并在卡片注明推算。周期规则参考 [WFCD 的周期模型](https://github.com/WFCD/warframe-worldstate-parser/tree/master/lib/models)，固定周期可能随游戏更新调整。地球普通任务昼夜与夜灵平野独立。“夜灵平原”旧命令已移除。
