---
name: update-issue-conclusion
description: Use when explicitly asked to draft and update a Redmine issue conclusion from the issue, latest local Git commit, and corresponding Gerrit change.
disable-model-invocation: true
---

# 更新 Redmine 结论

开始前检查交互宿主是否提供 `confirm_gate`。缺少该工具时停止并说明所需环境。CLI 用法见 [Redmine](../redmine/SKILL.md) 和 [Gerrit](../gerrit/SKILL.md)。

## 收集证据并起草

1. 取得一个匹配 `^[1-9][0-9]*$` 的 issue ID。用 Redmine CLI 的 `issue <issue-id>` 读取项目、跟踪类型、字段和日志。核实唯一的 `结论` 字段及其当前值。任务不可读或字段无法确定时停止。
2. 读取 [本地结论规则快照](references/bu1-sdk-conclusion-rules.md)，记录 `source_version`、`checked_at` 和 `checked_by`。按快照覆盖的场景起草，缺少规则时请用户提供。需要刷新快照时由用户单独调用 [refresh-bu1-sdk-rules](../refresh-bu1-sdk-rules/SKILL.md)。
3. 在与任务相关的 Git 仓库查看 HEAD 的完整 SHA、提交消息、作者、时间、父提交和 diff。仓库或提交不匹配时请用户补充上下文。
4. 调用 Gerrit CLI `resolve-commit --sha <完整 SHA>` 核对关联变更。根据 CLI 的结果，补齐经用户选择的 `--instance`、`--project`、`--branch` 或 `--pick <变更号>`，并重查。查询失败、候选为空或已选变更状态有别于 `NEW` 时停止。对选中的 revision 调用 `files` 和 `patch`，记录实例、数字变更号、项目、分支、状态、revision SHA，以及使用精确 SHA 或 `current_revision` 的匹配依据。已核实的 patch 编号才可填入 `{{patch(...)}}`。
5. 按快照起草简洁的中文结论，依据任务和变更描述原因、方案和影响范围。无法核实的范围写为待确认。对 `错误` 跟踪类型，按现有 `问题性质` 选用结构；字段为空时请用户从 `历史遗留`、`当前版本修改引入`、`上个版本修改引入` 中选择，该选择仅用于拟稿。补丁引入场景需要分别核实引入补丁和修复补丁。按快照处理 `规格变更`、`已拒绝` 和 `反馈`。需要确认同意事实时分别询问软件版本管理员是否同意拒绝、任务创建者是否同意反馈，用各自的两项选择。事实未获确认或结论结构改变时，按当前稿件重新核实。测试、评审和依赖完成情况需要独立证据。

## 结构化选择

用 `ask_user_question` 处理 Gerrit 候选、问题性质和同意事实。展示完整候选及证据；超过四项时每批最多三项候选和一个 `下一批候选`，保持显示顺序。两项选择无法覆盖的单候选页面可用 `停止并补充上下文` 作为退出项。把保留词、过长或重复的候选标签换成 `候选 N`，在描述中写出完整值。只采用当前问题无错误、未取消的结构化 `kind: option` 答案，并按该次问题文本和标签映射匹配。翻页、备注和自由文本不产生选项结果。界面不可用或用户退出时停止。

## 授权、执行与核验

先展示 issue ID、项目、跟踪类型、规则元数据、Git 和 Gerrit 证据、旧结论和拟定的完整文本。若用户要求修改，复核受影响的事实并重拟。定稿后用 Redmine CLI 调用 `plan-conclusion <issue-id> --conclusion <结论全文>`，按照 [确认门禁](../confirm-gate/README.md) 用返回的 `action_id` 调用 `confirm_gate`。用户取消、拒绝或工具失败时停止。确认后有新事实或草稿变化时，重做相关检查并生成新计划。

仅在工具返回 `approved` 后调用 `apply-conclusion --action-id <action_id>`。执行器重新核对 Redmine 实例、规则快照和任务状态后领取一次性凭据，在同一请求中提交审批的 `结论` 和审计备注，然后回读。现场变化时重做分析和确认。若写入已接受而回读失败，报告写入状态和核验失败，避免直接重试 PUT。核验通过后报告 issue ID、项目、跟踪类型、最终结论、可用的更新时间和 Gerrit 匹配依据。
