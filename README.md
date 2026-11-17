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
| `分析`（附图或引用图片） | 识别紫卡词条，比较均值并评级 |
| `帮助` | 查看全部命令名称 |
| `突击` | 查看每日突击任务、特殊条件与刷新时间 |
| `入侵` | 查看当前入侵任务、双方奖励与进度 |
| `执刑官` | 查看每周执刑官任务和源力石类型 |
| `平原` | 查看夜灵平野、福尔图纳、魔胎之境、双衍王境和地球状态 |
| `裂缝` / `钢铁裂缝` / `九重天` | 查看对应类型的虚空裂缝 |
| `赏金` | 地球三个帐篷、圣所与扎里曼第 4、5 项、1999 第 4、5 项和杀毒任务 |
| `地球` | 查看本期赏金任务、等级、声望，以及三个帐篷的任务 |
| `金星` | 查看本期赏金、声望和图内据点任务 |
| `火卫二` | 查看本期赏金、母亲石印和图内据点任务 |
| `金星 1` / `火卫二 1` | 查看指定任务的奖励概率和阶段任务池 |
| `圣所` / `扎里曼` / `1999` | 查看任务、额外目标与固定奖励；1999 含同行角色 |
| `圣所 1` / `扎里曼 1` / `1999 1` | 查看指定任务的完成奖励概率 |
| `地球 1` | 查看第 1 项赏金阶段奖励概率和任务池；其他编号同理 |
| `时光` / `深层` | 查看本周三场任务、偏差、普通与精英风险、个人变量及刷新时间 |
| `氏族` | 本周与下周奖励、积分门槛和双倍区域 |
| `日历` | 1999 本周日历任务与可选奖励 |
| `钢精` | 本周与下周钢铁精华兑换物品及价格 |
| `回廊` | 本周与下周普通回廊战甲、钢铁回廊灵化奖励 |
| `灵化` | 完整灵化武器周轮换表，高亮本周 |
| `电波` | 查看当前每日、每周和精英每周任务、声望与剩余时间 |
| `wk 伯斯顿` | 最多返回 3 条中文维基条目、摘要和可点击链接 |
| `奸商` | 本次虚空商人的单图分组货单与价格 |
| `仲裁` | 当前和下一场仲裁 |
| `今日仲裁` | 北京时间今天的全部仲裁 |
| `仲裁 生存` | 未来 10 场生存仲裁，可替换为其他任务类型 |
| `高效仲裁` | 未来 10 场 S 级仲裁 |
| `wm 膛线` | 查看物品的在线买卖挂单 |
| `wm 满级膛线` | 查看满级物品的在线买卖挂单 |
| `趋势 川流不息p` | 查看 0 级物品近 48 小时、90 天的成交量、均价与趋势图 |
| `趋势 满级川流不息P` | 查看满级物品的成交趋势 |
| `部件 阿利乌双枪p 枪机` | 查询掉落指定部件的所有遗物 |
| `部件 阿利乌双枪p` | 查询整件装备各部件对应的遗物 |
| `遗物 古纪A1` | 查看全部奖励、四档精炼概率和 WM 卖价 |
| `wmr 伯斯顿 基伤多重射速 负任意` | 按武器和词条查找紫卡挂单 |
| `wmr 伯斯顿` | 查看该武器的 0 洗直售订单 |
| `词条` | 查看所有紫卡词条名称和缩写 |
| `zk` / `zk已洗` | 查看未洗 / 已洗紫卡价格排行 |
| `zk 伯斯顿` | 查看指定武器已洗和未洗紫卡的周统计 |
| `数值 伯斯顿` | 列出家族变种及共用的满级紫卡词条上下限，默认 3 正 1 负 |
| `数值 伯斯顿 2+0` | 指定词条组合，支持 2+0、2+1、3+0、3+1 |

WM 展示物品图片、名称和描述，上方为 5 条卖单，下方为 3 条买单，保留 Market 的 Top 排序。支持 `wm 满级川流不息p`、`wm 川流不息p满级`；有等级的物品默认查询 0 级。

趋势按 Warframe.market 已关闭订单记录统计成交量和加权均价。有等级的物品默认查询 0 级，添加“满级”查询满级；没有等级的物品直接输入名称。曲线显示成交均价，柱形显示成交量。

