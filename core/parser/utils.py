"""core.parser.utils 模块。"""

from __future__ import annotations
import json
import re
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse


class SkipParse(Exception):
    pass


# 在共享 aiohttp session 上挂载的短链展开缓存属性名（见 remember/recall 助手）
_B23_EXPAND_CACHE_ATTR = "_media_kit_b23_expand_cache"


def remember_expanded_url(session, short_url: str, expanded_url: str) -> None:
    """在会话级缓存记录短链展开结果，供回落的其它解析器复用。

    b23 短链先由直播解析器展开确认；确认是视频后会 SkipParse 回落到 B站视频
    解析器。把已得到的展开结果缓存到共享 session 上，可避免视频解析器重新
    发起一遍相同的重定向请求（省一次网络往返，也少一个失败点）。
    """
    try:
        if session is None or not short_url or not expanded_url:
            return
        cache = getattr(session, _B23_EXPAND_CACHE_ATTR, None)
        if not isinstance(cache, dict):
            cache = {}
            setattr(session, _B23_EXPAND_CACHE_ATTR, cache)
        cache[short_url.strip()] = expanded_url
    except Exception:
        # 缓存仅为优化，任何异常都不应影响解析主流程
        pass


def recall_expanded_url(session, short_url: str) -> Optional[str]:
    """读取会话级缓存中的短链展开结果；无记录返回 None。"""
    try:
        cache = getattr(session, _B23_EXPAND_CACHE_ATTR, None)
        if isinstance(cache, dict):
            value = cache.get((short_url or "").strip())
            return value if isinstance(value, str) else None
    except Exception:
        return None
    return None


