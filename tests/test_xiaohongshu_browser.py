"""XHS browser fallback: target binding, navigation safety and lifecycle bounds."""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support  # noqa: F401,E402
from core.parser.platform.xiaohongshu_browser import XiaohongshuBrowserClient  # noqa: E402

NOTE = "6afe68f60000000023013c6b"
URL = f"https://www.xiaohongshu.com/explore/{NOTE}?xsec_token=abc%2Bdef%3D"


def page_message(command_id, *, url=URL, note_id=NOTE, title="目标作品"):
    return {"id": command_id, "result": {"result": {"value": json.dumps({
        "url":url, "user_agent":"Actual Browser", "state":{
            "note":{"noteDetailMap":{note_id:{"note":{"noteId":note_id,"title":title}}}}
        }
    })}}}


class WebSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    async def receive_json(self):
        return next(self.messages)

    async def send_json(self, message):
        self.sent.append(message)


class TestXhsBrowser(unittest.IsolatedAsyncioTestCase):
    async def test_returns_target_state_and_actual_browser_user_agent(self):
        state, ua = await XiaohongshuBrowserClient()._read_detail(WebSocket([page_message(100)]), URL)
        self.assertEqual(state["note"]["noteDetailMap"][NOTE]["note"]["title"], "目标作品")
        self.assertEqual(ua, "Actual Browser")

    async def test_unrelated_note_is_ignored_until_target_arrives(self):
        ws = WebSocket([page_message(100, note_id="0"*24), page_message(101)])
        state, _ = await XiaohongshuBrowserClient()._read_detail(ws, URL)
        self.assertIn(NOTE, state["note"]["noteDetailMap"])

    async def test_wrong_browser_page_cannot_supply_note_data(self):
        ws = WebSocket([page_message(100, url=URL.replace("www.xiaohongshu.com","example.com")), page_message(101)])
        state, _ = await XiaohongshuBrowserClient()._read_detail(ws, URL)
        self.assertIn(NOTE, state["note"]["noteDetailMap"])

    async def test_unrelated_mobile_state_cannot_override_target_desktop_note(self):
        from core.parser.platform.xiaohongshu import XiaohongshuParser
        message = page_message(100)
        page = json.loads(message["result"]["result"]["value"])
        page["state"]["noteData"] = {"data":{"noteData":{
            "noteId":"0"*24,"title":"另一篇作品","user":{"nickname":"其他作者"}
        }}}
        target = page["state"]["note"]["noteDetailMap"][NOTE]["note"]
        target.update({"user":{"nickname":"目标作者"},"imageList":[{"urlDefault":"https://example.com/target.jpg"}]})
        message["result"]["result"]["value"] = json.dumps(page)
        state, _ = await XiaohongshuBrowserClient()._read_detail(WebSocket([message]), URL)
        result = XiaohongshuParser()._parse_note_data(state, URL)
        self.assertEqual(result["title"],"目标作品")
        self.assertEqual(result["author_name"],"目标作者")

    async def test_verification_page_reports_human_action(self):
        ws = WebSocket([page_message(100, url="https://www.xiaohongshu.com/website-login/captcha")])
        with self.assertRaisesRegex(RuntimeError, "人工验证"):
            await XiaohongshuBrowserClient()._read_detail(ws, URL)

    async def test_invalid_navigation_urls_are_rejected_before_launch(self):
        for url in ("https://example.com/explore/"+NOTE, "https://www.xiaohongshu.com/login", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                await XiaohongshuBrowserClient().fetch_note(url)

    async def test_timeout_cancels_browser_operation(self):
        closed = asyncio.Event()
        async def slow(*args):
            try:
                await asyncio.Future()
            finally:
                closed.set()
        client = XiaohongshuBrowserClient(timeout=.02)
        with patch.object(client, "_find_executable", return_value="browser"), patch.object(client,"_launch_and_read",side_effect=slow):
            with self.assertRaisesRegex(RuntimeError,"超时"):
                await client.fetch_note(URL)
        self.assertTrue(closed.is_set())

    async def test_document_redirect_to_untrusted_host_is_blocked(self):
        ws = WebSocket([])
        await XiaohongshuBrowserClient._route_navigation(ws, {
            "requestId":"nav", "request":{"url":"http://127.0.0.1/private"}
        }, 900)
        self.assertEqual(ws.sent[0]["method"], "Fetch.failRequest")

    async def test_interception_error_aborts_browser_setup(self):
        ws = WebSocket([{"id":4,"error":{"message":"Fetch domain unavailable"}}])
        with self.assertRaisesRegex(RuntimeError,"导航拦截"):
            await XiaohongshuBrowserClient()._configure_page(ws)

    async def test_interception_ack_is_checked_before_navigation(self):
        ws = WebSocket([{"id":1,"result":{}},{"id":4,"result":{}}])
        await XiaohongshuBrowserClient()._configure_page(ws)
        self.assertEqual(ws.sent[-1]["method"],"Fetch.enable")

    async def test_https_upgrade_keeps_signed_query_unchanged(self):
        client = XiaohongshuBrowserClient()
        launch = AsyncMock(return_value=({}, "UA"))
        with patch.object(client,"_find_executable",return_value="browser"), patch.object(client,"_launch_and_read",launch):
            await client.fetch_note(URL.replace("https://","http://",1))
        self.assertEqual(launch.await_args.args[1], URL)
