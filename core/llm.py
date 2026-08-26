"""用 Claude 按人设和攻略生成回复。

和「关键词→罐头话」的区别全在这个文件里：这里不做匹配，
而是把「你是谁、怎么说话、这类事怎么处理、最近聊了什么」交给模型，
让它自己判断该回什么。
"""

from __future__ import annotations

import logging
from typing import Optional

import anthropic

from .config import Config
from .models import IncomingMessage
from .persona import ConversationMemory, build_system_prompt

logger = logging.getLogger(__name__)


class ClaudeReplyWriter:
    """把一条微信消息变成一句像我说的话。构造一次，重复使用。"""

    def __init__(
        self,
        client: Optional[anthropic.Anthropic] = None,
        memory: Optional[ConversationMemory] = None,
    ) -> None:
        # 不传 api_key：SDK 会依次读 ANTHROPIC_API_KEY、ANTHROPIC_AUTH_TOKEN
        # 以及 `ant auth login` 存下的 profile。
        self._client = client or anthropic.Anthropic()
        self._memory = memory or ConversationMemory()

    def __call__(self, message: IncomingMessage, config: Config) -> Optional[str]:
        persona = config.persona
        if not persona.is_configured():
            logger.warning("没有配置人设，跳过 AI 生成——空人设只会生成客服腔")
            return None

        chat_key = message.chat_name
        self._memory.remember(chat_key, "them", message.text, message.timestamp)

        # 上下文作为多轮对话传入，而不是塞进一个字符串——
        # 模型对真实的多轮结构理解得更准。
        history = self._memory.recent(chat_key, message.timestamp)
        messages: list[dict] = []
        for turn in history:
            role = "user" if turn.speaker == "them" else "assistant"
            if messages and messages[-1]["role"] == role:
                # 连续同一方发言合并，避免出现非法的连续同角色
                messages[-1]["content"] += "\n" + turn.text
            else:
                messages.append({"role": role, "content": turn.text})

        # 首条必须是 user；历史被裁剪后可能以我方开头
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        if not messages:
            messages = [{"role": "user", "content": message.text}]

        if message.is_group:
            messages[-1]["content"] = (
                f"（群「{message.chat_name}」里 {message.sender_name} 说）"
                + messages[-1]["content"]
            )

        try:
            response = self._client.beta.messages.create(
                model=config.llm.model,
                max_tokens=config.llm.max_tokens,
                system=build_system_prompt(persona, message.style_context),
                # 低 effort：自动回复要的是低延迟。保持 thinking 默认开启，
                # 在 Opus 5 上关闭 thinking 反而可能把内部标签漏进正文。
                output_config={"effort": config.llm.effort},
                # 安全分类器偶尔会误伤正常内容，开启服务端兜底让请求
                # 自动换模型重跑，而不是直接失败。
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=messages,
            )
        except anthropic.APIError as exc:
            logger.warning("调用失败，本条跳过: %s", exc)
            return None

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            logger.warning("模型拒绝生成（category=%s），本条跳过", category)
            return None

        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            return None

        # 模型偶尔会自带引号，去掉以免发出去很怪
        text = text.strip("「」\"'“”").strip()

        # 超长时截断而不是原样发出：宁可短一点，也别一眼假
        limit = persona.max_chars
        if limit > 0 and len(text) > limit * 2:
            logger.info("生成内容过长（%d 字），已截断", len(text))
            text = text[: limit * 2].rstrip("，、。 ") + "…"

        self._memory.remember(chat_key, "me", text, message.timestamp)
        return text