def format_duration_ms(duration_ms) -> str:
    """将毫秒时长格式化为 mm:ss 或 hh:mm:ss。"""
    if duration_ms is None:
        return ""
    try:
        total_seconds = max(0, int(duration_ms) // 1000)
    except (TypeError, ValueError):
        return ""

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _ensure_url_has_scheme(url: str) -> str:
    """确保URL带有scheme，便于urlparse正确解析hostname。"""
    if not url:
        return url
    u = url.strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith(("http://", "https://")):
        return u
    return "https://" + u


def _is_live_url_basic(url: str) -> bool:
    """仅基于hostname标签判断是否为live域名。"""
    parsed = urlparse(_ensure_url_has_scheme(url))
    host = (parsed.hostname or "").strip(".").lower()
    if not host:
        return False
    labels = [x for x in host.split(".") if x]
    return "live" in labels


def is_live_url(url: str) -> bool:
    """判断是否为直播类型链接或“跳转到直播”的重定向链接。

    规则：
    - 直链：hostname 的任意标签为 live，则判定为直播域名链接
    - 重定向：若URL的 query 参数里包含一个可解码出的URL，且该URL为直播域名链接，则也判定为直播

    例：
    - https://live.bilibili.com/ -> True
    - https://api.live.bilibili.com/ -> True
    - https://example.com/redirect?url=https%3A%2F%2Flive.example.com%2Froom -> True
    - https://www.douyin.com/ -> False
    """
    if not url:
        return False
    try:
        if _is_live_url_basic(url):
            return True

        parsed = urlparse(_ensure_url_has_scheme(url))
        qs = parse_qs(parsed.query, keep_blank_values=True)
        for values in qs.values():
            for v in values:
                if not v:
                    continue
                candidate = v.strip()
                for _ in range(3):
                    if _is_live_url_basic(candidate):
                        return True
                    new_candidate = unquote(candidate)
                    if new_candidate == candidate:
                        break
                    candidate = new_candidate

        return False
    except Exception:
        return False


def extract_url_from_card_data(msg_data) -> Optional[str]:
    """从单个消息段的 data 字段中提取 QQ 结构化卡片 URL。"""
    try:
        curl_link = None
        if isinstance(msg_data, dict) and not msg_data.get('data'):
            meta = msg_data.get("meta") or {}
            detail_1 = meta.get("detail_1") or {}
            curl_link = detail_1.get("qqdocurl")
            if not curl_link:
                news = meta.get("news") or {}
                curl_link = news.get("jumpUrl")

        if not curl_link:
            json_str = (
                msg_data.get('data', '')
                if isinstance(msg_data, dict) else msg_data
            )
            if json_str and isinstance(json_str, str):
                message_data = json.loads(json_str)
                meta = message_data.get("meta") or {}
                detail_1 = meta.get("detail_1") or {}
                curl_link = detail_1.get("qqdocurl")
                if not curl_link:
                    news = meta.get("news") or {}
                    curl_link = news.get("jumpUrl")
        return curl_link
    except (AttributeError, KeyError, json.JSONDecodeError, TypeError):
        return None


# 从 JSON 卡片原文里通用扫描 http(s) 链接的正则：匹配到空白或 JSON 标点为止。
# 覆盖哔哩哔哩 QQ 小程序（miniapp）等「qqdocurl / news.jumpUrl 字段不存在、
# 但分享链接以明文嵌在 JSON 内」的卡片；命中后仍交给各平台解析器按域名认领，
# 因此 QQ 自己的域名（如 qq.com / qlogo.cn 图片 CDN）不会被误解析。
_CARD_RAW_URL_RE = re.compile(r"https?://[^\s\"'<>\\\]\[{}（）]+", re.IGNORECASE)
# 链接尾部常见的 JSON / 标点残留（正则无法用字符类表达的收尾字符）
_CARD_URL_TRAILING = ".,!?;:，。！？；：）】》」'\")"


def extract_urls_from_card_raw(msg_data) -> list:
    """从单个消息段的原始内容（JSON 卡片）中通用扫描全部 http(s) 链接。

    QQ 结构化卡片的字段结构随分享类型变化很大（文档卡片 qqdocurl、新闻卡片
    news.jumpUrl、哔哩哔哩等小程序卡片则把 b23.tv/直播链接内嵌在 JSON 其它字段）。
    与其逐一猜测字段，这里直接在序列化后的原始文本里扫描所有链接，再由各平台
    解析器按域名筛选：只有真正受支持的平台链接会被认领，其余自动忽略。

    Returns:
        去重、保序的链接字符串列表；无内容时为空列表。
    """
    try:
        raw = ""
        if isinstance(msg_data, dict):
            inner = msg_data.get("data")
            if isinstance(inner, str) and inner.strip():
                raw = inner
            elif msg_data:
                # 有些适配层把卡片 JSON 直接放在 dict 里（无 data 包装）
                raw = json.dumps(msg_data, ensure_ascii=False)
        elif isinstance(msg_data, str) and msg_data.strip():
            raw = msg_data
        if not raw:
            return []

        urls = []
        seen = set()
        for match in _CARD_RAW_URL_RE.finditer(raw):
            url = match.group(0).rstrip(_CARD_URL_TRAILING)
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
        return urls
    except Exception:
        return []


def build_request_headers(
    is_video: bool = False,
    referer: str = None,
    default_referer: str = None,
    origin: str = None,
    user_agent: str = None,
    custom_headers: dict = None
) -> dict:
    """构建请求头

    Args:
        is_video: 是否为视频（True为视频，False为图片）
        referer: Referer URL，如果提供则使用
        default_referer: 默认Referer URL（如果referer未提供）
        origin: Origin URL（可选）
        user_agent: User-Agent（可选，默认使用桌面端 User-Agent）
        custom_headers: 自定义请求头（如果提供，会与默认请求头合并）

    Returns:
        请求头字典
    """
    if custom_headers and 'Referer' in custom_headers:
        referer_url = custom_headers['Referer']
    else:
        referer_url = referer if referer else (default_referer or '')
    
    if user_agent:
        effective_user_agent = user_agent
    else:
        effective_user_agent = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
    
    default_accept_language = 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    
    if is_video:
        headers = {
            'User-Agent': effective_user_agent,
            'Accept': '*/*',
            'Accept-Language': default_accept_language,
            'Accept-Encoding': 'gzip, deflate',
        }
    else:
        headers = {
            'User-Agent': effective_user_agent,
            'Accept': (
                'image/avif,image/webp,image/apng,image/svg+xml,'
                'image/*,*/*;q=0.8'
            ),
            'Accept-Language': default_accept_language,
            'Accept-Encoding': 'gzip, deflate',
        }
    
    if referer_url:
        headers['Referer'] = referer_url
    
    if origin:
        headers['Origin'] = origin
    
    if custom_headers:
        headers.update(custom_headers)
    
    return headers

