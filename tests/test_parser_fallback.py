# -*- coding: utf-8 -*-
"""SkipParse 回落 与 JSON 小程序卡片链接扫描的离线单测。

复现 v1.1.1-beta 修复的问题：b23.tv 短链 / QQ 小程序卡片在提链阶段无法区分
直播与视频，直播解析器优先认领后若确认非直播，必须回落到能解析该链接的
平台解析器（否则普通视频短链被静默丢弃）。
"""
import asyncio
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import support  # noqa: F401,E402

from core.parser.manager import ParserManager  # noqa: E402
from core.parser.platform.base import BaseVideoParser  # noqa: E402
from core.parser.utils import (  # noqa: E402
    SkipParse,
    extract_urls_from_card_raw,
    recall_expanded_url,
    remember_expanded_url,
)


class _FakeParser(BaseVideoParser):
    """可控解析器：can_parse 集合决定认领，parse 可抛 SkipParse 或返回 dict。"""

    def __init__(self, name, can_parse_urls, skip_urls=None, result=None):
        super().__init__(name)
        self._can = set(can_parse_urls or [])
        self._skip = set(skip_urls or [])
        self._result = result or {"platform": name, "video_urls": [], "image_urls": []}
        self.parse_calls = []

    def can_parse(self, url: str) -> bool:
        return url in self._can

    def extract_links(self, text: str):
        return []

    async def parse(self, session, url: str):
        self.parse_calls.append(url)
        if url in self._skip:
            raise SkipParse(f"{self.name} 不解析 {url}")
        return dict(self._result)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


class TestSkipParseFallback(unittest.TestCase):
    def test_primary_skip_falls_back_to_next_parser(self):
        # live 认领 b23 并 SkipParse；bilibili 也认领且能解析 -> 回落成功
        live = _FakeParser("live", can_parse_urls={"b23"}, skip_urls={"b23"})
        bili = _FakeParser(
            "bilibili",
            can_parse_urls={"b23"},
            result={"platform": "bilibili", "title": "视频", "video_urls": [["v"]], "image_urls": []},
        )
        pm = ParserManager([live, bili])
        metas = _run(pm.parse_text("", None, links_with_parser=[("b23", live)]))
        self.assertEqual(len(metas), 1)
        # 实际归因到回落的 bilibili
        self.assertEqual(metas[0]["platform"], "bilibili")
        self.assertEqual(metas[0]["parser_name"], "bilibili")
        self.assertIn("b23", live.parse_calls)
        self.assertIn("b23", bili.parse_calls)

    def test_primary_success_no_fallback(self):
        live = _FakeParser(
            "live",
            can_parse_urls={"live"},
            result={"platform": "live", "is_live": True, "card_cover_urls": [["c"]],
                    "video_urls": [], "image_urls": []},
        )
        bili = _FakeParser("bilibili", can_parse_urls=set())
        pm = ParserManager([live, bili])
        metas = _run(pm.parse_text("", None, links_with_parser=[("live", live)]))
        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0]["platform"], "live")
        self.assertEqual(bili.parse_calls, [])

    def test_all_skip_drops_link_silently(self):
        # 两个解析器都 SkipParse -> 该链接被跳过，不产生错误元数据
        live = _FakeParser("live", can_parse_urls={"x"}, skip_urls={"x"})
        bili = _FakeParser("bilibili", can_parse_urls={"x"}, skip_urls={"x"})
        pm = ParserManager([live, bili])
        metas = _run(pm.parse_text("", None, links_with_parser=[("x", live)]))
        self.assertEqual(metas, [])

    def test_fallback_skips_parser_that_cannot_parse(self):
        # 回落时不允许选中 can_parse=False 的解析器
        live = _FakeParser("live", can_parse_urls={"u"}, skip_urls={"u"})
        other = _FakeParser("other", can_parse_urls=set())
        bili = _FakeParser(
            "bilibili",
            can_parse_urls={"u"},
            result={"platform": "bilibili", "video_urls": [["v"]], "image_urls": []},
        )
        pm = ParserManager([live, other, bili])
        metas = _run(pm.parse_text("", None, links_with_parser=[("u", live)]))
        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0]["platform"], "bilibili")
        self.assertEqual(other.parse_calls, [])

    def test_fallback_error_attributed_to_effective_parser(self):
        # 回落到的解析器抛真实错误时，错误归因到该解析器
        live = _FakeParser("live", can_parse_urls={"u"}, skip_urls={"u"})

        class _BoomParser(_FakeParser):
            async def parse(self, session, url):
                self.parse_calls.append(url)
                raise RuntimeError("boom")

        boom = _BoomParser("bilibili", can_parse_urls={"u"})
        pm = ParserManager([live, boom])
        metas = _run(pm.parse_text("", None, links_with_parser=[("u", live)]))
        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0]["parser_name"], "bilibili")
        self.assertIn("boom", metas[0]["error"])


