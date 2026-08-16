# Doc Corpus Audit

Maintenance regression for a doc corpus AI helps maintain. Run it periodically, after a large merge, and whenever a fresh-reader test failed. The disease is **drift**: each misunderstanding got an inline patch at its own site and no patch was ever merged, so the corpus's implied reader slid from the declared baseline to "the AI plus its validator".

The audit is done when every check below has run over every file in scope and produced either fixes or an explicit clean verdict, and the fresh-reader test has passed.

Sweeps cover the whole corpus, AI-facing files included — the canonical ghost-term case lived in a glossary's _Avoid_ line. Fixes split by declared reader: human-facing files you repair directly; for hits inside `CONTEXT.md` or ADR prose, load and follow the available **domain-modeling** skill to make the change — it challenges whether a term is truly dead before touching the glossary.

## Structural checks

1. **Patch scars.** The same warning or disclaimer pasted at N sites. Grep its distinctive phrase and count; merge into one owning section and turn the other sites into links.
2. **Ghost terms.** A mechanism was deleted; its vocabulary lingers — an _Avoid_ line still saying 「复用 Tombstone ID」 after the Tombstone mechanism is gone. List the terms of each mechanism removed since the last audit (the change log and ADRs are the record), grep each across the corpus.
3. **Split names.** One concept traveling under several names（八件套 / 八文件 / 仓库侧八文件文档）. Compare headings and the term table against running prose; keep the pinned name, fix every site, record the decision in the term table.
4. **Stale decisions.** An overturned ADR whose frontmatter still reads as active — a newcomer meets the dead decision first. Set `status: superseded by ADR-XXXX` on the loser and confirm the corpus's authority-precedence statement (its declaration of which file wins on conflict) covers ADRs. (This check touches only status metadata and links.)
5. **Edit wounds.** Scars of past trimming: a heading deleted with its body left attached to the previous entry, missing blank lines around blocks, a list whose order contradicts the prose beside it. These are invisible to grep — read the files git history shows most edited, linearly.

## Style checks

Re-run the writing rules of [SKILL.md](SKILL.md) as a checklist over the corpus: unanchored architectural claims, load-bearing terms without operational definitions or instances, entry points not organized by the reader's task, missing reader baselines, explanation layers written definition-first.

## Verdict

Run [FRESH-READER-TEST.md](FRESH-READER-TEST.md); fix what it surfaces and re-run until it passes. An audit without it proves the corpus consistent, not usable.
