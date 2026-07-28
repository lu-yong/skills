---
name: to-issues
description: Break a plan, specification, PRD, or Redmine requirement into independently grabbable tracer-bullet issues, review the breakdown, and publish them as related child issues in the Nationalchip Redmine instance. Use when the user wants implementation tickets, task decomposition, child issues, or executable work items created from a plan or requirement.
---

# To Issues

Break source material into thin, end-to-end implementation slices and publish the approved breakdown to Redmine.

Use the `redmine` skill for every Redmine read or write. Follow its authentication and secret-handling rules. Use native Redmine parent-child and issue relations; do not substitute GitHub labels.

## Process

### 1. Gather context

Work from the conversation and supplied plan, specification, or PRD. If the user supplies a Redmine issue number or URL, fetch its full description, journals, relations, attachments metadata, and children. Treat that issue as the default parent and its project as the default target.

Inspect the codebase when necessary to understand current architecture, domain vocabulary, ADRs, test seams, and realistic delivery boundaries.

### 2. Resolve Redmine mappings

Before publication, query Redmine rather than inventing IDs. Resolve the target project and its available trackers, statuses, priorities, versions, and relevant custom fields where the API and permissions allow it.

Use these mappings:

- Parent: the source PRD/requirement issue when one exists.
- Implementation slice: a Redmine child issue using `parent_issue_id`.
- Preferred task tracker names, in order: the project's configured task tracker, `任务`, `Task`, then `Feature`. Use the parent tracker's tracker only when project convention supports it.
- Status and priority: use explicit user/project mappings; otherwise omit them and let Redmine apply project defaults.
- Target version and category: inherit from the parent only when valid for the child project and consistent with project convention.
- Assignee and estimated hours: do not guess.
- AFK/HITL and agent readiness: map to real configured custom fields or statuses only. If no mapping exists, preserve AFK/HITL in the issue description and leave readiness unset.

If the project or tracker cannot be selected unambiguously, ask the user before publishing.

### 3. Draft tracer-bullet slices

Each issue must deliver a narrow but complete path through all applicable layers, such as schema, service, API, UI, integration, migration, observability, and tests. Do not create horizontal layer tickets unless the work is genuinely independent infrastructure with its own verifiable outcome.

Each slice must be independently grabbable and demoable or verifiable. Prefer several thin slices to a few broad ones, but avoid slices too small to produce observable value.

Classify each slice:

- **AFK**: an agent or developer can implement and merge it using recorded decisions and acceptance criteria without additional human decisions.
- **HITL**: a human decision, credential, physical action, design approval, production operation, or other interaction is required.

Use dependencies only when sequencing is real. Do not create a chain merely to impose an order.

### 4. Review the breakdown

Present a numbered list before writing to Redmine. For every slice show:

- **Title**
- **Type**: HITL or AFK
- **Blocked by**: slice numbers or none
- **User stories covered**: source story numbers when available
- **Verification**: the observable proof that the slice is complete

Ask whether granularity, dependencies, and HITL/AFK classifications are correct and whether any slices should be merged or split. Iterate until the user approves. Skip this review only when the user explicitly asks for immediate publication and the breakdown is unambiguous.

### 5. Publish in dependency order

Create blockers first so later issues can reference real Redmine IDs. For each slice:

1. Create a Redmine issue using the resolved project and tracker.
2. Set `parent_issue_id` to the source PRD/requirement issue when available.
3. Apply only resolved fields; never fabricate statuses, priorities, custom fields, users, or versions.
4. After both issues exist, create native Redmine relations for real dependencies. If slice A blocks slice B, create a `blocks` relation from A to B using Redmine's issue-relation API.
5. If relation creation is unavailable or denied, keep the dependency references in the body, report the failure, and do not claim that a native relation was created.

Do not close, rewrite, or change the status of the parent issue unless the user explicitly requests it.

Use this body template:

<issue-template>

## Parent

Reference the parent Redmine issue by ID and URL. Omit this section when no parent exists.

## Type

AFK or HITL. For HITL, state the exact human action or decision required.

## What to build

Describe the end-to-end observable behavior of this slice, not a layer-by-layer task list. Avoid file paths and ordinary code snippets. Include a small prototype-derived decision artifact only when it is more durable and precise than prose.

## Acceptance criteria

- [ ] State independently verifiable outcomes.
- [ ] Include relevant success, failure, permission, compatibility, and observability behavior.
- [ ] Include the test or demonstration evidence expected for completion.

## Blocked by

List blocking Redmine issue IDs and URLs, or `None - can start immediately`.

## User stories covered

List source user-story numbers when available. Omit when the source has no user stories.

</issue-template>

### 6. Verify and report

Fetch or inspect the created issues after publication. Verify parent IDs, trackers, statuses, and native dependency relations. Return a compact table containing each issue's ID, URL, title, type, parent, and blockers. Explicitly list any field or relation Redmine rejected or that could not be mapped.
