---
name: code-review
description: Review a branch, PR, fixed point, or working tree independently for spec conformance, standards and design, and security and reliability.
---

# Code Review

## 1. Establish scope

- **Branch, PR, or fixed point**. Resolve the base with `git rev-parse --verify '<base>^{commit}'`. Stop and report an invalid base before delegating. Read `git diff <base>...HEAD` and `git log <base>..HEAD --oneline`. Enumerate staged, unstaged, and untracked changes separately. Review all three when requested, and state their scope in the report.
- **Current working tree**. Read `git status -sb`, `git diff HEAD --stat`, and `git diff HEAD`. List untracked files with `git ls-files --others --exclude-standard` and read those in scope. If there are no changes, report the empty scope and ask for a ref or range.
- For a large diff, group files by feature and identify entry points, writes, authentication, and other critical paths. Identify generated files, vendored code, migrations, and lockfiles. Inspect generated output when it affects behavior or the user requests it.

## 2. Gather evidence

Find requirements in linked issues or PRs, user-supplied paths or URLs, repository specs and plans, or concrete user requests and commit messages. Report inaccessible sources and use any remaining spec. If no usable spec exists, mark the Spec axis **No spec available**.

Read applicable `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, coding standards, and relevant package documentation. Check local test, migration, API, and security conventions. Apply documented repository rules first.

## 3. Review independently

Give each reviewer the same scope, commits, relevant context, and finding format. Run three independent reviewers in parallel when available. Otherwise, make three separate passes.

| Axis | What to check |
| --- | --- |
| Spec | Missing, partial, or incorrect behavior, scope changes, and compatibility with the stated API or data contract. Quote the requirement for each finding. |
| Standards / Design | Repository conventions and concrete design or maintenance consequences. Check callers and ownership before proposing a small, local change. |
| Security / Reliability | Data and credential handling, access control, input handling, concurrency, failure and retry paths, resource limits, and boundary cases. Trace the trigger to its impact. |

This is a review-only workflow. Apply fixes when the user authorizes implementation. If proposing removal, check static and dynamic consumers, tests, configuration, docs, and available telemetry. Indicate whether removal can happen now or needs migration and rollback.

## 4. Verify and report

Re-read surrounding code, check callers and tests, and run focused non-destructive checks when practical. Tie each finding to evidence and explain what was reproduced and what follows from the code. Check that the proposed fix respects the spec and repository rules.

Use the following order for each finding.

1. Severity and confidence
2. File and line
3. Evidence, impact, and trigger
4. Smallest suggested fix and how to verify it

**P0** covers critical security, data loss, or release-blocking failures. **P1** covers reproducible contract or serious reliability failures. **P2** covers moderate reliability or maintainability problems. **P3** covers minor improvements. Set confidence to High, Medium, or Low based on available evidence.

Start with the reviewed scope, file and line counts, checks actually run, and **APPROVE**, **REQUEST_CHANGES**, or **COMMENT**. Group findings by axis and severity, state the outcome for empty axes, and report residual risks and coverage gaps. End with finding counts and offer the user the choice to fix all, fix high-severity or selected findings, or close the review.
