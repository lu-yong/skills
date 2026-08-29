---
name: commit-gerrit
description: Submit changes as a Nationalchip Gerrit review, using the local patch-rule snapshot and requiring a valid issue number, a confirmed commit draft, an amend choice, and a verified target branch before pushing.
disable-model-invocation: true
---

# Commit Gerrit

This is a side-effectful skill that the user must invoke explicitly. It exists only to create review patches on the company Gerrit; do not invoke it automatically for ordinary commit, push, or Gerrit query requests. Complete the checks and draft first, then proceed step by step only after user confirmation.

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

**When the tool is unavailable.** A non-interactive host strips `ask_user_question` from the tool list entirely, so the gate cannot be reached at all. When the tool is absent from the available tools, or a call returns `no_ui` or `no_custom_ui`, stop and report that this skill requires an interactive host. Never substitute a natural-language confirmation, and never run `git add`, `git commit`, or `git push` on that path.

## Immutable Preconditions

- Require the user to provide one Redmine issue number. Accept only a single positive integer matching `^[1-9][0-9]*$`; reject URLs, `#123`, ranges, comma-separated values, values with surrounding text, and non-decimal IDs.
- Use the available **Redmine** skill to read `https://git.nationalchip.com/redmine/issues/<id>.json`, confirm the issue exists and is accessible with the current credentials. Record the issue number, project identifier, title, tracker, and status; stop and ask the user when the issue is inaccessible or does not exist.
- Business rules come solely from this skill's local snapshot [references/bu1-sdk-gerrit-rules.md](references/bu1-sdk-gerrit-rules.md); read it fully before drafting. Use the local snapshot as-is. This skill does not validate snapshot freshness, source version, metadata completeness, or a refresh transaction, and does not route to [refresh-bu1-sdk-rules](../refresh-bu1-sdk-rules/SKILL.md). Snapshot updates are the user's responsibility via that refresh skill. Do not access the online Wiki, refresh online rules, or write or silently modify any reference file during the run.
- The current Git repository's changes are the default commit scope, including staged, unstaged, and unignored untracked files. Use an explicit scope only when the user specifies files, paths, patches, or a range.
- The local work branch must first pass the “Phase 0: local work-branch hard gate”: it must not be detached HEAD, `main`, `master`, `develop`, `sdk-release`, or share the name of the Gerrit target branch, and it must have a valid configured target branch. End the skill immediately on failure and ask the user to create and switch to a local work branch before invoking again.
- Before pushing, confirm the current branch has a non-empty `branch.<local_branch>.merge` and that the target branch exists on the push remote. Stop when the config is missing or the remote-branch check fails; never create, rename, or guess the target branch.
- Gerrit commits must carry a valid `Change-Id` generated by the repository's `commit-msg` hook. Stop when the hook is not executable, the hook fails, or the final commit lacks a valid `Change-Id: I<40 hex characters>` footer; never fabricate a Change-Id by hand.
- Never display or write the Redmine API key, Gerrit password, netrc contents, Authorization header, or other credentials.

## Phase 0: Local Work-Branch Hard Gate

This is the first step of the skill and must run before Redmine validation, change analysis, and draft generation. Run:

