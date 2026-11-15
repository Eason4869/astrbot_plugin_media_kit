import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))
import support
from core.parser.platform.douyin_browser import DouyinBrowserClient
from core.parser.platform import douyin_browser

ITEM_ID = "7707709905020505359"


class WebSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    async def receive_json(self):
        return next(self.messages)

    async def send_json(self, message):
        self.sent.append(message)


def detail_messages(host="www.douyin.com", item_id=ITEM_ID, body=None, response_id=4):
    return [
        {"method": "Network.responseReceived", "params": {
            "requestId": "detail", "response": {"status": 200,
                "url": f"https://{host}/aweme/v1/web/aweme/detail/?aweme_id={item_id}"}}},
        {"method": "Network.loadingFinished", "params": {"requestId": "detail"}},
        {"id": response_id, "result": {"body": body or json.dumps({
            "aweme_detail": {"aweme_id": item_id, "desc": "target", "video": {}}
        })}},
    ]


class TestBrowserResponse(unittest.IsolatedAsyncioTestCase):
    async def test_site_response_is_returned_with_actual_browser_user_agent(self):
        ws = WebSocket([{"id": 3, "result": {"userAgent": "Actual Browser"}}] + detail_messages())
        data, user_agent = await DouyinBrowserClient._read_detail(ws, ITEM_ID)
        self.assertEqual(data["aweme_detail"]["aweme_id"], ITEM_ID)
        self.assertEqual(user_agent, "Actual Browser")

    async def test_wrong_payload_id_is_ignored_until_target_arrives(self):
        wrong = json.dumps({"aweme_detail": {"aweme_id": "999"}})
        ws = WebSocket(detail_messages(body=wrong) + detail_messages(response_id=5))
        data, _ = await DouyinBrowserClient._read_detail(ws, ITEM_ID)
        self.assertEqual(data["aweme_detail"]["desc"], "target")

    async def test_wrong_host_is_not_read(self):
        ws = WebSocket(detail_messages(host="douyin.com.evil.test")[:2] + detail_messages())
        data, _ = await DouyinBrowserClient._read_detail(ws, ITEM_ID)
        self.assertEqual(data["aweme_detail"]["aweme_id"], ITEM_ID)
        self.assertEqual(len(ws.sent), 1)

    async def test_malformed_json_is_ignored(self):
        ws = WebSocket(detail_messages(body="{broken}") + detail_messages(response_id=5))
        data, _ = await DouyinBrowserClient._read_detail(ws, ITEM_ID)
        self.assertEqual(data["aweme_detail"]["aweme_id"], ITEM_ID)

    async def test_missing_browser_has_actionable_error(self):
        with patch.object(DouyinBrowserClient, "_find_executable", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Chromium"):
                await DouyinBrowserClient().fetch_detail(ITEM_ID)

    async def test_disabled_fallback_never_starts_a_process(self):
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as launch:
            with self.assertRaisesRegex(RuntimeError, "已关闭"):
                await DouyinBrowserClient(enabled=False).fetch_detail(ITEM_ID)
            launch.assert_not_awaited()

    async def test_invalid_id_is_rejected_before_launch(self):
        with self.assertRaises(ValueError):
            await DouyinBrowserClient().fetch_detail("../other")

    async def test_timeout_cancels_the_browser_operation(self):
        closed = asyncio.Event()
        async def slow(*args):
            try:
                await asyncio.Future()
            finally:
                closed.set()
        client = DouyinBrowserClient(timeout=0.02)
        with patch.object(client, "_find_executable", return_value="browser"), \
             patch.object(client, "_launch_and_read", side_effect=slow):
            with self.assertRaisesRegex(RuntimeError, "验证"):
                await client.fetch_detail(ITEM_ID)
        self.assertTrue(closed.is_set())

    async def test_cancellation_propagates_and_releases_serial_slot(self):
        entered = asyncio.Event()
        closed = asyncio.Event()
        async def slow(*args):
            try:
                entered.set()
                await asyncio.Future()
            finally:
                closed.set()
        client = DouyinBrowserClient()
        with patch.object(client, "_find_executable", return_value="browser"), \
             patch.object(client, "_launch_and_read", side_effect=slow):
            task = asyncio.create_task(client.fetch_detail(ITEM_ID))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(closed.is_set())
        self.assertFalse(client._lock.locked())

    async def test_browser_close_is_requested_before_waiting_for_exit(self):
        process = type("Process", (), {"returncode": None, "wait": AsyncMock(return_value=0)})()
        ws = AsyncMock()
        connection = AsyncMock()
        connection.__aenter__.return_value = ws
        session = type("Session", (), {"ws_connect": lambda self, *args: connection})()
        context = AsyncMock()
        context.__aenter__.return_value = session
        with patch.object(douyin_browser.aiohttp, "ClientSession", return_value=context):
            await DouyinBrowserClient._stop_browser(process, "ws://127.0.0.1:1234/devtools/browser/test")
        ws.send_json.assert_awaited_once_with({"id": 1, "method": "Browser.close"})
        process.wait.assert_awaited_once()

    async def test_stalled_windows_browser_kills_only_its_own_process_tree(self):
        process = type("Process", (), {"pid": 12345, "returncode": None,
                                      "wait": AsyncMock(side_effect=[asyncio.TimeoutError(), 0])})()
        killer = type("Killer", (), {"wait": AsyncMock(return_value=0)})()
        with patch.object(douyin_browser.sys, "platform", "win32"), \
             patch.object(douyin_browser.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
             patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=killer) as launch:
            await DouyinBrowserClient._stop_browser(process, "")
        self.assertEqual(launch.call_args.args[:5], ("taskkill", "/PID", "12345", "/T", "/F"))
        self.assertEqual(process.wait.await_count, 2)

    async def test_launch_failure_still_runs_process_cleanup(self):
        process = type("Process", (), {"returncode": 1})()
        client = DouyinBrowserClient()
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process), \
             patch.object(client, "_stop_browser", new_callable=AsyncMock) as cleanup:
            with self.assertRaisesRegex(RuntimeError, "沙箱"):
                await client._launch_and_read("browser", ITEM_ID, "video")
        cleanup.assert_awaited_once_with(process, "")

    async def test_cancellation_during_cleanup_waits_for_browser_to_close(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        closed = asyncio.Event()
        async def stop(*args):
            entered.set()
            await release.wait()
            closed.set()
        process = type("Process", (), {"returncode": 1})()
        client = DouyinBrowserClient()
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process), \
             patch.object(client, "_stop_browser", side_effect=stop):
            task = asyncio.create_task(client._launch_and_read("browser", ITEM_ID, "video"))
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0.01)
            still_cleaning = not task.done()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(still_cleaning)
        self.assertTrue(closed.is_set())
