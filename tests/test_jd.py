import json
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


def mobile_page(price="3689.00", *, masked=False):
    # Shape captured from the user's real Switch2 share, with a different variant first.
    item = {"newColorSize": [{"skuId": "20341866190", "imagePath": "jfs/wrong-variant.jpg"}],
            "skuId": "10235967540747", "skuName": "任天堂 港版Switch2国际多语言",
            "image": ["jfs/switch2-main.jpg", "jfs/switch2-second.jpg"]}
    info = {"product": {"skuId": item["skuId"], "skuName": item["skuName"]},
            "priceFloor": {"price": "3??9" if masked else "font-encoded", "ext": {"jdPrice": "3??9" if masked else price}},
            "commonInfo": {"urgeLogin": masked}, "taxinfov2": {"taxPrice": "335.70"}}
    return '<script>window._itemOnly = (' + json.dumps({"item": item}, ensure_ascii=False) + ');\nwindow._itemInfo = (' + json.dumps(info, ensure_ascii=False)[:-1] + ',\n});</script>'


class TestJD(unittest.IsolatedAsyncioTestCase):
    async def test_official_risk_redirect_is_reported_without_following_it(self):
        class Response:
            status = 302
            headers = {"Location": "https://cfe.m.jd.com/privatedomain/risk_handler/03101900/?returnurl=test"}
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
        session = type("Session", (), {})()
        from unittest.mock import Mock
        session.get = Mock(return_value=Response())
        with self.assertRaisesRegex(RuntimeError, "人工验证"):
            await JDParser()._fetch_page(session, "https://mitem.jd.hk/product/10235967540747.html")
        self.assertEqual(session.get.call_count, 1)

    def test_actual_hk_share_is_recognized(self):
        parser = JDParser()
        text = '【京东】https://3.jd.hk/104-oHdd 「港版Switch2国际多语言」 点击链接直接打开'
        self.assertEqual(parser.extract_links(text), ["https://3.jd.hk/104-oHdd"])
        self.assertTrue(parser.can_parse("https://mitem.jd.hk/product/10235967540747.html"))
        for url in ("https://3.jd.hk.evil.test/104-oHdd", "https://user@3.jd.hk/104-oHdd"):
            self.assertFalse(parser.can_parse(url))

    def test_mobile_state_uses_target_sku_and_public_numeric_price(self):
        result = extract_product(mobile_page(), "10235967540747")
        self.assertEqual(result["sku"], "10235967540747")
        self.assertEqual(result["price_text"], "¥3689.00")
        self.assertEqual(len(result["main_images"]), 2)
        self.assertFalse(any("wrong-variant" in u for u in result["main_images"]))

    def test_mobile_mask_is_not_decoded_or_replaced_with_tax(self):
        result = extract_product(mobile_page(masked=True), "10235967540747")
        self.assertEqual(result["price_text"], "暂未获取")
        self.assertEqual(result["price_status"], "login_required")

    def test_mobile_identity_mismatch_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "不匹配"):
            extract_product(mobile_page(), "10121597563336")

    async def test_legacy_numeric_page_tries_same_sku_mobile_before_browser(self):
        parser = JDParser(browser_fallback=False)
        # Real Switch2 shape with the same ID as the requested numeric link.
        source = mobile_page().replace("10235967540747", "10121597563336")
        parser._fetch_page = AsyncMock(side_effect=[
            ("https://item.jd.com/10121597563336.html", "<html>generic shell</html>"),
            ("https://item.m.jd.com/product/10121597563336.html", source)])
        result = await parser.parse(None, "https://item.jd.com/10121597563336.html")
        self.assertEqual(parser._fetch_page.await_args_list[1].args[1], "https://item.m.jd.com/product/10121597563336.html")
        self.assertEqual(result["product_info"]["sku"], "10121597563336")

    async def test_short_link_checks_resolved_numeric_identity(self):
        parser = JDParser(browser_fallback=False)
        parser._fetch_page = AsyncMock(return_value=("https://mitem.jd.hk/product/999999.html", mobile_page()))
        with self.assertRaisesRegex(RuntimeError, "不匹配"):
            await parser.parse(None, "https://3.jd.hk/104-oHdd")
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
