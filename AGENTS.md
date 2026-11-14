# nonebot-plugin-warframe

## 核心约束

- 所有的代码和文档，均以最小化输出位第一原则。以最少的代码实现功能，最少的文字编写文档。
- 文档需要减少技术细节的描写，以最浅显易懂的方式讲给可能不懂技术的人。
- 任何情况下，只确认代码逻辑的正确性，不做实际测试验证。只要代码的逻辑没问题，后续有Bug会有人体提Issues的。
- 你应该在每一个 python 文件的上方加入注释片段，Desc、Date，Author 为 Aameow。

## 项目核心

项目是一个 Nonebot2 的插件，安装此插件可以在 QQ 群内查询游戏 Warframe 的各种游戏数据。

- 官方提供的 API 接口
     - https://wiki.warframe.com/w/WARFRAME#APIs
- 游戏最大的交易市场 Warframe Market 提供的 API 接口
     - https://docs.warframe.market/docs/intro/

回复总是使用[nonebot-plugin-htmlrender](https://github.com/kexue-z/nonebot-plugin-htmlrender)渲染图片回复，我们在编写数据对应的渲染用模板时，应该遵守渲染约束中的内容。

在改动与新增、设计项目架构的时候，我们应该考虑到统一性、可扩展性与性能，项目架构应该符合人类的逻辑，方便人类读懂项目。

## 渲染约束

1. 图片应该被渲染为WebP格式。
2. 目标平台为QQ，我们在设计模板的时候应当以数据的展示为主要目的，最佳情况是让用户不用打开图片就能找到目标信息，最次情况也要让打开后不用再次放大就能看到所有信息。
3. 模板的设计主要以用户的阅读体验为核心，保证用户可以舒适、快速的阅读到自己想要获取的信息，在能展示所有信息的情况下，排版应该紧凑且放大字号。
4. 不应该添加多余的描述，如此功能的实现细节等。
5. 应该在图片的右下角添加我的署名 By. Aameow
6. 图片最大不能超过2000x2000
7. 所有的模板应该只有HTML内容，通过统一的class或者id，读取不同的CSS文件实现不同的主题。


## 自动部署

当前的Codespaces的key已经放到了目标服务器上，通过ssh ubuntu@140.245.86.178可以直接连接。在`/home/ubuntu/aabot`下是Nonebot2，通过screen在后台运行。