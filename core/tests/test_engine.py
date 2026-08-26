"""引擎单测。不联网、不碰微信，纯逻辑验证。"""

from __future__ import annotations

import pytest

from core.config import ConfigError, build_config
from core.engine import ReplyEngine
from core.models import IncomingMessage


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


BASE_CONFIG = {
    "enabled": True,
    "scope": {"reply_to_private": True, "reply_to_group": "only_at_me"},
    "limits": {
        "per_chat_cooldown_seconds": 600,
        "max_replies_per_chat_per_day": 3,
        "global_max_replies_per_hour": 10,
        "min_delay_seconds": 1,
        "max_delay_seconds": 2,
        "cross_device_dedup_seconds": 0,   # 默认关闭，跨端去重由专门的用例覆盖
    },
    "rules": [
        {"name": "在吗", "match": {"type": "keyword", "any": ["在吗"]}, "reply": "在的"},
    ],
    "fallback": {"type": "text", "text": "稍后回复"},
}


def make_engine(overrides: dict | None = None, clock: FakeClock | None = None) -> tuple[ReplyEngine, FakeClock]:
    data = {**BASE_CONFIG, **(overrides or {})}
    clock = clock or FakeClock()
    return ReplyEngine(build_config(data), clock=clock), clock


def msg(text: str, **kwargs) -> IncomingMessage:
    kwargs.setdefault("chat_id", "chat-1")
    kwargs.setdefault("chat_name", "小王")
    return IncomingMessage(text=text, **kwargs)


# ------------------------------------------------------------------ 基本匹配


def test_keyword_rule_hits():
    engine, _ = make_engine()
    decision = engine.decide(msg("在吗？"))
    assert decision.should_reply
    assert decision.text == "在的"
    assert decision.rule_name == "在吗"


def test_falls_back_when_no_rule_matches():
    engine, _ = make_engine()
    decision = engine.decide(msg("今天天气不错"))
    assert decision.should_reply
    assert decision.text == "稍后回复"
    assert decision.rule_name is None


def test_regex_rule():
    engine, _ = make_engine(
        {"rules": [{"name": "价格", "match": {"type": "regex", "pattern": r"多少钱|报价"}, "reply": "私聊报价"}]}
    )
    assert engine.decide(msg("这个多少钱")).text == "私聊报价"


def test_empty_message_skipped():
    engine, _ = make_engine()
    assert not engine.decide(msg("   ")).should_reply


def test_signature_appended():
    engine, _ = make_engine({"signature": "[自动]"})
    assert engine.decide(msg("在吗")).text == "在的[自动]"


# ------------------------------------------------------------------ 安全优先


@pytest.mark.parametrize("text", ["帮我转账 500", "发个红包", "验证码是多少", "借钱应急"])
def test_hard_block_keywords_never_replied(text):
    """即使冷却为 0、规则全匹配，敏感词也必须拦住。"""
    engine, _ = make_engine(
        {
            "limits": {**BASE_CONFIG["limits"], "per_chat_cooldown_seconds": 0},
            "rules": [{"name": "全匹配", "match": {"type": "always"}, "reply": "好的"}],
        }
    )
    decision = engine.decide(msg(text))
    assert not decision.should_reply
    assert "敏感词" in decision.reason


def test_hard_block_beats_rate_limit_ordering():
    """敏感词判断必须早于频率判断，否则日志会误导排查。"""
    engine, _ = make_engine()
    engine.decide(msg("在吗"))  # 先占用冷却
    decision = engine.decide(msg("帮我转账"))
    assert "敏感词" in decision.reason  # 而不是「冷却中」


def test_blocked_contact():
    engine, _ = make_engine({"scope": {**BASE_CONFIG["scope"], "block_contacts": ["老板"]}})
    assert not engine.decide(msg("在吗", chat_name="老板")).should_reply


