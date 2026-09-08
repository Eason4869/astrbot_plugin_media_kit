"""表情仲裁器单测：顺序确定性、单参与者胜出、仲裁上下文与状态贴图。"""
import os
import sys
import unittest
from unittest import IsolatedAsyncioTestCase

# 自举路径：兼容 `python -m unittest discover -s tests` 等任意启动方式。
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)  # tests/
sys.path.insert(0, os.path.dirname(_HERE))  # 仓库根

# 参数名 set 遮蔽内建，这里先取一份内建 set 引用。
from builtins import set as builtins_set  # noqa: E402

import support  # noqa: F401,E402

from core.arbiter import (  # noqa: E402
    ArbiterContext,
    EmojiLikeArbiter,
    build_arbiter_context,
)


class _MockBot:
    """模拟支持 set_msg_emoji_like / fetch_emoji_like 的 Bot。

    self_qq 表示“当前这台 Bot”的 QQ，只有它调用 set 时才会把自己计入。
    """

    def __init__(self, self_qq: int):
        self.self_qq = self_qq
        # emoji_id -> set(qq)
        self._likes = {}
        self.set_calls = []

    async def set_msg_emoji_like(self, message_id, emoji_id, emoji_type="1",
                                 set=True):
        self.set_calls.append((message_id, int(emoji_id), emoji_type, bool(set)))
        key = int(emoji_id)
        if set:
            self._likes.setdefault(key, builtins_set()).add(self.self_qq)
        else:
            self._likes.get(key, builtins_set()).discard(self.self_qq)

    async def fetch_emoji_like(self, message_id, emoji_id, emojiId=None,
                               emojiType="1", count=20):
        qqs = sorted(self._likes.get(int(emoji_id), set()))
        return {"emojiLikesList": [{"tinyId": str(qq)} for qq in qqs]}


class TestArbiterDecideOrder(unittest.TestCase):
    def setUp(self):
        self.arbiter = EmojiLikeArbiter()

    def test_order_is_deterministic(self):
        users = [10001, 10002, 10003]
        self.assertEqual(
            self.arbiter._decide_order(list(users), msg_time=10000),
            self.arbiter._decide_order(list(users), msg_time=10000),
        )

    def test_order_is_rotated_by_time_slice(self):
        # participants 排序后为 [1,3,5]；msg_time=123 ->
        # base = (123 // 60) % 3 = 2 -> 从索引 2(=5) 起循环移位 => [5,1,3]
        order = self.arbiter._decide_order([5, 3, 3, 1, 5], msg_time=123)
        self.assertEqual(order, [5, 1, 3])
        # 顺序是参与者集合的一个轮换（元素不重不漏）
        self.assertEqual(sorted(order), [1, 3, 5])

    def test_order_rotation_base_zero(self):
        # msg_time=0 -> base=0 -> 即排序后的原序
        order = self.arbiter._decide_order([5, 3, 1], msg_time=0)
        self.assertEqual(order, [1, 3, 5])

    def test_empty_returns_empty(self):
        self.assertEqual(self.arbiter._decide_order([], 1), [])


class TestArbiterCompetition(IsolatedAsyncioTestCase):
    async def test_no_prior_occupier_single_bot_wins(self):
        arbiter = EmojiLikeArbiter()
        bot = _MockBot(self_qq=10001)
        ctx = ArbiterContext(message_id=7, msg_time=999, self_id=10001)
        # 无其他机器人占坑 -> 本机占坑后 fetch 只看到自己 -> fast-path 胜出。
        # compete 内含约 1 秒仲裁窗口等待，属正常协议耗时。
        won = await arbiter.compete(bot, ctx)
        self.assertTrue(won)

    async def test_other_bot_occupies_first_loses(self):
        arbiter = EmojiLikeArbiter()
        bot = _MockBot(self_qq=10002)
        # 另一个 bot(10001) 已占仲裁表情 -> Phase 1 直接判负，不进入等待。
        bot._likes[arbiter._EMOJI_ID] = {10001}
        ctx = ArbiterContext(message_id=7, msg_time=999, self_id=10002)
        won = await arbiter.compete(bot, ctx)
        self.assertFalse(won)


class TestBuildArbiterContext(unittest.TestCase):
    def test_private_chat_returns_none(self):
        class _PrivateEvent:
            def is_private_chat(self):
                return True

        self.assertIsNone(build_arbiter_context(_PrivateEvent()))

    def test_no_bot_attribute_returns_none(self):
        class _Event:
            def is_private_chat(self):
                return False
            message_obj = None

        self.assertIsNone(build_arbiter_context(_Event()))


if __name__ == "__main__":
    unittest.main()
