"""链接提取/识别的离线单测：覆盖 Twitter/X 与 Steam 的 can_parse/extract_links。"""
import unittest

from . import support  # noqa: F401

from core.parser.platform.base import BaseVideoParser
from core.parser.platform.steam import SteamParser
from core.parser.platform.twitter import TwitterParser


def _make(parser_cls, **kwargs) -> BaseVideoParser:
    return parser_cls(**kwargs)


class TestTwitterRecognition(unittest.TestCase):
    def setUp(self):
        self.parser = _make(TwitterParser)

    def test_can_parse_status_links(self):
        for url in (
            "https://twitter.com/user/status/1234567890",
            "https://x.com/user/status/1234567890?s=20",
            "https://mobile.twitter.com/user/status/12345",
        ):
            self.assertTrue(self.parser.can_parse(url), url)

    def test_cannot_parse_non_tweet(self):
        for url in (
            "https://twitter.com/user",
            "https://example.com/x",
            "https://www.bilibili.com/video/BV1xx",
        ):
            self.assertFalse(self.parser.can_parse(url), url)

    def test_extract_links_dedup(self):
        text = (
            "看这个 https://twitter.com/a/status/111 "
            "和 https://x.com/a/status/111 还有 https://twitter.com/b/status/222"
        )
        links = self.parser.extract_links(text)
        ids = set()
        for link in links:
            self.assertTrue(self.parser.can_parse(link))
            ids.add(link)
        # 111 去重后只剩一个
        self.assertEqual(len([l for l in links if "111" in l]), 1)
        self.assertEqual(len([l for l in links if "222" in l]), 1)


class TestSteamRecognition(unittest.TestCase):
    def setUp(self):
        self.parser = _make(SteamParser)

    def test_can_parse_app_url(self):
        for url in (
            "https://store.steampowered.com/app/730/CS2/",
            "https://store.steampowered.com/app/320/",
        ):
            self.assertTrue(self.parser.can_parse(url), url)

    def test_extract_appid(self):
        self.assertEqual(
            self.parser._parse_appid("https://store.steampowered.com/app/730/CS2/"),
            "730",
        )


if __name__ == "__main__":
    unittest.main()
