# Skills 仓库

这是面向团队的 Agent 技能集合。每项技能的入口为目录中的 `SKILL.md`，说明适用场景、步骤和完成条件。通用技能可在不同项目复用，公司流程技能使用 Nationalchip 的 Gerrit、Redmine 和 BU1-SDK 规则。

## 在你的 Agent 中使用

保留仓库目录结构，让宿主发现需要的技能。可以把技能目录链接到宿主的技能目录，或在宿主配置中指向仓库。要适配到 pi、Codex、Claude Code 或 OpenCode，可先让 Agent 检查技能发现方式、命令依赖和本地凭据。标有 `disable-model-invocation: true` 的技能按宿主支持的方式手动调用。

Gerrit 和 Redmine 的 CLI 使用 Python 3，Gerrit 还需要 curl。运行 `python3 gerrit/scripts/gerrit.py instances` 查看实例，用 `python3 redmine/scripts/redmine.py --help` 查看 Redmine 子命令。查询实例、认证方式、TLS 回退和评审推送主机由同一份 [Gerrit 实例表](gerrit/instances.json) 管理。仅登记为推送目标的主机需要显式指定查询实例。认证配置见 [Gerrit](gerrit/SKILL.md) 和 [Redmine](redmine/SKILL.md)。

提交和推送、结论回写与规则刷新都由业务脚本校验用户确认。pi 用户可按 [确认门禁接入说明](confirm-gate/README.md) 加载扩展，了解结构化选择和写入授权的分工，以及 `bash` 拦截与本地凭据的执行范围。

## 技能目录

### 公司开发流程

- 按本地规则和指定范围生成提交，确认后推送 Gerrit 评审。[commit-gerrit](commit-gerrit/SKILL.md)
- 核对 Redmine issue、本地提交与 Gerrit 变更，确认后写回中文结论并复查。[update-issue-conclusion](update-issue-conclusion/SKILL.md)
- 从 Redmine Wiki 刷新 BU1-SDK 的两份本地规则快照。[refresh-bu1-sdk-rules](refresh-bu1-sdk-rules/SKILL.md)
- 只读查询 Gerrit 变更、patchset、文件、项目和账号，或定位本地提交对应的评审。[gerrit](gerrit/SKILL.md)
- 查询和管理 Redmine issue、项目、附件和工时等数据。[redmine](redmine/SKILL.md)

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
node --test confirm-gate/pi-extension/
```
