---
name: commit-gerrit
description: Use when explicitly asked to create or amend a commit and send it to Nationalchip Gerrit for review, using a verified Redmine issue and separately approved Git actions.
disable-model-invocation: true
---

# 提交 Gerrit 评审补丁

在目标 Git 工作区运行 `python3 "$SKILL_DIR/scripts/commit_gerrit.py"`，`SKILL_DIR` 指向本文件所在目录。先检查交互宿主是否提供 `confirm_gate`，缺少时停止。每次暂存、提交或推送都需要当次计划的独立确认。接入方法见 [确认门禁](../confirm-gate/README.md)。

## 检查并起草

1. 先运行 `preflight`，核实本地工作分支、唯一的 remote 和目标分支、有效 push URL、[Gerrit 实例表](../gerrit/instances.json)中的推送主机、远端目标分支和可执行的 `commit-msg` hook。检查失败时停止，由用户修正工作区配置。
2. 取得一个匹配 `^[1-9][0-9]*$` 的 Redmine issue ID。用 [Redmine CLI](../redmine/SKILL.md) 的 `issue <id>` 核实可访问，记录项目标识、标题、跟踪类型和状态。读取 [本地 Gerrit 规则快照](references/bu1-sdk-gerrit-rules.md)，记录来源、`source_version`、`checked_at` 和 `checked_by`。由用户另行调用 [规则刷新技能](../refresh-bu1-sdk-rules/SKILL.md) 更新快照。
3. 检查 HEAD、完整索引、工作区 diff 和未忽略的未跟踪路径。默认范围是整个仓库；仅在用户指定时传入 `--scope` 的精确文件路径。区分已有暂存版本和待暂存修改，检查敏感、生成或无关文件。范围外已有暂存时展示冲突，用结构化选择决定是否扩展范围或由用户处理暂存区。只在用户选择扩展后按扩大后的范围重新起草。保留用户现有暂存版本。
4. 按快照确定提交者要求、Type、Redmine ID、Subject、Body 和 Footer。Type 有歧义时用结构化选择。规则、提交者角色或影响执行的依赖状态待确认时，先向用户核实。以 diff 为依据写完整消息，Subject 用中文动词开头，遵守长度和标点要求。新提交由已有 `commit-msg` hook 添加 `Change-Id`。用户明确表示未自测或要求帮助时，先处理自测；其余情况按快照的提交者保证处理。自 Review+1、Reviewer、依赖补丁和干净版本全功能测试的状态只按已知事实报告。
5. 用 `ask_user_question` 选择`创建新提交`或`amend 当前提交`。新提交的消息文件包含完整草稿。amend 的消息文件只包含基于实际修改的追加段；执行器保留现有 Subject、Body 和 Footer，把追加段放入 Footer 前的正文。无法可靠识别 Footer 或生成真实追加段时停止并询问。将消息文件放在目标 Git 仓库之外。

结构化选择只采用本次问题无错误、未取消的 `kind: option` 答案，并按本次问题文本和选项映射匹配。展示全部候选；超过四项时每批最多三项候选和一个 `下一批候选`。备注和自由文本只提供上下文。界面不可用或用户退出时停止。

## 依次确认并执行

每一步先展示计划，包括完整消息或推送 SHA、范围及目的地；用该计划的 `action_id` 调用 `confirm_gate`，只有 `approved` 才执行对应命令。现场状态变化或用户要求改稿时，从受影响的步骤重做检查和计划。取消、拒绝或工具失败时停在当前阶段。

| 操作 | 生成计划 | 经当次确认后执行 |
| --- | --- | --- |
| 暂存 | `stage --plan --issue <id> --mode <new或amend> --message-file <文件>`，需要限定范围时加 `--scope <路径...>` | `stage --action <暂存 action_id>` |
| 提交 | `commit-plan --mode <new或amend> --stage-action <成功执行的暂存 action_id>` | `commit --action <提交 action_id>` |
| 推送 | `push-plan --commit-action <成功执行的提交 action_id> --sha <提交返回的完整 SHA>` | `push --action <推送 action_id>` |

暂存前展示 Redmine 任务、变更概况、规则来源、已有暂存及待暂存路径、工作区快照和有效目的地。将计划的 remote、有效 push URL 和目标分支与预检结果核对，发现变化时重新预检和起草。提交前展示最终消息，amend 时展示合成后的整条消息。脚本校验暂存差异，以及提交结果的树、消息和 Change-Id。核验失败时报告已发生的 Git 操作，停止后续步骤。推送只使用已核验 SHA 对应的 `refs/for/<目标分支>`，推送失败后保留本地提交并报告错误。

推送成功后报告 Redmine ID、SHA、是否 amend、提交消息摘要、工作分支、remote、目标分支、评审 ref 和可用的 Gerrit 结果。分别报告干净版本补丁功能测试和自 Review+1 状态，缺少证据时标为待完成或未知。
