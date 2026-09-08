"""离线解析响应单测：验证 X(Twitter) 头像字段修复与 Steam/B站直播封面提取。"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import support  # noqa: F401,E402

from core.parser.platform.bili_live import BiliLiveParser  # noqa: E402
from core.parser.platform.steam import SteamParser  # noqa: E402
from core.parser.platform.twitter import TwitterParser  # noqa: E402


def _make_parser(cls, **kwargs):
    return cls(**kwargs)


class TestTwitterFxtwitterParse(unittest.TestCase):
    def setUp(self):
        self.parser = _make_parser(TwitterParser)

    def test_parse_with_avatar_and_media(self):
        payload = {
            "tweet": {
                "id": "1001",
                "url": "https://twitter.com/hoge/status/1001",
                "text": "hello world",
                "created_at": "Mon Sep 07 12:34:56 +0800 2026",
                "author": {
                    "name": "Hoge",
                    "screen_name": "hoge",
                    "avatar": "https://pbs.twimg.com/avatar.jpg",
                },
                "media": {
                    "photos": [{"url": "https://pbs.twimg.com/p1.jpg"}],
                    "videos": [{"url": "https://video.twimg.com/v1.mp4",
                                "thumbnail_url": "https://pbs.twimg.com/v1.jpg",
                                "duration": 12}],
                },
            }
        }
        result = self.parser._parse_fxtwitter_response(payload, "1001")
        self.assertEqual(result["title"], "Hoge(@hoge) 的推文")
        self.assertTrue(
            result["avatar_url"].startswith("https://"),
            f"avatar_url 应被提取: {result['avatar_url']!r}",
        )
        self.assertEqual(result["images"], ["https://pbs.twimg.com/p1.jpg"])
        self.assertEqual(len(result["videos"]), 1)

    def test_wrong_tweet_id_raises(self):
        payload = {"tweet": {"id": "999", "url": "https://x.com/a/status/999"}}
        from core.parser.platform.twitter import FxTwitterTweetUnavailableError

        with self.assertRaises(FxTwitterTweetUnavailableError):
            self.parser._parse_fxtwitter_response(payload, "1001")


class TestTwitterGraphqlParse(unittest.TestCase):
    def setUp(self):
        self.parser = _make_parser(TwitterParser)

    def test_graphql_avatar_url_extracted(self):
        payload = {
            "data": {
                "tweetResult": {
                    "result": {
                        "rest_id": "42",
                        "core": {
                            "user_results": {
                                "result": {
                                    "legacy": {
                                        "screen_name": "alice",
                                        "name": "Alice",
                                        "profile_image_url_https":
                                            "https://pbs.twimg.com/a.jpg",
                                    }
                                }
                            }
                        },
                        "legacy": {
                            "id_str": "42",
                            "full_text": "a photo tweet",
                            "created_at": "Mon Sep 07 12:34:56 +0800 2026",
                            "extended_entities": {
                                "media": [
                                    {
                                        "type": "photo",
                                        "media_url_https":
                                            "https://pbs.twimg.com/m1.jpg",
                                    }
                                ]
                            },
                        },
                    }
                }
            }
        }
        result = self.parser._parse_graphql_response(payload, "42")
        self.assertIn("alice", result["title"])
        self.assertTrue(
            result["avatar_url"].startswith("https://"),
            f"GraphQL avatar_url 缺失: {result['avatar_url']!r}",
        )
        self.assertEqual(len(result["images"]), 1)


class TestSteamCoverExtraction(unittest.TestCase):
    def setUp(self):
        self.parser = _make_parser(SteamParser)

    def test_cover_is_header_image(self):
        video_urls, covers, images, game_cover = self.parser._extract_media(
            {
                "header_image": "https://cdn.akamai.steamstatic.com/header.jpg",
                "screenshots": [],
                "movies": [],
            }
        )
        self.assertEqual(
            game_cover, "https://cdn.akamai.steamstatic.com/header.jpg"
        )
        self.assertEqual(video_urls, [])
        self.assertEqual(covers, [])


class _FakeLiveResponse:
    def __init__(self, payload=None, text_body=""):
        self.status = 200
        self._payload = payload
        self._text = text_body

    def raise_for_status(self):
        return None

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeLiveSession:
    """按 URL 分发：get_info 返回 JSON，房间页返回内嵌 JSON 的 HTML。"""

    def __init__(self, room_info):
        self._room_info = room_info

    def get(self, url, **kwargs):
        if "Room/get_info" in url:
            return _FakeLiveResponse(payload=self._room_info)
        # 页面内嵌 JSON：uname / face（正斜杠，生产代码兼容 \/ 与 //）
        page = (
            '<html><script>{"info":{"uname":"主播A"},'
            '"base_info":{"face":"https://i0.hdslb.com/face.jpg"}}'
            "</script></html>"
        )
        return _FakeLiveResponse(text_body=page)


class TestBiliLiveParse(unittest.IsolatedAsyncioTestCase):
    async def test_card_only_metadata_with_cover(self):
        parser = BiliLiveParser()
        room_info = {
            "code": 0,
            "data": {
                "title": "今晚打游戏",
                "user_cover": "//i0.hdslb.com/live_cover.jpg",
                "live_status": 1,
                "area_name": "单机游戏",
                "online": 12345,
                "live_time": "2026-09-08 20:00:00",
                "description": "<p>欢迎来到直播间&nbsp;!</p>",
            },
        }
        session = _FakeLiveSession(room_info)
        meta = await parser.parse(session, "https://live.bilibili.com/21452505")
        self.assertEqual(meta["platform"], "live")
        self.assertTrue(meta["is_live"])
        # 封面补全协议头
        self.assertTrue(meta["cover_url"].startswith("https://"))
        # 仅卡片：无任何可下载媒体
        self.assertEqual(meta["video_urls"], [])
        self.assertEqual(meta["image_urls"], [])
        self.assertTrue(meta["card_cover_urls"])
        self.assertIn("主播A", meta["author"])
        self.assertIn("直播中", meta["desc"])


if __name__ == "__main__":
    unittest.main()
