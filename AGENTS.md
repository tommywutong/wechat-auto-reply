# Agent 工作规则

本文件是仓库级入口。任何 agent 开始任务时先读本文件，但不要因此一次性读取整个仓库。
项目知识按渐进式披露组织：根 [`MEMORY.md`](MEMORY.md) 只负责模块路由，每个模块自己的
`MEMORY.md` 保存实现约束。先确定改动范围，再读取对应模块记忆和其中列出的源码。

## 1. 渐进式阅读协议

按以下顺序取上下文，读到足以完成任务即停止：

1. 读本文件，确认全局安全边界、工作方式和验证要求。
2. 用 `git status --short --branch` 检查工作区，保留用户已有改动。
3. 根据下方“任务路由”定位一个模块的 `MEMORY.md`。
4. 只读该模块列出的入口源码、相邻测试和直接相关文档。
5. 只有遇到跨模块契约、行为不一致或信息缺口时，才读取第二个模块记忆。

不要把 `MEMORY.md` 当成比源码更高的事实来源。信息冲突时采用以下优先级：

1. 当前源码与构建配置
2. 当前测试及测试夹具
3. `README.md`、`docs/`、`PRODUCT.md`、`DESIGN.md`
4. `MEMORY.md` 中的快照说明

发现记忆过期时，在同一改动中更新对应章节；不要保留已知错误的说明。

## 2. 任务路由

| 任务范围 | 先读 | 主要入口 |
|---|---|---|
| 回复决策、安全规则、限流、人设、模型、问答 | `core/MEMORY.md` | `core/engine.py`, `core/config.py`, `core/persona.py` |
| HTTP API、鉴权、热加载 | `server/MEMORY.md` | `server/app.py` |
| TraceMemo 读取、轮询、草稿、OCR 发送 | `macos/MEMORY.md` | `macos/tracememo_poller.py`, `macos/wechat_sender.py` |
| macOS 控制面板 | `macos/TraceMemoAutoReplyApp/MEMORY.md` | SwiftUI source, `scripts/app_config.py` |
| Android App 或内嵌引擎 | `android/MEMORY.md` | `android/app/src/main/java/com/wxauto/reply/` |
| iOS 自动化或注入实验 | `ios/MEMORY.md` | `ios/appium/`, `ios/tweak/` |
| 安装、launchd、构建、联系人/配置桥接 | `scripts/MEMORY.md` | `scripts/` |
| 用户文档、部署说明、能力声明 | `docs/MEMORY.md` | `README.md`, `docs/`, `PRODUCT.md`, `DESIGN.md` |
| 多账号、跨端去重 | `core/MEMORY.md`，必要时 `docs/MEMORY.md` | `core/models.py`, `docs/multi-account.md` |

## 3. 不可破坏的安全约束

这是会代表用户发送真实微信消息的自动化项目。以下约束优先于便利性：

- 保持失败关闭：无法确认消息、目标会话、配置、凭据、模型结果或发送状态时，不发送。
- 敏感词、黑名单、屏蔽词和会话范围判断必须发生在模型调用与频率提交之前。
- 模型只决定“说什么”，不能绕过“是否允许回复”的确定性规则。
- AI 失败不得偷偷回退到可能改变语气或语义的规则文案。
- 发送前必须再次检查总开关；macOS 发送器还必须复核右侧完整会话标题。
- 不得弱化白名单、群聊 `@` 策略、冷却、配额、跨会话间隔或发送延迟，除非用户明确要求并理解风险。
- 未经用户明确授权，不运行真实发送模式、不操作微信界面、不安装 launchd 服务、不写 Keychain。
- 验证优先使用单元测试、预览、`--dry-run`、`--once`、`--diagnose-name` 或草稿模式。

任何改变判断顺序、会话身份、状态提交时机、延迟计算或发送确认的修改，都属于高风险改动，必须同时补回归测试。

## 4. 凭据与隐私

- Token 和模型密钥应从 macOS Keychain 或环境变量读取，不写进源文件、提交记录或 UI 日志。
- 不读取、展示或提交真实聊天正文、联系人列表、截图、OCR 失败产物和运行日志，除非用户明确把具体文件纳入任务。
- 以下均为本机私有或生成内容，不得提交：
  - `core/config.yaml`
  - `.wxauto_token`
  - `var/`
  - `.venv/`
  - `.build/`
  - `dist/`
  - `android/local.properties`
  - APK、DEB、失败截图及 OCR 元数据
- 示例配置只能包含虚构、脱敏数据。
- 新日志不得打印 Authorization、Keychain 返回值、API Key、完整请求头或私人消息正文。

## 5. 跨实现一致性

Python 引擎和 Android Kotlin 引擎是两份独立实现，不共享运行时代码。修改以下语义时，必须检查另一端是否需要同步：

- 硬拦截敏感词与判断顺序
- 会话名归一化、群/私聊身份和账号隔离
- 白名单、黑名单、群聊策略与活动时段
- 冷却、单会话/全局配额、跨会话间隔
- 回复轮换、签名、随机延迟与按字数计算的输入耗时
- AI 模式、提示词、输出清洗、对话记忆和失败策略
- 配置问答题目、默认值及生成结果

若只修改单端平台能力，明确说明为什么不需要同步另一端。不要假设两份字段名称完全相同，以行为和测试为准。

## 6. 修改纪律

- 修 Bug：先复现或用测试固定失败行为，再改实现。
- 新功能：先确认落在哪个数据流和模块，不在控制层重复实现引擎规则。
- 配置变更：同步检查示例 YAML、解析校验、控制面板/Android 存储和相关文档。
- API 变更：同步检查所有客户端、Pydantic 模型、鉴权与兼容性。
- macOS UI 变更：遵循 `PRODUCT.md` 与 `DESIGN.md`；不在界面中显示或保存 Token。
- 脚本变更：保持路径带空格时可用，使用引号，保留 `set -euo pipefail`，避免继承明文密钥。
- 不顺手改无关文件，不覆盖用户工作区改动，不提交生成物。
- 注释解释“为什么”和风险边界，避免复述代码。

## 7. 验证矩阵

从最小相关验证开始；跨模块或高风险修改再扩大范围。

| 范围 | 命令 |
|---|---|
| Python 核心、服务、macOS Python、脚本辅助逻辑 | `python -m pytest -q` |
| Android 引擎与问答 | `cd android && ./gradlew testDebugUnitTest` |
| Android 构建/Manifest/资源 | `cd android && ./gradlew assembleDebug` |
| macOS SwiftUI App | `cd macos/TraceMemoAutoReplyApp && swift test` |
| macOS App 打包 | `bash scripts/build-macos-app.sh` |
| Python 语法快速检查 | `python -m compileall -q core server macos scripts ios/appium` |

完成声明必须写清实际运行了哪些命令和结果。没有真机、微信、TraceMemo、真实模型凭据或 macOS 权限时，只能声称静态/单元/构建验证，不能声称端到端发送成功。

## 8. 文档维护

- `README.md` 面向使用者与贡献者；`新手指南.md` 面向非技术用户。
- `docs/` 保存平台部署、运行限制和专项说明。
- `AGENTS.md` 只放每次任务都适用的仓库级规则，避免膨胀成源码百科。
- 根 `MEMORY.md` 是模块索引；模块 `MEMORY.md` 保存稳定事实与修改约束，并链接到真实源码。
- 不在长期文档中硬编码测试数量；数量会随代码变动，需时以测试命令输出为准。
