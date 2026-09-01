import pytest

from core.config import ConfigError, build_config
from core.persona import STYLE_PRESETS, build_persona, build_system_prompt


def test_grok41_preset_adds_direct_witty_guidance_without_tool_claims() -> None:
    persona = build_persona(
        {
            "identity": "独立开发者",
            "style_preset": "grok4_1",
        }
    )

    prompt = build_system_prompt(persona)

    assert "直接、清楚、少客套" in prompt
    assert "轻微吐槽或反讽" in prompt
    assert "X 搜索" not in prompt
    assert "调用工具" not in prompt
    assert "安全边界" in prompt


def test_empty_style_preset_keeps_existing_prompt_unchanged() -> None:
    persona = build_persona({"identity": "独立开发者"})

    assert persona.style_preset == ""
    assert "表达风格预设" not in build_system_prompt(persona)


def test_style_preset_is_explicitly_registered() -> None:
    assert set(STYLE_PRESETS) == {"grok4_1"}


def test_config_accepts_registered_style_preset() -> None:
    config = build_config(
        {
            "reply_mode": "ai",
            "persona": {"identity": "独立开发者", "style_preset": "grok4_1"},
        }
    )

    assert config.persona.style_preset == "grok4_1"


def test_config_rejects_unknown_style_preset() -> None:
    with pytest.raises(ConfigError, match="persona.style_preset"):
        build_config(
            {
                "reply_mode": "ai",
                "persona": {"identity": "独立开发者", "style_preset": "grok"},
            }
        )


def test_sending_config_defaults_deferred_reply_expiry_to_ten_minutes() -> None:
    config = build_config({"reply_mode": "rules"})

    assert config.sending.deferred_reply_expiry_seconds == 600


def test_sending_config_rejects_too_short_deferred_reply_expiry() -> None:
    with pytest.raises(ConfigError, match="deferred_reply_expiry_seconds"):
        build_config(
            {
                "reply_mode": "rules",
                "sending": {"deferred_reply_expiry_seconds": 59},
            }
        )
