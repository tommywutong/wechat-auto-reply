"""通过 TraceMemo 轮询当前个人微信的白名单会话，并生成本地草稿。

这个采集端只负责读取 TraceMemo、识别新入站消息并调用现有规则服务；
图片和表情包会尽力做本地 OCR，无法识别时保留明确的媒体占位信息。
默认永远不操作微信界面，也不会向 TraceMemo 的机器人接口发送消息。
"""

from __future__ import annotations

import argparse
import dataclasses
import fcntl
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import requests

# 这个文件既会被 pytest 导入，也会被 launchd 直接作为脚本运行。
# 直接运行时 Python 只会把 macos/ 放进 sys.path，需要显式补上仓库根目录。
REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from core.config import load_config
from core.keychain import read_secret
from core.models import clean_chat_display_name, normalize_chat_name
from core.style_profiles import StyleProfile, StyleProfileStore, build_style_profile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tracememo-poller")

TRACE_MEMO_BASE_URL = "http://127.0.0.1:6131/api/v1"
TRACE_MEMO_KEYCHAIN_SERVICE = "com.wxauto.tracememo-api-token"
MAX_SEND_RETRIES = 3
SEND_RETRY_DELAY_SECONDS = 3.0

_TALKER_KEYS = (
    "m_nsUsrName",
    "talker",
    "username",
    "userName",
    "user_name",
    "wxid",
    "conversationId",
)
_NAME_KEYS = (
    "remark",
    "m_nsNickName",
    "wechatNickname",
    "nickname",
    "displayName",
    "chatName",
    "name",
    "talker",
)
_TEXT_KEYS = ("content", "strContent", "msgContent", "message", "text", "body")
_MEDIA_URL_KEYS = ("url", "encryptUrl", "imageUrl", "img", "path", "filePath", "localPath")
_MEDIA_ID_KEYS = ("md5", "mediaId", "aeskey", "datName")
_ID_KEYS = ("serverId", "msgSvrId", "msgId", "localId", "messageId", "id")
_TIME_KEYS = ("createTime", "datetime", "msgTime", "timestamp", "time", "lastMsgTime")
_OUTGOING_KEYS = ("isSender", "isSend", "isSelf", "fromMe", "isOutgoing", "outgoing")
_SENDER_KEYS = ("name", "senderName", "sender", "fromUser", "fromUserName", "from")
_GROUP_KEYS = ("isChatRoom", "isGroup", "is_group", "group")
_ALIAS_KEYS = ("remark", "m_nsNickName", "wechatNickname", "nickname", "displayName", "chatName", "name")
STYLE_HISTORY_DAYS = 30
STYLE_PROFILE_REFRESH_SECONDS = 86_400


class TraceMemoError(RuntimeError):
    """TraceMemo 未启动、鉴权失败或响应无法安全解析。"""


@dataclass(frozen=True)
class Conversation:
    talker: str
    name: str
    is_group: bool
    aliases: tuple[str, ...] = field(default=(), compare=False)


@dataclass(frozen=True)
class ChatMessage:
    message_id: str
    talker: str
    chat_name: str
    text: str
    timestamp: float
    sender_name: str
    is_group: bool
    outgoing: bool
    mentioned_me: bool = False
    message_type: str = "text"
    media_url: str = ""
    media_id: str = ""
    ocr_text: str = ""
    message_ids: tuple[str, ...] = ()
    batch_size: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "message_type", (self.message_type or "text").strip().lower())
        ids = tuple(self.message_ids) or (self.message_id,)
        object.__setattr__(self, "message_ids", ids)
        object.__setattr__(self, "batch_size", max(int(self.batch_size or 1), len(ids)))


def _first_string(data: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _first_bool(data: dict[str, Any], keys: Iterable[str]) -> Optional[bool]:
    for key in keys:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "outgoing", "self"}:
                return True
            if lowered in {"0", "false", "no", "incoming", "other"}:
                return False
    return None


def _contains_self_mention(text: str, self_nicknames: Iterable[str]) -> bool:
    """TraceMemo 当前版本把群聊 @ 保留为 ``@昵称`` 文本。"""

    normalized_text = (text or "").replace("＠", "@").casefold()
    for raw_name in self_nicknames:
        nickname = str(raw_name or "").strip()
        if not nickname:
            continue
        needle = "@" + nickname.casefold()
        start = 0
        while True:
            index = normalized_text.find(needle, start)
            if index < 0:
                break
            after = normalized_text[index + len(needle) : index + len(needle) + 1]
            # 英文昵称后紧跟字母/数字时更可能是普通文本（如 @Loky2），
            # 中文昵称则允许直接接正文，因为微信通常不保留分隔空格。
            if not (nickname[-1].isascii() and after and after.isalnum()):
                return True
            start = index + len(needle)
    return False


def _timestamp(data: dict[str, Any]) -> float:
    for key in _TIME_KEYS:
        value = data.get(key)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            # TraceMemo 的部分版本同时提供可读的 datetime 字段，而不是
            # Unix 秒。解析失败时继续尝试 ISO/常见本地时间格式。
            if isinstance(value, str):
                raw = value.strip()
                try:
                    parsed_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    parsed_dt = None
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                        try:
                            parsed_dt = datetime.strptime(raw, fmt)
                            break
                        except ValueError:
                            pass
                if parsed_dt is not None:
                    return parsed_dt.timestamp()
            continue
        # 微信类数据常用毫秒级时间戳。
        return parsed / 1000 if parsed > 10_000_000_000 else parsed
    return 0.0


