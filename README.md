<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://github.com/nekox41/nonebot-plugin-aawarframe/blob/master/imgs/logo.png" width="180" height="180" alt="aawarframeLogo"></a>
  <br>
  <p><img src="https://github.com/nekox41/nonebot-plugin-aawarframe/blob/master/imgs/logo.svg" width="240" alt="aawarframeLogo"></p>
</div>

<div align="center">

# nonebot-plugin-aawarframe

_✨ Aa 的 Warframe 助手，用于查询游戏状态。 ✨_


<a href="./LICENSE">
    <img src="https://img.shields.io/github/license/nekox41/nonebot-plugin-aawarframe.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-aawarframe">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-aawarframe.svg" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="python">

</div>

## 📖 介绍

这是一个用于游戏 Warframe 的插件，提供游戏内的信息查询功能。

功能列表：
- [x] 查询夜灵平原时间
- [x] 查询本周科研任务
  - [x] 时光科研
  - [x] 深层科研
- [ ] 查询仲裁任务
  - [x] 当前仲裁任务与下一次仲裁
  - [x] 今日所有仲裁
  - [x] 未来 5 个 S 级仲裁时间
- [ ] Warframe Market 商品信息查询

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-aawarframe

</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details>
<summary>pip</summary>

    pip install nonebot-plugin-aawarframe
</details>
<details>
<summary>pdm</summary>

    pdm add nonebot-plugin-aawarframe
</details>
<details>
<summary>poetry</summary>

    poetry add nonebot-plugin-aawarframe
</details>
<details>
<summary>conda</summary>

    conda install nonebot-plugin-aawarframe
</details>

打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分追加写入

    plugins = ["nonebot_plugin_template"]

</details>

## 🎉 使用
### 指令表
|  指令  | 权限  | 需要@ | 范围 |        说明        |
|:----:|:---:|:---:|:--:|:----------------:|
| 夜灵平原 | 所有人 |  否  | 群聊 |     返回夜灵平原时间     |
| 时光科研 | 所有人 |  否  | 群聊 |     返回本周时光科研     |
| 深层科研 | 所有人 |  否  | 群聊 |     返回本周深层科研     |
|  仲裁  | 所有人 |  否  | 群聊 |   返回当前仲裁和下一次仲裁   |
| 今日仲裁 | 所有人 |  否  | 群聊 |     返回今日所有仲裁     |
| 高效仲裁 | 所有人 |  否  | 群聊 | 返回 5 个接下来的 S 级仲裁 |
### 效果图
<p><img src="https://github.com/nekox41/nonebot-plugin-aawarframe/blob/master/imgs/example1.png" alt="效果图1"></p>
<p><img src="https://github.com/nekox41/nonebot-plugin-aawarframe/blob/master/imgs/example2.png" alt="效果图2"></p>