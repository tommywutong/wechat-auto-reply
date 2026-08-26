"""防风控相关行为的单测。

这些机制的共同点是：**平时看不出效果，出事时才知道有没有**。
所以必须有测试钉住，否则以后随手改一行限流逻辑就悄悄没了。

这里测的不是「能不能回」，而是「回得像不像人」：
间隔、节奏、内容重复度。
"""

from __future__ import annotations

from core.config import build_config
from core.engine import ReplyEngine
from core.models import IncomingMessage

from .test_engine import BASE_CONFIG, FakeClock


def make_engine(limits: dict, rules=None, clock=None):
    data = {
        **BASE_CONFIG,
        "limits": {**BASE_CONFIG["limits"], **limits},
    }
    if rules is not None:
        data["rules"] = rules
    clock = clock or FakeClock()
    return ReplyEngine(build_config(data), clock=clock), clock


def msg(text: str = "在吗", chat: str = "小王") -> IncomingMessage:
    return IncomingMessage(chat_id=chat, chat_name=chat, text=text)


# ------------------------------------------------------------ 跨会话最小间隔


def test_replies_to_different_people_are_spaced_out():
    """三十个人同时发消息时，不能在几十秒内挨个回完。

    冷却是按会话算的，挡不住这种情况——真人不可能一秒切一个会话回一条，
    这是最容易被认出来的机器特征。
    """
    engine, clock = make_engine({
        "min_delay_seconds": 0,
        "max_delay_seconds": 0,
        "typing_seconds_per_char": 0,
        "global_min_interval_seconds": 45,
    })

    first = engine.decide(msg(chat="甲"))
    second = engine.decide(msg(chat="乙"))
    third = engine.decide(msg(chat="丙"))

    assert first.should_reply and second.should_reply and third.should_reply
    # 三条依次排开，而不是同时发出
    assert first.delay_seconds == 0
    assert second.delay_seconds == 45
    assert third.delay_seconds == 90


def test_spacing_shrinks_as_real_time_passes():
    """如果消息本来就是隔开来的，就不该额外等待。"""
    engine, clock = make_engine({
        "min_delay_seconds": 0,
        "max_delay_seconds": 0,
        "typing_seconds_per_char": 0,
        "global_min_interval_seconds": 45,
    })

    engine.decide(msg(chat="甲"))
    clock.advance(100)          # 一百秒后另一个人才发消息
    second = engine.decide(msg(chat="乙"))

    assert second.delay_seconds == 0


def test_spacing_delays_but_never_drops():
    """间隔不够时把消息往后推，而不是丢掉。

    丢掉的话，群发场景下大部分人就永远收不到回复了，
    而用户完全不知道发生了什么。
    """
    engine, _ = make_engine({
        "global_min_interval_seconds": 60,
    })

    decisions = [engine.decide(msg(chat=f"联系人{i}")) for i in range(5)]

    assert all(d.should_reply for d in decisions)
    # 时间上严格递增
    delays = [d.delay_seconds for d in decisions]
    assert delays == sorted(delays)
    assert delays[-1] >= 4 * 60


def test_spacing_can_be_turned_off():
    engine, _ = make_engine({
        "min_delay_seconds": 0,
        "max_delay_seconds": 0,
        "typing_seconds_per_char": 0,
        "global_min_interval_seconds": 0,
    })
    assert engine.decide(msg(chat="甲")).delay_seconds == 0
    assert engine.decide(msg(chat="乙")).delay_seconds == 0


# ------------------------------------------------------------ 打字时间


def test_longer_replies_take_longer_to_send():
    """真人打一句 30 字的话比打「嗯」慢得多。

    固定延迟会让长短回复的响应时间一模一样，反而不自然。
    """
    engine, _ = make_engine(
        {
            "min_delay_seconds": 0,
            "max_delay_seconds": 0,
            "typing_seconds_per_char": 0.1,
            "global_min_interval_seconds": 0,
        },
        rules=[
            {"name": "短", "match": {"type": "keyword", "any": ["短"]}, "reply": "嗯"},
            {
                "name": "长",
                "match": {"type": "keyword", "any": ["长"]},
                "reply": "我这会儿手上有点事，等下忙完了详细跟你说这个情况",
            },
        ],
    )

    short = engine.decide(msg("短", chat="甲"))
    long_ = engine.decide(msg("长", chat="乙"))

    assert short.delay_seconds < long_.delay_seconds
    assert abs(short.delay_seconds - 0.1) < 0.01           # 「嗯」一个字
    assert abs(long_.delay_seconds - 24 * 0.1) < 0.05      # 二十四个字


