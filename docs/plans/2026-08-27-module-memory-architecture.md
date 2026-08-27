# Module Memory Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 为八个一级模块分别创建就近的 `MEMORY.md` 和 `README.md`，并把根级文件改造成渐进式披露入口。

**Architecture:** 根 `AGENTS.md` 只保存全局规则，根 `MEMORY.md` 只保存跨模块地图。每个模块用 `MEMORY.md` 服务 agent，用 `README.md` 服务开发者；模块文件再指向最小必要源码、测试和专项文档。

**Tech Stack:** Markdown、Git、现有 Python/Kotlin/Swift/Shell 项目结构。

---

### Task 1: 建立模块文件骨架

**Files:**

- Create: `core/MEMORY.md`, `core/README.md`
- Create: `server/MEMORY.md`, `server/README.md`
- Create: `macos/MEMORY.md`, `macos/README.md`
- Create: `macos/TraceMemoAutoReplyApp/MEMORY.md`, `macos/TraceMemoAutoReplyApp/README.md`
- Create: `android/MEMORY.md`, `android/README.md`
- Create: `ios/MEMORY.md`, `ios/README.md`
- Create: `scripts/MEMORY.md`, `scripts/README.md`
- Create: `docs/MEMORY.md`, `docs/README.md`

**Step 1:** 从当前根 `MEMORY.md` 按职责迁移事实，不复制易漂移测试数量。

**Step 2:** 每个 `MEMORY.md` 写明何时读取、入口、约束、影响面和验证。

**Step 3:** 每个 `README.md` 写明用途、架构、主要文件、开发入口和限制。

### Task 2: 更新根级阅读路由

**Files:**

- Modify: `AGENTS.md`
- Modify: `MEMORY.md`

**Step 1:** 让 `AGENTS.md` 的任务路由直接指向模块记忆。

**Step 2:** 将根 `MEMORY.md` 改成八模块索引与跨模块契约说明。

**Step 3:** 保留全局安全、隐私、跨实现一致性和完成声明边界。

### Task 3: 验证模块覆盖和链接

**Files:**

- Verify: all created and modified Markdown files

**Step 1:** 检查所有模块对文件存在且非空。

**Step 2:** 提取 Markdown 相对链接并检查目标存在。

**Step 3:** 检查尾随空白、秘密模式和 Git 工作区范围。

**Step 4:** 对照模块清单确认八个模块均能从根索引到达。