class TestCardRawUrlExtraction(unittest.TestCase):
    def test_miniapp_card_with_embedded_b23(self):
        # 哔哩哔哩 QQ 小程序卡片：链接内嵌在 JSON，不在 qqdocurl/news.jumpUrl
        card = {"prompt": "[QQ小程序]哔哩哔哩", "url": "https://b23.tv/qFO2a5Q",
                "meta": {"miniapp": {"avatar": "https://q.qlogo.cn/a/100"}}}
        seg = {"data": json.dumps(card, ensure_ascii=False)}
        urls = extract_urls_from_card_raw(seg)
        self.assertIn("https://b23.tv/qFO2a5Q", urls)

    def test_trailing_punctuation_stripped(self):
        seg = {"data": '{"a":"https://b23.tv/abc,","b":"https://live.bilibili.com/1)"}'}
        urls = extract_urls_from_card_raw(seg)
        self.assertIn("https://b23.tv/abc", urls)
        self.assertIn("https://live.bilibili.com/1", urls)

    def test_dedup_preserves_order(self):
        seg = {"data": "https://b23.tv/x https://b23.tv/x https://b23.tv/y"}
        urls = extract_urls_from_card_raw(seg)
        self.assertEqual(urls, ["https://b23.tv/x", "https://b23.tv/y"])

    def test_empty_and_nonstring(self):
        self.assertEqual(extract_urls_from_card_raw(None), [])
        self.assertEqual(extract_urls_from_card_raw({"data": ""}), [])
        self.assertEqual(extract_urls_from_card_raw({"data": 123}), [])

    def test_dict_without_data_wrapper(self):
        # 适配层直接把卡片 dict 传入（无 data 包装）也能扫描
        card = {"url": "https://b23.tv/z"}
        urls = extract_urls_from_card_raw(card)
        self.assertIn("https://b23.tv/z", urls)


class _TimeoutSession:
    """模拟 b23 请求超时（asyncio.TimeoutError 的 str() 为空）。"""

    def get(self, *args, **kwargs):
        class _CM:
            async def __aenter__(self_inner):
                raise asyncio.TimeoutError()

            async def __aexit__(self_inner, *exc):
                return False

        return _CM()


class TestBiliLiveB23Hardening(unittest.TestCase):
    def setUp(self):
        from core.parser.platform.bili_live import BiliLiveParser

        self.parser = BiliLiveParser()

    def test_expand_network_timeout_becomes_skip(self):
        # 展开期网络超时必须转成 SkipParse（让解析管理器回落），不能是硬错误
        with self.assertRaises(SkipParse):
            asyncio.run(
                self.parser._expand_b23_to_live(
                    _TimeoutSession(), "https://b23.tv/toOIjEI"
                )
            )

    def test_parse_video_b23_falls_back_when_expand_times_out(self):
        # 直播解析器展开超时抛 SkipParse -> 回落的视频解析器接管并成功
        calls = {"n": 0}

        class _TimeoutLive(_FakeParser):
            async def parse(self, session, url):
                calls["live"] = True
                raise SkipParse("b23 短链展开失败，交给视频解析器重试: TimeoutError")

        live = _TimeoutLive(
            "live",
            can_parse_urls={"https://b23.tv/x"},
            result={"platform": "live", "video_urls": [], "image_urls": []},
        )
        bili = _FakeParser(
            "bilibili",
            can_parse_urls={"https://b23.tv/x"},
            result={"platform": "bilibili", "title": "v",
                    "video_urls": [["v"]], "image_urls": []},
        )
        pm = ParserManager([live, bili])
        metas = asyncio.run(
            pm.parse_text("", None, links_with_parser=[("https://b23.tv/x", live)])
        )
        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0]["platform"], "bilibili")


class TestB23ExpandCache(unittest.TestCase):
    def test_remember_and_recall_on_fake_session(self):
        class _S:
            pass

        s = _S()
        self.assertIsNone(recall_expanded_url(s, "https://b23.tv/a"))
        remember_expanded_url(s, "https://b23.tv/a",
                              "https://www.bilibili.com/video/BV1xx")
        self.assertEqual(
            recall_expanded_url(s, "https://b23.tv/a"),
            "https://www.bilibili.com/video/BV1xx",
        )

    def test_cache_helpers_tolerate_bad_inputs(self):
        # None session / 空值 / 不可设属性的对象都不应抛错
        remember_expanded_url(None, "u", "v")
        remember_expanded_url(object(), "u", "v")  # 无 __dict__ 的普通 object
        remember_expanded_url(object(), "", "v")
        self.assertIsNone(recall_expanded_url(None, "u"))
        self.assertIsNone(recall_expanded_url(object(), "u"))


if __name__ == "__main__":
    unittest.main()
