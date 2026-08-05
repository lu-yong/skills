---
name: update-bu1-sdk-issue-conclusion
description: Use when the user wants to complete a BU1-SDK-2007-01-UNIFY Redmine issue; require a numeric issue number, inspect its tracker, the latest local Git commit, and its Gerrit change, draft the tracker-specific fields and a rule-compliant Chinese conclusion, obtain explicit user confirmation, then update only the approved fields.
disable-model-invocation: true
---

# Update BU1-SDK Issue Conclusion

This skill is a two-phase workflow: **determine and draft first, write second**. The Redmine project identifier for `BU1-SDK-2007-01-UNIFY` is `bu1-sdk`.

Load and follow the available **Redmine** skill for authentication, issue API usage, field updates, and write-audit requirements. Load and follow the available **Gerrit** skill for the read-only Gerrit queries. Use the host's native skill-loading mechanism; do not assume a slash command or a particular Agent API.

## Tracker-specific field matrix

The issue's exact Redmine tracker name controls which metadata fields this workflow may update. The `结论` field is always drafted and updated by this skill in addition to the fields listed here.

| Tracker | Required fields to draft and update |
| --- | --- |
| `功能` | `状态`, `接口调整`, `%完成` |
| `错误` | `状态`, `接口调整`, `%完成`, `问题性质`, `问题归属`, `公版问题类别` |
| `节点` | `状态`, `%完成` |
| `需求` | `状态` |
| `测试` | `状态`, `%完成` |

Use the exact `issue.tracker.name` returned by Redmine. If the tracker is missing or is not one of these five values, ask the user which field matrix applies before drafting. Do not update fields that are not required for the issue's tracker.

## Phase 1: Determine the approved field values and draft

1. **Validate the input.** Ask the user for one Redmine issue number if it was not supplied. Accept only a positive decimal integer matching `^[1-9][0-9]*$`. Treat the number as the Redmine issue ID, not as a project identifier. Reject extra text, URLs, ranges, comma-separated IDs, and non-decimal IDs.

2. **Verify the issue belongs to BU1-SDK.** Read the issue with its tracker, custom fields, `done_ratio`, allowed statuses, and relevant history. Confirm that `issue.project.identifier` is exactly `bu1-sdk`. Stop and ask for a corrected issue number when the issue does not exist, access is denied, or the project identifier differs. Never update an issue based only on its title or project name.

3. **Load the local conclusion snapshot.** Read [references/bu1-sdk-conclusion-rules.md](references/bu1-sdk-conclusion-rules.md) before drafting. Record its `source_version`, `checked_at`, and `checked_by`. The local snapshot is the only rules source during this workflow; do not access online Wiki, refresh rules, or modify the reference. If the snapshot is missing, metadata is invalid, `checked_at` is not a valid UTC ISO 8601 timestamp, or it is more than 30 days old, stop and ask the user to call [refresh-bu1-sdk-rules](../refresh-bu1-sdk-rules/SKILL.md). If the user explicitly accepts an old but complete snapshot after a failed refresh, continue only with that explicit permission and disclose the snapshot age in the draft and final report. If `refresh-bu1-sdk-rules/.refresh.pending` exists, stop until the refresh transaction is completed or recovered according to that skill.

4. **Resolve the tracker matrix and fields.** Read the exact tracker name and select the required field set from the matrix above. Always locate the `结论` custom field. Locate the other custom fields only when required by the selected tracker. For each required custom field, record its numeric field ID, current value, and available option values. Treat `状态` as the standard Redmine `status_id`, and `%完成` as the standard Redmine `done_ratio` integer from 0 to 100. Record the current status name/ID and allowed target statuses. If a required field is absent or its option mapping is unavailable, ask the user or inspect project custom-field metadata before drafting. Never guess a field ID or invent an option value.

5. **Inspect the current Git reference.** In the current Git repository:
   - Resolve the repository root with `git rev-parse --show-toplevel`.
   - Read the most recent commit with its full message, author/date, commit SHA, and parent relationship.
   - Inspect the commit diff and changed-file summary (`git show`/equivalent). Summarize only behavior supported by the diff; distinguish facts from inferences.
   - If there is no repository, no commit, or the worktree is not the repository relevant to the issue, ask the user to switch to the correct repository or provide the repository context.

6. **Resolve the Gerrit change through the Gerrit skill.**
   - Determine the Gerrit instance from the Git remote. Use the internal instance for `git.nationalchip.com` and the external instance for `gerrit.nationalchip.com`; ask the user to choose when the host is ambiguous.
   - Use the latest commit SHA to query the selected Gerrit instance for the matching change. When available, use the commit's `Change-Id` footer as a second identity check. Obtain the numeric Gerrit change number (`_number`) and fetch its detail. Use the current revision or the exact matching revision as appropriate.
   - Inspect changed files and the patch needed to report the change accurately. Do not inspect or infer testing, review, or dependency completion from Gerrit labels, branch state, or other repository evidence. Respect the Gerrit skill's XSSI parsing, authentication, TLS, and secret-handling rules.
   - If no matching change can be found, or multiple changes cannot be disambiguated, ask the user for the Gerrit instance/change identity. Do not fabricate a change number.

