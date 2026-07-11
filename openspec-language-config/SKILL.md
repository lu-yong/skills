---
name: openspec-language-config
description: Configure OpenSpec to generate proposals, specs, tasks, and other artifacts in a requested natural language by editing openspec/config.yaml context. Use when Codex needs to set, change, verify, or explain OpenSpec multi-language/language-localization settings, including Simplified Chinese, Japanese, Spanish, Portuguese, French, German, or custom terminology rules.
---

# OpenSpec Language Config

## Workflow

1. Locate the project OpenSpec config, normally `openspec/config.yaml`.
2. Preserve existing `schema` and project context. Add or update language instructions inside the YAML `context: |` block.
3. Put language instructions near the top of `context` so they apply to all generated artifacts.
4. Keep code identifiers, file paths, command names, package names, API names, and protocol names in English unless the user explicitly requests translation.
5. Verify with `openspec instructions proposal --change <change-id>` when a change id is available. Confirm the output includes the language context.

## Config Pattern

Use this structure when creating or updating `openspec/config.yaml`:

```yaml
schema: spec-driven

context: |
  Language: <language name and locale when useful>
  All artifacts must be written in <target language>.

  # Existing project context below...
  Tech stack: <existing stack>
```

If the file already has a `context: |` block, edit that block instead of adding a second one. If `context` exists in another YAML style, convert only when needed and keep the existing meaning.

## Language Instructions

For common templates and terminology guidance, read `references/language-templates.md`.

Use the user's requested language verbatim when possible. For Chinese requests, prefer Simplified Chinese only when the user says Chinese, Simplified Chinese, 简体中文, or the surrounding project uses Simplified Chinese.

## Verification

Run this when the project has an OpenSpec change id:

```bash
openspec instructions proposal --change <change-id>
```

Check that the generated instructions include the configured language context. If no change id exists, inspect `openspec/config.yaml` directly and tell the user verification is limited to config review.

## Edit Discipline

- Keep edits scoped to OpenSpec configuration unless the user asks for broader localization.
- Do not translate source code, identifiers, package names, file paths, or existing spec content unless requested.
- When combining language settings with project context, keep both in the same `context: |` block.
- If YAML parsing or formatting tools are available in the repo, prefer them for non-trivial config edits.
