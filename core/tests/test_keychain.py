from __future__ import annotations

import subprocess

from core import keychain


def test_environment_variable_takes_priority(monkeypatch) -> None:
    monkeypatch.setenv("TRACEMEMO_API_TOKEN", "from-environment")

    assert keychain.read_secret("TRACEMEMO_API_TOKEN", "unused") == "from-environment"


def test_keychain_is_used_when_environment_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("TRACEMEMO_API_TOKEN", raising=False)
    monkeypatch.setattr(
        keychain.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "from-keychain\n", ""),
    )

    assert keychain.read_secret("TRACEMEMO_API_TOKEN", "com.wxauto.test") == "from-keychain"


def test_keychain_failure_does_not_raise_or_expose_stderr(monkeypatch) -> None:
    monkeypatch.delenv("TRACEMEMO_API_TOKEN", raising=False)
    monkeypatch.setattr(
        keychain.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 44, "", "private detail"),
    )

    assert keychain.read_secret("TRACEMEMO_API_TOKEN", "com.wxauto.test") == ""
