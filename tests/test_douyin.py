"""抖音分享页偶发缺失 videoInfoRes 时应有界重试。"""
import asyncio
import json
import os
import sys
import unittest

import aiohttp

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from support import FakeResponse  # noqa: E402
from core.parser.platform.douyin import DouyinParser  # noqa: E402

ITEM_ID = "7707709905020505359"
SHORT_URL = "https://v.douyin.com/XNJd6x40Rrs/"
SHARE_URL = f"https://www.iesdouyin.com/share/video/{ITEM_ID}/"
PLAY_URL = "https://www.douyin.com/aweme/v1/play/?video_id=test_video"


def share_page(*, item_id=ITEM_ID, complete=True):
    # 保留线上失败页的路由和 itemId，失败页唯独没有 videoInfoRes。
    loader = {"itemId": ITEM_ID, "renderInSSR": 1}
    if complete:
        loader["videoInfoRes"] = {
            "status_code": 0,
            "item_list": [{
                "aweme_id": item_id,
                "desc": "赵老师《慌啥子嘛》录音棚完整版上线🎵",
                "author": {"nickname": "刘老根传媒", "unique_id": "llgcm"},
                "video": {"play_addr": {"uri": "test_video"}},
            }],
        }
    data = {"loaderData": {"video_layout": None, "video_(id)/page": loader}}
    return "<script>window._ROUTER_DATA = " + json.dumps(data) + ";</script>"


class ShareSession:
    """只替换 HTTP 边界；签名接口不可用，分享页按顺序返回真实结构。"""
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
        if url != SHARE_URL:
            raise AssertionError(f"unexpected URL: {url}")
        self.share_requests += 1
        if not self.responses:
            raise AssertionError("share retry budget exceeded")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class TestDouyinShareRetry(unittest.IsolatedAsyncioTestCase):
    async def test_short_link_recovers_from_missing_video_info(self):
        session = ShareSession(
            FakeResponse(text_body=share_page(complete=False)),
            FakeResponse(text_body=share_page()),
        )
        result = await DouyinParser().parse(session, SHORT_URL)
        self.assertEqual(result["video_urls"], [[PLAY_URL]])
        self.assertEqual(result["author"], "刘老根传媒(uid:llgcm)")
        self.assertIn("慌啥子嘛", result["title"])
        self.assertEqual(session.share_requests, 2)

    async def test_complete_page_needs_no_retry(self):
        session = ShareSession(FakeResponse(text_body=share_page()))
        result = await DouyinParser().parse(session, SHORT_URL)
        self.assertEqual(result["video_urls"], [[PLAY_URL]])
        self.assertEqual(session.share_requests, 1)

    async def test_missing_data_stops_after_three_attempts(self):
        session = ShareSession(*[
            FakeResponse(text_body=share_page(complete=False)) for _ in range(3)
        ])
        result = await DouyinParser().fetch_douyin_info(session, ITEM_ID)
        self.assertIsNone(result)
        self.assertEqual(session.share_requests, 3)

    async def test_transient_network_and_server_errors_recover(self):
        session = ShareSession(
            aiohttp.ClientConnectionError("connection reset"),
            FakeResponse(status=503),
            FakeResponse(text_body=share_page()),
        )
        result = await DouyinParser().fetch_douyin_info(session, ITEM_ID)
        self.assertEqual(result["video_url_list"], [PLAY_URL])
        self.assertEqual(session.share_requests, 3)

    async def test_permanent_http_error_is_not_retried(self):
        session = ShareSession(FakeResponse(status=404))
        result = await DouyinParser().fetch_douyin_info(session, ITEM_ID)
        self.assertIsNone(result)
        self.assertEqual(session.share_requests, 1)

    async def test_wrong_item_is_never_returned(self):
        session = ShareSession(*[
            FakeResponse(text_body=share_page(item_id="123")) for _ in range(3)
        ])
        result = await DouyinParser().fetch_douyin_info(session, ITEM_ID)
        self.assertIsNone(result)
        self.assertEqual(session.share_requests, 3)

    async def test_cancellation_propagates_without_retry(self):
        session = ShareSession(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await DouyinParser().fetch_douyin_info(session, ITEM_ID)
        self.assertEqual(session.share_requests, 1)


if __name__ == "__main__":
    unittest.main()