7. **Determine the target values for the selected tracker.** Analyze the issue, local commit, Gerrit metadata, current field values/options, and cached rules. Determine only the fields required by the tracker matrix, plus `结论`:
   - `状态`: choose a target status only when the completion or feedback/rejection decision is supported. Use the actual status ID returned by Redmine. Do not assume `已解决` merely because code changed; when the target is `已解决`, require the user's explicit four-line prerequisite confirmation below and do not independently verify those items.
   - `%完成`: choose an integer from 0 to 100 that reflects the confirmed progress. Ask when the appropriate percentage is not explicit.
   - `问题性质`: classify as `当前版本修改引入`, `上个版本修改引入`, `历史遗留`, or an exact available alternative. Ask when the version relationship cannot be established.
   - `问题归属`: classify as `应用`, `平台`, or `芯片` according to the affected ownership boundary. Ask when the diff and issue do not establish this.
   - `接口调整`: determine whether the change is an interface or scheme-specification change using the rules and exact available field option. Ask when the evidence does not establish the value.
   - `公版问题类别`: select an exact available category from the issue/project options using the wiki definitions. Ask when more than one category is plausible or no category is supported.
   - `结论`: write the rule-compliant conclusion using the verified Gerrit change number and only established facts.

8. **Ask for missing facts before drafting.** If any required target field cannot be determined reliably, pause and ask focused questions listing the tracker, current value, candidate values, and evidence gap. Do not independently detect or collect evidence for the four patch/testing prerequisites. When the proposed target status is `已解决`, require the user to confirm them in exactly this format:
   ```text
   提交前自测：已完成/未完成
   干净版本补丁测试：已完成/未完成
   提交者自 Review+1：已完成/未完成
   依赖补丁：无/有，且已合入 sdk-release/有但未合入
   ```
   Treat this confirmation as the user's guarantee: do not ask for logs, Gerrit labels, test output, or dependency evidence, and do not re-check these four items. Only propose `已解决` when the response says the first three are `已完成` and the dependency is `无` or `有，且已合入 sdk-release`. After answers arrive, rerun only the affected field and conclusion checks.

9. **Apply the conclusion rules.** The conclusion must contain these three elements with concrete content:
   - `问题原因：` why the issue occurred, supported by the issue and commit analysis;
   - `处理方案：` what was changed, including the Gerrit change number when a patch exists;
   - `影响范围：` affected modules, targets, branches, versions, or a precise statement of the verified scope.

   For `错误` issues with `问题性质` equal to `当前版本修改引入` or `上个版本修改引入`, include `修改补丁：{{patch(<Gerrit change number>)}}` and the required patch-cause wording. For `规格变更`, include the cause, before/after differences, usage examples, affected project/module/system/chip scope, and patch where applicable. For `已拒绝` or `反馈`, include the explicit reason or analysis-process conclusion and the required agreement information. Do not claim any status or scope that was not established or supplied by the user. Handling a patch's `abandoned` status is outside this skill's scope; the user performs that operation separately, and it is not an update-conclusion prerequisite. For the four `已解决` prerequisites, the user's exact confirmation is sufficient and no additional evidence is required.

10. **Present the complete draft and stop.** Show the target issue/project and exact tracker, local rule source, `source_version`, `checked_at`, and `checked_by`, latest Git commit SHA, Gerrit instance/change number, evidence-based change summary, and a field-change table containing current value and proposed value for exactly the required tracker fields plus `结论`. Include `%完成` when required and omit non-required metadata fields. When the target is `已解决`, include the user's exact four-line prerequisite confirmation alongside the draft; do not add an evidence request. Then show the exact proposed `结论` in a fenced text block. State that no Redmine write has happened. Ask for explicit confirmation such as `确认更新`; a vague acknowledgement or a request for edits is not confirmation.

Phase 1 is complete only when the issue is verified as `bu1-sdk`, the tracker matrix is selected, the Gerrit change identity is verified, every required field has a confirmed proposed value, every required conclusion element is known, and the exact combined update draft has been shown to the user. When the target status is `已解决`, the user's four-line prerequisite confirmation must also have been received and must contain only allowed values.

## Phase 2: Update the approved tracker fields and conclusion

1. Re-check that the user's latest message explicitly confirms the displayed combined draft. If the user requests any edit, apply the edit, rerun the tracker-matrix and conclusion checks, display the revised combined draft, and wait for confirmation again.

2. Before writing, re-read the issue and verify that the project is still `bu1-sdk`, the tracker has not changed, all required field IDs are unchanged, and current values have not changed in a way that invalidates the draft. Re-read the local rule snapshot metadata and confirm its `source_version`, `checked_at`, `checked_by`, and content hash are unchanged from Phase 1; a changed or newly refreshed snapshot invalidates the draft and requires regeneration and confirmation. If any of these changed, refresh the analysis and ask for confirmation again.

3. Send one authenticated `PUT /issues/<issue-id>.json` request with `Content-Type: application/json`. In the same request, update only the fields required by the selected tracker, plus the conclusion:
   - `issue.status_id` to the approved target status ID;
   - `issue.done_ratio` to the approved percentage when the matrix requires `%完成`;
   - required custom fields among `接口调整`, `问题性质`, `问题归属`, and `公版问题类别`, using their discovered IDs;
   - the `结论` custom field using its discovered ID;
   - `issue.notes` with a concise Chinese audit note beginning exactly with `由 luyong-AI 操作：` and listing the issue ID plus the actual changed field values and conclusion summary.

   Do not update metadata fields that the selected tracker does not require. Do not update assignee, tags, target version, dates, relations, or unrelated custom fields. Do not claim success before the request returns success.

4. Re-read the issue after the PUT and verify the tracker, approved status name/ID, approved `done_ratio` when applicable, every required custom-field value, and the conclusion text. Report the issue ID, project, tracker, each updated field, timestamp if returned, and the Gerrit change number. Report HTTP or verification failures plainly and do not claim completion when verification fails.
