---
name: update-bu1-sdk-issue-conclusion
description: Use when the user wants to complete a BU1-SDK-2007-01-UNIFY Redmine issue; require an issue number, inspect the issue, latest local Git commit, and its Gerrit change, draft a rule-compliant Chinese conclusion, obtain explicit confirmation, then update the conclusion.
disable-model-invocation: true
---

# Update BU1-SDK Issue Conclusion

This skill is a two-phase workflow: **determine and draft first, write second**. The Redmine project identifier for `BU1-SDK-2007-01-UNIFY` is `bu1-sdk`.

Load and follow the available **Redmine** skill for authentication, issue API usage, the conclusion custom field, and write-audit requirements. Load and follow the available **Gerrit** skill for the read-only Gerrit queries. Use the host's native skill-loading mechanism; do not assume a slash command or a particular Agent API.

## Phase 1: Analyze the issue and draft the conclusion

1. **Validate the input.** Ask the user for one Redmine issue number if it was not supplied. Accept only a positive decimal integer matching `^[1-9][0-9]*$`. Treat the number as the Redmine issue ID, not as a project identifier. Reject extra text, URLs, ranges, comma-separated IDs, and non-decimal IDs.

2. **Verify the issue belongs to BU1-SDK.** Read the issue with its tracker, custom fields, journals, and relevant history. Confirm that `issue.project.identifier` is exactly `bu1-sdk`. Locate the `结论` custom field and record its numeric field ID and current value. Read the exact tracker name and existing issue context as input to the conclusion rules. Stop and ask for a corrected issue number when the issue does not exist, access is denied, or the project identifier differs. Never update an issue based only on its title or project name.

3. **Load the local conclusion snapshot.** Read [references/bu1-sdk-conclusion-rules.md](references/bu1-sdk-conclusion-rules.md) before drafting. Record its `source_version`, `checked_at`, and `checked_by`. The local snapshot is the only rules source during this workflow; do not access online Wiki, refresh rules, or modify the reference. If the snapshot is missing, metadata is invalid, `checked_at` is not a valid UTC ISO 8601 timestamp, or it is more than 30 days old, stop and ask the user to call [refresh-bu1-sdk-rules](../refresh-bu1-sdk-rules/SKILL.md). If the user explicitly accepts an old but complete snapshot after a failed refresh, continue only with that explicit permission and disclose the snapshot age in the draft and final report. If `refresh-bu1-sdk-rules/.refresh.pending` exists, stop until the refresh transaction is completed or recovered according to that skill.

4. **Inspect the current Git reference.** In the current Git repository:
   - Resolve the repository root with `git rev-parse --show-toplevel`.
   - Read the most recent commit with its full message, author/date, commit SHA, and parent relationship.
   - Inspect the commit diff and changed-file summary (`git show`/equivalent). Summarize only behavior supported by the diff; distinguish facts from inferences.
   - If there is no repository, no commit, or the worktree is not the repository relevant to the issue, ask the user to switch to the correct repository or provide the repository context.

5. **Resolve the Gerrit change through the Gerrit skill, deterministically.**
   - Determine the Gerrit instance from the Git remote. Use the internal instance for `git.nationalchip.com` and the external instance for `gerrit.nationalchip.com`; ask the user to choose when the host is ambiguous.
   - Query candidates by the full 40-character local commit SHA with `GET /changes/?q=commit:<sha>` using the Gerrit skill's query contract. Fetch every page (`n=` page size, `start=` offset from 0, stop only when a returned page is shorter than `n`); never claim the candidate list is complete while pagination is not exhausted. Remove the XSSI guard before parsing each page and follow the Gerrit skill's authentication, TLS, and secret-handling rules.
   - Fetch `GET /changes/{change-id}/detail` for every candidate and record `_number`, `change_id`, `project`, `branch`, `status`, `current_revision`, and the `revisions` map whose keys are revision SHAs.
   - Apply the disambiguation layers in order and keep only candidates that pass every layer:
     1. Change-Id: when the local commit message contains a `Change-Id: I<40 hex>` footer, the candidate's `change_id` must equal it;
     2. Project: the candidate's `project` must equal the local repository's Gerrit project, derived from the remote URL path or confirmed with the user;
     3. Target branch: the candidate's `branch` must equal the confirmed target branch (`branch.<local_branch>.merge` with the `refs/heads/` prefix removed, or the branch confirmed with the user);
     4. Revision: prefer candidates whose `revisions` contain a key exactly equal to the local commit SHA; a candidate without an exact revision match is kept only when no candidate has one.
   - After all layers: exactly one candidate means the change is uniquely identified and the flow continues; zero candidates means stop and ask the user (the commit may not be pushed, the instance may be wrong, or pagination may have been truncated); more than one candidate means stop, show every candidate's identity fields, and ask the user to choose. Never guess a change number or fabricate an identity.
   - For multiple patchsets, prefer the revision whose SHA exactly equals the local commit SHA. When no exact revision matches (for example the change was located via `Change-Id` after a re-push), use `current_revision` and disclose that basis in the draft. Never use the local commit SHA or the `Change-Id` as the change number.
   - Only proceed when the unique change's `status` is `NEW`. When it is `MERGED`, `ABANDONED`, or otherwise unsuitable for the current conclusion, stop and ask the user; do not report a pushed-but-unsuitable change as valid.
   - Inspect changed files and the patch needed to report the change accurately. Do not inspect or infer testing, review, or dependency completion from Gerrit labels, branch state, or other repository evidence.
   - Record the change number (`_number`), revision SHA, branch, project, status, and the matching basis (which fields matched at each layer); show them in the draft and in the final report.