```bash
local_branch=$(git branch --show-current)
test -n "$local_branch" || { printf '%s\n' 'commit-gerrit 已停止：当前处于 detached HEAD，未创建或未切换到本地工作分支。请先创建并切换工作分支后重新调用 skill。' >&2; exit 1; }
dest_branch=$(git config --get "branch.$local_branch.merge" | sed 's#^refs/heads/##')
test -n "$dest_branch" || { printf '%s\n' 'commit-gerrit 已停止：当前本地分支没有配置 Gerrit 目标分支。请先创建并配置工作分支后重新调用 skill。' >&2; exit 1; }
case "$local_branch" in
  main|master|develop|sdk-release) printf '%s\n' 'commit-gerrit 已停止：当前分支是基础分支，不是本地工作分支。请先创建并切换 topic/work 分支后重新调用 skill。' >&2; exit 1 ;;
esac
test "$local_branch" != "$dest_branch" || { printf '%s\n' 'commit-gerrit 已停止：当前本地分支与 Gerrit 目标分支相同，不是独立工作分支。请先创建并切换工作分支后重新调用 skill。' >&2; exit 1; }
remote_name=$(git config --get "branch.$local_branch.remote")
test -n "$remote_name" || { printf '%s\n' 'commit-gerrit 已停止：当前分支没有配置 branch.<local_branch>.remote。请先配置工作分支对应的 push remote 后重新调用 skill。' >&2; exit 1; }
pushurl_count=$(git config --get-all "remote.$remote_name.pushurl" | wc -l | tr -d ' ')
if [ "$pushurl_count" -gt 1 ]; then printf '%s\n' 'commit-gerrit 已停止：当前分支对应 remote 配置了多个 pushurl，无法唯一确定推送目标。请先处理 remote 配置后重新调用 skill。' >&2; exit 1; fi
if [ "$pushurl_count" -eq 1 ]; then
  push_url=$(git config --get "remote.$remote_name.pushurl")
else
  url_count=$(git config --get-all "remote.$remote_name.url" | wc -l | tr -d ' ')
  test "$url_count" -eq 1 || { printf '%s\n' 'commit-gerrit 已停止：当前 remote 没有唯一 pushurl 或 url，无法确定推送目标。请先处理 remote 配置后重新调用 skill。' >&2; exit 1; }
  push_url=$(git config --get "remote.$remote_name.url")
fi
test -n "$push_url" || { printf '%s\n' 'commit-gerrit 已停止：当前 remote 的推送 URL 为空。请先配置 remote 后重新调用 skill。' >&2; exit 1; }
remote_host=$(printf '%s\n' "$push_url" | sed -E 's#^[^:]+://([^@/]+@)?([^/:]+).*#\2#; s#^[^@]+@([^:]+):.*#\1#')
case "$remote_host" in
  git.nationalchip.com|gerrit.nationalchip.com) ;;
  *) printf '%s\n' 'commit-gerrit 已停止：push URL host 不是允许的公司 Gerrit host。请先确认 remote 配置后重新调用 skill。' >&2; exit 1 ;;
esac
git ls-remote --exit-code --heads "$push_url" "refs/heads/$dest_branch" >/dev/null || { printf '%s\n' 'commit-gerrit 已停止：Gerrit 目标分支尚未创建或当前 push URL 无法访问。请先确认目标分支和 push URL 后重新调用 skill。' >&2; exit 1; }
confirmed_remote_name="$remote_name"
confirmed_push_url="$push_url"
confirmed_remote_host="$remote_host"
confirmed_dest_branch="$dest_branch"
printf '%s\n' '已固定本次流程目标：remote 名称、push URL、host 和目标 branch。这些硬检查只在阶段零执行，是唯一权威首次执行点；后续阶段不重新执行这些检查，只复核快照一致性，并只能使用这些已确认值。'
```

When any check above fails, end this skill invocation immediately: do not read Redmine, analyze Git changes, generate a commit draft, or run any `git add`, `git commit`, or `git push`. Do not auto-create, switch, rename, or repair branches. The user must create/switch to a local work branch and configure the target branch, then invoke the skill again.

## Phase 1: Inspect and Draft

1. First validate the Redmine issue number and read the issue details. A syntactically valid number only means well-formed; the number counts as a “valid issue number” only when the API returns the issue details. Record the project identifier as context. The Redmine ID used in the commit message is that validated issue number; no separate Unify association is required.
2. Read the local reference before continuing rule analysis. Use it as-is; do not validate freshness, version, or a refresh transaction.
3. Resolve the repository root and collect the current state:
   - `git rev-parse --show-toplevel`
   - `git status --short`
   - `git branch --show-current`
   - the current branch's remote, merge config, and push URL.
   The default scope must list every path that would be committed, including deleted, modified, added, and staged paths. For untracked files, read only what is necessary to check whether they are sensitive files, build artifacts, or unrelated content; do not output file contents or credentials to the user. Record the fixed fields of the state collection per the Fixed Workspace Snapshot Format.
