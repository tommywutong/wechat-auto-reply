# macOS SwiftUI 控制 App 模块记忆

## 何时读取

任务涉及原生 macOS UI、菜单栏状态、设置编辑、会话管理、日志展示、服务启动停止或 App 打包时读取本文件。

## 模块定位

本模块是现有本地服务的控制面板，不是回复引擎、TraceMemo 数据库或微信发送器。主要实现集中在 `Sources/TraceMemoAutoReplyApp.swift`。

## 责任

- 发现并记住仓库目录。
- 查询 TraceMemo、Keychain 凭据和两个 launchd 服务状态。
- 同时管理规则服务和真实自动回复服务。
- 调用 `../../scripts/tracememo_contacts.py` 导入稳定会话。
- 调用 `../../scripts/app_config.py` 读写配置和轮询间隔。
- 展示概览、会话白名单、设置和自动刷新的日志。

## 不变量

- App 不读取、显示、复制或保存 API Token。
- UI 不复制 `core` 的业务判断；配置合法性最终由 Python parser 保证。
- 显示“已运行”或“已保存”必须有真实进程/命令结果支撑。
- Dock 重新激活且控制窗口不可见时必须恢复或创建主窗口；窗口关闭不等于退出 App。
- 启动检查更新只能调用受限脚本：仅干净 `main` 的 fast-forward 可更新，不能覆盖本机改动或配置。
- 启动、停止、重启和设置保存要考虑 `com.wxauto.server` 与 `com.wxauto.tracememo-autoreply` 的联动。
- 状态不能只靠颜色表达；日志与错误不能泄露私人消息或密钥。
- 会话白名单优先保存稳定 `talker`，同时兼容旧名称字段。
- 遵循根目录 `PRODUCT.md` 和 `DESIGN.md` 的克制原生界面原则。

## 影响面

- 设置字段变化：检查 `../../scripts/app_config.py`、`../../core/config.py` 和默认显示。
- 服务标签或日志路径变化：检查安装脚本与所有状态查询。
- 会话模型变化：检查联系人脚本、筛选、搜索、旧配置迁移和 Swift 测试。
- UI 文案变化：保持非技术用户可理解，并区分未配置、已停止、降级和错误。

## 验证

```bash
cd macos/TraceMemoAutoReplyApp
swift test
cd ../..
bash scripts/build-macos-app.sh
```

不要在没有授权时打开 App、启动 launchd 或点击真实发送相关操作。

## 继续阅读

- 开发者说明：[`README.md`](README.md)
- 产品原则：[`../../PRODUCT.md`](../../PRODUCT.md)
- 视觉规则：[`../../DESIGN.md`](../../DESIGN.md)
- 完整功能说明：[`../../docs/macos-app.md`](../../docs/macos-app.md)
- 自动化模块：[`../MEMORY.md`](../MEMORY.md)
