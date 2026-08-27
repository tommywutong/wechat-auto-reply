# Android 模块记忆

## 何时读取

任务涉及 Android UI、通知监听、RemoteInput、无障碍兜底、快捷开关、内嵌 Kotlin 引擎、SharedPreferences、Android AI writer 或问答时读取本文件。

## 模块定位

Android App 是独立部署端。常规模式不调用 Python 服务，而是在 APK 内运行 Kotlin 决策引擎。

```text
微信通知 -> NotificationListener -> Kotlin ReplyEngine -> RemoteInput
                    \-> 无回复入口时可由 AccessibilityService 兜底
```

## 平台入口

| 文件 | 责任 |
|---|---|
| `app/src/main/AndroidManifest.xml` | Activity、通知监听、Tile、无障碍服务声明 |
| `MainActivity.kt` | 设置、运行状态、事件和预览 |
| `SetupWizardActivity.kt` | 首次问答界面 |
| `WeChatNotificationService.kt` | 主路径：解析通知、决策、等待、RemoteInput 发送 |
| `WeChatAccessibilityService.kt` | 兜底：读取前台微信 UI 并输入发送 |
| `QuickToggleTileService.kt` | 通知栏快捷开关 |

## 引擎入口

`app/src/main/java/com/wxauto/reply/engine/`：

- `Models.kt`：消息、决策、规则、人设和配置。
- `ReplyEngine.kt`：安全判断、范围、限流、规则、延迟与提交。
- `Storage.kt`：配置/状态/事件持久化和 writer 构建。
- `EngineHolder.kt`：复用引擎与 AI 记忆，设置变化时重建。
- `AiWriter.kt`：OpenAI 兼容与中继调用、提示词、输出清洗。
- `ConversationMemory.kt`：按会话短期上下文。
- `SetupWizard.kt`：问答定义与配置映射。

## 不变量

- 通知监听是主路径，无障碍是高权限兜底，不要颠倒默认关系。
- 通知监听与无障碍服务的 `exported` 要求不同，不能机械统一。
- 引擎判断和模型调用不阻塞通知回调或主线程。
- 延迟结束后必须重新读取总开关。
- 通知 action 失效、微信离开前台、控件找不到或点击失败时记录“未发送”。
- AI writer 复用以保留会话记忆，但 key 不得泄露凭据。
- 共享判断语义变化时同步检查 `../core/MEMORY.md`。

## 影响面

- 新配置字段：检查 `Models.kt`、`Storage.kt`、UI、wizard、测试及 Python 端。
- 通知解析：覆盖私聊/群聊识别、正文截断、无 RemoteInput 和系统字段缺失。
- 最低 API 变化：检查所有平台 API 调用和 Manifest 行为。
- provider 变化：检查 preset、endpoint、凭据存储、错误解释与 writer key。

## 验证

```bash
cd android
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

JVM 测试和 APK 构建不能证明真实微信通知、定制 ROM 或无障碍控件兼容。

## 继续阅读

- 开发者说明：[`README.md`](README.md)
- Android 专项：[`../docs/android-setup.md`](../docs/android-setup.md)
- Python 对等语义：[`../core/MEMORY.md`](../core/MEMORY.md)
