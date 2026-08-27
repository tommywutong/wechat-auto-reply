"""用 OpenAI 兼容接口生成回复（豆包 / DeepSeek / 通义千问 / 智谱 / Moonshot）。

和 llm.py（Claude）是并列关系，共用同一套人设、上下文和清洗逻辑——
换模型不该换人设，否则同一个人在两台机器上语气都不一样。

刻意用标准库的 urllib 而不是 openai SDK：这个仓库要能在一台
只装了 python3 的 Mac 上跑起来，少一个依赖就少一处装不上的可能。
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from .config import Config
from .keychain import read_secret
from .models import IncomingMessage
from .persona import ConversationMemory, build_system_prompt
from .providers import PROVIDERS

logger = logging.getLogger(__name__)

_GENERIC_DEFER_REPLY = re.compile(
    r"(?:忙完|等会(?:儿)?|一会(?:儿)?|晚点|回头).{0,8}(?:再说|回(?:你)?|聊|看)"
    r"|(?:等我).{0,8}(?:回(?:你)?|回复|再说)",
    re.IGNORECASE,
)
_CASUAL_MESSAGE_HINTS = (
    "在吗",
    "在不在",
    "咋了",
    "怎么了",
    "干嘛",
    "忙吗",
    "忙不忙",
    "方便吗",
    "哈哈",
    "笑死",
    "最近",
    "吃了吗",
    "好久不见",
    "牛",
    "收到",
)
_HUMAN_CONFIRMATION_HINTS = (
    "约",
    "见面",
    "明天",
    "后天",
    "今晚",
    "下周",
    "几点",
    "时间",
    "日程",
    "地址",
    "报价",
    "价格",
    "钱",
    "合同",
    "转账",
    "付款",
    "借",
    "投票",
)


def _sanitize_salutation(text: str, chat_name: str) -> str:
    """过滤模型沿用历史样例的错误身份称呼。"""

    if chat_name and "老林" in chat_name:
        return text
    if "老林" in text:
        logger.warning("模型生成了未配置的身份称呼，丢弃本条回复")
        return ""
    return text.strip()


def _clean_generated_text(text: Optional[str], chat_name: str) -> str:
    """统一处理模型候选，重写前后都走同一份身份安全检查。"""

    if not text:
        return ""
    return _sanitize_salutation(text.strip().strip("「」\"'“”").strip(), chat_name)


def _should_rewrite_generic_defer(message: IncomingMessage, text: str) -> bool:
    """仅对低风险闲聊纠正机械拖延，不替代需要人工确认的谨慎回复。"""

    compact = re.sub(r"\s+", "", text)
    if (
        message.batch_size != 1
        or message.message_type != "text"
        or len(compact) > 32
        or _GENERIC_DEFER_REPLY.search(compact) is None
    ):
        return False
    incoming = message.text.casefold()
    if any(hint in incoming for hint in _HUMAN_CONFIRMATION_HINTS):
        return False
    return any(hint in incoming for hint in _CASUAL_MESSAGE_HINTS)


class LLMConfigError(RuntimeError):
    """key 没配、地址没填这类「用户能自己修」的问题。"""


def _explain_http(code: int, body: str) -> str:
    """状态码翻译成用户能照着做的话。"""
    if code in (401, 403):
        return "API Key 不对或者没权限"
    if code == 404:
        return "模型名不对，去控制台把模型 ID 复制到 llm.model"
    if code == 402:
        return "余额不足"
    if code == 429:
        return "调用太频繁，或者免费额度用完了"
    if 500 <= code < 600:
        return "对方服务器出问题了"
    return f"接口返回 {code}：{body[:200]}"


class OpenAICompatibleReplyWriter:
    """把一条微信消息变成一句像我说的话。构造一次，重复使用。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        memory: Optional[ConversationMemory] = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise LLMConfigError("没有拿到 API Key")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._memory = memory or ConversationMemory()
        self._timeout = timeout

    def __call__(self, message: IncomingMessage, config: Config) -> Optional[str]:
        persona = config.persona
        if not persona.is_configured():
            logger.warning("没有配置人设，跳过 AI 生成——空人设只会生成客服腔")
            return None

        # TraceMemo 的 chat_id 含稳定 talker，备注改名不会把短期上下文切断。
        chat_key = message.chat_id.strip() or message.chat_name
        self._memory.remember(chat_key, "them", message.text, message.timestamp)

        # 上下文作为真实的多轮对话传入，而不是塞进一个字符串
        messages: list[dict] = [
            {"role": "system", "content": build_system_prompt(persona, message.style_context)}
        ]
        for turn in self._memory.recent(chat_key, message.timestamp):
            role = "user" if turn.speaker == "them" else "assistant"
            if len(messages) > 1 and messages[-1]["role"] == role:
                messages[-1]["content"] += "\n" + turn.text
            else:
                messages.append({"role": role, "content": turn.text})

        if len(messages) == 1:
            messages.append({"role": "user", "content": message.text})

        if message.is_group:
            messages[-1]["content"] = (
                f"（群「{message.chat_name}」里 {message.sender_name} 说）"
                + messages[-1]["content"]
            )
        messages[-1]["content"] += (
            f"\n\n【称呼约束】当前会话显示名是「{message.chat_name}」。"
            "不要把对方称作其他姓名；除非对方在本条消息中明确自称，否则不要猜测称呼。"
        )
        if message.batch_size > 1:
            messages[-1]["content"] += (
                f"\n【连续消息】这是对方短时间内连续发来的 {message.batch_size} 条消息。"
                "请自行判断合并回答或分点回答，不要逐条机械复述。"
            )

        try:
            text = self._post(messages, config.llm.max_tokens)
        except LLMConfigError:
            raise
        except Exception as exc:  # 网络问题等，本条跳过即可
            logger.warning("调用失败，本条跳过: %s", exc)
            return None

        if not text:
            return None

        text = _clean_generated_text(text, message.chat_name)
        if not text:
            return None

        if _should_rewrite_generic_defer(message, text):
            logger.info("检测到低风险闲聊的机械拖延回复，要求模型重写一次")
            revision_messages = [
                *messages,
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        "上一句候选过于像机械拖延。当前是普通低风险闲聊，"
                        "请直接、自然地重新回复，不要使用“忙完再说”“等会儿再说”"
                        "或“晚点回”这一类空泛拖延句；仍不得编造事实或承诺。"
                    ),
                },
            ]
            try:
                rewritten = _clean_generated_text(
                    self._post(revision_messages, config.llm.max_tokens),
                    message.chat_name,
                )
            except LLMConfigError:
                raise
            except Exception as exc:
                logger.warning("重写机械拖延回复失败，保留首个可用候选：%s", exc)
                rewritten = ""
            if rewritten:
                text = rewritten

        # 超长时截断而不是原样发出：宁可短一点，也别一眼假
        limit = persona.max_chars
        if limit > 0 and len(text) > limit * 2:
            logger.info("生成内容过长（%d 字），已截断", len(text))
            text = text[: limit * 2].rstrip("，、。 ") + "…"

        self._memory.remember(chat_key, "me", text, message.timestamp)
        return text

    def _post(self, messages: list[dict], max_tokens: int) -> Optional[str]:
        payload = json.dumps(
            {
                "model": self._model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": False,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            reason = _explain_http(exc.code, detail)
            # key 和模型名这类填错了的，报到日志顶层——用户不改就一直不回
            if exc.code in (401, 402, 403, 404):
                raise LLMConfigError(reason) from exc
            logger.warning("%s", reason)
            return None

        data = json.loads(body)
        choices = data.get("choices") or []
        if not choices:
            logger.warning("接口没返回 choices：%s", body[:200])
            return None
        return (choices[0].get("message") or {}).get("content")


def build_writer(config: Config) -> object:
    """按配置造生成器。放这里而不是 server/app.py，是为了让 macOS
    采集端和其他入口也能共用同一套构造逻辑。"""
    provider_id = config.llm.provider

    if provider_id not in PROVIDERS:
        raise LLMConfigError(f"未知的 llm.provider: {provider_id!r}")

    provider = PROVIDERS[provider_id]

    # 优先用通用变量，方便一台机器上换着试；再退到这家自己的惯用变量
    api_key = (
        config.llm.api_key
        or os.environ.get("WXAUTO_LLM_API_KEY", "")
        or os.environ.get(provider.api_key_env, "")
        or read_secret(
            provider.api_key_env,
            f"com.wxauto.{provider_id}-api-key",
        )
    )
    if not api_key:
        raise LLMConfigError(
            f"{provider.name} 需要 API Key。"
            f"设一下环境变量：export {provider.api_key_env}=你的key"
        )

    return OpenAICompatibleReplyWriter(
        base_url=config.llm.base_url or provider.base_url,
        api_key=api_key,
        model=config.llm.model or provider.model,
    )
