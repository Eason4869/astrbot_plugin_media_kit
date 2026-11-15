"""普通 Chromium 访客会话回退：仅观察站点自身的作品详情响应。"""

import asyncio
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit

import aiohttp

from .douyin_web import DOUYIN_WEB_USER_AGENT, DouyinWebClient


class DouyinBrowserClient:
    """串行、限时启动隔离浏览器；不读取已有账号或处理人工验证码。"""

    def __init__(self, *, enabled: bool = True, executable: str = "", timeout: float = 30):
        self.enabled = enabled
        self.executable = executable
        self.timeout = timeout
        self._lock = asyncio.Lock()

    def _find_executable(self) -> Optional[str]:
        if self.executable:
            path = Path(self.executable).expanduser()
            return str(path) if path.is_file() else shutil.which(self.executable)
        for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge", "msedge"):
            if found := shutil.which(name):
                return found
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        if sys.platform == "win32":
            for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
                base = os.environ.get(variable)
                if base:
                    candidates.extend(str(Path(base) / relative) for relative in (
                        "Google/Chrome/Application/chrome.exe",
                        "Microsoft/Edge/Application/msedge.exe",
                    ))
        return next((path for path in candidates if Path(path).is_file()), None)

    async def fetch_detail(self, item_id: str, media_type: str = "video") -> tuple[dict, str]:
        if not item_id.isdigit() or media_type not in {"video", "note"}:
            raise ValueError("无效的抖音作品 ID 或类型")
        if not self.enabled:
            raise RuntimeError("抖音 HTTP 解析受限，浏览器回退已关闭")
        executable = self._find_executable()
        if not executable:
            raise RuntimeError("抖音 HTTP 解析受限；请安装 Chromium/Chrome/Edge，或在抖音设置中指定浏览器路径")
        try:
            # 将排队也纳入超时，避免群聊并发请求无限等待浏览器。
            return await asyncio.wait_for(
                self._fetch_serial(executable, item_id, media_type), self.timeout
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError("抖音浏览器解析超时；站点可能仍要求人工验证，请稍后重试") from exc

    async def _fetch_serial(self, executable: str, item_id: str, media_type: str):
        async with self._lock:
            return await self._launch_and_read(executable, item_id, media_type)

    async def _launch_and_read(self, executable: str, item_id: str, media_type: str):
        with tempfile.TemporaryDirectory(prefix="media-kit-douyin-", ignore_cleanup_errors=True) as profile:
            process = None
            browser_ws = ""
            try:
                kwargs: dict[str, Any] = {}
                if sys.platform == "win32":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                else:
                    kwargs["start_new_session"] = True
                process = await asyncio.create_subprocess_exec(
                    executable, "--headless=new", "--remote-debugging-port=0",
                    "--remote-debugging-address=127.0.0.1", "--no-first-run",
                    "--disable-extensions", "--disable-background-networking",
                    "--autoplay-policy=user-gesture-required", "--mute-audio",
                    f"--user-data-dir={profile}", "about:blank",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    **kwargs,
                )
                port_file = Path(profile) / "DevToolsActivePort"
                while True:
                    if process.returncode is not None:
                        raise RuntimeError("抖音浏览器未能启动，请检查浏览器安装和沙箱运行条件")
                    try:
                        lines = port_file.read_text(encoding="utf-8").splitlines()
                        port = int(lines[0])
                        browser_ws = f"ws://127.0.0.1:{port}{lines[1]}"
                        break
                    except (OSError, ValueError, IndexError):
                        await asyncio.sleep(0.1)
                # CDP 仅连接本机端口，不使用用户配置的网络代理。
                async with aiohttp.ClientSession(trust_env=False) as session:
                    async with session.get(f"http://127.0.0.1:{port}/json/list") as response:
                        pages = await response.json()
                    page = next(page for page in pages if page.get("type") == "page")
                    async with session.ws_connect(page["webSocketDebuggerUrl"], max_msg_size=8 * 1024 * 1024) as ws:
                        await ws.send_json({"id": 1, "method": "Network.enable"})
                        await ws.send_json({"id": 2, "method": "Page.navigate", "params": {
                            "url": f"https://www.douyin.com/{media_type}/{item_id}"
                        }})
                        await ws.send_json({"id": 3, "method": "Browser.getVersion"})
                        return await self._read_detail(ws, item_id)
            except (OSError, aiohttp.ClientError, StopIteration) as exc:
                raise RuntimeError("抖音浏览器连接失败，请检查浏览器安装和运行环境") from exc
            finally:
                if process is not None:
                    # 超时/取消也可能首次发生在正常清理期间；先等自己的
                    # 浏览器关闭，再向调用方传播取消，避免留下子进程和目录。
                    cleanup = asyncio.create_task(self._stop_browser(process, browser_ws))
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        await cleanup
                        raise

    @staticmethod
    async def _stop_browser(process, browser_ws: str):
        if browser_ws and process.returncode is None:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2), trust_env=False) as session:
                    async with session.ws_connect(browser_ws) as ws:
                        await ws.send_json({"id": 1, "method": "Browser.close"})
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
            return
        except asyncio.TimeoutError:
            pass
        # 仅终止本次启动的浏览器进程树，防止取消后残留渲染进程。
        if sys.platform == "win32":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(process.pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            await killer.wait()
        else:
            import signal
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await process.wait()

    @staticmethod
    async def _read_detail(ws, item_id: str) -> tuple[dict, str]:
        requests = set()
        pending = set()
        command_id = 3
        user_agent = DOUYIN_WEB_USER_AGENT
        while True:
            message = await ws.receive_json()
            params = message.get("params", {})
            method = message.get("method")
            if message.get("id") == 3:
                user_agent = message.get("result", {}).get("userAgent") or user_agent
            elif method == "Network.responseReceived":
                response = params.get("response", {})
                url = urlsplit(response.get("url", ""))
                if (url.scheme == "https" and url.hostname == "www.douyin.com"
                        and url.path == "/aweme/v1/web/aweme/detail/"
                        and response.get("status") == 200
                        and parse_qs(url.query).get("aweme_id") == [item_id]):
                    requests.add(params["requestId"])
            elif method == "Network.loadingFinished" and params.get("requestId") in requests:
                requests.remove(params["requestId"])
                command_id += 1
                pending.add(command_id)
                await ws.send_json({"id": command_id, "method": "Network.getResponseBody",
                                    "params": {"requestId": params["requestId"]}})
            elif message.get("id") in pending:
                pending.remove(message["id"])
                result = message.get("result", {})
                body = result.get("body", "")
                try:
                    if result.get("base64Encoded"):
                        body = base64.b64decode(body, validate=True).decode("utf-8")
                    data = json.loads(body)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(data, dict) and DouyinWebClient._contains_target(data, item_id):
                    return data, user_agent
