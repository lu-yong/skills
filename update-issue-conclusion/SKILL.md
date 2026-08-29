---
name: update-issue-conclusion
description: Use when the user wants to complete a Redmine issue conclusion; require an issue number, inspect the issue, latest local Git commit, and its Gerrit change, draft a rule-compliant Chinese conclusion, obtain explicit confirmation, then update the conclusion.
disable-model-invocation: true
---

# Update Issue Conclusion

This skill is a two-phase workflow: **determine and draft first, write second**.

## ask_user_question interaction contract

Use `ask_user_question` for every finite user decision or confirmation in this workflow. Each question carries a `header` (at most 16 characters, the chip label identifying the question), a `question` text ending in a question mark, and 2-4 `options`, each with a `label` (at most 60 characters, 1-5 words) and a required `description`. Never author an option labelled `Other`, `Type something.`, or `Next`: these are reserved and rejected with `reserved_label`. A `Type something.` row is appended to every question automatically and cannot be disabled, so free-form text is always reachable and never authorizes an action.

Issue exactly one question per call in this workflow. Read only structured `details.answers`, and inspect `details.error` first.

**When `details.error` is present.** Every error result also carries `cancelled: true` and an empty `answers` array, so an error is never a user decision and must never be reported as one. Never re-issue the same call unchanged on an error: an identical call reproduces the identical error.

- Authoring errors (`reserved_label`, `duplicate_option_label`, `empty_options`, `too_many_questions`, `duplicate_question`) mean this skill built an invalid question. Repair the authored question (relabel the offending option, re-batch the candidates) and issue a corrected call. After 2 failed repair attempts, stop and report.
- Host errors (`no_ui`, `no_custom_ui`, `session_load_failed`, `stale_module_cache`) mean the question could not be presented at all. Stop and report that. Never claim the user cancelled, never fall back to natural-language confirmation, and never proceed.

**When `details.error` is absent.** An answer authorizes an action only when all of the following hold:

- `details.cancelled` is `false`
- an entry exists whose `question` string exactly equals the `question` text of the call just issued
- that entry's `kind` is exactly `option` (`custom` is typed free text and never authorizes anything; `multi` is unused in this workflow)
- that entry's `answer` exactly equals the intended option `label`

Bind on the `question` string, not on `questionIndex`. Every call in this workflow is single-question, so `questionIndex` is always `0` and cannot distinguish one gate's answer from another's. An answer is valid only for the call that produced it; discard results of earlier calls.

Anything else repeats the same call unchanged: a missing entry, `kind: "custom"`, or a mismatched label. `details.cancelled: true` with no `details.error` means the user declined or pressed `Esc`; stop without side effects.

A submission carrying only a global note yields `cancelled: false` with an empty or incomplete `answers` array, and the tool's prose still reads as answered. Never treat the tool's prose text as the decision; always verify the `answers` entry described above. `details.globalNote` and `answers[].notes` are context only and never constitute an answer.

Use ordinary conversation only for open-ended values such as an issue number, an edit request, or a reason. Do not use the `qna` extension's Q&A summary. Record the matched `question`, the `answer` label, and the `header`, without recording secrets.

**Batching candidates.** Ask all candidates in a single call when 4 or fewer remain. When more than 4 candidates exist, display every candidate as text first, then batch in that displayed order, holding the order stable across re-calls: at most 3 candidates per call plus a fourth option labelled `下一批候选` that advances to the next batch, wrapping from the last batch back to the first. Selecting `下一批候选` decides nothing. Control labels never resolve to a candidate; a label with no entry in the batch's recorded label-to-candidate mapping is an unmatched label and repeats the call. Never drop a candidate, never shrink the set to fit one batch, never guess.

**Labels built from external data.** Check candidate labels derived from Gerrit or Redmine values before use: a value equal to `Other`, `Type something.`, or `Next` is rejected by the tool, and a value equal to a control label would be read as a control option. When a candidate value is reserved, collides with a control label, collides with another label in the same batch, or exceeds 60 characters, replace the label with a positional form (`候选 1`, `候选 2`, … within that batch) and put the full value in `description`. Record the label-to-candidate mapping for that call and resolve the returned label back through it.

**When the tool is unavailable.** A non-interactive host strips `ask_user_question` from the tool list entirely, so the gate cannot be reached at all. When the tool is absent from the available tools, or a call returns `no_ui` or `no_custom_ui`, stop and report that this skill requires an interactive host. Never substitute a natural-language confirmation, and never send the Redmine `PUT` on that path.

