# 安装

插件需要 Python 3.12 和 NoneBot2。根据机器人使用的协议，选择对应的安装方式即可。

## 通过 PyPI 安装

QQ 官方机器人：

```bash
pip install "nonebot-plugin-aawarframe[qq]"
```

OneBot V11：

```bash
pip install "nonebot-plugin-aawarframe[onebot]"
```

两个协议都要使用：

```bash
pip install "nonebot-plugin-aawarframe[qq,onebot]"
```

如果还要使用紫卡图片识别，再安装 OCR 依赖：

```bash
pip install "nonebot-plugin-aawarframe[ocr]"
```

## 在 NoneBot2 中加载

在 NoneBot 项目的配置中加入插件名和实际使用的适配器。例如，QQ 官方机器人：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_aawarframe"]
adapters = ["nonebot.adapters.qq"]
```

OneBot V11 使用 `nonebot.adapters.onebot.v11`。如果项目已经有 `[tool.nonebot]` 配置，只需把对应条目合并进去，不要覆盖原有插件和适配器。

也可以在启动代码中加载：

```python
nonebot.load_plugin("nonebot_plugin_aawarframe")
```

## 从 GitHub Release 手动安装

如果不想通过 PyPI 安装，可以到 [GitHub Releases](https://github.com/nekox41/nonebot-plugin-aawarframe/releases) 下载手动安装包。

解压后会得到一个 `nonebot_plugin_aawarframe` 目录。把整个目录放进 NoneBot 项目的插件目录，再按项目原本的方式加载它即可。

压缩包里只有插件目录，不需要再寻找或安装单独的 core 包。

## 图片渲染

插件使用 nonebot-plugin-htmlrender 生成图片卡片。请按该插件的说明准备 Playwright 浏览器运行环境。若普通文本查询正常、图片卡片无法生成，优先检查浏览器是否安装，以及运行用户是否有权限访问浏览器文件。

## 升级前

插件的数据默认保存在 `data/aawarframe`。升级前建议备份这个目录，里面可能有本地资源、市场索引、订阅和其他运行数据。
