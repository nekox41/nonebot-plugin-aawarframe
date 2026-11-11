<div align="center">
  <img src="./imgs/logo.png" width="160" alt="Aa 的 Warframe 助手">

# nonebot-plugin-aawarframe

Aa 的 Warframe 助手，把游戏查询带到 QQ。

[![PyPI](https://img.shields.io/pypi/v/nonebot-plugin-aawarframe.svg)](https://pypi.org/project/nonebot-plugin-aawarframe/)
![Python 3.12](https://img.shields.io/badge/Python-3.12-blue)
[![License](https://img.shields.io/github/license/nekox41/nonebot-plugin-aawarframe.svg)](./LICENSE)

</div>

## 介绍

基于 NoneBot2 的 Warframe 国际服查询插件，支持通过 NapCat 等 OneBot V11 实现在 QQ 中查询游戏状态、市场价格和紫卡周统计，以 WebP 图片卡片展示结果。

希望让玩家在聊天时就能方便地查看任务、安排活动、了解价格。目前以 PC 为主，市场默认查询 PC / 跨平台交易。

### 常用命令

| 命令 | 用途 |
| --- | --- |
| `help` (`wf帮助`) | 默认查看第 1 页；发送 `help 2` 换页 |
| `平原` | 查看夜灵平野、福尔图纳、魔胎之境、双衍王境和地球状态 |
| `裂缝` / `钢铁裂缝` / `九重天` | 查看对应类型的虚空裂缝 |
| `赏金` | 地球三个帐篷、圣所与扎里曼第 4、5 项、1999 第 4、5 项和杀毒任务 |
| `地球赏金` (`地球`) | 查看本期赏金任务、等级、声望，以及三个帐篷的任务 |
| `金星赏金` (`金星`) | 查看本期赏金、声望和图内据点任务 |
| `火卫二赏金` (`火卫二`) | 查看本期赏金、母亲石印和图内据点任务 |
| `金星赏金1` / `火卫二赏金1` | 查看指定任务的奖励概率和阶段任务池 |
| `圣所赏金` / `扎里曼赏金` / `1999赏金` | 查看任务、额外目标与固定奖励；1999 含同行角色 |
| `圣所赏金1` / `扎里曼赏金1` / `1999赏金1` | 查看指定任务的完成奖励概率 |
| `地球赏金1` | 查看第 1 项赏金阶段奖励概率和任务池；其他编号同理 |
| `时光科研` (`时光`) / `深层科研` (`深层`) | 查看本周三场任务、偏差、普通与精英风险、个人变量及刷新时间 |
| `氏族` (`氏族奖励`) | 本周与下周奖励、积分门槛和双倍区域 |
| `日历` | 1999 本周日历任务与可选奖励 |
| `钢精` | 本周与下周钢铁精华兑换物品及价格 |
| `回廊` | 本周与下周普通回廊战甲、钢铁回廊灵化奖励 |
| `灵化` | 完整灵化武器周轮换表，高亮本周 |
| `午夜电波` (`电波`) | 查看当前每日、每周和精英每周任务、声望与剩余时间 |
| `wm 膛线` | 查看物品的在线买卖挂单 |
| `wm 满级膛线` | 查看满级物品的在线买卖挂单 |
| `紫卡排行` / `已洗紫卡排行` | 查看未洗 / 已洗紫卡价格排行 |
| `紫卡统计 伯斯顿` | 查看指定武器已洗和未洗紫卡的周统计 |

命令前缀由机器人配置决定，例如 `/平原`。市场查询支持中文、英文及带空格的物品名；状态卡片使用北京时间（UTC+8）。

紫卡排行默认按中位价降序，每页 10 条，只展示热度不低于 5 的记录。发送 `紫卡排行2` 翻页，发送 `紫卡排行3 热度` 按热度查看第三页，已洗榜用法相同。`紫卡统计` 不做热度筛选。紫卡数据每日同步，反映官方公布的周交易情况；市场挂单价与实际成交价有所区别。

## 安装

需要 **Python 3.12**，以及已连接 OneBot V11 的 NoneBot2 机器人。

在机器人目录安装插件：

```bash
nb plugin install nonebot-plugin-aawarframe
```

也可以使用 pip：

```bash
python -m pip install nonebot-plugin-aawarframe
```

使用 pip 安装时，在机器人 `pyproject.toml` 的插件列表中加入：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_aawarframe"]
```

已有其他插件时，将本插件追加到列表中。

### 安装浏览器和中文字体

图片生成需要 Chromium。以下为 Linux 安装示例，将浏览器目录替换为自己的绝对路径：

```bash
PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers python -m playwright install --with-deps chromium
```

Ubuntu / Debian 安装中文字体：

```bash
sudo apt-get install -y fonts-noto-cjk fontconfig
fc-cache -f
```

## 配置

在机器人的 `.env` 或 `.env.prod` 中配置浏览器，目录需与安装时一致：

```dotenv
RENDER='{"provider":"playwright","startup":"off","provider_config":{"storage_path":"/path/to/browsers","skip_browser_install":true}}'
```

其余配置均有默认值，按需添加即可：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `AAWARFRAME_CACHE_DIR` | `data/aawarframe` | 数据保存目录 |
| `AAWARFRAME_HTTP_TIMEOUT` | `12` | 请求超时，单位为秒 |
| `AAWARFRAME_WORLDSTATE_TTL` | `45` | 游戏状态刷新间隔，单位为秒 |
| `AAWARFRAME_MARKET_TTL` | `30` | 市场挂单刷新间隔，单位为秒 |
| `AAWARFRAME_RENDER_CONCURRENCY` | `2` | 同时生成图片的数量，可设为 1 或 2 |
| `AAWARFRAME_WORLDSTATE_PROXY` | 不使用 | 游戏状态接口的 HTTP / HTTPS 代理地址 |

保存后重启机器人，发送 `help` 查看命令。

## 计划清单

- [x] 平原周期、夜灵昼夜与虚空裂缝
- [x] 地球赏金、科研任务与氏族奖励
- [x] 市场物品搜索与在线买卖挂单
- [x] 紫卡中文名称、价格 / 热度排行与单武器统计
- [ ] 虚空商人、入侵与突击查询
- [ ] 市场成交统计
- [ ] 仲裁查询，待确认可用的数据来源
- [ ] 完善卡片样式与排版

**Wiki 功能已停用。** 受灰机 Wiki 的 Cloudflare 和出口 IP 访问限制，目前无法实现稳定查询，`wk` / `wiki` 命令不可用。

## 设计架构

命令负责接收查询，业务模块整理数据，渲染模块生成图片。各部分分开维护，方便后续增加功能和调整卡片。

```text
nonebot_plugin_aawarframe/
├── commands/       # 命令与参数
├── services/       # 查询、筛选与排序
├── providers/      # 获取接口数据
├── worldstate/     # 解析游戏状态与计算周期
├── models/         # 数据结构
├── localization/   # 中文名称与别名
├── rendering/      # HTML 模板、样式与图片生成
└── infrastructure/ # 网络请求、缓存与本地存储
```

游戏状态和紫卡周统计来自 DE 官方接口，市场数据来自 Warframe.market。图片使用 Jinja2 模板，由 htmlrender 和 Playwright 生成。

开发约定见 [AGENTS.md](./AGENTS.md)，本地 QQ 联调说明见 [tests/napcat/README.md](./tests/napcat/README.md)。

## 鸣谢

- [Digital Extremes](https://www.warframe.com/)：Warframe 与公开游戏数据。
- [NoneBot2](https://github.com/nonebot/nonebot2) 与 [NapCat](https://github.com/NapNeko/NapCatQQ)：机器人框架与 QQ 接入。
- [Warframe.market](https://warframe.market/)：市场接口与物品名称目录。
- [nonebot-plugin-htmlrender](https://github.com/kexue-z/nonebot-plugin-htmlrender) 与 [Playwright](https://github.com/microsoft/playwright)：图片生成工具。
- [WFCD](https://github.com/WFCD/warframe-worldstate-parser)：周期计算方式的参考实现。

三大平原赏金任务池整理：[Aameow《Warframe 三大平原赏金任务链》](https://www.bilibili.com/opus/1243452642045198337)。

赏金轮换、图内据点计算及任务配置参考：[wf.browse.oracle](https://github.com/calamity-inc/wf.browse.oracle)。
赏金奖励表及中文名称：[warframe-public-export-plus](https://github.com/calamity-inc/warframe-public-export-plus)。
