我认为这次的 **GRQ（Game Resource Query）系统**设计方向已经比较合理了，而且比之前的统一实体图谱更加简单、稳定，也更容易扩展。

我们不再试图让解析器理解 Warframe 中所有物品之间的关系，而是建立一个**按资源域组织、统一提供查询能力的游戏资源管理系统**。

最关键的设计理念是：

**域负责定义资源范围，GRQ 负责统一检索、翻译、别名、缓存与更新，业务模块只需要指定目标域。**

# **一、GRQ 总体架构**

**NoneBot2 业务功能**

wm / wk / 紫卡统计 / 裂缝 / 仲裁 / 其他功能

**GRQ · Game Resource Query**

统一资源检索与管理接口

精确标识检索

多语言名称搜索

自定义别名管理

模糊匹配与歧义检测

资源加载与更新

内存索引与缓存

Items

游戏物品目录

WarframeMarket

可交易商品目录

Node

星图节点

Desc

描述文本

MissionType

任务类型

Faction

敌对派系

各域独立数据集 · 统一持久化 · 统一索引

这样新增一个功能，不需要重新实现名称解析器，只需要声明：

```
# wk：游戏物品查询grq.search("Items", "伯斯顿")# wm：市场商品查询grq.search("WarframeMarket", "空刃")# WorldState：节点内部标识翻译grq.get("Node", "SolNode123")# 游戏描述翻译grq.translate(    "Desc",    "/Lotus/Language/Resources/RivenIdentifierDesc")
```

这里有一点需要注意：`Items` 域的目标是收录游戏全部物品，但实际覆盖程度取决于数据源。GRQ 不能因为域名叫 Items，就假定尚未收录的物品不存在。

## **二、域内采用统一的数据结构**

我建议所有域都遵循一份**最小公共 Schema**，再允许各域自行扩展数据字段。

例如 `WarframeMarket` 域中一个物品可以这样保存：

```

{
  "id": "market:example_item",
  "identifiers": {
    "market.slug": "example_item",
    "game.ref": "/Lotus/..."
  },
  "names": {
    "zh-hans": "物品中文名称",
    "en": "Item English Name"
  },
  "aliases": [
    "中文简称",
    "玩家俗称"
  ],
  "metadata": {
    "tradable": true
  }
}

```

这个结构只展示公共规范，并非真实物品数据。

建议公共字段为：

| 字段            | 作用                   |
| ------------- | -------------------- |
| `id`          | 域内稳定资源 ID            |
| `identifiers` | API slug、内部游戏路径等精确标识 |
| `names`       | 各语言正式名称              |
| `aliases`     | 自定义别名、简称和俗称          |
| `metadata`    | 域特有的扩展数据             |

不要求所有域都有完整字段。例如 `Desc` 域可能只有资源路径和多语言文本，不一定有别名。

**不同域允许存在相同的资源 ID 或名称，因为域名本身就是命名空间。**

因此内部资源身份实际采用：

`(domain, resource_id)`

### **特殊情况：Desc 域**

你举出的例子更适合这种数据：

```

{
  "id": "/Lotus/Language/Resources/RivenIdentifierDesc",
  "texts": {
    "zh-hans": "使用并消耗破解器即可立即完成一项尚未揭开的裂罅 Mod 挑战。"
  }
}

```

`Desc` 域与普通物品域并不完全相同，它本质上是一个本地化字符串字典。

所以我们可以允许不同的域声明不同的资源模式，但共享注册、加载、查询和更新能力。

## **三、每个域拥有自己的检索策略**

我建议把域配置设计成声明式，而不是每增加一个域就写一个新的 Resolver。

```
GRQ_DOMAINS = {    "Items": {        "searchable": True,        "fuzzy": True,        "aliases": True,    },    "WarframeMarket": {        "searchable": True,        "fuzzy": True,        "aliases": True,    },    "Node": {        "searchable": True,        "fuzzy": False,        "aliases": True,    },    "Desc": {        "searchable": False,        "fuzzy": False,        "aliases": False,    },}
```

