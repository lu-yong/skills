---
name: redmine
description: Use when the user asks to query, create, update, delete, analyze, or organize Redmine issues, projects, users, time entries, attachments, watchers, statuses, trackers, priorities, custom fields, or work logs on the Nationalchip Redmine instance.
---

# Redmine

## Instance and credentials

- URL: `https://git.nationalchip.com/redmine` (override with `REDMINE_URL` for tests or another mirror; the value must be a bare HTTP(S) address).
- API key file: `SECRET.md` in this skill's own directory — resolve it relative to the loaded `SKILL.md` (skills may be symlinked; the script resolves its own real path), not to an install path. `REDMINE_SECRET_FILE` can point elsewhere.
- Auth is the `X-Redmine-API-Key` request header only. Never put the key in a URL query parameter, in HTTP Basic, or in an argv value. Do not print the key, include it in final answers, or write it into repository files.

`SECRET.md` may contain comments and blank lines. Exactly one non-empty line must match `^API_KEY=`; use only the value after the first `=`. Fail closed when the line is missing, duplicated, or empty.

## CLI first

`scripts/redmine.py` (Python 3, standard library only) already implements credential handling, header auth, pagination, and the write audit. Prefer it over hand-written `curl`:

```bash
python3 redmine/scripts/redmine.py whoami                                   # 校验凭据
python3 redmine/scripts/redmine.py issue 434931                             # 详情（含 journals 等）
python3 redmine/scripts/redmine.py get /issues.json --param assigned_to_id=me --param status_id=open --all
python3 redmine/scripts/redmine.py get "/projects/bu1-sdk/wiki/Redmine使用规则.json"
```

Every command prints one JSON object and exits nonzero with `{"ok": false, "error": ..., "message": ...}` on failure. Read that error JSON — do not retry blindly, and never switch to another tool or a hand-built URL to work around it. When the script is unusable in your host (no Python 3, no file access), fall back to the endpoint reference below, keeping every rule in this file by hand.

- Lists paginate with `limit=100` + `offset`; the CLI's `--all` follows pages and reports `complete` — treat `complete: false` as truncated and say so.
- `POST`/`PUT` send `Content-Type: application/json`.
- The CLI deliberately offers no generic write command. Writes go through it only as `plan-conclusion` / `apply-conclusion` (see [update-issue-conclusion](../update-issue-conclusion/SKILL.md)); other writes are composed by hand from the endpoint reference and follow the audit rules below.

## AI Write Audit Trail

Every Redmine write operation performed by the AI must leave a visible audit note using this exact prefix:

`由 luyong-AI 操作：`

- Append a concise Chinese summary of the actual operation after the prefix, including the important changed fields and values.
- For issue creation, include the audit text in the issue description or creation notes if supported, without replacing user-provided content.
- For issue updates, always send the audit text through `issue.notes` in the same `PUT /issues/{id}.json` request.
- For writes to related resources that cannot carry notes directly (such as watchers, relations, attachments, or time entries), add an audit note to the associated issue immediately after the write.
- For deletion, add the audit note to the associated issue before deletion. If the issue itself will be deleted, state in the pre-deletion note that the issue is about to be deleted.
- Do not claim success in the note before an operation that may fail, except for the required pre-deletion note. For multi-step writes, only summarize steps that actually succeeded; verify before claiming completion.
- Read-only queries and analyses do not require an audit note.

## Workflow

1. Identify whether the user wants to read, create, update, delete, upload, or analyze Redmine data.
2. Read first: `whoami` to verify credentials when in doubt, then `issue` / `get` for the data. For large lists use `--all` and honor `complete`.
3. Writes: confirm intent for destructive or broad changes before executing unless the user explicitly requested the exact operation; follow the AI Write Audit Trail above; for issue conclusions use the gated `update-issue-conclusion` skill.
4. Summarize results clearly. Include issue IDs, subjects, status, assignee, project, and timestamps when relevant. Never include the API key.

## Common filters

- Assigned to me: `/issues.json?assigned_to_id=me&status_id=open&limit=100`
- All statuses in project: `/issues.json?project_id=<id>&status_id=*&limit=100`
- Recently updated: `/issues.json?sort=updated_on:desc&limit=20`
- Specific issues: `/issues.json?issue_id=1,2,3`
- Time entries in a date range: `/time_entries.json?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=100`

## Status IDs

| ID | Status |
| --- | --- |
| 1 | New |
| 2 | In Progress |
| 3 | Resolved |
| 4 | Feedback |
| 5 | Closed |
| 6 | Rejected |

## Detailed reference

For payload shapes, attachment upload flow, relation types, custom fields, bookmark plugin notes, and additional examples, read [references/redmine-api.md](references/redmine-api.md).
