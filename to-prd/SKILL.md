---
name: to-prd
description: Turn the current conversation and codebase context into a PRD, review it with the user, and publish it as a parent requirement issue in the Nationalchip Redmine instance. Use when the user wants to create, draft, or publish a PRD or consolidate a feature discussion into a Redmine requirement.
---

# To PRD

Create a PRD from existing context and publish the approved document to Redmine as the parent issue for subsequent implementation slices.

Use the `redmine` skill for every Redmine read or write. Follow its authentication and secret-handling rules. Do not use GitHub-style labels or assume a `ready-for-agent` label exists.

## Process

### 1. Gather context

Synthesize the conversation, referenced Redmine issues, and relevant codebase state. Do not run a broad requirements interview. Ask only when a missing decision would materially change the PRD or when a required Redmine target cannot be resolved safely.

If the user supplies a Redmine issue number or URL, fetch its full description, journals, relations, attachments metadata, and children before drafting. Use the project's domain glossary and respect relevant ADRs.

### 2. Resolve the Redmine target

Resolve the project in this order:

1. Explicit project supplied by the user.
2. Project of a referenced parent/source issue.
3. Unambiguous project configuration or repository context.
4. Ask the user if more than one plausible project remains.

Before publishing, query Redmine rather than inventing IDs. Resolve the project's available trackers, statuses, priorities, versions, and relevant custom fields where the API and current user's permissions allow it.

Use these mappings:

- PRD: one parent issue in a requirement-like tracker.
- Preferred tracker names, in order: the project's configured PRD tracker, `需求`, `Requirement`, then `Feature`.
- Status and priority: use explicit user/project mappings; otherwise omit them and let Redmine apply project defaults.
- Target version, assignee, category, watchers, and custom fields: set only when explicitly supplied or unambiguously implied.
- Agent readiness: map to a real configured Redmine status or custom field only. Never fabricate a label or field. If no mapping exists, leave it unset and mention that in the result.

If no single usable PRD tracker can be selected, ask the user before publishing.

### 3. Design testing seams

Prefer existing test seams and test at the highest stable boundary that verifies external behavior. Propose a new seam only when existing seams cannot express the required behavior.

Record the chosen seams in the draft. Ask for clarification only if the choice is consequential and cannot be inferred from existing project practice.

### 4. Draft and review

Write the PRD with the template below. Avoid implementation file paths and code snippets because they become stale. A concise prototype-derived state machine, schema, reducer, or type shape may be included when it records a decision more precisely than prose; identify it as prototype-derived.

Present the complete draft and the intended Redmine project/tracker before publishing. If the user already explicitly requested immediate publication and all targets are unambiguous, publish without a second confirmation. Otherwise, obtain approval and incorporate requested changes.

<prd-template>

## Problem Statement

Describe the problem from the user's perspective.

## Solution

Describe the intended solution and observable outcome from the user's perspective.

## User Stories

Provide a numbered, sufficiently comprehensive list using:

1. As an <actor>, I want <capability>, so that <benefit>.

Cover primary flows, edge cases, permissions, failure handling, operability, and compatibility where relevant. Prefer useful coverage over artificial length.

## Implementation Decisions

Record durable decisions, including affected modules and interfaces, architecture, schemas, API contracts, compatibility constraints, and important interactions. Do not prescribe incidental implementation details.

## Testing Decisions

Describe externally observable behaviors, the highest practical test seams, modules or boundaries to test, and relevant prior art in the codebase. Avoid tests coupled to implementation details.

## Out of Scope

State explicit exclusions.

## Further Notes

Record assumptions, unresolved risks, rollout or migration notes, and follow-up decisions.

</prd-template>

### 5. Publish to Redmine

Create one Redmine issue with:

- `project_id`: resolved project.
- `tracker_id`: resolved PRD tracker.
- `subject`: concise requirement title; do not prefix it with `PRD` unless project convention requires it.
- `description`: approved PRD body.
- Other fields: only those resolved in step 2.
- `parent_issue_id`: source/parent issue only when the user intends this PRD to be a child of that issue; otherwise omit it.

Do not overwrite or close a referenced source issue. If the user requested a draft only, do not perform a Redmine write.

After creation, return the Redmine issue ID and URL, project, tracker, status, and any requested field that could not be set. Treat the created PRD issue as the parent input for `to-issues`.
