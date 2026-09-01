# iPhone 控制端

`ios/companion` 是 Objective-C/UIKit 编写的 iPhone 控制端。它解决的是“人在外面时查看和
控制家里的 Mac 自动回复服务”，不是在 iPhone 上运行微信自动回复。

## 运行关系

```text
iPhone 控制端 ──局域网 Bearer 控制令牌──> Mac 控制服务 :8850
                                           ├─ launchd 规则服务 :8848
                                           ├─ TraceMemo Reader :6131
                                           └─ 微信界面发送器
```

Mac 必须保持开机、联网、微信登录，并且自动回复服务已经按原流程配置好。iPhone 断网、
Mac 睡眠或 Mac 服务停止时，控制端只会显示状态错误，不会尝试在 iPhone 上操作微信。

## Mac 端配对

在仓库根目录执行：

```bash
bash scripts/install-tracememo-control.sh
```

脚本会：

- 在 `var/` 生成本机控制令牌和 10 分钟有效的一次性配对码；这些文件已加入 `.gitignore`。
- 以 launchd 服务 `com.wxauto.tracememo-control` 启动局域网 API，默认端口 `8850`。
- 打印配对码。配对码只用于换取控制令牌，换取后会立即删除。

在 iPhone App 输入脚本显示的 Mac `.local` 地址（也可填同一局域网的私有 IPv4 地址）、端口和配对码，点击“连接并保存”。控制令牌进入 iPhone
Keychain；后续请求统一使用 `Authorization: Bearer`。不要把端口映射到公网，也不要把配对码
发给其他人。

首次连接时，iPhone 会请求“本地网络”权限。请允许；若 macOS 防火墙弹出入站连接提示，也要
允许本项目的 Python 控制服务接受局域网连接。

## 打包和安装

在仓库根目录运行 `bash scripts/build-ios-companion.sh`。脚本会生成模拟器包，并根据本机
Apple 开发者账号和 provisioning profile 是否可用，尝试导出 `dist/TraceMemoRemote.ipa`。
开发签名 IPA 只能安装到已注册的设备；没有签名条件时的 `.xcarchive` 仅供后续在 Xcode
中重新签名，不能直接安装。iOS 不允许像 APK 一样把一个未签名包直接发给任意手机。

## 当前能力

- 查看规则服务、自动回复服务和控制服务状态。
- 启动、停止、重启两个已有服务。
- 查看脱敏后的最近日志，不返回回复正文或完整联系人信息。
- 修改轮询间隔、私信白名单和回复风格说明；保存后 Mac 服务自动重启。

首版不包含 APNs 推送和后台持续连接。打开 App 时刷新，前台每 8 秒刷新一次，符合 iOS
后台执行限制。

## 安全边界

控制 API 与 `/reply` 使用不同令牌。控制端不会接触 DeepSeek、Qwen 或 TraceMemo Token，
也不会把 Mac 上的微信数据库复制到 iPhone。服务只适合可信的家庭/个人局域网。
