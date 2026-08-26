#!/usr/bin/env python3
"""安全读取 TraceMemo 联系人/群聊列表，供 macOS 控制 App 使用。

Token 只从当前进程环境或 macOS Keychain 读取，不会写入 stdout、日志或配置文件。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Iterable

import requests

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from core.keychain import read_secret
from core.models import clean_chat_display_name

BASE_URL = "http://127.0.0.1:6131/api/v1"
TOKEN_SERVICE = "com.wxauto.tracememo-api-token"


class TraceMemoContactsError(RuntimeError):
    pass


def _record_lists(payload: Any) -> list[list[dict[str, Any]]]:
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return [payload]
    if isinstance(payload, dict):
        result: list[list[dict[str, Any]]] = []
        for value in payload.values():
            result.extend(_record_lists(value))
        return result
    return []


def _first_string(record: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = str(record.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "group"}


def _best_records(payload: Any) -> list[dict[str, Any]]:
    candidates = _record_lists(payload)
    if not candidates:
        return []
    return max(
        candidates,
        key=lambda records: sum(
            1 for record in records if any(key in record for key in ("m_nsUsrName", "talker", "username"))
        ),
    )


def parse_contacts(payload: Any, *, preserve_order: bool = False) -> list[dict[str, Any]]:
    """把 TraceMemo 的响应规整为稳定、可供 UI 展示的会话对象。"""

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in _best_records(payload):
        talker = _first_string(record, ("m_nsUsrName", "talker", "username", "wxid", "conversationId"))
        if not talker or talker in seen:
            continue
        seen.add(talker)
        aliases: list[str] = []
        for key in ("remark", "m_nsNickName", "wechatNickname", "nickname", "displayName", "chatName", "name"):
            value = clean_chat_display_name(str(record.get(key, "") or ""))
            if value and value not in aliases:
                aliases.append(value)
        name = aliases[0] if aliases else talker
        raw_type = str(record.get("type", "") or "").strip().lower()
        is_group = raw_type in {"group", "chatroom"} or talker.endswith("@chatroom")
        result.append(
            {
                "talker": talker,
                "name": name,
                "aliases": aliases,
                "isGroup": is_group,
                "isOfficialAccount": _as_bool(record.get("isOfficialAccount")),
                "isFolded": _as_bool(record.get("isFolded")),
                "isMuted": _as_bool(record.get("isMuted")),
            }
        )
    if preserve_order:
        return result
    return sorted(result, key=lambda item: (bool(item["isGroup"]), str(item["name"]).casefold(), item["talker"]))


def _fetch_payload(
    token: str,
    base_url: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> Any:
    if not token:
        raise TraceMemoContactsError("未找到 TraceMemo API Token")
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        if response.status_code == 401:
            raise TraceMemoContactsError("TraceMemo Token 无效或已轮换")
        if response.status_code == 503:
            raise TraceMemoContactsError("TraceMemo 数据库尚未就绪")
        response.raise_for_status()
        return response.json()
    except TraceMemoContactsError:
        raise
    except (requests.RequestException, ValueError) as exc:
        raise TraceMemoContactsError(f"TraceMemo 联系人读取失败：{exc}") from exc


def fetch_contacts(token: str, base_url: str = BASE_URL) -> list[dict[str, Any]]:
    return parse_contacts(_fetch_payload(token, base_url, "contact"))


def fetch_recent_contacts(
    token: str,
    base_url: str = BASE_URL,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """读取按最近活跃顺序返回的会话，并记录每个会话的排序位置。"""

    records = parse_contacts(
        _fetch_payload(token, base_url, "recent_chat", params={"limit": max(30, limit)}),
        preserve_order=True,
    )
    for rank, record in enumerate(records):
        record["recentRank"] = rank
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("list",))
    parser.add_argument("--type", choices=("all", "private", "group"), default="all")
    parser.add_argument("--url", default=BASE_URL)
    args = parser.parse_args()
    try:
        token = read_secret("TRACEMEMO_API_TOKEN", TOKEN_SERVICE)
        # recent_chat 能覆盖完整会话列表，同时保留微信侧的最近活跃顺序。
        # 某些旧版 TraceMemo 没有该端点时，退回联系人列表，搜索仍可用。
        try:
            contacts = fetch_recent_contacts(token, args.url)
        except TraceMemoContactsError:
            contacts = fetch_contacts(token, args.url)
        if args.type == "private":
            contacts = [item for item in contacts if not item["isGroup"]]
        elif args.type == "group":
            contacts = [item for item in contacts if item["isGroup"]]
        print(json.dumps({"contacts": contacts, "count": len(contacts)}, ensure_ascii=False))
        return 0
    except TraceMemoContactsError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