6. **Draft the conclusion.** Analyze the issue context, exact tracker, local commit, Gerrit metadata, current conclusion, and cached rules. The conclusion must contain these three elements with concrete content:
   - `问题原因：` why the issue occurred, supported by the issue and commit analysis;
   - `处理方案：` what was changed, including the Gerrit change number when a patch exists;
   - `影响范围：` affected modules, targets, branches, versions, or a precise statement of the verified scope.

   For tracker `错误`, read the existing `问题性质` only as context for selecting the conclusion structure. When it has a value, use that value. When it is empty, present exactly this prompt:
   ```text
   问题性质为空，请选择：
   1. 历史遗留
   2. 当前版本修改引入
   3. 上个版本修改引入
   请输入 1-3：
   ```
   Parse the answer strictly. Trim surrounding ASCII whitespace, then accept only the single digit `1`, `2`, or `3`. Reject full-width digits or punctuation (`１`-`３`, `1。`, `2、`), attached explanations (`2 当前版本修改引入`), multiple values, and empty input. On any rejection, state the concrete reason and re-display the same prompt in full; never guess, complete, or reinterpret the answer. Record the user's raw answer verbatim and show it in the draft; do not rephrase it. Map `1` to the ordinary conclusion structure; map `2` and `3` to the corresponding patch-cause structure. This selection affects only the conclusion draft; it does not update the `问题性质` field.

   Apply the supplemental format for the issue's current context:
   - For an `错误` issue whose `问题性质` is `当前版本修改引入` or `上个版本修改引入`, include the patch-cause wording and `修改补丁：{{patch(<Gerrit change number>)}}` when the numeric change number is available.
   - For `规格变更`, include the reason, before/after differences, usage examples, affected project/module/system/chip scope, and the patch when available.
   - For `已拒绝`, include the explicit rejection reason and the recorded software version manager agreement.
   - For `反馈`, include the analysis-process conclusion and the recorded issue creator agreement.

   Use concrete evidence and preserve uncertainty in the wording when the scope or cause is not established. The conclusion remains concise and in Chinese.

7. **Present the draft and wait.** Show the target issue/project, exact tracker, local rule source, `source_version`, `checked_at`, and `checked_by`, latest Git commit SHA, Gerrit instance, change number, revision SHA, branch, project, status, and matching basis, evidence-based change summary, current conclusion, and proposed conclusion in a fenced text block. State that no Redmine write has happened. Ask for explicit confirmation in exactly this format: `确认更新`. Trim surrounding ASCII whitespace before matching; a request for edits, a vague acknowledgement, a partial phrase, or any other text is not confirmation: state the concrete reason and re-ask with the required format. Keep the user's raw confirmation text verbatim and include it in the final report. This protocol has no `abandoned` prerequisite; non-mainline patch abandonment is outside this skill and the user handles it separately. A request for edits starts a revised draft and requires confirmation again.

Phase 1 is complete only when the issue is verified as `bu1-sdk`, the `结论` field is identified, the available Git/Gerrit evidence is summarized, and the complete proposed conclusion has been shown.

## Phase 2: Update and verify the conclusion

1. Re-check the user's latest message against the Phase 1 confirmation contract: trim surrounding ASCII whitespace and require exactly `确认更新`; anything else is not confirmation: give the concrete reason and re-ask with the required format. If the user requests an edit, apply exactly that edit, re-run every affected check (conclusion structure, underlying facts and fields, Git/Gerrit identity, verified scope), display the revised draft with the user's raw edit request preserved verbatim, and wait for confirmation again. When any new fact arrives after confirmation: a changed issue value, a changed or refreshed rule snapshot, a changed commit or Gerrit identity, or a corrected user-supplied fact: re-run all affected checks and require a fresh confirmation; never proceed on a partial re-check of one aspect while others may have changed.

2. Before writing, re-read the issue and verify that the project is still `bu1-sdk`, the `结论` field ID is unchanged, and the current conclusion has not changed in a way that invalidates the draft. Re-read the local rule snapshot metadata and confirm its `source_version`, `checked_at`, `checked_by`, and content hash are unchanged from Phase 1; a changed or newly refreshed snapshot invalidates the draft and requires regeneration and confirmation. If any of these changed, refresh the analysis and ask for confirmation again.

3. Send one authenticated `PUT /issues/<issue-id>.json` request with `Content-Type: application/json`. In the request, update only:
   - the `结论` custom field using its discovered ID;
   - `issue.notes` with a concise Chinese audit note beginning exactly with `由 luyong-AI 操作：` and listing the issue ID plus the conclusion summary.

   Do not update `status_id`, `done_ratio`, assignee, tags, target version, dates, relations, or any other custom field. Do not claim success before the request returns success.

4. Re-read the issue after the PUT and verify the `结论` custom-field value. Report the issue ID, project, tracker, updated conclusion, timestamp if returned, and the Gerrit identity (change number, revision SHA, branch, project, status, and matching basis). Report HTTP or verification failures plainly and do not claim completion when verification fails.

The workflow is complete after the verified Redmine issue contains the approved conclusion and the required audit note.
