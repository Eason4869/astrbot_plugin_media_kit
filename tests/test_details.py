"""Detail dispatch, configuration and separate link/shared user limits."""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
import support
from core.config_manager import ConfigManager
from core.parser.manager import ParserManager
from core.storage.parse_record import ParseRecordManager
from core.parser.platform.jd import JDParser
from core.rika_render.adapter import _parse_timestamp


class TestDetails(unittest.IsolatedAsyncioTestCase):
    def test_github_iso_timestamp_displays(self):
        self.assertEqual(_parse_timestamp("2026-11-17T00:00:00Z"), 1794873600)

    async def test_detail_dispatch_and_legacy_compatibility(self):
        parser = JDParser()
        parser.parse = AsyncMock(return_value={"title": "card"})
        parser.parse_detail = AsyncMock(return_value={"title": "details"})
        manager = ParserManager([parser])
        result = await manager.parse_text("", None, links_with_parser=[("url", parser)], detail=True)
        self.assertEqual(result[0]["title"], "details")
        parser.parse.assert_not_awaited()

    def test_optional_token_and_independent_proxies(self):
        cfg = ConfigManager({"proxy": {"address": "http://127.0.0.1:7890",
                                      "github": {"parse": True, "image": False}}})
        parser = next(p for p in cfg.create_parsers() if p.name == "github")
        self.assertEqual(parser.token, "")
        self.assertTrue(parser.use_parse_proxy)
        self.assertFalse(parser.use_image_proxy)
        self.assertEqual(parser.proxy_url, "http://127.0.0.1:7890")
        self.assertEqual(cfg.admin.detail_parse_keyword, "详细解析")
        self.assertTrue(cfg.github.summary_enabled)

    def test_command_conflict_keeps_existing_commands(self):
        cfg = ConfigManager({"admin": {"detail_parse_keyword": "强制解析"}})
        self.assertEqual(cfg.admin.detail_parse_keyword, "")
        self.assertEqual(cfg.admin.force_parse_keyword, "强制解析")

    def test_mode_limits_do_not_bypass_user_limit(self):
        parser = SimpleNamespace(name="github")
        links = [("https://github.com/a/b", parser)]
        manager = ParseRecordManager(same_link_max_count=1, same_link_window_seconds=3600,
                                     same_user_max_count=2, same_user_window_seconds=3600)
        self.assertEqual(len(manager.filter_links(links, user_key="u")[0]), 1)
        self.assertEqual(len(manager.filter_links(links, user_key="u", mode="detail")[0]), 1)
        self.assertEqual(len(manager.filter_links(links, user_key="v", mode="detail")[1]), 1)
        other = [("https://github.com/a/c", parser)]
        self.assertEqual(manager.filter_links(other, user_key="u")[0], [])
