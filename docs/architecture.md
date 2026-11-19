# 项目架构

项目现在只有一个 Python 包：`nonebot_plugin_aawarframe`。协议入口、查询业务和运行资源都放在这个目录里，不再拆成单独的 core 包。

## 一次查询会经过哪里

```text
QQ / OneBot 消息
       ↓
NoneBot 事件入口
       ↓
命令识别与权限检查
       ↓
业务服务
       ↓
数据提供方与资源查询
       ↓
图片卡片或文本结果
       ↓
对应平台发送消息
```

不同平台只在消息、图片和主动通知这些地方做必要的转换。查询逻辑不需要为 QQ 和 OneBot 各写一份。

## 目录

```text
nonebot_plugin_aawarframe/
├── __init__.py       插件入口和元数据
├── router.py         消息入口、命令分发和平台转换
├── media_qq.py       QQ 图片读取
├── media_onebot.py   OneBot 图片读取
├── admin/            管理台和访问控制
├── commands/         命令解析与分发
├── services/         查询业务
├── providers/        外部数据接口
├── grq/              游戏资源查询与索引
├── models/           数据模型
├── protocols/        平台无关的消息结构
├── rendering/        图片卡片和模板
├── subscriptions/    订阅规则、存储和调度
├── worldstate/       世界状态解析
├── initialization/   首次资源准备与更新
└── assets/           随插件发布的资源
```

## 几个重要边界

- `router.py` 负责接收消息、识别协议和发送结果，不负责实现每一种游戏查询。
- `services/` 负责组织业务；`providers/` 负责从外部来源拿数据。
- `grq/` 负责游戏资源的名称、别名、检索和持久化。
- `rendering/` 负责把查询结果变成图片。
- `subscriptions/` 负责保存订阅、判断是否有新事件，以及安排通知。
- `bootstrap.py` 创建运行时需要的服务，并在 NoneBot 启动和退出时管理它们。

## 数据放在哪里

程序代码和随包发布的基础资源放在插件目录。运行后产生的数据放在 `AAWARFRAME_CACHE_DIR` 指定的目录中，默认是 `data/aawarframe`。升级插件不会要求你把用户数据重新放进代码目录。
