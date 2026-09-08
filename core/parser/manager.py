"""解析管理器，维护解析器列表并按链接匹配。"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple

import aiohttp

from ..logger import logger

from .platform.base import BaseVideoParser
from .router import LinkRouter
from .utils import SkipParse


class ParserManager:
    """解析器管理器，按链接选择并调用具体平台解析器。"""

    def __init__(self, parsers: List[BaseVideoParser]):
        """初始化解析器管理器；空列表表示插件处于安全停用状态。"""
        self.parsers = list(parsers or [])
        self.link_router = LinkRouter(self.parsers)

    @staticmethod
    def _resolve_platform_name(
        parser: BaseVideoParser, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """按解析结果归一平台名。"""
        explicit = (metadata or {}).get("platform")
        return explicit or parser.name

    def _normalize_metadata(
        self, url: str, parser: BaseVideoParser, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """补齐解析结果的统一字段。"""
        platform = self._resolve_platform_name(parser, metadata)
        metadata["platform"] = platform
        metadata.setdefault("parser_name", parser.name)
        metadata.setdefault("source_url", url)
        metadata.setdefault("video_urls", [])
        metadata.setdefault("image_urls", [])
        metadata.setdefault("image_headers", {})
        metadata.setdefault("video_headers", {})
        return metadata

    @classmethod
    def _error_metadata(
        cls, url: str, parser: BaseVideoParser, error: str
    ) -> Dict[str, Any]:
        """构造单链接解析失败结果，供后续统一展示或调试。"""
        return {
            "url": url,
            "source_url": url,
            "error": error,
            "video_urls": [],
            "image_urls": [],
            "image_headers": {},
            "video_headers": {},
            "platform": cls._resolve_platform_name(parser),
            "parser_name": parser.name,
            "has_valid_media": False,
        }

    @staticmethod
    def _parser_can_parse(parser: BaseVideoParser, url: str) -> bool:
        """安全调用解析器的 can_parse；异常时视为不匹配。"""
        try:
            return bool(parser.can_parse(url))
        except Exception:
            logger.exception(
                f"解析器 {getattr(parser, 'name', '?')} 判断链接支持状态失败，已跳过"
            )
            return False

    async def _parse_with_fallback(
        self,
        primary: BaseVideoParser,
        session: aiohttp.ClientSession,
        url: str,
    ) -> Tuple[Optional[BaseVideoParser], Any]:
        """调用主解析器；主解析器 SkipParse 时按注册顺序回落到其它候选解析器。

        为了解决「b23.tv / 小程序卡片短链在提链阶段无法区分直播与视频」：
        直播解析器注册在视频解析器之前、优先认领并展开确认，若展开后并非直播
        （指向视频/动态）则抛 SkipParse，此时必须回落到 B站视频解析器，否则该
        短链会被静默丢弃。回落仅针对 SkipParse，且候选解析器必须 can_parse 该链接。

        Returns:
            (实际生效的解析器, parse 返回值)。所有解析器均 SkipParse 时，
            生效解析器为最后尝试的那个，返回值为最后抛出的 SkipParse 异常。
        """
        tried = set()
        parser: BaseVideoParser = primary
        last_skip: Optional[SkipParse] = None
        while parser is not None:
            tried.add(id(parser))
            try:
                result = await parser.parse(session, url)
                return parser, result
            except SkipParse as skip:
                logger.debug(
                    f"解析器 {getattr(parser, 'name', '?')} 跳过 {url}: {skip}，尝试回落"
                )
                last_skip = skip
                fallback = None
                for candidate in self.parsers:
                    if id(candidate) in tried:
                        continue
                    if self._parser_can_parse(candidate, url):
                        fallback = candidate
                        break
                parser = fallback
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                # 当前尝试的解析器抛出真实错误（非 SkipParse）：归因到该解析器
                return parser, exc
        return primary, last_skip

    def find_parser(self, url: str) -> Optional[BaseVideoParser]:
        """根据URL查找合适的解析器

        Args:
            url: 视频链接

        Returns:
            匹配的解析器实例，未找到时为None
        """
        try:
            return self.link_router.find_parser(url)
        except ValueError:
            return None

    def extract_all_links(self, text: str) -> List[Tuple[str, BaseVideoParser]]:
        """从文本中提取所有可解析的链接

        Args:
            text: 输入文本

        Returns:
            包含(链接, 解析器)元组的列表。原文可定位项按出现位置排序，
            解析器规范化后无法定位的链接按提取顺序保留在其后。
        """
        return self.link_router.extract_links_with_parser(text)

    async def parse_text(
        self,
        text: str,
        session: aiohttp.ClientSession,
        links_with_parser: Optional[List[Tuple[str, BaseVideoParser]]] = None,
    ) -> List[Dict[str, Any]]:
        """解析文本中的所有链接

        Args:
            text: 输入文本
            session: aiohttp会话
            links_with_parser: 预先提取好的链接与解析器列表（可选）

        Returns:
            解析结果字典列表（元数据列表）
        """
        if links_with_parser is None:
            links_with_parser = self.extract_all_links(text)
        if not links_with_parser:
            logger.debug("未提取到任何可解析链接")
            return []
        unique_links = {link: parser for link, parser in links_with_parser}
        logger.debug(f"需要解析 {len(unique_links)} 个链接")

        async def _parse_route(url: str, primary: BaseVideoParser):
            """解析单链接，返回 (最终生效解析器, 结果或异常)。

            用 gather 的 return_exceptions 兜底未预期错误；SkipParse 的回落
            已在 _parse_with_fallback 内部完成，这里仅透传。
            """
            try:
                effective, result = await self._parse_with_fallback(primary, session, url)
                return effective, result
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # 未预期错误：按绑定解析器归因
                return primary, exc

        tasks = [
            _parse_route(url, parser) for url, parser in unique_links.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        metadata_list = []
        link_items = list(unique_links.items())
        for i, routed in enumerate(results):
            url, bound_parser = link_items[i]
            if isinstance(routed, asyncio.CancelledError):
                raise routed
            if isinstance(routed, BaseException):
                # gather 级别的未预期异常（理论上不发生），按绑定解析器报错
                logger.error(f"解析URL失败: {url}, 错误: {routed}")
                metadata_list.append(self._error_metadata(url, bound_parser, str(routed)))
                continue
            parser, result = routed
            if isinstance(result, SkipParse):
                # 主解析器与所有回落解析器均跳过（如所有候选都不认领）
                logger.debug(f"跳过解析: {url}, 原因: {result}")
                continue
            if isinstance(result, BaseException):
                logger.error(f"解析URL失败: {url}, 错误: {result}")
                metadata_list.append(self._error_metadata(url, parser, str(result)))
            elif result is None:
                continue
            elif not isinstance(result, dict):
                error = (
                    "解析器返回了无效结果类型: "
                    f"{type(result).__name__}（应为 dict 或 None）"
                )
                logger.error(f"解析URL失败: {url}, 错误: {error}")
                metadata_list.append(self._error_metadata(url, parser, error))
            elif result:
                metadata_list.append(self._normalize_metadata(url, parser, result))
        logger.debug(f"解析完成，获得 {len(metadata_list)} 条元数据")
        return metadata_list
