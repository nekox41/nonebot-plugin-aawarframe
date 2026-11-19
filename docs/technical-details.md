# 技术细节

这份文档写给想了解插件内部工作方式、排查问题或参与开发的人。日常安装和配置请先看[安装指南](installation.md)与[配置说明](configuration.md)。

## 资源准备

发布前，CI 会运行 `scripts/build_resources.py`。脚本从项目使用的数据源获取游戏物品、掉落表、市场目录和其他基础数据，校验后生成离线资源包。

离线包会随 Python 包一起发布。机器人启动时先从本地恢复这份资源，不需要在每次启动时重新下载整套游戏目录。运行中需要更新的数据仍由对应服务按需获取。

## 数据访问

- 世界状态、市场和 Wiki 使用各自的数据提供方。
- 常用结果带有缓存，减少重复请求。
- 游戏资源查询使用 SQLite 保存目录和用户调整，并建立内存索引供常规查询使用。
- 订阅记录保存在数据目录中，机器人重启后仍然存在。

外部数据源偶尔会维护、限流或返回不完整内容。遇到上游故障时，部分查询可能暂时不可用，缓存也可能不是最新状态。

## 图片和 OCR

图片卡片由统一的渲染层生成，模板和样式分别维护。渲染使用 nonebot-plugin-htmlrender 与 Playwright。

紫卡识别使用 PaddleOCR。OCR 依赖是可选项，不安装时不会影响普通查询。识别任务通过独立工作进程处理，避免长时间识别阻塞其他命令。

更多识别说明见[紫卡图片分析](riven-analysis.md)。

## 订阅

订阅保存在 SQLite 数据库中。服务定期检查对应的数据源，发现符合条件的新事件后，再交给当前在线的平台 Bot 发送。不同机器人、群组和用户的订阅身份会分别保存。

通知是否能成功送达，还取决于 QQ 官方平台或 OneBot 服务端的权限、在线状态和频率限制。

## 开发与验证

本地开发安装：

```bash
python -m pip install -e ".[dev,qq,onebot]"
python scripts/build_resources.py --build
python -m compileall -q nonebot_plugin_aawarframe scripts tests
python -m pytest -q
```

构建资源需要访问上游数据源。测试使用项目内的记录样本，不需要连接真实机器人。

## 进一步阅读

- [统一物品标识与数据库](unified-items.md)
- [Wiki 请求方式记录](wiki-request-comparison.md)
- [紫卡图片分析](riven-analysis.md)
