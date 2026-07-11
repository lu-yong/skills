<!-- Source: install-openspec-superpowers-bridge/references/AGENTS.fragment.zh-CN.md -->
<!-- BEGIN OPENSPEC SUPERPOWERS BRIDGE -->
## 工作流路由

本仓库使用 [`superpowers-bridge`](https://github.com/JiangWay/openspec-schemas/tree/main/superpowers-bridge) 把 OpenSpec 和 Superpowers 串起来。具体 artifact 规则以 bridge README 为准，这一节只负责代理路由。

### 入口分流

- 用户先发起叙述式设计讨论或脑暴：先讨论，但不要把内容写到 `docs/superpowers/specs/`。当范围、关键决策、跨系统依赖、验收条件、对话收敛都明确后，再建议 `/opsx:propose`。
- 用户直接执行 `/opsx:new`、`/opsx:ff` 或 `/opsx:propose`：按 schema 流程走。
- 用户明确说是 bug fix、typo、小型配置调整、纯文档变更：直接 PR，不要开 change。
- 已经处于某个 change 中：继续用 `/opsx:continue`、`/opsx:apply`、`/opsx:verify` 或 `/opsx:archive`。

### 何时跳过 opsx

- 新功能、架构变更、破坏性变更：走 opsx。
- 不改变契约的 bug fix、补测试、lint 调整、非破坏性升级、typo、文档、小型配置值调整：跳过 opsx。

### 升级为 opsx 的门槛

只有以下五项全部满足，才把口头脑暴升级成 opsx：

1. 范围已经锁定。
2. 主要设计分支已经收敛。
3. 跨系统依赖已经盘点清楚。
4. 验收条件足够具体。
5. 对话已经进入收敛阶段。

### 反模式

- 把 brainstorming 输出写到 `docs/superpowers/specs/`
- 把 writing-plans 输出写到 `docs/superpowers/plans/`
- 还有阻塞性 TBD 时就开 change
- 对低风险修复也开 change
<!-- END OPENSPEC SUPERPOWERS BRIDGE -->
