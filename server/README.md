# HTTP 决策服务

`server/app.py` 使用 FastAPI 将 Python 回复引擎暴露给 macOS、iOS 参考脚本和可选的 Android 中继模式。

## 启动

```bash
export WXAUTO_CONFIG=core/config.example.yaml
export WXAUTO_STATE=var/state.json
export WXAUTO_TOKEN=<随机且保密的令牌>
uvicorn server.app:app --host 127.0.0.1 --port 8848
```

生产或真实账号环境不要使用示例 Token，也不要把服务无鉴权暴露到局域网或公网。

## API

### `POST /reply`

请求包含会话 ID、名称、正文、群聊/提及状态、平台和账号。响应包含是否回复、原因、文本、延迟与命中规则。请求必须携带：

```text
Authorization: Bearer <WXAUTO_TOKEN>
```

### `POST /reload`

修改 YAML 后重新构造引擎；状态文件保持不变，因此冷却和配额不会因为热加载自动清空。

### `GET /health`

用于本机服务探活，不返回私人规则。

## 责任边界

服务层只处理协议、鉴权和依赖组装。安全顺序、限流、模型模式与状态提交均属于 [`../core/`](../core/)；平台采集和发送属于各客户端。

## 开发

```bash
python -m pytest -q
uvicorn server.app:app --host 127.0.0.1 --port 8848
```

真实启动需要有效配置与 Token。Agent 修改本模块前应读取 [`MEMORY.md`](MEMORY.md)。
