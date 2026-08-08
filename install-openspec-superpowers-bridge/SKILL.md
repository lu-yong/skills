---
name: install-openspec-superpowers-bridge
description: Install or upgrade the OpenSpec `superpowers-bridge` schema into the current project, then optionally wire AGENTS.md routing for Codex/OpenCode-compatible agents. Use when the user wants to combine OpenSpec with Superpowers in Codex, OpenCode, or another agent CLI.
disable-model-invocation: true
license: MIT
metadata:
  compatibility: "Codex, OpenCode, Claude Code-compatible skill layout"
---

# Install OpenSpec Superpowers Bridge

## Use This Skill For

- Installing `openspec-schemas/superpowers-bridge` into `openspec/schemas/`
- Upgrading an existing bridge install after showing a diff first
- Appending or refreshing an `AGENTS.md` routing section for Codex/OpenCode

## Workflow

1. Confirm the target project root. Default to the current repository root.
2. Ensure `openspec/` exists. If missing, stop and tell the user to run `openspec init` first.
3. Run `scripts/install_superpowers_bridge.sh` from this skill with one of:
   - Fresh install: `--mode install`
   - Upgrade with diff: `--mode upgrade`
4. If the user wants agent routing, append or replace the `AGENTS.md` fragment from `references/`.
5. Validate with:
   - `openspec schema validate superpowers-bridge`
   - `openspec schemas`
6. Show the final state, including whether routing was updated.

## Commands

Run from the repository root unless the user provides another target. First set `SKILL_DIR` to the absolute directory containing this loaded `SKILL.md`; do not assume the skill is installed inside the repository:

```bash
"${SKILL_DIR:?set SKILL_DIR to the directory containing this SKILL.md}/scripts/install_superpowers_bridge.sh" --mode install --project-root "$PWD"
```

Upgrade flow:

```bash
"${SKILL_DIR:?set SKILL_DIR to the directory containing this SKILL.md}/scripts/install_superpowers_bridge.sh" --mode upgrade --project-root "$PWD"
```

Useful flags:

- `--skip-routing`: do not touch `AGENTS.md`
- `--locale en|zh-CN|zh-TW`: choose the routing fragment locale
- `--source-dir /path/to/openspec-schemas`: use an already-cloned local source instead of cloning
- `--repo-url <url>`: override the upstream repo URL

## Routing Rules

For Codex/OpenCode, prefer `AGENTS.md` over `CLAUDE.md`.

- If `AGENTS.md` exists, offer to append or replace the bridge routing section.
- If only `CLAUDE.md` exists, do not rewrite it automatically unless the user asks.
- If neither file exists and the user wants routing, create `AGENTS.md` with only the fragment.

Read these files only when needed:

- English routing: `references/AGENTS.fragment.md`
- Simplified Chinese routing: `references/AGENTS.fragment.zh-CN.md`
- Traditional Chinese routing: `references/AGENTS.fragment.zh-TW.md`

## Upgrade Discipline

- For upgrades, show a diff between local and upstream schema directories before overwriting.
- Treat `openspec/schemas/superpowers-bridge/` as a full-directory replacement.
- Never overwrite `AGENTS.md` silently. Show the existing managed section and the replacement fragment first.

## Validation Notes

- If `openspec` is unavailable, still install the files and report validation was skipped.
- If the current CLI cannot confirm Superpowers plugin availability, report that separately instead of blocking schema install.
