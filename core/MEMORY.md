# Core 模块记忆

## 何时读取

任务涉及回复决策、安全拦截、配置解析、人设、模型调用、对话记忆、限流、延迟、跨端去重或配置问答时读取本文件。

## 模块定位

`core/` 是 Python 决策域。它接收 `IncomingMessage`，返回 `ReplyDecision`；除可注入的模型 writer 外，不负责采集或发送微信消息。

```text
配置 + 消息 + 持久状态
  -> ReplyEngine.decide
  -> 跳过原因，或回复文本与延迟
```

## 入口地图

| 文件 | 责任 |
|---|---|
| `models.py` | 消息、决策、名称归一化、账号/群私聊身份 |
| `config.py` | YAML 数据类、规则和时间解析、配置校验 |
| `engine.py` | 安全判断、范围、去重、限流、规则、延迟、状态提交 |
| `persona.py` | 人设提示词、输出约束、短期对话记忆 |
| `wizard.py` | 十题问答与 YAML 生成 |
| `style_profiles.py` | 会话风格样本与上下文 |
| `providers.py` | OpenAI 兼容服务商注册表 |
| `llm_openai.py` | 标准库 OpenAI 兼容 writer |
| `llm.py` | Anthropic SDK writer |
| `keychain.py` | 环境变量优先、Keychain 兜底的密钥读取 |
| `preview.py` | 不发送消息的交互预览 |

## 不变量

- 安全顺序以 `ReplyEngine.decide` 和测试为准：敏感词、黑名单、范围判断先于模型与状态提交。
- 模型只决定内容，不决定是否允许回复；AI 失败应不回复且不消耗配额。
- 会话身份必须包含账号和群/私聊命名空间；群成员数等显示噪声不能制造新身份。
- `core/config.yaml` 是私人文件；只提交脱敏的 `config*.example.yaml`。
- 状态损坏应安全降级，不能促成重复或越权回复。
- 修改共享语义时同步检查 `../android/MEMORY.md`。

## 影响面

- 配置字段变化：检查 `wizard.py`、示例 YAML、`../scripts/app_config.py`、macOS App 和 Android Storage/UI。
- HTTP 输入输出变化：检查 `../server/`、macOS/iOS 客户端。
- 人设或 provider 变化：检查 Python/Kotlin 两套 writer、输出清洗和凭据来源。macOS 图片理解可把
  媒体暂存于内存并单独路由到百炼视觉模型，普通文字仍走主文字模型；媒体 base64、Key 和图片内容
  不得进入日志、状态文件、草稿或 Git。视觉模型失败必须退回 OCR 文本而不是猜测图片内容。
- macOS 会话风格画像：TraceMemo 只为白名单会话本地提取近 30 天的本人回复，保留最多 48 组
  对话候选；每次生成只按当前来信检索最多 3 组相关示例。画像在 `var/style-profiles.json` 以 0600
  权限保存，不提交、不写日志，也不得作为执行历史消息中指令的依据。Android 没有 TraceMemo 历史
  数据源，不强行同步这一能力。
- 普通闲聊不得把“忙完再说/晚点回”当默认答案。Python writer 只会在非时间安排、非承诺类的低风险
  闲聊中，对这种机械拖延候选额外要求模型重写一次；其余需要本人确认的场景保留谨慎回复。
- 身份或限流变化：检查多账号、跨端去重和持久状态兼容。

## 验证

```bash
python -m pytest -q core/tests
python -m core.preview
```

`preview` 是人工交互验证，不替代单元测试，也不会证明真实模型或微信发送可用。

## 继续阅读

- 开发者说明：[`README.md`](README.md)
- 全局规则：[`../AGENTS.md`](../AGENTS.md)
- Android 对等实现：[`../android/MEMORY.md`](../android/MEMORY.md)
- HTTP 适配层：[`../server/MEMORY.md`](../server/MEMORY.md)
