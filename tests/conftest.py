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
assert nonebot.load_plugin("nonebot_plugin_aawarframe") is not None

# The production wheel ships an offline archive, not unpacked JSON files.
# Restore the resource layout as the backend does on startup.
from nonebot_plugin_aawfcore.initialization.pipeline import ensure_offline
from nonebot_plugin_aawfcore.localization.resources import PACKAGED, configure_resources

_test_resource_root = tempfile.TemporaryDirectory(prefix="aawf-pytest-")
_test_assets = (
    ensure_offline(Path(_test_resource_root.name))
    if (PACKAGED / "offline.tar.gz").exists() else None
)


@pytest.fixture(scope="session")
def test_assets_root():
    return _test_assets


@pytest.fixture(autouse=True)
def reset_resource_directory():
    # Some tests deliberately reconfigure the global resource directory.
    if _test_assets is not None:
        configure_resources(_test_assets)
    yield
    if _test_assets is not None:
        configure_resources(_test_assets)


@pytest.fixture
def worldstate():
    return json.loads((Path(__file__).parent / "fixtures" / "worldstate.json").read_text())


@pytest.fixture
def market_items():
    return json.loads((Path(__file__).parent / "fixtures" / "market-items.json").read_text())
