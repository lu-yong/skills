---
name: improve-codebase-architecture
description: Scan a codebase for deepening opportunities, present them as a visual HTML report, then grill through whichever one you pick.
disable-model-invocation: true
---

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

This command is _informed_ by the project's domain model and built on a shared design vocabulary:

- Load and follow the available **codebase-design** skill for the architecture vocabulary (**module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**) and its principles (the deletion test, "the interface is the test surface", "one adapter = hypothetical seam, two = real"). Use these terms exactly in every suggestion — don't drift into "component," "service," "API," or "boundary."
- The domain language in `CONTEXT.md` gives names to good seams; ADRs in `docs/adr/` record decisions this command should not re-litigate.

Every skill named in this file is loaded through the host's native skill-loading mechanism; do not assume a slash command, `$name` syntax, or a particular Agent API. If a named skill is unavailable here, tell the user which one is missing.

## Report language

The HTML report is written for a Chinese-reading audience. Every piece of prose in it — page title, headings, legend, badges, diagram labels, problem, solution, wins, top recommendation — is Simplified Chinese (简体中文).

What stays in English, spelled exactly as the code spells it: file paths, filenames, module and package names, class/function/variable names, CLI commands, code snippets, config keys, ADR ids, and the domain terms `CONTEXT.md` shares with the codebase. Translating an identifier breaks the link between the report and the code — that link is the whole point of naming files and modules in a review.

The architecture vocabulary is translated on a fixed table — see the term table in [HTML-REPORT.md](HTML-REPORT.md). The pinned Chinese word is as strict as the English one: 接缝 is the only word for **seam**, never 边界 or 缝合点. First occurrence in the report annotates the English in parentheses — `接缝 (seam)` — and every later use is Chinese alone.

This rule governs the report only. The grilling loop in step 3 is a conversation, so it follows whatever language the user is speaking. `CONTEXT.md` and ADR edits follow the **domain-modeling** skill's own language rule instead.

## Process

### 1. Explore

**Scope before you scan — YAGNI.** Deepening a module pays off by making future changes to it easier, so put extra weight on the parts of the codebase that have recently changed. Decide *where* to look before you look:

- If the user named a direction — a module, a subsystem, a pain point — take it, and skip the inference below.
- Otherwise, walk back a good stretch of the commit history (`git log --oneline`) to find the codebase's hot spots — the files and areas that keep coming up — and let those paths pull your attention first. If the changes are scattered with no clear hot spot, widen the net.

Read the project's domain glossary (`CONTEXT.md`) and any ADRs in the area you're touching first.

Then walk the codebase. Delegate the walk to isolated exploration sub-agents when the host supports them; otherwise explore inline in this session. Either way, don't follow rigid heuristics — explore organically and note where you experience friction:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity, or just move it? A "yes, concentrates" is the signal you want.

### 2. Present candidates as an HTML report

Write a self-contained HTML file to the OS temp directory so nothing lands in the repo. Resolve the temp dir from `$TMPDIR`, falling back to `/tmp` (or `%TEMP%` on Windows), and write to `<tmpdir>/architecture-review-<timestamp>.html` so each run gets a fresh file. Open it for the user — `xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on Windows — and tell them the absolute path.

The report uses **Tailwind via CDN** for layout and styling, and **Mermaid via CDN** for diagrams where a graph/flow/sequence reliably communicates the structure. Mix Mermaid with hand-crafted CSS/SVG visuals — use Mermaid when relationships are graph-shaped (call graphs, dependencies, sequences), and hand-built divs/SVG when you want something more editorial (mass diagrams, cross-sections, collapse animations). Each candidate gets a **before/after visualisation**. Be visual.

For each candidate, render a card with (Chinese heading in brackets — render that string, not the English):

- **Files** [`涉及文件`] — which files/modules are involved
- **Problem** [`问题`] — why the current architecture is causing friction
- **Solution** [`方案`] — one plain sentence on what would change
- **Benefits** [`收益`] — explained in terms of 局部性 (locality) and 杠杆 (leverage), and how tests would improve
- **Before / After diagram** [`现状` / `深化后`] — side-by-side, custom-drawn, illustrating the shallowness and the deepening
- **Recommendation strength** — one of `强烈推荐`, `值得一试`, `试探性`, rendered as a badge

End the report with a **Top recommendation** section headed `首选建议`: which candidate you'd tackle first and why.

**Use CONTEXT.md vocabulary for the domain, and the codebase-design vocabulary for the architecture.** Domain terms keep the spelling `CONTEXT.md` gives them, dropped straight into the Chinese sentence: if `CONTEXT.md` defines "Order," write 「Order intake 模块」— not 「FooBarHandler」, and not 「Order 服务」.

**ADR conflicts**: if a candidate contradicts an existing ADR, only surface it when the friction is real enough to warrant revisiting the ADR. Mark it clearly in the card (e.g. a warning callout: _「与 ADR-0007 冲突 —— 但值得重开，因为……」_). Don't list every theoretical refactor an ADR forbids.

See [HTML-REPORT.md](HTML-REPORT.md) for the full HTML scaffold, diagram patterns, and styling guidance.

Do NOT propose interfaces yet. After the file is written, ask the user which candidate they'd like to explore — that question is conversation, so ask it in the language the user is speaking.

### 3. Grilling loop

Once the user picks a candidate, load and follow the available **grilling** skill to walk the decision tree with them — constraints, dependencies, the shape of the deepened module, what sits behind the seam, what tests survive.

Side effects happen inline as decisions crystallize — load and follow the available **domain-modeling** skill to keep the domain model current as you go:

- **Naming a deepened module after a concept not in `CONTEXT.md`?** Add the term to `CONTEXT.md`. Create the file lazily if it doesn't exist.
- **Sharpening a fuzzy term during the conversation?** Update `CONTEXT.md` right there.
- **User rejects the candidate with a load-bearing reason?** Offer an ADR, framed as: _"Want me to record this as an ADR so future architecture reviews don't re-suggest it?"_ Only offer when the reason would actually be needed by a future explorer to avoid re-suggesting the same thing — skip ephemeral reasons ("not worth it right now") and self-evident ones.
- **Want to explore alternative interfaces for the deepened module?** Load and follow the available **codebase-design** skill and use its design-it-twice pattern.
