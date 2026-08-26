"""回复决策引擎。

所有平台共用这一份逻辑：给一条 IncomingMessage，返回 ReplyDecision。
引擎本身不发消息、不碰网络（除非 fallback 走 LLM），因此可以单测覆盖。

拒绝顺序是有意为之的：安全类判断（黑名单、敏感词）永远排在
频率限制之前，这样即使把冷却时间调到 0 也不会误回转账类消息。
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections import deque
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Callable, Optional

from .config import Config
from .models import IncomingMessage, ReplyDecision, chat_identity, normalize_chat_name

logger = logging.getLogger(__name__)

_DAY_SECONDS = 24 * 3600
_HOUR_SECONDS = 3600

# 这些词一旦出现就永不自动回复，无论配置怎么写。
# 自动回复「好的」给一条转账/验证码消息的代价，远高于漏回一条正常消息。
HARD_BLOCK_KEYWORDS = (
    "转账",
    "红包",
    "验证码",
    "银行卡",
    "身份证",
    "密码",
    "借钱",
    "急用钱",
    "汇款",
    "付款码",
)


class ReplyEngine:
    def __init__(
        self,
        config: Config,
        llm_reply: Optional[Callable[[IncomingMessage, Config], Optional[str]]] = None,
        state_path: Optional[str | Path] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self._llm_reply = llm_reply
        self._clock = clock
        self._state_path = Path(state_path) if state_path else None

        # 下面所有的键都是「会话身份」而不是各端上报的 chat_id：
        # 微信多端同时在线时，安卓传 android:xxx、macOS 传 macos:xxx，
        # 用 chat_id 会分裂成两套独立冷却，对方就收到两条重复回复。
        # 归一化到会话名之后，各端共享同一份额度。
        # chat 身份 -> 上次回复时间戳
        self._last_reply_at: dict[str, float] = {}
        # chat 身份 -> 当天已回复的时间戳列表
        self._chat_replies: dict[str, list[float]] = {}
        # 账号 -> 最近一小时的回复时间戳。按账号隔离而不是全局共用：
        # 一个号的规则写错刷爆保险丝，不该把另一个号也一起饿死。
        self._recent_replies: dict[str, deque[float]] = {}
        # 规则名 -> 上次用过的文案下标。
        #
        # 刻意用「全局」而不是「每会话」计数：按会话算的话，每个人拿到的
        # 都是 replies[0]——一百个人收到一模一样的一句话，这是批量发送的
        # 典型特征。全局轮换让相邻两条发出去的内容不同。
        self._rotation: dict[str, int] = {}
        # 账号 -> 上一条回复的「预计发出时刻」。用来拉开跨会话的间隔，
        # 记的是发送时刻而不是决策时刻，这样连续几条能正确地依次排开。
        self._last_send_at: dict[str, float] = {}
        # 账号 -> 当天已回复的时间戳
        self._daily_replies: dict[str, list[float]] = {}
        # chat 身份 -> (最后处理的消息内容, 时间戳)，用于跨端去重
        self._last_seen: dict[str, tuple[str, float]] = {}

        self._load_state()

    # ------------------------------------------------------------------ 决策

    def decide(self, message: IncomingMessage) -> ReplyDecision:
        cfg = self.config
        now = self._clock()

        if not cfg.enabled:
            return ReplyDecision.skip("总开关关闭")

        if not message.text:
            return ReplyDecision.skip("空消息")

        # ---- 安全类判断（永远优先） ----
        blocked = self._hard_blocked(message.text)
        if blocked:
            return ReplyDecision.skip(f"命中硬性敏感词 {blocked!r}，人工处理")

        # 归一化后比对：用户手打的名字常有多余空格或大小写差异，
        # 而比对失败是静默的——名单形同虚设，用户还不知道
        name = normalize_chat_name(message.chat_name)
        if name in {normalize_chat_name(c) for c in cfg.scope.block_contacts}:
            return ReplyDecision.skip(f"{message.chat_name} 在黑名单里")

        soft_blocked = next((k for k in cfg.scope.block_keywords if k in message.text), None)
        if soft_blocked:
            return ReplyDecision.skip(f"命中自定义屏蔽词 {soft_blocked!r}")

        if cfg.scope.allow_contacts and name not in {
            normalize_chat_name(c) for c in cfg.scope.allow_contacts
        }:
            return ReplyDecision.skip(f"{message.chat_name} 不在白名单里")

        # ---- 会话类型 ----
        if message.is_group:
            policy = cfg.scope.reply_to_group
            if policy == "never":
                return ReplyDecision.skip("群消息不回")
            if policy == "only_at_me" and not message.mentioned_me:
                return ReplyDecision.skip("群消息未 @ 我")
        elif not cfg.scope.reply_to_private:
            return ReplyDecision.skip("私聊不回")

        # ---- 时间段 ----
        if not self._within_active_hours(now):
            return ReplyDecision.skip("不在自动回复时段内")

        identity = chat_identity(message)

        # ---- 跨端去重 ----
        # 同一条消息被另一端抢先处理过，这里直接跳过。
        # 单独成一条判断而不是靠冷却兜底，是为了让日志能一眼看出
        # 「不是被限流，是另一端已经回了」。
        seen = self._last_seen.get(identity)
        if seen and seen[0] == message.text:
            elapsed = now - seen[1]
            if elapsed < cfg.limits.cross_device_dedup_seconds:
                return ReplyDecision.skip(
                    f"{elapsed:.0f}s 前另一端已处理过同样内容，跨端去重"
                )
        self._last_seen[identity] = (message.text, now)

        # ---- 频率限制 ----
        limit_reason = self._rate_limited(identity, message.account, now)
        if limit_reason:
            return ReplyDecision.skip(limit_reason)

        # ---- AI 模式：整段交给模型，规则不参与 ----
        # 安全类判断已经在上面做完了，模型只负责「说什么」，
        # 不负责「该不该说」——那部分不能交给概率性的东西。
        if cfg.reply_mode == "ai":
            return self._ai_reply(message, identity, now)

        # ---- 命中规则 ----
        for rule in cfg.rules:
            if rule.matches(message.text):
                text = self._pick_reply(identity, rule.name, rule.replies)
                return self._commit(message, identity, text, f"命中规则 {rule.name!r}", rule.name, now)

        # ---- 兜底 ----
        if cfg.reply_mode == "rules":
            return ReplyDecision.skip("无规则命中（当前是纯规则模式）")

        if cfg.fallback.kind == "none":
            return ReplyDecision.skip("无规则命中，且未配置兜底回复")

        if cfg.fallback.kind == "text":
            if not cfg.fallback.text:
                return ReplyDecision.skip("fallback.type 为 text 但 fallback.text 为空")
            return self._commit(message, identity, cfg.fallback.text, "兜底文案", None, now)

        # fallback.kind == "llm"
        return self._ai_reply(message, identity, now)

    def _ai_reply(self, message, identity: str, now: float) -> ReplyDecision:
        """交给模型生成。任何失败都退化成「不回复」，绝不乱发。"""
        if self._llm_reply is None:
            return ReplyDecision.skip("未接入模型客户端")
        try:
            generated = self._llm_reply(message, self.config)
        except Exception as exc:  # 生成失败绝不能拖垮整条链路
            logger.warning("生成失败，跳过本条: %s", exc)
            return ReplyDecision.skip(f"生成失败: {exc}")
        if not generated:
            return ReplyDecision.skip("模型未返回可用内容")
        return self._commit(message, identity, generated, "AI 生成", None, now)

    # ------------------------------------------------------------------ 内部

    def _hard_blocked(self, text: str) -> Optional[str]:
        return next((k for k in HARD_BLOCK_KEYWORDS if k in text), None)

    def _within_active_hours(self, now: float) -> bool:
        ranges = self.config.active_hours
        if not ranges:
            return True
        current = datetime.fromtimestamp(now).time()
        return any(self._in_range(current, start, end) for start, end in ranges)

    @staticmethod
    def _in_range(current: dtime, start: dtime, end: dtime) -> bool:
        if start <= end:
            return start <= current <= end
        # 跨零点，例如 22:00-02:00
        return current >= start or current <= end

    def _rate_limited(self, identity: str, account: str, now: float) -> Optional[str]:
        limits = self.config.limits

        last = self._last_reply_at.get(identity)
        if last is not None and now - last < limits.per_chat_cooldown_seconds:
            remaining = int(limits.per_chat_cooldown_seconds - (now - last))
            return f"该会话冷却中，还剩 {remaining}s"

        today = [t for t in self._chat_replies.get(identity, []) if now - t < _DAY_SECONDS]
        self._chat_replies[identity] = today
        if (
            limits.max_replies_per_chat_per_day > 0
            and len(today) >= limits.max_replies_per_chat_per_day
        ):
            return f"该会话今日已达上限 {limits.max_replies_per_chat_per_day} 条"

        recent = self._recent_replies.setdefault(account, deque())
        while recent and now - recent[0] >= _HOUR_SECONDS:
            recent.popleft()
        if len(recent) >= limits.global_max_replies_per_hour:
            return f"账号 {account!r} 一小时上限 {limits.global_max_replies_per_hour} 条已满"

        daily = [t for t in self._daily_replies.get(account, []) if now - t < _DAY_SECONDS]
        self._daily_replies[account] = daily
        if len(daily) >= limits.global_max_replies_per_day:
            return f"账号 {account!r} 今日上限 {limits.global_max_replies_per_day} 条已满"

        return None

    def _pick_reply(self, identity: str, rule_name: str, replies: list[str]) -> str:
        """轮换文案。

        计数是全局的（只按规则名），不按会话分开。按会话算的话，每个人
        拿到的都是 replies[0]，一百个人收到一模一样的一句话——那正是
        批量发送最容易被认出来的地方。
        """
        index = self._rotation.get(rule_name, -1) + 1
        self._rotation[rule_name] = index
        return replies[index % len(replies)]

    def _commit(
        self,
        message: IncomingMessage,
        identity: str,
        text: str,
        reason: str,
        rule_name: Optional[str],
        now: float,
    ) -> ReplyDecision:
        """记账并生成最终决策。只有真正要发的消息才走到这里。"""
        if self.config.signature:
            text = f"{text}{self.config.signature}"

        limits = self.config.limits

        # ---- 延迟 ----
        # 三个部分：
        #   1. 基础随机延迟——秒回是最明显的机器特征
        #   2. 按字数追加的「打字时间」——真人打 30 个字比打「嗯」慢
        #   3. 跨会话的最小间隔——见下
        delay = random.uniform(limits.min_delay_seconds, limits.max_delay_seconds)
        delay += len(text) * limits.typing_seconds_per_char

        # 拉开与上一条回复的间隔。
        #
        # 冷却是按会话算的，所以三十个人同时发消息时，程序本来会在几十秒内
        # 挨个回完——真人不可能一秒切一个会话。这里不丢消息，只是把发送
        # 时刻往后推，于是多条回复会自然地依次排开。
        account = message.account
        earliest = self._last_send_at.get(account, 0.0) + limits.global_min_interval_seconds
        send_at = max(now + delay, earliest)
        delay = send_at - now
        self._last_send_at[account] = send_at

        self._last_reply_at[identity] = now
        self._chat_replies.setdefault(identity, []).append(now)
        self._recent_replies.setdefault(account, deque()).append(now)
        self._daily_replies.setdefault(account, []).append(now)
        self._save_state()

        logger.info(
            "[%s/%s] %s -> %s (%s)",
            message.account, message.platform, message.chat_name, text, reason,
        )
        return ReplyDecision(
            should_reply=True,
            reason=reason,
            text=text,
            delay_seconds=round(delay, 2),
            rule_name=rule_name,
        )

    # ------------------------------------------------------- 状态持久化（可选）

    def _load_state(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("状态文件损坏，从空状态开始: %s", exc)
            return
        self._last_reply_at = data.get("last_reply_at", {})
        self._chat_replies = data.get("chat_replies", {})
        self._recent_replies = {
            k: deque(v) for k, v in data.get("recent_replies", {}).items()
        }
        self._rotation = data.get("rotation", {})
        self._daily_replies = data.get("daily_replies", {})
        self._last_seen = {
            k: tuple(v) for k, v in data.get("last_seen", {}).items()
        }
        # _last_send_at 刻意不持久化：它只影响未来 45 秒内的排队，
        # 重启后从零开始最多让第一条回复早发一点，没有意义再存一份。

    def _save_state(self) -> None:
        if not self._state_path:
            return
        payload = {
            "last_reply_at": self._last_reply_at,
            "chat_replies": self._chat_replies,
            "recent_replies": {k: list(v) for k, v in self._recent_replies.items()},
            "rotation": self._rotation,
            "daily_replies": self._daily_replies,
            "last_seen": {k: list(v) for k, v in self._last_seen.items()},
        }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("状态写入失败: %s", exc)