Load and follow the available **Redmine** skill for authentication, issue API usage, the conclusion custom field, and write-audit requirements. Load and follow the available **Gerrit** skill for the read-only Gerrit queries. Use the host's native skill-loading mechanism; do not assume a slash command or a particular Agent API.

## Phase 1: Analyze the issue and draft the conclusion

1. **Validate the input.** Ask the user for one Redmine issue number if it was not supplied. Accept only a positive decimal integer matching `^[1-9][0-9]*$`. Treat the number as the Redmine issue ID, not as a project identifier. Reject extra text, URLs, ranges, comma-separated IDs, and non-decimal IDs.

2. **Read the issue.** Read the issue with its tracker, custom fields, journals, and relevant history. Locate the `结论` custom field and record its numeric field ID and current value. Record `issue.project.identifier` as context. Read the exact tracker name and existing issue context as input to the conclusion rules. Stop and ask for a corrected issue number when the issue does not exist or access is denied. Never update an issue based only on its title or project name.

3. **Load the local conclusion snapshot.** Read [references/bu1-sdk-conclusion-rules.md](references/bu1-sdk-conclusion-rules.md) before drafting. Record its `source_version`, `checked_at`, and `checked_by` for disclosure in the draft and final report. Use the local snapshot as-is. This skill does not validate snapshot freshness, source version, metadata completeness, or a refresh transaction, and does not route to [refresh-bu1-sdk-rules](../refresh-bu1-sdk-rules/SKILL.md). Snapshot updates are the user's responsibility via that refresh skill. When the selected scenario is not covered by the snapshot, stop and ask the user for the rule; do not invent a format. Do not access online Wiki, refresh rules, or modify the reference.

4. **Inspect the current Git reference.** In the current Git repository:
   - Resolve the repository root with `git rev-parse --show-toplevel`.
   - Read the most recent commit with its full message, author/date, commit SHA, and parent relationship.
   - Inspect the commit diff and changed-file summary (`git show`/equivalent). Summarize only behavior supported by the diff; distinguish facts from inferences.
   - If there is no repository, no commit, or the worktree is not the repository relevant to the issue, ask the user to switch to the correct repository or provide the repository context.