def _is_text_message(data: dict[str, Any]) -> bool:
    """微信文本消息通常为 type=1；未知格式保持兼容而不盲目拒绝。"""

    value = data.get("type")
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in {
        "text",
        "message",
        "普通文本",
        "文本消息",
        "文字消息",
    }:
        return True
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return False


def _message_type(data: dict[str, Any]) -> str:
    """把 TraceMemo 的中文 type 和数字 type 归一化成少量安全类别。"""

    raw = data.get("type")
    if raw is None:
        return "text"
    value = str(raw or "").strip().lower()
    mapping = {
        "1": "text",
        "text": "text",
        "message": "text",
        "普通文本": "text",
        "文本消息": "text",
        "文字消息": "text",
        "3": "image",
        "图片": "image",
        "image": "image",
        "照片": "image",
        "表情包": "sticker",
        "sticker": "sticker",
        "emoji": "sticker",
    }
    return mapping.get(value, "unknown")


def _media_value(record: dict[str, Any], keys: Iterable[str]) -> str:
    content_data = record.get("contentData")
    candidates: list[dict[str, Any]] = []
    if isinstance(content_data, dict):
        candidates.append(content_data)
    candidates.append(record)
    for source in candidates:
        for key in keys:
            value = source.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _media_url(record: dict[str, Any]) -> str:
    value = _media_value(record, _MEDIA_URL_KEYS)
    return value if value.startswith(("http://", "https://", "file://", "/")) else ""


def _record_lists(payload: Any) -> list[list[dict[str, Any]]]:
    """寻找响应中的对象列表，兼容常见 data/items/list 包装。"""

    found: list[list[dict[str, Any]]] = []
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        found.append(payload)
    elif isinstance(payload, dict):
        for value in payload.values():
            found.extend(_record_lists(value))
    return found


def _best_records(payload: Any, required: Iterable[str]) -> list[dict[str, Any]]:
    required_keys = tuple(required)
    candidates = _record_lists(payload)
    if not candidates:
        return []
    return max(
        candidates,
        key=lambda records: sum(
            any(key in record for key in required_keys) for record in records
        ),
    )


def parse_conversations(payload: Any) -> list[Conversation]:
    conversations: list[Conversation] = []
    for record in _best_records(payload, _TALKER_KEYS):
        talker = _first_string(record, _TALKER_KEYS)
        if not talker:
            continue
        aliases: list[str] = []
        for key in _ALIAS_KEYS:
            value = str(record.get(key, "") or "").strip()
            if value and value not in aliases:
                aliases.append(value)
        name = clean_chat_display_name(aliases[0]) if aliases else talker
        is_group = _first_bool(record, _GROUP_KEYS)
        conversations.append(
            Conversation(
                talker=talker,
                name=name,
                is_group=bool(is_group) or talker.endswith("@chatroom"),
                aliases=tuple(aliases),
            )
        )
    return conversations


def parse_messages(
    payload: Any,
    conversation: Conversation,
    self_nicknames: Iterable[str] = (),
) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for record in _best_records(payload, _TEXT_KEYS):
        text = _first_string(record, _TEXT_KEYS)
        outgoing = _first_bool(record, _OUTGOING_KEYS)
        kind = _message_type(record)
        media_url = _media_url(record)
        media_id = _media_value(record, _MEDIA_ID_KEYS)
        # 缺少方向时一律跳过，不能根据文案猜是不是自己发的。图片/表情包
        # 没有文字正文，但必须有 TraceMemo 提供的媒体地址或 ID 才值得进入引擎；
        # 这样不会把旧版 type=3 的普通说明文字误当成真实图片。
        if outgoing is None:
            continue
        if kind == "text" and not text:
            continue
        if kind in {"image", "sticker"} and not (media_url or media_id):
            continue
        if kind not in {"text", "image", "sticker"}:
            continue
        timestamp = _timestamp(record)
        raw_id = _first_string(record, _ID_KEYS)
        fingerprint = "|".join(
            [conversation.talker, raw_id, str(timestamp), text, _first_string(record, _SENDER_KEYS)]
        )
        message_id = raw_id or hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        messages.append(
            ChatMessage(
                message_id=message_id,
                talker=conversation.talker,
                chat_name=conversation.name,
                text=text or ("【图片】" if kind == "image" else "【表情包】"),
                timestamp=timestamp,
                sender_name=_first_string(record, _SENDER_KEYS) or conversation.name,
                is_group=conversation.is_group,
                outgoing=outgoing,
                mentioned_me=(
                    conversation.is_group
                    and _contains_self_mention(text, self_nicknames)
                ),
                message_type=kind,
                media_url=media_url,
                media_id=media_id,
            )
        )
    return sorted(messages, key=lambda message: (message.timestamp, message.message_id))


