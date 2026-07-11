<!-- Source: install-openspec-superpowers-bridge/references/AGENTS.fragment.md -->
<!-- BEGIN OPENSPEC SUPERPOWERS BRIDGE -->
## Workflow routing

This repo uses [`superpowers-bridge`](https://github.com/JiangWay/openspec-schemas/tree/main/superpowers-bridge) to bridge OpenSpec and Superpowers. Follow the bridge README for artifact rules and use this section only for agent routing.

### Entry routing

- Narrative design or brainstorming request: discuss first, but do not write to `docs/superpowers/specs/`. Once scope, decisions, dependencies, acceptance criteria, and convergence are clear, suggest `/opsx:propose`.
- Direct `/opsx:new`, `/opsx:ff`, or `/opsx:propose`: follow the schema flow.
- Explicit bug fix, typo, small config tweak, docs-only change: use a direct PR, not a change.
- Existing change in progress: continue with `/opsx:continue`, `/opsx:apply`, `/opsx:verify`, or `/opsx:archive`.

### Skip opsx

- Use opsx for new features, architectural changes, and breaking changes.
- Skip opsx for bug fixes without contract changes, test backfills, lint tweaks, non-breaking upgrades, typos, docs, and minor config value changes.

### Promotion gate

Promote a verbal brainstorm to opsx only after all five are true:

1. Scope is locked.
2. Major design forks are resolved.
3. Cross-system dependencies are mapped.
4. Acceptance criteria are concrete.
5. The conversation is converging.

### Anti-patterns

- Writing brainstorming output to `docs/superpowers/specs/`
- Writing plans to `docs/superpowers/plans/`
- Opening a change before blocking TBDs are resolved
- Opening a change for a low-risk fix
<!-- END OPENSPEC SUPERPOWERS BRIDGE -->
