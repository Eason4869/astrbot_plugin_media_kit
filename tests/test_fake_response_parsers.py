"""离线解析响应单测：验证 X(Twitter) 头像字段修复与 Steam 封面提取。"""
import unittest

from . import support  # noqa: F401

from core.parser.platform.steam import SteamParser
from core.parser.platform.twitter import TwitterParser


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


if __name__ == "__main__":
    unittest.main()
