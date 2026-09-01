# Android 客户端

Android 客户端把回复引擎完整内嵌到 APK 中。安装后不需要 Python、电脑或局域网服务；用户授予通知使用权后，App 可通过微信通知自带的 `RemoteInput` 回复入口发送文字。

## 要求

- 最低 Android 8.0（API 26）。
- compile/target SDK 34。
- Java/Kotlin JVM 17。

版本和依赖以 [`app/build.gradle.kts`](app/build.gradle.kts) 为准。

## 两条发送路径

### 通知监听

[`WeChatNotificationService.kt`](app/src/main/java/com/wxauto/reply/WeChatNotificationService.kt) 是默认主路径。它读取微信通知、寻找回复 action、调用内嵌引擎，并在安全延迟后通过 `RemoteInput` 请求发送。此路径不需要打开微信、不会抢占屏幕；`PendingIntent.send()` 只能确认系统接收了发送请求，不能证明对方已收到。

限制包括免打扰会话不可见、通知正文可能截断，以及部分 ROM 移除回复 action。

### 无障碍兜底

[`WeChatAccessibilityService.kt`](app/src/main/java/com/wxauto/reply/WeChatAccessibilityService.kt) 在前台微信页面读取气泡并操作输入框。它需要高权限，且控件 ID 会随微信版本变化，因此不应作为默认方案。

## 内嵌引擎

`app/src/main/java/com/wxauto/reply/engine/` 包含 Kotlin 版安全判断、限流、规则、人设、AI writer、会话记忆、配置存储和问答。它与 Python 版共享行为目标但不共享运行时代码。

AI 模式还支持 Grok 4.1 风格预设和按会话的本地语气画像：Mac 可将已脱敏的画像导出为 JSON，再由 Android 设置页导入。Android 只保存显示名、统计摘要和最多 48 组裁剪样例；每次请求只取当前消息最相关的 3 组，不保存微信 ID、Token 或完整聊天记录。

Android 仍以通知文字为输入，不保证可靠识别图片、表情包或长消息附件。这些媒体能力属于 macOS + TraceMemo 链路，不能把它当成 Android 的等价功能。

## 构建和测试

```bash
cd android
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

CI 配置位于 [`../.github/workflows/build-apk.yml`](../.github/workflows/build-apk.yml)，先运行单元测试再构建 APK。

## 深入阅读

- [`../docs/android-setup.md`](../docs/android-setup.md)
- [`MEMORY.md`](MEMORY.md)（agent 修改约束）
- [`../core/README.md`](../core/README.md)（Python 对等实现）
