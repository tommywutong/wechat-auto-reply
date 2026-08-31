# iOS 参考路线

iOS 沙盒不允许普通第三方 App 读取或控制微信。本目录因此提供的是自动化和注入参考，不是可直接提交 App Store 的应用。

## 路线一：Appium + WebDriverAgent

目录：[`appium/`](appium/)

脚本通过 WDA 操作前台微信界面，并把读到的消息交给本地 HTTP 决策服务。它不要求越狱，但需要 Mac/设备连接、开发者签名、微信常驻前台和稳定的 UI 选择器。

```bash
python ios/appium/wechat_ios_bot.py --dry-run
```

完整环境步骤见 [`appium/README.md`](appium/README.md)。

## 路线二：Theos tweak

目录：[`tweak/`](tweak/)

通过 hook 微信内部类获取消息与调用发送方法。它需要越狱，或对微信重签并注入动态库；每次微信更新都可能需要重新定位类和方法。

完整构建与适配说明见 [`tweak/README.md`](tweak/README.md)。

## 推荐替代方案

对普通 iPhone 用户，推荐让同账号的 macOS 微信代为回复。这样不修改 iPhone、不要求越狱，也不长期占用手机前台。

## 路线三：Objective-C 控制端

目录：[`companion/`](companion/)

这是一个普通的 UIKit App，只控制 Mac 上的服务状态、日志和安全配置。它不读取微信，不能
替代 Mac 端的 TraceMemo 轮询器和微信发送器。构建与局域网配对步骤见
[`companion/README.md`](companion/README.md)。

从仓库根目录执行 `bash scripts/build-ios-companion.sh` 可生成模拟器包，并在签名条件具备时
导出 iPhone 用的 `dist/TraceMemoRemote.ipa`。

路线比较、限制和风险见 [`../docs/ios-feasibility.md`](../docs/ios-feasibility.md)。Agent 修改本模块前应读取 [`MEMORY.md`](MEMORY.md)。
