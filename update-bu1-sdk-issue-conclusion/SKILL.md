---
name: update-bu1-sdk-issue-conclusion
description: Use when the user wants to complete a BU1-SDK-2007-01-UNIFY Redmine issue; require an issue number, inspect the issue, latest local Git commit, and its Gerrit change, draft a rule-compliant Chinese conclusion, obtain explicit confirmation, then update the conclusion.
disable-model-invocation: true
---

# Update BU1-SDK Issue Conclusion

This skill is a two-phase workflow: **determine and draft first, write second**. The Redmine project identifier for `BU1-SDK-2007-01-UNIFY` is `bu1-sdk`.

## Questionnaire interaction contract

Use `questionnaire` for every finite choice, prerequisite confirmation, or write authorization, with stable `id`/`value` pairs, descriptive options, and `allowOther: false`. Read only structured `details.answers`: explicit cancel or user cancellation stops without a Redmine write; invalid/missing results repeat the same questionnaire; free-form text never authorizes a write. Use ordinary conversation only for open-ended values such as an issue number, an edit request, or a reason. Do not use the `qna` extension's Q&A summary. Record selected `id`, `value`, and returned label (when present).

Load and follow the available **Redmine** skill for authentication, issue API usage, the conclusion custom field, and write-audit requirements. Load and follow the available **Gerrit** skill for the read-only Gerrit queries. Use the host's native skill-loading mechanism; do not assume a slash command or a particular Agent API.

## Phase 1: Analyze the issue and draft the conclusion

1. **Validate the input.** Ask the user for one Redmine issue number if it was not supplied. Accept only a positive decimal integer matching `^[1-9][0-9]*$`. Treat the number as the Redmine issue ID, not as a project identifier. Reject extra text, URLs, ranges, comma-separated IDs, and non-decimal IDs.

2. **Verify the issue belongs to BU1-SDK.** Read the issue with its tracker, custom fields, journals, and relevant history. Confirm that `issue.project.identifier` is exactly `bu1-sdk`. Locate the `结论` custom field and record its numeric field ID and current value. Read the exact tracker name and existing issue context as input to the conclusion rules. Stop and ask for a corrected issue number when the issue does not exist, access is denied, or the project identifier differs. Never update an issue based only on its title or project name.

3. **Load the local conclusion snapshot.** Read [references/bu1-sdk-conclusion-rules.md](references/bu1-sdk-conclusion-rules.md) before drafting. Record its `source_version`, `checked_at`, and `checked_by`. Apply the reference's 快照使用与刷新 section as the single source of snapshot-validity conditions: when the snapshot is missing, metadata invalid, `checked_at` unparseable, a refresh transaction is pending, or the scenario is uncovered, stop and route to [refresh-bu1-sdk-rules](../refresh-bu1-sdk-rules/SKILL.md) exactly as that section directs. When `checked_at` is older than 30 days and the old-snapshot fallback is applicable, display the snapshot metadata and call `questionnaire` with one question whose `id` is `expired_snapshot_decision`, label is `规则快照`, prompt asks whether to use the displayed old snapshot for this run, options are `{ "value": "accept_old", "label": "本次使用旧快照", "description": "继续本次流程，并在草稿和最终报告中披露旧快照的 checked_at 和过期状态。" }` and `{ "value": "refresh_first", "label": "先刷新规则", "description": "停止本次流程，先调用 refresh-bu1-sdk-rules。" }`, and `allowOther` is `false`. Continue only for the exact structured `value: "accept_old"`; `refresh_first` or user cancellation stops without a Redmine write; invalid/missing results re-call the same questionnaire. Disclose the accepted old snapshot exactly as the reference section mandates. Do not access online Wiki, refresh rules, or modify the reference.

4. **Inspect the current Git reference.** In the current Git repository:
   - Resolve the repository root with `git rev-parse --show-toplevel`.
   - Read the most recent commit with its full message, author/date, commit SHA, and parent relationship.
   - Inspect the commit diff and changed-file summary (`git show`/equivalent). Summarize only behavior supported by the diff; distinguish facts from inferences.
   - If there is no repository, no commit, or the worktree is not the repository relevant to the issue, ask the user to switch to the correct repository or provide the repository context.

