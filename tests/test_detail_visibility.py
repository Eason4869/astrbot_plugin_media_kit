"""Exercise the real node-building body without importing an AstrBot runtime."""
import ast
from pathlib import Path
import typing
import unittest
import support
from core.message_text import split_message_text
from core.metadata_visibility import text_metadata_field_enabled


class Plain:
    def __init__(self, text):
        self.text = text


def node_builder():
    source = Path(__file__).resolve().parents[1] / "core/message_adapter/node_builder.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"_build_node_parts_for_link", "_split_plain_node", "_resolve_output_flag"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    namespace = {key: getattr(typing, key) for key in ("Dict", "Any", "List", "Optional", "Union")}
    namespace.update(Plain=Plain, Image=object, Video=object, split_message_text=split_message_text,
                     text_metadata_field_enabled=text_metadata_field_enabled,
                     build_media_nodes=lambda *args: [], build_text_node=lambda *args: None,
                     build_hot_comments_node=lambda *args: None)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace["_build_node_parts_for_link"]


class TestDetailVisibility(unittest.TestCase):
    def test_summary_source_is_hidden_but_other_detail_text_remains_available(self):
        build = node_builder()
        self.assertEqual(build({"detail_text": "long README source", "detail_text_visible": False})[0], [])
        nodes, _ = build({"detail_text": "explicit product details"})
        self.assertIn("explicit product details", nodes[0].text)

    def test_media_only_still_suppresses_detail_text(self):
        self.assertEqual(node_builder()({"detail_text": "body", "_enable_text_metadata": False})[0], [])
