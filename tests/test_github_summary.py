import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
import support
from core.config_manager import TranslationConfig
from core.github_summary import GitHubSummarizer


class TestGitHubSummary(unittest.IsolatedAsyncioTestCase):
    def make_service(self):
        service = GitHubSummarizer(TranslationConfig(), enabled=True)
        service.transport._missing_llm_fields = lambda context: []
        service.transport._astrbot_provider_id = AsyncMock(return_value="test-provider")
        return service

    async def test_disabled_translation_does_not_disable_summary_and_cache(self):
        service = self.make_service()
        service.transport.complete_payload = AsyncMock(return_value='{"summary":"这是项目介绍。"}')
        metadata = {"platform": "github", "url": "https://github.com/a/b", "title": "a/b",
                    "github_info": {"kind": "repository"}, "detail_text": "README"}
        self.assertEqual(await service.summarize(metadata, {}), "这是项目介绍。")
        self.assertEqual(await service.summarize(metadata, {}), "这是项目介绍。")
        self.assertEqual(service.transport.complete_payload.await_count, 1)
        metadata["detail_text"] = "README changed"
        await service.summarize(metadata, {})
        self.assertEqual(service.transport.complete_payload.await_count, 2)

    async def test_malformed_or_failed_summary_preserves_source(self):
        service = self.make_service()
        service.transport.complete_payload = AsyncMock(return_value="not JSON")
        meta = {"url": "u", "detail_text": "trusted source"}
        self.assertEqual(await service.summarize(meta, {}), "")
        self.assertEqual(meta["detail_text"], "trusted source")
        service.transport.complete_payload.side_effect = RuntimeError("unavailable")
        self.assertEqual(await service.summarize(meta, {}), "")

    async def test_no_source_no_call_and_input_is_bounded(self):
        service = self.make_service()
        service.transport.complete_payload = AsyncMock(return_value='{"summary":"简述"}')
        self.assertEqual(await service.summarize({}, {}), "")
        service.transport.complete_payload.assert_not_awaited()
        await service.summarize({"detail_text": "x" * 60000}, {})
        payload = service.transport.complete_payload.call_args.args[0]
        self.assertLess(len(payload["messages"][1]["content"]), 25000)

    async def test_provider_scope_is_part_of_cache_key(self):
        service = self.make_service()
        service.transport.complete_payload = AsyncMock(return_value='{"summary":"简述"}')
        service.transport._astrbot_provider_id = AsyncMock(side_effect=["model-a", "model-b"])
        meta = {"url": "u", "detail_text": "README"}
        await service.summarize(meta, {"_astrbot_unified_msg_origin": "group:a"})
        await service.summarize(meta, {"_astrbot_unified_msg_origin": "group:b"})
        self.assertEqual(service.transport.complete_payload.await_count, 2)