部件查询支持中文、英文、Prime 简写及已有物品别名，入库遗物也会保留并标记。遗物中的售价取 WM 返回的在线卖单最低单价；奖励有多件时展示对应总价。不可交易或没有在线卖单的奖励会单独标注。

命令与参数之间用空格分隔，例如 `zk 伯斯顿`、`数值 伯斯顿`。所有命令均无别名，命令前缀由机器人配置决定，例如 `/平原`。物品名称支持中文、英文及自定义别名；紫卡数值自动采用最接近的匹配，其他查询存在歧义时提示候选。状态卡片使用北京时间（UTC+8）。

紫卡排行默认按中位价降序，每页 10 条，只展示热度不低于 5 的记录。`zk 武器名` 查询周统计，统计结果不做热度筛选。发送 `zk 2` 翻页，发送 `zk 3 热度` 按热度查看第三页，已洗榜用法相同。紫卡数据每日同步，反映官方公布的周交易情况；市场挂单价与实际成交价有所区别。

### QQ 群订阅与图片提醒（测试版）

订阅到点会在原 QQ 群 **@订阅者并发送图片**：醒目展示本次事件、以及该用户在当前群里的其他订阅状态。
沿用现有 Chromium/Playwright 渲染；浏览器不可用时退回纯文本。
按机器人 ID、群号、QQ 用户隔离，单群最多 10 条个人订阅，可用 `我的订阅` 和 `取消订阅 编号` 管理。

```text
订阅 夜灵
订阅 地球平原
订阅 裂缝 生存
订阅 裂缝 虚空 生存 古纪
订阅 钢铁裂缝 塞德娜
订阅 钢铁裂缝 塞德娜 生存 后纪
订阅 九重天
订阅 九重天 生存 古纪
订阅 仲裁
订阅 扎里曼
订阅 圣所
订阅 1999
订阅 阿耶
订阅 wm AliceMarket
订阅 wmr 伯斯顿 伤害 暴击 200
我的订阅
取消订阅 12
```

**触发条件和语义**：

- **夜灵/地球平原**：两条命令等价，每轮夜灵平野进入黑夜前固定 15 分钟提醒，不允许自定义提前量。
- **裂缝/钢铁裂缝/九重天**：分别监控普通裂缝、钢铁裂缝及九重天虚空风暴；三种类型互不混合。可按**地区、任务类型、纪元**任意组合筛选，缺省的维度表示不限。发现匹配的新任务时提醒，首次检查只记录已有任务。
- **仲裁**：无参数，所有**评级为 S 的仲裁**按已知时间表在开场前固定 15 分钟提醒；评级读取内置节点资料和后台自定义覆盖值。
- **扎里曼/圣所**：只关注当前赏金第 4、5 级中的**歼灭**，并排除包含“禁用技能”等限制的任务。
- **1999**：第 5 级或**杀毒赏金**出现歼灭且不禁止技能时提醒；此外关注“捕获传承种”同时要求“找到保险箱”的任务。
- **阿耶**：监控地球平原三个帐篷生成的任务；出现“搜索并救援”或“捕获 Grineer 特工”时提醒。
- **wm 用户ID**：指定 Warframe.market 用户名或其个人主页 slug（不是 QQ 号）。仅当其 Market 在线状态为 **ingame** 时，**每分钟**获取他所有公开卖单，与相同物品、等级/子类等条件下其他在线卖单比较。卖价高于当前最低价时提醒；并列最低视为第一位。持续被压价不会每分钟重复发信，回到最低价后再次被压价才重新提醒。公开 API 不返回他人的隐藏订单；商品排名以可见在线卖单单价比较，可能与网站的部分特殊品类排序不完全一致。
- **wmr 武器 词条 价格上限**：复用紫卡武器与词条解析，筛选 Warframe.market 紫卡拍卖搜索中满足词条要求且**买断价严格小于上限**的新挂单；首次检查只建立基线。无买断价的拍卖不把起拍价当作可直接购买的价格；后台约每 3 分钟轮询一次。

裂缝、定向赏金、阿耶及紫卡都采用持久化首次基线和事件去重，不会在初次订阅时批量推送旧任务/旧挂单。
世界状态每约 15 秒进行一轮扫描，仍受官方 TTL 与网络质量影响；Market 状态检查独立于世界状态。
数据库位于配置项 `aawarframe_cache_dir` 下的 `subscriptions.sqlite3`，重启后保留订阅和状态。
机器人离线、上游失败或状态过期时可能推迟提醒或跳过过期事件。单进程调度，暂不支持多个并行副本。

