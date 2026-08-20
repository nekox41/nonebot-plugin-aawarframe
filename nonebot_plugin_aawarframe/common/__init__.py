import asyncio
from pathlib import Path
from typing import Any, Dict

import httpx
from nonebot import logger, get_plugin_config, get_driver
from nonebot_plugin_htmlrender import RenderPluginConfig

driver = get_driver()
client = httpx.AsyncClient()
_ASSETS_DIR = Path(__file__).parent.parent / "assets"
TEMPLATES_DIR = get_plugin_config(
    RenderPluginConfig
).render.resources.local_access.allowed_paths[0]
TEMPLATES = [
    "archimedea.html",
    "bouties.html",
    "current_arbys.html",
    "eidolon_clock.html",
    "orders.html",
    "s_arbys.html",
    "today_arbys.html",
    "void_fissures.html",
]


async def fetch_world_state() -> Dict[str, Any]:
    url = "https://api.warframe.com/cdn/worldState.php"
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.json()


async def read_template(name: str) -> str:
    """根据模板名读取 assets/templates/ 下的 HTML 文件并返回文本内容"""
    template_path = _ASSETS_DIR / "templates" / name
    if not template_path.exists():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")
    return template_path.read_text(encoding="utf-8")


async def download_file(name: str, save_path: str | Path):
    """
    使用 httpx.AsyncClient 流式下载文件到本地
    :param name: 模板名称
    :param save_path: 本地保存路径，建议使用 Path 对象
    """
    BASE_URL = "https://raw.githubusercontent.com/nekox41/nonebot-plugin-aawarframe/refs/heads/master/"
    url = BASE_URL + name
    # 确保保存路径是 Path 对象，并创建其父目录
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    # 使用 stream() 方法获取响应对象，进入上下文后即可读取流式内容
    async with client.stream("GET", url) as response:
        # 检查请求是否成功
        response.raise_for_status()

        # 以二进制写入模式打开目标文件
        with open(save_path, "wb") as f:
            # 分块读取响应内容并写入文件，避免一次性加载大文件到内存
            async for chunk in response.aiter_bytes():
                f.write(chunk)
    logger.info(f"{name} 已经下载到 {save_path}")


@driver.on_startup()
async def download_templates():
    logger.info(f"开始下载渲染模板到：{TEMPLATES_DIR}")
    tasks = []
    for template_name in TEMPLATES:
        save_path = Path(TEMPLATES_DIR) / template_name
        tasks.append(download_file(template_name, save_path))
        results = await asyncio.gather(*tasks, return_exceptions=True)