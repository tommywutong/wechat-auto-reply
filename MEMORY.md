# 项目记忆路由

本文件只负责把 agent 导向当前任务需要的模块知识。先读 [`AGENTS.md`](AGENTS.md)，
默认只选择一个模块；需要跨模块修改时再增加对应记忆。

## 阅读顺序

```text
AGENTS.md
  -> 本文件选择模块
  -> <module>/MEMORY.md
  -> <module>/README.md（需要开发背景时）
  -> 模块记忆指定的源码、测试或专项文档
```

源码与测试高于记忆。发现模块记忆过期时，在同一改动中更新它。

## 模块索引

| 模块 | Agent 记忆 | 开发者说明 | 负责内容 |
|---|---|---|---|
| Python 核心 | [`core/MEMORY.md`](core/MEMORY.md) | [`core/README.md`](core/README.md) | 配置、决策、安全、限流、人设、模型、问答 |
| HTTP 服务 | [`server/MEMORY.md`](server/MEMORY.md) | [`server/README.md`](server/README.md) | FastAPI、鉴权、schema、热加载 |
| macOS 自动化 | [`macos/MEMORY.md`](macos/MEMORY.md) | [`macos/README.md`](macos/README.md) | TraceMemo、轮询、草稿、OCR 与微信发送 |
| macOS 控制 App | [`macos/TraceMemoAutoReplyApp/MEMORY.md`](macos/TraceMemoAutoReplyApp/MEMORY.md) | [`macos/TraceMemoAutoReplyApp/README.md`](macos/TraceMemoAutoReplyApp/README.md) | SwiftUI、服务控制、设置、会话和日志 |
| Android | [`android/MEMORY.md`](android/MEMORY.md) | [`android/README.md`](android/README.md) | 通知监听、无障碍兜底、Kotlin 内嵌引擎 |
| iOS 参考实现 | [`ios/MEMORY.md`](ios/MEMORY.md) | [`ios/README.md`](ios/README.md) | Appium/WDA、Theos tweak、能力边界 |
| 构建与部署脚本 | [`scripts/MEMORY.md`](scripts/MEMORY.md) | [`scripts/README.md`](scripts/README.md) | 安装、launchd、构建、配置/联系人桥接 |
| 文档体系 | [`docs/MEMORY.md`](docs/MEMORY.md) | [`docs/README.md`](docs/README.md) | 用户文档、部署、产品设计和计划 |

## 如何选择

- 规则为什么没回复、回复不安全、冷却或文案问题：读 `core/MEMORY.md`。
- HTTP 401、请求字段或 reload 问题：读 `server/MEMORY.md`。
- TraceMemo 读不到消息、重复轮询、草稿或发错会话风险：读 `macos/MEMORY.md`。
- 原生 Mac 界面、服务状态、设置保存或日志：读 macOS App 记忆。
- APK、通知、RemoteInput、无障碍或 Android AI：读 `android/MEMORY.md`。
- iPhone/WDA/越狱注入可行性：读 `ios/MEMORY.md`。
- 安装失败、LaunchAgent、Keychain 环境或打包：读 `scripts/MEMORY.md`。
- README、部署说明或能力表述：读 `docs/MEMORY.md`。

## 跨模块数据流

### macOS 推荐链路

```text
TraceMemo
  -> macos/tracememo_poller.py
  -> server/app.py
  -> core/ReplyEngine
  -> macos/wechat_sender.py
```

通常依次读取 `macos/MEMORY.md`、`server/MEMORY.md`、`core/MEMORY.md`；只改控制面板时不要加载这三份实现细节。

### Android 链路

```text
微信通知
  -> WeChatNotificationService
  -> Kotlin ReplyEngine
  -> RemoteInput
```

先读 `android/MEMORY.md`。只有共享决策语义或配置契约变化时，再读 `core/MEMORY.md`。

### 控制 App 链路

```text
SwiftUI App
  -> scripts/app_config.py / tracememo_contacts.py
  -> core/config.yaml / TraceMemo
  -> launchd services
```

先读 macOS App 记忆；涉及配置序列化或服务安装时，再读 `scripts/MEMORY.md` 和 `core/MEMORY.md`。

## 必须联动检查的契约

| 改动 | 需要增加读取的模块 |
|---|---|
| 安全顺序、限流、延迟、身份归一化 | `core` + `android` |
| 配置字段或默认值 | `core` + `android` + macOS App + `scripts` |
| HTTP schema | `server` + `macos` + `ios`，必要时 Android 中继 |
| TraceMemo 会话字段 | `macos` + `scripts` + macOS App |
| launchd 标签、日志路径、服务联动 | `scripts` + macOS App |
| 用户能力声明 | 实现模块 + `docs` |
| 凭据或日志 | 所有受影响模块，并复核根 `AGENTS.md` |

## 全局事实

- Python 与 Android Kotlin 是两份独立决策实现，行为目标一致但不共享代码。
- macOS 当前主链路使用 TraceMemo；`wechat_mac_bot.py` 是兼容路径。
- SwiftUI App 是控制面板，不保存 Token，也不实现回复规则。
- iOS 目录是自动化/注入参考，不是普通沙盒 App。
- `core/config.yaml`、`.wxauto_token`、`var/`、`.build/`、`dist/` 等是私人或生成内容。
- 单元测试、构建、模拟器、真机和真实发送是不同验证层级，不能互相替代。

## 维护原则

- 根文件保持短小，只放路由和跨模块契约。
- 模块记忆写 agent 必需的约束；模块 README 写开发者背景。
- 细节已有专项文档时使用链接，不复制成第二事实源。
- 不记录测试数量、当前联系人、真实凭据或未经验证的第三方状态。
