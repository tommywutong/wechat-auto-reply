"""能接哪些模型服务。

安卓端有同一份表（AiWriter.kt 的 PRESETS），两边保持一致。

为什么不只支持 Claude：在国内拿一个能用的 Anthropic key 并不容易，
而这套东西的目标用户就是「不折腾」的人。豆包、DeepSeek 这些都是
OpenAI 兼容格式，注册即用、国内直连，接进来只是多几行代码的事。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    base_url: str
    model: str
    api_key_env: str
    note: str = ""


# 豆包放第一个：这套东西要的是「聊天像真人」，不是解数学题，
# 而豆包的中文口语是这几家里最自然的，价格也便宜。
PROVIDERS: dict[str, Provider] = {
    p.id: p
    for p in (
        Provider(
            id="doubao",
            name="豆包（火山方舟）",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            model="doubao-seed-1-6-251015",
            api_key_env="ARK_API_KEY",
            note=(
                "在火山方舟控制台建 API Key。model 既可以写模型 ID，"
                "也可以写推理接入点（ep- 开头那串）；"
                "提示模型不存在时，去控制台复制一个填到 llm.model。"
            ),
        ),
        Provider(
            id="deepseek",
            name="DeepSeek",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            api_key_env="DEEPSEEK_API_KEY",
        ),
        Provider(
            id="qwen",
            name="通义千问",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
            api_key_env="DASHSCOPE_API_KEY",
        ),
        Provider(
            id="zhipu",
            name="智谱 GLM",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model="glm-4-flash",
            api_key_env="ZHIPU_API_KEY",
        ),
        Provider(
            id="moonshot",
            name="Moonshot",
            base_url="https://api.moonshot.cn/v1",
            model="moonshot-v1-8k",
            api_key_env="MOONSHOT_API_KEY",
        ),
    )
}

ANTHROPIC = "anthropic"
"""Claude 走官方 SDK，不在上面这张表里。"""


def is_openai_compatible(provider_id: str) -> bool:
    return provider_id in PROVIDERS


def describe() -> str:
    """给报错信息用：把能填的值列出来，省得用户去翻文档。"""
    return "、".join([ANTHROPIC, *PROVIDERS])
