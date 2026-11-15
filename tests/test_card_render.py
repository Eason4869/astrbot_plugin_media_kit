"""四种卡片布局都应在主体底边结束，不附带半透明阴影条。"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import support  # noqa: F401,E402
from core.rika_render.data import Author, ParseResult, Platform  # noqa: E402
from core.rika_render.render import ShareCardRenderer  # noqa: E402


class TestCardBounds(unittest.TestCase):
    def test_all_layouts_end_at_opaque_card_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cover = root / "cover.png"
            Image.new("RGB", (640, 360), (70, 110, 160)).save(cover)
            result = ParseResult(
                platform=Platform("douyin", "抖音"),
                title="录音棚完整版上线",
                author=Author("刘老根传媒"),
                url="https://www.douyin.com/video/7707709905020505359",
            )
            for layout in ("standard", "magazine", "immersive", "feed"):
                for theme in ("dark", "light"):
                    for hero in (None, cover):
                        with self.subTest(layout=layout, theme=theme, cover=bool(hero)):
                            renderer = ShareCardRenderer(root, width=520, layout=layout, theme=theme)
                            path = renderer._render_sync(
                                result, {"hero": hero, "avatar": None, "grid": []},
                                root / f"{layout}-{theme}-{bool(hero)}.png",
                            )
                            with Image.open(path) as image:
                                alpha = image.getchannel("A")
                                center_strip = alpha.crop((image.width // 2, image.height - 14,
                                                           image.width // 2 + 1, image.height))
                                self.assertEqual(center_strip.getextrema(), (255, 255))
                                self.assertLess(alpha.getpixel((0, image.height - 1)), 255)


if __name__ == "__main__":
    unittest.main()
