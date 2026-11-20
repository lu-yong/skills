# Skills 仓库

这是 Agent 技能集合。每项技能的入口为目录中的 `SKILL.md`，说明适用场景、步骤和完成条件，可在不同项目复用。Nationalchip 的 Gerrit、Redmine 和 BU1-SDK 流程技能（`gerrit`、`redmine`、`commit-gerrit`、`update-issue-conclusion`、`refresh-bu1-sdk-rules`）以及它们用的确认门禁已迁到团队仓库 `ai_home`，在那里安装和维护。

## 在你的 Agent 中使用

保留仓库目录结构，让宿主发现需要的技能。可以把技能目录链接到宿主的技能目录，或在宿主配置中指向仓库。要适配到 pi、Codex、Claude Code 或 OpenCode，可先让 Agent 检查技能发现方式、命令依赖和本地凭据。标有 `disable-model-invocation: true` 的技能按宿主支持的方式手动调用。

## 技能目录

### 设计、评审和测试

- 用共用术语讨论模块接口、职责与可测试性。[codebase-design](codebase-design/SKILL.md)
- 找出阻碍演进的模块接口，比较可深化的重构机会。[improve-codebase-architecture](improve-codebase-architecture/SKILL.md)
- 逐轮追问设计决策并给出推荐答案，需要记录术语和 ADR 时用文档版。[grilling](grilling/SKILL.md)、[grill-with-docs](grill-with-docs/SKILL.md)
- 从规格、规范与设计、安全与可靠性三条独立路径审查改动。[code-review](code-review/SKILL.md)
- 用 red → green → refactor 实现并验证每个可观察行为。[tdd](tdd/SKILL.md)
- 搭一次性原型验证状态模型、逻辑或界面方向。[prototype](prototype/SKILL.md)

### 文档和跨会话协作

- 写出让首次接触项目的读者能用的技术文档。[humanize-tech-docs](humanize-tech-docs/SKILL.md)
- 维护领域模型、术语表和 ADR。[domain-modeling](domain-modeling/SKILL.md)
- 把跨会话工作整理成可逐项解决的决策工单。[wayfinder](wayfinder/SKILL.md)
- 把计划或对话拆成带依赖关系的工单。[to-tickets](to-tickets/SKILL.md)
- 把当前工作压缩成交接文档。[handoff](handoff/SKILL.md)
- 查阅技能编写和维护原则。[writing-great-skills](writing-great-skills/SKILL.md)

### OpenSpec

- 安装、升级并验证适用于 AOSP Repo 项目的 `aosp-repo` schema。[install-openspec-aosp-repo](install-openspec-aosp-repo/SKILL.md)
- 安装、升级并验证 `tdd-spec` schema，让 OpenSpec apply 按可观察行为落实 TDD。[install-openspec-tdd](install-openspec-tdd/SKILL.md)
- 配置 OpenSpec 产出文档时使用的自然语言。[openspec-language-config](openspec-language-config/SKILL.md)

## 本地检查

```bash
python3 -m unittest discover -s tests
```
