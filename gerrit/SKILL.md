---
name: gerrit
description: Read-only workflows for querying Nationalchip Gerrit REST APIs, including change details, revisions, patches, changed files, projects, account information, and pagination. Use when the user asks to fetch, inspect, or summarize a Gerrit change or patch from git.nationalchip.com/gerrit or gerrit.nationalchip.com.
---

# Gerrit

Use this skill for read-only requests to the two Nationalchip Gerrit instances. Do not use it for creating reviews, comments, approvals, or other writes unless the user explicitly asks for a separate workflow.

## Instances

The two instances are not synchronized and their change numbers are independent. Confirm the target instance when the user does not identify it.

| Instance | API base URL | Authentication | TLS |
| --- | --- | --- | --- |
| Internal | `https://git.nationalchip.com/gerrit/a` | HTTP Digest | Verify the certificate normally |
| External | `https://gerrit.nationalchip.com/a` | HTTP Basic | The legacy certificate may require `--insecure` |

The `/a/` prefix is used for authenticated REST requests. A change identifier can be a number or a full Gerrit change ID such as `project~branch~I...`.

## Credentials

Never put a password in a prompt, URL, source file, shell history, command output, or final response. Do not expect this skill directory to contain a secret file. Credentials must be supplied by the user's existing credential setup.

For `curl`, prefer a user-owned netrc file. The default is `~/.netrc`; set `GERRIT_NETRC_FILE` when a different file is already configured. It must be readable only by the owner, for example `chmod 600 ~/.netrc`, and contain host entries for the required Gerrit hosts. Do not print or commit that file.

Use this common command prefix and keep the secret out of command arguments:

```bash
NETRC_FILE="${GERRIT_NETRC_FILE:-$HOME/.netrc}"
test -r "$NETRC_FILE" || { printf '%s\n' "Configure GERRIT_NETRC_FILE or ~/.netrc first" >&2; exit 1; }
```

Internal request:

```bash
curl --digest --netrc-file "$NETRC_FILE" \
  --fail --silent --show-error \
  'https://git.nationalchip.com/gerrit/a/accounts/self'
```

External request:

```bash
curl --netrc-file "$NETRC_FILE" \
  --fail --silent --show-error --insecure \
  'https://gerrit.nationalchip.com/a/accounts/self'
```

Only use `--insecure` for the external legacy endpoint when normal certificate verification fails. Do not broaden it to other hosts or hide the TLS warning from the user.

## Response handling

Successful Gerrit REST responses begin with the XSSI guard `)]}'`, usually followed by a newline. Remove that guard before parsing JSON; do not blindly remove the first four characters from a response that does not have the guard. Always check the HTTP status before parsing the body. Preserve the raw response when the user asks for a patch, because a patch is not JSON.

A Python parser for JSON responses is:

```python
import json


def parse_gerrit_json(text: str):
    prefix = ")]}'"
    if text.startswith(prefix):
        text = text[len(prefix):]
    return json.loads(text)
```

For Python requests, keep credentials outside source control and pass them through the process environment or an existing credential provider. Set a timeout and call `raise_for_status()` before parsing:

```python
import json
import os
from urllib.parse import quote

import requests
from requests.auth import HTTPDigestAuth

base_url = "https://git.nationalchip.com/gerrit/a"

def get_change_detail(change_id: str):
    username = os.environ["GERRIT_USERNAME"]
    password = os.environ["GERRIT_PASSWORD"]
    change_key = quote(change_id, safe="")
    response = requests.get(
        f"{base_url}/changes/{change_key}/detail",
        auth=HTTPDigestAuth(username, password),
        timeout=30,
    )
    response.raise_for_status()
    text = response.text
    if text.startswith(")]}'"):
        text = text[4:]
    return json.loads(text)
```

The Python example assumes `change_id` is provided by the caller. For the external instance, use Basic Auth and make the TLS decision explicit with `verify=True` first; use `verify=False` only for the documented legacy certificate problem and report that choice.

## Common read-only endpoints

Use `{change-id}` as a URL-encoded path segment when it contains characters such as `~` or `/`, and use the `current` revision alias when the user asks for the current patchset.

### Current account

```text
GET /accounts/self
```

### Change detail

```text
GET /changes/{change-id}/detail
```

Example:

```bash
curl --digest --netrc-file "$NETRC_FILE" --fail --silent --show-error \
  'https://git.nationalchip.com/gerrit/a/changes/127887/detail'
```

### Open or filtered changes

```bash
curl --digest --netrc-file "$NETRC_FILE" \
  --fail --silent --show-error --get \
  --data-urlencode 'q=status:open' \
  --data-urlencode 'n=20' \
  'https://git.nationalchip.com/gerrit/a/changes/'
```

For a project filter, use a separate query term rather than manually concatenating URL-escaped text:

```bash
curl --digest --netrc-file "$NETRC_FILE" \
  --fail --silent --show-error --get \
  --data-urlencode 'q=project:goxceed/loader status:open' \
  --data-urlencode 'n=20' \
  'https://git.nationalchip.com/gerrit/a/changes/'
```

### Search by commit SHA

Search candidate changes by the full 40-character local commit SHA when the caller has a local commit that may already be pushed:

```bash
curl --digest --netrc-file "$NETRC_FILE" \
  --fail --silent --show-error --get \
  --data-urlencode 'q=commit:<full-sha>' \
  --data-urlencode 'n=20' \
  'https://git.nationalchip.com/gerrit/a/changes/'
```

`commit:` matches every change whose patchset includes that exact commit. Combine it with `project:` and `branch:` query terms when the caller knows them, and paginate with `start=<offset>` until a returned page is shorter than the page size. Do not claim the candidate list is complete when pagination is not exhausted.

### Changed files

```text
GET /changes/{change-id}/revisions/current/files/
```

### Patch text

```text
GET /changes/{change-id}/revisions/current/patch
```

Fetch the patch endpoint as text and do not run the XSSI JSON parser on it. If a specific revision is requested, replace `current` with that revision identifier.

### Projects

```text
GET /projects/
```

The projects response may be large. Filter or limit it when the server version supports the requested query parameters, and do not load the entire response into the conversation unnecessarily.

## Pagination

For change lists, use `n=<page-size>` and `start=<offset>`. Start at `0`, repeat with `start += n`, and stop when the returned page is shorter than `n` or the response indicates there are no more results. Parse each page after removing the XSSI guard. Do not claim that a list is complete if pagination was not exhausted.

## Agent-host compatibility

This file intentionally uses only standard skill frontmatter and ordinary shell/Python instructions. Do not assume that another skill is invoked with a slash command, `$name` syntax, a particular `Agent` tool, or a particular subagent API. Pi Agent, Codex CLI, and OpenCode may discover the same `SKILL.md` from their own skill directories; the `agents/openai.yaml` file is optional Codex/ChatGPT metadata and is ignored by Pi and OpenCode.

## Safety and reporting

- Read-only API calls are the default. Confirm before any write, deletion, credential change, or TLS relaxation beyond the external legacy endpoint.
- Ask for the target instance when it is ambiguous; never silently switch because the change number exists on only one instance.
- Do not expose passwords, netrc contents, authorization headers, or private response fields that the user did not request.
- Report the target instance, change identifier, revision, HTTP failures, pagination limits, and whether external TLS verification was disabled.
- If authentication, DNS, or TLS fails, report the failure and the next configuration step instead of guessing credentials or retrying destructive operations.
