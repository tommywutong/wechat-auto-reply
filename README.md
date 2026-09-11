# 微信自动回复

[![编译安卓 APK](https://github.com/tommywutong/wechat-auto-reply/actions/workflows/build-apk.yml/badge.svg)](https://github.com/tommywutong/wechat-auto-reply/actions/workflows/build-apk.yml)
![平台](https://img.shields.io/badge/平台-Android%20%7C%20macOS%20%7C%20iOS-lightgrey)
![测试](https://img.shields.io/badge/测试-194%20passed-brightgreen)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

基于大语言模型的微信自动回复：把**身份、语气和应对原则**交给模型实时生成回复，而不是匹配关键词。

- **非技术用户** → 先看 [新手指南.md](新手指南.md)（图文步骤）
- **开发者 / 二次开发** → 继续读本文
- **只想装 Android APK** → [下载最新构建](https://github.com/tommywutong/wechat-auto-reply/releases/latest/download/wechat-auto-reply.apk)

---

## 这是什么

常见自动回复靠关键词库，对话稍变就露馅。本项目把「判断依据」写进人设配置，具体措辞由模型在消息到达时生成：

```
对方：明天下午有空不，一起吃个饭
回复：我看下日程，晚点回你

对方：那个东西弄得怎么样了
回复：在弄了，这两天给你结果

对方：帮我转账 500
（不回复——命中敏感词，移交人工处理）
```

配置里并没有上述问答对，回复均为实时生成。

| 端 | 能做什么 | 要不要电脑 |
|---|---|---|
| **Android** | 手机独立运行；通知监听收消息，APK 内嵌决策引擎 | 否 |
| **macOS** | 读本机 TraceMemo 聊天库 + 操作 Mac 微信窗口发送；自带 SwiftUI 控制面板 | 是（常开） |
| **iPhone 遥控** | 局域网查看/控制 Mac 上的服务状态、日志、白名单 | 依赖 Mac 在跑 |

iPhone 用户推荐 macOS 方案：微信手机与桌面同号同消息，Mac 回复等效于本人在 iPhone 回复，无需越狱。

---

## 效果预览

<!-- 将录屏导出为 docs/assets/demo.gif（≤5MB，宽约 1200px）并取消注释
![demo](docs/assets/demo.gif)
-->

macOS 控制面板与回复效果演示图可放在 `docs/assets/`，在此引用。

---

## 快速开始

### Android（最快上手）

手机浏览器打开（微信内置浏览器会拦截下载，请用系统浏览器）：

```text
https://github.com/tommywutong/wechat-auto-reply/releases/latest/download/wechat-auto-reply.apk
```

1. 安装后完成十题配置引导（约一分钟）
2. 授予通知使用权
3. 打开主开关

启用 AI 时在「怎么回」选 AI 模式，并二选一：

- **自有 API Key**（推荐）— 设置页点厂商按钮自动填接口与模型名，粘贴 Key 即可
- **接入他人服务** — 填对方地址与令牌（消息会经对方服务器）

要求：Android 8.0（API 26）+。

### macOS（控制 App 一跳进入）

没有可双击的签名安装包，需从源码初始化。完整链路：

`TraceMemo Reader → 本地规则服务 → 自动回复轮询器 → Mac 微信界面`

**要求**：macOS 13+、Python 3.9+、Xcode CLT、已登录 Mac 版微信。TraceMemo **不必单独安装**，首次启动会自动准备 Reader 并复用本机已有数据；若从未连过微信库，需先用 TraceMemo 连接一次。

```bash
git clone https://github.com/tommywutong/wechat-auto-reply.git
cd wechat-auto-reply
bash scripts/macos-setup.sh          # 或双击「安装到Mac.command」
bash scripts/run-macos-app.sh        # 打开控制面板
```

**凭据写入 Keychain**（输入不回显，不写进项目文件）：

```bash
security add-generic-password -U -a "$USER" -s com.wxauto.tracememo-api-token -w
security add-generic-password -U -a "$USER" -s com.wxauto.deepseek-api-key -w
```

**系统权限**（系统设置 → 隐私与安全性）：

- 辅助功能 — 读取/操作微信窗口  
- 屏幕录制 — 截取微信窗口做 OCR 与发送前确认  

授权后重启控制 App。

**先试跑，再真发**（项目根目录）：

```bash
"./1 检查微信.command"                 # 只诊断界面
"./2 试运行（不真发消息）.command"      # 出决策与草稿，不按发送
"./3 开始自动回复.command"              # 确认无误后再开
```

也可在控制 App 概览页直接启停。默认跳过停机期间的旧消息；需要追补时打开「启动时追补停机消息」。

更完整的面板说明、自动更新与故障排查：[docs/macos-app.md](docs/macos-app.md)。

---

## 核心特性

| 特性 | 说明 |
|---|---|
| **人设驱动生成** | 基于身份、语气、应对攻略生成回复，非关键词匹配 |
| **Grok 风格预设** | macOS / Android 可选直接、坦率、适度幽默（实验）；只改表达，不改安全边界 |
| **会话语气画像** | Mac 本地提取，可脱敏导入 Android；按当前消息只取少量相关历史 |
| **引导式配置** | 十道选择题生成完整人设，不必手写提示词 |
| **双模式** | AI 生成 / 本地关键词（后者完全离线） |
| **多模型** | 豆包、DeepSeek、通义千问、智谱 GLM、Moonshot、Claude |
| **安全前置** | 敏感词、黑名单、限流在调用模型之前执行 |
| **上下文记忆** | 每会话最近 8 轮、1 小时，仅存内存 |
| **一键开关** | Android 通知栏快捷开关 |
| **零服务依赖** | Android 引擎内嵌 APK，无需服务器 |

---

## macOS 控制 App

原生 SwiftUI 面板：管理自动回复服务、白名单、轮询与实时日志。**不保存、不展示 API Token**，凭据只在 Keychain。

- **会话列表**：从 TraceMemo 导入联系人与群聊，默认最近活跃共 30 条；公众号不进列表，其余可搜。开关按稳定会话 ID，兼容旧名称白名单。
- **服务管理**：概览页启动 / 停止 / 重启 / 保存设置会同时处理规则服务与自动回复服务。
- **发送定位**：优先左侧会话列表；私信严格匹配，群聊容错搜索，最后用右侧完整标题复核。
- **自动更新**：启动或再次点 Dock 图标时检查远端 `main`。工作区干净且可安全快进则拉取、重建并切换；本地有未提交改动、分支分叉或网络异常则跳过。**不会**强杀正在跑的后台服务——需要加载新代码时，在概览里点一次「重启服务」。关窗口不退出进程，再点 Dock 即可回到面板。

旧的纯终端 `run-mac-bot.sh` 仍保留作兼容；新安装优先走上面的控制 App 流程。

---

## 人设配置

人设决定像不像本人。系统提供引导式问答，把十项选择映射为完整配置：

```bash
python3 -m core.wizard     # 重新生成配置
python3 -m core.preview    # 交互式预览，不发送
```

同一套问答也覆盖关键词规则，两种模式语气一致；Android 端内置相同逻辑，题目顺序由单测约束保持两端一致。

配置可直接改：

```yaml
reply_mode: ai              # ai | rules | rules_then_ai

persona:
  identity: |
    我是做独立开发的，白天基本埋在代码里，微信经常隔一两个小时才翻一次。

  tone: |
    句子短，口语，不用敬语，不说「您」，不用感叹号。

  playbook: |
    有人约时间：一律说要确认日程，等我本人回，不要当场答应。
    有人问进度：给个模糊的时间感觉，不给具体日期，不打包票。
    看不懂或事情重要：直接说等我本人回你，不要硬猜着接话。

  boundaries: ["不谈具体报价", "不评价第三方"]
  max_chars: 35

  examples:                 # 示范语气，模型据此模仿
    - {them: "在吗", me: "在，怎么了"}
```

字段说明见 [`core/config.ai.example.yaml`](core/config.ai.example.yaml)。  
Grok 风格来源与许可见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

---

## 模型服务

| provider | 服务商 | 凭据环境变量 |
|---|---|---|
| `doubao` | 豆包（火山方舟） | `ARK_API_KEY` |
| `deepseek` | DeepSeek | `DEEPSEEK_API_KEY` |
| `qwen` | 通义千问 | `DASHSCOPE_API_KEY` |
| `zhipu` | 智谱 GLM | `ZHIPU_API_KEY` |
| `moonshot` | Moonshot | `MOONSHOT_API_KEY` |
| `anthropic` | Claude | `ANTHROPIC_API_KEY` |

默认豆包：这里要的是自然中文口语，不是复杂推理；国内网络可直连。前五家为 OpenAI 兼容接口，标准库实现、无三方依赖；仅 `anthropic` 需装 SDK。`model` 与 `base_url` 留空则用服务商默认。

> 火山方舟 `model` 可填模型 ID（如 `doubao-seed-1-6-251015`）或接入点 ID（`ep-` 前缀）。模型 ID 带版本日期，若报模型不存在，请从控制台复制当前有效值。

---

## 安全机制

自动回复的主要风险不是漏回，而是**回错**。下列约束不可通过配置关闭。

**敏感消息拦截。** 转账、红包、验证码、银行卡、身份证、密码、借钱、急用钱、汇款、付款码等一律不回复。该判断在所有频率逻辑之前；冷却为 0、规则全匹配也拦得住。AI 模式下此类消息不会发给模型。

**决策顺序固定。**

```text
主开关 → 空消息 → 敏感词 → 黑名单 → 屏蔽词 → 白名单
→ 会话类型 → 时段 → 跨端去重 → 频率限制 → [AI 生成 | 关键词规则] → 兜底
```

模型只决定「怎么表述」，不决定「该不该回」——后者交给确定性规则。

**四层限流。** 单会话冷却（默认 30 分钟）、单会话日上限、全局小时上限、全局日上限。后两层是熔断，防配置失误刷屏。

**跨会话最小间隔（默认 45 秒）。** 按会话冷却挡不住「多人几乎同时来消息、几十秒内逐一回完」——这是最像机器人的特征。命中时顺延发送时刻而非丢弃，回复因此依次排开。

**发送延迟 = 三段。** 基础随机延迟（默认 3–12 秒）+ 按字数估的输入耗时（默认 0.12 秒/字）+ 上述跨会话间隔。固定延迟会让长短回复耗时一样，反而假。

**文案轮换按全局计数。** 若按会话独立计数，每个联系人收到的都是第一条——批量相同内容是典型风控信号。

**回复标识。** 可选尾注；Android 新配置默认空，不强制暴露自动化。

**失败静默。** 接口异常、生成失败、读取失败一律不回复；AI 失败**不会**退回关键词文案，避免语气突变。

**联系人白名单。** `scope.allow_contacts` 非空时只回名单内。这是**最有效的风控手段**：被举报才是账号受限主路径，熟人一般不会举报。配置问答最后一题即此项。

**账号隔离。** 限流键为「账号 + 会话类型 + 归一化会话名」。多账号各算各的；同号多端配置相同 `account` 可共享冷却并去重。详见 [docs/multi-account.md](docs/multi-account.md)。

---

## 系统架构

```text
┌──────────────┐     ┌─────────────────────┐     ┌──────────────┐
│  消息采集     │ ──▶ │      决策引擎        │ ──▶ │   回复发送    │
│              │     │                     │     │              │
│ Android 通知  │     │ 安全检查 → 频率限制  │     │ RemoteInput  │
│ macOS 辅助功能│     │ → AI 生成 / 规则匹配 │     │ 辅助功能操作  │
└──────────────┘     └─────────────────────┘     └──────────────┘
```

决策引擎有 Python 与 Kotlin 两份实现：Android 无法方便地跑 Python 服务，也不该要求用户装 Termux，因此完整移植进 APK。两份实现的决策顺序必须一致，单测各自约束。

```text
core/                 决策引擎（Python），109 项测试
  engine.py             决策主流程
  wizard.py             引导式配置问答
  persona.py            人设建模、对话记忆、提示词构造
  providers.py          模型服务注册表
  llm_openai.py         OpenAI 兼容调用（标准库）
  llm.py                Anthropic SDK 调用
  preview.py            交互式预览
  config.py             配置解析与校验
server/app.py         HTTP 服务（FastAPI），供 macOS 与中继
android/              Android 客户端（Kotlin），76 项测试
  engine/               引擎、问答、模型调用的 Kotlin 实现
macos/                macOS 采集端与 TraceMemo 轮询器
ios/                  iOS 参考实现（见下）
docs/                 部署、多账号、iOS 可行性
```

### 关于 iOS

未越狱 iOS 无法由第三方 App 读/写其他 App 的消息（沙盒限制）。仓库提供三种参考：

| 方案 | 越狱 | 可用性 | 路径 |
|---|---|---|---|
| UI 自动化（Appium + WDA） | 否 | 微信需常驻前台 | [`ios/appium/`](ios/appium/) |
| 注入插件（Theos） | 是 | 完整 | [`ios/tweak/`](ios/tweak/) |
| **macOS 代理（推荐）** | 否 | 完整，不占手机 | [`macos/`](macos/) |

完整分析：[docs/ios-feasibility.md](docs/ios-feasibility.md)。

### iPhone 控制端

Objective-C/UIKit 遥控器：在 iPhone 上查看 Mac 服务状态、日志、白名单与部分设置，并远程启停。**不是**微信插件，不读 iPhone 微信，Mac 关机时也不能独立回复。

配对：Mac 先执行 `bash scripts/install-tracememo-control.sh`，把终端里的 Mac `.local` 地址与一次性配对码填进 iPhone App。控制服务使用独立令牌，不复用微信或模型密钥。说明见 [`ios/companion/README.md`](ios/companion/README.md)。

---

## 开发与测试

```bash
python -m pytest -q                          # 193 项
cd android && ./gradlew testDebugUnitTest     # 76 项
```

APK 由 GitHub Actions 构建，单测失败不产出制品；推送到 `main` 后自动更新 Release 下载地址。

---

## 已知限制

以下仅完成编译与逻辑验证，**尚未在真机跑通**：

- Android 通知拦截与 RemoteInput 发送的真实行为
- 各版本 / 定制 ROM 上微信通知正文格式解析
- macOS 辅助功能控件路径（微信改版可能失效，可用 `--doctor` 诊断调整）
- 模型接口已对照文档实现，未用真实凭据验证

固有限制：

- Android 只处理能产生通知的消息，免打扰会话不可见
- 通知正文可能被系统截断，超长消息读不全
- 部分定制 ROM 去掉了通知 RemoteInput，需开无障碍方案
- macOS 读取消息需展开会话，未读状态会被清除

---

## 免责声明

功能未经微信官方开放，请自行评估：

- **账号风险。** 自动化可能触发风控，导致限制或封号。内置限流与随机延迟只能降低概率，不构成保证。
- **权限范围。** 通知使用权、辅助功能授权范围较大。建议只装自己编译的，或从本仓库 Actions 拿构建。
- **数据流向。** AI 模式下，待回复消息与上下文会发给所选模型服务商；敏感词与黑名单在本地拦截，不会外发。关键词模式完全离线。
- **服务条款。** 行为可能违反微信用户协议。

建议初期只对少量熟识联系人开启，观察数日再扩大。本项目仅供学习与个人使用，后果自负。

---

## 致谢与本地依赖

早期跨平台思路与部分实现参考了 [taotao-river/wechat-auto-reply](https://github.com/taotao-river/wechat-auto-reply)，在此致谢。当前仓库独立维护，不继承其 Git 历史。

macOS 自动回复依赖 [TraceMemo](https://github.com/Wxw-Gu/TraceMemo) Reader：通过本机 HTTP API 读联系人、会话与聊天记录。消息留在本机，Token 只从 Keychain 读取。启动时会准备独立 Reader 运行时——已有 TraceMemo 数据则复用；未安装也会按固定版本下到用户目录，无需单独安装 App。首次仍需在 TraceMemo 完成一次微信数据库连接，或提供已连接好的本机数据目录。

---

## 许可证

本仓库源码采用 [MIT License](LICENSE)。第三方依赖与提示词风格参考见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
