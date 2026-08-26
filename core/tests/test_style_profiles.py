from types import SimpleNamespace

from core.style_profiles import build_style_profile


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
