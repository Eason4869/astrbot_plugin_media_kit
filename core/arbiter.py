"""消息表情仲裁与解析状态反馈模块。

基于 CQHTTP（OneBot v11）贴表情能力实现两件事：

1. 多 Bot 仲裁：同一条链接消息可能被群内多个 Bot 同时看到，
   通过固定表情的点赞用户列表做弱一致分布式仲裁，保证只有一个 Bot 解析。
   协议与 Zhalslar/astrbot_plugin_parser 的 EmojiLikeArbiter 兼容，
   不同插件的 Bot 之间也能互相仲裁。
2. 解析状态反馈：Bot 在被解析的链接消息上贴表情，
   让用户直观看到「已识别 → 解析中 → 成功/失败」的状态。

本模块不依赖任何机器人框架，仅假设 bot 对象支持 CQHTTP 标准 action
（set_msg_emoji_like / fetch_emoji_like），框架侧负责构造上下文。
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from .logger import logger


@dataclass(frozen=True)
class ArbiterContext:
    """仲裁所需的最小不可变上下文。

    任一字段缺失或非法，均视为不满足协议前提。

    Attributes:
        message_id: 被解析链接所在消息的 message_id。
        msg_time: 消息时间戳（秒），用于确定性递补排序。
        self_id: 当前 Bot 的 QQ 号。
    """

    message_id: int
    msg_time: int
    self_id: int


class EmojiLikeArbiter:
    """基于 CQHTTP 表情点赞状态的弱一致分布式仲裁器（支持确定性递补）。

    协议特性：
    - 仲裁顺序一次性确定
    - 递补不重新仲裁，仅推进顺序指针
    - 表情 124 作为“胜出权存在性证明”
    """

    # ================= 协议常量（与参考实现保持一致，严禁配置化） =================

    _EMOJI_ID = 289
    _EMOJI_TYPE = "1"
    _WAIT_SEC = 1.0

    _FEEDBACK_EMOJI_ID = 124
    _FEEDBACK_EMOJI_TYPE = "1"
    _FEEDBACK_WAIT_SEC = 0.7

    _TIME_SLICE = 60

    async def compete(self, bot: Any, ctx: ArbiterContext) -> bool:
        """执行一次完整的 EmojiLikeArbiter 仲裁流程。

        Args:
            bot: 任意 CQHTTP Bot（支持 set_msg_emoji_like / fetch_emoji_like）。
            ctx: 仲裁上下文。

        Returns:
            当前 Bot 是否为实际胜出者。
        """
        mid = ctx.message_id

        # Phase 1：初始窗口检测，已有其他 Bot 占坑则直接退出。
        if await self._fetch_users(bot, mid, self._EMOJI_ID, self._EMOJI_TYPE):
            return False

        # Phase 2：占坑。
        try:
            await bot.set_msg_emoji_like(
                message_id=mid,
                emoji_id=self._EMOJI_ID,
                emoji_type=self._EMOJI_TYPE,
                set=True,
            )
        except Exception as e:
            logger.debug(f"[仲裁] 贴占坑表情失败，放弃仲裁: {e}")
            return False

        # Phase 3：仲裁窗口等待。
        await asyncio.sleep(self._WAIT_SEC)

        # Phase 4：参与者收集。
        users = await self._fetch_users(bot, mid, self._EMOJI_ID, self._EMOJI_TYPE)
        if not users:
            # 极端 API 延迟兜底：视为成功。
            return True

        # Phase 5：胜出顺序计算（仅一次）。
        order = self._decide_order(users, ctx.msg_time)
        if not order:
            return False

        # Fast-Path：单参与者。
        if len(order) == 1:
            return order[0] == ctx.self_id

        # Phase 6：确定性递补确认。
        for candidate in order:
            if candidate == ctx.self_id:
                try:
                    await bot.set_msg_emoji_like(
                        message_id=mid,
                        emoji_id=self._FEEDBACK_EMOJI_ID,
                        emoji_type=self._FEEDBACK_EMOJI_TYPE,
                        set=True,
                    )
                except Exception:
                    pass

            await asyncio.sleep(self._FEEDBACK_WAIT_SEC)

            if await self._has_feedback(bot, mid):
                return candidate == ctx.self_id

        return False

    async def _fetch_users(
        self,
        bot: Any,
        message_id: int,
        emoji_id: int,
        emoji_type: str,
    ) -> list:
        """拉取指定表情的点赞用户 QQ 号列表。"""
        try:
            resp = await bot.fetch_emoji_like(
                message_id=message_id,
                emoji_id=str(emoji_id),
                emojiId=str(emoji_id),
                emojiType=emoji_type,
                count=20,
            )
        except Exception:
            return []

        likes = (resp or {}).get("emojiLikesList") or []
        users = []
        for item in likes:
            try:
                users.append(int(item["tinyId"]))
            except (KeyError, TypeError, ValueError):
                continue
        return users

    async def _has_feedback(self, bot: Any, message_id: int) -> bool:
        """判断是否观测到胜出确认信号（表情 124）。"""
        users = await self._fetch_users(
            bot,
            message_id,
            self._FEEDBACK_EMOJI_ID,
            self._FEEDBACK_EMOJI_TYPE,
        )
        return bool(users)

    def _decide_order(self, users: list, msg_time: int) -> list:
        """基于确定性规则生成胜出递补顺序。

        保证：
        - 顺序在所有 Bot 上完全一致
        - 不随时间推进而变化
        """
        participants = sorted(set(users))
        if not participants:
            return []

        base = (msg_time // self._TIME_SLICE) % len(participants)
        return [
            participants[(base + i) % len(participants)]
            for i in range(len(participants))
        ]


# ── 解析状态反馈表情 ──────────────────────────────────────

# QQ 贴表情（戳一戳/表情回应）使用的 emoji_id：
# 289 为仲裁占坑表情（👀 语义），124 为仲裁胜出确认表情，
# 以下两个用于解析结果反馈。
STATUS_PARSING_EMOJI_ID = 289
STATUS_SUCCESS_EMOJI_ID = 324
STATUS_FAILED_EMOJI_ID = 336


async def _safe_set_emoji_like(
    bot: Any,
    message_id: int,
    emoji_id: int,
    emoji_type: str = "1",
) -> bool:
    """安全贴表情，任何失败都不影响主流程。

    Args:
        bot: CQHTTP Bot 实例。
        message_id: 目标消息 ID。
        emoji_id: QQ 表情 ID。
        emoji_type: 表情类型。

    Returns:
        是否贴成功。
    """
    try:
        await bot.set_msg_emoji_like(
            message_id=message_id,
            emoji_id=emoji_id,
            emoji_type=emoji_type,
            set=True,
        )
        return True
    except Exception as e:
        logger.debug(f"[表情反馈] 贴表情 {emoji_id} 失败: {e}")
        return False


def build_arbiter_context(event: Any) -> Optional[ArbiterContext]:
    """从 AstrBot 事件构造仲裁上下文。

    仅在 aiocqhttp（OneBot v11）平台、群聊消息、且 Bot 支持贴表情 action 时
    返回有效上下文；其他平台或缺少能力时返回 None。

    Args:
        event: AstrBot 消息事件。

    Returns:
        仲裁上下文；不满足前提时返回 None。
    """
    try:
        if event.is_private_chat():
            return None
        bot = getattr(event, "bot", None)
        if bot is None:
            return None
        if not all(
            callable(getattr(bot, name, None))
            for name in ("set_msg_emoji_like", "fetch_emoji_like")
        ):
            return None
        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return None
        message_id = int(raw.get("message_id"))
        msg_time = int(raw.get("time"))
        self_id = int(raw.get("self_id"))
    except (TypeError, ValueError, AttributeError):
        return None
    return ArbiterContext(
        message_id=message_id,
        msg_time=msg_time,
        self_id=self_id,
    )


async def mark_parse_success(event: Any) -> None:
    """解析成功后在链接消息上贴成功表情。"""
    ctx = build_arbiter_context(event)
    if ctx is None:
        return
    await _safe_set_emoji_like(
        event.bot, ctx.message_id, STATUS_SUCCESS_EMOJI_ID
    )


async def mark_parse_failed(event: Any) -> None:
    """解析失败（无任何有效结果）后在链接消息上贴失败表情。"""
    ctx = build_arbiter_context(event)
    if ctx is None:
        return
    await _safe_set_emoji_like(
        event.bot, ctx.message_id, STATUS_FAILED_EMOJI_ID
    )
