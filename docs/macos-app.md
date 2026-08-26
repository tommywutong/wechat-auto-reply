# macOS 控制 App

`TraceMemo 自动回复.app` 是现有本地自动回复服务的控制面板。它不替换
TraceMemo、DeepSeek 或微信界面发送器，只负责把常用的启动、停止、设置和日志
操作集中到一个原生 SwiftUI 窗口里。

## 构建

在 macOS、Swift 5.9 或更高版本上运行：

```bash
bash scripts/build-macos-app.sh
open "dist/TraceMemo 自动回复.app"
```

App 首次打开时，在左侧底部选择项目目录。默认会自动发现当前仓库，也可以通过
`WXAUTO_REPO_DIR` 指定其他项目目录。项目发现不依赖个人 `core/config.yaml`；若该文件
缺失，App 会连接项目并提示初始化配置，而不会要求重新选择目录。

## 功能

- 菜单栏状态和启动、停止、重启操作
- `launchd` 服务状态检查
- TraceMemo 健康检查和 Keychain 凭据存在性检查
- 从 TraceMemo 导入全部联系人和群聊；默认按最近活跃顺序显示合计 30 个私聊和群聊，公众号不进入列表
- 按名称、备注或稳定会话 ID 搜索全部非公众号会话
- 用会话开关管理私信/群聊白名单；保留旧名称配置并自动迁移到稳定 ID
- 私信/群聊白名单与 `@` 策略编辑
- 轮询间隔、模型名称、输出限制和全局限流设置
- 自动刷新 stdout/stderr 日志，支持复制日志文本
- 日志页默认自动跟随最新一行，也可以关闭跟随以查看历史内容
- 设置页支持活动时段、回复风格、单会话冷却、全局限流、随机等待和打字速度

设置保存到本地 `core/config.yaml`，其中 `scope.allow_talkers` 保存 TraceMemo 稳定会话
ID，`scope.allow_contacts` 作为旧配置兼容和显示名称备份；轮询间隔保存到
`var/poll-interval`。保存设置后 App 会同时重启 `com.wxauto.server` 规则服务和
`com.wxauto.tracememo-autoreply` 自动回复服务，确保人设、模型、回复模式以及
轮询/限流设置都从最新配置加载。API Token 仍只从 macOS Keychain 读取，App 不会显示或写入 Token。

首次进入会话管理页时，App 通过 `scripts/tracememo_contacts.py` 调用本机 TraceMemo
`/recent_chat` 和 `/contact` 接口。`/recent_chat` 提供微信侧最近活跃顺序；如果旧版
TraceMemo 不支持该端点，会自动退回 `/contact`。Token 不经过 Swift UI，也不会进入日志
或配置文件。列表支持私聊/群聊筛选；开启某一行的开关即允许该稳定会话进入自动回复链路。

## 微信会话定位

发送器对私信和群聊使用不同的搜索容错：

1. 先扫描当前左侧会话列表。
2. 找不到时用独立滚轮向上、向下做有限次数的小步滚动，并检测列表内容是否真的变化。
3. 找到目标后执行同坐标短促单击，不使用拖拽。
4. 进入会话后必须 OCR 确认右侧顶部完整标题；群聊允许微信追加成员数量。
5. 左侧仍找不到时才打开搜索。私信要求精确名称，群聊允许成员数后缀、长名称分段和安全的长前缀；搜索后仍必须经过标题复核。

Computer Use 只用于开发时观察不同微信版本的界面，不参与后台轮询，因此不会增加
日常 Token 消耗，也不会绕过屏幕录制或辅助功能权限。

## 权限

自动回复链路仍需要用户给运行 Python/辅助程序的终端或 App 授予屏幕录制和辅助
功能权限。App 只负责显示服务状态，不能绕过 macOS 隐私权限。

## 开源发布注意事项

提交 GitHub 前不要提交：

- `core/config.yaml`
- `.wxauto_token`
- `var/`
- `dist/`
- `.build/`
- 任何包含联系人、聊天内容、截图或 Token 的文件

发布给其他人时，应提供脱敏的 `core/config.example.yaml` 和构建说明；用户在本机
完成 Keychain、TraceMemo 和微信权限配置后再启动服务。
