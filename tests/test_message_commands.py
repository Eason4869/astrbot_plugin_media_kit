"""执行真实消息处理函数；仅隔离 AstrBot 装饰器与网络会话。"""
import ast
import asyncio
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))
import support
from core.constants import Config
from core.storage.parse_record import ParseRecordManager


class OfflineSession:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def load_handler():
    # 主模块依赖 AstrBot；不执行注册与初始化，直接运行同一函数的完整函数体。
    source = Path(_HERE).parent / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "VideoParserPlugin")
    handler = next(node for node in plugin.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "auto_parse")
    handler.decorator_list = []
    namespace = {
        "asyncio": asyncio, "AstrMessageEvent": object, "Config": Config,
        "ParseRecordManager": ParseRecordManager,
        "create_public_only_connector": lambda **kwargs: None,
        "aiohttp": SimpleNamespace(ClientTimeout=lambda **kwargs: None, ClientSession=OfflineSession),
    }
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["auto_parse"]


def event(text):
    return SimpleNamespace(
        message_str=text, message_obj=SimpleNamespace(message_id="message"),
        is_private_chat=lambda: True, get_sender_id=lambda: "admin",
        get_self_id=lambda: "bot", get_platform_name=lambda: "test",
    )


def plugin(manager, *, outputs=True):
    short = "https://v.douyin.com/example/"
    parser = SimpleNamespace(name="douyin")
    assist = SimpleNamespace(try_update_admin_origin=lambda event: None,
                             handle_admin_command=AsyncMock(return_value=False))
    cfg = SimpleNamespace(
        permission=SimpleNamespace(check=lambda *args: True),
        admin=SimpleNamespace(clean_cache_keyword="", status_keyword="", force_parse_keyword="force",
                              force_parse_admin_only=True, debug_mode=False),
        parser_output=SimpleNamespace(has_any_output=lambda: outputs),
        emoji_feedback=SimpleNamespace(arbitration_enabled=False, feedback_enabled=False),
        proxy=SimpleNamespace(address=""), message=SimpleNamespace(archive=SimpleNamespace(command="")),
        trigger=SimpleNamespace(should_parse=lambda text: True),
    )
    return SimpleNamespace(
        config_manager=cfg, admin_cookie_assist=assist, bilibili_auth_runtime=None,
        _start_expired_cache_cleanup=lambda: None,
        _is_admin_sender=lambda sender: True,
        _try_extract_reply_links=lambda event: ([(short, parser)], "quoted"),
        _filter_links_by_output=lambda links: links,
        _extract_urls_from_json_cards=lambda event: [],
        parse_record_manager=manager,
        parser_manager=SimpleNamespace(
            extract_all_links=lambda text: [(short, parser)],
            parse_text=AsyncMock(return_value=[{"url": "https://www.douyin.com/video/123", "parser_name": "douyin"}]),
        ),
        message_sender=SimpleNamespace(get_sender_info=lambda event: ("Admin", "admin")),
        _trigger_bilibili_cookie_assist_if_needed=lambda: None,
        _apply_output_flags=lambda metadata: None,
        _metadata_has_output_candidate=lambda metadata: False,
    )


class TestMessageCommands(unittest.IsolatedAsyncioTestCase):
    async def test_detail_command_dispatches_and_has_its_own_link_quota(self):
        manager = ParseRecordManager(same_link_max_count=1, same_link_window_seconds=3600)
        instance = plugin(manager)
        instance.config_manager.admin.detail_parse_keyword = "详细解析"
        parser = SimpleNamespace(name="github", supports_detail=True)
        url = "https://github.com/acme/demo"
        instance._try_extract_reply_links = lambda event: ([(url, parser)], "quoted")
        manager.filter_links([(url, parser)], user_key="other")
        instance.config_manager.trigger.should_parse = lambda text: False
        message = event("详细解析")
        message.send = AsyncMock()
        message.plain_result = lambda text: text
        await load_handler()(instance, message)
        self.assertTrue(instance.parser_manager.parse_text.await_args.kwargs["detail"])

    async def test_detail_command_rejects_unsupported_quoted_links(self):
        instance = plugin(ParseRecordManager())
        instance.config_manager.admin.detail_parse_keyword = "详细解析"
        message = event("详细解析")
        message.send = AsyncMock()
        message.plain_result = lambda text: text
        await load_handler()(instance, message)
        instance.parser_manager.parse_text.assert_not_awaited()
        self.assertIn("支持详细解析", message.send.call_args.args[0])

    async def test_force_short_link_does_not_consume_canonical_url_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ParseRecordManager(record_file=str(Path(directory) / "records.json"),
                                         same_link_max_count=1, same_link_window_seconds=3600)
            instance = plugin(manager)
            await load_handler()(instance, event("force"))
            allowed, blocked = manager.filter_links(
                [("https://www.douyin.com/video/123", SimpleNamespace(name="douyin"))], user_key="other"
            )
            self.assertEqual(len(allowed), 1)
            self.assertEqual(blocked, [])

    async def test_normal_short_link_still_records_canonical_url(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ParseRecordManager(record_file=str(Path(directory) / "records.json"),
                                         same_link_max_count=1, same_link_window_seconds=3600)
            await load_handler()(plugin(manager), event("https://v.douyin.com/example/"))
            allowed, blocked = manager.filter_links(
                [("https://www.douyin.com/video/123", SimpleNamespace(name="douyin"))], user_key="other"
            )
            self.assertEqual(allowed, [])
            self.assertEqual(len(blocked), 1)

    async def test_cookie_command_works_when_all_parser_outputs_are_off(self):
        instance = plugin(ParseRecordManager(), outputs=False)
        instance.admin_cookie_assist.handle_admin_command.return_value = True
        message = event("B站更新Cookie")
        await load_handler()(instance, message)
        instance.admin_cookie_assist.handle_admin_command.assert_awaited_once_with(message, None)
