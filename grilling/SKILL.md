---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases.
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the frontier in rounds of **at most four questions**, ranked by how many downstream decisions they unlock; the rest of a larger frontier waits for the next round. Then wait for the user's answers before the next round.

## Asking a round

This is a conversation skill: its answers steer the conversation and authorize nothing, so when the host provides a structured question tool (pi's `ask_user_question`), ask every round through it, and degrade to plain text when it is unavailable or fails.

**Through the tool, one round = one call:**

- At most one markdown sentence before the call, recapping what the previous round settled; the questions themselves live only in the call.
- Keep each question body to a few sentences; put the background and trade-offs into the option `description`s. A question that will not fit is several questions: split it.
- Recommended answer: the first option, its label suffixed `(Recommended)`.
- An open question with no natural candidates gets your hypotheses as the options — the options are hypotheses, not a menu, so expect the real answer through the free-form row and treat a typed answer as first-class.
- Use multi-select when several answers can hold at once.
- A cancelled questionnaire is a pause signal, never answers: drop to plain chat and ask what is wrong (too many questions? wrong direction? missing context?), then resume rounds. Two consecutive cancellations: offer to close the session and summarize the state of the tree.
- Treat a clicked answer as a seed, not a conclusion: when the branch it settles is expensive to reverse, keep drilling into it in later rounds.

**When the tool is missing from the tool list, or a call returns an error** (`no_ui`, `no_custom_ui`, `details.error`), ask that round in plain text instead, numbering each question and stating your recommended answer:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it; don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.
