# iOS 注入式插件（Theos Tweak）

字面意义上的「微信插件」：把 dylib 注入微信进程，直接 hook 收发消息的方法。
功能最完整、后台常驻、不占用手机。代价是需要越狱或重签名。

原理和取舍见 [`docs/ios-feasibility.md`](../../docs/ios-feasibility.md) 路线 B。

## 一、装 Theos

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/theos/theos/master/bin/install-theos)"
export THEOS=~/theos
```

## 二、改配置

打开 `Tweak.x`，改这两行：

```objc
static NSString *const kEngineURL = @"http://192.168.1.10:8848/reply";  // 规则服务地址
static NSString *const kEngineToken = @"CHANGE_ME";                      // 和 WXAUTO_TOKEN 一致
```

手机和跑规则服务的机器要在同一局域网。

## 三、编译安装

### 越狱机

```bash
cd ios/tweak

# 生成 deb
make package FINALPACKAGE=1

# 直接装到设备（先设好 SSH）
export THEOS_DEVICE_IP=192.168.1.20
make do
```

装完微信会自动重启。看日志确认加载成功：

```bash
ssh root@$THEOS_DEVICE_IP 'tail -f /var/log/syslog' | grep WXAutoReply
# 应该看到：[WXAutoReply] 已加载，enabled=1，引擎 http://...
```

### 未越狱机（重签名 + 注入）

思路是把编译出的 dylib 塞进微信 IPA，再用你的证书重签名侧载。
需要 `insert_dylib` 或 Sideloadly 这类工具。这条路各家工具差异较大，
且随 iOS 版本变化，这里不写具体步骤——网上按 "iOS 微信 IPA 注入 dylib"
能找到当前有效的做法。

注意：重签名后的微信会覆盖 App Store 版本，且证书过期后要重签。

## 四、适配新版微信（重要）

`Tweak.x` 里的方法签名来自微信 iOS 8.0.x。**微信改版后签名可能变化，
hook 会静默失效——不崩溃，就是什么都不发生。**

确认签名是否还有效：

```bash
# 方法 1：Frida（越狱机，推荐）
frida -U -n WeChat -e '
  ObjC.classes.CMessageMgr.$ownMethods
    .filter(m => m.includes("AddMsg") || m.includes("SendText"))
    .forEach(m => console.log(m));
'

# 方法 2：class-dump（拿到脱壳后的二进制）
class-dump -H WeChat -o headers/
grep -rn "AsyncOnAddMsg\|SendTextMessage" headers/CMessageMgr.h
```

对照输出改 `Tweak.x` 里的 `%hook` 方法名和 `@interface` 声明即可。
需要确认的有三处：

| 用途 | 当前假设的签名 |
|---|---|
| 收消息 | `-[CMessageMgr AsyncOnAddMsg:MsgWrap:]` |
| 发消息 | `-[CMessageMgr SendTextMessage:toUsr:msgText:]` |
| 取自己 | `-[CContactMgr getSelfContact]` |

## 五、临时关掉

不想卸载但要暂停时：

```bash
# 在设备上
defaults write com.tencent.xin WXAutoReplyEnabled -bool NO
killall WeChat
```

## 六、注意

- 这个插件运行在微信进程里，**能看到你所有的消息**。只装你自己编译的版本，
  不要装来路不明的 deb。
- 消息处理跑在微信的消息线程上，所以网络请求是异步的（`AskEngine` 用的是
  `NSURLSession` 回调）。**不要改成同步请求**，会卡死微信 UI。
- 只 hook 了纯文本消息（`m_uiMessageType == 1`）。图片、语音、红包、转账
  一律不处理，这是有意为之。
