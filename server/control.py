"""局域网控制 API。

该进程只负责控制 Mac 上已有的服务，不读取微信数据库，也不接受微信消息。
首次配对使用 install-tracememo-control.sh 生成的短期代码，配对后所有请求都
必须携带独立的 Bearer 控制令牌。
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field


REPO_DIR = Path(os.environ.get("WXAUTO_REPO_DIR", Path(__file__).resolve().parents[1])).resolve()
CONTROL_TOKEN = os.environ.get("WXAUTO_CONTROL_TOKEN", "").strip()
PAIRING_FILE = Path(os.environ.get("WXAUTO_CONTROL_PAIRING_FILE", REPO_DIR / "var" / "control-pairing-code"))
PAIRING_TTL = 600
APP = FastAPI(title="TraceMemo AutoReply Control", version="1.0")


class PairRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=32)


class ConfigPatch(BaseModel):
    values: dict[str, Any]


def _launch_domain() -> str:
    return f"gui/{os.getuid()}"


def _run(args: list[str], timeout: float = 12.0) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def _read_pairing_code() -> str:
    try:
        payload = json.loads(PAIRING_FILE.read_text(encoding="utf-8"))
        if time.time() - float(payload.get("created_at", 0)) > PAIRING_TTL:
            return ""
        return str(payload.get("code", "")).strip()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return ""


def _service_state(label: str) -> str:
    status, stdout, _ = _run(["/bin/launchctl", "print", f"{_launch_domain()}/{label}"])
    if status != 0:
        plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        return "stopped" if plist.exists() else "not_installed"
    output = (stdout or "").lower()
    if "state = running" in output or "pid = " in output:
        return "running"
    return "stopped"


def _public_config() -> dict[str, Any]:
    script = REPO_DIR / "scripts" / "app_config.py"
    status, stdout, stderr = _run([str(REPO_DIR / ".venv" / "bin" / "python"), str(script), "get"])
    if status != 0:
        raise HTTPException(status_code=503, detail=stderr.strip() or "无法读取配置")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="配置响应格式无效") from exc


def _logs(limit: int) -> list[str]:
    paths = [
        REPO_DIR / "var" / "tracememo-autoreply.log",
        REPO_DIR / "var" / "tracememo-autoreply.err.log",
    ]
    lines: list[str] = []
    for path in paths:
        try:
            lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    # 远程控制端只返回状态事件，不能把联系人、消息正文或 OCR 内容带出 Mac。
    return [_redact_log_line(line) for line in lines[-limit:]]


def _redact_log_line(line: str) -> str:
    """将本地详细日志降级为可远程查看的无个人数据摘要。"""
    prefix, _, message = line.partition(" INFO ")
    if not message:
        prefix, _, message = line.partition(" WARNING ")
    if not message:
        prefix, _, message = line.partition(" ERROR ")
    prefix = prefix.strip()

    if "检测到新消息" in message:
        event = "检测到新消息"
    elif "草稿已生成" in message or "已生成" in message:
        event = "已生成回复草稿"
    elif "开始第" in message and "重试" in message:
        event = "正在重试发送"
    elif "发送失败" in message or "未确认发送" in message:
        event = "发送失败"
    elif "发送成功" in message or "已确认发送" in message:
        event = "已确认发送"
    elif "本轮状态" in message or "状态：" in message:
        event = message
    elif "TraceMemo" in message and ("失败" in message or "超时" in message):
        event = "TraceMemo 请求失败"
    elif "启动" in message:
        event = "自动回复服务已启动"
    else:
        event = "已记录运行事件"
    return f"{prefix} {event}".strip()


def _require_token(authorization: str = Header(default="")) -> None:
    if not CONTROL_TOKEN or not secrets.compare_digest(authorization, f"Bearer {CONTROL_TOKEN}"):
        raise HTTPException(status_code=401, detail="unauthorized")


@APP.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "pairing_available": bool(_read_pairing_code()), "service": "control"}


@APP.post("/pair")
def pair(payload: PairRequest) -> dict[str, Any]:
    expected = _read_pairing_code()
    if not expected or not secrets.compare_digest(payload.code.strip(), expected):
        raise HTTPException(status_code=401, detail="配对码无效或已过期")
    if not CONTROL_TOKEN:
        raise HTTPException(status_code=503, detail="控制服务未配置控制令牌")
    try:
        PAIRING_FILE.unlink()
    except OSError:
        pass
    return {"token": CONTROL_TOKEN, "device": "TraceMemo AutoReply Mac"}


@APP.get("/status", dependencies=[Depends(_require_token)])
def status() -> dict[str, Any]:
    return {
        "services": {
            "engine": _service_state("com.wxauto.server"),
            "autoreply": _service_state("com.wxauto.tracememo-autoreply"),
            "control": "running",
        },
        "updated_at": int(time.time()),
    }


@APP.get("/logs", dependencies=[Depends(_require_token)])
def logs(limit: int = Query(default=120, ge=1, le=500)) -> dict[str, Any]:
    return {"lines": _logs(limit), "updated_at": int(time.time())}


@APP.get("/config", dependencies=[Depends(_require_token)])
def config() -> dict[str, Any]:
    return _public_config()


@APP.put("/config", dependencies=[Depends(_require_token)])
def update_config(payload: ConfigPatch) -> dict[str, Any]:
    script = REPO_DIR / "scripts" / "app_config.py"
    python = REPO_DIR / ".venv" / "bin" / "python"
    body = json.dumps(payload.values, ensure_ascii=False).encode("utf-8")
    try:
        result = subprocess.run(
            [str(python), str(script), "set"],
            cwd=REPO_DIR,
            input=body,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip() or "保存配置失败")
    # 配置变更必须让两个已有服务重新加载，避免 App 显示的设置与实际行为分离。
    service_result = _service_action("restart")
    if not service_result[0]:
        raise HTTPException(status_code=503, detail=service_result[1])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return _public_config()


def _service_action(action: str) -> tuple[bool, str]:
    if action not in {"start", "stop", "restart"}:
        return False, "不支持的服务操作"
    labels = ["com.wxauto.tracememo-autoreply", "com.wxauto.server"]
    operations: list[tuple[str, str]] = []
    if action in {"stop", "restart"}:
        operations.extend(("bootout", label) for label in labels)
    if action in {"start", "restart"}:
        operations.extend(("bootstrap", label) for label in reversed(labels))
    for operation, label in operations:
        target = f"{_launch_domain()}/{label}"
        if operation == "bootout":
            _run(["/bin/launchctl", "bootout", target])
            continue
        plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        if not plist.exists():
            if label == "com.wxauto.tracememo-autoreply":
                status, _, stderr = _run(["/bin/bash", str(REPO_DIR / "scripts" / "install-tracememo-autoreply.sh")])
                if status != 0:
                    return False, stderr.strip() or "自动回复服务未安装"
                continue
            return False, f"缺少 {label} 的 launchd 配置"
        status, _, stderr = _run(["/bin/launchctl", "enable", target])
        if status != 0:
            return False, stderr.strip() or f"无法重新启用 {label}"
        status, _, stderr = _run(["/bin/launchctl", "bootstrap", _launch_domain(), str(plist)])
        if status != 0 and _service_state(label) != "running":
            kick_status, _, kick_err = _run(["/bin/launchctl", "kickstart", target])
            if kick_status != 0:
                return False, kick_err.strip() or stderr.strip() or f"{label} 启动失败"
    return True, ""


@APP.post("/service/{action}", dependencies=[Depends(_require_token)])
def service(action: str) -> dict[str, Any]:
    ok, detail = _service_action(action)
    if not ok:
        raise HTTPException(status_code=503, detail=detail)
    return status()
