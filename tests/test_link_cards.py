from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import support
from core.rika_render.data import ParseResult, Platform
from core.rika_render.render import ShareCardRenderer
from core.rika_render.adapter import build_parse_result


class TestLinkCards(unittest.TestCase):
    def test_product_cover_is_not_a_video(self):
        with tempfile.TemporaryDirectory() as directory:
            renderer = ShareCardRenderer(Path(directory), layout="magazine")
            result = ParseResult(platform=Platform("jd", "京东"), title="商品")
            self.assertFalse(renderer._prep(result, {"hero": Path("product.jpg")})["is_video_hero"])

    def test_magazine_title_uses_matching_measurement_and_draw_font(self):
        with tempfile.TemporaryDirectory() as directory:
            renderer = ShareCardRenderer(Path(directory), width=700, layout="magazine")
            result = ParseResult(platform=Platform("github", "GitHub"),
                                 title="Eason4869/astrbot_plugin_media_kit_with_a_very_long_name")
            with patch.object(renderer, "_draw_text", wraps=renderer._draw_text) as draw:
                renderer._render_sync(result, {"hero": None, "grid": [], "avatar": None}, Path(directory)/"card.png")
            titles = [call for call in draw.call_args_list if len(call.args) > 3 and call.args[3] == 36]
            self.assertTrue(titles)
            for call in titles:
                self.assertLessEqual(renderer._text_width(call.args[2], renderer._font(36, bold=True)), 628)

    def test_card_labels_match_resource(self):
        result = build_parse_result({"platform": "jd", "title": "商品"})
        self.assertEqual(result.content_type, "商品")