def test_allowlist_excludes_others():
    engine, _ = make_engine({"scope": {**BASE_CONFIG["scope"], "allow_contacts": ["小王"]}})
    assert engine.decide(msg("在吗", chat_name="小王")).should_reply
    assert not engine.decide(msg("在吗", chat_id="c2", chat_name="小李")).should_reply


# ------------------------------------------------------------------ 群聊策略


def test_group_only_at_me():
    engine, _ = make_engine()
    assert not engine.decide(msg("在吗", is_group=True)).should_reply
    assert engine.decide(msg("在吗", is_group=True, mentioned_me=True)).should_reply


def test_group_never():
    engine, _ = make_engine({"scope": {**BASE_CONFIG["scope"], "reply_to_group": "never"}})
    assert not engine.decide(msg("在吗", is_group=True, mentioned_me=True)).should_reply


def test_private_disabled():
    engine, _ = make_engine({"scope": {**BASE_CONFIG["scope"], "reply_to_private": False}})
    assert not engine.decide(msg("在吗")).should_reply


# ------------------------------------------------------------------ 频率限制


def test_cooldown_blocks_second_reply():
    engine, clock = make_engine()
    assert engine.decide(msg("在吗")).should_reply
    assert not engine.decide(msg("在吗")).should_reply
    clock.advance(601)
    assert engine.decide(msg("在吗")).should_reply


def test_daily_cap_per_chat():
    engine, clock = make_engine()
    for _ in range(3):
        assert engine.decide(msg("在吗")).should_reply
        clock.advance(601)
    decision = engine.decide(msg("在吗"))
    assert not decision.should_reply
    assert "今日已达上限" in decision.reason


def test_daily_cap_resets_after_24h():
    engine, clock = make_engine()
    for _ in range(3):
        engine.decide(msg("在吗"))
        clock.advance(601)
    clock.advance(24 * 3600)
    assert engine.decide(msg("在吗")).should_reply


def test_zero_per_chat_daily_cap_means_unlimited():
    engine, clock = make_engine(
        {
            "limits": {
                **BASE_CONFIG["limits"],
                "max_replies_per_chat_per_day": 0,
                "per_chat_cooldown_seconds": 0,
                "global_max_replies_per_hour": 100,
            }
        }
    )
    for _ in range(20):
        assert engine.decide(msg("在吗")).should_reply
        clock.advance(1)


def test_global_hourly_cap():
    engine, clock = make_engine(
        {"limits": {**BASE_CONFIG["limits"], "per_chat_cooldown_seconds": 0, "global_max_replies_per_hour": 2}}
    )
    assert engine.decide(msg("在吗", chat_id="a", chat_name="A")).should_reply
    assert engine.decide(msg("在吗", chat_id="b", chat_name="B")).should_reply
    decision = engine.decide(msg("在吗", chat_id="c", chat_name="C"))
    assert not decision.should_reply
    assert "一小时上限" in decision.reason


def test_cooldown_is_per_chat():
    engine, _ = make_engine()
    assert engine.decide(msg("在吗", chat_id="a", chat_name="A")).should_reply
    assert engine.decide(msg("在吗", chat_id="b", chat_name="B")).should_reply


# ------------------------------------------------------------------ 时间段


def test_active_hours_respected():
    # 1700000000 UTC = 2023-11-14 22:13:20；用一个必然不包含当前时刻的窗口
    engine, _ = make_engine({"active_hours": ["03:00-03:01"]})
    decision = engine.decide(msg("在吗"))
    assert not decision.should_reply
    assert "时段" in decision.reason


def test_no_active_hours_means_always_on():
    engine, _ = make_engine({"active_hours": []})
    assert engine.decide(msg("在吗")).should_reply


def test_chat_name_normalization_removes_trace_memo_invisible_prefix_and_dot():
    from core.models import clean_chat_display_name, normalize_chat_name

    assert normalize_chat_name("real") == normalize_chat_name("\u00a0￴￴real.")
    assert clean_chat_display_name("\u00a0￴￴real.") == "real."


