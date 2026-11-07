# nonebot-plugin-warframe · 核心架构规范（精简版 v1.1）

> 用途：供后续设计、编码和 AI 协作快速读取。优先遵守本文件；视觉细节以 `design.md` 为准。本文只记录已确定的方向与必须遵循的约束。

## 1. 项目定位

- **运行环境**：NoneBot2 + NapCat（OneBot V11），Python 异步插件。
- **交互协议**：严格命令式，不做自然语言自动触发。
- **支持范围**：仅 Warframe **国际服**；世界状态以 PC 为目标，市场默认 PC / Crossplay。
- **输出形式**：图片卡片优先；失败时回退简明文本。
- **渲染方式**：`nonebot-plugin-htmlrender>=0.8.0` + Playwright（Chromium），HTML/CSS + Jinja2 模板生成 PNG；**不使用 Pillow 绘制卡片**。
- **核心原则**：模块化单体、异步 I/O、数据解析与业务逻辑及渲染分离。

## 2. 数据来源及边界

| 数据 | 来源 | 约束 |
| --- | --- | --- |
| 世界状态 | `https://api.warframe.com/cdn/worldState.php` | **自己解析官方原始数据**，不使用 WFCD/warframestat.us 等第三方解析 API |
| 交易市场 | `https://api.warframe.market/v2/` | 直接使用 Warframe.market API v2；属于市场数据源，不是 DE 官方接口 |
| 本地化 | 本地映射表 + Market 物品目录中的可用名称 | 支持中文别名与模糊搜索；未知项不得猜测 |

- 官方 WorldState 原始字段可能变化：保留原始快照、独立校验各解析器、记录异常；一个解析器失败不得影响其他模块。
- 区分“无数据”“解析失败”“过期缓存”；数据模型携带来源与 UTC 时间。
- `/仲裁` **暂不承诺 V1 可用**，需先核实官方原始数据能否独立支撑；不允许暗中调用第三方排期 API。
- Market 接口必须集中管理 `User-Agent`、语言、平台、Crossplay、限流与请求重试。

## 3. 分层与调用约束

```text
QQ / NapCat / NoneBot2
  └─ Command（命令解析、参数校验、消息发送）
       └─ Service（业务筛选、排序、聚合）
            ├─ Provider（官方 WorldState / Market v2 HTTP）
            ├─ Parser（原始数据 → 统一领域模型）
            └─ Resolver（中文名、节点、任务类型映射）
       └─ ViewModel → Jinja2 Template → htmlrender → PNG → QQ

基础设施：共享 httpx.AsyncClient / TTL Cache / Singleflight / 限流 / 日志
```

**硬性边界**：Command 不直接访问 HTTP 或处理原始 JSON；Service 不调用 QQ 或 Playwright；Renderer 不访问外部 API。所有 HTML 输入必须转义，不拼接用户提供的代码。

## 4. 目录约定

```text
nonebot_plugin_warframe/
├─ __init__.py, config.py, bootstrap.py
├─ commands/                 # /wf 路由、参数解析
├─ services/                 # 世界状态、市场、物品检索
├─ providers/                # 官方 WorldState、Market v2
├─ worldstate/parsers/       # 裂缝、商人、入侵、突击、周期等
├─ models/                   # 统一 Pydantic 数据模型
├─ localization/             # 节点、名称、别名映射
├─ rendering/
│  ├─ renderer.py             # 唯一 htmlrender 调用入口
│  ├─ viewmodels.py
│  ├─ templates/              # base + 各业务卡片 Jinja2
│  └─ assets/css/             # tokens、base、components、cards
├─ infrastructure/           # HTTP、缓存、限流、持久化
└─ tests/                    # 固定 API 样本 + 解析/渲染测试
```

## 5. 命令规划

| 命令 | 功能 |
| --- | --- |
| `help` | 帮助卡片 |
| `平原` | 各大平原状态 |
| `裂缝` | 裂缝列表 |
| `钢铁裂缝` | 钢铁裂缝列表 |
| `九重天裂缝` | 九重天裂缝列表 |
| `奸商` | 虚空商人 |
| `入侵` | 当前入侵 |
| `仲裁` | 当前仲裁任务 |
| `wm 物品名` | 在线此物品的买卖售价，与销售数据统计 |
| `wm 满级物品名` | 在线此物品的满级买卖售价，与销售数据统计 |

- 选项必须显式校验；物品名称允许空格；模糊匹配时匹配距离最近的。
- 市场价格必须明确：买/卖单、在线状态、等级、数量/单位、数据获取时间；**挂单价不等于成交价**。

## 6. 缓存与可靠性

- 共用一次 WorldState 快照供各世界状态命令查询；建议 **45 秒 TTL**，过期最多 **3 分钟兜底**并显著标记。
- Market 订单按物品、等级、子类型、平台、Crossplay 建缓存键；建议 **30 秒 TTL**，最多 **90 秒过期兜底**。
- 目录持久化并按版本检测更新；相同缓存键的并发请求通过 **Singleflight 合并**。
- Market 以 **每秒最多 2 次**作为初始客户端速率上限（低于服务端公开的常规限制）；遇 429 退避，遵守服务端限制及适用规则。
- 浏览器渲染并发初始不超过 **2**；图片缓存与数据版本/模板版本绑定，避免重复截图。
- 所有外部服务故障应被隔离；启动不应被一次网络失败阻断。

## 7. 开发与验收顺序

1. **M1 渲染链路**：插件加载、`help` 帮助卡片、HTML 模板及 Playwright 图片发送。
2. **M2 官方数据解析**：WorldState 获取、原始快照存储、字段校验、独立解析器。
3. **M3 世界状态**：裂缝、商人、入侵、平原周期、总览卡片。
4. **M4 交易市场**：Market v2、目录同步、名称解析、价格/搜索卡片。
5. **M5 稳定性**：缓存、限流、并发合并、异常降级、自动化回归测试。

**V1 验收**：中文卡片无溢出；同键并发只请求上游一次；异常模块隔离；数据过期可辨；接口 429/超时可控；插件可安全启动与关闭。

**暂不做**：订阅推送、WebSocket、历史趋势、Riven 高级分析、Web 后台、国服支持、自动交易。
