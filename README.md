# 微信自动回复

## macOS 控制 App

项目现在包含一个原生 SwiftUI 控制面板，可管理自动回复服务、白名单、轮询设置和
实时日志。它不会保存或显示 API Token，凭据仍从 macOS Keychain 读取。

在 macOS 上构建并打开：

```bash
bash scripts/run-macos-app.sh
```

控制 App 每次启动或再次点击 Dock 图标时会检查远端 `main`：本地工作区干净且能安全快进时，自动拉取代码、重建 App 并切换到新版本。检测到本地未提交修改、分支分叉或网络异常时会跳过更新，保留现有版本和本机配置。自动更新不会强行重启正在运行的后台服务；需要让服务加载新代码时，在概览里点击一次“重启服务”。关闭窗口后点击 Dock 图标会重新显示控制面板，无需先退出进程。

详细说明见 [docs/macos-app.md](docs/macos-app.md)。

控制面板的日志页默认跟随最新输出，会话管理页会从 TraceMemo 导入全部联系人和群聊，
默认按最近活跃顺序显示合计 30 个私聊和群聊，公众号不进入列表；其余会话仍可通过
搜索找到。使用稳定会话 ID 的开关控制自动回复，并保留旧名称白名单兼容；概览页的启动、停止、重启和设置保存都会同时管理规则服务和自动回复服务。
发送器会优先从左侧会话列表定位，私信和群聊分别使用严格匹配与群聊容错搜索，最后统一
用右侧完整标题复核。

