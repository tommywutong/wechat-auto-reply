# 构建、安装与运行脚本

本目录把 Python 核心、TraceMemo Reader 运行时、macOS helper、SwiftUI App 和 launchd 服务连接起来。部分脚本会改变本机状态，运行前先看脚本头部说明。

## 安全分类

### 只读或构建

- `build-macos-helpers.sh`
- `build-macos-app.sh`
- `tracememo_contacts.py`（读取本机 TraceMemo）
- `app_config.py` 的读取操作

构建会写 `.build/` 或 `dist/`，这些目录被 Git 忽略。

### 会修改本机状态

- `macos-setup.sh`
- `update-macos-app.sh`（仅在工作区干净且可快进时拉取 `main`）
- `install-tracememo-poller.sh`
- `install-tracememo-autoreply.sh`
- `app_config.py` 的写入操作
- `termux-setup.sh`

这些脚本可能创建虚拟环境、配置、Token、LaunchAgent 或服务。

### 会启动运行链路

- `run-tracememo-poller.sh`：草稿模式。
- `run-tracememo-autoreply.sh`：真实发送模式。
- `ensure-tracememo-runtime.sh`：检查本机 Reader；必要时下载并以托盘模式启动内置 TraceMemo Reader，优先复用已有数据目录。
- `update-macos-app.sh`：检查远端 `main` 并按提交号重建控制 App；本地有未提交修改、分支分叉或网络失败时跳过更新，不覆盖本机内容。
- `run-macos-app.sh`：执行上述更新检查后打开控制面板。
- `watch-tracememo-autoreply.sh`：状态与日志观察。

## 常用入口

构建 macOS 组件：

```bash
bash scripts/build-macos-helpers.sh
bash scripts/build-macos-app.sh
```

首次安装流程：

```bash
bash scripts/macos-setup.sh
```

真实账号环境应先完成 TraceMemo 诊断和草稿验证，再安装自动回复服务。

## 凭据

运行脚本会主动清理继承的敏感环境变量，并通过 [`../core/keychain.py`](../core/keychain.py) 或受保护的兼容 Token 文件读取凭据。不要在脚本、plist、终端输出或文档中硬编码真实密钥。内置 Reader 下载文件会放在用户目录，不进入 Git 仓库。

## 开发检查

```bash
bash -n scripts/*.sh
python -m pytest -q core/tests/test_app_config.py core/tests/test_tracememo_contacts.py
```

Agent 修改本模块前应读取 [`MEMORY.md`](MEMORY.md)。
