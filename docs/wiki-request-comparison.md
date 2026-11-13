# Wiki 请求方式对照

2026-11-13，在同一目标服务器上对照同一个搜索 URL。请求串行发送，间隔至少一秒；API 请求不携带 Cookie。

## 实测结果

| 方式 | 结果 |
| --- | --- |
| Chromium 页面内 fetch，实际协商 HTTP/3 | 200，返回搜索数据 |
| HTTPX，复制浏览器请求头，HTTP/1.1 | 403，Cloudflare 验证页 |
| HTTPX，复制浏览器请求头，HTTP/2 | 403，Cloudflare 验证页 |
| requests，复制浏览器请求头 | 403 |
| Playwright APIRequestContext | 403 |
| curl_cffi，默认协议协商 | 403 |
| curl_cffi，Chromium 协议配置并固定 HTTP/1.1 | 200，返回搜索数据 |

直连成功不需要页面、Cookie、来源页验证参数或网页 JavaScript。异步会话复用后，不同关键词及重复查询均成功。

## 当前实现

Wiki 使用 curl_cffi 的异步连接，不启动浏览器。请求头只保留 Accept、Accept-Encoding、Accept-Language 和包含项目联系网址的 User-Agent；使用已验证的组合与发送顺序。

优先请求 HTTP；站点目前会将它重定向到 HTTPS，每一跳都经过同一队列限速。请求最多每秒一次，同词查询合并，结果缓存五分钟。验证页和失败响应不缓存。

23 项相关检查及服务器完整命令验证通过。图片命令继续使用 htmlrender，Wiki 查询不再维护浏览器页面。

## 可以确认的区别

复制 User-Agent 或全部请求头，不足以让不同客户端得到相同结果。本次可用配置包含客户端协议实现、HTTP 版本和请求头组合；不能仅凭这些结果认定某一个字段是唯一原因。

Cloudflare 支持通过 [JA3/JA4](https://developers.cloudflare.com/bots/additional-configurations/ja3-ja4-fingerprint/) 识别 TLS 客户端。具体站点规则需要站方日志才能确认。
