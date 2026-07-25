import httpx
from typing import Any, Dict

async def fetch_world_state() -> Dict[str, Any]:
    url = "https://api.warframe.com/cdn/worldState.php"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()