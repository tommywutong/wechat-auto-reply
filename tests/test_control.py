from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from server import control


def test_pairing_code_is_valid_until_ttl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "pairing.json"
    path.write_text(json.dumps({"code": "abc123", "created_at": time.time()}), encoding="utf-8")
    monkeypatch.setattr(control, "PAIRING_FILE", path)
    assert control._read_pairing_code() == "abc123"

    path.write_text(json.dumps({"code": "abc123", "created_at": time.time() - control.PAIRING_TTL - 1}), encoding="utf-8")
    assert control._read_pairing_code() == ""


def test_pairing_code_rejects_malformed_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "pairing.json"
    path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(control, "PAIRING_FILE", path)
    assert control._read_pairing_code() == ""


def test_logs_redact_message_payload_without_losing_timestamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    var = tmp_path / "var"
    var.mkdir()
    (var / "tracememo-autoreply.log").write_text(
        "2026-08-31 12:00:00,000 INFO 状态：运行中\n"
        "2026-08-31 12:00:00,500 INFO 检测到新消息：会话 Biscoffee\n"
        "2026-08-31 12:00:01,000 INFO 草稿已生成：Biscoffee\n"
        "2026-08-31 12:00:02,000 INFO -> Biscoffee: 私人回复正文\n",
        encoding="utf-8",
    )
    (var / "tracememo-autoreply.err.log").write_text("2026-08-31 12:00:03,000 ERROR 发送失败\n", encoding="utf-8")
    monkeypatch.setattr(control, "REPO_DIR", tmp_path)
    lines = control._logs(10)
    assert lines[0].startswith("2026-08-31 12:00:00,000")
    assert lines[1].endswith("检测到新消息")
    assert "Biscoffee" not in lines[1]
    assert "Biscoffee" not in "\n".join(lines)
    assert "私人回复正文" not in "\n".join(lines)
    assert lines[-1].endswith("发送失败")


def test_require_token_uses_constant_time_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control, "CONTROL_TOKEN", "secret")
    control._require_token("Bearer secret")
    with pytest.raises(Exception) as exc_info:
        control._require_token("Bearer wrong")
    assert getattr(exc_info.value, "status_code", None) == 401
