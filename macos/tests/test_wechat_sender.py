from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "wechat_sender.py"
SPEC = importlib.util.spec_from_file_location("wechat_sender", MODULE_PATH)
assert SPEC and SPEC.loader
sender = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sender
SPEC.loader.exec_module(sender)


def test_has_exact_ignores_ocr_whitespace() -> None:
    observations = (
        sender.OCRObservation("Bisco", 0.1, 0.2, 0.1, 0.03),
        sender.OCRObservation("ffee", 0.2, 0.2, 0.1, 0.03),
    )
    assert sender._has_exact(observations, "Biscoffee", y_min=0.1, y_max=0.4)


def test_has_exact_does_not_accept_other_name() -> None:
    observations = (sender.OCRObservation("Biscoffee2", 0.1, 0.2, 0.2, 0.03),)
    assert not sender._has_exact(observations, "Biscoffee", y_min=0.1, y_max=0.4)


def test_has_exact_accepts_group_member_count_in_title() -> None:
    observations = (sender.OCRObservation("iOS蛋蛋牛离异带五娃(7)", 0.4, 0.05, 0.3, 0.03),)

    assert sender._has_exact(observations, "iOS蛋蛋牛离异带五娃", y_min=0.0, y_max=0.2)


def test_contains_text_accepts_wrapped_input_with_signature() -> None:
    observations = (
        sender.OCRObservation("回复内容（由 AI 自动", 0.1, 0.82, 0.4, 0.03),
        sender.OCRObservation("发送、自动回复）", 0.1, 0.87, 0.4, 0.03),
    )
    assert sender._contains_text(observations, "回复内容", y_min=0.78, y_max=1.0)


def test_contains_text_ignores_emoji_that_vision_does_not_ocr() -> None:
    observations = (sender.OCRObservation("收到", 0.2, 0.82, 0.1, 0.03),)

    assert sender._contains_text(observations, "收到😂", y_min=0.78, y_max=1.0)


def test_emoji_only_detection_supports_variation_selectors() -> None:
    assert sender._emoji_only("😂👍🏻")
    assert not sender._emoji_only("收到😂")


def test_find_send_button_only_accepts_bottom_right_exact_label() -> None:
    observations = (
        sender.OCRObservation("发送", 0.84, 0.93, 0.05, 0.03),
        sender.OCRObservation("发送", 0.10, 0.80, 0.05, 0.03),
        sender.OCRObservation("发送中", 0.90, 0.93, 0.08, 0.03),
    )

    button = sender._find_send_button(observations)

    assert button is not None
    assert button.x == 0.84


def test_dynamic_layout_helpers_use_actual_ocr_positions() -> None:
    button = sender.OCRObservation("③〔发送", 0.86, 0.94, 0.09, 0.03)

    region = sender._input_region_from_button(button)

    assert region[0] < 0.36 < region[1]
    assert region[2] < 0.75 < region[3]


def test_sidebar_target_excludes_header_title() -> None:
    observations = (
        sender.OCRObservation("Biscoffee", 0.346, 0.027, 0.077, 0.015),
        sender.OCRObservation("Biscoffee", 0.148, 0.084, 0.076, 0.017),
    )

    target = sender._find_sidebar_target(observations, "Biscoffee")

    assert target is not None
    assert target.y == 0.084


def test_sidebar_target_joins_split_long_group_name() -> None:
    observations = (
        sender.OCRObservation("iOS 蛋蛋牛离异", 0.15, 0.20, 0.12, 0.02),
        sender.OCRObservation("带五娃", 0.27, 0.20, 0.08, 0.02),
    )

    target = sender._find_sidebar_target(observations, "iOS蛋蛋牛离异带五娃")

    assert target is not None
    assert target.y == 0.20
    assert target.x < 0.16


def test_sidebar_target_accepts_truncated_prefix_for_title_confirmation() -> None:
    observations = (
        sender.OCRObservation("iOS蛋蛋牛离异带五", 0.15, 0.20, 0.22, 0.02),
    )

    target = sender._find_sidebar_target(observations, "iOS蛋蛋牛离异带五娃")

    assert target is not None
    assert target.text.startswith("iOS蛋蛋牛离异带五")


def test_group_search_accepts_member_count_suffix() -> None:
    observations = (
        sender.OCRObservation("群聊", 0.12, 0.14, 0.08, 0.02),
        sender.OCRObservation("iOS蛋蛋牛离异带五娃 (7)", 0.15, 0.22, 0.25, 0.03),
    )

    target = sender._find_search_target(
        observations, "iOS蛋蛋牛离异带五娃", is_group=True
    )

    assert target is not None
    assert "五娃" in target.text