4. Inspect the full change against the `HEAD` baseline: use `git diff --binary HEAD` for staged and unstaged changes; check untracked files separately. Generate and record the complete snapshot per the Fixed Workspace Snapshot Format; the snapshot records only paths, types, sizes, and hashes, never file contents or credentials. When the user explicitly specified a scope:
   - First read the index paths that existed before the skill was invoked with NUL-safe `git diff --cached --name-only -z` and compare the complete path set against `confirmed-paths`; cover modified, added, deleted, renamed, and space-containing paths.
   - When any pre-existing staged path is outside the confirmed scope, show the paths, scope, and blocker, then call `ask_user_question` with one question whose `header` is `提交范围`, whose `question` asks whether the displayed staged paths should be included in this patch, and whose two options are `扩展提交范围` (`description`: include them, regenerate the complete draft, and obtain a fresh `提交确认` answer) and `自行处理暂存区` (`description`: stop without changing the index so the user can adjust the staging area). Continue only when `details.error` is absent, `details.cancelled` is `false`, and an `answers` entry whose `question` equals this call's `question` text has `kind: "option"` and `answer` exactly `扩展提交范围`. An `answer` of `自行处理暂存区`, or `details.cancelled: true` with no `details.error`, stops; a missing entry, `kind: "custom"`, or a mismatched label repeats the same call unchanged; a `details.error` is handled per the contract's error rules and never repeats the call unchanged. Never run `git restore --staged` or silently alter the user's index.
   - When no out-of-scope paths exist, confirm every in-scope path is present in the snapshot, and record the scope, the pre-existing staged paths, and the paths to be added separately in the draft.
5. Re-check the work-branch targets fixed in Phase 0 (snapshot-consistency re-check only; do not re-run Phase 0's hard checks):
   - Re-read the current raw value of `branch.<local_branch>.remote`, all `pushurl` values of that remote (all `url` values when no `pushurl` exists), the parsed host, and the current raw value of `branch.<local_branch>.merge`.
   - Compare these current values field by field against the `confirmed_remote_name`, `confirmed_push_url`, `confirmed_remote_host`, and `confirmed_dest_branch` saved in Phase 0.
   - When any value changed, is missing, or differs from the confirmed value (including newly appearing multiple candidates), stop and regenerate the draft; do not pick another remote and do not re-run Phase 0's host allowlist or `ls-remote` checks (they are Phase 0's sole responsibility).
   - The draft shows the remote name, push URL (redacted per the secret-handling rules), host, target branch, and the consistency-check result.
6. Check the repository hooks path:
   ```bash
   commit_msg_hook=$(git rev-parse --git-path hooks/commit-msg)
   test -x "$commit_msg_hook" || { printf '%s\n' '缺少可执行 commit-msg hook' >&2; exit 1; }
   ```
   When the repository uses `core.hooksPath`, use the path Git resolves.
