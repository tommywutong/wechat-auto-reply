import json
from types import SimpleNamespace

from core.style_profiles import StyleProfileStore, build_style_profile


def _message(text: str, timestamp: int, outgoing: bool) -> SimpleNamespace:
    return SimpleNamespace(text=text, timestamp=timestamp, outgoing=outgoing)


def test_style_profile_uses_only_outgoing_messages_and_pairs_recent_turns() -> None:
    profile = build_style_profile(
        [
            _message("你在吗", 1, False),
            _message("在，咋了", 2, True),
            _message("哈哈哈哈", 3, False),
            _message("确实", 4, True),
            _message("外部不应进入画像", 5, False),
        ]
    )

    assert profile.sample_count == 2
    assert "平均" in profile.summary
    assert any(example.reply == "确实" for example in profile.examples)
    assert all("外部不应进入画像" not in example.reply for example in profile.examples)


def test_style_profile_removes_legacy_auto_reply_suffix() -> None:
    profile = build_style_profile(
        [_message("收到（由 AI 自动发送、自动回复）", 1, True)]
    )

    assert profile.sample_count == 1
    assert all("自动发送" not in example.reply for example in profile.examples)


def test_style_profile_retrieves_examples_relevant_to_current_message() -> None:
    profile = build_style_profile(
        [
            _message("项目进度怎么样", 1, False),
            _message("还在弄，差一点", 2, True),
            _message("明天去吃饭吗", 3, False),
            _message("行啊，去哪", 4, True),
            _message("周末一起吃饭不", 5, False),
            _message("可以，到时候说", 6, True),
        ]
    )

    examples = profile.examples_for("明天要不要一起吃饭")

    assert examples
    assert examples[0].reply in {"行啊，去哪", "可以，到时候说"}
    assert "项目进度怎么样" not in profile.prompt_context("明天要不要一起吃饭")


def test_style_profile_does_not_reinforce_generic_defer_reply_when_other_samples_exist() -> None:
    profile = build_style_profile(
        [
            _message("在吗", 1, False),
            _message("忙完再说", 2, True),
            _message("这个能看吗", 3, False),
            _message("可以，我看看", 4, True),
        ]
    )

    assert [example.reply for example in profile.examples] == ["可以，我看看"]


def test_style_profile_drops_generic_defer_replies_when_they_are_the_only_samples() -> None:
    profile = build_style_profile(
        [
            _message("在吗", 1, False),
            _message("忙完再说", 2, True),
            _message("方便吗", 3, False),
            _message("等会儿再说", 4, True),
        ]
    )

    assert profile.examples == ()


def test_style_profile_tie_breaking_does_not_compare_examples() -> None:
    profile = build_style_profile(
        [
            _message("甲乙", 1, False),
            _message("收到", 2, True),
            _message("甲丙", 3, False),
            _message("可以", 4, True),
        ]
    )

    assert len(profile.examples_for("甲丁", max_examples=2)) == 2


def test_legacy_profile_is_marked_for_refresh(tmp_path) -> None:
    path = tmp_path / "style-profiles.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": {
                    "wxid-a": {
                        "summary": "旧画像",
                        "sample_count": 1,
                        "updated_at": 123.0,
                        "examples": [{"incoming": "在吗", "reply": "晚点回"}],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    profile = StyleProfileStore(path).get("wxid-a")

    assert profile is not None
    assert profile.updated_at == 0
