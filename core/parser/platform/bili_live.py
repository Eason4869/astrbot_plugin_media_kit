"""B站直播房间解析器。

为 B站直播链接返回「仅卡片」元数据：卡片渲染使用直播间封面，不产生任何
视频 / 图片下载节点。数据来源为 B站公开接口 `room/v1/Room/get_info` 与
直播间页面内嵌的作者名，无需登录即可获取直播间标题、作者、封面、开播状态与公告。
"""

from __future__ import annotations

import asyncio
import html as html_lib
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from ...types import MediaMetadata
from ..utils import build_request_headers
from .base import BaseVideoParser

BILI_LIVE_GET_INFO_API = (
    "https://api.live.bilibili.com/room/v1/Room/get_info"
)
BILI_LIVE_HOSTS = {"live.bilibili.com"}
BILI_LIVE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
LIVE_ROOM_PATH_RE = re.compile(
    r"^/(?:[\w-]+/)?(\d{1,12})(?:/|$)",
    re.IGNORECASE,
)
LIVE_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class BiliLiveParser(BaseVideoParser):
    """解析 B站直播间链接，仅返回可渲染卡片的信息，不下发媒体。"""

    def __init__(self) -> None:
        super().__init__("live")
        self.semaphore = asyncio.Semaphore(4)

    # ── 链接识别 ────────────────────────────────────────

    def _parse_room_id(self, url: str) -> Optional[str]:
        """从 B站 直播间 URL 中提取真实的房间号（short/long 均可）。"""
        if not isinstance(url, str) or not url.strip():
            return None
        try:
            parsed = urlparse(url.strip())
        except (TypeError, ValueError):
            return None
        if parsed.scheme.lower() not in {"http", "https"}:
            return None
        host = (parsed.hostname or "").lower().rstrip(".")
        if host not in BILI_LIVE_HOSTS:
            return None
        match = LIVE_ROOM_PATH_RE.search(parsed.path or "")
        if not match:
            return None
        room_id = match.group(1)
        # 忽略纯数字 ID 内误带的其它数字片段；房间号应为一串数字
        digits = re.sub(r"\D", "", room_id)
        if not digits or int(digits) <= 0:
            return None
        return digits

    def can_parse(self, url: str) -> bool:
        """判断是否为可解析的 B站 直播间链接。"""
        return self._parse_room_id(url) is not None

    def extract_links(self, text: str) -> List[str]:
        """从文本中提取 B站 直播间链接并去重。"""
        links: List[str] = []
        seen_ids = set()
        for match in re.finditer(
            r"https?://live\.bilibili\.com/[^\s<>\"'()]+",
            text or "",
            re.IGNORECASE,
        ):
            link = match.group(0).rstrip(".,!?)]}>\"'，。！？；：）】》」")
            room_id = self._parse_room_id(link)
            if room_id and room_id not in seen_ids:
                seen_ids.add(room_id)
                links.append(link)
        return links

    # ── 数据获取 ────────────────────────────────────────

    @staticmethod
    def _clean_html(value: Any) -> str:
        """清理 B站 直播公告 HTML 为纯文本。"""
        text = str(value or "").strip()
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("\u00a0", " ").replace("\u3000", " ")
        return re.sub(r"[ \t\r\f\v]+", " ", html_lib.unescape(text)).strip()[:400]

    async def _fetch_room_info(
        self, session: aiohttp.ClientSession, room_id: str
    ) -> Dict[str, Any]:
        """调用 B站 公开接口获取直播间信息。"""
        headers = {
            "User-Agent": BILI_LIVE_UA,
            "Referer": f"https://live.bilibili.com/{room_id}",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        async with session.get(
            BILI_LIVE_GET_INFO_API,
            params={"room_id": room_id},
            headers=headers,
            timeout=LIVE_REQUEST_TIMEOUT,
        ) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
        if not isinstance(payload, dict):
            raise RuntimeError("B站直播接口返回的 JSON 不是对象")
        if payload.get("code") not in (0,):
            msg = str(payload.get("msg") or payload.get("message") or "未知错误")
            raise RuntimeError(f"B站直播接口返回错误: {msg}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("B站直播接口未返回房间数据")
        return data

    async def _fetch_anchor_meta(
        self, session: aiohttp.ClientSession, room_id: str
    ) -> tuple[str, str]:
        """从直播间页面内嵌 JSON 中解析主播昵称与头像（无需登录态）。"""
        headers = {
            "User-Agent": BILI_LIVE_UA,
            "Referer": "https://live.bilibili.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        try:
            async with session.get(
                f"https://live.bilibili.com/{room_id}",
                headers=headers,
                timeout=LIVE_REQUEST_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
        except Exception:
            return "", ""
        # 页面以 JSON 字段嵌入主播信息
        name = ""
        m = re.search(r'"uname"\s*:\s*"([^"]*)"', text)
        if m:
            name = m.group(1).strip()
        else:
            m = re.search(r'"nickname"\s*:\s*"([^"]*)"', text)
            name = m.group(1).strip() if m else ""
        face = ""
        m = re.search(r'"face"\s*:\s*"([^"]*)"', text)
        if m:
            face = m.group(1).strip().replace("\\u002F", "/").replace("\\/", "/")
            if face.startswith("//"):
                face = "https:" + face
        return name, face

    # ── 解析主流程 ──────────────────────────────────────

    async def parse(
        self, session: aiohttp.ClientSession, url: str
    ) -> Optional[MediaMetadata]:
        """解析 B站 直播间并返回仅卡片元数据。"""
        async with self.semaphore:
            room_id = self._parse_room_id(url)
            if not room_id:
                raise RuntimeError(f"无法从链接提取直播间号: {url}")
            self.logger.debug(
                f"[{self.name}] parse: 解析直播间 room_id={room_id}"
            )

            room = await self._fetch_room_info(session, room_id)
            if not room:
                raise RuntimeError(f"无法获取直播间信息: {room_id}")

            title = str(room.get("title") or "B站直播间").strip()
            # 封面优先级：user_cover（直播间封面）> keyframe（开播关键帧）> background
            cover = (
                str(room.get("user_cover") or "").strip()
                or str(room.get("keyframe") or "").strip()
                or str(room.get("background") or "").strip()
            )
            if cover.startswith("//"):
                cover = "https:" + cover

            live_status = int(room.get("live_status") or 0)
            status_text = {0: "未开播", 1: "直播中", 2: "轮播中"}.get(
                live_status, "未知状态"
            )
            area = str(room.get("area_name") or "").strip()
            online = int(room.get("online") or 0)
            live_time = str(room.get("live_time") or "").strip()
            if live_time == "0000-00-00 00:00:00":
                live_time = ""
            description = self._clean_html(room.get("description"))

            anchor_name, anchor_face = await self._fetch_anchor_meta(
                session, room_id
            )

            detail_lines = [f"直播状态：{status_text}"]
            if live_status == 1 and online >= 0:
                detail_lines.append(f"在线观众：{online}")
            if area:
                detail_lines.append(f"直播分区：{area}")
            if live_time:
                detail_lines.append(f"开播时间：{live_time}")
            if description:
                detail_lines.extend(["", "直播间公告：", description])
            desc = "\n".join(detail_lines)

            canonical_url = f"https://live.bilibili.com/{room_id}"
            result: MediaMetadata = {
                "url": url,
                "source_url": url,
                "platform": "live",
                "parser_name": self.name,
                "title": title,
                "author": anchor_name,
                "avatar_url": anchor_face,
                "desc": desc,
                "timestamp": live_time or "",
                "video_urls": [],
                "image_urls": [],
                # 仅卡片：直播间封面仅用于渲染卡片主视觉，不属于可下载媒体
                "card_cover_urls": [[cover]] if cover else [],
                "cover_url": cover,
                "is_live": True,
                "live_status": live_status,
                "image_headers": build_request_headers(
                    is_video=False,
                    referer=canonical_url,
                ),
                "video_headers": build_request_headers(
                    is_video=True,
                    referer=canonical_url,
                ),
            }
            self.logger.debug(
                f"[{self.name}] parse: 直播解析完成 room_id={room_id}, "
                f"status={live_status}, title={title[:30]!r}"
            )
            return result