7. Read and apply [references/bu1-sdk-gerrit-rules.md](references/bu1-sdk-gerrit-rules.md) in full, validating the `Type: [Redmine ID]: [Subject]` structure, the Type enum, and the Subject (at most 50 characters, Simplified Chinese imperative, English proper-noun exceptions, no trailing period), Body (at most 72 characters per line), Footer, and `Change-Id` rules per the 补丁提交格式 section. When the Type cannot be determined uniquely, call `ask_user_question` with one question whose `header` is `提交类型` and whose `question` asks which Type the displayed change summary should use; each option carries the Type token as its `label` and that Type's rule meaning as its `description`. The reference's Type enum has 7 members, so batch per the contract's **Batching candidates** rule: first display every candidate Type and its meaning as text, then ask at most 3 candidate Types per call plus a fourth option labelled `下一批候选` (`description`: 展示并询问下一批候选 Type，本次不选定任何 Type), where the last batch's `下一批候选` wraps back to the first batch so no candidate becomes unreachable; ask all candidates in a single call only when 4 or fewer remain. The seven Type tokens are plain ASCII identifiers, so they neither hit a reserved label nor collide with `下一批候选`; still apply the contract's **Labels built from external data** rule if a refreshed snapshot ever introduces a Type token that does. Never shrink the candidate set by guessing. Use only an `answers` entry whose `question` equals this call's `question` text, whose `kind` is `option`, and whose `answer` exactly equals one of the Type tokens displayed in the batch just sent; an `answer` of `下一批候选` advances to the next batch and decides nothing, and a label absent from the batch just sent is an unmatched label. `details.cancelled: true` with no `details.error` stops drafting; a missing entry, `kind: "custom"`, or a mismatched label re-issues the same call unchanged; a `details.error` is handled per the contract's error rules. Mark the draft with the `source_version`, `checked_at`, and `checked_by` used.
   - The complete commit message may only contain confirmed facts; generate the Subject per the reference's Subject rules, not by copying the Redmine title.
   - Follow the reference's 补丁代码提交者要求 section for the committer guarantees (code conventions, no excess code/files, self-testing) and the 测试时序 and 执行解释 sections for clean-version test timing and Review/dependency status: this skill does not ask for self-test logs, commands, or test output and does not stop for missing self-test evidence; unless the user explicitly says self-testing was not done or asks for testing help, treat self-testing as the user's guarantee that it passed. Keep self Review+1, Reviewer, and dependency-patch status unknown when unknown; never assume completion in the draft or final report. Every rule must point to a local rule reference or current fact.
8. Generate the commit-message draft. The draft may only use confirmed facts and must show the full subject, body, and footer to be committed; associate the Redmine issue number in the exact format of the read rules. Do not write local paths, unverified test results, or guesses as facts.
9. Show the user the following, then stop and invoke `ask_user_question` for the decision:
   - The Redmine issue details, the recorded `issue.project.identifier`, and the access result.
   - The Git repository, current work branch, target branch, push remote, and push scope.
   - The changed-file list and a brief factual summary.
   - The local rule snapshot's source page, version, `checked_at`, and `checked_by`.
   - The fixed-field snapshot summary (`HEAD`, worktree and staged diff hashes, untracked-file hashes, branch/merge/remote/push URL/target branch, `commit-msg` hook path and hash; no file contents, hook contents, or credentials).
   - The Gerrit rule requirements and any questions still awaiting the user (do not enter the confirmation phase while any remain).
   - The complete commit-message draft.
   - An explicit statement that no `git add`, `git commit`, or `git push` has been run in this flow; state truthfully any pre-existing user staged state.

   Use this call shape:
   ```json
   {
     "questions": [
       {
         "header": "提交确认",
         "question": "是否按以上完整草稿和已展示的固定工作区快照创建并推送 Gerrit 审核补丁？",
         "options": [
           {
             "label": "确认提交",
             "description": "允许后续按快照执行 git add、git commit，并在提交验证通过后推送。"
           },
           {
             "label": "修改草稿",
             "description": "暂不执行任何 Git 写操作；随后用文字说明需要修改的内容。"
           },
           {
             "label": "取消提交",
             "description": "结束本次流程，不执行 git add、git commit 或 git push。"
           }
         ]
       }
     ]
   }
   ```
   Continue to Phase 2 only when `details.error` is absent, `details.cancelled` is `false`, and `details.answers` contains an entry whose `question` equals this call's `question` text, whose `kind` is exactly `option`, and whose `answer` is exactly `确认提交`. For `修改草稿`, collect the requested edit, rerun the affected checks, show a revised complete draft, and invoke the same call again. An `answer` of `取消提交` ends the flow without any Git write, and is the recordable decline: record it in the final report. `details.cancelled: true` with no `details.error` means the user declined or pressed `Esc`: stop without any Git write and report that the confirmation was interrupted rather than that the user rejected the draft. A missing entry, `kind: "custom"` (including free text that reads like `确认提交`), or a mismatched label re-issues the same call unchanged; a `details.error` is handled per the contract's error rules and never re-issues the call unchanged. Natural-language replies, `details.globalNote`, and `answers[].notes` are never confirmation, and the tool's prose text is never the decision. Record the matched `question`, `answer` label, and `header` instead of requiring a typed `确认提交` reply.
