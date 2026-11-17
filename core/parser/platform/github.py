"""Public GitHub facts via REST; expensive content is fetched only on demand."""
from __future__ import annotations

import asyncio
import base64
from collections import OrderedDict
import copy
from contextvars import ContextVar
import html
import json
import re
import time
from urllib.parse import quote, unquote, urljoin, urlsplit

from .base import BaseVideoParser


MAX_DETAIL_CHARS = 24000
_RESERVED = {"settings", "features", "topics", "collections", "marketplace", "orgs",
             "users", "login", "signup", "search", "notifications", "sponsors"}


def identify_link(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"https", "http"} or parsed.hostname not in {"github.com", "www.github.com"}
                or parsed.username or parsed.password or parsed.port not in {None, 80, 443}):
            return None
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2 or parts[0].lower() in _RESERVED:
            return None
        owner, repo = parts[:2]
        repo = repo.removesuffix(".git")
        if not re.fullmatch(r"[A-Za-z0-9-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
            return None
        if repo in {".", ".."}:
            return None
        kind, identifier = "repository", ""
        if len(parts) == 4 and parts[2] in {"issues", "pull"} and re.fullmatch(r"[1-9][0-9]*", parts[3]):
            kind, identifier = ("issue" if parts[2] == "issues" else "pull"), parts[3]
        elif len(parts) == 4 and parts[2:] == ["releases", "latest"]:
            kind, identifier = "release", "latest"
        elif len(parts) >= 5 and parts[2:4] == ["releases", "tag"]:
            kind, identifier = "release", unquote("/".join(parts[4:]))
        elif len(parts) != 2:
            return None
        return owner, repo, kind, identifier
    except (TypeError, ValueError):
        return None


class GitHubParser(BaseVideoParser):
    supports_detail = True

    def __init__(self, token="", use_parse_proxy=False, use_image_proxy=True, proxy_url=None):
        super().__init__("github")
        self.token = str(token or "").strip()
        self.use_parse_proxy = use_parse_proxy
        self.use_image_proxy = use_image_proxy
        self.proxy_url = proxy_url
        self._cache = OrderedDict()
        self._semaphore = asyncio.Semaphore(3)
        self._staged_cache = ContextVar(f"github_staged_{id(self)}", default=None)

    def can_parse(self, url):
        return identify_link(url) is not None

    def extract_links(self, text):
        links = []
        for match in re.finditer(r"https?://(?:www\.)?github\.com/[^\s<>\"'()]+", text or "", re.I):
            url = match.group().rstrip(".,!?;:，。！？；：）】》」")
            if self.can_parse(url) and url not in links:
                links.append(url)
        return links

    async def _get(self, session, path):
        cached = self._cache.get(path)
        is_root = bool(re.fullmatch(r"/repos/[^/]+/[^/?]+", path))
        if cached and time.monotonic() - cached[0] < 300 and not (self.token and is_root):
            self._cache.move_to_end(path)
            return copy.deepcopy(cached[2])
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "AstrBot-Media-Kit",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if cached and cached[1]:
            headers["If-None-Match"] = cached[1]
        url = "https://api.github.com" + path
        proxy = self.proxy_url if self.use_parse_proxy else None
        async with self._semaphore:
            for _ in range(4):
                async with session.get(url, headers=headers, proxy=proxy, allow_redirects=False) as response:
                    if response.status in {301, 302, 307, 308}:
                        target = urljoin(url, response.headers.get("Location", ""))
                        parsed = urlsplit(target)
                        if (parsed.scheme != "https" or parsed.hostname != "api.github.com"
                                or parsed.username or parsed.password or parsed.port not in {None, 443}
                                or not parsed.path.startswith("/repos/")):
                            raise RuntimeError("GitHub API 重定向地址不受信任")
                        url = target
                        continue
                    if response.status == 304 and cached:
                        self._cache[path] = (time.monotonic(), cached[1], cached[2])
                        return copy.deepcopy(cached[2])
                    if response.status in {403, 429}:
                        raise RuntimeError("GitHub 访问受限或达到请求额度，请稍后重试；可配置可选 Token 和解析代理")
                    if response.status == 404:
                        raise RuntimeError("GitHub 资源不存在或不是公开资源")
                    if response.status != 200:
                        raise RuntimeError(f"GitHub API 请求失败：HTTP {response.status}")
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > 2 * 1024 * 1024:
                            raise RuntimeError("GitHub 响应过大，已停止读取")
                        chunks.append(chunk)
                    data = json.loads(b"".join(chunks))
                    if isinstance(data, dict):
                        data.pop("temp_clone_token", None)
                    # Private metadata must never enter the content cache.
                    if not (isinstance(data, dict) and data.get("private")):
                        entry = (time.monotonic(), response.headers.get("ETag", ""), copy.deepcopy(data))
                        staged = self._staged_cache.get()
                        if self.token and not is_root and staged is not None:
                            staged[path] = entry
                        else:
                            self._store_cache(path, entry)
                    return data
            raise RuntimeError("GitHub API 重定向次数过多")

    def _store_cache(self, path, entry):
        self._cache[path] = entry
        self._cache.move_to_end(path)
        while len(self._cache) > 128:
            self._cache.popitem(last=False)

    async def parse(self, session, url):
        return await self._parse(session, url, detail=False)

    async def parse_detail(self, session, url):
        return await self._parse(session, url, detail=True)

    async def _parse(self, session, url, *, detail):
        target = identify_link(url)
        if target is None:
            raise RuntimeError("不支持的 GitHub 链接")
        root = f"/repos/{target[0]}/{target[1]}"
        staged = {}
        context_token = self._staged_cache.set(staged)
        try:
            result = await self._parse_public(session, url, detail=detail)
            if self.token:
                # Privileged requests must not trust an old public visibility snapshot.
                visibility = await self._get(session, root)
                if visibility.get("private") or visibility.get("visibility", "public") != "public":
                    raise RuntimeError("仅支持公开 GitHub 资源")
                for path, entry in staged.items():
                    self._store_cache(path, entry)
            return result
        except BaseException:
            if self.token:
                for path in list(self._cache):
                    if path == root or path.startswith(root + "/"):
                        del self._cache[path]
            raise
        finally:
            self._staged_cache.reset(context_token)

    async def _parse_public(self, session, url, *, detail):
        target = identify_link(url)
        if target is None:
            raise RuntimeError("不支持的 GitHub 链接")
        owner, name, kind, identifier = target
        root = f"/repos/{owner}/{name}"
        repo = await self._get(session, root)
        if repo.get("private") or repo.get("visibility", "public") != "public":
            raise RuntimeError("仅支持公开 GitHub 资源")
        base_url = repo.get("html_url") or f"https://github.com/{owner}/{name}"
        author = repo.get("owner") or {}
        info = {"kind": kind, "repository": repo.get("full_name") or f"{owner}/{name}", "truncated": False}
        lines, source = [], ""
        title = info["repository"]
        timestamp = repo.get("pushed_at") or ""
        canonical = base_url
        image_base = base_url + "/"
        if kind == "repository":
            lines = [str(repo.get("description") or "暂无项目简介"),
                     f"Stars：{repo.get('stargazers_count', 0)} · Forks：{repo.get('forks_count', 0)}",
                     f"语言：{repo.get('language') or '未标注'} · 许可证：{(repo.get('license') or {}).get('spdx_id') or '未标注'}"]
            if repo.get("archived"):
                lines.append("状态：已归档")
            if detail:
                try:
                    readme = await self._get(session, root + "/readme")
                    content = readme.get("content") or ""
                    source = (base64.b64decode(content).decode("utf-8", errors="replace")
                              if readme.get("encoding") == "base64" else content)
                    if not source:
                        source = "README 正文暂未获取，可能超过接口内容大小限制；请查看原链接。"
                    image_base = (f"https://raw.githubusercontent.com/{owner}/{name}/"
                                  f"{quote(repo.get('default_branch') or 'main', safe='')}/"
                                  + str(readme.get("path") or "README.md"))
                except RuntimeError as exc:
                    source = f"README 暂未获取：{exc}"
        elif kind in {"issue", "pull"}:
            endpoint = "issues" if kind == "issue" else "pulls"
            item = await self._get(session, f"{root}/{endpoint}/{identifier}")
            if kind == "issue" and item.get("pull_request"):
                kind = info["kind"] = "pull"
                item = await self._get(session, f"{root}/pulls/{identifier}")
            title = f"{info['repository']} #{identifier} · {item.get('title') or ''}"
            author = item.get("user") or author
            timestamp = item.get("updated_at") or ""
            canonical = item.get("html_url") or f"{base_url}/{'issues' if kind == 'issue' else 'pull'}/{identifier}"
            state = ("已合并" if kind == "pull" and item.get("merged") else
                     "草稿" if item.get("draft") else "已关闭" if item.get("state") == "closed" else "进行中")
            info["state"] = state
            lines = [f"状态：{state} · 评论：{item.get('comments', 0)}"]
            labels = [label.get("name", "") for label in item.get("labels") or [] if isinstance(label, dict)]
            if labels:
                lines.append("标签：" + "、".join(labels))
            if kind == "pull":
                lines.extend([f"分支：{(item.get('head') or {}).get('ref', '?')} → {(item.get('base') or {}).get('ref', '?')}",
                              f"改动：{item.get('changed_files', 0)} 文件 · +{item.get('additions', 0)} / -{item.get('deletions', 0)}"])
            lines.append(str(item.get("body") or "暂无正文")[:400])
            if detail:
                source = str(item.get("body") or "暂无正文")
                try:
                    if kind == "pull":
                        files = await self._get(session, f"{root}/pulls/{identifier}/files?per_page=20")
                        for item_file in files[:20]:
                            source += f"\n\n文件：{item_file.get('filename', '')}\n{item_file.get('patch') or '无可用文本差异'}"
                        if item.get("changed_files", 0) > len(files):
                            info["truncated"] = True
                    elif item.get("comments"):
                        total = int(item["comments"])
                        # The last two pages cover the latest ten comments, including a short final page.
                        last = (total + 9) // 10
                        comments = []
                        for page in range(max(1, last - 1), last + 1):
                            comments.extend(await self._get(session, f"{root}/issues/{identifier}/comments?per_page=10&page={page}"))
                        for comment in comments[-10:]:
                            source += f"\n\n{(comment.get('user') or {}).get('login', '')}：{comment.get('body') or ''}"
                        info["truncated"] = total > 10
                except RuntimeError as exc:
                    source += f"\n\n补充详情暂未获取：{exc}"
        else:
            suffix = "latest" if identifier == "latest" else "tags/" + quote(identifier, safe="")
            release = await self._get(session, f"{root}/releases/{suffix}")
            if release.get("draft"):
                raise RuntimeError("仅支持公开发布的 GitHub 版本")
            title = f"{info['repository']} · {release.get('name') or release.get('tag_name') or identifier}"
            author = release.get("author") or author
            timestamp = release.get("published_at") or ""
            canonical = release.get("html_url") or f"{base_url}/releases/tag/{quote(identifier, safe='')}"
            assets = release.get("assets") or []
            lines = [f"版本：{release.get('tag_name') or identifier}",
                     f"{'预发布' if release.get('prerelease') else '正式版'} · 附件：{len(assets)}",
                     str(release.get("body") or "暂无更新说明")[:400]]
            if detail:
                source = str(release.get("body") or "暂无更新说明")
                for asset in assets[:20]:
                    source += f"\n\n附件：{asset.get('name', '')}（{asset.get('size', 0)} 字节）\n{asset.get('browser_download_url', '')}"
                info["truncated"] = len(assets) > 20
        if len(source) > MAX_DETAIL_CHARS:
            info["truncated"] = True
        if info["truncated"]:
            source = source[:MAX_DETAIL_CHARS - 32] + "\n\n[内容已截断，完整内容请查看原链接]"
        result = {"url": canonical, "source_url": url, "platform": "github", "parser_name": self.name,
                  "title": title, "author": author.get("login") or "", "avatar_url": author.get("avatar_url") or "",
                  "desc": "\n".join(lines), "timestamp": timestamp, "video_urls": [], "image_urls": [],
                  "image_headers": {}, "use_image_proxy": self.use_image_proxy, "proxy_url": self.proxy_url,
                  "github_info": info}
        if detail:
            result["detail_text"] = source
            result["image_urls"] = [[image] for image in extract_images(source, image_base)]
        return result


def extract_images(markdown, base_url):
    """Only正文 images; no recursive page fetches or badge endpoints."""
    candidates = re.findall(r"!\[[^\]]*\]\(<?([^\s)>]+)", markdown)
    candidates += re.findall(r'<img\b[^>]*\bsrc=[\"\x27]([^\"\x27]+)', markdown, re.I)
    images = []
    for candidate in candidates:
        try:
            url = urljoin(base_url, html.unescape(candidate))
            parsed = urlsplit(url)
            if parsed.port not in {None, 80, 443}:
                continue
        except (ValueError, TypeError):
            continue
        if (parsed.scheme not in {"http", "https"} or parsed.username or parsed.password
                or not parsed.hostname or re.search(r"shield|badge|travis|codecov|tracking|pixel", url, re.I)):
            continue
        if url not in images:
            images.append(url)
        if len(images) == 6:
            break
    return images
