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
        },
    )

    assert payload["enabled"] is False
    assert payload["scope"]["allow_contacts"] == ["Biscoffee"]
    assert payload["scope"]["allow_talkers"] == ["wxid_biscoffee"]
    assert payload["scope"]["block_keywords"] == ["验证码"]
    assert payload["limits"]["max_replies_per_chat_per_day"] == 0
    assert payload["persona"]["max_chars"] == 120


def test_interval_is_clamped_and_written_securely(tmp_path: Path, monkeypatch) -> None:
    interval_file = tmp_path / "var" / "poll-interval"
    monkeypatch.setattr(app_config, "_interval_path", lambda: interval_file)

    assert app_config._write_interval(1) == 5
    assert interval_file.read_text(encoding="utf-8") == "5\n"
    assert app_config._read_interval() == 5