## Fixed Workspace Snapshot Format

Phase 1 generates the fixed-field snapshot once and records it in the draft; Phase 2 regenerates it in the same format before `git add` and compares field by field. Any field change invalidates the Phase 1 `提交确认` answer and requires regenerating the draft and issuing the `提交确认` question again.

Fixed fields and their generation:

| Field | Generation method |
| --- | --- |
| `HEAD` SHA | the full 40-character SHA of `git rev-parse HEAD` |
| Worktree change hash | SHA-256 of the `git diff --binary HEAD` output |
| Staged change hash | SHA-256 of the `git diff --cached --binary` output |
| Untracked-file hash | one `path|type|size|content-SHA-256` line per path listed by `git ls-files --others --exclude-standard -z`, sorted by path, then one more SHA-256 over the whole list |
| Current branch | `git branch --show-current` |
| Merge config | the normalized value of `git config --get branch.<local_branch>.merge` |
| Remote name | `git config --get branch.<local_branch>.remote` |
| Push URL | the unique `pushurl` confirmed in Phase 0 (the unique `url` when no `pushurl` exists) |
| Target branch | `branch.<local_branch>.merge` with the `refs/heads/` prefix removed |
| Hook path | `git rev-parse --git-path hooks/commit-msg` (the Git-resolved path when `core.hooksPath` is set) |
| Hook hash | SHA-256 of the `commit-msg` hook file |

Generation example (use `shasum -a 256` on macOS and `sha256sum` on Linux for SHA-256):

```bash
git rev-parse HEAD
git diff --binary HEAD | shasum -a 256
git diff --cached --binary | shasum -a 256
git ls-files --others --exclude-standard -z | while IFS= read -r -d '' f; do
  [ -L "$f" ] && t=symlink || t=file
  printf '%s|%s|%s|%s\n' "$f" "$t" "$(wc -c < "$f" | tr -d ' ')" "$(shasum -a 256 "$f" | cut -d' ' -f1)"
done | sort | shasum -a 256
```

Rules:

- The snapshot records only paths, types, sizes, and hashes; it never records or outputs untracked-file contents, diff contents, hook contents, credentials, or any secret; when content, `HEAD`, remote, hook, or untracked files change without a filename change, the corresponding hash or field value differs and must be discoverable.
- Record untracked files one per line as `path|type|size|content-SHA-256`, sorted by path so they are comparable; type is only `file`/`symlink` and size is in bytes.
- Phase 2 regenerates every field before `git add` and compares each against Phase 1: stop immediately when any field is missing, ungeneratable, or different; re-run Phase 1 to generate a new draft and issue the `提交确认` question again; continue to `git add` only when every field matches.

## Phase 2: Stage After ask_user_question Confirmation

1. Accept only a `提交确认` answer entry with `kind: "option"` and `answer` exactly `确认提交`, obtained for the complete Phase 1 draft with `details.error` absent, `details.cancelled: false`, and a `question` equal to the `提交确认` call's `question` text. An `answer` of `修改草稿` starts revised checks and a fresh call; an `answer` of `取消提交` ends the flow. `details.cancelled: true` with no `details.error` ends the flow; a missing entry, `kind: "custom"`, or a mismatched label re-issues the same call unchanged; a `details.error` is handled per the contract's error rules; natural-language replies and `details.globalNote` do not authorize staging. When the user changes the issue number, scope, message, or any rule-related content, re-run the affected checks, show a new draft, and obtain a fresh structured confirmation.
2. Before running `git add`, regenerate every snapshot field per the Fixed Workspace Snapshot Format and compare each against the Phase 1 record. Any field change (`HEAD`, worktree or staged diff hash, untracked files, branch, merge config, remote name, push URL, target branch, `commit-msg` hook path or hash) invalidates the Phase 1 confirmation: stop, re-run Phase 1 to generate a new draft, and issue the `提交确认` question again; never silently fold changes produced after confirmation into the commit.
3. Run `git add` only after confirming the snapshot is unchanged:
   - Default scope: run `git add -A -- .` at the repository root.
   - User-specified scope: run `git add -A -- <confirmed-paths>` only on the confirmed paths, handling deletions and space-containing paths correctly.
