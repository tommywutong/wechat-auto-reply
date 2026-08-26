"""回复引擎的 HTTP 服务。

手机端（Android App / iOS Appium 脚本 / macOS 脚本）把消息 POST 过来，
拿到「回不回、回什么、等几秒」。规则改动只需要重启这个服务，
不用重新打包 App。

启动：
    export WXAUTO_CONFIG=core/config.example.yaml
    export WXAUTO_TOKEN=$(openssl rand -hex 16)
    uvicorn server.app:app --host 0.0.0.0 --port 8848
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.config import ConfigError, load_config
from core.engine import ReplyEngine
from core.models import IncomingMessage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CONFIG_PATH = os.environ.get("WXAUTO_CONFIG", "core/config.example.yaml")
STATE_PATH = os.environ.get("WXAUTO_STATE", "var/state.json")
AUTH_TOKEN = os.environ.get("WXAUTO_TOKEN", "")

app = FastAPI(title="WeChat Auto Reply Engine", version="1.0")

_engine: Optional[ReplyEngine] = None


def _build_engine() -> ReplyEngine:
    config = load_config(CONFIG_PATH)

    llm_reply = None
    if config.llm.enabled:
        if config.llm.provider == "anthropic":
            # 只有真要用 Claude 时才 import，免得没装 anthropic 的人跑不起来
            from core.llm import ClaudeReplyWriter

            llm_reply = ClaudeReplyWriter()
        else:
            # 豆包这类走 OpenAI 兼容接口，只用标准库，没有额外依赖
            from core.llm_openai import build_writer

            llm_reply = build_writer(config)
        logger.info("AI 生成已启用：%s / %s", config.llm.provider, config.llm.model)

    return ReplyEngine(config, llm_reply=llm_reply, state_path=STATE_PATH)


@app.on_event("startup")
def startup() -> None:
    global _engine
    if not AUTH_TOKEN:
        # 这个服务能替你发微信消息，裸奔监听公网等于把号交出去。
        raise RuntimeError("必须设置 WXAUTO_TOKEN 环境变量，否则任何人都能驱动你的微信")
    _engine = _build_engine()
    logger.info("引擎已加载：%s（%d 条规则）", CONFIG_PATH, len(_engine.config.rules))


def require_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {AUTH_TOKEN}"
    # 常数时间比较，避免通过响应时间猜 token
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


class MessageIn(BaseModel):
    chat_id: str = Field(..., min_length=1)
    chat_name: str
    text: str
    sender_name: str = ""
    is_group: bool = False
    mentioned_me: bool = False
    style_context: str = ""
    platform: str = "unknown"
    account: str = ""
    """驱动的是哪个微信号。同号多端填相同值，不同号填不同值；
    留空则回退成 platform（按平台隔离）。"""


class DecisionOut(BaseModel):
    should_reply: bool
    reason: str
    text: Optional[str] = None
    delay_seconds: float = 0.0
    rule_name: Optional[str] = None


@app.post("/reply", response_model=DecisionOut, dependencies=[Depends(require_token)])
def reply(payload: MessageIn) -> DecisionOut:
    assert _engine is not None
    decision = _engine.decide(IncomingMessage(**payload.model_dump()))
    return DecisionOut(**decision.__dict__)


@app.post("/reload", dependencies=[Depends(require_token)])
def reload_config() -> dict[str, object]:
    """改完 YAML 不用重启进程。注意：冷却计数会保留（读的是同一个 state 文件）。"""
    global _engine
    try:
        _engine = _build_engine()
    except (ConfigError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"配置加载失败: {exc}") from exc
    return {"ok": True, "rules": len(_engine.config.rules)}


@app.get("/health")
def health() -> dict[str, object]:
    """不鉴权，只暴露存活状态，不泄露任何规则内容。"""
    return {"ok": _engine is not None, "config": Path(CONFIG_PATH).name}
