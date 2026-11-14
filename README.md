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
| `突击` | 查看每日突击任务、特殊条件与刷新时间 |
| `入侵` | 查看当前入侵任务、双方奖励与进度 |
| `执刑官` | 查看每周执刑官任务和源力石类型 |
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
| `wk 伯斯顿` / `wiki 伯斯顿` | 最多返回 3 条中文维基条目、摘要和可点击链接 |
| `奸商` | 本次虚空商人的单图分组货单与价格 |
| `仲裁` | 当前和下一场仲裁 |
| `今日仲裁` | 北京时间今天的全部仲裁 |
| `仲裁生存` | 未来 10 场生存仲裁，可替换为其他任务类型 |
| `高效仲裁` | 未来 10 场 S 级仲裁 |
| `wm 膛线` | 查看物品的在线买卖挂单 |
| `wm 满级膛线` | 查看满级物品的在线买卖挂单 |
| `紫卡排行` / `已洗紫卡排行` | 查看未洗 / 已洗紫卡价格排行 |
| `紫卡统计 伯斯顿` | 查看指定武器已洗和未洗紫卡的周统计 |
| `紫卡数值 伯斯顿` | 查看武器全部变体的满级紫卡词条上下限，默认 3 正 1 负 |
| `紫卡数值 伯斯顿 2+0` | 指定词条组合，支持 2+0、2+1、3+0、3+1 |

WM 展示物品图片、名称和描述，上方为 5 条卖单，下方为 3 条买单，保留 Market 的 Top 排序。支持 `wm 满级川流不息p`、`wm 川流不息p满级`；有等级的物品默认查询 0 级。

命令前缀由机器人配置决定，例如 `/平原`。市场和紫卡查询支持统一的中文、英文及自定义别名；名称有歧义时会提示候选。状态卡片使用北京时间（UTC+8）。

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

保存后重启机器人。卡片主题通过 `AAWARFRAME_THEME` 选择，默认为 `default`。

### 网页管理台

管理台通过左侧导航切换别名管理和仲裁管理。别名管理支持选择物品并添加常用称呼；仲裁管理支持搜索节点、修改评级和每分钟生息精华掉落量，保存后立即生效。

在 `.env.prod` 中启用：

```dotenv
AAWARFRAME_ADMIN_ENABLED=true
AAWARFRAME_ADMIN_HOST=0.0.0.0
AAWARFRAME_ADMIN_PORT=8443
AAWARFRAME_ADMIN_PUBLIC_HOST=你的服务器IP或域名
```

重启后访问 `https://服务器IP:8443`。首次启动会生成登录口令，默认保存在机器人目录下的 `data/aawarframe/admin/password`，仅服务器用户可读。可通过 `AAWARFRAME_ADMIN_PASSWORD` 指定至少 16 位的口令，修改口令后需重启。

未配置证书时，管理台会生成自签名证书，首次访问需在浏览器中确认。已有域名证书时，用 `AAWARFRAME_ADMIN_CERT` 和 `AAWARFRAME_ADMIN_KEY` 指定证书与私钥路径。远程访问需要在服务器防火墙和云安全组中放行管理端口。

- **添加别名**：输入“毒妈”，搜索并选择 Saryn，点击添加。之后可使用 `wk 毒妈`；`wm 毒妈` 会匹配对应的 Saryn Prime 套装。
- **删除别名**：在已有别名列表中点击删除，并确认对应物品。
- **仲裁记录**：仅列出会参与仲裁的节点。评级来自 browse.wf，掉落量初始为 0，可自行记录；人工修改不随资源更新而重置。
- **数据备份**：物品目录和人工别名保存在 `data/aawarframe/registry.sqlite3`。升级前会自动创建数据库备份。

星图节点、任务类型、派系、描述、任务池和奖励表使用 JSON 维护。自定义文件放在 `data/aawarframe/mappings/`，重启后生效；仲裁评级和掉落记录由后台单独保存。

### 数据初始化与离线安装

首次启动会自动获取最新物品、市场、紫卡、奖励表、节点和仲裁排期，并进行预处理。联网失败时自动解压随插件附带的离线包，包含已处理资源、物品数据库、别名和人工映射；已有数据库和人工记录不会被覆盖。口令、白名单及服务器配置不在资源包内。

后续启动每天最多检查更新一次。可设置 `AAWARFRAME_DATA_AUTO_UPDATE=false` 仅使用本地数据。资源版本在完整校验后切换，更新失败时继续使用上一个版本。

在源码目录可以手动更新、导出或恢复资源：

```bash
python scripts/initialize_data.py --refresh --data-dir data/aawarframe
python scripts/initialize_data.py --export warframe-data.tar.gz --data-dir data/aawarframe
python scripts/initialize_data.py --restore warframe-data.tar.gz --data-dir data/aawarframe
```

仲裁排期以 `Unix秒时间戳,节点ID` 保存。显示时间统一为北京时间；不在排期中的节点，仲裁属性为 `null`。

## 计划清单

