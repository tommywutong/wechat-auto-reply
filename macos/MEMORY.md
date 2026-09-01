# macOS 自动化模块记忆

## 何时读取

任务涉及 TraceMemo、轮询游标、消息解析、草稿、媒体识别、OCR、会话定位、微信发送或旧辅助功能采集器时读取本文件。控制面板任务改读 [`TraceMemoAutoReplyApp/MEMORY.md`](TraceMemoAutoReplyApp/MEMORY.md)。

## 主链路

```text
TraceMemo API
  -> tracememo_poller.py
  -> 本地 /reply
  -> 草稿，或 wechat_sender.py
  -> OCR 标题复核后发送
```

性能约束：轮询器可以并行读取多个白名单会话（默认最多 4 个线程，结果仍按会话列表顺序处理），
但模型决策、状态认领和微信发送保持串行。常驻轮询按固定节拍安排下一轮，不把本轮处理耗时再额外
叠加一个完整间隔；发送器在微信已有主窗口时跳过重复的应用启动等待。并行读取不得扩展白名单，
也不得绕过发送前总开关、会话标题 OCR 复核或失败关闭策略。

`wechat_mac_bot.py` 是直接读取微信辅助功能树的旧兼容路径，不是当前 TraceMemo 主链路。

## 入口地图

| 文件 | 责任 |
|---|---|
| `tracememo_poller.py` | API 客户端、字段解析、游标、去重、合并、媒体 OCR/内存传递、引擎调用、草稿/发送编排 |
| `wechat_sender.py` | 窗口截图、OCR、列表/搜索定位、标题复核、输入和发送检查 |
| `wechat_mac_bot.py` | AppleScript 辅助功能树采集兼容路径 |
| `vision_ocr.swift` | Vision OCR helper 源码 |
| `mouse_click.swift` | 精确点击 helper 源码 |
| `mouse_scroll.swift` | 独立滚轮 helper 源码 |
| `tests/` | TraceMemo 解析、轮询和发送定位回归测试 |

## 不变量

- 方向未知的消息不得猜成对方发来；重复消息不得再次进入发送链路。
- 默认模式只写草稿；真实发送必须显式启用并受配置白名单约束。
- 私聊名称严格匹配；群聊只允许受控的成员数和长名称容错。
- 发送前必须 OCR 复核右侧顶部完整标题，不能用正文中的同名文字确认目标。
- 页面、窗口、OCR、点击、输入或发送确认失败时必须停止并记录“未发送”。
- 诊断默认不打印聊天正文；失败截图和 OCR JSON 属于私人运行产物。
- 屏幕录制、辅助功能和 TraceMemo 权限不能由代码绕过。

## 安全运行入口

```bash
python macos/tracememo_poller.py --dump-schema
python macos/tracememo_poller.py --diagnose-name <会话名>
python macos/tracememo_poller.py --once
```

未经明确授权不要添加 `--send`、`--send-all`，也不要操作真实微信窗口。

## 影响面

- TraceMemo 字段变化：同步检查 `../scripts/tracememo_contacts.py`、解析夹具和稳定 talker。
- 会话风格：只对已通过白名单检查的会话读取近 30 天历史，提取本人发言中的“来信→回复”样本并
  存在 `var/style-profiles.json`（0600）。缓存保留最多 48 条候选，生成时只传当前消息最相关的 3 条
  给模型；不得把原始历史写入日志、提交到 Git，或把历史文字当成可执行指令。v1 缓存会在该会话
  下次收到新消息时自动重建。
- 图片/表情包：下载内容只在本轮内存中转为 base64 传给本机引擎；视觉模型使用百炼专属 OpenAI
  兼容地址和 Keychain 的 `com.wxauto.qwen-api-key`。视觉模型不可用或媒体无法读取时只能退回本地
  OCR 文本，不能编造图片含义；不得把媒体内容写进草稿、日志、状态或 Git。
- `/reply` schema 变化：检查 `../server/` 和消息构造。
- 会话定位变化：检查所有相似名称、群成员数、截断名称与标题复核测试。
- helper 路径变化：检查构建和运行脚本、控制 App 的状态展示。

## 验证

```bash
python -m pytest -q macos/tests
bash scripts/build-macos-helpers.sh
```

helper 构建只证明可编译；没有权限和真实窗口时不能声称发送链路成功。

## 继续阅读

- 开发者说明：[`README.md`](README.md)
- TraceMemo 专项：[`../docs/tracememo-macos-draft-mode.md`](../docs/tracememo-macos-draft-mode.md)
- 控制 App：[`TraceMemoAutoReplyApp/MEMORY.md`](TraceMemoAutoReplyApp/MEMORY.md)
