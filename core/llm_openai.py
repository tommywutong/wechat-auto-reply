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
import urllib.error
import urllib.request
from typing import Optional

from .config import Config
from .keychain import read_secret
from .models import IncomingMessage
from .persona import ConversationMemory, build_system_prompt
from .providers import PROVIDERS

logger = logging.getLogger(__name__)


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

        chat_key = message.chat_name
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

        try:
            text = self._post(messages, config.llm.max_tokens)
        except LLMConfigError:
            raise
        except Exception as exc:  # 网络问题等，本条跳过即可
            logger.warning("调用失败，本条跳过: %s", exc)
            return None

        if not text:
            return None

        # 模型偶尔会自带引号，去掉以免发出去很怪
        text = text.strip().strip("「」\"'“”").strip()
        if not text:
            return None

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
