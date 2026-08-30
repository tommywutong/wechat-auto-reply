#!/usr/bin/env python3
"""Bridge safe app settings between SwiftUI and the YAML configuration.

The desktop app calls this helper with JSON on stdin/stdout. Secrets and raw
conversation history are deliberately not exposed here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml


def _repo_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _config_path() -> Path:
    value = os.environ.get("WXAUTO_CONFIG", "").strip()
    path = Path(value) if value else _repo_dir() / "core" / "config.yaml"
    return path if path.is_absolute() else _repo_dir() / path


def _interval_path() -> Path:
    value = os.environ.get("WXAUTO_INTERVAL_FILE", "").strip()
    path = Path(value) if value else _repo_dir() / "var" / "poll-interval"
    return path if path.is_absolute() else _repo_dir() / path


def _replay_offline_path() -> Path:
    value = os.environ.get("WXAUTO_REPLAY_OFFLINE_FILE", "").strip()
    path = Path(value) if value else _repo_dir() / "var" / "replay-offline"
    return path if path.is_absolute() else _repo_dir() / path


def _read_interval() -> int:
    try:
        value = int(_interval_path().read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return 5
    return max(5, min(value, 300))


def _read_replay_offline() -> bool:
    try:
        return _replay_offline_path().read_text(encoding="utf-8").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    except (FileNotFoundError, OSError):
        return False


def _write_interval(value: Any) -> int:
    interval = max(5, min(int(value), 300))
    path = _interval_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{interval}\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return interval


def _write_replay_offline(value: Any) -> bool:
    if isinstance(value, str):
        enabled = value.strip().lower() in {"1", "true", "yes", "on"}
    else:
        enabled = bool(value)
    path = _replay_offline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n" if enabled else "0\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return enabled


def _load() -> dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        raise RuntimeError(f"配置文件不存在：{path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError("配置文件顶层必须是对象")
    return payload


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_persona_examples(value: Any) -> list[dict[str, str]]:
    """只保留可安全写回 YAML 的示例对话字段。"""
    if not isinstance(value, list):
        return []
    examples: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        incoming = str(item.get("them", item.get("incoming", "")) or "").strip()
        reply = str(item.get("me", item.get("reply", "")) or "").strip()
        note = str(item.get("note", "") or "").strip()
        if incoming and reply:
            examples.append({"them": incoming, "me": reply, "note": note})
    return examples


def _public_settings(data: dict[str, Any]) -> dict[str, Any]:
    scope = data.get("scope") or {}
    limits = data.get("limits") or {}
    llm = data.get("llm") or {}
    persona = data.get("persona") or {}
    sending = data.get("sending") or {}
    return {
        "enabled": bool(data.get("enabled", True)),
        "replyMode": str(data.get("reply_mode", "ai")),
        "replyToPrivate": bool(scope.get("reply_to_private", True)),
        "replyToGroup": str(scope.get("reply_to_group", "only_at_me")),
        "selfNicknames": _as_string_list(scope.get("self_nicknames")),
        "allowContacts": _as_string_list(scope.get("allow_contacts")),
        "allowTalkers": _as_string_list(scope.get("allow_talkers")),
        "blockContacts": _as_string_list(scope.get("block_contacts")),
        "blockKeywords": _as_string_list(scope.get("block_keywords")),
        "activeHours": [str(item).strip() for item in (data.get("active_hours") or []) if str(item).strip()],
        "pollInterval": _read_interval(),
        "replayOfflineOnStart": _read_replay_offline(),
        "provider": str(llm.get("provider", "deepseek")),
        "model": str(llm.get("model", "deepseek-chat")),
        "visionProvider": str(llm.get("vision_provider", "qwen_bailian")),
        "visionModel": str(llm.get("vision_model", "qwen3-vl-flash")),
        "visionFallbackModel": str(llm.get("vision_fallback_model", "qwen3-vl-plus")),
        "visionBaseUrl": str(llm.get("vision_base_url", "")),
        "visionEnabled": bool(llm.get("vision_enabled", True)),
        "maxTokens": int(llm.get("max_tokens", 300)),
        "maxChars": int(persona.get("max_chars", 80)),
        "personaIdentity": str(persona.get("identity", "")),
        "personaTone": str(persona.get("tone", "")),
        "personaPlaybook": str(persona.get("playbook", "")),
        "personaBoundaries": _as_string_list(persona.get("boundaries")),
        "personaExamples": _as_persona_examples(persona.get("examples")),
        "personaStylePreset": str(persona.get("style_preset", "")).strip().lower(),
        "quietMode": bool(sending.get("quiet_mode", True)),
        "onlyWhenUserIdle": bool(sending.get("only_when_user_idle", True)),
        "userIdleSeconds": float(sending.get("user_idle_seconds", 1.5)),
        "allowFrontmostSwitch": bool(sending.get("allow_frontmost_switch", True)),
        "deferredRetrySeconds": float(sending.get("deferred_retry_seconds", 15.0)),
        "perChatCooldownSeconds": int(limits.get("per_chat_cooldown_seconds", 0)),
        "maxRepliesPerChatPerDay": int(limits.get("max_replies_per_chat_per_day", 0)),
        "globalMaxPerHour": int(limits.get("global_max_replies_per_hour", 30)),
        "globalMaxPerDay": int(limits.get("global_max_replies_per_day", 100)),
        "globalMinIntervalSeconds": int(limits.get("global_min_interval_seconds", 0)),
        "minDelaySeconds": float(limits.get("min_delay_seconds", 0)),
        "maxDelaySeconds": float(limits.get("max_delay_seconds", 0)),
        "typingSecondsPerChar": float(limits.get("typing_seconds_per_char", 0)),
    }


def _set_path(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = data
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _apply(data: dict[str, Any], patch: dict[str, Any]) -> None:
    mapping: dict[str, tuple[str, ...]] = {
        "enabled": ("enabled",),
        "replyMode": ("reply_mode",),
        "replyToPrivate": ("scope", "reply_to_private"),
        "replyToGroup": ("scope", "reply_to_group"),
        "selfNicknames": ("scope", "self_nicknames"),
        "allowContacts": ("scope", "allow_contacts"),
        "allowTalkers": ("scope", "allow_talkers"),
        "blockContacts": ("scope", "block_contacts"),
        "blockKeywords": ("scope", "block_keywords"),
        "activeHours": ("active_hours",),
        "provider": ("llm", "provider"),
        "model": ("llm", "model"),
        "visionProvider": ("llm", "vision_provider"),
        "visionModel": ("llm", "vision_model"),
        "visionFallbackModel": ("llm", "vision_fallback_model"),
        "visionBaseUrl": ("llm", "vision_base_url"),
        "visionEnabled": ("llm", "vision_enabled"),
        "maxTokens": ("llm", "max_tokens"),
        "maxChars": ("persona", "max_chars"),
        "personaIdentity": ("persona", "identity"),
        "personaTone": ("persona", "tone"),
        "personaPlaybook": ("persona", "playbook"),
        "personaBoundaries": ("persona", "boundaries"),
        "personaExamples": ("persona", "examples"),
        "personaStylePreset": ("persona", "style_preset"),
        "quietMode": ("sending", "quiet_mode"),
        "onlyWhenUserIdle": ("sending", "only_when_user_idle"),
        "userIdleSeconds": ("sending", "user_idle_seconds"),
        "allowFrontmostSwitch": ("sending", "allow_frontmost_switch"),
        "deferredRetrySeconds": ("sending", "deferred_retry_seconds"),
        "perChatCooldownSeconds": ("limits", "per_chat_cooldown_seconds"),
        "maxRepliesPerChatPerDay": ("limits", "max_replies_per_chat_per_day"),
        "globalMaxPerHour": ("limits", "global_max_replies_per_hour"),
        "globalMaxPerDay": ("limits", "global_max_replies_per_day"),
        "globalMinIntervalSeconds": ("limits", "global_min_interval_seconds"),
        "minDelaySeconds": ("limits", "min_delay_seconds"),
        "maxDelaySeconds": ("limits", "max_delay_seconds"),
        "typingSecondsPerChar": ("limits", "typing_seconds_per_char"),
    }
    allowed_modes = {"ai", "rules", "rules_then_ai"}
    allowed_groups = {"never", "only_at_me", "always"}
    allowed_style_presets = {"", "grok4_1"}
    for key, path in mapping.items():
        if key not in patch:
            continue
        value = patch[key]
        if key == "replyMode" and value not in allowed_modes:
            raise ValueError("replyMode 无效")
        if key == "replyToGroup" and value not in allowed_groups:
            raise ValueError("replyToGroup 无效")
        if key == "personaStylePreset":
            value = str(value or "").strip().lower()
            if value not in allowed_style_presets:
                raise ValueError("personaStylePreset 无效")
        if key in {"selfNicknames", "allowContacts", "allowTalkers", "blockContacts", "blockKeywords", "activeHours", "personaBoundaries"}:
            value = _as_string_list(value)
        if key == "personaExamples":
            value = _as_persona_examples(value)
        if key in {"maxTokens", "maxChars", "globalMaxPerHour", "globalMaxPerDay"}:
            value = max(1, min(int(value), 10_000))
        if key == "maxRepliesPerChatPerDay":
            value = max(0, min(int(value), 10_000))
        if key in {"perChatCooldownSeconds", "globalMinIntervalSeconds"}:
            value = max(0, min(int(value), 86_400))
        if key in {"minDelaySeconds", "maxDelaySeconds", "typingSecondsPerChar"}:
            value = max(0.0, min(float(value), 60.0))
        if key == "userIdleSeconds":
            value = max(0.0, min(float(value), 60.0))
        if key == "deferredRetrySeconds":
            value = max(1.0, min(float(value), 3600.0))
        _set_path(data, path, value)

    limits = data.get("limits") or {}
    minimum = float(limits.get("min_delay_seconds", 0) or 0)
    maximum = float(limits.get("max_delay_seconds", 0) or 0)
    if minimum > maximum:
        raise ValueError("最短等待不能大于最长等待")


def _write(data: dict[str, Any]) -> None:
    path = _config_path()
    backup = path.with_suffix(path.suffix + ".before-app-edit")
    if path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(backup, 0o600)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("get", "set"))
    args = parser.parse_args()
    try:
        data = _load()
        if args.command == "get":
            print(json.dumps(_public_settings(data), ensure_ascii=False))
            return 0
        patch = json.load(sys.stdin)
        if not isinstance(patch, dict):
            raise ValueError("设置补丁必须是对象")
        interval = patch.pop("pollInterval", None)
        replay_offline = patch.pop("replayOfflineOnStart", None)
        _apply(data, patch)
        if interval is not None:
            _write_interval(interval)
        if replay_offline is not None:
            _write_replay_offline(replay_offline)
        _write(data)
        print(json.dumps(_public_settings(data), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, yaml.YAMLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
