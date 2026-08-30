# TraceMemo 草稿模式（当前个人微信）

这一模式通过 TraceMemo 读取当前个人微信的白名单会话，按轮询间隔检查新消息，调用现有 DeepSeek 回复引擎，并把草稿写入本机文件。发送模式会额外使用 macOS 界面能力；它不读取微信数据库、不注入微信进程，也不调用机器人发送接口。

## 一次性配置密钥

在 macOS 终端中分别执行两次命令。每次命令会安全地要求输入一次密钥；输入时终端不会回显。

```bash
security add-generic-password -U -a "$USER" -s com.wxauto.tracememo-api-token -w
security add-generic-password -U -a "$USER" -s com.wxauto.deepseek-api-key -w
```

不要使用 `-A` 参数，也不要把密钥写进 YAML、`.env` 或项目文件。下面命令只验证钥匙串项目是否存在，不会输出密钥：

```bash
security find-generic-password -a "$USER" -s com.wxauto.tracememo-api-token -w >/dev/null && echo "TraceMemo Token 已保存"
security find-generic-password -a "$USER" -s com.wxauto.deepseek-api-key -w >/dev/null && echo "DeepSeek Key 已保存"
```

## 先验证 TraceMemo 字段

保持 TraceMemo 打开并完成数据库连接，然后运行：

```bash
./scripts/run-tracememo-poller.sh --dump-schema
```

它只打印 `/recent_chat`，以及一条白名单最近会话的 `/chatlog` 返回对象字段名，不打印联系人、会话名称或聊天内容。首次运行时 macOS 可能询问 Python 是否可以读取钥匙串，选择允许。如果当前没有白名单会话出现在最近列表中，输出只会包含 `recent_chat`，这时先让该联系人或群聊产生一条新消息后再运行一次。

## 手动草稿验证

```bash
./scripts/run-tracememo-poller.sh --once
tail -n 20 var/tracememo-poller.log
tail -n 20 var/tracememo-drafts.jsonl
```

默认情况下，服务每次启动的首轮扫描只为白名单会话建立当前历史游标，绝不会追补停机期间的历史消息。从后续扫描起，轮询器只处理上次扫描后出现的白名单新消息；为了兼容 TraceMemo 的查询性能，它会读取当天窗口并在本机按游标过滤。没有明确入站方向的记录会被跳过。若确实需要补处理停机期间的消息，可在控制 App 的设置中打开“启动时追补停机消息”，或手动运行 `./scripts/run-tracememo-poller.sh --replay-offline`。

同一会话、同一发送人在 8 秒内连续发来的最多 4 条消息会作为一轮交给模型。模型会判断这些内容应该合并成一条自然回复，还是在同一条微信消息中分点回应；间隔较长或群聊中不同人发的消息会分开处理。可以用 `--merge-window <秒>` 调整判断窗口。

轮询器会为每个白名单会话在本机建立风格画像：从近 30 天记录中提取最多 48 组“对方来信 → 本人回复”候选，
每次按当前消息检索最多 3 组相近示例给模型。这是本地上下文检索，不是把聊天记录上传用于模型训练；
画像保存在被 Git 忽略且权限为 0600 的 `var/style-profiles.json`，原始历史不写日志。普通问候、闲聊和可直接回答的问题会优先自然回应；约时间、金额、承诺或需要本人判断的事项仍会保守处理。

TraceMemo 提供图片和表情包地址时，轮询器会把媒体下载到临时目录并调用 macOS Vision OCR。识别到的文字会随“图片/表情包”标记交给模型；没有文字、地址过期或 OCR 不可用时，也会明确标记为“暂未识别到图片中的文字”，不会假装看懂。回复中的 Unicode emoji 会按普通文字通过剪贴板发送，模型只会在语境合适时偶尔使用。

## 常驻草稿模式

确认字段和草稿正确后，安装登录后自动启动的本地服务：

```bash
bash scripts/install-tracememo-poller.sh
```

日志和本地草稿分别在：

```text
var/tracememo-poller.log
var/tracememo-poller.err.log
var/tracememo-drafts.jsonl
```

每个消息批次认领前后都会立即保存轮询状态。这样服务在生成回复或发送界面动作期间重启时，
已经认领的批次不会再次交给模型；未认领的后续批次仍会在下一轮继续处理。

停止服务：

```bash
launchctl bootout "gui/$(id -u)/com.wxauto.tracememo-poller"
```

进入下一阶段的微信界面发送功能前，需要先人工核对草稿、白名单、群聊识别和重复处理情况。

发送模式下，如果检测到用户仍在操作电脑，回复会暂缓并持久化到等待队列；默认有效期为 600 秒
（10 分钟），超过后自动丢弃，避免重启服务后发送已经失去时效的旧内容。这个有效期可以在
macOS 控制 App 的“安静发送”设置中调整，普通发送失败重试不受影响。

## Biscoffee 端到端测试

现在可以把链路接到本机微信界面，常驻服务会对配置白名单中的私聊真实发送，群聊仍必须明确 @ 当前昵称。发送器不依赖微信辅助功能树，而是用快捷键搜索、窗口 OCR 和相对窗口坐标点击输入框；搜索结果、会话标题、粘贴后的输入内容任一步未确认，都会停止且不按发送键。发送完成后会尽量恢复发送前的前台应用，但由于微信 4.x 没有稳定后台发送接口，无法保证完全不显示微信窗口。

先在微信中打开并登录主账号，让 TraceMemo 保持运行，并确保终端（或启动脚本的应用）已获得：

- 屏幕录制
- 辅助功能

编译本机辅助程序：

```bash
bash scripts/build-macos-helpers.sh
```

把微信窗口保持在前台可见，然后从 `Biscoffee` 小号给主号发送一条普通文字。在项目目录只运行这一条前台命令：

```bash
bash scripts/run-tracememo-autoreply.sh --once
```

它会读取 TraceMemo、调用 DeepSeek、先写入 `var/tracememo-drafts.jsonl` 作为审计记录，再尝试在确认的白名单会话中粘贴并发送。`--once` 只检查一轮，便于首次观察；持续运行时去掉 `--once`。

群聊只有在消息正文明确包含配置中的 `scope.self_nicknames`（例如 `@Northern Lights`）时才会进入回复引擎；普通群消息会被跳过。每个会话的本人历史文字会在本机生成轻量风格画像，保存到 `var/style-profiles.json`，不会写入日志。

如果没有生成草稿或不确定 TraceMemo 是否识别到新消息，先运行不调用 AI 的诊断：

```bash
bash scripts/run-tracememo-poller.sh --diagnose-name Biscoffee
```

诊断只输出记录数量、`type`、`isSender` 方向、时间字段和本地游标统计，不输出消息正文。

确认 Biscoffee 的真实发送成功后，再考虑安装常驻服务：

```bash
bash scripts/install-tracememo-autoreply.sh
```

观察常驻服务的实时状态（不会启动第二个轮询器，也不会停止后台服务）：

```bash
bash scripts/watch-tracememo-autoreply.sh
```

有新消息时会立即显示检测、生成、发送或失败事件；没有新消息时默认每 30 秒输出一次运行状态。按 `Ctrl+C` 只退出观察，不会停止自动回复服务。

卸载：

```bash
launchctl bootout "gui/$(id -u)/com.wxauto.tracememo-autoreply"
```
