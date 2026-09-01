#!/usr/bin/env python3
"""导出可导入 Android App 的脱敏会话语气画像。

输入是 macOS 自动回复已生成的 ``var/style-profiles.json``。脚本只向
TraceMemo 查询最近会话的显示名，用它替换画像内部的稳定 talker；导出文件
不包含微信 ID、API Token、完整聊天记录或时间戳。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from core.keychain import read_secret
from scripts.tracememo_contacts import (  # noqa: E402
    BASE_URL,
    TOKEN_SERVICE,
    TraceMemoContactsError,
    fetch_recent_contacts,
)


MAX_PROFILES = 120
MAX_EXAMPLES = 48
MAX_NAME_LENGTH = 80
MAX_SUMMARY_LENGTH = 600
MAX_SAMPLE_COUNT = 5_000
MAX_EXAMPLE_LENGTH = 240


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit].rstrip()


def _load_profile_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"画像缓存无法读取：{exc}") from exc
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, dict):
        raise ValueError("画像缓存格式不正确")
    return profiles


def _profile_for_android(display_name: str, raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = _clip(display_name, MAX_NAME_LENGTH)
    summary = _clip(raw.get("summary"), MAX_SUMMARY_LENGTH)
    try:
        sample_count = max(0, min(int(raw.get("sample_count", 0)), MAX_SAMPLE_COUNT))
    except (TypeError, ValueError):
        sample_count = 0

    examples: list[dict[str, str]] = []
    for raw_example in raw.get("examples") or []:
        if not isinstance(raw_example, dict):
            continue
        # macOS v2 uses incoming/reply. Legacy reply-only examples lack the
        # incoming side, therefore cannot safely participate in relevance search.
        them = _clip(raw_example.get("incoming"), MAX_EXAMPLE_LENGTH)
        me = _clip(raw_example.get("reply"), MAX_EXAMPLE_LENGTH)
        if them and me:
            examples.append({"them": them, "me": me})
        if len(examples) >= MAX_EXAMPLES:
            break
    if not name:
        return None
    return {
        "displayName": name,
        "summary": summary,
        "sampleCount": sample_count,
        "examples": examples,
    }


def build_export(profiles: dict[str, Any], contacts: list[dict[str, Any]]) -> dict[str, Any]:
    """按最近会话顺序输出，并拒绝没有当前显示名映射的旧画像。"""

    exported: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for contact in contacts:
        talker = str(contact.get("talker", "") or "")
        if not talker or talker not in profiles:
            continue
        profile = _profile_for_android(str(contact.get("name", "")), profiles[talker])
        if profile is None:
            continue
        normalized = profile["displayName"].strip().casefold()
        if not normalized or normalized in seen_names:
            continue
        seen_names.add(normalized)
        exported.append(profile)
        if len(exported) >= MAX_PROFILES:
            break
    return {"version": 1, "profiles": exported}


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as temporary:
        temporary.write(encoded)
        temporary_path = Path(temporary.name)
    try:
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 Android 可导入的脱敏会话画像")
    parser.add_argument("--profile-path", type=Path, default=REPO_DIR / "var/style-profiles.json")
    parser.add_argument("--output", type=Path, default=REPO_DIR / "var/android-style-profiles.json")
    parser.add_argument("--url", default=BASE_URL)
    parser.add_argument("--dry-run", action="store_true", help="只检查，不写出文件")
    args = parser.parse_args()

    try:
        raw_profiles = _load_profile_file(args.profile_path)
        token = read_secret("TRACEMEMO_API_TOKEN", TOKEN_SERVICE)
        if not token:
            raise TraceMemoContactsError("未找到 TraceMemo API Token")
        contacts = fetch_recent_contacts(token, args.url, limit=1000)
        payload = build_export(raw_profiles, contacts)
        if not args.dry_run:
            _write_private_json(args.output, payload)
        # 不输出名称或示例，避免终端历史留下聊天数据。
        print(json.dumps({"exported": len(payload["profiles"]), "written": not args.dry_run}))
        return 0
    except (TraceMemoContactsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