**升级注意**：旧版 `订阅 仲裁 生存` 会自动转为 S 级全任务仲裁；旧的 `订阅 wm 物品 卖价<=价格` 已停用，需要 `取消订阅 编号` 后重新使用新命令。已创建的普通裂缝订阅会按原类型继续执行。

### 紫卡挂单

`wmr 武器名 [正面词条] [负面条件]`：支持词条全名、缩写或混合输入，可连写或用空格分开。最多指定 3 个正面词条，按价格升序展示前 10 条，保留在线、游戏中和离线卖家。未指定任何词条时，仅查询 0 洗直售订单，按价格升序展示。0 价订单会被剔除；有效样本不少于 5 条时，根据价格分布过滤异常低价，再取前 10 条。

- `wmr 伯斯顿 基伤多重射速`：不限制是否有负面。
- `wmr 伯斯顿 基伤多重射速 负任意`：必须有一个负面。
- `wmr 伯斯顿 基伤多重射速 负变焦`：负面必须为变焦。
- `wmr 伯斯顿 异常状态伤害`：按词条全名查询。
- `wmr 伯斯顿`：查看 0 洗直售订单。

发送 `词条` 查看完整映射；无法识别输入时也会提示查询映射。正负词条共用以下名称和缩写；实际可用词条取决于武器类型。`暴率`也可表示暴击几率，`攻速`也可表示射速／攻击速度。

| 缩写 | 词条 | 缩写 | 词条 |
| --- | --- | --- | --- |
| `额连` | 额外连击获取几率 | `连击` | 连击获取几率 |
| `弹药` | 弹药上限 | `C歧` | 对 Corpus 的伤害 |
| `G歧` | 对 Grineer 的伤害 | `I歧` | 对 Infested 的伤害 |
| `冰冻` | 冰冻伤害 | `连时` | 连击持续时间 |
| `暴击` | 暴击几率 | `滑暴` | 滑行攻击暴击几率 |
| `暴伤` | 暴击伤害 | `基伤` | 伤害 |
| `电击` | 电击伤害 | `火焰` | 火焰伤害 |
| `处决` | 处决伤害 | `射速` | 射速 |
| `弹速` | 弹道飞行速度 | `初连` | 初始连击 |
| `冲击` | 冲击伤害 | `弹匣` | 弹匣容量 |
| `重效` | 重击效率 | `多重` | 多重射击 |
| `毒素` | 毒素伤害 | `穿透` | 穿透 |
| `穿刺` | 穿刺伤害 | `装填` | 装填速度 |
| `范围` | 攻击范围 | `切割` | 切割伤害 |
| `触发` | 触发几率 | `触时` | 触发持续时间 |
| `后坐` | 后坐力 | `变焦` | 变焦 |
| `弹效` | 弹药效率 | `爆炸` | 爆炸伤害 |
| `腐蚀` | 腐蚀伤害 | `O歧` | 对 Orokin 的伤害 |
| `炽歧` | 对炽蛇军的伤害 | `科歧` | 对科腐者的伤害 |
| `毒气` | 毒气伤害 | `重速` | 重击准备速度 |
| `磁力` | 磁力伤害 | `重伤` | 重击伤害 |
| `格挡` | 格挡角度 | `辐射` | 辐射伤害 |
| `收装` | 收起时装填 | `震地` | 震地攻击伤害 |
| `触伤` | 异常状态伤害 | `病毒` | 病毒伤害 |
| `弱伤` | 弱点伤害 | `弱暴` | 弱点暴击几率 |

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

Wiki 查询使用 `wk 关键词`，最多返回 3 条结果，以文本展示标题、摘要和链接。Wiki 查询无需启动浏览器，优先使用 HTTP。API 请求每秒最多一次，跳转同样限速，其余查询排队等待；同一关键词的结果缓存 5 分钟。

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

### 紫卡图片分析

发送 `分析` 并附上一张紫卡图片，或引用图片。可只截武器名称和完整词条。无法确定强化等级时，使用 `分析 满级` 或 `分析 0级` 等。

需额外安装 `pip install "nonebot-plugin-aawarframe[ocr]"`。若 OCR 使用独立 Python 环境，配置 `AAWARFRAME_OCR_PYTHON` 为其 Python 路径。首次启动识别服务会下载模型。


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