5. **Resolve the Gerrit change through the Gerrit skill, deterministically.**
   - Determine the Gerrit instance from the Git remote. Use the internal instance for `git.nationalchip.com` and the external instance for `gerrit.nationalchip.com`. When the host is ambiguous, display the evidence and call `questionnaire` with one question whose `id` is `gerrit_instance_choice`, label is `Gerrit 实例`, prompt asks which company Gerrit instance contains the change, options are `{ "value": "internal", "label": "内部 Gerrit", "description": "使用 git.nationalchip.com 查询。" }` and `{ "value": "external", "label": "外部 Gerrit", "description": "使用 gerrit.nationalchip.com 查询。" }`, and `allowOther` is `false`. Use only the exact structured answer. User cancellation stops; invalid/missing results re-call the same questionnaire; a free-form host name is not a selection.
   - Query candidates by the full 40-character local commit SHA with `GET /changes/?q=commit:<sha>` using the Gerrit skill's query contract. Fetch every page (`n=` page size, `start=` offset from 0, stop only when a returned page is shorter than `n`); never claim the candidate list is complete while pagination is not exhausted. Remove the XSSI guard before parsing each page and follow the Gerrit skill's authentication, TLS, and secret-handling rules.
   - Fetch `GET /changes/{change-id}/detail` for every candidate and record `_number`, `change_id`, `project`, `branch`, `status`, `current_revision`, and the `revisions` map whose keys are revision SHAs.
   - Apply the disambiguation layers in order and keep only candidates that pass every layer:
     1. Change-Id: when the local commit message contains a `Change-Id: I<40 hex>` footer, the candidate's `change_id` must equal it;
     2. Project: the candidate's `project` must equal the local repository's Gerrit project, derived from the remote URL path. If it cannot be derived uniquely, display the candidate projects and call `questionnaire` with one question whose `id` is `gerrit_project_choice`, label is `Gerrit 项目`, prompt asks which displayed project matches the current repository, options contain one entry per candidate (the exact project name is both `value` and `label`, and `description` states the matching remote/candidate evidence), and `allowOther` is `false`. Accept only the exact structured selection. User cancellation stops; invalid/missing results re-call the same questionnaire; a typed project name is not a selection.
     3. Target branch: the candidate's `branch` must equal the confirmed target branch (`branch.<local_branch>.merge` with the `refs/heads/` prefix removed). If no unique configured target branch exists but a finite candidate set is available, display it and call `questionnaire` with one question whose `id` is `gerrit_branch_choice`, label is `目标分支`, prompt asks which displayed branch is the target, options contain one entry per candidate (the exact branch is both `value` and `label`, and `description` states the supporting config/candidate evidence), and `allowOther` is `false`. Accept only the exact structured selection. User cancellation stops; invalid/missing results re-call the same questionnaire; never guess or accept a typed branch.
     4. Revision: prefer candidates whose `revisions` contain a key exactly equal to the local commit SHA; a candidate without an exact revision match is kept only when no candidate has one.
   - After all layers: exactly one candidate means the change is uniquely identified and the flow continues; zero candidates means stop and request corrected repository/Gerrit context (the commit may not be pushed or the instance may be wrong). More than one candidate means show every candidate's identity fields and call `questionnaire` with one question whose `id` is `gerrit_change_choice`, label is `Gerrit 变更`, prompt asks which displayed change matches the local commit, options contain one entry per candidate (use a stable internal candidate key as `value`, a readable change number/title as `label`, and include `_number`, `change_id`, `project`, `branch`, `status`, and revision basis in `description`) plus `{ "value": "cancel", "label": "取消", "description": "停止本次流程，不更新 Redmine。" }`, and `allowOther` is `false`. Proceed only for an exact candidate value. `cancel` or user cancellation stops; invalid/missing results re-call the same questionnaire; a free-form change number is not a selection. Never guess or fabricate an identity.
   - For multiple patchsets, prefer the revision whose SHA exactly equals the local commit SHA. When no exact revision matches (for example the change was located via `Change-Id` after a re-push), use `current_revision` and disclose that basis in the draft. Never use the local commit SHA or the `Change-Id` as the change number.
   - Only proceed when the unique change's `status` is `NEW`. When it is `MERGED`, `ABANDONED`, or otherwise unsuitable for the current conclusion, stop and ask the user; do not report a pushed-but-unsuitable change as valid.
   - Inspect changed files and the patch needed to report the change accurately. Do not inspect or infer testing, review, or dependency completion from Gerrit labels, branch state, or other repository evidence.
   - Record the change number (`_number`), revision SHA, branch, project, status, and the matching basis (which fields matched at each layer); show them in the draft and in the final report.

