# iOS 参考实现模块记忆

## 何时读取

任务涉及 iPhone 自动化能力边界、Appium、WebDriverAgent、Theos、tweak、注入或 macOS 代理方案比较时读取本文件。

## 模块定位

`ios/` 包含两条高风险参考路线，不是可直接上架的普通 iOS App。未越狱第三方 App 无法跨沙盒读取或发送微信消息。

## 子模块

### `appium/`

- `wechat_ios_bot.py`：用 WebDriverAgent 操作前台微信并调用 HTTP 决策服务。
- `requirements.txt`：Appium Python 依赖。
- `README.md`：环境、WDA、启动和限制。

不要求越狱，但设备需连接，微信需常驻前台，选择器会随 UI 变化。

### `tweak/`

- `Tweak.x`：注入微信进程的 hook 实现。
- `WXAutoReply.plist`：目标进程过滤。
- `Makefile`：Theos 构建。
- `control`：包元数据。
- `README.md`：越狱/重签安装和版本适配。

需要越狱或重签注入，类名和方法签名与具体微信版本强绑定。

## 不变量

- 不把“技术上可行”描述成 App Store 或普通沙盒 App 可行。
- Appium 默认先用 `--dry-run`；没有明确授权不操作真实设备和微信。
- tweak 没有对应设备、微信版本和 runtime 证据时，只能称静态参考。
- 两条路线都通过服务获得确定性决策，不能在自动化脚本中绕过安全规则。
- 任何凭据都不得写入源码、包元数据或日志。

## 影响面

- HTTP schema 变化：检查 Appium `EngineClient`。
- 微信 UI 变化：只修改 Appium 选择器并补可复现证据，不外推其他版本。
- hook 变化：记录目标微信版本、类/方法证据和回退方式。
- 面向普通 iPhone 用户的文档仍优先推荐 macOS 代理方案。

## 验证

```bash
python -m compileall -q ios/appium
python ios/appium/wechat_ios_bot.py --help
```

Theos 构建、WDA 连接与真实设备操作依赖外部环境，需单独说明验证层级。

## 继续阅读

- 开发者说明：[`README.md`](README.md)
- 能力分析：[`../docs/ios-feasibility.md`](../docs/ios-feasibility.md)
- Appium 操作：[`appium/README.md`](appium/README.md)
- tweak 操作：[`tweak/README.md`](tweak/README.md)