class TraceMemoClient:
    def __init__(self, token: str, base_url: str = TRACE_MEMO_BASE_URL) -> None:
        if not token:
            raise TraceMemoError("未找到 TraceMemo API Token")
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

    def health(self) -> dict[str, Any]:
        payload = self._get("/health")
        return payload if isinstance(payload, dict) else {}

    def _get(self, path: str, **params: Any) -> Any:
        request_timeout = float(params.pop("_timeout", 15))
        last_error: requests.RequestException | None = None
        for attempt in range(2):
            try:
                response = self._session.get(
                    f"{self._base_url}{path}",
                    params=params,
                    timeout=request_timeout,
                )
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt == 0 and isinstance(exc, requests.ReadTimeout):
                    time.sleep(0.5)
                    continue
                raise TraceMemoError(f"TraceMemo 请求失败（{path}）：{exc}") from exc
        else:  # pragma: no cover - 循环总会在成功或异常时结束
            raise TraceMemoError(f"TraceMemo 请求失败（{path}）：{last_error}") from last_error
        if response.status_code == 401:
            raise TraceMemoError("TraceMemo Token 无效或已轮换")
        if response.status_code == 503:
            raise TraceMemoError("TraceMemo 数据库尚未就绪")
        try:
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TraceMemoError(f"TraceMemo 响应无效：{exc}") from exc

    def recent_conversations(self, limit: int = 100) -> list[Conversation]:
        return parse_conversations(self._get("/recent_chat", limit=limit))

    def chatlog(
        self,
        conversation: Conversation,
        start_time: int,
        end_time: int,
        self_nicknames: Iterable[str] = (),
    ) -> list[ChatMessage]:
        payload = self._get(
            "/chatlog",
            talker=conversation.talker,
            startTime=start_time,
            endTime=end_time,
            _timeout=30,
        )
        return parse_messages(payload, conversation, self_nicknames)

    def raw_chatlog(self, conversation: Conversation, start_time: int, end_time: int) -> list[dict[str, Any]]:
        """返回诊断所需的原始记录；调用方只能输出元数据，不能打印正文。"""

        payload = self._get(
            "/chatlog",
            talker=conversation.talker,
            startTime=start_time,
            endTime=end_time,
            _timeout=30,
        )
        return _best_records(payload, _TEXT_KEYS)

    def schema(self, allowed_names: set[str]) -> dict[str, list[str]]:
        payload = self._get("/recent_chat", limit=5)
        records = _best_records(payload, _TALKER_KEYS)
        result = {"recent_chat": sorted({key for record in records for key in record})}
        target = next(
            (
                conversation
                for conversation in parse_conversations(payload)
                if any(
                    normalize_chat_name(alias) in allowed_names
                    for alias in (conversation.name, *conversation.aliases)
                )
            ),
            None,
        )
        if target:
            chatlog_payload = self._get(
                "/chatlog",
                talker=target.talker,
                startTime=int(time.time()) - 86_400,
                endTime=int(time.time()),
            )
            messages = _best_records(chatlog_payload, _TEXT_KEYS)
            result["chatlog"] = sorted({key for message in messages for key in message})
        return result


class PollState:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.last_polled_at = 0.0
        self.ready_talkers: set[str] = set()
        self.seen_ids: dict[str, list[str]] = {}
        self.retry_state: dict[str, dict[str, dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.last_polled_at = float(data.get("last_polled_at", 0))
        self.ready_talkers = set(data.get("ready_talkers", []))
        self.seen_ids = {key: list(value)[-200:] for key, value in data.get("seen_ids", {}).items()}
        raw_retry = data.get("retry_state", {})
        self.retry_state = {
            talker: {message_id: dict(meta) for message_id, meta in entries.items()}
            for talker, entries in raw_retry.items()
            if isinstance(entries, dict)
        }

    def has_seen(self, talker: str, message_id: str) -> bool:
        return message_id in self.seen_ids.get(talker, [])

    def mark_seen(self, talker: str, message_id: str) -> None:
        seen = self.seen_ids.setdefault(talker, [])
        if message_id not in seen:
            seen.append(message_id)
            del seen[:-200]

    def retry_ready(self, talker: str, message_id: str, now: float) -> bool:
        meta = self.retry_state.get(talker, {}).get(message_id)
        return bool(meta and float(meta.get("next_at", 0)) <= now)

    def retry_attempts(self, talker: str, message_id: str) -> int:
        return int(self.retry_state.get(talker, {}).get(message_id, {}).get("attempts", 0))

    def retry_text(self, talker: str, message_id: str) -> str:
        value = self.retry_state.get(talker, {}).get(message_id, {}).get("reply_text", "")
        return str(value).strip()

    def schedule_retry(
        self,
        talker: str,
        message_id: str,
        now: float,
        reply_text: str,
        delay: float = SEND_RETRY_DELAY_SECONDS,
    ) -> int:
        entries = self.retry_state.setdefault(talker, {})
        attempts = int(entries.get(message_id, {}).get("attempts", 0)) + 1
        entries[message_id] = {
            "attempts": attempts,
            "next_at": now + delay,
            "reply_text": reply_text,
        }
        return attempts

    def clear_retry(self, talker: str, message_id: str) -> None:
        entries = self.retry_state.get(talker)
        if not entries:
            return
        entries.pop(message_id, None)
        if not entries:
            self.retry_state.pop(talker, None)

    def save(self, now: float | None = None) -> None:
        """持久化状态；传入 now 时推进轮询游标，否则只保存已认领消息。"""
        if now is not None:
            self.last_polled_at = now
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_polled_at": self.last_polled_at,
            "ready_talkers": sorted(self.ready_talkers),
            "seen_ids": self.seen_ids,
            "retry_state": self.retry_state,
        }
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self._path)


