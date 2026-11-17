from unittest.mock import AsyncMock
import unittest
import support
from core.parser.platform.product_browser import ProductBrowserClient


class TestProductBrowser(unittest.IsolatedAsyncioTestCase):
    async def test_document_requests_validated_before_continuing(self):
        client = ProductBrowserClient()
        ws = AsyncMock()
        for url in ("http://127.0.0.1/admin", "https://evil.test/", "https://user@item.jd.com/123.html"):
            await client._route_document(ws, {"requestId": "blocked", "request": {"url": url}}, 10)
            self.assertEqual(ws.send_json.call_args.args[0]["method"], "Fetch.failRequest")
        await client._route_document(ws, {"requestId": "ok", "request": {"url": "https://item.jd.com/123.html"}}, 11)
        self.assertEqual(ws.send_json.call_args.args[0]["method"], "Fetch.continueRequest")
