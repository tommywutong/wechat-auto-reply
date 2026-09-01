# Python 决策核心

`core` 提供与平台无关的自动回复判断。平台层把消息标准化后交给引擎，引擎只返回“是否回复、原因、文本和等待时间”，不直接操作微信。

## 数据流

```text
YAML -> config.py -> Config
消息 -> models.py -> IncomingMessage
Config + IncomingMessage + state -> engine.py -> ReplyDecision
                                      |
                                      +-> persona / LLM writer（按模式）
```

## 主要能力

- 硬敏感词、黑白名单、屏蔽词与群聊策略。
- 活动时段、单会话冷却、小时/每日配额与跨会话间隔。
- 跨平台去重、账号隔离和回复文案轮换。
- `ai`、`rules`、`rules_then_ai` 三种回复模式。
- 人设提示词、会话记忆、输出清洗与多模型服务商。
- 引导式问答和不发送消息的本地预览。

## 配置

从以下示例开始：

- [`config.example.yaml`](config.example.yaml)：规则优先配置。
- [`config.ai.example.yaml`](config.ai.example.yaml)：人设与 AI 配置。

实际运行文件通常为 `core/config.yaml`，其中可能包含联系人和私人规则，已被 Git 忽略。

重新运行问答或预览：

```bash
python -m core.wizard
python -m core.preview
```

## 模型接入

Anthropic 使用 SDK；豆包、DeepSeek、通义千问、百炼业务空间、智谱和 Moonshot 等通过 OpenAI 兼容 writer。服务商默认值以 [`providers.py`](providers.py) 为准，凭据应来自环境变量或 macOS Keychain。图片和表情包可单独路由到视觉模型（默认 `qwen3-vl-flash`，失败时尝试 `qwen3-vl-plus`），普通文字不会上传到视觉模型。

## 开发与测试

```bash
python -m pytest -q core/tests
```

修改决策顺序、配置默认值、提示词或问答映射时，还要检查 Android 的独立 Kotlin 实现。测试通过只证明纯逻辑和夹具行为，不证明第三方模型或微信环境可用。

Agent 修改本模块前应读取 [`MEMORY.md`](MEMORY.md)。
