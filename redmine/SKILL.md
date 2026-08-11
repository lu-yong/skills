---
name: redmine
description: Use when the user asks to query, create, update, delete, analyze, or organize Redmine issues, projects, users, time entries, attachments, watchers, statuses, trackers, priorities, custom fields, bookmarks, or work logs on the Nationalchip Redmine instance.
---

# Redmine

## Instance

- URL: `https://git.nationalchip.com/redmine`
- API key file: `SECRET.md` in the directory containing this loaded `SKILL.md`; resolve it relative to the skill directory, not a Codex/OpenCode install path.
- Preferred auth header: `X-Redmine-API-Key: <key>`

Read `SECRET.md` only when a Redmine API call is needed. It may contain comments and blank lines. Extract exactly one non-empty configuration line matching `^API_KEY=` and use only the value after the first `=`; never assume the key is on the first line or use a comment/title as the key. Fail closed when the matching line is missing, duplicated, or has an empty value. Do not print the key, include it in final answers, or write it into repository files. If running shell commands, avoid command forms that echo the key into logs.

## Workflow

1. Identify whether the user wants to read, create, update, delete, upload, or analyze Redmine data.
2. Use Redmine REST JSON endpoints with the API key header.
3. For lists, request `limit=100` and handle pagination with `offset` until all required data is collected.
4. For `POST` and `PUT`, send `Content-Type: application/json`.
5. Summarize results clearly for the user. Include issue IDs, subjects, status, assignee, project, and timestamps when relevant.
6. For destructive or broad changes, confirm intent before executing unless the user explicitly requested the exact operation.

## AI Write Audit Trail

Every Redmine write operation performed by the AI must leave a visible audit note using this exact prefix:

`由 luyong-AI 操作：`

- Append a concise Chinese summary of the actual operation after the prefix, including the important changed fields and values.
- For issue creation, include the audit text in the issue description or creation notes if supported, without replacing user-provided content.
- For issue updates, always send the audit text through `issue.notes` in the same `PUT /issues/{id}.json` request.
- For writes to related resources that cannot carry notes directly (such as watchers, relations, attachments, or time entries), add an audit note to the associated issue immediately after the write.
- For deletion, add the audit note to the associated issue before deletion. If the issue itself will be deleted, state in the pre-deletion note that the issue is about to be deleted.
- Do not claim success in the note before an operation that may fail, except for the required pre-deletion note. For multi-step writes, only summarize steps that actually succeeded.
- Read-only queries and analyses do not require an audit note.

## Common Endpoints

- Issue list: `GET /issues.json`
- Issue detail: `GET /issues/{id}.json?include=journals,attachments,relations,children`
- Create issue: `POST /issues.json`
- Update issue or add notes: `PUT /issues/{id}.json`
- Delete issue: `DELETE /issues/{id}.json`
- Add watcher: `POST /issues/{id}/watchers.json`
- Remove watcher: `DELETE /issues/{id}/watchers/{user_id}.json`
- Projects: `GET /projects.json`, `GET /projects/{id}.json`
- Current user: `GET /users/current.json?include=memberships,groups`
- Time entries: `GET /time_entries.json`, `POST /time_entries.json`, `PUT /time_entries/{id}.json`
- Statuses: `GET /issue_statuses.json`
- Trackers: `GET /trackers.json`
- Priorities: `GET /enumerations/issue_priorities.json`
- Search: `GET /search.json?q=<query>`

## Common Filters

- Assigned to me: `/issues.json?assigned_to_id=me&status_id=open&limit=100`
- All statuses in project: `/issues.json?project_id=<id>&status_id=*&limit=100`
- Recently updated: `/issues.json?sort=updated_on:desc&limit=20`
- Specific issues: `/issues.json?issue_id=1,2,3`
- Date range for time entries: `/time_entries.json?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=100`

## Status IDs

| ID | Status |
| --- | --- |
| 1 | New |
| 2 | In Progress |
| 3 | Resolved |
| 4 | Feedback |
| 5 | Closed |
| 6 | Rejected |

## Detailed Reference

For payload shapes, attachment upload flow, relation types, custom fields, bookmark plugin notes, and additional examples, read [references/redmine-api.md](references/redmine-api.md).
