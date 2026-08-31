# TraceMemo iPhone 控制端

这是一个 Objective-C/UIKit 编写的 iPhone 控制端。它不读取或控制 iPhone 上的微信，
只通过局域网连接 Mac 上的 TraceMemo AutoReply 控制服务。

## 构建

需要 macOS、Xcode 15 或更高版本。仓库已提供 XcodeGen 工程描述：

```bash
cd ios/companion
xcodegen generate
xcodebuild -project TraceMemoRemote.xcodeproj \
  -scheme TraceMemoRemote \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  CODE_SIGNING_ALLOWED=NO build
```

真机运行需要在 Xcode 中选择自己的 Apple Developer Team 并签名。首版不需要推送证书，
打开 App 时主动刷新状态和日志。

## 配对

在 Mac 上执行：

```bash
bash scripts/install-tracememo-control.sh
```

命令会启动局域网控制服务，并打印 Mac `.local` 地址和 10 分钟有效的配对码。iPhone App
填写这个 `.local` 地址（也可填同一局域网的私有 IPv4 地址）、端口（默认 `8850`）和配对码，点击“连接并保存”。配对后的独立控制令牌
存入 iPhone Keychain，不会显示在界面或日志中。

首次访问时允许 iPhone 的“本地网络”权限；若 macOS 防火墙提示，则允许控制服务接收局域网连接。

## 能力边界

- 可以查看规则服务、自动回复服务和控制服务状态。
- 可以启动、停止、重启服务。
- 可以查看经过脱敏的最近日志。
- 可以编辑轮询间隔、私信白名单和回复风格说明。
- TraceMemo、AI 请求和微信发送仍在 Mac 上运行，Mac 关机时 iPhone 不能独立回复微信。

这是本地控制工具，不是微信插件，也不绕过 iOS 沙盒或微信安全机制。
