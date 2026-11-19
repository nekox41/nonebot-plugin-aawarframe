# 作用：验证 Wiki libcurl 传输的解压处理、凭据隔离和资源释放。
# 编写日期：2026-11-13
# 作者：Aameow

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from nonebot_plugin_aawarframe.infrastructure.wiki_http import WIKI_HEADERS
from nonebot_plugin_aawarframe.infrastructure.wiki_transport import WikiCurlTransport


async def test_decompressed_body_is_not_decoded_twice_and_only_public_headers_are_forwarded(monkeypatch):
    session = SimpleNamespace(
        request=AsyncMock(return_value=SimpleNamespace(
            status_code=200,
            headers={'content-type': 'application/json', 'content-encoding': 'gzip',
                     'content-length': '999', 'cf-cache-status': 'HIT'},
            content=b'["Te",[],[],[]]',
        )),
        close=AsyncMock(),
    )
    monkeypatch.setattr('nonebot_plugin_aawarframe.infrastructure.wiki_transport.AsyncSession',
                        lambda **kwargs: session)
    async with httpx.AsyncClient(transport=WikiCurlTransport()) as client:
        response = await client.get('https://warframe.huijiwiki.com/api.php',
                                    headers={**WIKI_HEADERS, 'Cookie': 'private', 'Authorization': 'private'})
        assert response.json() == ['Te', [], [], []]
        assert response.headers['cf-cache-status'] == 'HIT'
        forwarded = session.request.await_args.kwargs['headers']
        assert list(forwarded) == ['accept', 'accept-encoding', 'accept-language', 'user-agent']
        assert 'Cookie' not in forwarded and 'Authorization' not in forwarded
    session.close.assert_awaited_once()
