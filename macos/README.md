# macOS 微信自动回复

macOS 模块负责从本机微信数据源取得新消息，并在决策引擎允许时生成草稿或安全地操作微信界面发送。推荐的数据源是单独安装的 TraceMemo。

## 推荐架构

```text
TraceMemo :6131
  -> tracememo_poller.py
  -> FastAPI :8848
  -> core ReplyEngine
  -> tracememo-drafts.jsonl（默认）
     或 wechat_sender.py（显式真实发送）
```

## 轮询器

[`tracememo_poller.py`](tracememo_poller.py) 负责：

- 获取最近会话和消息。
- 兼容 TraceMemo 字段并过滤方向不明、旧消息和重复消息。
- 合并短时间内同一会话的连续输入。
- 为图片等媒体补充可用描述。
- 图片和表情包可通过配置的百炼视觉模型理解，视觉请求失败时退回本地 OCR 文本。

视觉配置示例：

```yaml
llm:
  vision_enabled: true
  vision_provider: qwen_bailian
  vision_model: qwen3-vl-flash
  vision_fallback_model: qwen3-vl-plus
  vision_base_url: https://你的百炼业务空间/compatible-mode/v1
```

视觉 Key 只从 `QWEN_API_KEY` 或 macOS Keychain 服务 `com.wxauto.qwen-api-key` 读取。
- 调用本地决策服务。
- 写草稿，或把批准结果交给发送器。

每个白名单会话首次收到新消息时，轮询器会通过 TraceMemo 读取近 30 天聊天记录，只提取“对方说什么、
本人怎么回”的本地风格画像。画像最多保存 48 组候选、权限为仅当前用户可读；生成回复时只会选当前
来信最相近的 3 组示例，因此同一个人聊技术、熟人闲聊、群聊时的语气可以不同。原始聊天记录不会写
进日志或 Git，也不会被完整发送给模型。旧画像会在该会话下一次收到消息时自动升级重建。

普通问候和闲聊默认直接回应，不再把“忙完再说”“晚点回”当作常规话术。只有约时间、金额、承诺、
资料不足或需要本人决策时，模型才会保守地留给本人确认。

图片和表情包会保留在本机内存中，按 `llm.vision_*` 配置发送到百炼视觉模型；默认使用
`qwen3-vl-flash`，模型不可用时尝试 `qwen3-vl-plus`，都失败才退回本地 OCR 文本。普通文字仍使用
`llm.provider` 配置的文字模型。媒体不会写入 Git、日志或草稿文件。

性能上，轮询器会并行读取多个白名单会话，再按原会话顺序完成去重、批次决策和发送；模型调用与真实
微信发送不会并发。常驻模式按固定节拍开始下一轮，处理耗时不会额外拖慢下一轮。默认读取线程数为 4，
可用 `--fetch-workers 1-8` 调整；TraceMemo 或电脑负载较高时可以调低。微信已经打开并有主窗口时，
发送器会跳过重复的应用启动等待，但仍保留标题 OCR、输入内容和发送结果确认。

先使用诊断或单轮草稿模式，确认字段与规则后再考虑真实发送。详细步骤见 [`../docs/tracememo-macos-draft-mode.md`](../docs/tracememo-macos-draft-mode.md)。

## 发送器

[`wechat_sender.py`](wechat_sender.py) 不读取消息，也不做业务判断。它只负责定位目标会话、复核标题、写入文本和验证发送动作。OCR、点击与滚动 helper 由以下命令生成：

```bash
bash scripts/build-macos-helpers.sh
```

运行需要屏幕录制和辅助功能权限。失败诊断写入被 Git 忽略的 `var/`，可能包含私人界面信息。

## 旧兼容路径

[`wechat_mac_bot.py`](wechat_mac_bot.py) 直接读取微信辅助功能树。微信 UI 结构变化会使选择器失效，优先使用 TraceMemo 主链路。

## 测试

```bash
python -m pytest -q macos/tests
```

Agent 修改本模块前应读取 [`MEMORY.md`](MEMORY.md)。SwiftUI 控制面板有独立的 [`TraceMemoAutoReplyApp/README.md`](TraceMemoAutoReplyApp/README.md)。
