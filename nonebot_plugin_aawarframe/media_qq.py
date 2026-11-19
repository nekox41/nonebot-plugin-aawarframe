"""QQ CDN 附件下载：只在协议层使用，禁止非 QQ 地址和重定向越域。"""

import base64
from urllib.parse import urljoin, urlsplit

import httpx

MAX_IMAGE_BYTES = 12 * 1024 * 1024
ALLOWED_DOMAINS = ("qq.com", "qq.com.cn", "qpic.cn")


async def download_image(url: str) -> bytes | None:
    async with httpx.AsyncClient(timeout=25) as client:
        for _ in range(4):
            parts = urlsplit(url)
            domain = (parts.hostname or "").lower()
            if (
                parts.scheme not in {"http", "https"}
                or not any(domain == item or domain.endswith("." + item) for item in ALLOWED_DOMAINS)
                or parts.username or parts.password
                or parts.port not in {None, 80, 443}
            ):
                return None
            async with client.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared and declared.isdecimal() and int(declared) > MAX_IMAGE_BYTES:
                    raise ValueError("图片超过 12 MB")
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ValueError("图片超过 12 MB")
                return bytes(data)
    return None


def decode_inline(value: str) -> bytes | None:
    if not value.startswith("base64://"):
        return None
    encoded = value[len("base64://"):]
    if len(encoded) > (MAX_IMAGE_BYTES + 2) // 3 * 4 + 16:
        raise ValueError("图片超过 12 MB")
    image = base64.b64decode(encoded, validate=True)
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("图片超过 12 MB")
    return image
