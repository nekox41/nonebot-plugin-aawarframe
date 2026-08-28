from ...common import client
from typing import List, Dict
from nonebot import logger


BASE_URL = "https://browse.wf"

async def translate(unique_name: str) -> str:
    """
    将内部标识翻译为中文
    """
    url = BASE_URL + unique_name
    resp = await client.get(url)
    if resp.json().get("name", None):
        name_url = BASE_URL + resp.json().get("name")
    else:
        return resp.json().get("zh", unique_name.split("/")[-1])
    result = await client.get(name_url)
    return result.json().get("zh", unique_name.split("/")[-1])


async def translate_batch(unique_names: List[str]) -> Dict[str, str]:
    """
    批量翻译内部标识为中文

    Args:
        unique_names: 需要翻译的内部标识列表

    Returns:
        {unique_name: 中文名} 的字典
    """

    import asyncio

    async def fetch_one(name: str) -> tuple[str, str]:
        url = BASE_URL + name
        logger.info(f"请求 {url}")
        resp = await client.get(url, follow_redirects=True)
        logger.info(f"响应：{resp.json()}")
        if resp.json().get("name", None):
            name_url = BASE_URL + resp.json().get("name")
        else:
            return name, resp.json().get("zh", name.split("/")[-1])
        result = await client.get(name_url, follow_redirects=True)
        zh_data = result.json()
        return name, zh_data.get("zh", name.split("/")[-1])

    results = await asyncio.gather(*[fetch_one(name) for name in unique_names])

    return dict(results)