5. **Resolve the Gerrit change through the Gerrit skill, deterministically.**
   - Determine the Gerrit instance from the Git remote. Use the internal instance for `git.nationalchip.com` and the external instance for `gerrit.nationalchip.com`. When the host is ambiguous, display the evidence and call `ask_user_question` with one question whose `header` is `Gerrit 实例`, whose `question` asks which company Gerrit instance contains the change, and whose two options are `{ "label": "内部 Gerrit", "description": "使用 git.nationalchip.com 查询。" }` and `{ "label": "外部 Gerrit", "description": "使用 gerrit.nationalchip.com 查询。" }`. Accept only an `answers` entry whose `question` equals this call's `question` text, whose `kind` is `option`, and whose `answer` exactly equals one of those two labels. `details.cancelled: true` with no `details.error` stops; a missing entry, `kind: "custom"`, or an unmatched label re-calls the same question unchanged; a `details.error` is handled per the contract's error rules and never re-calls the question unchanged; a free-form host name is not a selection.
   - Query candidates by the full 40-character local commit SHA with `GET /changes/?q=commit:<sha>` using the Gerrit skill's query contract. Fetch every page (`n=` page size, `start=` offset from 0, stop only when a returned page is shorter than `n`); never claim the candidate list is complete while pagination is not exhausted. Remove the XSSI guard before parsing each page and follow the Gerrit skill's authentication, TLS, and secret-handling rules.
   - Fetch `GET /changes/{change-id}/detail` for every candidate and record `_number`, `change_id`, `project`, `branch`, `status`, `current_revision`, and the `revisions` map whose keys are revision SHAs.
   - Apply the disambiguation layers in order and keep only candidates that pass every layer:
     1. Change-Id: when the local commit message contains a `Change-Id: I<40 hex>` footer, the candidate's `change_id` must equal it;
     2. Project: the candidate's `project` must equal the local repository's Gerrit project, derived from the remote URL path. If it cannot be derived uniquely, display every candidate project as text first, then call `ask_user_question` with one question whose `header` is `Gerrit 项目` and whose `question` asks which displayed project matches the current repository, batching per the contract's **Batching candidates** rule in the displayed order and keeping that order stable across re-calls: ask all candidates in a single call when 4 or fewer remain; when more than 4 candidates exist, send at most 3 candidates per call plus a fourth option `下一批候选` (`description`: `展示下一批候选项目，不做选择。`), whose selection re-issues the question with the next batch and wraps from the last batch back to the first. Each candidate option's `label` is the exact project name and its `description` states the matching remote/candidate evidence, with the contract's **Labels built from external data** rule applied: a project name that is reserved, equals a control label (`下一批候选`, `重新提供上下文`), collides with another label in the same batch, or exceeds 60 characters is sent as `候选 1`, `候选 2`, … within that batch with the full name in `description`. Record the label-to-candidate mapping for each call. When exactly one candidate remains and confirmation is still required, offer that candidate plus `重新提供上下文` (`description`: `停止本次流程，要求用户提供正确的仓库/Gerrit 上下文。`) so the question still carries two options. Accept only an `answers` entry whose `question` equals this call's `question` text, whose `kind` is `option`, and whose `answer` exactly equals one label in the batch just sent. Resolve that label back through the recorded mapping for that call: `下一批候选` and `重新提供上下文` are control labels with no mapping entry and never resolve to a candidate; `下一批候选` advances to the next batch and decides nothing, and `重新提供上下文` stops the flow and asks the user for the correct repository/Gerrit context without updating Redmine. A returned label with no mapping entry and no control meaning is an unmatched label. `details.cancelled: true` with no `details.error` stops; a missing entry, `kind: "custom"`, or an unmatched label re-calls the same batch unchanged; a `details.error` is handled per the contract's error rules; a typed project name is not a selection. Never drop a candidate from the batches and never guess.
     3. Target branch: the candidate's `branch` must equal the confirmed target branch (`branch.<local_branch>.merge` with the `refs/heads/` prefix removed). If no unique configured target branch exists but a finite candidate set is available, display every candidate branch as text first, then ask with the same batching, wrap-around, external-data labelling, control-label, and single-candidate rules as the project choice above, using `header` `目标分支`, a `question` asking which displayed branch is the target, one option per candidate whose `label` is the exact branch name and whose `description` states the supporting config/candidate evidence, `下一批候选` as the fourth option in every batch when more than 4 candidates exist, and `重新提供上下文` as the second option when only one candidate remains. A branch literally named `Other`, `Type something.`, `Next`, `下一批候选`, or `重新提供上下文` is realistic in Gerrit, so send it as `候选 N` with the full branch name in `description` and resolve through the recorded mapping. Accept only an `answers` entry whose `question` equals this call's `question` text, whose `kind` is `option`, and whose `answer` exactly equals one label in the batch just sent; control labels never resolve to a branch. `details.cancelled: true` with no `details.error` stops; a missing entry, `kind: "custom"`, or an unmatched label re-calls the same batch unchanged; a `details.error` is handled per the contract's error rules; never guess or accept a typed branch.
     4. Revision: prefer candidates whose `revisions` contain a key exactly equal to the local commit SHA; a candidate without an exact revision match is kept only when no candidate has one.
   - After all layers: exactly one candidate means the change is uniquely identified and the flow continues; zero candidates means stop and request corrected repository/Gerrit context (the commit may not be pushed or the instance may be wrong). More than one candidate means display every candidate's identity fields as text first, then ask with the same batching, wrap-around, and control-label rules as the project choice above, using `header` `Gerrit 变更`, a `question` asking which displayed change matches the local commit, and one option per candidate whose `label` is `变更 <_number>` (unique within the batch because `_number` is unique, never reserved, and never equal to a control label) and whose `description` carries `_number`, `change_id`, `project`, `branch`, `status`, and the revision basis. Ask all candidates in a single call when 4 or fewer remain; when more than 4 candidates exist, send at most 3 candidates per call plus `下一批候选` as the fourth option. Record the label-to-candidate mapping for each call. Do not author a cancel option here: the fourth option slot belongs to `下一批候选`, and `Esc` yields `details.cancelled: true`, which stops the flow without updating Redmine. Proceed only for an `answers` entry whose `question` equals this call's `question` text, whose `kind` is `option`, and whose `answer` exactly equals one label in the batch just sent, then resolve that label back through the recorded mapping for that call; `下一批候选` has no mapping entry, advances to the next batch, and decides nothing. A missing entry, `kind: "custom"`, or an unmatched label re-calls the same batch unchanged; a `details.error` is handled per the contract's error rules; a free-form change number is not a selection. Never guess or fabricate an identity, and never shrink the candidate set to make it fit one batch.
   - For multiple patchsets, prefer the revision whose SHA exactly equals the local commit SHA. When no exact revision matches (for example the change was located via `Change-Id` after a re-push), use `current_revision` and disclose that basis in the draft. Never use the local commit SHA or the `Change-Id` as the change number.
   - Only proceed when the unique change's `status` is `NEW`. When it is `MERGED`, `ABANDONED`, or otherwise unsuitable for the current conclusion, stop and ask the user; do not report a pushed-but-unsuitable change as valid.
   - Inspect changed files and the patch needed to report the change accurately. Do not inspect or infer testing, review, or dependency completion from Gerrit labels, branch state, or other repository evidence.
   - Record the change number (`_number`), revision SHA, branch, project, status, and the matching basis (which fields matched at each layer); show them in the draft and in the final report.

