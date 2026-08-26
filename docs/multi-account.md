# 跑多个微信号 / 多个端

限流和去重是按**账号**隔离的，不是按平台。这两件事必须分清楚，
否则要么重复回复，要么该回的被误杀。

## 先确定你属于哪种情况

| 你的情况 | 怎么配 | 效果 |
|---|---|---|
| **两个不同的微信号**，各跑一端 | 两端填**不同**的 `account`（或都留空） | 各算各的额度，互不影响 |
| **同一个微信号**，手机和电脑同时登录 | 两端填**相同**的 `account` | 共享冷却，同一条消息只回一次 |
| 只跑一端 | 不用管 | — |

留空时会回退成平台名（`android` / `macos` / `ios`），也就是**默认按平台隔离**。
对「两个号各跑一端」这种最常见的配置，默认值就是对的，不用额外配置。

## 为什么不能用平台代替账号

平台和账号是两个维度：

- 同一个号可以登录在多个平台上 → 需要**合并**额度，否则重复回复
- 不同的号可以跑在不同平台上 → 需要**隔离**额度，否则误杀

只看平台的话，两个号里都有个叫「小王」的联系人，就会被当成同一个会话——
B 号该回的消息因为 A 号刚回过而被跳过，而且日志里写的是「跨端去重」，
排查时极具误导性。

所以身份键是三段式的：`账号 | 会话类型 : 归一化会话名`。

## 怎么填

### macOS

```bash
export WXAUTO_ACCOUNT=私人号
python macos/wechat_mac_bot.py
```

### Android

App 配置页第三个输入框「微信号标识」，填 `工作号` 之类。改完需要到
「通知使用权」里关掉再打开本应用才会生效。

### iOS

- Appium：`export WXAUTO_ACCOUNT=...`
- Tweak：改 `Tweak.x` 顶部的 `kAccount` 常量后重新编译

值本身没有意义，只要**同一个号在各端填的字符串一致**、不同号之间不同即可。

## 部署拓扑

两个号可以共用一个规则服务——账号隔离是在服务端做的：

```
        ┌─────────── Mac（常开）───────────┐
        │  uvicorn server.app:app :8848    │  ← 规则服务，两个号共用
        │  wechat_mac_bot.py               │  ← WXAUTO_ACCOUNT=私人号
        └──────────────┬───────────────────┘
                       │ 局域网 http://192.168.1.10:8848
                ┌──────┴──────┐
                │ Android App │  ← 微信号标识 = 工作号
                └─────────────┘
```

Mac 上起服务时注意用 `--host 0.0.0.0`，默认的 `127.0.0.1` 手机连不上：

```bash
export WXAUTO_CONFIG=core/config.yaml
export WXAUTO_TOKEN=$(openssl rand -hex 16)   # 两端填同一个
uvicorn server.app:app --host 0.0.0.0 --port 8848
```

先在手机浏览器访问 `http://192.168.1.10:8848/health` 确认通不通。

## 目前的限制：规则是全局的

**两个账号共用同一份规则、同一套文案。** 如果你想让工作号和私人号
回不同的内容（大概率是想的），现在有两个办法：

1. **起两个服务**，各用各的配置文件和端口：

   ```bash
   WXAUTO_CONFIG=core/work.yaml   WXAUTO_STATE=var/work.json   uvicorn server.app:app --port 8848
   WXAUTO_CONFIG=core/personal.yaml WXAUTO_STATE=var/personal.json uvicorn server.app:app --port 8849
   ```

   两端各连各的。缺点是要维护两份配置、两个进程。

2. **用 `allow_contacts` 变相区分**——只有当两个号的联系人完全不重叠时才有效，
   通常不好用。

引擎本身支持「一个服务承载多个账号各自的规则」，只是配置格式还没做。
需要的话可以加成这样：

```yaml
accounts:
  工作号:
    signature: "（工作时间外自动回复）"
    rules: [...]
  私人号:
    rules: [...]
defaults:        # 没匹配到账号时用这套
  rules: [...]
```

## 让 Mac 上的服务开机自启

存成 `~/Library/LaunchAgents/com.wxauto.server.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.wxauto.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>server.app:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8848</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/你的用户名/path/to/repo</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>WXAUTO_CONFIG</key>
        <string>core/config.yaml</string>
        <key>WXAUTO_TOKEN</key>
        <string>你的token</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/wxauto.err.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.wxauto.server.plist
```

> `wechat_mac_bot.py` 不建议这样自启——它需要辅助功能权限，
> launchd 拉起的进程权限归属容易出问题。手动在终端里跑更省心。

## 排查

**对方收到了两条一样的回复**
同一个号的两端 `account` 填的不一样。统一成同一个字符串。

**某个号一条都不回，日志写「跨端去重」**
两个不同的号填了相同的 `account`，被当成同一个号了。改成不同的值。

**日志里分不清是哪个号**
回复日志格式是 `[账号/平台] 会话名 -> 内容 (原因)`，例如
`[工作号/android] 小王 -> 在的…（自动回复）(命中规则 '打招呼')`。

**改了 account 之后冷却计数不对**
状态文件里的键包含账号名，改名等于换了个新会话。删掉
`var/state.json` 重来即可，代价只是冷却计数清零。
