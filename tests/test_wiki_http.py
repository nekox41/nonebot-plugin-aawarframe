# 作用：验证 Wiki 队列限速、跳转、同词合并与关闭清理。
# 编写日期：2026-11-13
# 作者：Aameow

import asyncio
from time import monotonic

import httpx
import pytest

from nonebot_plugin_aawarframe.infrastructure.wiki_http import WikiHttpClient
from nonebot_plugin_aawarframe.models.errors import WikiChallengeError
from nonebot_plugin_aawarframe.providers.wiki import WikiProvider

API = 'http://warframe.huijiwiki.com/api.php?action=opensearch&search=Te'


async def test_http_first_fifo_redirects_rate_limit_and_duplicate_cache():
    calls = []

    async def handle(request):
        calls.append((request.url.scheme, request.url.params['search'], monotonic()))
        assert 'AAWarframe/' in request.headers['User-Agent']
        assert 'https://github.com/nekox41/nonebot-plugin-aawarframe' in request.headers['User-Agent']
        assert request.headers['Accept-Encoding'] == 'gzip, deflate, br, zstd'
        if request.url.scheme == 'http' and request.url.params['search'] == 'A':
            return httpx.Response(301, headers={'Location': str(request.url.copy_with(scheme='https'))})
        return httpx.Response(200, json=[request.url.params['search'], [], [], []])

    http = WikiHttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    provider = WikiProvider(http)
    try:
        results = await asyncio.gather(*(provider.search(key) for key in ['A', 'A', 'B']))
        assert [r.data.query for r in results] == ['A', 'A', 'B']
        assert [(scheme, key) for scheme, key, _ in calls] == [('http', 'A'), ('https', 'A'), ('http', 'B')]
        assert all(b[2] - a[2] >= .99 for a, b in zip(calls, calls[1:]))
        await provider.search('A')
        assert len(calls) == 3
    finally:
        await provider.close()
        await http.close()


async def test_retry_after_cools_down_following_requests_without_hidden_retries():
    calls = []

    def handle(request):
        calls.append(monotonic())
        if len(calls) == 1:
            return httpx.Response(429, headers={'Retry-After': '1.2'})
        return httpx.Response(200, json=['Te', [], [], []])

    http = WikiHttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    try:
        results = await asyncio.gather(http.get_json(API), http.get_json(API), return_exceptions=True)
        assert isinstance(results[0], httpx.HTTPStatusError)
        assert results[1] == ['Te', [], [], []]
        assert len(calls) == 2 and calls[1] - calls[0] >= 1.19
    finally:
        await http.close()


async def test_one_cancelled_caller_does_not_cancel_shared_query():
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def handle(request):
        calls.append(request)
        started.set()
        await release.wait()
        return httpx.Response(200, json=['Te', [], [], []])

    http = WikiHttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    provider = WikiProvider(http)
    first = asyncio.create_task(provider.search('Te'))
    second = asyncio.create_task(provider.search('Te'))
    try:
        await started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert (await second).data.query == 'Te'
        await provider.search('Te')
        assert len(calls) == 1
    finally:
        release.set()
        await provider.close()
        await http.close()


async def test_shutdown_cancels_active_and_queued_requests():
    started = asyncio.Event()

    async def handle(request):
        started.set()
        await asyncio.Event().wait()

    http = WikiHttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    tasks = [asyncio.create_task(http.get_json(API)) for _ in range(3)]
    await started.wait()
    await http.close()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(result, asyncio.CancelledError) for result in results)
    assert http.queue.empty() and http.client.is_closed
    with pytest.raises(RuntimeError):
        await http.get_json(API)


async def test_foreign_redirect_is_rejected_without_following_it():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(302, headers={'Location': 'https://other.example/api.php'})

    http = WikiHttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    try:
        with pytest.raises(RuntimeError, match='非本站'):
            await http.get_json(API)
        assert len(calls) == 1
    finally:
        await http.close()


async def test_api_challenge_is_not_cached():
    def handle(request):
        return httpx.Response(403)

    http = WikiHttpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    provider = WikiProvider(http)
    try:
        with pytest.raises(WikiChallengeError):
            await provider.search('Te')
        assert not provider.cache.entries
    finally:
        await provider.close()
        await http.close()
