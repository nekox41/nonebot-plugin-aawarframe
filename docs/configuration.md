# 配置

插件的配置项以 `AAWARFRAME_` 开头，放在 NoneBot 项目的环境文件中，例如 `.env.prod`。

下面列出插件启动时读取的配置。大多数情况下，默认值就够用。

## 常用配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AAWARFRAME_CACHE_DIR` | `data/aawarframe` | 数据、缓存和订阅数据库目录 |
| `AAWARFRAME_WORLDSTATE_PROXY` | 不设置 | 获取官方世界状态时使用的代理地址 |
| `AAWARFRAME_HTTP_TIMEOUT` | `12` | 普通 HTTP 请求超时秒数 |
| `AAWARFRAME_WORLDSTATE_TTL` | `45` | 世界状态缓存秒数 |
| `AAWARFRAME_MARKET_TTL` | `30` | 市场数据缓存秒数 |
| `AAWARFRAME_THEME` | `default` | 图片卡片主题名称 |
| `AAWARFRAME_RENDER_CONCURRENCY` | `2` | 同时渲染的图片数量，范围为 1–2 |
| `AAWARFRAME_OCR_PYTHON` | 自动选择 | OCR 子进程使用的 Python 可执行文件 |

## 管理台

管理台默认关闭。确实需要网页管理功能时再开启：

```dotenv
AAWARFRAME_ADMIN_ENABLED=true
AAWARFRAME_ADMIN_HOST=127.0.0.1
AAWARFRAME_ADMIN_PORT=8443
AAWARFRAME_ADMIN_PASSWORD=请替换为自己的长随机密码
```

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AAWARFRAME_ADMIN_ENABLED` | `false` | 是否启动管理台 |
| `AAWARFRAME_ADMIN_HOST` | `127.0.0.1` | 管理台监听地址 |
| `AAWARFRAME_ADMIN_PORT` | `8443` | 管理台端口 |
| `AAWARFRAME_ADMIN_PASSWORD` | 自动生成 | 管理台登录口令 |
| `AAWARFRAME_ADMIN_PUBLIC_HOST` | 不设置 | 对外访问时使用的主机名 |
| `AAWARFRAME_ADMIN_CERT` | 不设置 | HTTPS 证书文件 |
| `AAWARFRAME_ADMIN_KEY` | 不设置 | HTTPS 私钥文件 |

管理台涉及命令开关、访问名单和本地资源修改。不要把它直接暴露在公网；确实需要远程访问时，请同时配置强口令和 HTTPS。

## 一个简单的环境文件

```dotenv
AAWARFRAME_CACHE_DIR=data/aawarframe
AAWARFRAME_HTTP_TIMEOUT=12
AAWARFRAME_WORLDSTATE_TTL=45
AAWARFRAME_MARKET_TTL=30
AAWARFRAME_THEME=default
AAWARFRAME_ADMIN_ENABLED=false
```

配置项不需要全部填写。没有写出的项目会使用默认值。

## 数据目录

`AAWARFRAME_CACHE_DIR` 不只是临时缓存目录。订阅、资源索引和用户调整的数据也会保存在这里。迁移机器人或更换部署目录时，记得一并迁移这个目录。
