# 项目文档地图

本目录保存跨模块的专项说明。若只修改单个代码模块，先读取该模块自己的 `README.md` 和 `MEMORY.md`；涉及部署、平台能力或完整工作流时再进入这里。

## 平台与功能

- [`android-setup.md`](android-setup.md)：Android 通知监听、无障碍兜底、内嵌引擎与验证。
- [`macos-app.md`](macos-app.md)：SwiftUI 控制 App、服务状态、设置、会话和日志。
- [`tracememo-macos-draft-mode.md`](tracememo-macos-draft-mode.md)：TraceMemo 字段诊断、草稿模式和端到端准备。
- [`ios-feasibility.md`](ios-feasibility.md)：iOS 沙盒边界、Appium、tweak 与 macOS 代理比较。
- [`ios-companion.md`](ios-companion.md)：Objective-C/UIKit iPhone 控制端的构建、配对和安全边界。

## 部署

- [`deployment.md`](deployment.md)：按设备类型选择部署方案。
- [`multi-account.md`](multi-account.md)：账号身份、跨端去重、状态隔离和多服务拓扑。

## 设计和计划

- [`../PRODUCT.md`](../PRODUCT.md)：macOS App 产品原则。
- [`../DESIGN.md`](../DESIGN.md)：视觉、布局、控件和无障碍规则。
- [`plans/`](plans/)：具体功能的设计与实施计划。

## 面向不同读者

- 项目总览：[`../README.md`](../README.md)
- 非技术安装：[`../新手指南.md`](../新手指南.md)
- Agent 全局规则：[`../AGENTS.md`](../AGENTS.md)
- Agent 模块索引：[`../MEMORY.md`](../MEMORY.md)

维护本目录前请读取 [`MEMORY.md`](MEMORY.md)，避免把验证范围、第三方状态或私人信息写成永久事实。
