import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))
import support
from core.config_manager import ConfigManager
from core.parser.platform.douyin import DouyinParser


class TestDouyinConfig(unittest.TestCase):
    def test_browser_configuration_reaches_the_parser(self):
        config = ConfigManager({"parsers": {"douyin": "全部发送"}, "douyin": {
            "browser_fallback": False, "browser_path": "/opt/chromium"
        }})
        parser = next(p for p in config.create_parsers() if isinstance(p, DouyinParser))
        self.assertFalse(parser.browser_client.enabled)
        self.assertEqual(parser.browser_client.executable, "/opt/chromium")
