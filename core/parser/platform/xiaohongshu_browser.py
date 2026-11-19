"""小红书隔离访客浏览器回退，复用已有的浏览器启动和清理流程。"""
import asyncio
import json
import re
from urllib.parse import urlsplit, urlunsplit

from .douyin_browser import DouyinBrowserClient


class XiaohongshuBrowserClient(DouyinBrowserClient):
    @staticmethod
    def _trusted(url):
        try:
            parsed = urlsplit(url)
            return (parsed.scheme in {"http", "https"}
                    and parsed.hostname in {"www.xiaohongshu.com", "xiaohongshu.com"}
                    and parsed.username is None and parsed.password is None
                    and parsed.port in {None, 80, 443})
        except (TypeError, ValueError):
            return False

    @classmethod
    def _note_id(cls, url):
        if not cls._trusted(url):
            return ""
        match = re.fullmatch(r"/(?:explore|discovery/item)/([0-9a-f]{24})/?", urlsplit(url).path)
        return match.group(1) if match else ""

    async def fetch_note(self, url):
        note_id = self._note_id(url)
        if not note_id:
            raise ValueError("无效的小红书作品地址")
        if not self.enabled:
            raise RuntimeError("小红书浏览器回退已关闭")
        executable = self._find_executable()
        if not executable:
            raise RuntimeError("小红书 HTTP 页面受限，请在 AstrBot 所在环境安装 Chromium / Chrome / Edge")
        parsed = urlsplit(url)
        target = urlunsplit(parsed._replace(scheme="https", netloc="www.xiaohongshu.com", path=f"/explore/{note_id}", fragment=""))
        try:
            return await asyncio.wait_for(self._fetch_serial(executable, target, "note"), self.timeout)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("小红书浏览器解析超时；站点可能要求登录或人工验证，请稍后重试") from exc
        except RuntimeError as exc:
            raise RuntimeError(str(exc).replace("抖音", "小红书")) from exc

    def _navigation_url(self, item_id, media_type):
        return item_id

    async def _configure_page(self, ws):
        await super()._configure_page(ws)
        await ws.send_json({"id": 4, "method": "Fetch.enable", "params": {
            "patterns": [{"resourceType": "Document", "requestStage": "Request"}]
        }})
        while True:
            message = await ws.receive_json()
            if message.get("id") == 4:
                if message.get("error"):
                    raise RuntimeError("小红书浏览器无法启用安全导航拦截")
                return

    @classmethod
    async def _route_navigation(cls, ws, params, command_id):
        allowed = cls._trusted(params.get("request", {}).get("url", ""))
        await ws.send_json({"id": command_id,
                            "method": "Fetch.continueRequest" if allowed else "Fetch.failRequest",
                            "params": {"requestId": params["requestId"],
                                       **({} if allowed else {"errorReason": "BlockedByClient"})}})

    @staticmethod
    def _target_state(state, note_id):
        if not isinstance(state, dict):
            return None
        note_state = state.get("note") or {}
        details = note_state.get("noteDetailMap") if isinstance(note_state, dict) else None
        if isinstance(details, dict):
            detail = details.get(note_id)
            note = detail.get("note") if isinstance(detail, dict) else None
            if isinstance(note, dict) and note and str(note.get("noteId") or note.get("note_id") or note_id) == note_id:
                selected = {**state, "note": {**note_state, "noteDetailMap": {note_id: detail}}}
                selected.pop("noteData", None)
                return selected
        mobile = state.get("noteData") or {}
        if isinstance(mobile, dict) and isinstance(mobile.get("data"), dict):
            note = mobile["data"].get("noteData")
            if isinstance(note, dict) and str(note.get("noteId") or note.get("note_id") or "") == note_id:
                return state
        return None

    async def _read_detail(self, ws, item_id):
        note_id = self._note_id(item_id)
        command_id = 100
        while True:
            await ws.send_json({"id": command_id, "method": "Runtime.evaluate", "params": {
                "expression": "JSON.stringify({url:location.href,user_agent:navigator.userAgent,state:window.__INITIAL_STATE__||null})",
                "returnByValue": True,
            }})
            while True:
                message = await ws.receive_json()
                if message.get("method") == "Fetch.requestPaused":
                    await self._route_navigation(ws, message.get("params", {}), command_id + 100000)
                    continue
                if message.get("id") != command_id:
                    continue
                raw = message.get("result", {}).get("result", {}).get("value", "")
                if not isinstance(raw, str) or len(raw) > 2 * 1024 * 1024:
                    break
                try:
                    page = json.loads(raw)
                except (TypeError, ValueError):
                    break
                if not isinstance(page, dict):
                    break
                page_url = page.get("url", "")
                if self._trusted(page_url) and urlsplit(page_url).path in {"/login", "/website-login/captcha"}:
                    raise RuntimeError("小红书要求登录或人工验证，无法自动读取作品")
                if self._note_id(page_url) == note_id:
                    state = self._target_state(page.get("state"), note_id)
                    if state is not None:
                        return state, str(page.get("user_agent") or "")
                break
            command_id += 1
            await asyncio.sleep(.2)
