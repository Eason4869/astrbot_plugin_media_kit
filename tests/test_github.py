"""Public GitHub parsing, detail boundaries and anonymous/proxy behavior."""
import asyncio
import json
import aiohttp
import unittest
from unittest.mock import AsyncMock

import support
from core.parser.platform.github import GitHubParser


REPO = {"full_name": "acme/demo", "name": "demo", "private": False,
        "html_url": "https://github.com/acme/demo", "description": "A useful tool",
        "owner": {"login": "acme", "avatar_url": "https://avatars.githubusercontent.com/u/1"},
        "stargazers_count": 42, "forks_count": 2, "language": "Python",
        "license": {"spdx_id": "MIT"}, "default_branch": "main"}


class TestGitHub(unittest.IsolatedAsyncioTestCase):
    async def test_optional_readme_timeout_preserves_card_without_fake_summary_source(self):
        parser = GitHubParser()
        parser._get = AsyncMock(side_effect=[REPO, asyncio.TimeoutError()])
        result = await parser.parse(None, REPO["html_url"])
        self.assertEqual(result["title"], "acme/demo")
        self.assertNotIn("error", result)
        self.assertEqual(result["detail_text"], "")
        self.assertIn("README 暂未获取", result["desc"])

    async def test_optional_issue_and_pr_requests_preserve_original_body(self):
        for path, kind in (("issues/1", "issue"), ("pull/2", "pull")):
            with self.subTest(kind=kind):
                parser = GitHubParser()
                parser._get = AsyncMock(side_effect=[REPO,
                    {"title": "Known facts", "body": "Original body", "comments": 1, "state": "open"},
                    aiohttp.ClientConnectionError("disconnected")])
                result = await parser.parse(None, "https://github.com/acme/demo/" + path)
                self.assertIn("Known facts", result["title"])
                self.assertIn("Original body", result["detail_text"])
                self.assertNotIn("error", result)

    async def test_optional_enrichment_does_not_swallow_cancellation(self):
        parser = GitHubParser()
        parser._get = AsyncMock(side_effect=[REPO, asyncio.CancelledError()])
        with self.assertRaises(asyncio.CancelledError):
            await parser.parse(None, REPO["html_url"])

    async def test_issue_url_pointing_at_pr_has_real_merge_state(self):
        parser = GitHubParser()
        parser._get = AsyncMock(side_effect=[REPO,
            {"pull_request": {"url": "https://api.github.com/repos/acme/demo/pulls/2"}},
            {"title": "Fix", "state": "closed", "merged": True}, []])
        result = await parser.parse(None, "https://github.com/acme/demo/issues/2")
        self.assertEqual(result["github_info"]["kind"], "pull")
        self.assertIn("已合并", result["desc"])

    async def test_api_proxy_token_cache_and_revalidation(self):
        session = FakeSession([Response(REPO, headers={"ETag": '"v1"'}), Response(None, status=304)])
        parser = GitHubParser(token="secret-test", use_parse_proxy=True, proxy_url="http://127.0.0.1:7890")
        await parser._get(session, "/repos/acme/demo/issues/1")
        await parser._get(session, "/repos/acme/demo/issues/1")
        self.assertEqual(len(session.calls), 1)
        first = session.calls[0][1]
        self.assertEqual(first["proxy"], "http://127.0.0.1:7890")
        self.assertEqual(first["headers"]["Authorization"], "Bearer secret-test")
        self.assertFalse(first["allow_redirects"])
        entry = parser._cache["/repos/acme/demo/issues/1"]
        parser._cache["/repos/acme/demo/issues/1"] = (entry[0] - 301, entry[1], entry[2])
        self.assertEqual(await parser._get(session, "/repos/acme/demo/issues/1"), REPO)
        self.assertEqual(session.calls[-1][1]["headers"]["If-None-Match"], '"v1"')

    async def test_anonymous_request_and_no_cross_origin_token(self):
        session = FakeSession([Response(REPO)])
        parser = GitHubParser()
        await parser._get(session, "/repos/acme/demo")
        self.assertNotIn("Authorization", session.calls[0][1]["headers"])
        parser = GitHubParser(token="secret-test")
        session = FakeSession([Response(None, status=302, headers={"Location": "https://evil.test/repos/a/b"})])
        with self.assertRaisesRegex(RuntimeError, "重定向"):
            await parser._get(session, "/repos/acme/demo")
        self.assertEqual(len(session.calls), 1)

    def test_link_types_and_rejections(self):
        parser = GitHubParser()
        for path in ("acme/demo", "acme/demo/issues/1", "acme/demo/pull/2",
                     "acme/demo/releases/tag/v1.0", "acme/demo/releases/latest"):
            self.assertTrue(parser.can_parse("https://github.com/" + path), path)
        for url in ("https://github.com.evil.test/acme/demo", "https://github.com/acme/demo/blob/main/a.py",
                    "https://github.com/acme/demo/commit/abc", "https://user@github.com/acme/demo",
                    "https://github.com/settings/profile"):
            self.assertFalse(parser.can_parse(url), url)
        self.assertEqual(parser.extract_links("看 https://github.com/acme/demo，"),
                         ["https://github.com/acme/demo"])

    async def test_default_link_fetches_images_and_summary_source_without_long_text(self):
        parser = GitHubParser()
        parser._get = AsyncMock(side_effect=[REPO,
            {"path": "README.md", "encoding": "none", "content": "Useful project\n![screen](screen.png)"}])
        result = await parser.parse(None, REPO["html_url"])
        self.assertIn("42", result["desc"])
        self.assertEqual(result["image_urls"], [["https://raw.githubusercontent.com/acme/demo/main/screen.png"]])
        self.assertIn("Useful project", result["detail_text"])
        self.assertFalse(result["detail_text_visible"])
        self.assertEqual(parser._get.await_count, 2)
        self.assertEqual(result["github_info"]["kind"], "repository")
        self.assertFalse(parser.supports_detail)

    async def test_private_repo_rejected_before_details(self):
        parser = GitHubParser(token="test-token")
        parser._get = AsyncMock(return_value={**REPO, "private": True})
        with self.assertRaisesRegex(RuntimeError, "公开"):
            await parser.parse_detail(None, REPO["html_url"])
        self.assertEqual(parser._get.await_count, 1)

    async def test_visibility_change_during_fetch_discards_data_and_cache(self):
        class VisibilitySession:
            private = False
            def get(self, url, **kwargs):
                if url.endswith("/readme"):
                    self.private = True
                    return Response({"path": "README.md", "encoding": "none", "content": "PRIVATE SECRET"})
                return Response({**REPO, "private": self.private})
        parser = GitHubParser(token="privileged-test-token")
        session = VisibilitySession()
        await parser._get(session, "/repos/acme/demo")
        with self.assertRaisesRegex(RuntimeError, "公开"):
            await parser.parse_detail(session, REPO["html_url"])
        self.assertEqual(len(parser._cache), 0)

    async def test_malformed_image_preserves_text_and_other_images(self):
        parser = GitHubParser()
        body = "README survives\n![broken](https://[bad/image.png)\n![valid](images/demo.png)"
        parser._get = AsyncMock(side_effect=[REPO, {"path": "README.md", "encoding": "none", "content": body}])
        result = await parser.parse_detail(None, REPO["html_url"])
        self.assertIn("README survives", result["detail_text"])
        self.assertEqual(result["image_urls"], [["https://raw.githubusercontent.com/acme/demo/main/images/demo.png"]])

    async def test_merged_pr_and_bounded_files(self):
        parser = GitHubParser()
        pr = {"number": 2, "title": "Fix parser", "state": "closed", "merged": True,
              "user": {"login": "dev"}, "body": "Fixes links", "changed_files": 21,
              "base": {"ref": "main"}, "head": {"ref": "fix"}}
        parser._get = AsyncMock(side_effect=[REPO, pr,
            [{"filename": f"file{i}.py", "patch": "+fix"} for i in range(20)]])
        result = await parser.parse_detail(None, "https://github.com/acme/demo/pull/2")
        self.assertIn("已合并", result["desc"])
        self.assertIn("截断", result["detail_text"])
        self.assertIn("file19.py", result["detail_text"])

    async def test_readme_relative_images_and_badges(self):
        parser = GitHubParser(use_parse_proxy=True, use_image_proxy=True, proxy_url="http://127.0.0.1:7890")
        parser._get = AsyncMock(side_effect=[REPO, {"path": "docs/README.md", "encoding": "base64",
            "content": __import__("base64").b64encode(b"# Demo\n![screen](../images/demo.png)\n![badge](https://img.shields.io/a)\n![stats](https://api.star-history.com/svg?repos=a/b)\n![sponsor](https://sponsors.example.test/?v=1)\n![label](https://vendor.test/status.svg)").decode()}])
        result = await parser.parse_detail(None, REPO["html_url"])
        self.assertEqual(result["image_urls"], [["https://raw.githubusercontent.com/acme/demo/main/images/demo.png"]])
        self.assertTrue(result["use_image_proxy"])
        self.assertEqual(result["proxy_url"], "http://127.0.0.1:7890")
        self.assertNotIn("Authorization", result["image_headers"])

    async def test_summary_source_bounded(self):
        parser = GitHubParser()
        parser._get = AsyncMock(side_effect=[REPO, {"path": "README.md", "content": "A" * 40000,
                                                       "encoding": "none"}])
        result = await parser.parse_detail(None, REPO["html_url"])
        self.assertLessEqual(len(result["detail_text"]), 24000)
        self.assertTrue(result["github_info"]["truncated"])


class Response:
    def __init__(self, data, status=200, headers=None):
        self.data, self.status, self.headers = data, status, headers or {}
        self.content = self

    async def iter_chunked(self, size):
        yield json.dumps(self.data).encode()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)