# ------------------------------------------------------------------ 文案轮换


def test_replies_rotate():
    engine, clock = make_engine(
        {
            "limits": {
                **BASE_CONFIG["limits"],
                "per_chat_cooldown_seconds": 0,
                "max_replies_per_chat_per_day": 10,
            },
            "rules": [{"name": "多文案", "match": {"type": "keyword", "any": ["在吗"]}, "reply": ["A", "B"]}],
        }
    )
    texts = []
    for _ in range(4):
        texts.append(engine.decide(msg("在吗")).text)
        clock.advance(1)
    assert texts == ["A", "B", "A", "B"]


# ------------------------------------------------------------------ LLM 兜底


def test_llm_fallback_used():
    engine, _ = make_engine(
        {"fallback": {"type": "llm"}, "rules": []},
    )
    engine._llm_reply = lambda m, c: f"收到：{m.text}"
    assert engine.decide(msg("随便说点什么")).text == "收到：随便说点什么"


def test_llm_failure_does_not_crash():
    engine, _ = make_engine({"fallback": {"type": "llm"}, "rules": []})

    def boom(m, c):
        raise RuntimeError("network down")

    engine._llm_reply = boom
    decision = engine.decide(msg("你好"))
    assert not decision.should_reply
    assert "生成失败" in decision.reason


def test_llm_failure_does_not_consume_quota():
    """生成失败不该白白吃掉一次冷却额度。"""
    engine, _ = make_engine({"fallback": {"type": "llm"}, "rules": []})
    engine._llm_reply = lambda m, c: None
    engine.decide(msg("你好"))
    engine._llm_reply = lambda m, c: "这次成功了"
    assert engine.decide(msg("你好")).should_reply


def test_fallback_none_skips():
    engine, _ = make_engine({"fallback": {"type": "none"}, "rules": []})
    assert not engine.decide(msg("你好")).should_reply


# ------------------------------------------------------------------ 配置校验


def test_bad_group_policy_rejected():
    with pytest.raises(ConfigError, match="reply_to_group"):
        build_config({"scope": {"reply_to_group": "sometimes"}})


def test_bad_time_range_rejected():
    with pytest.raises(ConfigError, match="active_hours"):
        build_config({"active_hours": ["9点到12点"]})


def test_bad_regex_rejected():
    with pytest.raises(ConfigError, match="正则"):
        build_config({"rules": [{"name": "x", "match": {"type": "regex", "pattern": "["}, "reply": "y"}]})


def test_rule_without_reply_rejected():
    with pytest.raises(ConfigError, match="缺少 reply"):
        build_config({"rules": [{"name": "x", "match": {"type": "keyword", "any": ["a"]}}]})


def test_delay_range_validated():
    with pytest.raises(ConfigError, match="min_delay_seconds"):
        build_config({"limits": {"min_delay_seconds": 10, "max_delay_seconds": 2}})


# ------------------------------------------------------------------ 状态持久化


def test_state_survives_restart(tmp_path):
    state = tmp_path / "state.json"
    clock = FakeClock()
    engine = ReplyEngine(build_config(BASE_CONFIG), state_path=state, clock=clock)
    assert engine.decide(msg("在吗")).should_reply

    reborn = ReplyEngine(build_config(BASE_CONFIG), state_path=state, clock=clock)
    assert not reborn.decide(msg("在吗")).should_reply  # 冷却状态被读回来了