6. **Draft the conclusion.** Analyze the issue context, exact tracker, local commit, Gerrit metadata, current conclusion, and cached rules. Apply the conclusion structures defined in [references/bu1-sdk-conclusion-rules.md](references/bu1-sdk-conclusion-rules.md): the three-element 普通结论 (普通结论 section), the 问题性质-based structure selection with the patch-cause formats (问题性质与结论补充格式 section), and the supplemental formats for `规格变更`, `已拒绝`, and `反馈` (same section). Use concrete evidence and preserve uncertainty in the wording when the scope or cause is not established; the conclusion remains concise and in Chinese. When the selected scenario requires a user-supplied agreement fact (for example, `已拒绝` requires software version manager agreement or `反馈` requires issue creator agreement), collect that yes/no fact with the `ask_user_question` call prescribed below before drafting; do not treat a free-form acknowledgement as agreement.
   - For `已拒绝`, when software version manager agreement is not already established, call `ask_user_question` with `header` `版本管理员同意`, the `question` `是否已征得软件版本管理员同意拒绝此问题？`, and two options labelled `版本管理员已同意` and `版本管理员未同意` whose descriptions state that `版本管理员已同意` permits the rejection conclusion and `版本管理员未同意` stops.
   - For `反馈`, when issue creator agreement is not already established, call `ask_user_question` with `header` `任务创建者同意`, the `question` `是否已征得任务创建者同意本次反馈结论？`, and two options labelled `任务创建者已同意` and `任务创建者未同意` whose descriptions state that `任务创建者已同意` permits the feedback conclusion and `任务创建者未同意` stops.
   The two gates deliberately carry distinct labels as well as distinct `question` texts: an entry answering one gate can never be mistaken for the other, so a draft that switches from `已拒绝` to `反馈` after the first gate cannot inherit the first gate's agreement. Agreement is established only by an `answers` entry whose `question` equals that gate's `question` text, whose `kind` is `option`, and whose `answer` exactly equals that gate's affirmative label (`版本管理员已同意` or `任务创建者已同意` respectively), obtained from the call issued for the current draft. Discard any agreement answer collected before the conclusion structure changed and ask again. The negative label or `details.cancelled: true` with no `details.error` stops without a write; a missing entry, `kind: "custom"`, or an unmatched label re-calls the same question unchanged; a `details.error` is handled per the contract's error rules.

   For tracker `错误`, read the existing `问题性质` only as context for selecting the conclusion structure. When it has a value, use that value. When it is empty, call `ask_user_question` with this single-choice question:
   ```json
   {
     "questions": [
       {
         "header": "问题性质",
         "question": "问题性质为空，本次结论使用哪种结构？",
         "options": [
           {
             "label": "历史遗留",
             "description": "使用普通结论结构。"
           },
           {
             "label": "当前版本修改引入",
             "description": "使用当前版本补丁引入结构。"
           },
           {
             "label": "上个版本修改引入",
             "description": "使用上个版本补丁引入结构。"
           }
         ]
       }
     ]
   }
   ```
   Accept only an `answers` entry whose `question` equals this call's `question` text, whose `kind` is `option`, and whose `answer` exactly equals `历史遗留`, `当前版本修改引入`, or `上个版本修改引入`. `details.cancelled: true` with no `details.error` stops; a missing entry, `kind: "custom"`, or an unmatched label re-calls the same question unchanged; a `details.error` is handled per the contract's error rules; a typed 问题性质 name or digit is not a selection. Record the matched `question` and `answer` label in the draft, not a rephrased or raw typed answer. Map `历史遗留` to the 普通结论 structure and `当前版本修改引入`/`上个版本修改引入` to their corresponding structures in the reference's 问题性质与结论补充格式 section; this selection affects only the conclusion draft and does not update the `问题性质` field.