def test_typing_time_stacks_on_top_of_base_delay():
    engine, _ = make_engine({
        "min_delay_seconds": 3,
        "max_delay_seconds": 3,
        "typing_seconds_per_char": 0.1,
        "global_min_interval_seconds": 0,
    })
    # 「在的」两个字 → 3 + 0.2
    assert abs(engine.decide(msg()).delay_seconds - 3.2) < 0.01


# ------------------------------------------------------------ 内容重复度


def test_different_people_get_different_wording():
    """一百个人收到一模一样的一句话，是批量发送最明显的特征。

    轮换计数必须是全局的：按会话分开算的话，每个人拿到的都是第一句。
    """
    engine, _ = make_engine(
        {"global_min_interval_seconds": 0},
        rules=[{
            "name": "在吗",
            "match": {"type": "keyword", "any": ["在吗"]},
            "reply": ["在的", "在，怎么了", "在，稍等"],
        }],
    )

    texts = [engine.decide(msg(chat=f"联系人{i}")).text for i in range(3)]
    assert len(set(texts)) == 3, f"三个人收到了重复内容：{texts}"


def test_same_person_still_gets_variation_over_time():
    engine, clock = make_engine(
        {
            "per_chat_cooldown_seconds": 0,
            "max_replies_per_chat_per_day": 10,   # 基础配置是 3，这里要跑 4 轮
            "global_min_interval_seconds": 0,
        },
        rules=[{
            "name": "在吗",
            "match": {"type": "keyword", "any": ["在吗"]},
            "reply": ["A", "B"],
        }],
    )
    seen = []
    for _ in range(4):
        seen.append(engine.decide(msg()).text)
        clock.advance(1)
    assert seen == ["A", "B", "A", "B"]


# ------------------------------------------------------------ 总量


def test_daily_global_cap():
    """只有每小时上限的话，跑满一天是 720 条。"""
    engine, clock = make_engine({
        "per_chat_cooldown_seconds": 0,
        "max_replies_per_chat_per_day": 1000,
        "global_max_replies_per_hour": 1000,
        "global_max_replies_per_day": 5,
        "global_min_interval_seconds": 0,
    })

    for i in range(5):
        assert engine.decide(msg(chat=f"人{i}")).should_reply
        clock.advance(10)

    blocked = engine.decide(msg(chat="第六个人"))
    assert not blocked.should_reply
    assert "今日上限" in blocked.reason


def test_daily_cap_resets_after_a_day():
    engine, clock = make_engine({
        "per_chat_cooldown_seconds": 0,
        "max_replies_per_chat_per_day": 1000,
        "global_max_replies_per_hour": 1000,
        "global_max_replies_per_day": 2,
        "global_min_interval_seconds": 0,
    })
    engine.decide(msg(chat="甲"))
    engine.decide(msg(chat="乙"))
    assert not engine.decide(msg(chat="丙")).should_reply

    clock.advance(24 * 3600 + 1)
    assert engine.decide(msg(chat="丁")).should_reply


def test_hourly_cap_still_applies_within_the_daily_budget():
    engine, clock = make_engine({
        "per_chat_cooldown_seconds": 0,
        "max_replies_per_chat_per_day": 1000,
        "global_max_replies_per_hour": 2,
        "global_max_replies_per_day": 100,
        "global_min_interval_seconds": 0,
    })
    engine.decide(msg(chat="甲"))
    engine.decide(msg(chat="乙"))
    blocked = engine.decide(msg(chat="丙"))
    assert not blocked.should_reply
    assert "一小时上限" in blocked.reason


# ------------------------------------------------------------ 顺序不能乱


def test_sensitive_words_still_win_over_everything():
    """限流改动不能把安全判断挤到后面去。

    敏感词必须在任何频率逻辑之前——否则「刚回过」会盖住
    「这是转账消息」，排查时被误导，行为上也更危险。
    """
    engine, _ = make_engine({"global_min_interval_seconds": 0})
    engine.decide(msg(chat="甲"))
    decision = engine.decide(msg("帮我转账500", chat="甲"))
    assert not decision.should_reply
    assert "敏感词" in decision.reason
