# TraceMemo AutoReply macOS App

这是一个原生 SwiftUI 控制面板，用来管理本仓库的本地微信自动回复服务。它把状态、会话白名单、设置和日志集中到一个窗口中，但不替代 TraceMemo、Python 决策引擎或微信发送器。

## 构建与测试

在仓库根目录运行：

```bash
cd macos/TraceMemoAutoReplyApp && swift test
cd ../..
bash scripts/build-macos-app.sh
open "dist/TraceMemo 自动回复.app"
```

打开 App 属于本机 UI 操作；自动化环境不应在未经允许时执行最后一条命令。

## 代码结构

- `Package.swift`：Swift Package 定义，macOS 13+。
- `Sources/TraceMemoAutoReplyApp.swift`：应用入口、模型、服务控制、配置桥接和视图。
- `Tests/SessionMatchingTests.swift`：稳定会话与名称匹配。
- `Tests/LogFormatterTests.swift`：日志格式化与展示行为。
- `Resources/Info.plist`：打包元数据。

## 外部协作

App 通过仓库脚本完成配置和会话读取：

- `scripts/app_config.py`
- `scripts/tracememo_contacts.py`
- `scripts/install-tracememo-autoreply.sh`
- `scripts/build-macos-app.sh`

设置写入本机 `core/config.yaml` 和 `var/poll-interval`。Token 保持在 Keychain 或受保护的兼容路径中，不进入 SwiftUI 状态。

## 设计要求

界面优先展示服务是否安全运行，再展示设置；使用原生控件、系统字体和文字化状态，不使用营销式布局或暴露秘密。详见：

- [`../../PRODUCT.md`](../../PRODUCT.md)
- [`../../DESIGN.md`](../../DESIGN.md)
- [`../../docs/macos-app.md`](../../docs/macos-app.md)

Agent 修改本模块前应读取 [`MEMORY.md`](MEMORY.md)。
