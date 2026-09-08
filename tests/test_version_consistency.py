"""版本一致性测试：Config.PLUGIN_VERSION 与 metadata.yaml / main.py 注册版本保持一致。"""
import os
import re
import sys
import unittest

# 自举路径：兼容 `python -m unittest discover -s tests` 等任意启动方式。
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import support  # noqa: F401,E402


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _read(rel_path: str) -> str:
    with open(os.path.join(_repo_root(), rel_path), encoding="utf-8") as fh:
        return fh.read()


class TestVersionConsistency(unittest.TestCase):
    def test_constants_version(self):
        import core.constants

        self.assertTrue(
            re.fullmatch(r"\d+\.\d+\.\d+", core.constants.Config.PLUGIN_VERSION)
        )

    def test_metadata_matches_constants(self):
        import core.constants

        metadata = _read("metadata.yaml")
        match = re.search(r"^version:\s*v?(?P<ver>[\d.]+)", metadata, re.MULTILINE)
        self.assertIsNotNone(match, "metadata.yaml 缺少 version 行")
        self.assertEqual(
            match.group("ver"),
            core.constants.Config.PLUGIN_VERSION,
            "metadata.yaml 版本与 Config.PLUGIN_VERSION 不一致",
        )

    def test_main_register_matches_constants(self):
        import core.constants

        main_src = _read("main.py")
        # main.py 应通过 Config.PLUGIN_VERSION 引用版本，而非手写字符串
        self.assertIn(
            "Config.PLUGIN_VERSION",
            main_src,
            "main.py 应引用 Config.PLUGIN_VERSION 作为注册版本",
        )
        # 若仍有手写的独立版本字符串常量则视为不一致（排除注释）
        # 用 register 块后再单独校验太脆弱，此处校验弱一致：文件中不允许出现
        # 形如 "数字.数字.数字" 的明文版本号（README/CHANGELOG 不在此列）
        for number in re.findall(r'"(\d+\.\d+\.\d+)"', main_src):
            self.assertEqual(
                number,
                core.constants.Config.PLUGIN_VERSION,
                f"main.py 出现手写版本 {number}，请改用 Config.PLUGIN_VERSION",
            )

    def test_changelog_tracks_latest(self):
        import core.constants

        changelog = _read("CHANGELOG.md")
        latest = core.constants.Config.PLUGIN_VERSION
        self.assertIn(
            f"## v{latest}",
            changelog,
            f"CHANGELOG.md 缺少最新版本 v{latest} 条目",
        )


if __name__ == "__main__":
    unittest.main()
