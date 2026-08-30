from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "app_config.py"
SPEC = importlib.util.spec_from_file_location("app_config", MODULE_PATH)
assert SPEC and SPEC.loader
app_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app_config)


def test_public_settings_never_expose_credentials() -> None:
    payload = {
        "enabled": True,
        "scope": {"allow_contacts": ["测试联系人"], "allow_talkers": ["wxid-test"]},
        "llm": {"provider": "deepseek", "api_key": "secret"},
    }

    result = app_config._public_settings(payload)

    assert "api_key" not in result
    assert "secret" not in str(result)
    assert result["allowContacts"] == ["测试联系人"]
    assert result["allowTalkers"] == ["wxid-test"]
    assert "blockKeywords" in result
    assert "personaTone" in result
    assert result["personaStylePreset"] == ""


def test_public_settings_include_vision_configuration_without_credentials() -> None:
    result = app_config._public_settings(
        {
            "llm": {
                "vision_provider": "qwen_bailian",
                "vision_model": "qwen3-vl-flash",
                "vision_fallback_model": "qwen3-vl-plus",
                "vision_base_url": "https://example.invalid/v1",
                "vision_enabled": True,
                "api_key": "must-not-appear",
            }
        }
    )

    assert result["visionProvider"] == "qwen_bailian"
    assert result["visionModel"] == "qwen3-vl-flash"
    assert result["visionFallbackModel"] == "qwen3-vl-plus"
    assert result["visionBaseUrl"] == "https://example.invalid/v1"
    assert result["visionEnabled"] is True
    assert "must-not-appear" not in str(result)


def test_apply_updates_only_safe_fields() -> None:
    payload = {"scope": {}, "llm": {}, "limits": {}, "persona": {}}

    app_config._apply(
        payload,
        {
            "enabled": False,
            "replyMode": "ai",
            "replyToGroup": "only_at_me",
            "allowContacts": ["Biscoffee"],
            "allowTalkers": ["wxid_biscoffee"],
            "blockKeywords": ["验证码"],
            "maxRepliesPerChatPerDay": 0,
            "maxChars": 120,
            "personaIdentity": "独立开发者",
            "personaPlaybook": "重要事项等本人回复",
            "personaBoundaries": ["不承诺具体时间"],
            "personaExamples": [{"them": "在吗", "me": "在，怎么了", "note": "简短"}],
            "personaStylePreset": "grok4_1",
        },
    )

    assert payload["enabled"] is False
    assert payload["scope"]["allow_contacts"] == ["Biscoffee"]
    assert payload["scope"]["allow_talkers"] == ["wxid_biscoffee"]
    assert payload["scope"]["block_keywords"] == ["验证码"]
    assert payload["limits"]["max_replies_per_chat_per_day"] == 0
    assert payload["persona"]["max_chars"] == 120
    assert payload["persona"]["identity"] == "独立开发者"
    assert payload["persona"]["playbook"] == "重要事项等本人回复"
    assert payload["persona"]["boundaries"] == ["不承诺具体时间"]
    assert payload["persona"]["examples"] == [{"them": "在吗", "me": "在，怎么了", "note": "简短"}]
    assert payload["persona"]["style_preset"] == "grok4_1"


def test_apply_rejects_unknown_style_preset() -> None:
    payload = {"persona": {}}

    try:
        app_config._apply(payload, {"personaStylePreset": "unknown"})
    except ValueError as exc:
        assert "personaStylePreset" in str(exc)
    else:
        raise AssertionError("expected unknown style preset to fail")


def test_apply_rejects_inverted_delay_range() -> None:
    payload = {"limits": {"min_delay_seconds": 1, "max_delay_seconds": 2}}

    try:
        app_config._apply(payload, {"minDelaySeconds": 10, "maxDelaySeconds": 2})
    except ValueError as exc:
        assert "最短等待" in str(exc)
    else:
        raise AssertionError("expected inverted delay range to fail")


def test_interval_is_clamped_and_written_securely(tmp_path: Path, monkeypatch) -> None:
    interval_file = tmp_path / "var" / "poll-interval"
    monkeypatch.setattr(app_config, "_interval_path", lambda: interval_file)

    assert app_config._write_interval(1) == 5
    assert interval_file.read_text(encoding="utf-8") == "5\n"
    assert app_config._read_interval() == 5


def test_replay_offline_flag_is_stored_outside_yaml(tmp_path: Path, monkeypatch) -> None:
    replay_file = tmp_path / "var" / "replay-offline"
    monkeypatch.setattr(app_config, "_replay_offline_path", lambda: replay_file)

    assert app_config._read_replay_offline() is False
    assert app_config._write_replay_offline(True) is True
    assert replay_file.read_text(encoding="utf-8") == "1\n"
    assert app_config._read_replay_offline() is True
    assert app_config._write_replay_offline(False) is False
    assert app_config._read_replay_offline() is False


def test_public_settings_expose_replay_offline_flag(tmp_path: Path, monkeypatch) -> None:
    replay_file = tmp_path / "var" / "replay-offline"
    monkeypatch.setattr(app_config, "_replay_offline_path", lambda: replay_file)
    app_config._write_replay_offline(True)

    result = app_config._public_settings({})

    assert result["replayOfflineOnStart"] is True


def test_public_settings_and_apply_support_quiet_sending() -> None:
    payload = {"sending": {}}
    app_config._apply(
        payload,
        {
            "quietMode": True,
            "onlyWhenUserIdle": True,
            "userIdleSeconds": 2.5,
            "allowFrontmostSwitch": False,
            "deferredRetrySeconds": 20,
        },
    )

    settings = app_config._public_settings(payload)
    assert settings["quietMode"] is True
    assert settings["onlyWhenUserIdle"] is True
    assert settings["userIdleSeconds"] == 2.5
    assert settings["allowFrontmostSwitch"] is False
    assert settings["deferredRetrySeconds"] == 20
