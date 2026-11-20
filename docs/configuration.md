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
管理台使用 HTTP。建议保持监听地址为 `127.0.0.1`，通过 SSH 本地端口转发访问；不要直接暴露在公网。

管理台涉及本地配置与模板修改。通过 SSH 隧道访问时，浏览器使用 `http://localhost:本地端口`。HTTP 不提供传输加密，因此应保持回环地址监听，并通过 SSH 隧道远程访问。

登录后可以在 WebUI 中使用以下功能：

- **运行概览**：查看已注册协议、Bot 数量、资源索引、别名、订阅和图片渲染性能。
- **渲染预览**：使用本地示例数据生成各功能的 WebP 图片，不会为了预览额外请求上游接口。
- **资源别名**：搜索游戏物品并添加、删除自定义别名。
- **模板编辑器**：查看功能可用数据与 Jinja 占位符，创建多个 HTML/Jinja 模板和 CSS 版本，并在渲染预览中按功能选择启用版本。版本不会互相覆盖。
- **仲裁数据**：修改仲裁节点评级与每分钟生息精华记录。

模板版本、CSS 版本和各功能的选择配置保存在 `AAWARFRAME_CACHE_DIR/admin/overrides/`，不会改写安装包文件。升级插件时这些版本与选择仍会保留。

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
