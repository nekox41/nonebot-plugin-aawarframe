import httpx
from typing import Any, Dict
from pathlib import Path

client = httpx.AsyncClient()

async def fetch_world_state() -> Dict[str, Any]:
    url = "https://api.warframe.com/cdn/worldState.php"
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.json()

_ASSETS_DIR = Path(__file__).parent.parent / "assets"

async def read_template(name: str) -> str:
    """根据模板名读取 assets/templates/ 下的 HTML 文件并返回文本内容"""
    template_path = _ASSETS_DIR / "templates" / name
    if not template_path.exists():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")
    return template_path.read_text(encoding="utf-8")