- [x] 平原周期、夜灵昼夜与虚空裂缝
- [x] 地球赏金、科研任务与氏族奖励
- [x] 市场物品搜索与在线买卖挂单
- [x] 紫卡中文名称、价格 / 热度排行与单武器统计
- [x] 武器全变体的紫卡词条数值与组合修正
- [x] 每日突击、入侵与每周执刑官猎杀
- [x] 统一物品目录、交易标记与别名管理
- [x] 带登录口令的网页管理台
- [x] 虚空商人单图分组货单
- [ ] 市场成交统计
- [x] 仲裁当前任务、今日排期、类型筛选与 S 级排期
- [ ] 完善卡片样式与排版

Wiki 查询支持 `wk 关键词` 和 `wiki 关键词`，最多返回 3 条结果，以文本展示标题、摘要和链接。Wiki 查询无需启动浏览器，优先使用 HTTP。API 请求每秒最多一次，跳转同样限速，其余查询排队等待；同一关键词的结果缓存 5 分钟。

## 设计架构

命令负责接收查询，业务模块整理数据，渲染模块生成图片。各部分分开维护，方便后续增加功能和调整卡片。

```text
nonebot_plugin_aawarframe/
├── commands/       # 命令与参数
├── services/       # 查询、筛选与排序
├── providers/      # 获取接口数据
├── worldstate/     # 解析游戏状态与计算周期
├── models/         # 数据结构
├── initialization/ # 联网预处理、离线恢复与数据包导出
├── grq/            # 统一物品目录、别名和 JSON 映射
├── localization/   # 现有业务的兼容入口
├── admin/          # 别名管理页面与登录认证
├── rendering/      # HTML 模板、样式与图片生成
└── infrastructure/ # 网络请求、缓存与本地存储
```

GRQ（Game Resource Query）使用一个统一的物品目录。游戏物品资料和 Market 商品按内部标识合并，可交易物品带有交易标记、市场编号和商品名称。`wk` 搜索全部物品；`wm` 只在当前市场目录中带交易标记的物品里匹配。基础物品可匹配对应的可交易版本，但不会误选蓝图或部件。

物品资料和人工别名保存在 SQLite，查询使用内存索引。别名只添加一次，供 Wiki、市场和紫卡查询共同使用。紫卡兼容关系、武器类型和其他固定映射由 JSON 提供。

| 数据 | 维护位置 |
| --- | --- |
| 游戏物品、交易标记、人工别名 | `registry.sqlite3` |
| 星图节点及仲裁初始属性 | `ExportRegions_zh.json` |
| 任务类型、派系、描述 | `descriptions.json` |
| 赏金任务池与据点 | `bounties.json` |
| 原始奖励表 | `rewards.json` |
| 仲裁时间表 | `arbitrations.csv.gz` |
| 紫卡兼容和官方掉落表快照 | `grq/riven.json.gz`、`grq/droptables.json.gz` |

预处理资源保存在数据目录的 `resources/versions/` 中，`resources/current.json` 指向当前版本。手工映射放在独立的 `mappings/` 目录，避免更新时被覆盖。仲裁后台记录保存在 `mappings/arbitration_overrides.json`。

外部数据的下载和预处理统一位于 `initialization/`，开发时也使用同一套流程。

游戏状态和紫卡周统计来自 DE 官方接口，市场数据来自 Warframe.market。图片使用 Jinja2 模板，由 htmlrender 和 Playwright 生成。

开发约定见 [AGENTS.md](./AGENTS.md)，本地 QQ 联调说明见 [tests/napcat/README.md](./tests/napcat/README.md)。

## 鸣谢

- [Digital Extremes](https://www.warframe.com/)：Warframe 与公开游戏数据。
- [NoneBot2](https://github.com/nonebot/nonebot2) 与 [NapCat](https://github.com/NapNeko/NapCatQQ)：机器人框架与 QQ 接入。
- [Warframe.market](https://warframe.market/)：市场接口与物品名称目录。
- [nonebot-plugin-htmlrender](https://github.com/kexue-z/nonebot-plugin-htmlrender) 与 [Playwright](https://github.com/microsoft/playwright)：图片生成工具。
- [WFCD](https://github.com/WFCD/warframe-items)：完整物品与多语言资料；[worldstate-parser](https://github.com/WFCD/warframe-worldstate-parser) 提供世界状态解析参考。
- [warframe-drop-data](https://github.com/WFCD/warframe-drop-data)：整理 DE 官方掉落表。
- [Warframe Wiki](https://wiki.warframe.com/w/Riven_Mods)：紫卡词条、计算公式与可用条件（[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)）。

三大平原赏金任务池整理：[Aameow《Warframe 三大平原赏金任务链》](https://www.bilibili.com/opus/1243452642045198337)。

赏金轮换、图内据点计算及任务配置参考：[wf.browse.oracle](https://github.com/calamity-inc/wf.browse.oracle)。
赏金奖励表及中文名称：[warframe-public-export-plus](https://github.com/calamity-inc/warframe-public-export-plus)。

仲裁排期与评级：[browse.wf](https://browse.wf/arbys)，评级资料由 Arbitration Goons 整理。
