# iOS 免越狱方案：Appium + WebDriverAgent

这条路不需要越狱，但需要一台 Mac 和一台可以被占用的 iPhone。
原理和限制见 [`docs/ios-feasibility.md`](../../docs/ios-feasibility.md) 路线 A。

## 一、装环境（在 Mac 上）

```bash
# 1. Xcode + 命令行工具
xcode-select --install

# 2. Appium 和 iOS driver
npm install -g appium
appium driver install xcuitest

# 3. 设备工具链
brew install libimobiledevice ios-deploy

# 4. Python 依赖
pip install -r ios/appium/requirements.txt
```

## 二、把 WebDriverAgent 跑到手机上

这是整条链路里最容易卡住的一步。WebDriverAgent 是一个需要用**你自己的
开发者证书**签名的测试 App。

```bash
# 找到 WDA 工程
cd ~/.appium/node_modules/appium-xcuitest-driver/node_modules/appium-webdriveragent
open WebDriverAgent.xcodeproj
```

在 Xcode 里：

1. 选中 `WebDriverAgentRunner` target → Signing & Capabilities
2. 勾上 **Automatically manage signing**，Team 选你的 Apple ID
3. Bundle Identifier 改成一个全球唯一的，比如 `com.yourname.WebDriverAgentRunner`
4. 手机连上 Mac，选中你的设备，`Product → Test`（⌘U）

手机上会装出一个白图标的 App。第一次运行时手机会提示"不受信任的开发者"，
去 **设置 → 通用 → VPN与设备管理** 里信任你的证书。

> **免费 Apple ID 的证书 7 天过期**，过期后要重新 `Product → Test`。
> 付费开发者账号（$99/年）是 1 年。

## 三、启动

三个终端窗口：

```bash
# 终端 1：规则服务
export WXAUTO_CONFIG=core/config.example.yaml
export WXAUTO_TOKEN=$(openssl rand -hex 16)   # 记下这个值
uvicorn server.app:app --port 8848

# 终端 2：Appium
appium

# 终端 3：机器人
export IOS_UDID=$(idevice_id -l | head -1)
export WXAUTO_SERVER=http://127.0.0.1:8848
export WXAUTO_TOKEN=<终端 1 里那个值>

# 先干跑，只打印不发送 —— 强烈建议先跑几轮确认没问题
python ios/appium/wechat_ios_bot.py --dry-run

# 确认无误后再真发
python ios/appium/wechat_ios_bot.py
```

手机上手动打开微信，停在会话列表页，然后别动它。

## 四、常见问题

**「找不到「微信」tab」**
微信没在前台，或系统语言不是简体中文。改 `wechat_ios_bot.py` 顶部的
`SELECTORS` 字典。

**「连接设备失败」**
按顺序查：手机是否解锁、是否信任了这台 Mac（`idevicepair validate`）、
WDA 是否还在手机上跑（证书没过期）。

**扫不到未读会话**
微信改版后 cell 结构可能变了。用 Appium Inspector 看一眼实际的控件树：

```bash
npm install -g appium-inspector
```

连上后能可视化看到每个元素的 label / class / 坐标，对着改
`list_unread_chats()` 里的定位逻辑。

**发出去了但内容是乱的**
`send_keys` 对中文输入法有时会丢字。可以改成用剪贴板：先
`pbcopy` 再模拟 ⌘V。这条路径在不同 iOS 版本上表现不一，需要实测。

## 五、这条路的天花板

- **锁屏就停**。iOS 不允许后台持续做 UI 自动化。
- **只能读文本**。图片、语音、文件、转账卡片都读不出内容——不过引擎
  本来也不会自动回这些。
- **微信必须前台**。这台手机基本没法同时干别的。

如果这几条你接受不了，看 [`docs/ios-feasibility.md`](../../docs/ios-feasibility.md)
的路线 B（注入插件）或路线 C（macOS 代打）。