class PollerLock:
    """防止 launchd 与手动测试命令同时轮询同一个状态文件。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle = None

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._handle.close()
            self._handle = None
            raise TraceMemoError("已有另一个轮询器在运行") from exc

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


class EngineClient:
    def __init__(self, server_url: str, token: str) -> None:
        self._url = server_url.rstrip("/") + "/reply"
        self._headers = {"Authorization": f"Bearer {token}"}

    def draft(self, message: ChatMessage, style_context: str = "") -> Optional[dict[str, Any]]:
        try:
            response = requests.post(
                self._url,
                json={
                    "chat_id": f"tracememo:{message.talker}",
                    "chat_name": message.chat_name,
                    "text": message.text,
                    "message_type": message.message_type,
                    "ocr_text": message.ocr_text,
                    "batch_size": message.batch_size,
                    "sender_name": message.sender_name,
                    "is_group": message.is_group,
                    "mentioned_me": message.mentioned_me,
                    "style_context": style_context,
                    "platform": "tracememo",
                    "account": "personal-wechat",
                },
                headers=self._headers,
                timeout=45,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.error("回复引擎不可用，本条不写草稿：%s", exc)
            return None


class MediaRecognizer:
    """对新收到的图片/表情包做一次本地 OCR，失败时保留明确占位信息。"""

    def __init__(
        self,
        *,
        repo_dir: str | Path | None = None,
        timeout: float = 10.0,
        max_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        root = Path(repo_dir) if repo_dir else REPO_DIR
        self._ocr_binary = root / ".build" / "vision-ocr"
        self._timeout = timeout
        self._max_bytes = max_bytes

    def _download(self, url: str, path: Path) -> bool:
        if url.startswith("file://") or url.startswith("/"):
            source = Path(url.removeprefix("file://"))
            try:
                if not source.is_file() or source.stat().st_size > self._max_bytes:
                    return False
                path.write_bytes(source.read_bytes())
                return path.stat().st_size > 0
            except OSError:
                return False
        if not url.startswith(("http://", "https://")):
            return False
        try:
            response = requests.get(url, timeout=self._timeout, stream=True)
            response.raise_for_status()
            total = 0
            with path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > self._max_bytes:
                        return False
                    handle.write(chunk)
            return total > 0
        except (OSError, requests.RequestException):
            logger.debug("媒体下载失败", exc_info=True)
            return False

    def _ocr(self, path: Path) -> str:
        if not self._ocr_binary.is_file() or not os.access(self._ocr_binary, os.X_OK):
            return ""
        try:
            result = subprocess.run(
                [str(self._ocr_binary), str(path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                return ""
            payload = json.loads(result.stdout)
            values = [
                str(item.get("text", "")).strip()
                for item in payload.get("observations", [])
                if str(item.get("text", "")).strip()
            ]
            return " ".join(values)[:500]
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, json.JSONDecodeError):
            logger.debug("媒体 OCR 失败", exc_info=True)
            return ""

    def enrich(self, message: ChatMessage) -> ChatMessage:
        if message.message_type not in {"image", "sticker"}:
            return message
        label = "图片" if message.message_type == "image" else "表情包"
        ocr_text = ""
        if message.media_url:
            with tempfile.TemporaryDirectory(prefix="wxauto-media-") as temp_dir:
                image_path = Path(temp_dir) / "media.bin"
                if self._download(message.media_url, image_path):
                    ocr_text = self._ocr(image_path)
        if ocr_text:
            text = f"【{label}】图片文字：{ocr_text}"
        else:
            text = f"【{label}】（暂未识别到图片中的文字）"
        return dataclasses.replace(message, text=text, ocr_text=ocr_text, media_url="")


class DraftWriter:
    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, message: ChatMessage, decision: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": int(time.time()),
            "chat_name": message.chat_name,
            "talker": message.talker,
            "message_id": message.message_id,
            "message_ids": list(message.message_ids),
            "message_count": message.batch_size,
            "message_timestamp": message.timestamp,
            "sender_name": message.sender_name,
            "draft": decision.get("text"),
            "reason": decision.get("reason"),
        }
        descriptor = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class WeChatSenderProtocol:
    """避免在非 macOS 单元测试导入 GUI 依赖。"""

    def send(self, target_name: str, text: str) -> None:  # pragma: no cover - 接口声明
        raise NotImplementedError


def _combine_messages(messages: list[ChatMessage]) -> ChatMessage:
    """把同一轮连续消息提交给引擎，让模型决定合并表达还是逐项回应。"""

    if len(messages) == 1:
        return messages[0]
    first = messages[0]
    labels = {
        "text": "文字",
        "image": "图片",
        "sticker": "表情包",
    }
    parts = [
        f"第{index}条（{labels.get(message.message_type, '消息')}）：{message.text}"
        for index, message in enumerate(messages, start=1)
    ]
    return dataclasses.replace(
        first,
        # 用第一条的 ID 作为重试键；下一轮 TraceMemo 仍会返回这条已读消息，
        # PollState 才能在发送失败后安全重放同一份合并回复。
        message_id=first.message_id,
        text=(
            f"对方连续发来 {len(messages)} 条消息：\n"
            + "\n".join(parts)
            + "\n请先判断它们是否属于同一件事：相关就合并成一条自然回复；"
            "不相关时用简短分点分别回应，但仍只发一条微信消息。"
        ),
        message_type="batch",
        ocr_text="\n".join(message.ocr_text for message in messages if message.ocr_text),
        message_ids=tuple(message.message_id for message in messages),
        batch_size=len(messages),
    )


@dataclass
class TickStats:
    conversations_scanned: int = 0
    new_messages: int = 0
    drafts_generated: int = 0
    retries_attempted: int = 0
    skipped: int = 0
    sent: int = 0
    send_failures: int = 0
    errors: int = 0


class Poller:
    def __init__(
        self,
        trace_memo: TraceMemoClient,
        engine: EngineClient,
        allowed_names: set[str],
        state: PollState,
        drafts: DraftWriter,
        allowed_talkers: set[str] | None = None,
        sender: WeChatSenderProtocol | None = None,
        send_name: str = "Biscoffee",
        send_all: bool = False,
        self_nicknames: Iterable[str] = (),
        style_profiles: StyleProfileStore | None = None,
        style_signature: str = "",
        media_recognizer: MediaRecognizer | None = None,
        merge_window_seconds: float = 8.0,
        replay_offline: bool = False,
    ) -> None:
        self._trace_memo = trace_memo
        self._engine = engine
        self._allowed_names = allowed_names
        self._allowed_talkers = {str(talker).strip() for talker in (allowed_talkers or set()) if str(talker).strip()}
        self._state = state
        self._drafts = drafts
        self._sender = sender
        self._send_name = normalize_chat_name(send_name)
        self._send_all = send_all
        self._self_nicknames = tuple(str(name).strip() for name in self_nicknames if str(name).strip())
        self._style_profiles = style_profiles
        self._style_signature = style_signature
        self._style_profile_attempted_at: dict[str, float] = {}
        self._media_recognizer = media_recognizer or MediaRecognizer()
        self._merge_window_seconds = max(1.0, merge_window_seconds)
        self._skip_startup_history = not replay_offline

    def _new_messages_for_conversation(
        self,
        messages: list[ChatMessage],
        previous_poll: float,
        stats: TickStats,
    ) -> list[ChatMessage]:
        """筛选新消息，消息 ID 在对应批次认领后才写入状态。"""

        fresh: list[ChatMessage] = []
        for message in messages:
            if message.outgoing:
                continue
            if message.timestamp <= previous_poll or self._state.has_seen(message.talker, message.message_id):
                continue
            stats.new_messages += 1
            fresh.append(self._media_recognizer.enrich(message))
        return fresh

    def _claim_batch(self, messages: list[ChatMessage]) -> None:
        """先记录本批消息，避免发送过程中重启再次生成同一批回复。"""
        for message in messages:
            self._state.mark_seen(message.talker, message.message_id)
        self._state.save()

    def _message_batches(self, messages: list[ChatMessage]) -> list[list[ChatMessage]]:
        """同一人短时间连发的内容为一轮；群聊不同发言人绝不混合。"""

        batches: list[list[ChatMessage]] = []
        for message in messages:
            if not batches:
                batches.append([message])
                continue
            current = batches[-1]
            previous = current[-1]
            close_enough = message.timestamp - previous.timestamp <= self._merge_window_seconds
            same_sender = (
                not message.is_group
                or normalize_chat_name(message.sender_name) == normalize_chat_name(previous.sender_name)
            )
            if close_enough and same_sender and len(current) < 4:
                current.append(message)
            else:
                batches.append([message])
        return batches

    def _send_target_allowed(self, message: ChatMessage) -> bool:
        return self._sender is not None and (
            self._send_all or normalize_chat_name(message.chat_name) == self._send_name
        )

    def _process_decision(
        self,
        message: ChatMessage,
        decision: dict[str, Any] | None,
        stats: TickStats,
    ) -> None:
        if decision and decision.get("should_reply"):
            self._drafts.append(message, decision)
            stats.drafts_generated += 1
            logger.info("草稿已生成：%s（%d 条消息）", message.chat_name, message.batch_size)
            if self._send_target_allowed(message):
                reply_text = str(decision.get("text") or "").strip()
                if reply_text:
                    delay = max(0.0, float(decision.get("delay_seconds") or 0.0))
                    if delay:
                        logger.info("已生成 %s 回复，等待 %.1f 秒后发送", message.chat_name, delay)
                        time.sleep(delay)
                    self._send_reply(message, reply_text, stats)
        elif decision:
            stats.skipped += 1
            logger.info("跳过 %s：%s", message.chat_name, decision.get("reason"))

    def _conversation_allowed(self, conversation: Conversation) -> bool:
        if conversation.talker in self._allowed_talkers:
            return True
        candidates = (conversation.name, *conversation.aliases)
        return any(normalize_chat_name(candidate) in self._allowed_names for candidate in candidates)

    def _style_for_message(
        self,
        conversation: Conversation,
        current_messages: list[ChatMessage],
        now: float,
    ) -> StyleProfile | None:
        if self._style_profiles is None:
            return None
        existing = self._style_profiles.get(conversation.talker)
        if (
            existing is not None
            and existing.sample_count
            and now - existing.updated_at < STYLE_PROFILE_REFRESH_SECONDS
        ):
            return existing
        last_attempt = self._style_profile_attempted_at.get(conversation.talker, 0)
        if now - last_attempt < 3600:
            return existing
        self._style_profile_attempted_at[conversation.talker] = now

        source = current_messages
        try:
            if self._self_nicknames:
                history = self._trace_memo.chatlog(
                    conversation,
                    max(0, int(now) - STYLE_HISTORY_DAYS * 86_400),
                    int(now),
                    self._self_nicknames,
                )
            else:
                history = self._trace_memo.chatlog(
                    conversation,
                    max(0, int(now) - STYLE_HISTORY_DAYS * 86_400),
                    int(now),
                )
            if history:
                source = history
        except TraceMemoError as exc:
            logger.info("会话 %s 历史风格读取失败，使用当前窗口：%s", conversation.name, exc)

        profile = build_style_profile(source, signature=self._style_signature)
        if profile.sample_count:
            self._style_profiles.put(conversation.talker, profile)
            logger.info("已更新会话风格画像：%s（%d 条本人样本）", conversation.name, profile.sample_count)
        return profile

    def _send_reply(
        self,
        message: ChatMessage,
        reply_text: str,
        stats: TickStats,
        *,
        retry_attempt: int = 0,
    ) -> None:
        """发送一条已确认目标会话的回复，并安排安全重试。"""

        if self._sender is None:
            return
        try:
            self._sender.send(message.chat_name, reply_text, is_group=message.is_group)
        except Exception as exc:  # GUI 失败不能拖垮轮询器
            stats.send_failures += 1
            send_attempted = bool(getattr(exc, "send_attempted", False))
            if send_attempted:
                self._state.clear_retry(message.talker, message.message_id)
                logger.error(
                    "%s 发送失败：已尝试最终发送动作，不自动重发：%s",
                    message.chat_name,
                    exc,
                )
                return
            if retry_attempt >= MAX_SEND_RETRIES:
                self._state.clear_retry(message.talker, message.message_id)
                logger.error(
                    "%s 第 %d/%d 次重试仍失败，已放弃：%s",
                    message.chat_name,
                    retry_attempt,
                    MAX_SEND_RETRIES,
                    exc,
                )
                return
            next_attempt = self._state.schedule_retry(
                message.talker,
                message.message_id,
                time.time(),
                reply_text,
            )
            logger.warning(
                "%s 发送失败，将在 %.0f 秒后进行第 %d/%d 次重试：%s",
                message.chat_name,
                SEND_RETRY_DELAY_SECONDS,
                next_attempt,
                MAX_SEND_RETRIES,
                exc,
            )
            return

        self._state.clear_retry(message.talker, message.message_id)
        stats.sent += 1
        logger.info("%s 自动回复已发送", message.chat_name)

    def tick(self) -> TickStats:
        now = time.time()
        # 默认启动时把当前历史视为基线，避免补回停机期间已经被人工读过的消息。
        # --replay-offline 会保留旧游标，显式开启离线追补。
        previous_poll = now if self._skip_startup_history else self._state.last_polled_at
        # TraceMemo 对极窄秒级范围的 chatlog 查询可能超时；读取当天窗口后
        # 在本地按游标过滤，既兼容该实现，也不会处理任何历史消息。
        start_time = int(now - 86_400)
        stats = TickStats()
        for conversation in self._trace_memo.recent_conversations():
            if not self._conversation_allowed(conversation):
                continue
            stats.conversations_scanned += 1
            # 默认模式首次看到一个会话只建立游标，不处理历史消息；
            # 显式追补模式则继续处理旧游标之后的消息。
            if conversation.talker not in self._state.ready_talkers:
                self._state.ready_talkers.add(conversation.talker)
                if self._skip_startup_history:
                    logger.info("已建立会话游标，跳过启动前历史：%s", conversation.name)
                    continue
                logger.info("已建立会话游标，按追补策略处理历史：%s", conversation.name)
            try:
                if self._self_nicknames:
                    messages = self._trace_memo.chatlog(
                        conversation,
                        start_time,
                        int(now),
                        self._self_nicknames,
                    )
                else:
                    messages = self._trace_memo.chatlog(
                        conversation,
                        start_time,
                        int(now),
                    )
            except TraceMemoError as exc:
                logger.warning("跳过会话 %s：%s", conversation.name, exc)
                stats.errors += 1
                continue
            # 未完成的安全重试优先执行，但不会影响新消息的分批。
            for message in messages:
                retry_attempt = self._state.retry_attempts(message.talker, message.message_id)
                if not retry_attempt or not self._state.retry_ready(message.talker, message.message_id, now):
                    continue
                reply_text = self._state.retry_text(message.talker, message.message_id)
                if not reply_text:
                    logger.error("%s 重试记录缺少回复内容，已清理", message.chat_name)
                    self._state.clear_retry(message.talker, message.message_id)
                    continue
                stats.retries_attempted += 1
                logger.info("%s 开始第 %d/%d 次发送重试", message.chat_name, retry_attempt, MAX_SEND_RETRIES)
                self._send_reply(message, reply_text, stats, retry_attempt=retry_attempt)

            fresh = self._new_messages_for_conversation(messages, previous_poll, stats)
            for batch in self._message_batches(fresh):
                self._claim_batch(batch)
                message = _combine_messages(batch)
                logger.info("检测到新消息：会话 %s（连续 %d 条）", message.chat_name, message.batch_size)
                profile = self._style_for_message(conversation, messages, now)
                decision = (
                    self._engine.draft(message, profile.prompt_context())
                    if profile and profile.sample_count
                    else self._engine.draft(message)
                )
                self._process_decision(message, decision, stats)
                # 批次完成后再次落盘重试记录、草稿对应的认领状态和其他游标信息。
                self._state.save()
        self._state.save(now)
        self._skip_startup_history = False
        if stats.new_messages:
            logger.info(
                "本轮状态：检测到 %d 条新消息，生成 %d 条草稿，发送成功 %d 条，跳过 %d 条，发送失败 %d 条",
                stats.new_messages,
                stats.drafts_generated,
                stats.sent,
                stats.skipped,
                stats.send_failures,
            )
        return stats


def _read_engine_token() -> str:
    path = Path(os.environ.get("WXAUTO_TOKEN_FILE", ".wxauto_token"))
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return os.environ.get("WXAUTO_TOKEN", "").strip()


def _diagnose(trace_memo: TraceMemoClient, name: str, state: PollState) -> int:
    """诊断一个会话的 TraceMemo 字段和本地过滤结果，不输出消息正文。"""

    wanted = normalize_chat_name(name)
    conversations = [
        item for item in trace_memo.recent_conversations()
        if any(
            normalize_chat_name(alias) == wanted
            for alias in (item.name, *item.aliases)
        )
    ]
    print(f"会话是否找到：{'是' if conversations else '否'}")
    if not conversations:
        return 1

    now = int(time.time())
    previous = state.last_polled_at
    for conversation in conversations:
        records = trace_memo.raw_chatlog(conversation, now - 86_400, now)
        type_counts: dict[str, int] = {}
        direction_counts = {"inbound": 0, "outbound": 0, "unknown": 0}
        timestamp_counts = {"valid": 0, "invalid": 0, "cursor_filtered": 0}
        text_count = 0
        media_counts = {"image": 0, "sticker": 0}
        eligible = 0
        ids_present = 0
        for record in records:
            type_value = str(record.get("type", "<missing>"))
            type_counts[type_value] = type_counts.get(type_value, 0) + 1
            if _first_string(record, _ID_KEYS):
                ids_present += 1
            if _is_text_message(record):
                text_count += 1
            kind = _message_type(record)
            if kind in media_counts:
                media_counts[kind] += 1
            outgoing = _first_bool(record, _OUTGOING_KEYS)
            if outgoing is True:
                direction_counts["outbound"] += 1
            elif outgoing is False:
                direction_counts["inbound"] += 1
            else:
                direction_counts["unknown"] += 1
            timestamp = _timestamp(record)
            if timestamp <= 0:
                timestamp_counts["invalid"] += 1
            else:
                timestamp_counts["valid"] += 1
                if timestamp <= previous:
                    timestamp_counts["cursor_filtered"] += 1
                elif outgoing is False and kind in {"text", "image", "sticker"}:
                    eligible += 1
        print(f"会话标识：{conversation.talker}")
        print(f"记录数量：{len(records)}；文本记录：{text_count}")
        print(f"媒体记录：{json.dumps(media_counts, ensure_ascii=False)}")
        print(f"type 统计：{json.dumps(type_counts, ensure_ascii=False, sort_keys=True)}")
        print(f"方向统计：{json.dumps(direction_counts, ensure_ascii=False)}")
        print(f"时间字段：有效 {timestamp_counts['valid']}，无效 {timestamp_counts['invalid']}，被本地游标过滤 {timestamp_counts['cursor_filtered']}")
        print(f"消息 ID：{ids_present} 条包含 serverId/localId 等 ID")
        print(f"当前游标：{previous:.0f}；按规则可进入引擎：{eligible}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TraceMemo 微信草稿轮询器")
    parser.add_argument("--interval", type=float, default=40, help="轮询间隔，默认 40 秒")
    parser.add_argument(
        "--merge-window",
        type=float,
        default=8.0,
        help="同一会话连续消息的合并判断窗口（秒），默认 8 秒",
    )
    parser.add_argument(
        "--replay-offline",
        action="store_true",
        help="启动时追补上次停止后积累的历史消息（默认跳过）",
    )
    parser.add_argument("--status-interval", type=float, default=30, help="无新消息时的状态输出间隔，默认 30 秒")
    parser.add_argument("--once", action="store_true", help="只轮询一轮")
    parser.add_argument("--dump-schema", action="store_true", help="只输出 API 字段名，不输出聊天内容")
    parser.add_argument("--diagnose-name", help="只诊断指定会话的 TraceMemo 字段，不调用 AI、不发送")
    parser.add_argument("--send", action="store_true", help="启用本地微信界面发送；默认关闭")
    parser.add_argument("--send-name", default="Biscoffee", help="允许真实发送的会话名，默认 Biscoffee")
    parser.add_argument(
        "--send-all",
        action="store_true",
        help="真实发送到配置白名单中的所有会话（群聊仍必须 @ 当前昵称）",
    )
    parser.add_argument("--config", default="core/config.yaml")
    parser.add_argument("--state-path", default="var/tracememo-poller-state.json")
    parser.add_argument("--draft-path", default="var/tracememo-drafts.jsonl")
    parser.add_argument("--style-profile-path", default="var/style-profiles.json")
    parser.add_argument("--trace-memo-url", default=TRACE_MEMO_BASE_URL)
    parser.add_argument("--engine-url", default="http://127.0.0.1:8848")
    args = parser.parse_args()

    if args.interval < 5:
        parser.error("轮询间隔不得低于 5 秒")
    if args.status_interval < 5:
        parser.error("状态输出间隔不得低于 5 秒")
    if args.merge_window < 1:
        parser.error("连续消息合并窗口不得低于 1 秒")

    process_lock = PollerLock(Path(args.state_path).with_name("tracememo-poller.lock"))
    if not args.dump_schema and not args.diagnose_name:
        try:
            process_lock.acquire()
        except TraceMemoError as exc:
            logger.info("%s，当前命令退出，不会重复处理消息", exc)
            return 0

    # 新变量优先；兼容旧版 Reader 使用的环境变量名。
    trace_memo_token = read_secret("TRACEMEMO_API_TOKEN", TRACE_MEMO_KEYCHAIN_SERVICE)
    if not trace_memo_token:
        trace_memo_token = os.environ.get("WECHATEXPLORER_API_TOKEN", "").strip()
    try:
        trace_memo = TraceMemoClient(trace_memo_token, args.trace_memo_url)
        trace_memo.health()
        config = load_config(args.config)
        allowed_names = {normalize_chat_name(name) for name in config.scope.allow_contacts}
        allowed_talkers = set(config.scope.allow_talkers)
        if args.dump_schema:
            print(json.dumps(trace_memo.schema(allowed_names), ensure_ascii=False, indent=2))
            return 0
        if args.diagnose_name:
            return _diagnose(trace_memo, args.diagnose_name, PollState(Path(args.state_path)))
        engine_token = _read_engine_token()
        if not engine_token:
            logger.error("找不到 .wxauto_token 或 WXAUTO_TOKEN")
            return 1
        config = load_config(args.config)
        allowed_names = {normalize_chat_name(name) for name in config.scope.allow_contacts}
        allowed_talkers = set(config.scope.allow_talkers)
        if not allowed_names and not allowed_talkers:
            logger.error("白名单为空，拒绝启动")
            return 1
        sender = None
        if args.send:
            if not args.send_all and normalize_chat_name(args.send_name) != normalize_chat_name("Biscoffee"):
                logger.error("真实发送目标不是 Biscoffee；如需发送全部白名单，请使用 --send-all")
                return 1
            from macos.wechat_sender import WeChatSender

            sender = WeChatSender(repo_dir=REPO_DIR)
        poller = Poller(
            trace_memo,
            EngineClient(args.engine_url, engine_token),
            allowed_names,
            PollState(Path(args.state_path)),
            DraftWriter(Path(args.draft_path)),
            allowed_talkers=allowed_talkers,
            sender=sender,
            send_name=args.send_name,
            send_all=args.send_all,
            self_nicknames=config.scope.self_nicknames,
            style_profiles=StyleProfileStore(Path(args.style_profile_path)),
            style_signature=config.signature,
            merge_window_seconds=args.merge_window,
            replay_offline=args.replay_offline,
        )
    except (OSError, TraceMemoError) as exc:
        logger.error("无法启动轮询器：%s", exc)
        process_lock.release()
        return 1

    logger.info(
        "TraceMemo %s轮询器启动，每 %.0f 秒扫描一次%s",
        "自动回复" if args.send else "草稿",
        args.interval,
        (
            "（发送全部白名单）"
            if args.send and args.send_all
            else f"（仅发送 {args.send_name}）" if args.send else ""
        ),
    )
    logger.info(
        "启动历史策略：%s",
        "追补停机期间消息" if args.replay_offline else "跳过停机期间消息，仅建立当前游标",
    )
    last_status_at = 0.0
    try:
        while True:
            try:
                stats = poller.tick()
                status_now = time.time()
                if not stats.new_messages and status_now - last_status_at >= args.status_interval:
                    logger.info(
                        "状态：运行中，已扫描 %d 个白名单会话，本轮未检测到新消息%s",
                        stats.conversations_scanned,
                        f"，TraceMemo 错误 {stats.errors} 个" if stats.errors else "",
                    )
                    last_status_at = status_now
            except TraceMemoError as exc:
                logger.error("本轮跳过：%s", exc)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("收到中断，退出")
    finally:
        process_lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
