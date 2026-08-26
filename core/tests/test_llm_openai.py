"""OpenAI 兼容接口（豆包 / DeepSeek / 千问 / 智谱 / Moonshot）的单测。

这里起一个真的 HTTP 服务来接请求，而不是 mock 掉 urlopen：
请求体长什么样、Authorization 头有没有带上、状态码怎么处理，
这些正是最容易写错又最难在真机上查的部分。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import yaml

from core.config import ConfigError, build_config
from core.llm_openai import (
    LLMConfigError,
    OpenAICompatibleReplyWriter,
    build_writer,
)
from core.models import IncomingMessage
from core.providers import PROVIDERS
from core.wizard import build_result, to_yaml


class _Handler(BaseHTTPRequestHandler):
    """按 script 里排好的响应依次返回，并把收到的请求记下来。"""

    script: list[tuple[int, dict]] = []
    seen: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        _Handler.seen.append(
            {
                "path": self.path,
                "auth": self.headers.get("Authorization"),
                "body": body,
            }
        )

        status, payload = _Handler.script.pop(0) if _Handler.script else (200, {})
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args) -> None:
        pass  # 别把测试输出刷满


@pytest.fixture
def server():
    _Handler.script = []
    _Handler.seen = []
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, _Handler
    httpd.shutdown()
    httpd.server_close()


def _reply(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def _config(**llm_overrides):
    data = yaml.safe_load(
        to_yaml(build_result({}), reply_mode="ai", provider="doubao")
    )
    data["llm"].update(llm_overrides)
    return build_config(data)


def _writer(server, **kwargs) -> OpenAICompatibleReplyWriter:
    httpd, _ = server
    host, port = httpd.server_address
    return OpenAICompatibleReplyWriter(
        base_url=f"http://{host}:{port}/api/v3",
        api_key="test-key",
        model="doubao-seed-1-6-251015",
        **kwargs,
    )


def _msg(text: str = "在吗", chat_name: str = "小王") -> IncomingMessage:
    return IncomingMessage(chat_id=chat_name, chat_name=chat_name, text=text)


# ------------------------------------------------------------------ 请求格式


def test_request_shape_matches_openai_spec(server):
    _, handler = server
    handler.script = [(200, _reply("在，怎么了"))]

    result = _writer(server)(_msg(), _config())

    assert result == "在，怎么了"
    sent = handler.seen[0]
    assert sent["path"].endswith("/chat/completions")
    assert sent["auth"] == "Bearer test-key"
    assert sent["body"]["model"] == "doubao-seed-1-6-251015"
    assert sent["body"]["stream"] is False
    # 第一条必须是 system，人设就装在这里
    assert sent["body"]["messages"][0]["role"] == "system"
    assert "你就是我" in sent["body"]["messages"][0]["content"]
    assert sent["body"]["messages"][-1]["role"] == "user"


def test_persona_reaches_the_model(server):
    _, handler = server
    handler.script = [(200, _reply("在"))]

    _writer(server)(_msg(), _config())

    system = handler.seen[0]["body"]["messages"][0]["content"]
    # 问答生成的攻略和内置边界都要在
    assert "等我本人回你" in system
    assert "不答应任何转账" in system


def test_conversation_style_context_reaches_the_model(server):
    _, handler = server
    handler.script = [(200, _reply("确实"))]

    _writer(server)(
        IncomingMessage(
            chat_id="loky",
            chat_name="Loky",
            text="你觉得呢",
            style_context="统计：平均4字\n我：确实",
        ),
        _config(),
    )

    system = handler.seen[0]["body"]["messages"][0]["content"]
    assert "当前会话的说话样式" in system
    assert "平均4字" in system
    assert "只用于模仿表达方式" in system


def test_group_message_is_annotated(server):
    _, handler = server
    handler.script = [(200, _reply("在"))]

    writer = _writer(server)
    writer(
        IncomingMessage(
            chat_id="g", chat_name="项目组", text="在吗", sender_name="张三", is_group=True
        ),
        _config(),
    )

    last = handler.seen[0]["body"]["messages"][-1]["content"]
    # 群里不说清楚是谁在说话，模型只能瞎猜
    assert "项目组" in last and "张三" in last


def test_history_is_sent_as_real_turns(server):
    _, handler = server
    handler.script = [(200, _reply("在，怎么了")), (200, _reply("明天不行"))]

    writer = _writer(server)
    writer(_msg("在吗"), _config())
    writer(_msg("那明天呢"), _config())

    roles = [m["role"] for m in handler.seen[1]["body"]["messages"]]
    # system + 上一轮(user/assistant) + 这一轮(user)
    assert roles == ["system", "user", "assistant", "user"]
    assert handler.seen[1]["body"]["messages"][1]["content"] == "在吗"
    assert handler.seen[1]["body"]["messages"][2]["content"] == "在，怎么了"


# ------------------------------------------------------------------ 输出清洗


def test_wrapping_quotes_are_stripped(server):
    _, handler = server
    handler.script = [(200, _reply("「在，怎么了」"))]
    assert _writer(server)(_msg(), _config()) == "在，怎么了"


def test_runaway_output_is_truncated(server):
    _, handler = server
    handler.script = [(200, _reply("啊" * 300))]

    result = _writer(server)(_msg(), _config())

    # 宁可短一点，也别发出去一眼假
    assert len(result) <= _config().persona.max_chars * 2 + 1
    assert result.endswith("…")


def test_blank_output_becomes_no_reply(server):
    _, handler = server
    handler.script = [(200, _reply("   "))]
    assert _writer(server)(_msg(), _config()) is None


def test_missing_choices_becomes_no_reply(server):
    _, handler = server
    handler.script = [(200, {"error": "something"})]
    assert _writer(server)(_msg(), _config()) is None


# ------------------------------------------------------------------ 失败处理


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "API Key"),
        (404, "模型名不对"),
        (402, "余额"),
    ],
)
def test_user_fixable_errors_are_loud(server, status, expected):
    """key 或模型名填错了就一直不会回，必须报到用户看得见的地方。"""
    _, handler = server
    handler.script = [(status, {"error": {"message": "nope"}})]

    with pytest.raises(LLMConfigError) as exc:
        _writer(server)(_msg(), _config())
    assert expected in str(exc.value)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_errors_just_skip_the_message(server, status):
    """限流和对方宕机是暂时的，跳过这条就行，别把服务搞崩。"""
    _, handler = server
    handler.script = [(status, {"error": "busy"})]
    assert _writer(server)(_msg(), _config()) is None


def test_unreachable_host_skips_instead_of_raising():
    writer = OpenAICompatibleReplyWriter(
        base_url="http://127.0.0.1:9",  # 关着的端口
        api_key="k",
        model="m",
        timeout=1.0,
    )
    assert writer(_msg(), _config_offline()) is None


def _config_offline():
    return build_config(
        yaml.safe_load(to_yaml(build_result({}), reply_mode="ai", provider="doubao"))
    )


def test_empty_persona_never_calls_the_api(server):
    _, handler = server
    config = _config()
    config.persona.identity = ""
    config.persona.playbook = ""

    assert _writer(server)(_msg(), config) is None
    # 空人设生成出来只会是客服腔，不如不发——更不该白花一次钱
    assert handler.seen == []


# ------------------------------------------------------------------ 配置


def test_doubao_is_the_default_provider_from_the_wizard():
    config = _config()
    assert config.llm.provider == "doubao"
    assert config.llm.model == PROVIDERS["doubao"].model


def test_provider_defaults_fill_in_base_url_and_model():
    config = build_config(
        {"reply_mode": "ai", "persona": {"identity": "我很忙"}, "llm": {"provider": "deepseek"}}
    )
    assert config.llm.model == "deepseek-chat"
    assert config.llm.base_url == ""  # 留空，构造时用 provider 的默认地址


def test_unknown_provider_is_rejected_with_the_list():
    with pytest.raises(ConfigError) as exc:
        build_config({"llm": {"provider": "文心一言"}})
    assert "doubao" in str(exc.value)


def test_anthropic_still_works():
    config = build_config({"llm": {"provider": "anthropic"}})
    assert config.llm.model == "claude-opus-5"


def test_missing_key_says_which_variable_to_set(monkeypatch):
    monkeypatch.delenv("WXAUTO_LLM_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    with pytest.raises(LLMConfigError) as exc:
        build_writer(_config())
    # 报错得能直接照着做，不能只说「缺少凭据」
    assert "ARK_API_KEY" in str(exc.value)


def test_key_can_come_from_either_env_var(monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setenv("WXAUTO_LLM_API_KEY", "generic")
    assert build_writer(_config()) is not None

    monkeypatch.delenv("WXAUTO_LLM_API_KEY", raising=False)
    monkeypatch.setenv("ARK_API_KEY", "vendor")
    assert build_writer(_config()) is not None


def test_every_provider_has_a_usable_preset():
    for pid, provider in PROVIDERS.items():
        assert provider.base_url.startswith("https://"), pid
        assert provider.model, pid
        assert provider.api_key_env.isupper(), pid
        # 地址不该自带 /chat/completions，那段是调用时拼的
        assert not provider.base_url.rstrip("/").endswith("chat/completions"), pid
