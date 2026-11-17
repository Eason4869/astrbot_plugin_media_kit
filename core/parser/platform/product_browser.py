"""Isolated, bounded JD DOM fallback using the existing browser lifecycle."""
import asyncio
import json

from .douyin_browser import DouyinBrowserClient
from .jd import extract_product, identify, ITEM_HOSTS, trusted_navigation
from urllib.parse import urlsplit


_BROWSER_LOCK = asyncio.Lock()


class ProductBrowserClient(DouyinBrowserClient):
    async def fetch_page(self, url, expected_id):
        if identify(url) is None:
            raise ValueError("无效的商品链接")
        self._target_url = url
        self._lock = _BROWSER_LOCK
        executable = self._find_executable()
        if not executable:
            raise RuntimeError("京东 HTTP 解析受限，未找到 Chromium/Chrome/Edge 浏览器")
        try:
            return await asyncio.wait_for(self._fetch_serial(executable, expected_id, "product"), 30)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("京东浏览器解析超时，站点可能要求登录或人工验证") from exc

    def _navigation_url(self, item_id, media_type):
        return self._target_url

    async def _configure_page(self, ws):
        await super()._configure_page(ws)
        await ws.send_json({"id": 4, "method": "Fetch.enable", "params": {
            "patterns": [{"urlPattern": "*", "resourceType": "Document", "requestStage": "Request"}]}})
        while True:
            message = await ws.receive_json()
            if message.get("id") == 4:
                if message.get("error"):
                    raise RuntimeError("京东浏览器无法启用跳转校验")
                break

    async def _route_document(self, ws, params, command_id):
        allowed = trusted_navigation(params.get("request", {}).get("url", ""))
        await ws.send_json({"id": command_id, "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest",
                            "params": {"requestId": params["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})}})

    async def _read_detail(self, ws, item_id):
        command_id = 100
        while True:
            command_id += 1
            await ws.send_json({"id": command_id, "method": "Runtime.evaluate", "params": {
                "expression": "JSON.stringify({url:location.href,html:document.documentElement.outerHTML.slice(0,2000000)})",
                "returnByValue": True}})
            deadline = asyncio.get_running_loop().time() + 1
            while asyncio.get_running_loop().time() < deadline:
                try:
                    message = await asyncio.wait_for(ws.receive_json(), max(.01, deadline - asyncio.get_running_loop().time()))
                except asyncio.TimeoutError:
                    break
                if message.get("method") == "Fetch.requestPaused":
                    command_id += 1
                    await self._route_document(ws, message.get("params", {}), 100000 + command_id)
                    continue
                if message.get("id") != command_id:
                    continue
                try:
                    data = json.loads(message.get("result", {}).get("result", {}).get("value", ""))
                    if urlsplit(data["url"]).hostname not in ITEM_HOSTS:
                        break
                    extract_product(data["html"], item_id)
                    return data["url"], data["html"]
                except (ValueError, KeyError, RuntimeError):
                    break
            await asyncio.sleep(.2)
