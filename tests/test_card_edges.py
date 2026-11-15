import os
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))
import support
from core.rika_render.data import Author, ParseResult, Platform
from core.rika_render.render import ShareCardRenderer


class TestCardEdges(unittest.TestCase):
    def test_bottom_edge_has_no_shadow_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cover = root / "cover.png"
            Image.new("RGB", (640, 360), "#4670a0").save(cover)
            result = ParseResult(platform=Platform("douyin", "抖音"),
                                 title="录音棚完整版上线", author=Author("刘老根传媒"))
            for layout in ("standard", "magazine", "immersive", "feed"):
                for theme in ("dark", "light"):
                    for hero in (None, cover):
                        with self.subTest(layout=layout, theme=theme, cover=bool(hero)):
                            renderer = ShareCardRenderer(root, width=520, layout=layout, theme=theme)
                            path = renderer._render_sync(result, {"hero": hero, "avatar": None, "grid": []},
                                                         root / "card.png")
                            with Image.open(path) as image:
                                alpha = image.getchannel("A")
                                strip = alpha.crop((image.width // 2, image.height - 14,
                                                    image.width // 2 + 1, image.height))
                                self.assertEqual(strip.getextrema(), (255, 255))
                                self.assertLess(alpha.getpixel((0, image.height - 1)), 255)
