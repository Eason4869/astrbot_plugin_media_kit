"""惰性下载：把 URL 列表下载到缓存目录，返回第一个成功文件的路径。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ..logger import logger


async def _download_one(url: str, cache_dir: Path, metadata: Dict[str, Any]) -> Optional[Path]:
    import aiohttp
    from PIL import Image
    from io import BytesIO
    import uuid
    from ..downloader.security import create_public_only_connector, safe_request
    from ..downloader.budget import DEFAULT_IMAGE_MAX_BYTES, MAX_IMAGE_PIXELS

    if url.startswith("//"):
        url = "https:" + url
    source_url = str(metadata.get("url") or "").strip()
    try:
        parsed_source = urlparse(source_url)
        referer = (
            f"{parsed_source.scheme}://{parsed_source.netloc}/"
            if parsed_source.scheme and parsed_source.netloc
            else "https://www.bilibili.com/"
        )
    except Exception:
        referer = "https://www.bilibili.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": referer,
    }
    image_headers = metadata.get("image_headers") or {}
    if isinstance(image_headers, dict):
        headers.update({k: str(v) for k, v in image_headers.items()})

    proxy = None
    if metadata.get("use_image_proxy") and metadata.get("proxy_url"):
        proxy = metadata["proxy_url"]

    try:
        timeout = aiohttp.ClientTimeout(total=20, connect=8)
        connector = create_public_only_connector(trusted_proxy_urls=[proxy] if proxy else [])
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            resp = await safe_request(session, "GET", url, headers=headers, proxy=proxy)
            try:
                if resp.status != 200:
                    logger.debug(f"rika 下载失败: HTTP {resp.status}: {url}")
                    return None
                chunks, total = [], 0
                async for chunk in resp.content.iter_chunked(65536):
                    total += len(chunk)
                    if total > DEFAULT_IMAGE_MAX_BYTES:
                        raise ValueError("卡片图片超过下载大小限制")
                    chunks.append(chunk)
                raw = b"".join(chunks)
            finally:
                resp.release()
    except Exception as e:
        logger.debug(f"rika 下载失败: {url}, 错误: {e}")
        return None

    if not raw:
        return None
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("卡片图片超过像素限制")
            image.verify()
    except Exception as e:
        logger.debug(f"rika 响应非图片: {url}, {e}")
        return None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        out = cache_dir / f"rika_{uuid.uuid4().hex}.jpg"
        out.write_bytes(raw)
        return out
    except Exception as e:
        logger.debug(f"rika 保存失败: {e}")
        return None


async def download_first_to_cache(
    urls: List[str],
    *,
    cache_dir: Path,
    metadata: Dict[str, Any],
    kind: str = "image",
) -> Path:
    """依次尝试下载，返回第一个成功的本地路径；全部失败抛异常。"""
    from aiohttp import ClientError

    for url in urls:
        path = await _download_one(url, cache_dir, metadata)
        if path is not None:
            logger.debug(f"rika {kind} 下载成功: {url}")
            return path
    raise RuntimeError(f"rika {kind} 下载失败: {urls[:2]}")