4. Re-check the staged content with `git diff --cached --check`, `git diff --cached --stat`, NUL-safe `git diff --cached --name-only -z`, and `git diff --cached` as needed. With a user-specified scope, the staged path set must be a subset of `confirmed-paths`; when any path is out of scope, disallowed by the rules, or fails validation, stop without committing and without running `git restore --staged`.
5. Tell the user the actually staged file list, staging statistics, and remaining risks. Do not commit yet. Invoke `ask_user_question` with this single-choice decision:
   ```json
   {
     "questions": [
       {
         "header": "提交方式",
         "question": "暂存内容已复核，本次是创建新提交还是改写当前最新提交？",
         "options": [
           {
             "label": "amend 当前提交",
             "description": "改写当前最新提交；将保留其 Subject、Body 和 Footer，并在提交前展示合成后的消息。"
           },
           {
             "label": "创建新提交",
             "description": "使用 Phase 1 已确认的完整 commit message 创建新提交。"
           },
           {
             "label": "暂不提交",
             "description": "停在这里，保留当前暂存区；不执行 git commit 或 git push。"
           }
         ]
       }
     ]
   }
   ```
   Accept only an `answers` entry whose `question` equals this call's `question` text, whose `kind` is exactly `option`, and whose `answer` is exactly `amend 当前提交` or `创建新提交`, with `details.error` absent and `details.cancelled: false`. An `answer` of `暂不提交` stops, preserves the staging area, and is the recordable decline: record it in the final report. `details.cancelled: true` with no `details.error` stops and preserves the staging area, and is reported as an interrupted confirmation rather than a rejection; a missing entry, `kind: "custom"`, or a mismatched label re-issues the same call unchanged; a `details.error` is handled per the contract's error rules; any free-form `1`/`2` reply and any `details.globalNote` are not a choice. Do not commit until a valid choice is recorded.
## Phase 3: Amend Choice, Commit, and Push

