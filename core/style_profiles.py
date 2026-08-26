"""按会话提取本地说话样式，避免每次把完整历史记录发给模型。

这里只做轻量的本地统计和少量示例筛选。TraceMemo 的原始聊天内容不会写入日志；
画像文件只保存在 ``var/``，默认被 git 忽略并以 0600 权限保存。
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_AUTO_SIGNATURE = re.compile(
    r"\s*（(?:由\s*AI\s*)?(?:自动发送[、,]?自动回复|自动生成|自动回复)）\s*$",
    re.IGNORECASE,
)
_COMMON_MARKERS = (
    "哈哈",
    "笑死",
    "确实",
    "我去",
    "我操",
    "卧槽",
    "可以",
    "行",
    "好吧",
    "额",
    "嗯",
    "啊",
    "吧",
    "呢",
    "呗",
    "xdm",
)


def _clean_text(value: str, signature: str = "") -> str:
    text = str(value or "").strip()
    if signature and text.endswith(signature):
        text = text[: -len(signature)].rstrip()
    return _AUTO_SIGNATURE.sub("", text).strip()


def _clip(value: str, limit: int = 96) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _is_emoji(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x1F000 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
    )


@dataclass(frozen=True)
class StyleExample:
    incoming: str = ""
    reply: str = ""


@dataclass(frozen=True)
class StyleProfile:
    summary: str
    examples: tuple[StyleExample, ...]
    sample_count: int
    updated_at: float

    def prompt_context(self) -> str:
        """生成短小、带边界说明的提示片段。"""

        lines = [f"统计：{self.summary}"]
        if self.examples:
            lines.append("历史示例（只模仿表达方式）：")
            for example in self.examples:
                if example.incoming:
                    lines.append(f"对方：{_clip(example.incoming)}")
                lines.append(f"我：{_clip(example.reply)}")
        return "\n".join(lines)


def build_style_profile(
    messages: Iterable[object],
    *,
    max_examples: int = 6,
    signature: str = "",
) -> StyleProfile:
    """从一段 TraceMemo 消息中提取当前账号的发言风格。"""

    ordered = sorted(
        messages,
        key=lambda item: float(getattr(item, "timestamp", 0) or 0),
    )
    outgoing: list[tuple[object, str]] = []
    pairs: list[StyleExample] = []
    last_incoming: tuple[object, str] | None = None

    for message in ordered:
        text = _clean_text(getattr(message, "text", ""), signature)
        if not text:
            continue
        if bool(getattr(message, "outgoing", False)):
            outgoing.append((message, text))
            if last_incoming is not None:
                incoming_message, incoming_text = last_incoming
                delta = float(getattr(message, "timestamp", 0) or 0) - float(
                    getattr(incoming_message, "timestamp", 0) or 0
                )
                if 0 <= delta <= 3600:
                    pairs.append(StyleExample(incoming=incoming_text, reply=text))
        else:
            last_incoming = (message, text)

    lengths = [len(text) for _, text in outgoing]
    if not lengths:
        return StyleProfile(
            summary="暂无足够的本人历史文字样本",
            examples=(),
            sample_count=0,
            updated_at=time.time(),
        )

    endings = Counter(text[-1] for _, text in outgoing if text)
    marker_counts = Counter(
        marker
        for _, text in outgoing
        for marker in _COMMON_MARKERS
        if marker in text
    )
    emoji_count = sum(_is_emoji(char) for _, text in outgoing for char in text)
    punctuation = "、".join(
        f"{char}{count}次" for char, count in endings.most_common(4)
    )
    markers = "、".join(
        marker for marker, _ in marker_counts.most_common(5)
    ) or "无明显固定口头禅"
    avg_length = sum(lengths) / len(lengths)
    short_ratio = sum(length <= 12 for length in lengths) / len(lengths)
    summary = (
        f"样本{len(lengths)}条，平均{avg_length:.1f}字，"
        f"{short_ratio:.0%}的回复不超过12字；"
        f"常见结尾：{punctuation or '无'}；"
        f"常见口头表达：{markers}；"
        f"表情字符约{emoji_count}个"
    )

    # 优先选最近、内容不重复的成对示例；没有入站配对时退化为本人单句样本。
    examples: list[StyleExample] = []
    seen_replies: set[str] = set()
    for example in reversed(pairs):
        key = example.reply.casefold()
        if key in seen_replies:
            continue
        seen_replies.add(key)
        examples.append(
            StyleExample(
                incoming=_clip(example.incoming),
                reply=_clip(example.reply),
            )
        )
        if len(examples) >= max_examples:
            break
    if not examples:
        for _, text in reversed(outgoing):
            key = text.casefold()
            if key in seen_replies:
                continue
            seen_replies.add(key)
            examples.append(StyleExample(reply=_clip(text)))
            if len(examples) >= max_examples:
                break

    return StyleProfile(
        summary=summary,
        examples=tuple(examples),
        sample_count=len(lengths),
        updated_at=time.time(),
    )


class StyleProfileStore:
    """本地持久化的会话画像仓库。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._profiles: dict[str, StyleProfile] = {}
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for talker, raw in (payload.get("profiles") or {}).items():
            if not isinstance(raw, dict):
                continue
            examples = tuple(
                StyleExample(
                    incoming=str(item.get("incoming", "")),
                    reply=str(item.get("reply", "")),
                )
                for item in (raw.get("examples") or [])
                if isinstance(item, dict) and str(item.get("reply", "")).strip()
            )
            self._profiles[str(talker)] = StyleProfile(
                summary=str(raw.get("summary", "")),
                examples=examples,
                sample_count=int(raw.get("sample_count", 0)),
                updated_at=float(raw.get("updated_at", 0)),
            )

    def get(self, talker: str) -> StyleProfile | None:
        return self._profiles.get(talker)

    def put(self, talker: str, profile: StyleProfile) -> None:
        self._profiles[talker] = profile
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "profiles": {
                talker: {
                    "summary": profile.summary,
                    "sample_count": profile.sample_count,
                    "updated_at": profile.updated_at,
                    "examples": [example.__dict__ for example in profile.examples],
                }
                for talker, profile in self._profiles.items()
            },
        }
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self._path)
