from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCRIPT = REPO_ROOT / "scripts" / "run-tracememo-autoreply.sh"


def _write_executable(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def test_launcher_handles_replay_flag_with_macos_bash(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / SOURCE_SCRIPT.name
    script.parent.mkdir(parents=True)
    shutil.copy2(SOURCE_SCRIPT, script)

    _write_executable(
        tmp_path / ".venv" / "bin" / "python",
        "#!/bin/sh\nprintf '%s\\n' \"$@\"\n",
    )
    for helper in ("vision-ocr", "mouse-click", "mouse-scroll"):
        _write_executable(tmp_path / ".build" / helper, "#!/bin/sh\nexit 0\n")

    fake_bin = tmp_path / "bin"
    _write_executable(fake_bin / "uname", "#!/bin/sh\necho Darwin\n")
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"

    without_replay = subprocess.run(
        ["/bin/bash", str(script), "--probe"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert without_replay.stdout.splitlines() == [
        "macos/tracememo_poller.py",
        "--interval",
        "5",
        "--send",
        "--send-all",
        "--probe",
    ]

    replay_file = tmp_path / "var" / "replay-offline"
    replay_file.parent.mkdir()
    replay_file.write_text("true\n", encoding="utf-8")
    with_replay = subprocess.run(
        ["/bin/bash", str(script), "--probe"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert with_replay.stdout.splitlines() == [
        "macos/tracememo_poller.py",
        "--replay-offline",
        "--interval",
        "5",
        "--send",
        "--send-all",
        "--probe",
    ]
