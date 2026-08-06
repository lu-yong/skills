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

5. **Resolve the Gerrit change through the Gerrit skill.**
   - Determine the Gerrit instance from the Git remote. Use the internal instance for `git.nationalchip.com` and the external instance for `gerrit.nationalchip.com`; ask the user to choose when the host is ambiguous.
   - Use the latest commit SHA to query the selected Gerrit instance for the matching change. When available, use the commit's `Change-Id` footer as a second identity check. Obtain the numeric Gerrit change number (`_number`) and fetch its detail. Use the current revision or the exact matching revision as appropriate.
   - Inspect changed files and the patch needed to report the change accurately. Do not inspect or infer testing, review, or dependency completion from Gerrit labels, branch state, or other repository evidence. Respect the Gerrit skill's XSSI parsing, authentication, TLS, and secret-handling rules.
   - If no matching change can be found, or multiple changes cannot be disambiguated, ask the user for the Gerrit instance/change identity. Do not fabricate a change number.

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
   Accept exactly one of `1`, `2`, or `3`. For any other input, show the same prompt again. Map `1` to the ordinary conclusion structure; map `2` and `3` to the corresponding patch-cause structure. This selection affects only the conclusion draft; it does not update the `问题性质` field.

   Apply the supplemental format for the issue's current context:
   - For an `错误` issue whose `问题性质` is `当前版本修改引入` or `上个版本修改引入`, include the patch-cause wording and `修改补丁：{{patch(<Gerrit change number>)}}` when the numeric change number is available.
   - For `规格变更`, include the reason, before/after differences, usage examples, affected project/module/system/chip scope, and the patch when available.
   - For `已拒绝`, include the explicit rejection reason and the recorded software version manager agreement.
   - For `反馈`, include the analysis-process conclusion and the recorded issue creator agreement.

   Use concrete evidence and preserve uncertainty in the wording when the scope or cause is not established. The conclusion remains concise and in Chinese.

7. **Present the draft and wait.** Show the target issue/project, exact tracker, local rule source, `source_version`, `checked_at`, and `checked_by`, latest Git commit SHA, Gerrit instance/change number, evidence-based change summary, current conclusion, and proposed conclusion in a fenced text block. State that no Redmine write has happened. Ask for explicit confirmation such as `确认更新`; a request for edits starts a revised draft and requires confirmation again.

Phase 1 is complete only when the issue is verified as `bu1-sdk`, the `结论` field is identified, the available Git/Gerrit evidence is summarized, and the complete proposed conclusion has been shown.

## Phase 2: Update and verify the conclusion

1. Re-check that the user's latest message explicitly confirms the displayed conclusion draft. If the user requests any edit, apply the edit, rerun the conclusion checks, display the revised draft, and wait for confirmation again.

2. Before writing, re-read the issue and verify that the project is still `bu1-sdk`, the `结论` field ID is unchanged, and the current conclusion has not changed in a way that invalidates the draft. Re-read the local rule snapshot metadata and confirm its `source_version`, `checked_at`, `checked_by`, and content hash are unchanged from Phase 1; a changed or newly refreshed snapshot invalidates the draft and requires regeneration and confirmation. If any of these changed, refresh the analysis and ask for confirmation again.

3. Send one authenticated `PUT /issues/<issue-id>.json` request with `Content-Type: application/json`. In the request, update only:
   - the `结论` custom field using its discovered ID;
   - `issue.notes` with a concise Chinese audit note beginning exactly with `由 luyong-AI 操作：` and listing the issue ID plus the conclusion summary.

   Do not update `status_id`, `done_ratio`, assignee, tags, target version, dates, relations, or any other custom field. Do not claim success before the request returns success.

4. Re-read the issue after the PUT and verify the `结论` custom-field value. Report the issue ID, project, tracker, updated conclusion, timestamp if returned, and the Gerrit change number. Report HTTP or verification failures plainly and do not claim completion when verification fails.

The workflow is complete after the verified Redmine issue contains the approved conclusion and the required audit note.
