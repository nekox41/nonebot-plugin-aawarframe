# AAWarframe Core

Shared backend for the AAWarframe NoneBot2 adapters. Contains the Warframe query engine, world-state services, Market access, SQLite subscriptions, renderer, and internal JSON/HTTP API.

Load through `nonebot_plugin_aawfqq` or `nonebot_plugin_aawfonebot`; both depend on this distribution.

The API is served in-process through FastAPI/ASGI with `httpx.ASGITransport`, so no unauthenticated public port is opened.

Generated offline game assets are fetched during CI from WFCD, warframe.market, browse.wf and a documented translation seed and then bundled into the wheel. See repository `scripts/build_resources.py`.
