# Skills 仓库

> 读者基线：组内同事，日常使用某种编码 Agent（pi、Codex、OpenCode、Claude Code、Cursor 等），不了解这个仓库里的任何约定。

这是我日常积累的一套 Agent 技能（skill）集合：每个目录是一个技能，入口都是该目录下的 `SKILL.md`，用自然语言描述"什么时候用、怎么做"。其中一部分绑定了我们公司的基础设施（Nationalchip 的 Gerrit / Redmine），另一部分是通用的工程方法类技能，拿到任何项目都能用。

## 拿到仓库后第一件事：让你的 Agent 读一遍并适配

**不要直接复制进你的 skill 目录就开用。** 组内各人用的 Agent 工具不同，这些技能是在我的环境下写和调试的——我主要用 pi，有时用 Codex 和 Claude Code，偶尔用 OpenCode，技能格式沿用 Claude Code 的 `SKILL.md` 约定；日常开发在公司的 Ubuntu 环境，也有部分在我个人的 macOS 上。你的工具和系统组合大概率跟我不同，里面存在三类需要适配的东西：

1. **技能加载机制不同。** 这些技能用的是 Claude Code 式的 `SKILL.md` frontmatter（如 `disable-model-invocation: true` 表示只能手动 `/技能名` 触发）；pi / Codex / OpenCode 等工具的技能发现方式和字段支持各不一样，可能需要改放置目录或在 AGENTS.md 里挂路由（仓库里的 `install-openspec-superpowers-bridge` 就是干这个的一个例子）。
2. **环境绑定的内容。** `commit-gerrit`、`gerrit`、`redmine`、`update-issue-conclusion`、`refresh-bu1-sdk-rules` 依赖公司 Gerrit / Redmine 的地址和你个人的认证凭据；个别技能里可能残留我机器上的绝对路径，macOS 与 Ubuntu 的命令差异（如 `sed`、`open` 等）也要留意。
3. **技能之间的交叉引用。** 例如 `humanize-tech-docs` 会引用 `domain-modeling`，`improve-codebase-architecture` 会用到 `codebase-design` 的词汇表。拆开单拿一个技能时，要么把被引用的一起拿走，要么让 Agent 知道缺了哪个。

所以推荐的做法是，把仓库丢给你自己的 Agent，说一句类似：

> 读一遍这个 skills 仓库里每个目录的 SKILL.md，告诉我哪些技能在你（当前 Agent 工具）里能直接用、哪些需要改加载方式、哪些引用了我环境里没有的地址/凭据/路径，然后帮我适配到我的环境。

## 里面有什么

按你想做的事找：

**想把代码提交到公司流程里**

- `commit-gerrit` — 按本地规则快照提交 Gerrit 评审（要求 issue 号、确认提交草稿、确认目标分支）。
- `update-issue-conclusion` — 完成 Redmine issue 的中文结论：核对 issue、本地提交和 Gerrit change 后草拟，确认后写回。
- `refresh-bu1-sdk-rules` — 从 Redmine Wiki 刷新本地的 BU1-SDK Gerrit/Redmine 规则快照。

**想查公司系统**

- `gerrit` — 只读查询 Gerrit：change 详情、patch、改动文件等。
- `redmine` — 查询和操作 Redmine 的 issue、项目、工时等。

**想做设计、评审、写代码**

- `codebase-design` — 深模块设计的共享词汇；其他设计类技能的基础。
- `grilling` / `grill-with-docs` — 让 Agent 对你的方案穷追猛打地提问；后者边问边沉淀 ADR 和术语表。
- `improve-codebase-architecture` — 扫描代码库找可深化的模块，出 HTML 报告。
- `code-review` — 从规格、设计规范、安全可靠性三条独立轴评审改动。
- `tdd` — 测试驱动开发流程。
- `prototype` — 快速搭一次性原型验证状态模型或 UI 方向。

**想写文档、建领域模型**

- `humanize-tech-docs` — 把技术文档写成/修成零上下文新读者能用的样子。
- `domain-modeling` — 维护项目领域模型、术语表和 ADR。

**想管理大块工作、跨会话协作**

- `wayfinder` — 把超出单次会话容量的大工程规划成 tracker 上的决策工单。
- `to-tickets` — 把计划或当前对话拆成带阻塞关系的 tracer-bullet 工单。
- `handoff` — 把当前对话压缩成交接文档给下一个会话。

**Android 相关**

- `adb` — adb 的设备诊断、日志收集、HAL/服务调试等工作流。

**维护技能本身 / 跨工具桥接**

- `writing-great-skills` — 写技能的参考规范；改这个仓库里的技能前先看它。
- `install-openspec-superpowers-bridge` — 在 Codex/OpenCode 里桥接 OpenSpec 与 Superpowers。
- `openspec-language-config` — 配置 OpenSpec 用指定自然语言产出文档。

## 反馈

用出问题（尤其是在非 Claude Code 的工具里跑不起来），或者适配出了更通用的写法，直接找我，或改完发我合回来——这个仓库的价值在于大家的适配经验能沉淀回来。
