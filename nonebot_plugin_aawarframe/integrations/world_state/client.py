from ...common import client
from typing import List
from .schemas import WeeklyVaultBonus, WorldState

WORLD_STATUS_URL = "https://api.warframe.com/cdn/worldState.php"


async def fetch_weekly_vault() -> List[WeeklyVaultBonus]:
    """获取氏族每周奖励数据"""

    response = await client.get(WORLD_STATUS_URL)
    data = response.json()

    vault_data = data.get("WeeklyVaultBonusRewards", [])
    return [WeeklyVaultBonus(**item) for item in vault_data]

async def fetch_world_state() -> WorldState:
    response = await client.get(WORLD_STATUS_URL)
    data = response.json()
    return WorldState(**data)