1. Consume the valid `提交方式` answer recorded in Phase 2. For `amend 当前提交`, confirm that `HEAD` exists and proceed only with the rewrite described in that option's `description`; for `创建新提交`, create a new commit. Do not accept a typed `1`/`2` or any other natural-language choice. After choosing `amend 当前提交`, never overwrite `HEAD`'s existing message with the Phase 1 draft generated for a new commit: first read and record `HEAD`'s complete commit message, then append a factual summary of the confirmed staged changes as a new paragraph to the existing Body. Preserve `HEAD`'s existing Subject, Body, and Footer exactly; insert the summary before the existing Footer (including `Change-Id`); only when there is no Footer, append it at the end of the message. Stop and ask when the Footer cannot be identified reliably or a factual summary cannot be generated from the actual changes.
2. Save the final commit message in a temporary file: a new commit uses the complete Phase 1-confirmed draft; an amend uses the message synthesized per the previous step. For an amend, display the complete synthesized message and invoke `ask_user_question` with one question whose `header` is `amend 消息确认`, whose `question` asks whether to amend the latest commit with the displayed message, and whose three options are `确认使用此消息` (`description`: 按已展示的完整消息执行 git commit --amend。), `修改 amend 消息` (`description`: 暂不执行 git commit --amend，保留暂存区；随后用文字说明调整要求，重新合成消息后再次确认。), and `取消 amend` (`description`: 结束本次流程，保留暂存区，不执行 git commit 或 git push。). Run `git commit --amend -F <temporary-message-file>` only when `details.error` is absent, `details.cancelled` is `false`, and an `answers` entry whose `question` equals that call's `question` text has `kind: "option"` and `answer` exactly `确认使用此消息`. An `answer` of `修改 amend 消息` collects the requested edit, re-synthesizes the message, and re-issues the same call; an `answer` of `取消 amend` stops, preserves the staging area, and is the recordable decline; `details.cancelled: true` with no `details.error` stops and preserves the staging area, and is reported as an interrupted confirmation rather than a rejection; a missing entry, `kind: "custom"`, or a mismatched label re-issues the same call unchanged; a `details.error` is handled per the contract's error rules; free-form replies and `details.globalNote` do not authorize the commit. For a new commit, use the already confirmed `提交确认` draft. Set `GIT_EDITOR=true` to avoid opening an interactive editor; do not put the temporary file into the repository. On commit failure, preserve the staging area, report the error, and do not push.
3. Before committing, re-check the staged path set with NUL-safe `git diff --cached --name-only -z`. With a user-specified scope, any path outside `confirmed-paths` stops the flow; record the actual staged set for comparing the actual commit scope afterward.
4. After a successful commit, verify with `git status --short`, `git show --stat --oneline HEAD`, `git diff-tree --no-commit-id --name-only -r HEAD -z`, the full commit message, the author, and `Change-Id`. Compare the actual committed path set with the staged set recorded before the commit; stop and ask the user when the path sets differ, the hook rewrote the message, there is no valid Change-Id, or the commit result differs from the draft.
5. After the commit succeeds and every rule/precondition re-check passes, push to the Gerrit review ref using only the `confirmed_remote_name`, `confirmed_push_url`, and `confirmed_dest_branch` fixed in Phase 0; do not re-resolve, re-read, or re-select the remote, host, push URL, or target branch, do not rewrite as a plain-branch push, and do not add `--force`:
   ```bash
   git push \
        --receive-pack='gerrit receive-pack' \
        --no-follow-tags \
        "$confirmed_remote_name" \
        "refs/heads/$local_branch:refs/for/$confirmed_dest_branch"
   ```
6. Report the patch as submitted to the Gerrit review only when `git push` returns success. The final report includes the Redmine issue number, commit SHA, whether it was an amend, the commit-message summary, and the Phase 0-confirmed `confirmed_remote_name`, `local_branch`, `confirmed_dest_branch`, and the Gerrit review ref; on push failure, summarize the error and next steps verbatim without claiming the patch entered the review.
   - Report the “clean-version patch full functional test” and committer self Review+1 statuses separately; when not yet done or the user provided no evidence, mark them “pending/unknown” and never write them as passed.

## Stop Conditions

Stop at the current phase and explain the concrete reason to the user for any of: unavailable credentials; a nonexistent Redmine issue number; a missing or unreadable local rule snapshot; a rule conflict; a Phase 0 local work-branch hard-gate failure; an unconfirmable committer role; unconfirmable branch/remote/target branch; `ask_user_question` being unavailable or returning a host error (`no_ui`, `no_custom_ui`, `session_load_failed`, `stale_module_cache`); any fixed workspace snapshot field changing after confirmation; a user-specified scope containing pre-existing out-of-scope staged paths; staged paths exceeding the confirmed scope after `git add` or before commit; the scope containing unconfirmed sensitive or unrelated files; a missing `commit-msg` hook; a message that violates the rules; a missing Change-Id; a failed commit; or a failed push. The flow must never fetch rules over the network, rewrite the reference, unstage the user's existing staging, or widen the commit scope. On a Phase 0 failure, do not continue to read Redmine, analyze Git changes, or generate a commit draft; the user must create and switch to a local work branch and invoke the skill again. Ask the user about any uncertain rule or fact; never fill in with assumed values.
