"""开场问答的单测。

重点不是「生成的话好不好听」——那没法测——而是：

  1. 不管用户怎么答，生成的配置都能被 config.py 正常解析
     （问答是给不懂技术的人用的，它生成的东西不能反过来让程序崩）
  2. 有几条底线不受回答影响，永远在
  3. 答案确实影响输出，而不是摆设
"""

from itertools import product

import pytest
import yaml

from core.config import build_config
from core.wizard import (
    QUESTIONS,
    build_result,
    to_yaml,
)


def answers(**overrides):
    base = {
        "who": ["work", "friend"],
        "busy": ["hands"],
        "style": "casual",
        "emoji": "none",
        "appointment": "hold",
        "progress": "rough",
        "stranger": "polite",
        "greeting": "",
        "never": [],
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------ 问题本身


def test_question_ids_are_unique():
    ids = [q.id for q in QUESTIONS]
    assert len(ids) == len(set(ids))


def test_option_ids_are_unique_within_each_question():
    for question in QUESTIONS:
        ids = [o.id for o in question.options]
        assert len(ids) == len(set(ids)), question.id


def test_choice_questions_have_options_and_text_questions_do_not():
    for question in QUESTIONS:
        if question.kind == "text":
            assert not question.options, question.id
        else:
            assert len(question.options) >= 2, question.id


def test_both_implementations_ask_the_same_questions():
    """安卓端（SetupWizard.kt）必须问一模一样的题。

    两边不一致的话，同一个人在电脑和手机上生成的人设就不一样，
    语气对不上——而那正是这套东西要解决的问题。
    """
    assert [q.id for q in QUESTIONS] == [
        "who",
        "busy",
        "style",
        "greeting",
        "appointment",
        "progress",
        "stranger",
        "emoji",
        "night",
        "never",
        "only_for",
    ]


def test_free_text_questions_are_optional():
    # 强制一个不懂技术的人写自由文本，是最容易让他卡住的一步
    for question in QUESTIONS:
        if question.kind == "text":
            assert question.optional, question.id


# ------------------------------------------------------------------ 底线


def test_playbook_always_keeps_the_escape_hatch():
    """「看不懂就交给本人」是最重要的一条，任何回答组合下都必须在。"""
    for style, appointment, stranger in product(
        ("casual", "polite", "warm", "brief"),
        ("hold", "refuse", "ask"),
        ("polite", "blunt", "later"),
    ):
        result = build_result(
            answers(style=style, appointment=appointment, stranger=stranger)
        )
        assert "等我本人回你" in result.playbook


def test_every_generated_rule_has_a_usable_reply():
    # 空回复会被引擎跳过，等于这条规则白写
    result = build_result(answers())
    for rule in result.rules:
        assert rule["replies"], rule["name"]
        assert all(r.strip() for r in rule["replies"]), rule["name"]
        assert rule["keywords"]


def test_unknown_answers_fall_back_instead_of_crashing():
    # 安卓端存了旧版本的答案、或者配置被改坏时，不能炸
    result = build_result(answers(style="不存在", appointment="乱写", busy="???"))
    assert result.tone
    assert result.playbook
    assert result.max_chars > 0


def test_empty_answers_still_produce_a_working_persona():
    result = build_result({})
    assert result.identity
    assert result.tone
    assert result.playbook
    assert result.examples
    assert result.fallback_text


# ------------------------------------------------------------------ 答案有效


def test_style_changes_the_voice():
    casual = build_result(answers(style="casual")).examples[0]["me"]
    polite = build_result(answers(style="polite")).examples[0]["me"]
    brief = build_result(answers(style="brief")).examples[0]["me"]
    assert casual != polite != brief
    assert "您" in polite
    assert len(brief) <= len(casual)


def test_no_exclamation_when_user_said_they_do_not_use_them():
    # 热情风格自带感叹号，但用户说了不用——示范必须跟着改。
    # 示范和语气说明打架时，模型照着示范走。
    result = build_result(answers(style="warm", emoji="none"))
    for example in result.examples:
        assert "！" not in example["me"]
    assert "不用感叹号" in result.tone


def test_exclamation_kept_when_user_likes_them():
    result = build_result(answers(style="warm", emoji="lots"))
    assert any("！" in e["me"] for e in result.examples)


def test_reply_length_follows_the_chosen_voice():
    """长度不再单独问一题——选了「在」的人不会突然写三句话。

    少一道题，而且推断出来的比用户自己估的准。
    """
    assert build_result(answers(style="brief")).max_chars == 20
    assert build_result(answers(style="casual")).max_chars == 30
    assert build_result(answers(style="warm")).max_chars == 45


def test_own_words_beat_the_template():
    """用户自己写的那句是他真实的声音，优先级最高。"""
    result = build_result(answers(greeting="咋了老铁"))
    assert result.examples[0]["me"] == "咋了老铁"
    # 关键词规则里也要用同一句，两种模式下表现才一致
    greeting_rule = next(r for r in result.rules if r["name"] == "问在不在")
    assert greeting_rule["replies"] == ["咋了老铁"]


def test_appointment_choice_changes_both_playbook_and_examples():
    hold = build_result(answers(appointment="hold"))
    refuse = build_result(answers(appointment="refuse"))
    assert hold.playbook != refuse.playbook
    assert hold.examples[1]["me"] != refuse.examples[1]["me"]
    assert "日程" in hold.examples[1]["me"]


def test_boundaries_come_from_checkboxes():
    """原来这题是个空框，让人对着它想「有什么绝对不能答应」。

    那是最难答的一种题，多数人直接跳过，于是这一段永远是空的。
    改成勾选之后，答案是常见的那几条，勾一下就有。
    """
    result = build_result(answers(never=["money", "favor"]))
    assert any("价格" in b for b in result.boundaries)
    assert any("投票" in b for b in result.boundaries)
    assert len(result.boundaries) == 2


def test_no_boundaries_checked_stays_empty():
    assert build_result(answers(never=[])).boundaries == []


# ------------------------------------------------------------ 几点回


def test_night_choice_controls_active_hours():
    """深夜自动回复本身就是可疑信号，所以这题得问，而且要好答。"""
    assert build_result(answers(night="day")).active_hours == ["09:00-23:00"]
    assert build_result(answers(night="work")).active_hours == ["09:00-18:00"]
    assert build_result(answers(night="always")).active_hours == []


def test_active_hours_reach_the_config():
    for night, expected in (("day", 1), ("work", 1), ("always", 0)):
        config = build_config(yaml.safe_load(to_yaml(build_result(answers(night=night)))))
        assert len(config.active_hours) == expected, night


# ------------------------------------------------------------ 谁在发消息


def test_client_makes_the_playbook_more_careful():
    """选了客户、甲方说明回错的代价高，这题就该真的改变行为。"""
    with_client = build_result(answers(who=["client"]))
    without = build_result(answers(who=["friend"]))
    assert "不表态" in with_client.playbook
    assert "报价" in with_client.playbook
    assert "报价" not in without.playbook


def test_who_appears_in_identity():
    result = build_result(answers(who=["client"]))
    assert "客户" in result.identity


def test_identity_survives_no_selection():
    result = build_result(answers(who=[]))
    assert result.identity.strip()


# ------------------------------------------------------------------ 产物可用


@pytest.mark.parametrize("reply_mode", ["ai", "rules", "rules_then_ai"])
def test_generated_yaml_loads_in_every_mode(reply_mode):
    text = to_yaml(build_result(answers()), reply_mode=reply_mode)
    config = build_config(yaml.safe_load(text))
    assert config.reply_mode == reply_mode
    assert config.persona.is_configured()
    assert config.rules


def test_generated_yaml_loads_for_every_situation_combo():
    for appointment, progress, stranger, style in product(
        ("hold", "refuse", "ask"),
        ("rough", "working", "person"),
        ("polite", "blunt", "later"),
        ("casual", "polite", "warm", "brief"),
    ):
        text = to_yaml(
            build_result(
                answers(
                    appointment=appointment,
                    progress=progress,
                    stranger=stranger,
                    style=style,
                )
            ),
            reply_mode="ai",
        )
        config = build_config(yaml.safe_load(text))
        assert config.persona.examples
        assert config.fallback.text


def test_generated_yaml_loads_for_every_identity_combo():
    for busy, style, emoji in product(
        ("work", "hands", "out", "later", "unsure"),
        ("casual", "polite", "warm", "brief"),
        ("none", "emoji", "mark", "both"),
    ):
        text = to_yaml(build_result(answers(busy=[busy], style=style, emoji=emoji)))
        config = build_config(yaml.safe_load(text))
        assert config.persona.max_chars > 0


def test_quotes_in_user_text_do_not_break_the_yaml():
    # 用户随手打个引号就让配置文件解析失败，是很蠢的失败方式
    result = build_result(answers(greeting='他说"好的"', never='不说"没问题"'))
    config = build_config(yaml.safe_load(to_yaml(result)))
    assert config.persona.examples[0].reply == '他说"好的"'


def test_ai_mode_config_passes_the_persona_requirement():
    """reply_mode: ai 缺人设会被 config.py 拒绝——问答生成的必须过得去。"""
    text = to_yaml(build_result({}), reply_mode="ai")
    config = build_config(yaml.safe_load(text))
    assert config.persona.is_configured()


# ------------------------------------------------------------------ 白名单


def test_only_for_becomes_allow_contacts():
    """「先只对哪几个人开」是最有效的防风控手段。

    真正会出事的路径是被举报，而熟人不会举报你。
    这一条藏在配置文件里的话，非技术用户根本用不到。
    """
    result = build_result(answers(only_for="小王，李雷、张三"))
    assert result.allow_contacts == ["小王", "李雷", "张三"]

    config = build_config(yaml.safe_load(to_yaml(result)))
    assert config.scope.allow_contacts == ["小王", "李雷", "张三"]


def test_blank_only_for_means_everyone():
    result = build_result(answers(only_for=""))
    assert result.allow_contacts == []
    config = build_config(yaml.safe_load(to_yaml(result)))
    assert config.scope.allow_contacts == []


def test_whitelist_actually_blocks_outsiders():
    """生成出来但引擎不认，等于白填。"""
    from core.engine import ReplyEngine
    from core.models import IncomingMessage

    data = yaml.safe_load(to_yaml(build_result(answers(only_for="小王"))))
    data["active_hours"] = []          # 时段不该干扰这条断言
    engine = ReplyEngine(build_config(data))

    inside = engine.decide(IncomingMessage(chat_id="小王", chat_name="小王", text="在吗"))
    outside = engine.decide(IncomingMessage(chat_id="陌生人", chat_name="陌生人", text="在吗"))

    assert inside.should_reply
    assert not outside.should_reply
    assert "白名单" in outside.reason


# ------------------------------------------------------------ 表情 ≠ 感叹号


def test_emoji_and_exclamation_are_independent():
    """有人爱发表情但从不用感叹号。

    原来把两者混成一个「用不用」的程度问题，是设计错误：
    选「偶尔用」的人没法表达「只发表情」。
    """
    only_emoji = build_result(answers(style="warm", emoji="emoji"))
    only_mark = build_result(answers(style="warm", emoji="mark"))

    # 只发表情 → 示范里有表情、没有感叹号
    assert all("！" not in e["me"] for e in only_emoji.examples)
    assert any("😂" in e["me"] for e in only_emoji.examples)

    # 只用感叹号 → 反过来
    assert any("！" in e["me"] for e in only_mark.examples)
    assert all("😂" not in e["me"] for e in only_mark.examples)


def test_emoji_choice_is_described_in_tone():
    assert "会发表情" in build_result(answers(emoji="emoji")).tone
    assert "会用感叹号" in build_result(answers(emoji="mark")).tone
    assert "都不用" not in build_result(answers(emoji="both")).tone


def test_legacy_emoji_answers_still_work():
    """旧版本存的答案不该让人设变样——重装一次语气就变了很怪。"""
    assert build_result(answers(emoji="some")).tone == build_result(
        answers(emoji="emoji")
    ).tone
    assert build_result(answers(emoji="lots")).tone == build_result(
        answers(emoji="both")
    ).tone


# ------------------------------------------------------------ 没马上回的理由


def test_busy_accepts_several_reasons():
    """「在上班」和「不知道怎么回」可以同时成立，原来只能选一个。"""
    result = build_result(answers(busy=["work", "unsure"]))
    assert "上班" in result.identity
    assert "想想怎么回" in result.identity


def test_unsure_makes_the_playbook_more_careful():
    """用户自己说了「有些消息不知道怎么回」，模型就该跟着保守。"""
    careful = build_result(answers(busy=["unsure"]))
    plain = build_result(answers(busy=["work"]))
    assert "绝对不要自己编一个答案" in careful.playbook
    assert "绝对不要自己编一个答案" not in plain.playbook


def test_legacy_single_busy_answer_still_works():
    result = build_result(answers(busy="work"))
    assert "上班" in result.identity
    assert result.fallback_text


def test_unknown_busy_falls_back():
    result = build_result(answers(busy=["乱写"]))
    assert result.identity.strip()
    assert result.fallback_text.strip()


# ------------------------------------------------------------ 名单比对


def test_whitelist_tolerates_spacing_and_case():
    """用户手打名字常有多余空格。比对失败是静默的，最难查。"""
    from core.engine import ReplyEngine
    from core.models import IncomingMessage

    data = yaml.safe_load(to_yaml(build_result(answers(only_for="  小王 "))))
    data["active_hours"] = []
    engine = ReplyEngine(build_config(data))

    d = engine.decide(IncomingMessage(chat_id="x", chat_name="小王", text="在吗"))
    assert d.should_reply, d.reason


def test_whitelist_does_not_do_fuzzy_matching():
    """「小王他哥」不该被当成「小王」——那会让名单形同虚设。"""
    from core.engine import ReplyEngine
    from core.models import IncomingMessage

    data = yaml.safe_load(to_yaml(build_result(answers(only_for="小王"))))
    data["active_hours"] = []
    engine = ReplyEngine(build_config(data))

    d = engine.decide(IncomingMessage(chat_id="x", chat_name="小王他哥", text="在吗"))
    assert not d.should_reply
