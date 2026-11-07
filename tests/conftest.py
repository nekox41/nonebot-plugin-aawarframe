import json
from pathlib import Path

import nonebot
import pytest

nonebot.init(driver="~none", render={"provider": "playwright", "startup": "off"})
assert nonebot.load_plugin("nonebot_plugin_aawarframe") is not None


@pytest.fixture
def worldstate():
    return json.loads((Path(__file__).parent / "fixtures" / "worldstate.json").read_text())


@pytest.fixture
def market_items():
    return json.loads((Path(__file__).parent / "fixtures" / "market-items.json").read_text())
