# Scripts 模块记忆

## 何时读取

任务涉及安装、构建、launchd、服务启停、Keychain 环境、联系人导入、配置桥接、轮询启动或 Termux 时读取本文件。

## 模块定位

`scripts/` 是部署和模块连接层。脚本会创建虚拟环境、编译 helper、写本机配置、安装 launchd 服务或启动真实进程，因此其副作用通常大于普通源码修改。

## 文件地图

| 文件 | 作用 |
|---|---|
| `macos-setup.sh` | 建 venv、生成配置/Token、安装基础规则服务 |
| `build-macos-helpers.sh` | 编译 OCR、点击和滚动 helper |
| `build-macos-app.sh` | 构建并打包 SwiftUI App |
| `run-macos-app.sh` | 运行控制 App |
| `install-tracememo-poller.sh` | 安装草稿轮询 launchd 服务 |
| `install-tracememo-autoreply.sh` | 安装真实自动回复 launchd 服务 |
| `run-tracememo-poller.sh` | 在受控环境中启动草稿轮询器 |
| `run-tracememo-autoreply.sh` | 从 Keychain 环境启动真实发送轮询器 |
| `watch-tracememo-autoreply.sh` | 查看服务状态和日志 |
| `tracememo_contacts.py` | 获取联系人、最近会话和本人昵称建议 |
| `app_config.py` | SwiftUI App 的配置读写桥接 |
| `termux-setup.sh` | Android/Termux 专项部署路径 |

两个 macOS 运行脚本都读取 `var/poll-interval`（默认 5 秒，范围 5-300 秒），与控制 App 的轮询设置保持一致。
轮询器内部按固定节拍安排下一轮，处理耗时不会再额外叠加一个完整间隔。

## 不变量

- 未经明确授权，不运行安装脚本、不写 `~/Library/LaunchAgents`、不操作 Keychain、不启动真实自动回复。
- Shell 路径必须加引号，支持仓库路径含空格和中文。
- 保持 `set -euo pipefail`，并对预期失败显式处理。
- launchd 启动前清理可能继承的明文密钥；真实凭据优先从 Keychain 读取。
- 脚本重复运行应尽可能幂等，不生成多个同标签服务或并发轮询器。
- 真实发送脚本必须保留白名单、helper 检查和失败关闭。
- 生成文件写入已忽略路径，不提交机器绝对路径和私人值。

## launchd 契约

- `com.wxauto.server`：本地 FastAPI 规则服务。
- `com.wxauto.tracememo-poller`：仅草稿轮询器。
- `com.wxauto.tracememo-autoreply`：真实发送轮询器。

标签、日志路径或服务联动变化时同步检查 macOS App。

## 影响面

- 配置 bridge：检查 `../core/config.py`、Swift 设置模型和 YAML 往返保真。
- 联系人脚本：检查 TraceMemo 字段解析、稳定 talker、排序和隐私日志。
- 构建脚本：检查输出目录、签名/Info.plist、忽略规则和清理行为。
- 安装脚本：检查升级路径、旧服务卸载、权限说明与非交互环境。

## 验证

优先静态验证和各脚本的安全参数；安装与服务控制需明确授权。

```bash
bash -n scripts/*.sh
python -m pytest -q core/tests/test_app_config.py core/tests/test_tracememo_contacts.py
python -m compileall -q scripts
```

## 继续阅读

- 开发者说明：[`README.md`](README.md)
- macOS 自动化：[`../macos/MEMORY.md`](../macos/MEMORY.md)
- 控制 App：[`../macos/TraceMemoAutoReplyApp/MEMORY.md`](../macos/TraceMemoAutoReplyApp/MEMORY.md)
