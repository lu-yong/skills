---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Work test-first where possible, at pre-agreed seams — load and follow the available **tdd** skill if this host has one.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, review the work — load and follow the available **code-review** skill if this host has one.

Load any named skill through the host's native skill-loading mechanism; do not assume a slash command, `$name` syntax, or a particular Agent API. If a named skill is unavailable here, tell the user which one is missing.

Commit your work to the current branch.
