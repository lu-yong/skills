---
name: install-openspec-aosp-repo
description: Install or upgrade the OpenSpec `aosp-repo` schema into the current project and point openspec/config.yaml at it. Use when the user wants to set up an AOSP implementation workspace in an owning repository.
disable-model-invocation: true
license: MIT
---

# Install OpenSpec aosp-repo Schema

## Use This Skill For

- Installing `lu-yong/openspec-schemas` 的 `aosp-repo` schema 到当前仓库 `openspec/schemas/`
- 升级已安装的 schema（升级前先展示 diff）
- 把 `openspec/config.yaml` 的 `schema:` 指到 `aosp-repo`

## Workflow

1. Confirm the target project root. Default to the current repository root.
2. Ensure `openspec/` exists. If missing, stop and tell the user to run `openspec init` first.
3. Run `scripts/install_aosp_repo.sh` from this skill with one of:
   - Fresh install: `--mode install`
   - Upgrade with diff: `--mode upgrade`
4. Report the final state, including the `schema:` line of `openspec/config.yaml`.
5. Remind the user of the completion discipline (see below) — it is also baked into the
   schema's tasks template.

## Commands

Run from the repository root unless the user provides another target. First set
`SKILL_DIR` to the absolute directory containing this loaded `SKILL.md`; do not assume
the skill is installed inside the repository:

```bash
"${SKILL_DIR:?set SKILL_DIR to the directory containing this SKILL.md}/scripts/install_aosp_repo.sh" --mode install --project-root "$PWD"
```

Upgrade flow:

```bash
"${SKILL_DIR:?set SKILL_DIR to the directory containing this SKILL.md}/scripts/install_aosp_repo.sh" --mode upgrade --project-root "$PWD"
```

Useful flags:

- `--no-set-schema`: do not touch `openspec/config.yaml`
- `--source-dir /path/to/openspec-schemas`: use an already-cloned local source instead of cloning
- `--repo-url <url>`: override the upstream repo URL (default `https://github.com/lu-yong/openspec-schemas`)

## Upgrade Discipline

- For upgrades, show a diff between the installed and upstream schema directories
  before overwriting.
- Treat `openspec/schemas/aosp-repo/` as a full-directory replacement.
- Never silently rewrite a non-default `schema:` line in `openspec/config.yaml`:
  if it points at another schema, print the current value and stop unless the user
  confirms.

## Completion Discipline (aosp-repo workflow)

- 完成动作：先把 Delta 合入本仓库 `docs/` 八文件，再
  `openspec archive <change-id> --skip-specs` 冻结工作区。
- `openspec/specs/` 保持为空；八文件是唯一权威。
- 需求正文规范性句式用 SHALL（中文叙述、英文关键词）。

## Validation Notes

- If `openspec` is unavailable, still install the files and report validation was skipped.
- Validate with `openspec schema validate aosp-repo` and confirm with `openspec schemas`.
