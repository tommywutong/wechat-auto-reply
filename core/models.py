"""跨平台共用的数据结构。

iOS / Android / macOS 各端把抓到的消息统一转成 IncomingMessage，
引擎返回 ReplyDecision，端上只负责「按不按发送键」。
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# 群名后面的成员数，如「项目组(8)」「项目组（8）」。
# 人数会变，不能进身份标识，否则有人进群就等于换了个会话。
_MEMBER_COUNT = re.compile(r"[（(]\s*\d+\s*[)）]\s*$")


@dataclass
class IncomingMessage:
    """一条待处理的微信消息。"""

    chat_id: str
    """会话唯一标识。安卓用通知的 conversation key，iOS/macOS 用会话名。"""

    chat_name: str
    """会话显示名（群名或联系人昵称）。"""

    text: str
    """消息正文。"""

    sender_name: str = ""
    """群里的发送者昵称；私聊时等于 chat_name。"""

    is_group: bool = False

    mentioned_me: bool = False
    """群消息里是否 @ 了我。"""

    style_context: str = ""
    """当前会话的本地风格画像；只影响措辞，不改变安全规则。"""

    platform: str = "unknown"
    """android / ios / macos，仅用于日志。"""

    account: str = ""
    """这一端在驱动哪个微信号。

    平台和账号是两件不同的事，必须分开：
      - 同一个号在安卓和 macOS 上同时登录 → 两端填**相同**的 account，
        共享冷却额度并互相去重，避免对方收到两条重复回复。
      - 两个不同的微信号分别跑在两端 → 两端填**不同**的 account
        （或都留空，默认按平台隔离），各自独立计数。

    留空时回退成 platform，这个默认值偏向「隔离」——误判方向是
    多回一条而不是漏回，且只在同号多端时才需要显式配置。
    """

    timestamp: float = field(default_factory=time.time)

    message_type: str = "text"
    """消息类型：text / image / sticker / unknown。"""

    ocr_text: str = ""
    """图片或表情包中本地 OCR 读到的文字（可能为空）。"""

    batch_size: int = 1
    """本次请求由几条连续入站消息组成。"""

    media_data: str = ""
    """可选的 base64 图片数据；只在视觉模型请求中使用，不落盘。"""

    media_mime_type: str = ""
    """图片 MIME 类型，例如 image/jpeg。"""

    def __post_init__(self) -> None:
        self.text = (self.text or "").strip()
        self.message_type = (self.message_type or "text").strip().lower() or "text"
        self.ocr_text = (self.ocr_text or "").strip()
        self.media_data = (self.media_data or "").strip()
        self.media_mime_type = (self.media_mime_type or "").strip().lower()
        self.batch_size = max(1, int(self.batch_size or 1))
        if not self.sender_name:
            self.sender_name = self.chat_name
        if not self.account:
            self.account = self.platform


@dataclass
class ReplyDecision:
    """引擎的判断结果。should_reply 为 False 时 text 无意义。"""

    should_reply: bool
    reason: str
    """为什么回 / 为什么不回，直接写进日志，方便调参。"""

    text: Optional[str] = None
    delay_seconds: float = 0.0
    """建议延迟多久再发，避免秒回被风控盯上。"""

    rule_name: Optional[str] = None

    @classmethod
    def skip(cls, reason: str) -> "ReplyDecision":
        return cls(should_reply=False, reason=reason)


def normalize_chat_name(name: str) -> str:
    """归一化会话名，用于和用户填的名单比对。

    用户手打名字时很容易多个空格、大小写不一致；而这里比对失败的后果
    是「名单里的人收不到回复」或者「名单外的人收到了」——两种都很糟，
    而且都不会报错，用户只会觉得程序坏了。所以比对前统一归一化。

    刻意不做模糊匹配（比如包含关系）：那会把「小王他哥」也算成「小王」。
    """
    value = clean_chat_display_name(name)
    value = _MEMBER_COUNT.sub("", value)
    value = re.sub(r"\s+", "", value).strip()
    value = re.sub(r"[。．.]+$", "", value)
    return value.casefold()


def clean_chat_display_name(name: str) -> str:
    """清理 TraceMemo 昵称中的不可见字符，但保留用户可见标点。"""

    value = unicodedata.normalize("NFKC", name or "")
    return "".join(
        char
        for char in value
        if unicodedata.category(char) not in {"Cc", "Cf", "Cs", "Co"}
        and not 0xFFF0 <= ord(char) <= 0xFFFF
    ).strip()


def chat_identity(message: IncomingMessage) -> str:
    """把一条消息归一化成「会话身份」，作为限流和去重的键。

    键由三段构成：账号 + 会话类型 + 归一化会话名。

    为什么不直接用各端上报的 chat_id：同一个微信号在安卓和 macOS 上
    同时登录时，两端的 chat_id 前缀天然不同
    （android:com.tencent.mm:小王 vs macos:小王），用它做键会分裂成
    两套独立冷却，对方就收到两条一模一样的自动回复。

    为什么必须带上 account：账号才是隔离边界，平台不是。两个不同的
    微信号各跑一端时，两边的「小王」是两个不同的人，绝不能共享额度，
    否则 B 号该回的消息会被 A 号刚回过的同名会话误杀。

    会话名的归一化：
      - 去掉群名后缀的成员数，人数变化不该被当成新会话
      - 去掉首尾空白、统一大小写，抹平各端取名的细微差异
      - 群聊和私聊分开命名空间，避免同名的群和人撞到一起

    残留代价：**同一个账号内**两个昵称完全相同的联系人会共享额度。
    这个方向的误判是「少回一条」，比重复回复安全，可以接受。
    """
    name = normalize_chat_name(message.chat_name)
    scope = "group" if message.is_group else "private"
    return f"{message.account}|{scope}:{name}"
