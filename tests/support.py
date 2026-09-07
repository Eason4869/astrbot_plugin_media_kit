"""共享测试支撑：路径注入与通用小工具。

在导入被测模块前，先确保仓库根目录在 sys.path 上，
以便以 ``core.parser...`` 的包路径导入，无需安装成发行包。
"""
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


class FakeResponse:
    """可控的类 aiohttp 响应，供离线单测使用。"""

    def __init__(self, status: int = 200, payload=None, text_body: str = "",
                 headers=None):
        self.status = status
        self._payload = payload
        self._text = text_body
        self._reason = ""

    def raise_for_status(self):
        if self.status >= 400:
            raise _FakeHttpError(self.status)

    async def json(self, content_type=None):
        return self._payload

    async def text(self, encoding=None):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeHttpError(RuntimeError):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.message = f"HTTP {status}"