def test_corrupt_state_file_does_not_crash(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{not json", encoding="utf-8")
    engine = ReplyEngine(build_config(BASE_CONFIG), state_path=state, clock=FakeClock())
    assert engine.decide(msg("在吗")).should_reply


# ------------------------------------------------------- 跨端去重（多端同时在线）


DEDUP_CONFIG = {
    **BASE_CONFIG,
    "limits": {**BASE_CONFIG["limits"], "cross_device_dedup_seconds": 120},
}


def test_android_and_macos_do_not_both_reply():
    """微信多端同时在线：同一条消息安卓和 macOS 各上报一次，只能回一次。

    这是最容易踩的坑——两端上报的 chat_id 前缀不同
    （android:com.tencent.mm:小王 vs macos:小王），如果拿 chat_id 当键，
    冷却会分裂成两套，对方就收到两条一模一样的自动回复。
    """
    engine, _ = make_engine(DEDUP_CONFIG)

    from_android = engine.decide(
        msg("在吗", chat_id="android:com.tencent.mm:小王", platform="android", account="主号")
    )
    from_macos = engine.decide(
        msg("在吗", chat_id="macos:小王", platform="macos", account="主号")
    )

    assert from_android.should_reply
    assert not from_macos.should_reply
    assert "跨端去重" in from_macos.reason


def test_cooldown_shared_across_platforms():
    """即使内容不同，两端也该共享同一份冷却额度。"""
    engine, clock = make_engine(DEDUP_CONFIG)
    assert engine.decide(msg("在吗", chat_id="android:xx:小王", account="主号")).should_reply
    clock.advance(200)  # 超过去重窗口，但没过冷却
    decision = engine.decide(msg("忙吗", chat_id="macos:小王", account="主号"))
    assert not decision.should_reply
    assert "冷却中" in decision.reason


def test_dedup_window_expires():
    engine, clock = make_engine(DEDUP_CONFIG)
    engine.decide(msg("在吗", chat_id="android:xx:小王", account="主号"))
    clock.advance(121)   # 去重窗口过了
    clock.advance(600)   # 冷却也过了
    assert engine.decide(msg("在吗", chat_id="macos:小王", account="主号")).should_reply


def test_different_text_not_deduped():
    """内容不同就不是同一条消息，不该被去重挡掉（此时只受冷却约束）。"""
    engine, clock = make_engine(
        {**DEDUP_CONFIG, "limits": {**DEDUP_CONFIG["limits"], "per_chat_cooldown_seconds": 0}}
    )
    assert engine.decide(msg("在吗", chat_id="android:xx:小王", account="主号")).should_reply
    assert engine.decide(msg("在不在", chat_id="macos:小王", account="主号")).should_reply


def test_group_member_count_not_part_of_identity():
    """群名里的成员数会变，不该被当成新会话。"""
    engine, _ = make_engine(DEDUP_CONFIG)
    first = engine.decide(
        msg("在吗", chat_id="a", chat_name="项目组(8)", is_group=True, mentioned_me=True)
    )
    second = engine.decide(
        msg("在吗", chat_id="b", chat_name="项目组(9)", is_group=True, mentioned_me=True)
    )
    assert first.should_reply
    assert not second.should_reply


def test_group_and_private_same_name_are_separate():
    """同名的群和联系人不该共享额度。"""
    engine, _ = make_engine(DEDUP_CONFIG)
    assert engine.decide(msg("在吗", chat_id="p", chat_name="小王")).should_reply
    assert engine.decide(
        msg("在吗", chat_id="g", chat_name="小王", is_group=True, mentioned_me=True)
    ).should_reply


def test_identity_ignores_platform_prefix_and_whitespace():
    from core.models import chat_identity

    a = IncomingMessage(chat_id="android:com.tencent.mm:小王", chat_name=" 小王 ", text="x", account="主号")
    b = IncomingMessage(chat_id="macos:小王", chat_name="小王", text="x", account="主号")
    assert chat_identity(a) == chat_identity(b)


# --------------------------------------------------- 多账号隔离（两个不同的微信号）


def test_two_accounts_same_contact_name_are_independent():
    """两个微信号各跑一端，即使联系人重名也必须各回各的。

    这是和「同号多端」相反的场景：账号才是隔离边界，平台不是。
    如果把平台当账号，B 号的「小王」会被 A 号刚回过的「小王」误杀。
    """
    engine, _ = make_engine(DEDUP_CONFIG)

    work = engine.decide(msg("在吗", chat_id="android:小王", platform="android", account="工作号"))
    personal = engine.decide(msg("在吗", chat_id="macos:小王", platform="macos", account="私人号"))

    assert work.should_reply
    assert personal.should_reply, "不同账号的同名联系人被误当成同一个会话"


def test_accounts_default_to_platform_isolation():
    """不填 account 时按平台隔离——对「两个号各跑一端」是安全的默认值。"""
    engine, _ = make_engine(DEDUP_CONFIG)
    assert engine.decide(msg("在吗", platform="android")).should_reply
    assert engine.decide(msg("在吗", platform="macos")).should_reply


def test_cooldown_isolated_between_accounts():
    engine, _ = make_engine(DEDUP_CONFIG)
    assert engine.decide(msg("在吗", account="工作号")).should_reply
    assert not engine.decide(msg("在吗", account="工作号")).should_reply  # 同号冷却
    assert engine.decide(msg("在吗", account="私人号")).should_reply      # 另一个号不受影响


def test_daily_cap_isolated_between_accounts():
    engine, clock = make_engine(DEDUP_CONFIG)
    for _ in range(3):
        engine.decide(msg("在吗", account="工作号"))
        clock.advance(601)
    assert not engine.decide(msg("在吗", account="工作号")).should_reply
    assert engine.decide(msg("在吗", account="私人号")).should_reply


def test_hourly_fuse_isolated_between_accounts():
    """一个号刷爆保险丝，不该把另一个号一起饿死。"""
    engine, clock = make_engine(
        {
            **DEDUP_CONFIG,
            "limits": {
                **DEDUP_CONFIG["limits"],
                "per_chat_cooldown_seconds": 0,
                "cross_device_dedup_seconds": 0,
                "global_max_replies_per_hour": 2,
            },
        }
    )
    for i in range(2):
        assert engine.decide(msg("在吗", chat_id=f"a{i}", chat_name=f"甲{i}", account="工作号")).should_reply
        clock.advance(1)

    blocked = engine.decide(msg("在吗", chat_id="a9", chat_name="甲9", account="工作号"))
    assert not blocked.should_reply
    assert "工作号" in blocked.reason

    assert engine.decide(msg("在吗", chat_id="b1", chat_name="乙", account="私人号")).should_reply


def test_account_falls_back_to_platform():
    m = IncomingMessage(chat_id="x", chat_name="小王", text="hi", platform="android")
    assert m.account == "android"


def test_explicit_account_wins_over_platform():
    m = IncomingMessage(
        chat_id="x", chat_name="小王", text="hi", platform="android", account="工作号"
    )
    assert m.account == "工作号"


def test_identity_separates_accounts():
    from core.models import chat_identity

    a = IncomingMessage(chat_id="x", chat_name="小王", text="hi", account="工作号")
    b = IncomingMessage(chat_id="y", chat_name="小王", text="hi", account="私人号")
    assert chat_identity(a) != chat_identity(b)


# ------------------------------------------------------------------ 预览工具


def test_preview_config_ignores_switch_and_hours():
    """预览要忽略总开关和时段，但敏感词等安全判断必须照常生效。"""
    from core.preview import _for_preview

    original = build_config({**BASE_CONFIG, "enabled": False, "active_hours": ["03:00-03:01"]})
    preview = _for_preview(original)

    assert preview.enabled
    assert preview.active_hours == []
    # 原配置不能被改动——预览不该影响正在跑的服务
    assert not original.enabled
    assert len(original.active_hours) == 1


def test_preview_still_blocks_sensitive_words():
    from core.preview import _for_preview

    engine = ReplyEngine(_for_preview(build_config(BASE_CONFIG)), clock=FakeClock())
    decision = engine.decide(msg("帮我转账 500"))
    assert not decision.should_reply
    assert "敏感词" in decision.reason


# --------------------------------------------------- AI 模式与人设


AI_CONFIG = {
    **BASE_CONFIG,
    "reply_mode": "ai",
    "persona": {
        "identity": "我是做独立开发的，白天在写代码",
        "tone": "偏短，口语，不用敬语",
        "playbook": "问进度就给大概时间，不打包票",
        "boundaries": ["不聊报价"],
        "max_chars": 30,
        "examples": [{"them": "在吗", "me": "在，怎么了"}],
    },
}


def test_ai_mode_bypasses_rules():
    """AI 模式下规则不参与，所有消息都交给模型。"""
    engine, _ = make_engine(AI_CONFIG)
    engine._llm_reply = lambda m, c: f"AI说：{m.text}"
    d = engine.decide(msg("在吗"))          # 这句本来能命中「在吗」规则
    assert d.text == "AI说：在吗"
    assert d.rule_name is None
    assert d.reason == "AI 生成"


def test_ai_mode_still_blocks_sensitive_words():
    """安全判断绝不能交给模型——必须在调用模型之前就拦下。"""
    engine, _ = make_engine(AI_CONFIG)
    called = []
    engine._llm_reply = lambda m, c: called.append(m) or "不该被调用"
    d = engine.decide(msg("帮我转账500"))
    assert not d.should_reply
    assert "敏感词" in d.reason
    assert called == [], "敏感词消息不该送到模型那里去"


def test_ai_mode_requires_persona():
    with pytest.raises(ConfigError, match="persona"):
        build_config({**BASE_CONFIG, "reply_mode": "ai"})


def test_rules_only_mode_never_calls_model():
    engine, _ = make_engine({**BASE_CONFIG, "reply_mode": "rules"})
    engine._llm_reply = lambda m, c: "不该被调用"
    assert engine.decide(msg("在吗")).text == "在的"
    d = engine.decide(msg("完全没规则的话", chat_id="x", chat_name="乙"))
    assert not d.should_reply
    assert "纯规则模式" in d.reason


def test_bad_reply_mode_rejected():
    with pytest.raises(ConfigError, match="reply_mode"):
        build_config({**BASE_CONFIG, "reply_mode": "随便"})


# --------------------------------------------------- 提示词与上下文


def test_system_prompt_contains_persona_and_rules():
    from core.persona import build_persona, build_system_prompt

    prompt = build_system_prompt(build_persona(AI_CONFIG["persona"]))
    assert "独立开发" in prompt
    assert "问进度就给大概时间" in prompt
    assert "不聊报价" in prompt          # 自定义边界
    assert "30 个字以内" in prompt        # 长度限制
    assert "转账" in prompt               # 内置硬性边界
    assert "在，怎么了" in prompt          # 示范语气
    assert "不要自称 AI" in prompt


def test_conversation_memory_keeps_context():
    from core.persona import ConversationMemory

    mem = ConversationMemory(max_turns=4, ttl_seconds=600)
    mem.remember("小王", "them", "在吗", now=100)
    mem.remember("小王", "me", "在", now=101)
    mem.remember("小王", "them", "那明天呢", now=102)

    turns = mem.recent("小王", now=103)
    assert [t.text for t in turns] == ["在吗", "在", "那明天呢"]


def test_conversation_memory_expires_old_turns():
    from core.persona import ConversationMemory

    mem = ConversationMemory(max_turns=8, ttl_seconds=60)
    mem.remember("小王", "them", "很久以前的事", now=0)
    mem.remember("小王", "them", "刚刚说的", now=100)
    # 太老的上下文会误导——三天前那事早翻篇了
    assert [t.text for t in mem.recent("小王", now=120)] == ["刚刚说的"]


def test_conversation_memory_is_per_chat():
    from core.persona import ConversationMemory

    mem = ConversationMemory()
    mem.remember("小王", "them", "甲的话", now=1)
    mem.remember("小李", "them", "乙的话", now=1)
    assert [t.text for t in mem.recent("小王", now=2)] == ["甲的话"]
