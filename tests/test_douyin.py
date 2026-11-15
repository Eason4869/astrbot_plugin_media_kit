"""HTTP 风控时使用浏览器响应，仍须校验目标作品。"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from support import FakeResponse
from core.parser.platform.douyin import DouyinParser
from core.parser.platform.douyin_web import DouyinWebClient

ITEM_ID = "7707709905020505359"
SHORT_URL = "https://v.douyin.com/XNJd6x40Rrs/"
SHARE_URL = f"https://www.iesdouyin.com/share/video/{ITEM_ID}/"
PLAY_URL = "https://www.douyin.com/aweme/v1/play/?video_id=test_video"
ITEM = {
    "aweme_id": ITEM_ID,
    "desc": "赵老师《慌啥子嘛》录音棚完整版上线🎵",
    "author": {"nickname": "刘老根传媒", "unique_id": "llgcm"},
    "video": {"play_addr": {"uri": "test_video"}},
}


def share_html(complete=True):
    value = {"itemId": ITEM_ID}
    if complete:
        value["videoInfoRes"] = {"item_list": [ITEM]}
    return "<script>window._ROUTER_DATA = " + json.dumps({
        "loaderData": {"video_(id)/page": value}
    }) + ";</script>"


class HttpSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.share_requests = 0

    def post(self, url, **kwargs):
        return FakeResponse(status=503)

    def head(self, url, **kwargs):
        response = FakeResponse(status=302 if url == SHORT_URL else 200)
        response.headers = {"Location": SHARE_URL} if url == SHORT_URL else {}
        return response

    def get(self, url, **kwargs):
        if not url.startswith(SHARE_URL):
            raise AssertionError(f"unexpected URL: {url}")
        self.share_requests += 1
        if not self.responses:
            raise AssertionError("unexpected extra share request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class TestDouyinFallback(unittest.IsolatedAsyncioTestCase):
    def make_parser(self, payload=None):
        parser = DouyinParser()
        parser.browser_client = type("Browser", (), {})()
        parser.browser_client.fetch_detail = AsyncMock(return_value=(
            payload or {"aweme_detail": ITEM}, "Browser-UA"
        ))
        return parser

    async def test_captcha_falls_back_once_and_returns_media(self):
        parser = self.make_parser()
        session = HttpSession(FakeResponse(text_body="<title>验证中间页</title><script>window.TTGCaptcha.init({})</script>"))
        result = await parser.parse(session, SHORT_URL)
        self.assertEqual(result["video_urls"], [[PLAY_URL]])
        self.assertEqual(result["author"], "刘老根传媒(uid:llgcm)")
        self.assertEqual(result["video_headers"]["User-Agent"], "Browser-UA")
        self.assertEqual(session.share_requests, 1)
        parser.browser_client.fetch_detail.assert_awaited_once()

    async def test_complete_http_page_does_not_launch_browser(self):
        parser = self.make_parser()
        result = await parser.parse(HttpSession(FakeResponse(text_body=share_html())), SHORT_URL)
        self.assertEqual(result["video_urls"], [[PLAY_URL]])
        parser.browser_client.fetch_detail.assert_not_awaited()

    async def test_incomplete_ssr_is_retried_before_browser(self):
        parser = self.make_parser()
        session = HttpSession(FakeResponse(text_body=share_html(False)), FakeResponse(text_body=share_html()))
        result = await parser.parse(session, SHORT_URL)
        self.assertEqual(result["video_urls"], [[PLAY_URL]])
        self.assertEqual(session.share_requests, 2)
        parser.browser_client.fetch_detail.assert_not_awaited()

    async def test_valid_data_wins_over_embedded_captcha_script(self):
        parser = self.make_parser()
        html = share_html() + "<script>window.TTGCaptcha</script>"
        result = await parser.parse(HttpSession(FakeResponse(text_body=html)), SHORT_URL)
        self.assertEqual(result["video_urls"], [[PLAY_URL]])
        parser.browser_client.fetch_detail.assert_not_awaited()

    async def test_no_more_than_three_share_attempts(self):
        parser = self.make_parser()
        session = HttpSession(*[FakeResponse(text_body=share_html(False)) for _ in range(3)])
        result = await parser.parse(session, SHORT_URL)
        self.assertEqual(result["video_urls"], [[PLAY_URL]])
        self.assertEqual(session.share_requests, 3)

    async def test_wrong_browser_item_is_rejected(self):
        parser = self.make_parser({"aweme_detail": dict(ITEM, aweme_id="123")})
        with self.assertRaisesRegex(RuntimeError, "目标作品"):
            await parser.parse(HttpSession(FakeResponse(text_body="window.TTGCaptcha.init({})")), SHORT_URL)

    async def test_cancellation_is_not_retried(self):
        parser = self.make_parser()
        session = HttpSession(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await parser.parse(session, SHORT_URL)
        self.assertEqual(session.share_requests, 1)
        parser.browser_client.fetch_detail.assert_not_awaited()


class TestDouyinWebFailure(unittest.IsolatedAsyncioTestCase):
    async def test_argus_rejection_does_not_request_ttwid_refresh(self):
        class Session:
            def get(self, url, **kwargs):
                return FakeResponse(status=403, text_body="Blocked by ArgusSecurityPlugin Uifid Not Found")
        data, refresh = await DouyinWebClient()._request_once(Session(), ITEM_ID, "", "test-token")
        self.assertIsNone(data)
        self.assertFalse(refresh)


if __name__ == "__main__":
    unittest.main()