6. **Draft the conclusion.** Analyze the issue context, exact tracker, local commit, Gerrit metadata, current conclusion, and cached rules. Apply the conclusion structures defined in [references/bu1-sdk-conclusion-rules.md](references/bu1-sdk-conclusion-rules.md): the three-element 普通结论 (普通结论 section), the 问题性质-based structure selection with the patch-cause formats (问题性质与结论补充格式 section), and the supplemental formats for `规格变更`, `已拒绝`, and `反馈` (same section). Use concrete evidence and preserve uncertainty in the wording when the scope or cause is not established; the conclusion remains concise and in Chinese. When the selected scenario requires a user-supplied agreement fact (for example, `已拒绝` requires software version manager agreement or `反馈` requires issue creator agreement), collect that yes/no fact with the reference-prescribed `questionnaire` before drafting; do not treat a free-form acknowledgement as agreement.
   - For `已拒绝`, when software version manager agreement is not already established, call `questionnaire` with `id: "release_manager_agreement"`, label `版本管理员同意`, the prompt `是否已征得软件版本管理员同意拒绝此问题？`, and `yes`/`no` options labelled `已同意`/`未同意` whose descriptions state that `yes` permits the rejection conclusion and `no` stops, with `allowOther: false`.
   - For `反馈`, when issue creator agreement is not already established, call `questionnaire` with `id: "issue_creator_agreement"`, label `任务创建者同意`, the prompt `是否已征得任务创建者同意本次反馈结论？`, and `yes`/`no` options labelled `已同意`/`未同意` whose descriptions state that `yes` permits the feedback conclusion and `no` stops, with `allowOther: false`.
   For both questions, only the exact structured `yes` value establishes agreement; `no` or cancellation stops without a write, and invalid/missing results repeat the questionnaire.

   For tracker `错误`, read the existing `问题性质` only as context for selecting the conclusion structure. When it has a value, use that value. When it is empty, call `questionnaire` with this single-choice question:
   ```json
   {
     "questions": [
       {
         "id": "issue_nature_choice",
         "label": "问题性质",
         "prompt": "问题性质为空，请选择本次结论使用的结构。",
         "options": [
           {
             "value": "1",
             "label": "历史遗留",
             "description": "使用普通结论结构。"
           },
           {
             "value": "2",
             "label": "当前版本修改引入",
             "description": "使用当前版本补丁引入结构。"
           },
           {
             "value": "3",
             "label": "上个版本修改引入",
             "description": "使用上个版本补丁引入结构。"
           }
         ],
         "allowOther": false
       }
     ]
   }
   ```
   Accept only `details.answers` with `id: "issue_nature_choice"` and `value` exactly `1`, `2`, or `3`. User cancellation stops; a missing/invalid answer re-calls the same questionnaire; a typed digit outside the questionnaire is not a selection. Record the structured answer (`id`, `value`, and label when returned) in the draft, not a rephrased or raw typed answer. Map `1` and `2`/`3` to the structures defined in the reference's 问题性质与结论补充格式 section; this selection affects only the conclusion draft and does not update the `问题性质` field.

