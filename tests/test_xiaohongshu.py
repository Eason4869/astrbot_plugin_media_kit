"""小红书小程序短链安全落地页的离线回归测试。"""
import json
import os
import sys
import unittest
import asyncio
from unittest.mock import AsyncMock
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: F401,E402
from support import FakeResponse  # noqa: E402
from core.parser.platform.xiaohongshu import XiaohongshuParser  # noqa: E402


SHORT_URL = "http://xhslink.com/m/example"
NOTE_URL = (
    "http://www.xiaohongshu.com/discovery/item/6afe68f60000000023013c6b"
    "?xsec_token=abc%2Bdef%3D&xsec_source=app_share"
)
DESKTOP_URL = (
    "http://www.xiaohongshu.com/explore/6afe68f60000000023013c6b"
    "?xsec_token=abc%2Bdef%3D&xsec_source=app_share"
)
CAPTCHA_URL = "https://www.xiaohongshu.com/website-login/captcha?" + urlencode(
    {"redirectPath": NOTE_URL, "verifyType": "217"}
)


class TestRecoverNoteUrl(unittest.TestCase):
    def test_captcha_redirect_path_preserves_encoded_note_token(self):
        self.assertEqual(
            XiaohongshuParser._recover_original_note_url(CAPTCHA_URL), NOTE_URL
        )

    def test_captcha_partially_encoded_redirect_path(self):
        landing = (
            "https://www.xiaohongshu.com/website-login/captcha?redirectPath="
            "http://www.xiaohongshu.com/discovery/item/6afe68f60000000023013c6b"
            "?xsec_token%3Dabc%3D%26xsec_source%3Dapp_share&verifyType=217"
        )
        self.assertEqual(
            XiaohongshuParser._recover_original_note_url(landing),
            "http://www.xiaohongshu.com/discovery/item/6afe68f60000000023013c6b"
            "?xsec_token=abc=&xsec_source=app_share",
        )

    def test_existing_original_url_landing_still_recovers(self):
        landing = "https://www.xiaohongshu.com/404?" + urlencode(
            {"originalUrl": NOTE_URL}
        )
        self.assertEqual(
            XiaohongshuParser._recover_original_note_url(landing), NOTE_URL
        )

    def test_untrusted_redirect_paths_are_not_recovered(self):
        for target in (
            "https://example.com/note",
            "https://www.xiaohongshu.com.example.com/note",
            "https://xiaohongshu.com@127.0.0.1/note",
            "file:///etc/passwd",
            "//www.xiaohongshu.com/explore/note",
        ):
            with self.subTest(target=target):
                landing = "https://www.xiaohongshu.com/website-login/captcha?" + urlencode(
                    {"redirectPath": target}
                )
                self.assertEqual(
                    XiaohongshuParser._recover_original_note_url(landing), landing
                )


class HttpSession:
    def get(self, url, **kwargs):
        if url == SHORT_URL:
            response = FakeResponse(status=302)
            response.headers = {"Location": NOTE_URL}
        elif url == NOTE_URL:
            response = FakeResponse(status=302)
            response.headers = {"Location": CAPTCHA_URL}
        elif url == DESKTOP_URL:
            state = {"note": {"noteDetailMap": {"note": {"note": {
                "type": "normal",
                "title": "小程序卡片图文笔记",
                "user": {"nickname": "作者", "userId": "author"},
                "imageList": [{"urlDefault": "https://example.com/image.jpg"}],
            }}}}}
            response = FakeResponse(text_body=(
                "<script>window.__INITIAL_STATE__ = " + json.dumps(state) + "</script>"
            ))
        else:
            raise AssertionError(f"unexpected request: {url}")
        response.url = url
        return response


class TestMiniappRedirect(unittest.IsolatedAsyncioTestCase):
    async def test_captcha_landing_recovers_note_and_returns_media(self):
        result = await XiaohongshuParser().parse(HttpSession(), SHORT_URL)
        self.assertEqual(result["title"], "小程序卡片图文笔记")
        self.assertEqual(len(result["image_urls"]), 1)
        self.assertEqual(result["image_urls"][0][0], "https://example.com/image.jpg")
        self.assertEqual(result["url"], SHORT_URL)
        self.assertEqual(result["image_headers"]["Referer"], DESKTOP_URL)

    def browser_parser(self, error=None):
        parser = XiaohongshuParser()
        state = {"note": {"noteDetailMap": {"6afe68f60000000023013c6b": {"note": {
            "type": "normal", "title": "浏览器读取的目标笔记",
            "user": {"nickname": "作者", "userId": "author"},
            "imageList": [{"urlDefault": "https://example.com/browser.jpg"}],
        }}}}}
        parser.browser_client = type("Browser", (), {})()
        parser.browser_client.fetch_note = AsyncMock(return_value=(state, "Actual Browser UA"), side_effect=error)
        return parser

    async def test_http_login_page_falls_back_to_browser_and_returns_media(self):
        parser = self.browser_parser()
        session = LoginSession()
        try:
            result = await parser.parse(session, SHORT_URL)
        except RuntimeError as exc:
            self.fail(f"HTTP 登录页应通过浏览器回退取得作品，而不是失败: {exc}")
        self.assertEqual(result["title"], "浏览器读取的目标笔记")
        self.assertEqual(result["image_urls"][0][0], "https://example.com/browser.jpg")
        self.assertEqual(result["image_headers"]["User-Agent"], "Actual Browser UA")

    async def test_working_http_page_does_not_use_browser(self):
        parser = self.browser_parser()
        result = await parser.parse(HttpSession(), SHORT_URL)
        self.assertEqual(result["title"], "小程序卡片图文笔记")
        parser.browser_client.fetch_note.assert_not_awaited()

    async def test_missing_browser_error_remains_actionable(self):
        parser = self.browser_parser(RuntimeError("请安装 Chromium / Chrome / Edge"))
        with self.assertRaisesRegex(RuntimeError, "请安装 Chromium"):
            await parser.parse(LoginSession(), SHORT_URL)

    async def test_browser_cancellation_propagates(self):
        parser = self.browser_parser(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await parser.parse(LoginSession(), SHORT_URL)


class LoginSession(HttpSession):
    def get(self, url, **kwargs):
        if url == DESKTOP_URL:
            return FakeResponse(text_body='<title>你访问的页面不见了</title><script>window.__INITIAL_STATE__ = {"feed":{}}</script>')
        if url == CAPTCHA_URL:
            return FakeResponse(text_body='<title>小红书</title>')
        return super().get(url, **kwargs)


if __name__ == "__main__":
    unittest.main()