7. **Present the draft and ask for confirmation.** Show the target issue/project, exact tracker, local rule source, `source_version`, `checked_at`, and `checked_by`, latest Git commit SHA, Gerrit instance, change number, revision SHA, branch, project, status, and matching basis, evidence-based change summary, current conclusion, and proposed conclusion in a fenced text block. State that no Redmine write has happened. Then call `ask_user_question` with this single-choice confirmation:
   ```json
   {
     "questions": [
       {
         "header": "结论确认",
         "question": "是否按以上证据和拟定结论更新 Redmine 的结论字段？",
         "options": [
           {
             "label": "确认更新",
             "description": "在写入前重新复核 issue、规则快照和字段，复核通过后执行一次 Redmine PUT。"
           },
           {
             "label": "修改草稿",
             "description": "不执行 Redmine 写入；随后用文字说明需要修改的内容。"
           },
           {
             "label": "取消更新",
             "description": "结束本次流程，不执行任何 Redmine 写入。"
           }
         ]
       }
     ]
   }
   ```
   Continue to Phase 2 only when `details.error` is absent, `details.cancelled` is `false`, and `details.answers` contains an entry whose `question` equals this call's `question` text, whose `kind` is `option`, and whose `answer` exactly equals `确认更新`. For `修改草稿`, collect the requested edit, rerun every affected check, show the revised draft, and issue a fresh confirmation call. An `answer` of `取消更新` ends the flow without a Redmine write and is the recordable decline: record it in the final report. `details.cancelled: true` with no `details.error` also ends the flow without a Redmine write, and is reported as an interrupted confirmation rather than a user rejection. A missing entry, `kind: "custom"`, or an unmatched label re-calls the same question unchanged; a `details.error` is handled per the contract's error rules and never re-calls the question unchanged; a submission carrying only a global note is not a confirmation even though `details.cancelled` is `false` and the tool's prose reads as answered; free-form `确认更新` typed as text is never authorization. Record the matched `question`, `answer` label, and `header`, not a typed raw confirmation, and include it in the final report. This protocol has no `abandoned` prerequisite; non-mainline patch abandonment is outside this skill and the user handles it separately.

Phase 1 is complete only when the issue is readable, the `结论` field is identified, the available Git/Gerrit evidence is summarized, the complete proposed conclusion has been shown, and the latest `结论确认` answer is a `kind: "option"` entry whose `answer` is exactly `确认更新`.

## Phase 2: Update and verify the conclusion

1. Re-check the structured `结论确认` answer from the latest `ask_user_question` call and require a `kind: "option"` entry whose `question` equals that call's `question` text and whose `answer` is exactly `确认更新`, with `details.error` absent and `details.cancelled` false, before writing. `修改草稿` means collect exactly the requested edit, re-run every affected check (conclusion structure, underlying facts and fields, Git/Gerrit identity, verified scope), display the revised draft with the edit request preserved verbatim, and issue a fresh `结论确认` call. `取消更新` or `details.cancelled: true` with no `details.error` ends the flow; a missing entry, `kind: "custom"`, or an unmatched label re-calls the same question unchanged; a `details.error` is handled per the contract's error rules; natural-language messages, `details.globalNote`, and `answers[].notes` never authorize a write. When any new fact arrives after confirmation—a changed issue value, a changed rule snapshot, a changed commit or Gerrit identity, or a corrected user-supplied fact—re-run all affected checks and require a fresh `结论确认` confirmation; never proceed on a partial re-check while other facts may have changed.

2. Before writing, re-read the issue and verify that the `结论` field ID is unchanged and the current conclusion has not changed in a way that invalidates the draft. Re-read the local rule snapshot and confirm its content is unchanged from Phase 1; a changed snapshot invalidates the draft and requires regeneration, display of the revised draft, and a fresh `结论确认` call. If any of these changed, refresh the analysis and do not write until a fresh `kind: "option"` answer is exactly `确认更新`.

3. Send one authenticated `PUT /issues/<issue-id>.json` request with `Content-Type: application/json`, following the **Redmine** skill's AI Write Audit Trail. In the request, update only:
   - the `结论` custom field using its discovered ID;
   - `issue.notes` with the audit note in the same PUT request, per the Redmine skill's exact prefix and format.

   Do not update `status_id`, `done_ratio`, assignee, tags, target version, dates, relations, or any other custom field. Do not claim success before the request returns success.

4. Re-read the issue after the PUT and verify the `结论` custom-field value. Report the issue ID, project, tracker, updated conclusion, timestamp if returned, and the Gerrit identity (change number, revision SHA, branch, project, status, and matching basis). Report HTTP or verification failures plainly and do not claim completion when verification fails.

The workflow is complete after the verified Redmine issue contains the approved conclusion and the required audit note.