其中 `searchable=False` 只是禁止用户输入名称进行模糊搜索，**不影响通过内部资源键精确读取数据**。

同样，`Node` 的 `fuzzy=False` 并不妨碍以后增加玩家直接按中文地名搜索的功能。业务需要时，可以新增特定查询模式，而不是修改原始 ID 翻译行为。

### **GRQ 的两种核心操作**

必须严格区分：

**Search：用户查询**

```
grq.search("WarframeMarket", "空刃")
```

支持名称标准化、别名、模糊匹配和候选列表。

**Get / Translate：内部标识查询**

```
grq.translate(    "Desc",    "/Lotus/Language/Resources/RivenIdentifierDesc")
```

严格按照原始资源键查表，不使用模糊匹配。

这样 WorldState 中发生字段变化时，不会因为编辑距离相近而错误地把一种资源翻译成另一种。

## **四、重新解决&#x20;**`wm 空刃`**&#x20;的问题**

这次不需要知道空刃属于 Weapon，也不需要先查 Items 域，更不需要让程序猜测武器变体。

我们只需要在 `WarframeMarket` 域中维护独立别名。

例如：

```

{
  "domain": "WarframeMarket",
  "target": "prisma_skana",
  "aliases": [
    "棱晶空刃",
    "空刃"
  ]
}

```

这里使用示意 slug，正式记录必须以实际 Market 目录标识为准。

于是：

`wm 空刃 → WarframeMarket 域 → 别名精确命中 → 市场商品`

而 `wk 空刃` 则完全不受此别名影响，因为它查询的是 `Items` 域。

但不能把“空刃”默认永久视为棱晶空刃的唯一对应物。未来若市场目录中又出现其他相关商品，或者这个别名在同一域内对应多个目标，GRQ 必须能够返回候选，而不是静默覆盖旧数据。

所以我们要规定：

**别名索引是一对多的，而不是一对一的。**

```
alias_index = {    "空刃": {"prisma_skana"},}
```

当存在多个候选时，系统返回歧义结果。新增别名时也必须执行冲突检测。

这样 GRQ 不用理解“棱晶”是什么，只要根据当前域中维护的准确资源数据进行解析即可。

## **五、域之间允许关联，但不自动混合**

尽管域彼此独立，我们仍然可以保留一个非常轻量的可选关联机制。

例如 `WarframeMarket` 商品本身可能提供 `gameRef` 字段，而 Market v2 官方数据模型确实包含 `slug`、`gameRef`、`i18n` 等信息。

