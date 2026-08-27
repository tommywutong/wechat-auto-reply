# Server 模块记忆

## 何时读取

任务涉及 FastAPI、Bearer 鉴权、`/reply`、`/reload`、`/health`、配置热加载、状态路径或客户端协议时读取本文件。

## 模块定位

`server/app.py` 是 Python 核心的薄 HTTP 适配层。它负责组装配置、模型 writer 和 `ReplyEngine`，不应复制决策规则。

## 当前契约

| 路由 | 鉴权 | 作用 |
|---|---|---|
| `POST /reply` | Bearer Token | 将 `MessageIn` 交给引擎并返回 `DecisionOut` |
| `POST /reload` | Bearer Token | 重新加载配置，沿用同一状态文件 |
| `GET /health` | 无 | 只暴露存活状态和配置文件名 |

环境变量：`WXAUTO_CONFIG`、`WXAUTO_STATE`、必填的 `WXAUTO_TOKEN`。Token 缺失时服务必须拒绝启动。

## 不变量

- 使用常数时间比较验证 Token。
- `/health` 不得泄露规则、联系人、Token、消息或模型配置。
- 输入校验留在 Pydantic；业务判断留在 `core`。
- 热加载失败返回可操作的错误，不能把半加载引擎投入服务。
- 不默认监听公网；macOS 推荐拓扑只监听 `127.0.0.1`。

## 客户端影响面

修改 schema 或错误格式时检查：

- `../macos/tracememo_poller.py`
- `../macos/wechat_mac_bot.py`
- `../ios/appium/wechat_ios_bot.py`
- Android `RelayWriter`（仅中继模式）
- 安装脚本与多账号文档

## 验证

```bash
python -m pytest -q
python -m compileall -q server
```

启动集成测试必须使用虚构配置和临时 Token；不要打印 Authorization 头。

## 继续阅读

- 开发者说明：[`README.md`](README.md)
- 核心语义：[`../core/MEMORY.md`](../core/MEMORY.md)
- 部署脚本：[`../scripts/MEMORY.md`](../scripts/MEMORY.md)
