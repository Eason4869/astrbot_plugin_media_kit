"""解析频率限制 force 旁路单测。"""
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import support  # noqa: F401,E402


class _DummyParser:
    def __init__(self, name: str):
        self.name = name


class TestParseRecordForce(unittest.TestCase):
    def _make_manager(self, record_file: str):
        from core.storage.parse_record import ParseRecordManager

        return ParseRecordManager(
            record_file=record_file,
            same_link_max_count=1,
            same_link_window_seconds=3600,
            same_user_max_count=2,
            same_user_window_seconds=3600,
        )

    def test_force_bypasses_and_does_not_write(self):
        parser = _DummyParser("bilibili")
        links = [("https://b23.tv/abc", parser)]
        with tempfile.TemporaryDirectory() as tmp:
            record_file = os.path.join(tmp, "records.json")
            manager = self._make_manager(record_file)

            allowed, blocked = manager.filter_links(links, user_key="u1")
            self.assertEqual(allowed, links)
            self.assertEqual(blocked, [])

            allowed2, blocked2 = manager.filter_links(links, user_key="u1")
            self.assertEqual(allowed2, [])
            self.assertEqual(len(blocked2), 1)

            allowed3, blocked3 = manager.filter_links(
                links, user_key="u1", force=True
            )
            self.assertEqual(allowed3, links)
            self.assertEqual(blocked3, [])

            # force 不应追加计数：再普通解析仍应被拦
            allowed4, blocked4 = manager.filter_links(links, user_key="u1")
            self.assertEqual(allowed4, [])
            self.assertEqual(len(blocked4), 1)

    def test_force_returns_copy_when_disabled(self):
        from core.storage.parse_record import ParseRateLimitRule

        parser = _DummyParser("bilibili")
        links = [("https://b23.tv/xyz", parser)]
        with tempfile.TemporaryDirectory() as tmp:
            record_file = os.path.join(tmp, "records.json")
            manager = self._make_manager(record_file)
            manager.same_link = ParseRateLimitRule(0, 0)
            manager.same_user = ParseRateLimitRule(0, 0)
            allowed, blocked = manager.filter_links(links, user_key="u1", force=True)
            self.assertEqual(allowed, links)
            self.assertEqual(blocked, [])


if __name__ == "__main__":
    unittest.main()
