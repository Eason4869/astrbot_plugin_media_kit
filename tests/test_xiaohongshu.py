"""小红书小程序短链安全落地页的离线回归测试。"""
import json
import os
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