7. **Present the draft and use questionnaire.** Show the target issue/project, exact tracker, local rule source, `source_version`, `checked_at`, and `checked_by`, latest Git commit SHA, Gerrit instance, change number, revision SHA, branch, project, status, and matching basis, evidence-based change summary, current conclusion, and proposed conclusion in a fenced text block. State that no Redmine write has happened. Then call `questionnaire` with this single-choice confirmation:
   ```json
   {
     "questions": [
       {
         "id": "conclusion_decision",
         "label": "结论更新确认",
         "prompt": "是否按以上证据和拟定结论更新 Redmine 的结论字段？",
         "options": [
           {
             "value": "confirm",
             "label": "确认更新",
             "description": "在写入前重新复核 issue、规则快照和字段，复核通过后执行一次 Redmine PUT。"
           },
           {
             "value": "revise",
             "label": "修改草稿",
             "description": "不执行 Redmine 写入；随后用文字说明需要修改的内容。"
           },
           {
             "value": "cancel",
             "label": "取消更新",
             "description": "结束本次流程，不修改 Redmine。"
           }
         ],
         "allowOther": false
       }
     ]
   }
   ```
   Continue to Phase 2 only when structured `details.answers` contains `id: "conclusion_decision"` and `value: "confirm"`. For `revise`, collect the requested edit, rerun every affected check, show the revised draft, and invoke a fresh questionnaire. `cancel` or user cancellation stops without a Redmine write; a missing/invalid answer re-calls the same questionnaire; free-form `确认更新` or other text is never authorization. Record the structured confirmation answer (`id`, `value`, and label when returned), not a typed raw confirmation, and include it in the final report. This protocol has no `abandoned` prerequisite; non-mainline patch abandonment is outside this skill and the user handles it separately.

Phase 1 is complete only when the issue is verified as `bu1-sdk`, the `结论` field is identified, the available Git/Gerrit evidence is summarized, the complete proposed conclusion has been shown, and the latest `conclusion_decision` answer is the structured `value: "confirm"`.

## Phase 2: Update and verify the conclusion

1. Re-check the structured `conclusion_decision` answer from the latest questionnaire and require exactly `value: "confirm"` before writing. `revise` means collect exactly the requested edit, re-run every affected check (conclusion structure, underlying facts and fields, Git/Gerrit identity, verified scope), display the revised draft with the edit request preserved verbatim, and invoke a fresh `conclusion_decision` questionnaire. `cancel` or user cancellation ends the flow; missing/invalid answers re-call the same questionnaire; natural-language messages never authorize a write. When any new fact arrives after confirmation—a changed issue value, a changed or refreshed rule snapshot, a changed commit or Gerrit identity, or a corrected user-supplied fact—re-run all affected checks and require a fresh questionnaire confirmation; never proceed on a partial re-check while other facts may have changed.

2. Before writing, re-read the issue and verify that the project is still `bu1-sdk`, the `结论` field ID is unchanged, and the current conclusion has not changed in a way that invalidates the draft. Re-read the local rule snapshot metadata and confirm its `source_version`, `checked_at`, `checked_by`, and content hash are unchanged from Phase 1; a changed or newly refreshed snapshot invalidates the draft and requires regeneration, display of the revised draft, and a fresh `conclusion_decision` questionnaire. If any of these changed, refresh the analysis and do not write until the fresh structured confirmation is `value: "confirm"`.

3. Send one authenticated `PUT /issues/<issue-id>.json` request with `Content-Type: application/json`, following the **Redmine** skill's AI Write Audit Trail. In the request, update only:
   - the `结论` custom field using its discovered ID;
   - `issue.notes` with the audit note in the same PUT request, per the Redmine skill's exact prefix and format.

   Do not update `status_id`, `done_ratio`, assignee, tags, target version, dates, relations, or any other custom field. Do not claim success before the request returns success.

4. Re-read the issue after the PUT and verify the `结论` custom-field value. Report the issue ID, project, tracker, updated conclusion, timestamp if returned, and the Gerrit identity (change number, revision SHA, branch, project, status, and matching basis). Report HTTP or verification failures plainly and do not claim completion when verification fails.

The workflow is complete after the verified Redmine issue contains the approved conclusion and the required audit note.