[image](https://www.google.com/s2/favicons?domain=https://docs.warframe.market\&sz=32)

Warframe.market Docs



因此可以在需要时建立：

```
WarframeMarket:
  market_slug
      │
      └── gameRef → Items 中的内部标识
```

这种关联可以用于未来的物品详情或跨域查询，但**不作为每次搜索的必经过程**。

没有关联也不影响 `wm` 或 `wk` 的普通查询。

这会让整套系统保持简单，而不会重新膨胀成复杂的游戏知识图谱。

## **六、GRQ 的数据更新和性能设计**

我建议使用 SQLite 持久化全部资源，再在内存中建立各域独立索引。

| 索引             | 用途        | 查找方式         |
| -------------- | --------- | ------------ |
| ID 索引          | 内部资源直接定位  | Hash O(1) 平均 |
| Name 索引        | 正式名称精确匹配  | Hash O(1) 平均 |
| Alias 索引       | 别名精确匹配    | Hash O(1) 平均 |
| Fuzzy 索引       | 错别字和相近名称  | RapidFuzz    |
| Translation 索引 | 原始游戏资源键翻译 | Hash O(1) 平均 |

**性能关键是所有常规查询都在内存中完成。** 无需为每次查询读取 JSON 文件，也无需访问 SQLite。

### **数据更新流程**

1. 从官方游戏资源、Market API、本地映射文件等来源加载新数据
2. 转换成对应 GRQ Domain 的统一格式
3. 合并本地补充翻译和自定义别名
4. 检测重复 ID、冲突别名和无效引用
5. 构建新的域索引，校验成功后原子切换

其中不同来源应记录来源类型、更新时间和数据版本。

我的建议是明确拆分：

- **Source Data：** 自动同步的数据，只读，不手工修改。
- **Overrides：** 我们补充的中文翻译和别名，独立保存。
- **Runtime Index：** 合并后生成的内存索引。

这样 Warframe.market 更新目录时，就不会把自己补充的别名覆盖掉。

对于游戏物品，Warframe 的 Public Export 提供包括资源、配方、地图节点等类别的导出文件，可以作为部分 Items、Node 域的数据来源；但它们不等于游戏所有内部资源的完整清单，需要允许其他官方资源和本地补充表共同导入。

[image](https://www.google.com/s2/favicons?domain=https://warframe.fandom.com\&sz=32)

Fandom



## **七、建议的最终代码结构**

```

grq/
├── __init__.py
├── manager.py            # GRQ 统一入口
├── registry.py           # 域注册
├── models.py             # 公共资源数据模型
├── normalizer.py         # 名称标准化
├── search.py             # 精确、模糊、歧义处理
├── index.py              # 内存索引
├── storage.py            # SQLite
├── sync.py               # 资源同步与更新
│
├── domains/
│   ├── items.py
│   ├── warframe_market.py
│   ├── node.py
│   ├── desc.py
│   ├── mission_type.py
│   └── faction.py
│
├── sources/
│   ├── game_export.py
│   ├── market.py
│   └── local_files.py
│
└── resources/
    └── overrides/
        ├── aliases.json
        └── translations.json

```

以后增加一个 `Relic` 域，通常只需要注册它的资源模式、数据来源和检索策略。无需重新编写一套字符串匹配机制。

## **八、最终的统一接口**

我认为可以把 GRQ 公共 API 控制在非常少的方法内：

```
# 用户名称查询，可能返回唯一结果或多个候选grq.search(    domain="WarframeMarket",    query="空刃")# 精确获取资源grq.get(    domain="Node",    resource_id="SolNode123")# 获取指定语言的名称grq.name(    domain="Items",    resource_id="item_id",    lang="zh-hans")# 精确翻译资源键grq.translate(    domain="Desc",    key="/Lotus/Language/Resources/RivenIdentifierDesc",    lang="zh-hans")# 添加自定义别名grq.add_alias(    domain="WarframeMarket",    resource_id="prisma_skana",    alias="空刃")
```

这里 `search()` 返回的应该是结构化结果，区分 `found`、`ambiguous`、`not_found`，而不是无条件返回最相近的一个资源。

`get()`、`name()`、`translate()` 均通过资源标识精确访问，不能自行启用模糊匹配。

## **我的建议**

我们可以正式放弃此前的 `Unified Entity Registry`，将 GRQ 确定为新的资源基础设施。

它只需要遵循四项原则：

1. **Domain 是资源隔离和查询的基本单位。** 每个业务功能明确选择目标域，不预先猜测物品类型。
2. **所有域共享相同的检索基础设施。** 不再重复实现名称匹配、别名、翻译、缓存和更新。
3. **域内有独立的正式数据和补充数据。** 自动更新不会破坏自定义别名和汉化。
4. **不同域默认互不依赖。** 仅在确实需要跨域查询时建立显式关联。

我还建议增加一个约束：**一个业务模块可以使用多个域，但每次 GRQ 调用必须明确指定域；GRQ 本身绝不私自跨域寻找“更合理”的结果。**

这能从根本上避免之前讨论的很多不确定行为，同时保持扩展能力。

以你现在的项目规模，我认为 **SQLite + 内存索引 + RapidFuzz + 声明式 Domain 配置** 就是很合适的技术组合。不需要向量数据库、AI 分类器，也不需要复杂的实体关系推理。

这版的优势不是系统能够“猜中用户想要什么”，而是让我们能精确控制**每个功能在哪里搜索、哪些名称有效、遇到歧义时怎么处理**。