---
name: install-openspec-tdd
description: Install or upgrade the OpenSpec `tdd-spec` schema (TDD-first workflow) into the current project and point openspec/config.yaml at it. Use when the user wants to set up a TDD-first OpenSpec workflow in a repository.
disable-model-invocation: true
license: MIT
---

# Install OpenSpec tdd-spec Schema

## Use This Skill For

- Installing `lu-yong/openspec-schemas` 的 `tdd-spec` schema 到当前仓库 `openspec/schemas/`
- 升级已安装的 schema（升级前先展示 diff）
- 把 `openspec/config.yaml` 的 `schema:` 指到 `tdd-spec`

## Workflow

1. Confirm the target project root. Default to the current repository root.
2. Ensure `openspec/` exists. If missing, stop and tell the user to run `openspec init` first.
3. Run `scripts/install_tdd_spec.sh` from this skill with one of:
   - Fresh install: `--mode install`
   - Upgrade with diff: `--mode upgrade`
4. Report the final state: the `schema:` line of `openspec/config.yaml` and, if present, its `context:` block (see Config Discipline).
5. Remind the user of the TDD discipline (see below) — it is also baked into the
   schema's tasks template and apply instruction.

## Commands

Run from the repository root unless the user provides another target. First set
`SKILL_DIR` to the absolute directory containing this loaded `SKILL.md`; do not assume
the skill is installed inside the repository:

```bash
"${SKILL_DIR:?set SKILL_DIR to the directory containing this SKILL.md}/scripts/install_tdd_spec.sh" --mode install --project-root "$PWD"
```

Upgrade flow:

```bash
"${SKILL_DIR:?set SKILL_DIR to the directory containing this SKILL.md}/scripts/install_tdd_spec.sh" --mode upgrade --project-root "$PWD"
```

Useful flags:

- `--no-set-schema`: do not touch `openspec/config.yaml`
- `--source-dir /path/to/openspec-schemas`: use an already-cloned local source instead of cloning
- `--repo-url <url>`: override the upstream repo URL (default `https://github.com/lu-yong/openspec-schemas`)

## Upgrade Discipline

- For upgrades, show a diff between the installed and upstream schema directories
  before overwriting.
- Treat `openspec/schemas/tdd-spec/` as a full-directory replacement.
- Never silently rewrite a non-default `schema:` line in `openspec/config.yaml`:
  if it points at another schema, print the current value and stop unless the user
  confirms.

## Config Discipline

- 本技能只管理 `schema:` 一行。不得添加、修改或删除 `context:`、`rules:`、`operations:`
  等任何其他字段——语言等偏好由用户自行设置，不要替用户决定。
- tdd-spec schema 默认中文正文（结构性标题 `## Why` / `## What Changes` 与 SHALL/MUST 保持英文）；
  若用户已在 `context:` 里显式指定其他语言（如 en），尊重该设置，不要「纠正」它。
- 安装完成后的报告必须展示 `openspec/config.yaml` 的 `schema:` 行与 `context:` 块，
  便于用户发现意外改动。

## TDD Discipline (tdd-spec workflow)

- apply 阶段要求先加载 `tdd` skill；确认目标环境已安装该 skill（缺失时提醒用户）。
- 一个任务 = 一个可观察行为 = 一轮 red → green → refactor（垂直切片），
  禁止「先写全部测试再写全部实现」。
- 每个 spec 场景必须被至少一个任务覆盖（行为任务或验证任务）。
- `## Why` 与 `## What Changes` 标题必须保持英文字面量（OpenSpec 解析器依赖）。

## Validation Notes

- If `openspec` is unavailable, still install the files and report validation was skipped.
- Validate with `openspec schema validate tdd-spec` and confirm with `openspec schemas`.
