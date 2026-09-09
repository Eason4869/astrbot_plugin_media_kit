"""管理命令配置默认值与关键词冲突校验单测。"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import support  # noqa: F401,E402


def _base_config(**overrides):
    config = {
        "trigger": {"auto_parse": True},
        "parsers": {
            "bilibili": "全部发送",
            "douyin": "全部发送",
            "live": "全部发送",
        },
        "admin": {
            "clean_cache_keyword": "清理媒体",
            "status_keyword": "解析状态",
            "force_parse_keyword": "强制解析",
            "force_parse_admin_only": True,
            "debug": False,
        },
        "message": {
            "progress": {
                "enable": False,
                "min_links": 2,
                "interval_seconds": 5,
            }
        },
        "parse_rate_limit": {
            "blocked_reply_enabled": False,
        },
    }
    config.update(overrides)
    return config


class TestAdminCommandConfig(unittest.TestCase):
    def test_defaults(self):
        from core.config_manager import ConfigManager

        cfg = ConfigManager(_base_config())
        self.assertEqual(cfg.admin.status_keyword, "解析状态")
        self.assertEqual(cfg.admin.force_parse_keyword, "强制解析")
        self.assertTrue(cfg.admin.force_parse_admin_only)
        self.assertFalse(cfg.parse_rate_limit.blocked_reply_enabled)
        self.assertFalse(cfg.message.progress.enabled)
        self.assertEqual(cfg.message.progress.min_links, 2)
        self.assertEqual(cfg.message.progress.interval_seconds, 5)

    def test_keyword_conflict_disables_force(self):
        from core.config_manager import ConfigManager

        cfg = ConfigManager(
            _base_config(
                admin={
                    "clean_cache_keyword": "清理媒体",
                    "status_keyword": "清理媒体",
                    "force_parse_keyword": "强制解析",
                }
            )
        )
        self.assertEqual(cfg.admin.clean_cache_keyword, "清理媒体")
        self.assertEqual(cfg.admin.status_keyword, "")
        self.assertEqual(cfg.admin.force_parse_keyword, "强制解析")

    def test_keyword_conflict_disables_force_against_status(self):
        from core.config_manager import ConfigManager

        cfg = ConfigManager(
            _base_config(
                admin={
                    "clean_cache_keyword": "清理媒体",
                    "status_keyword": "解析状态",
                    "force_parse_keyword": "解析状态",
                }
            )
        )
        self.assertEqual(cfg.admin.status_keyword, "解析状态")
        self.assertEqual(cfg.admin.force_parse_keyword, "")

    def test_keyword_conflict_disables_archive(self):
        from core.config_manager import ConfigManager

        cfg = ConfigManager(
            _base_config(
                admin={
                    "clean_cache_keyword": "清理媒体",
                    "status_keyword": "解析状态",
                    "force_parse_keyword": "强制解析",
                },
                message={
                    "archive": {"command": "强制解析"},
                },
            )
        )
        self.assertEqual(cfg.admin.force_parse_keyword, "强制解析")
        self.assertEqual(cfg.message.archive.command, "")

    def test_empty_keywords_disable_commands(self):
        from core.config_manager import ConfigManager

        cfg = ConfigManager(
            _base_config(
                admin={
                    "clean_cache_keyword": "清理媒体",
                    "status_keyword": "",
                    "force_parse_keyword": "",
                }
            )
        )
        self.assertEqual(cfg.admin.status_keyword, "")
        self.assertEqual(cfg.admin.force_parse_keyword, "")

    def test_enabled_platform_modes_skips_disabled(self):
        from core.config_manager import ConfigManager

        cfg = ConfigManager(
            _base_config(
                parsers={
                    "bilibili": "全部发送",
                    "douyin": "关闭",
                    "live": "仅文本",
                }
            )
        )
        modes = dict(cfg.enabled_platform_modes())
        self.assertIn("B站", modes)
        self.assertIn("B站直播", modes)
        self.assertNotIn("抖音", modes)

    def test_progress_clamps_min_links(self):
        from core.config_manager import ConfigManager

        cfg = ConfigManager(
            _base_config(
                message={
                    "progress": {
                        "enable": True,
                        "min_links": 1,
                        "interval_seconds": 0,
                    }
                }
            )
        )
        self.assertGreaterEqual(cfg.message.progress.min_links, 2)
        self.assertGreaterEqual(cfg.message.progress.interval_seconds, 1)


if __name__ == "__main__":
    unittest.main()