[![编译安卓 APK](https://github.com/tommywutong/wechat-auto-reply/actions/workflows/build-apk.yml/badge.svg)](https://github.com/tommywutong/wechat-auto-reply/actions/workflows/build-apk.yml)
![平台](https://img.shields.io/badge/平台-Android%20%7C%20macOS%20%7C%20iOS-lightgrey)
![测试](https://img.shields.io/badge/测试-194%20passed-brightgreen)

基于大语言模型的微信自动回复系统。通过一套可配置的人设与应对策略生成回复，
而非关键词匹配，因此能够处理未预设的对话内容。

支持 Android 与 macOS 双端部署，两端共用同一套决策逻辑与安全约束。

> **面向非技术用户的图文步骤：[新手指南.md](新手指南.md)**
> 本文档面向需要了解实现细节或修改代码的读者。

## 致谢与本地依赖

早期版本的跨平台思路和部分实现参考了 [taotao-river/wechat-auto-reply](https://github.com/taotao-river/wechat-auto-reply)，
在此致谢。当前仓库独立维护，不继承该项目的 Git 提交历史。

macOS 自动回复使用 [TraceMemo](https://github.com/Wxw-Gu/TraceMemo) 的 Reader 能力，通过本机
HTTP API 读取联系人、最近会话和聊天记录；消息数据留在本机，API Token 只从 macOS
Keychain 读取。自动回复启动时会准备一个独立的 TraceMemo Reader 运行时：已有 TraceMemo
数据会直接复用，没有安装也会按固定版本从官方 Release 下载到用户目录，不需要用户单独安装
TraceMemo 应用。首次使用仍需在 TraceMemo 中完成一次微信数据库连接，或提供已经连接好的本机数据目录。

---

## 目录

- [设计目标](#设计目标)
- [核心特性](#核心特性)
- [Android 与 macOS 的区别](#android-与-macos-的区别)
- [系统要求](#系统要求)
- [安装部署](#安装部署)
- [人设配置](#人设配置)
- [模型服务](#模型服务)
- [安全机制](#安全机制)
- [系统架构](#系统架构)
- [开发与测试](#开发与测试)
- [已知限制](#已知限制)
- [免责声明](#免责声明)

---

## 设计目标

传统自动回复依赖关键词匹配，只能覆盖预先设想的情形，对话稍有变化即暴露机器
特征。本项目的核心思路是：将「判断依据」而非「问答对」交给模型。

配置描述的是使用者的身份、语气与各类情形的处置原则；具体措辞由模型在收到消息
时生成。

```
对方：明天下午有空不，一起吃个饭
回复：我看下日程，晚点回你

对方：那个东西弄得怎么样了
回复：在弄了，这两天给你结果

对方：帮我转账 500
（不回复——命中敏感词，移交人工处理）
```

上述回复均为实时生成，配置中并不存在对应的问答条目。

macOS 设置页还提供“Grok 4.1 风格（实验）”预设。它只改变表达方式，不改变白名单、
群聊规则、限流、发送确认或安全边界；预设会和每个会话的本地风格画像叠加。该预设基于
xAI 公开提示词的行为描述进行本地适配，来源和许可证见
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## 核心特性

| 特性 | 说明 |
|---|---|
| **人设驱动生成** | 基于身份、语气、应对攻略生成回复，非关键词匹配 |
| **Grok 风格预设** | macOS 可选直接、坦率、适度幽默的 Grok 4.1 风格（实验） |
| **引导式配置** | 十道选择题生成完整人设，无需手工撰写提示词 |
| **双模式** | AI 生成 / 本地关键词匹配，后者完全离线 |
| **多模型支持** | 豆包、DeepSeek、通义千问、智谱 GLM、Moonshot、Claude |
| **安全前置** | 敏感词、黑名单、频率限制在调用模型前执行 |
| **上下文记忆** | 每会话保留最近 8 轮、1 小时，仅存于内存 |
| **一键开关** | Android 支持通知栏快捷开关 |
| **零服务依赖** | Android 端引擎内嵌，无需服务器或局域网 |

## Android 与 macOS 的区别

两端共用同一套安全判断、人设配置和模型接口，但消息的读取和发送方式完全不同：

| 对比项 | Android 版 | macOS 版 |
|---|---|---|
| **运行位置** | 微信手机旁的 Android 设备 | 一台常开的 Mac，微信桌面端保持登录 |
| **消息入口** | Android 通知监听；通知没有回复入口时可用无障碍兜底 | TraceMemo 本机 HTTP API 读取联系人、最近会话和聊天记录 |
| **微信是否要在前台** | 通知方案不需要；无障碍兜底需要停在聊天页 | 读取由 TraceMemo 完成；真实发送时会定位并操作 Mac 微信窗口 |
| **电脑要求** | 不需要电脑，服务和引擎都在 APK 内 | 需要 Mac、Python 和 Swift 构建工具；Reader 会自动准备 |
| **消息完整度** | 受系统通知内容限制，长消息可能被截断；免打扰会话通常没有通知 | 通过聊天记录读取，内容更完整；打开会话读取时可能清除未读状态 |
| **图片与表情包** | 当前主要按通知文本处理，不保证能读到媒体内容 | TraceMemo 提供媒体地址时可下载并用 macOS Vision OCR 尝试识别；回复可发送 Unicode emoji |
| **网络与数据** | 关键词模式可完全离线；AI 模式从手机直连所选模型或中继服务 | 消息、日志和配置留在 Mac；AI 请求从 Mac 发出，凭据放在 macOS Keychain |
| **适合场景** | 没有常开电脑、希望手机独立运行 | iPhone 用户、需要更完整消息、希望用桌面控制面板管理服务 |

简单选择：没有 Mac 就用 Android；有 Mac 且希望代理 iPhone 上的同一个微信号，优先用 macOS。

## 系统要求

| 部署方式 | 要求 | 是否需要电脑 |
|---|---|---|
| **Android** | Android 8.0 (API 26) 及以上 | 否 |
| **macOS 控制 App** | macOS 13 及以上，Python 3.9+，Swift 5.9+/Xcode Command Line Tools，已登录 macOS 版微信；Reader 自动准备 | 是（需常驻运行） |

iPhone 用户请采用 macOS 方案：微信支持手机与桌面端同时在线且共享消息，
在 Mac 端回复等效于本人在 iPhone 上回复，无需越狱或安装任何 iOS 应用。

## 安装部署

### Android

手机浏览器打开以下地址，下载后直接安装：

```
https://github.com/tommywutong/wechat-auto-reply/releases/latest/download/wechat-auto-reply.apk
```

该地址固定指向最新构建，无需登录。安装后按引导完成配置：

1. 首次启动进入配置问答（十题，约一分钟）
2. 授予通知使用权（设置项内提供跳转入口）
3. 开启主开关

如需启用 AI 生成，在「怎么回」中选择 AI 模式，并二选一：

- **使用自有 API Key** — 推荐。在设置页点击厂商按钮自动填充接口地址与模型名，
  仅需粘贴 Key。该方式不依赖任何第三方服务。
- **接入他人服务** — 填写对方提供的地址与令牌。消息将经由对方服务器处理。

> 微信内置浏览器会拦截外部下载，请复制链接至系统浏览器打开。

### macOS

macOS 版目前需要从源码自行安装，没有提供可直接双击的签名安装包。完整链路由
`TraceMemo Reader → 本地规则服务 → 自动回复轮询器 → Mac 微信界面` 组成；Mac 需要保持开机、
微信登录和已连接的本地微信数据库数据。

#### 1. 准备环境

安装以下软件：

- macOS 13 或更高版本
- Mac 版微信，并登录要自动回复的微信号
- Python 3.9 或更高版本
- Xcode Command Line Tools（构建 Swift 控制 App、OCR 和鼠标辅助程序）

不需要单独安装 TraceMemo。首次启动自动回复服务时，程序会检查 `127.0.0.1:6131`；已有
TraceMemo 正在运行时直接复用，没有运行时会自动下载官方 TraceMemo Reader 到
`~/Library/Application Support/TraceMemoAutoReply/runtime`，并优先复用本机已有的
`~/Library/Application Support/TraceMemo` 数据目录。若本机从未连接过微信数据库，需要先
用 TraceMemo 完成一次连接并保留其数据目录；这是微信数据库密钥和连接状态的来源。

如果尚未安装开发者命令行工具，可在终端执行：

```bash
xcode-select --install
```

#### 2. 下载并初始化项目

```bash
git clone https://github.com/tommywutong/wechat-auto-reply.git
cd wechat-auto-reply
bash scripts/macos-setup.sh
```

脚本会创建项目专用的 `.venv`、生成 `core/config.yaml` 和本地 token、安装规则服务，
并写入可双击运行的辅助启动器。已有配置时不会覆盖 `core/config.yaml`。

不熟悉终端时，也可以在 Finder 中双击仓库里的 `安装到Mac.command`；它执行同一套初始化流程。
从网络下载的 `.command` 文件若被 Gatekeeper 拦截，请在“系统设置 → 隐私与安全性 → 安全性”中
点击“仍要打开”。

#### 3. 把凭据放进 macOS Keychain

TraceMemo Token 是读取本机聊天数据所必需的；AI 模式还需要 DeepSeek Key。下面两条命令会
交互式提示输入内容，输入时不会回显，也不会把密钥写进项目文件：

```bash
security add-generic-password -U -a "$USER" -s com.wxauto.tracememo-api-token -w
security add-generic-password -U -a "$USER" -s com.wxauto.deepseek-api-key -w
```

可以只验证条目是否存在，不会打印密钥：

```bash
security find-generic-password -a "$USER" -s com.wxauto.tracememo-api-token >/dev/null && echo "TraceMemo Token 已保存"
security find-generic-password -a "$USER" -s com.wxauto.deepseek-api-key >/dev/null && echo "DeepSeek Key 已保存"
```

#### 4. 构建并打开 macOS 控制 App

```bash
bash scripts/run-macos-app.sh
```

首次打开后，在窗口底部选择刚刚克隆的项目目录。控制 App 会读取 TraceMemo 的联系人和群聊，
用稳定会话 ID 管理白名单，并统一管理规则服务与自动回复服务。设置保存后会自动重启相关服务，
无需手动编辑 YAML。

#### 5. 授予系统权限

在“系统设置 → 隐私与安全性”中，把实际运行脚本或控制 App 的程序加入并打开：

- **辅助功能**：读取和操作微信窗口
- **屏幕录制**：截取微信窗口用于 OCR 和发送前确认

首次授权后，退出并重新打开控制 App 或终端，确保权限生效。

#### 6. 先安全试跑，再开启真实发送

保持微信登录，并确认内置 Reader 已在控制 App 概览页显示正常，在项目目录按顺序执行：

```bash
"./1 检查微信.command"
"./2 试运行（不真发消息）.command"
```

第一步只诊断微信界面，不读取或发送消息；第二步会生成决策和本地草稿，但不会按发送键。
确认白名单、群聊 `@` 规则和回复内容都正确后，再执行：

```bash
"./3 开始自动回复.command"
```

也可以直接在控制 App 的概览页启动服务。启动时默认跳过停机期间已经存在的旧消息；需要追补时，
在设置中打开“启动时追补停机消息”。

#### 7. 日常运行与停止

控制 App 会把规则服务和自动回复服务汇总成“运行中 / 部分运行 / 已停止 / 未安装”状态。
“启动”按规则服务、自动回复服务的顺序补齐未运行项，不会重启已经运行的服务；“停止”按相反
顺序真正卸载两项；“重启”会完整停止后再依次启动。操作完成后 App 会复核两项服务的最终状态，
不会在其中一项仍未运行时显示成功。关闭控制 App 不会停止后台服务；要停止自动回复，点击
“停止服务”，或执行：

```bash
launchctl bootout "gui/$(id -u)/com.wxauto.tracememo-autoreply"
```

Mac 需要保持唤醒；合盖或进入睡眠后，微信界面发送无法继续。详细故障排查见
[docs/macos-app.md](docs/macos-app.md) 和 [docs/tracememo-macos-draft-mode.md](docs/tracememo-macos-draft-mode.md)。

旧的纯终端 `run-mac-bot.sh` 仍可用于兼容场景；新安装优先使用上面的 TraceMemo 控制 App 流程。

## 人设配置

人设决定回复是否贴近本人语气，是本系统效果的关键。为降低配置门槛，
系统提供引导式问答，将十项选择题映射为完整配置。

```bash
python3 -m core.wizard     # 重新生成配置
python3 -m core.preview    # 交互式预览，不发送消息
```

生成结果同时覆盖 AI 模式的人设与关键词模式的规则，两种模式语气一致。
Android 端内置同一套问答逻辑，题目顺序由单元测试约束保持两端一致。

生成的配置可直接编辑：

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

完整字段说明见 [`core/config.ai.example.yaml`](core/config.ai.example.yaml)。

## 模型服务

| provider | 服务商 | 凭据环境变量 |
|---|---|---|
| `doubao` | 豆包（火山方舟） | `ARK_API_KEY` |
| `deepseek` | DeepSeek | `DEEPSEEK_API_KEY` |
| `qwen` | 通义千问 | `DASHSCOPE_API_KEY` |
| `zhipu` | 智谱 GLM | `ZHIPU_API_KEY` |
| `moonshot` | Moonshot | `MOONSHOT_API_KEY` |
| `anthropic` | Claude | `ANTHROPIC_API_KEY` |

默认使用豆包。本场景需要的是自然的中文口语表达，而非复杂推理能力，
豆包在该维度表现较好，且国内网络可直接访问。

前五项均为 OpenAI 兼容接口，由标准库实现，无第三方依赖；
仅 `anthropic` 需额外安装 SDK。`model` 与 `base_url` 留空时使用该服务商默认值。

> 火山方舟的 `model` 字段接受模型 ID（如 `doubao-seed-1-6-251015`）
> 或推理接入点 ID（`ep-` 前缀）。模型 ID 含版本日期后缀，会随版本更新变化；
> 若接口返回模型不存在，请从控制台复制当前有效值。

## 安全机制

自动回复的主要风险并非漏回，而是回错。以下约束不可通过配置关闭：

**敏感消息拦截。** 包含转账、红包、验证码、银行卡、身份证、密码、借钱、
急用钱、汇款、付款码等字样的消息一律不回复。该判断位于所有频率逻辑之前，
即使冷却时间设为 0、规则配置为全匹配亦不受影响。AI 模式下此类消息不会
发送至模型。

**决策顺序固定。**

```
主开关 → 空消息 → 敏感词 → 黑名单 → 屏蔽词 → 白名单
→ 会话类型 → 时段 → 跨端去重 → 频率限制 → [AI 生成 | 关键词规则] → 兜底
```

模型仅决定「表述内容」，不参与「是否应当回复」的判断。后者依赖确定性规则，
不能交由概率性系统处理。

**四层频率限制。** 单会话冷却（默认 30 分钟）、单会话每日上限、
全局每小时上限、全局每日上限。后两层作为熔断，防止配置错误导致大量发送。

**跨会话最小间隔（默认 45 秒）。** 冷却按会话计算，无法阻止「多人同时来消息、
数十秒内逐一回复完毕」这一情形，而这是最易识别的自动化特征。命中该限制时
将发送时刻顺延而非丢弃消息，多条回复因而依次排开。

**发送延迟。** 由三部分构成：基础随机延迟（默认 3–12 秒）、按回复长度计算的
输入耗时（默认 0.12 秒/字）、以及上述跨会话间隔。固定延迟会使长短回复的
响应时间完全一致，反而不自然。

**文案轮换为全局计数。** 若按会话独立计数，每个联系人收到的都是第一条文案——
批量发送相同内容是风控的典型识别项。全局轮换确保相邻发出的内容不同。

**回复标识。** 默认追加「（自动回复）」后缀，可关闭但建议保留。

**失败静默。** 接口异常、生成失败、内容读取失败等所有异常路径均返回不回复。
AI 生成失败时不会退回关键词文案，以避免输出风格突变。

**联系人白名单。** `scope.allow_contacts` 非空时仅对名单内联系人回复。
这是本项目提供的**最有效的风险控制手段**——导致账号受限的主要路径是被举报，
而熟识联系人不会举报。配置问答的最后一题即为该项，Android 设置页同样提供入口。

**账号隔离。** 限流键为「账号 + 会话类型 + 归一化会话名」。多账号场景下
各自独立计数；同一账号多端登录时配置相同 `account` 值可共享冷却并去重。
详见 [`docs/multi-account.md`](docs/multi-account.md)。

## 系统架构

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────┐
│  消息采集     │ ──▶ │      决策引擎        │ ──▶ │   回复发送    │
│              │     │                     │     │              │
│ Android 通知  │     │ 安全检查 → 频率限制  │     │ RemoteInput  │
│ macOS 辅助功能│     │ → AI 生成 / 规则匹配 │     │ 辅助功能操作  │
└──────────────┘     └─────────────────────┘     └──────────────┘
```

决策引擎存在 Python 与 Kotlin 两份实现。Android 设备无法运行 Python 服务，
要求终端用户安装 Termux 并执行命令不具备可行性，因此引擎完整移植至 APK 内。
两份实现的决策顺序必须一致，各自的单元测试对此进行约束。

```
core/                 决策引擎（Python），109 项测试
  engine.py             决策主流程
  wizard.py             引导式配置问答
  persona.py            人设建模、对话记忆、提示词构造
  providers.py          模型服务注册表
  llm_openai.py         OpenAI 兼容接口调用（标准库实现）
  llm.py                Anthropic SDK 调用
  preview.py            交互式预览
  config.py             配置解析与校验
server/app.py         HTTP 服务（FastAPI），供 macOS 端及中继模式使用
android/              Android 客户端（Kotlin），76 项测试
  engine/               引擎、问答、模型调用的 Kotlin 实现
macos/                macOS 采集端与 TraceMemo 轮询器（辅助功能 API）
ios/                  iOS 方案参考实现，见下
docs/                 部署、多账号、iOS 可行性分析
```

### 关于 iOS

未越狱的 iOS 设备无法由第三方应用读取或发送其他应用的消息，此为系统沙盒
设计使然。本仓库提供三种参考实现：

| 方案 | 越狱要求 | 可用性 | 实现 |
|---|---|---|---|
| UI 自动化（Appium + WDA） | 否 | 微信需常驻前台 | [`ios/appium/`](ios/appium/) |
| 注入插件（Theos） | 是 | 完整 | [`ios/tweak/`](ios/tweak/) |
| **macOS 代理（推荐）** | 否 | 完整，不占用手机 | [`macos/`](macos/) |

完整分析见 [`docs/ios-feasibility.md`](docs/ios-feasibility.md)。

## 开发与测试

```bash
python -m pytest -q                          # 193 项
cd android && ./gradlew testDebugUnitTest     # 76 项
```

APK 由 GitHub Actions 构建，单元测试失败时不产出制品。
推送至 `main` 分支后自动更新 Release 下载地址。

## 已知限制

以下部分仅完成编译与逻辑验证，**尚未在真实设备上运行**：

- Android 端通知拦截与 RemoteInput 发送的实际行为
- 微信通知在各版本、各定制 ROM 上的正文格式解析
- macOS 端辅助功能控件路径（微信界面改版可能导致失效，
  可通过 `--doctor` 诊断并调整）
- 模型接口请求格式已对照官方文档实现，但未使用真实凭据验证

其他固有限制：

- Android 端仅能处理产生通知的消息，免打扰会话不可见
- 通知正文可能被系统截断，超长消息无法完整读取
- 部分定制 ROM 移除了通知的 RemoteInput，需启用无障碍方案
- macOS 端读取消息需展开会话，未读状态会被清除

## 免责声明

本项目实现的功能未经微信官方开放，使用者需自行评估以下风险：

- **账号风险。** 自动化行为可能触发风控策略，导致功能限制或账号封禁。
  项目内置的频率限制与随机延迟旨在降低该风险，但不构成任何保证。
- **权限范围。** 通知使用权与辅助功能权限的授权范围较大，可读取设备上
  其他应用的内容。建议仅安装自行编译或从本仓库 Actions 获取的版本。
- **数据流向。** AI 模式下，待回复消息及上下文将发送至所选模型服务商。
  敏感词消息与黑名单联系人的消息在本地拦截，不会外发。关键词模式完全离线。
- **服务条款。** 相关行为可能违反微信用户协议。

建议初期仅对少量熟识联系人启用，观察若干日后再扩大范围。

本项目仅供学习与个人使用。使用者应对由此产生的一切后果负责。
