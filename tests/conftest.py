# 作用：提供 conftest 测试与联调支持。
# 编写日期：2026-11-07
# 作者：Aameow

import json
import tempfile
from pathlib import Path

import nonebot
import pytest

nonebot.init(driver="~none", render={"provider": "playwright", "startup": "off"})
assert nonebot.load_plugin("nonebot_plugin_aawfcore") is not None

# The production wheel ships an offline archive, not unpacked JSON files.
# Restore the resource layout as the backend does on startup.
from nonebot_plugin_aawfcore.initialization.pipeline import ensure_offline
from nonebot_plugin_aawfcore.localization.resources import PACKAGED

_test_resource_root = tempfile.TemporaryDirectory(prefix="aawf-pytest-")
if (PACKAGED / "offline.tar.gz").exists():
    ensure_offline(Path(_test_resource_root.name))


@pytest.fixture
def worldstate():
    return json.loads((Path(__file__).parent / "fixtures" / "worldstate.json").read_text())


@pytest.fixture
def market_items():
    return json.loads((Path(__file__).parent / "fixtures" / "market-items.json").read_text())
