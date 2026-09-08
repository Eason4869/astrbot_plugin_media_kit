"""链接提取/识别的离线单测：覆盖 Twitter/X、Steam、B站直播的 can_parse/extract_links。"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import support  # noqa: F401,E402

from core.parser.platform.base import BaseVideoParser  # noqa: E402
from core.parser.platform.bili_live import BiliLiveParser  # noqa: E402
from core.parser.platform.steam import SteamParser  # noqa: E402
from core.parser.platform.twitter import TwitterParser  # noqa: E402


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


class TestBiliLiveRecognition(unittest.TestCase):
    def setUp(self):
        self.parser = BiliLiveParser()

    def test_can_parse_room_url(self):
        for url in (
            "https://live.bilibili.com/21452505",
            "https://live.bilibili.com/h5/21452505",
            "http://live.bilibili.com/6?broadcast_type=0",
        ):
            self.assertTrue(self.parser.can_parse(url), url)

    def test_room_id_extracted(self):
        self.assertEqual(
            self.parser._parse_room_id("https://live.bilibili.com/21452505"),
            "21452505",
        )

    def test_extract_links_dedup_by_room(self):
        text = (
            "来玩 https://live.bilibili.com/21452505 "
            "和 https://live.bilibili.com/21452505?from=search"
        )
        links = self.parser.extract_links(text)
        self.assertEqual(len(links), 1, links)

    def test_bilibili_video_parser_does_not_claim_live(self):
        # B站视频解析器不应认领直播间链接，避免与直播解析器冲突
        from core.parser.platform.bilibili import BilibiliParser

        bilibili = BilibiliParser()
        self.assertFalse(
            bilibili.can_parse("https://live.bilibili.com/21452505")
        )


if __name__ == "__main__":
    unittest.main()
