"""表情仲裁器单测：顺序确定性、单参与者胜出、仲裁上下文与状态贴图。"""
import asyncio
import unittest
from unittest import IsolatedAsyncioTestCase

from . import support  # noqa: F401

from core.arbiter import (
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

    async def set_msg_emoji_like(self, message_id, emoji_id, emoji_type="1", set=True):
        self.set_calls.append((message_id, int(emoji_id), emoji_type, bool(set)))
        key = int(emoji_id)
        if set:
            self._likes.setdefault(key, set()).add(self.self_qq)
        else:
            self._likes.get(key, set()).discard(self.self_qq)

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

    def test_participants_sorted_deduped(self):
        order = self.arbiter._decide_order([5, 3, 3, 1, 5], msg_time=123)
        self.assertEqual(order, [1, 3, 5])

    def test_empty_returns_empty(self):
        self.assertEqual(self.arbiter._decide_order([], 1), [])


class TestArbiterCompetition(IsolatedAsyncioTestCase):
    async def test_no_prior_occupier_single_bot_wins(self):
        arbiter = EmojiLikeArbiter()
        bot = _MockBot(self_qq=10001)
        ctx = ArbiterContext(message_id=7, msg_time=999, self_id=10001)
        # 无其他机器人占坑 -> 本机占坑后 fetch 只看到自己 -> 胜出
        won = await _patched_compete(arbiter, bot, ctx)
        self.assertTrue(won)

    async def test_other_bot_occupies_first_loses(self):
        arbiter = EmojiLikeArbiter()
        bot = _MockBot(self_qq=10002)
        # 另一个 bot(10001)先占了仲裁表情
        bot._likes[arbiter._EMOJI_ID] = {10001}
        ctx = ArbiterContext(message_id=7, msg_time=999, self_id=10002)
        won = await _patched_compete(arbiter, bot, ctx)
        self.assertFalse(won)


async def _patched_compete(arbiter, bot, ctx):
    """用零等待垫片让 compete 不依赖真实 sleep。"""
    orig = asyncio.sleep
    asyncio.sleep = _noop  # type: ignore[assignment]
    try:
        return await arbiter.compete(bot, ctx)
    finally:
        asyncio.sleep = orig  # type: ignore[assignment]


async def _noop(*_args, **_kwargs):
    return None


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
