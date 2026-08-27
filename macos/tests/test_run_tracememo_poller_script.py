from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCRIPT = REPO_ROOT / "scripts" / "run-tracememo-poller.sh"


def _write_executable(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def test_launcher_uses_shared_poll_interval(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / SOURCE_SCRIPT.name
    script.parent.mkdir(parents=True)
    shutil.copy2(SOURCE_SCRIPT, script)
    _write_executable(
        tmp_path / ".venv" / "bin" / "python",
        "#!/bin/sh\nprintf '%s\\n' \"$@\"\n",
    )

    fake_bin = tmp_path / "bin"
    _write_executable(fake_bin / "uname", "#!/bin/sh\necho Darwin\n")
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"

    default = subprocess.run(
        ["/bin/bash", str(script), "--probe"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert default.stdout.splitlines() == [
        "macos/tracememo_poller.py",
        "--interval",
        "5",
        "--probe",
    ]

    interval_file = tmp_path / "var" / "poll-interval"
    interval_file.parent.mkdir()
    interval_file.write_text("12\n", encoding="utf-8")
    configured = subprocess.run(
        ["/bin/bash", str(script), "--probe"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert configured.stdout.splitlines() == [
        "macos/tracememo_poller.py",
        "--interval",
        "12",
        "--probe",
    ]
