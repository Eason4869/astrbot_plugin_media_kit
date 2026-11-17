"""Anonymous JD product pages; only target-product regions are accepted."""
from __future__ import annotations

import asyncio
import html
from html.parser import HTMLParser
import json
import re
import aiohttp
from urllib.parse import parse_qs, urljoin, urlsplit

from .base import BaseVideoParser
from ..utils import recall_expanded_url, remember_expanded_url


ITEM_HOSTS = {"item.jd.com", "item.m.jd.com"}
SHORT_HOSTS = {"u.jd.com", "3.cn", "j.jd.com"}
REDIRECT_HOSTS = ITEM_HOSTS | SHORT_HOSTS | {"union-click.jd.com", "wq.jd.com"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36"


class UnsafeProductURLError(RuntimeError):
    """A rejected navigation must never be retried in a browser."""


def trusted_navigation(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme in {"http", "https"} and parsed.hostname in REDIRECT_HOSTS
                and not parsed.username and not parsed.password and parsed.port in {None, 80, 443})
    except (TypeError, ValueError):
        return False


def identify(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or parsed.username or parsed.password
                or parsed.port not in {None, 80, 443}):
            return None
        if parsed.hostname in SHORT_HOSTS and re.fullmatch(r"/[A-Za-z0-9_/-]+", parsed.path):
            return ""
        if parsed.hostname not in ITEM_HOSTS:
            return None
        match = re.fullmatch(r"/(?:product/)?([A-Za-z0-9_-]+)\.html", parsed.path)
        if match:
            return match[1]
        if parsed.path in {"/ware/view.action", "/ware/ware.jsp"}:
            value = parse_qs(parsed.query).get("wareId", [""])[0]
            return value if value.isdigit() else None
    except (TypeError, ValueError):
        pass
    return None


def image_url(value):
    value = html.unescape(value or "").strip().strip("\"'")
    if value.startswith("jfs/"):
        value = "https://img10.360buyimg.com/n1/" + value
    elif value.startswith("/sku/"):
        value = "https://img10.360buyimg.com" + value
    elif value.startswith("//"):
        value = "https:" + value
    try:
        parsed = urlsplit(value)
        if (parsed.scheme in {"http", "https"} and parsed.hostname
                and parsed.hostname.endswith(".360buyimg.com") and not parsed.username
                and not parsed.password and parsed.port in {None, 80, 443}):
            return value
    except ValueError:
        pass
    return ""


class ProductHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.title, self.shop = [], []
        self.main_images, self.detail_images, self.detail_classes = [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        parent = self.stack[-1][1] if self.stack else set()
        flags = set(parent)
        if attrs.get("id") == "spec-list":
            flags.add("gallery")
        if attrs.get("id") == "J-detail-content":
            flags.add("detail")
        if "sku-name-title" in classes:
            flags.add("title")
        if "shop-name" in classes or attrs.get("id") == "shop-name":
            flags.add("shop")
        if "detail" in flags:
            self.detail_classes.extend(classes)
            if attrs.get("id") == "zbViewWeChatMiniImages":
                self.detail_images.extend(attrs.get("value", "").split(","))
        if tag == "img":
            if "gallery" in flags:
                self.main_images.append(attrs.get("data-url") or attrs.get("src") or "")
            if "detail" in flags:
                self.detail_images.append(attrs.get("data-lazyload") or attrs.get("data-src") or attrs.get("src") or "")
        if tag not in {"img", "br", "hr", "input", "meta", "link", "source", "wbr", "area", "base", "embed", "param", "track", "col"}:
            self.stack.append((tag, flags))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        flags = self.stack[-1][1] if self.stack else set()
        if "title" in flags:
            self.title.append(data)
        if "shop" in flags:
            self.shop.append(data)


def extract_product(page, expected_id=""):
    matches = re.findall(r"\bskuid\s*:\s*['\"]?(\d+)", page, re.I)
    sku = matches[0] if matches else ""
    if expected_id and expected_id.isdigit() and sku and sku != expected_id:
        raise RuntimeError("京东返回的商品编号与链接不匹配")
    if not sku:
        raise RuntimeError("京东页面未提供目标商品数据，可能需要登录或验证")
    parser = ProductHTML()
    parser.feed(page)
    title = " ".join(" ".join(parser.title).split())
    if not title:
        raise RuntimeError("京东页面未提供商品名称，可能需要登录或验证")
    price = "暂未获取"
    for script in re.findall(r'<script\b[^>]*type=[\"\x27]application/ld\+json[\"\x27][^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(script)
            candidates = data if isinstance(data, list) else [data]
            for product in candidates:
                if (isinstance(product, dict) and product.get("@type") == "Product"
                        and str(product.get("sku") or product.get("productID")) == sku):
                    offers = product.get("offers") or {}
                    if isinstance(offers, dict) and offers.get("priceCurrency", "CNY") == "CNY":
                        value = str(offers.get("price") or "")
                        if re.fullmatch(r"\d+(?:\.\d{1,2})?", value):
                            price = "¥" + value
                        else:
                            low, high = str(offers.get("lowPrice") or ""), str(offers.get("highPrice") or "")
                            if all(re.fullmatch(r"\d+(?:\.\d{1,2})?", amount) for amount in (low, high)):
                                price = f"¥{low}–{high}"
        except (ValueError, TypeError):
            continue
    # CSS background images are accepted only for modules inside this product's description.
    backgrounds = dict(re.findall(r"\.ssd-module-wrap\s+\.([\w-]+)\s*\{[^}]*?background-image\s*:\s*url\(([^)]+)\)", page, re.I))
    parser.detail_images.extend(backgrounds[c] for c in parser.detail_classes if c in backgrounds)
    def unique(values):
        return list(dict.fromkeys(u for value in values if (u := image_url(value))))
    return {"sku": sku, "title": title, "shop": " ".join(" ".join(parser.shop).split()),
            "price_text": price, "main_images": unique(parser.main_images),
            "detail_images": unique(parser.detail_images)}


class JDParser(BaseVideoParser):
    supports_detail = True

    def __init__(self, *, browser_fallback=True, browser_path=""):
        super().__init__("jd")
        self.browser_fallback = browser_fallback
        self.browser_path = browser_path

    def can_parse(self, url):
        return identify(url) is not None

    def extract_links(self, text):
        links = []
        for match in re.finditer(r"https?://[^\s<>\"'()]+", text or ""):
            url = match.group().rstrip(".,!?;:，。！？；：）】》」")
            if self.can_parse(url) and url not in links:
                links.append(url)
        return links

    async def _fetch_page(self, session, url):
        original = url
        url = recall_expanded_url(session, url) or url
        for _ in range(6):
            if not trusted_navigation(url):
                raise UnsafeProductURLError("京东链接跳转到了不受信任的地址")
            parsed = urlsplit(url)
            async with session.get(url, headers={"User-Agent": UA}, allow_redirects=False) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise RuntimeError("京东重定向缺少目标地址")
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise RuntimeError(f"京东页面请求失败：HTTP {response.status}")
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > 2 * 1024 * 1024:
                        raise RuntimeError("京东页面过大，已停止读取")
                    chunks.append(chunk)
                raw = b"".join(chunks)
                page = raw.decode(response.charset or "utf-8", errors="replace")
                if "\ufffd" in page:
                    alternative = raw.decode("gb18030", errors="replace")
                    if alternative.count("\ufffd") < page.count("\ufffd"):
                        page = alternative
                if parsed.hostname in ITEM_HOSTS:
                    remember_expanded_url(session, original, url)
                    return url, page
                match = re.search(r'(?:location(?:\.href)?\s*=|location\.replace\()\s*[\"\x27]([^\"\x27]+)', page)
                if not match:
                    raise RuntimeError("京东短链无法展开为商品页")
                url = urljoin(url, html.unescape(match[1]))
        raise RuntimeError("京东链接跳转次数过多")

    async def parse(self, session, url):
        return await self._parse(session, url, detail=False)

    async def parse_detail(self, session, url):
        return await self._parse(session, url, detail=True)

    async def _parse(self, session, url, *, detail):
        expected = identify(url)
        if expected is None:
            raise RuntimeError("不支持的京东链接")
        try:
            final_url, page = await self._fetch_page(session, url)
            product = extract_product(page, expected)
        except UnsafeProductURLError:
            raise
        except (RuntimeError, OSError, asyncio.TimeoutError, aiohttp.ClientError):
            if not self.browser_fallback:
                raise
            from .product_browser import ProductBrowserClient
            final_url, page = await ProductBrowserClient(executable=self.browser_path).fetch_page(url, expected)
            product = extract_product(page, expected)
        images = list(dict.fromkeys(product["main_images"] + product["detail_images"]))
        desc = [f"参考价格：{product['price_text']}"]
        if product["shop"]:
            desc.append("店铺：" + product["shop"])
        if detail:
            desc.append(f"商品图片：已提取 {len(images)} 张，最多发送 20 张")
            if not product["detail_images"]:
                desc.append("详情图暂未获取，仅发送可用商品主图")
        # New product tokens may be accessible while the legacy numeric URL is blocked.
        canonical = final_url
        cover = product["main_images"][:1]
        return {"url": canonical, "source_url": url, "platform": "jd", "parser_name": self.name,
                "title": product["title"], "author": product["shop"], "desc": "\n".join(desc),
                "video_urls": [], "image_urls": [[image] for image in images[:20]] if detail else [],
                "card_cover_urls": [[image] for image in cover],
                "image_headers": {"Referer": final_url, "User-Agent": UA},
                "product_info": {"sku": product["sku"], "price_text": product["price_text"],
                                 "image_count": len(images), "detail_image_count": len(product["detail_images"])}}