def test_group_search_accepts_long_truncated_name_for_later_title_confirmation() -> None:
    observations = (sender.OCRObservation("iOS蛋蛋牛离异…", 0.15, 0.22, 0.20, 0.03),)

    assert sender._find_search_target(
        observations, "iOS蛋蛋牛离异带五娃", is_group=True
    ) is not None


def test_private_search_rejects_similar_contact() -> None:
    observations = (sender.OCRObservation("Biscoffee2", 0.15, 0.22, 0.20, 0.03),)

    assert sender._find_search_target(observations, "Biscoffee") is None


def test_sidebar_fingerprint_tracks_visible_rows() -> None:
    first = (
        sender.OCRObservation("Loky", 0.15, 0.20, 0.10, 0.03),
        sender.OCRObservation("Biscoffee", 0.15, 0.30, 0.15, 0.03),
    )
    second = (sender.OCRObservation("William", 0.15, 0.20, 0.12, 0.03),)

    assert sender._sidebar_fingerprint(first) != sender._sidebar_fingerprint(second)


def test_sidebar_click_scans_visible_list_then_broad_scrolls(tmp_path: Path, monkeypatch) -> None:
    instance = sender.WeChatSender(repo_dir=tmp_path)
    bounds = sender.WindowBounds(10, 20, 1200, 800)
    calls: list[tuple[str, object]] = []
    target = sender.OCRObservation("Biscoffee", 0.15, 0.30, 0.12, 0.03)
    visible = iter((None, target))

    monkeypatch.setattr(
        instance,
        "_sidebar_snapshot",
        lambda current, name: (next(visible), ("row",)),
    )
    monkeypatch.setattr(instance, "_scroll_sidebar", lambda current, delta: calls.append(("scroll", delta)))
    monkeypatch.setattr(instance, "_click_point", lambda x, y, label: calls.append(("click", (x, y, label))))
    monkeypatch.setattr(instance, "_is_current_target", lambda current, name: True)
    monkeypatch.setattr(sender, "_window_bounds", lambda: bounds)
    monkeypatch.setattr(sender.time, "sleep", lambda _: None)

    assert instance._click_sidebar_target(bounds, "Biscoffee")
    assert calls[0] == ("scroll", 35)
    assert calls[1][0] == "click"
    assert all(kind != "scroll" for kind, _ in calls[1:])


def test_sidebar_scroll_plan_covers_down_and_reverse_directions() -> None:
    deltas = sender.WeChatSender._SIDEBAR_SCROLL_DELTAS

    assert deltas[:8] == (35,) * 8
    assert deltas[8:] == (-35,) * 16
    assert sum(abs(delta) for delta in deltas) == 840


def test_sender_error_records_whether_final_action_was_attempted() -> None:
    before_send = sender.SenderError("标题未确认")
    after_send = sender.SenderError("结果未知", send_attempted=True)

    assert before_send.send_attempted is False
    assert after_send.send_attempted is True


def test_quiet_sender_defers_while_user_is_active(tmp_path: Path, monkeypatch) -> None:
    instance = sender.WeChatSender(
        repo_dir=tmp_path,
        quiet_mode=True,
        only_when_user_idle=True,
        user_idle_seconds=1.5,
        deferred_retry_seconds=12,
    )
    monkeypatch.setattr(instance, "_user_idle_for", lambda: 0.4)

    try:
        instance._ensure_user_idle("发送前")
    except sender.DeferredSendError as exc:
        assert exc.defer_retry is True
        assert exc.send_attempted is False
        assert exc.retry_after == 12
    else:
        raise AssertionError("expected active user to defer sending")


def test_quiet_sender_allows_send_after_idle_threshold(tmp_path: Path, monkeypatch) -> None:
    instance = sender.WeChatSender(
        repo_dir=tmp_path,
        quiet_mode=True,
        only_when_user_idle=True,
        user_idle_seconds=1.5,
    )
    monkeypatch.setattr(instance, "_user_idle_for", lambda: 2.0)

    instance._ensure_user_idle("发送前")


def test_disabled_quiet_mode_does_not_require_idle_helper(tmp_path: Path, monkeypatch) -> None:
    instance = sender.WeChatSender(repo_dir=tmp_path, quiet_mode=False)
    monkeypatch.setattr(instance, "_user_idle_for", lambda: None)

    instance._ensure_user_idle("发送前")


def test_post_send_check_tolerates_transient_ocr_residue(tmp_path: Path, monkeypatch) -> None:
    instance = sender.WeChatSender(repo_dir=tmp_path)
    statuses = iter((True, False))
    monkeypatch.setattr(instance, "_draft_present", lambda bounds, text: next(statuses))
    monkeypatch.setattr(sender.time, "sleep", lambda _: None)

    result = instance._post_send_check(
        sender.WindowBounds(0, 0, 1000, 1000),
        "回复内容",
    )

    assert result is False
