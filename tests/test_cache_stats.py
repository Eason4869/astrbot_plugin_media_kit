"""缓存目录统计单测。"""
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import support  # noqa: F401,E402


class TestCacheStats(unittest.TestCase):
    def test_summarize_missing_dir(self):
        from core.storage.cache_stats import format_cache_stats, summarize_cache_dir

        stats = summarize_cache_dir(os.path.join(tempfile.gettempdir(), "not-exist-mk"))
        self.assertFalse(stats.available)
        self.assertIn("不可用", format_cache_stats(stats))

    def test_summarize_empty_path(self):
        from core.storage.cache_stats import format_cache_stats, summarize_cache_dir

        self.assertIn("未配置", format_cache_stats(summarize_cache_dir("")))

    def test_summarize_counts_files(self):
        from core.storage.cache_stats import summarize_cache_dir

        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "media1")
            os.makedirs(sub)
            with open(os.path.join(sub, "a.bin"), "wb") as fh:
                fh.write(b"x" * 10)
            with open(os.path.join(tmp, "root.bin"), "wb") as fh:
                fh.write(b"y" * 5)
            stats = summarize_cache_dir(tmp)
            self.assertTrue(stats.available)
            self.assertEqual(stats.file_count, 2)
            self.assertEqual(stats.total_bytes, 15)
            self.assertGreaterEqual(stats.subdir_count, 1)
            self.assertFalse(stats.truncated)

    def test_should_emit_progress(self):
        from core.config_manager import MessageProgressConfig

        cfg = MessageProgressConfig(enabled=True, min_links=2, interval_seconds=5)
        self.assertFalse(
            cfg.should_emit(total_links=1, done_count=1, last_emit_at=None, now=0)
        )
        self.assertTrue(
            cfg.should_emit(total_links=2, done_count=1, last_emit_at=None, now=0)
        )
        self.assertFalse(
            cfg.should_emit(total_links=2, done_count=2, last_emit_at=0.0, now=4.9)
        )
        self.assertTrue(
            cfg.should_emit(total_links=2, done_count=2, last_emit_at=0.0, now=5.0)
        )
        disabled = MessageProgressConfig(enabled=False)
        self.assertFalse(
            disabled.should_emit(total_links=3, done_count=1, last_emit_at=None, now=0)
        )


if __name__ == "__main__":
    unittest.main()
