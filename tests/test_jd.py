import unittest
from unittest.mock import AsyncMock, patch
import support
from core.parser.platform.jd import JDParser, extract_product


PAGE = '''<html><head><title>测试手机【图片 价格】-京东</title>
<script>var pageConfig={product:{skuid:12345}};</script>
<style>.ssd-module-wrap .M1{background-image:url(//img10.360buyimg.com/sku/jfs/detail.jpg)}</style>
</head><body><span class="sku-name-title">测试手机 16GB</span>
<div id="spec-list"><img data-url="jfs/main.jpg"><img data-url="jfs/main2.jpg"></div>
<div id="J-detail-content"><div class="ssd-module M1"></div>
<div id="zbViewWeChatMiniImages" value="/sku/jfs/detail2.jpg,/sku/jfs/detail3.jpg"></div></div>
<div class="recommend"><img src="//img10.360buyimg.com/other.jpg">价格1元</div></body></html>'''


class TestJD(unittest.IsolatedAsyncioTestCase):
    async def test_untrusted_redirect_is_not_replayed_in_browser(self):
        from core.parser.platform.jd import UnsafeProductURLError
        parser = JDParser()
        parser._fetch_page = AsyncMock(side_effect=UnsafeProductURLError("不受信任的地址"))
        with patch("core.parser.platform.product_browser.ProductBrowserClient.fetch_page", new_callable=AsyncMock) as browser:
            with self.assertRaises(UnsafeProductURLError):
                await parser.parse(None, "https://u.jd.com/abc")
            browser.assert_not_awaited()
    def test_links_and_spoof_rejection(self):
        parser = JDParser()
        for url in ("https://item.jd.com/12345.html", "https://item.jd.com/product/abc_X.html",
                    "https://item.m.jd.com/product/12345.html", "https://u.jd.com/abc"):
            self.assertTrue(parser.can_parse(url), url)
        for url in ("https://item.jd.com.evil.test/12345.html", "https://user@item.jd.com/12345.html",
                    "https://item.jd.com:8888/12345.html", "https://item.jd.com/foo"):
            self.assertFalse(parser.can_parse(url), url)

    async def test_card_only_then_detail_images_no_recommendations(self):
        parser = JDParser(browser_fallback=False)
        parser._fetch_page = AsyncMock(return_value=("https://item.jd.com/12345.html", PAGE))
        card = await parser.parse(None, "https://item.jd.com/12345.html")
        self.assertEqual(card["title"], "测试手机 16GB")
        self.assertEqual(card["image_urls"], [])
        self.assertEqual(card["product_info"]["price_text"], "暂未获取")
        detail = await parser.parse_detail(None, "https://item.jd.com/12345.html")
        self.assertEqual(len(detail["image_urls"]), 5)
        self.assertFalse(any("other" in u for group in detail["image_urls"] for u in group))

    async def test_card_keeps_working_modern_product_link(self):
        url = "https://item.jd.com/product/token_ABC.html"
        parser = JDParser(browser_fallback=False)
        parser._fetch_page = AsyncMock(return_value=(url, PAGE))
        self.assertEqual((await parser.parse(None, url))["url"], url)

    def test_product_identity_must_match(self):
        with self.assertRaisesRegex(RuntimeError, "不匹配"):
            extract_product(PAGE, "99999")

    def test_matching_price_range_is_preserved(self):
        structured = '<script type="application/ld+json">{"@type":"Product","sku":"12345","offers":{"lowPrice":"1999","highPrice":"2999"}}</script>'
        self.assertEqual(extract_product(PAGE + structured, "12345")["price_text"], "¥1999–2999")

    def test_json_ld_price_requires_matching_identity(self):
        wrong = '<script type="application/ld+json">{"@type":"Product","sku":"99999","offers":{"price":"1"}}</script>'
        self.assertEqual(extract_product(PAGE + wrong, "12345")["price_text"], "暂未获取")
        right = wrong.replace('"99999"', '"12345"').replace('"1"', '"1999.00"')
        self.assertEqual(extract_product(PAGE + right, "12345")["price_text"], "¥1999.00")

    async def test_cap_and_missing_description_are_explicit(self):
        page = PAGE.replace('<img data-url="jfs/main2.jpg">', ''.join(f'<img data-url="jfs/{i}.jpg">' for i in range(30)))
        parser = JDParser(browser_fallback=False)
        parser._fetch_page = AsyncMock(return_value=("https://item.jd.com/12345.html", page))
        data = await parser.parse_detail(None, "https://item.jd.com/12345.html")
        self.assertEqual(len(data["image_urls"]), 20)
        self.assertIn("20", data["desc"])
