# HTML Report Format

The architectural review is rendered as a single self-contained HTML file in the OS temp directory. Tailwind and Mermaid both come from CDNs. Mermaid handles graph-shaped diagrams reliably; hand-built divs and inline SVG handle the more editorial visuals (mass diagrams, cross-sections). Mix the two — don't lean on Mermaid for everything, it'll start to look generic.

## Written language

Every word the reader reads is Simplified Chinese (简体中文) — page title, headings, legend, badges, diagram labels, prose, bullets.

Identifiers are not words the reader reads; they are what the code is called. File paths, filenames, module and package names, class/function/variable names, CLI commands, code snippets, config keys, ADR ids, and `CONTEXT.md` domain terms all keep their exact spelling, dropped into the Chinese sentence as-is: 「`guards.ts` 收窄成一份 profile」.

### 术语对照表

The architecture vocabulary comes from the **codebase-design** skill. Each term has exactly one Chinese rendering — treat the Chinese as strictly as the skill treats the English, and never reach for a synonym.

| codebase-design | 报告用词 | 不要写成 |
| --- | --- | --- |
| module | 模块 | 组件、服务、单元 |
| interface | 接口 | API、签名 |
| implementation | 实现 | 内部代码 |
| depth / deep / shallow | 深度 / 深模块 / 浅模块 | 厚、薄 |
| seam | 接缝 | 边界、缝合点、分界 |
| adapter | 适配器 | 包装器、代理 |
| leverage | 杠杆 | 复用、收益 |
| locality | 局部性 | 内聚、集中度 |
| deepening | 深化 | 重构、优化 |
| deletion test | 删除测试 | — |
| leak / leakage | 泄漏 | 越界、耦合 |

Badges and tags render as:

| English | 报告用词 |
| --- | --- |
| `Strong` | `强烈推荐` (emerald) |
| `Worth exploring` | `值得一试` (amber) |
| `Speculative` | `试探性` (slate) |
| `in-process` | `进程内` |
| `local-substitutable` | `本地可替换` |
| `ports & adapters` | `端口与适配器` |
| `mock` | `外部 mock`（mock 在中文技术语境里本就通用，不译） |

**First occurrence annotates the English**: the first time a term appears in the report, write it as `接缝 (seam)`; every later occurrence is Chinese alone. The legend annotates every entry regardless — it's the reader's bridge back to the **codebase-design** glossary.

## Scaffold

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>架构评审 — {{repo name}}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({
        startOnLoad: true,
        theme: "neutral",
        securityLevel: "loose",
        /* without this, Mermaid's own default stack renders CJK labels
           in a different face than the surrounding page */
        fontFamily: "var(--font-report)",
      });
    </script>
    <style>
      /* Latin faces first so identifiers keep their shape, CJK faces after so
         Chinese prose lands on PingFang / 苹方 rather than a fallback */
      :root {
        --font-report: ui-sans-serif, system-ui, -apple-system, "Segoe UI",
          "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC",
          sans-serif;
      }
      /* set here, not via Tailwind's font-sans utility — the utility would win
         on specificity and drop the CJK faces */
      body { font-family: var(--font-report); }
      /* small custom layer for things Tailwind doesn't cover cleanly:
         dashed seam lines, hand-drawn-feeling arrow heads, etc. */
      .seam { stroke-dasharray: 4 4; }
      .leak { stroke: #dc2626; }
      .deep { background: linear-gradient(135deg, #0f172a, #1e293b); }
    </style>
  </head>
  <body class="bg-stone-50 text-slate-900">
    <main class="max-w-5xl mx-auto px-6 py-12 space-y-12">
      <header>...</header>
      <section id="candidates" class="space-y-10">...</section>
      <section id="top-recommendation">...</section>
    </main>
  </body>
</html>
```

## Header

Repo name, date, and a compact legend — the legend is where the term table earns its keep, so annotate every entry: `实线框 = 模块 (module)`、`虚线 = 接缝 (seam)`、`红色箭头 = 泄漏 (leak)`、`粗深色框 = 深模块 (deep module)`. No introduction paragraph — straight into the candidates.

## Candidate card

The diagrams carry the weight. Prose is sparse, plain, and uses the pinned Chinese glossary terms (from the 术语对照表 above) without ceremony.

Each candidate is one `<article>`. Bracketed strings are what gets rendered:

- **Title** — short, names the deepening (e.g. 「收拢 Order intake 流水线」). Domain and code names stay as they are; the verb and the noun around them are Chinese.
- **Badge row** — recommendation strength (`强烈推荐` = emerald, `值得一试` = amber, `试探性` = slate), plus a tag for the dependency category (`进程内`、`本地可替换`、`端口与适配器`、`外部 mock`).
- **Files** [`涉及文件`] — monospaced list, `font-mono text-sm`. Paths and line ranges verbatim, never translated, never abbreviated to Chinese.
- **Before / After diagram** [`现状` / `深化后`] — the centrepiece. Two columns, side by side. See patterns below.
- **Problem** [`问题`] — one sentence. What hurts.
- **Solution** [`方案`] — one sentence. What changes.
- **Wins** [`收益`] — bullets, ≤12 个汉字 each. e.g. 「测试只打一个接口」「定价逻辑不再泄漏」「删掉 4 个浅包装」.
- **ADR callout** (if applicable) — one line in an amber-tinted box. The id stays `ADR-0007`; the sentence around it is Chinese.

No paragraphs of explanation. If the diagram needs a paragraph to be understood, redraw the diagram.

## Diagram patterns

Pick the pattern that fits the candidate. Mix them. Don't make every diagram look the same — variety is part of the point. Whichever pattern you pick, the two columns are always headed `现状` and `深化后`; "before"/"after" below is how the pattern is described here, not a string to render.

### Mermaid graph (the workhorse for dependencies / call flow)

Use a Mermaid `flowchart` or `graph` when the point is "X calls Y calls Z, and look at the mess." Wrap it in a Tailwind-styled card so it doesn't feel parachuted in. Style with classDef to colour leakage edges red and the deep module dark. Sequence diagrams work well for 「现状：6 次往返；深化后：1 次」.

Node labels are code names, so they stay English; edge labels are prose, so they're Chinese; `classDef` names are identifiers in the diagram source and never show up on screen, so leave them alone:

```html
<div class="rounded-lg border border-slate-200 bg-white p-4">
  <pre class="mermaid">
    flowchart LR
      A[OrderHandler] --> B[OrderValidator]
      B --> C[OrderRepo]
      C -.泄漏.-> D[PricingClient]
      classDef leak stroke:#dc2626,stroke-width:2px;
      class C,D leak
  </pre>
</div>
```

### Hand-built boxes-and-arrows (when Mermaid's layout fights you)

Modules as `<div>`s with borders and labels. Arrows as inline SVG `<line>` or `<path>` elements positioned absolutely over a relative container. Reach for this when you want the "after" diagram to feel like one thick-bordered deep module with greyed-out internals — Mermaid won't render that with the right weight.

### Cross-section (good for layered shallowness)

Stack horizontal bands (`h-12 border-l-4`) to show layers a call passes through. Before: 6 thin layers each doing nothing. After: 1 thick band labelled with the consolidated responsibility.

### Mass diagram (good for "interface as wide as implementation")

Two rectangles per module — one for interface surface area, one for implementation. Before: interface rectangle is nearly as tall as the implementation rectangle (shallow). After: interface rectangle is short, implementation rectangle is tall (deep).

### Call-graph collapse

Before: a tree of function calls rendered as nested boxes. After: the same tree collapsed into one box, with the now-internal calls shown faded inside it.

## Style guidance

- Lean editorial, not corporate-dashboard. Generous whitespace. Skip `font-serif` on Chinese headings — the CJK fallback is 宋体 and reads dated in a stone/slate report; get hierarchy from weight and size instead. Keep `font-serif` for headings that are entirely Latin.
- Colour sparingly: one accent (emerald or indigo) plus red for leakage and amber for warnings.
- Give Chinese prose blocks `leading-relaxed` — CJK needs more leading than Tailwind's default line-height.
- Keep diagrams ~320px tall so before/after sits comfortably side by side without scrolling. Keep the `接缝 (seam)` style annotation out of diagram labels — annotate in the legend or in prose, where the extra width doesn't push a box off the grid.
- Use `text-xs tracking-wider` for module labels inside diagrams — they should read as schematic, not as UI. Add `uppercase` only when the label is entirely a Latin identifier; on Chinese it does nothing.
- The only scripts are the Tailwind CDN and the Mermaid ESM import. The report is otherwise static — no app code, no interactivity beyond Mermaid's own rendering.

## Top recommendation section

One larger card, headed `首选建议`. Candidate name, one sentence on why, anchor link to its card. That's it.

## Tone

Plain Chinese, concise — but the architectural nouns and verbs come straight from the **codebase-design** skill, through the 术语对照表 above. Concision is not an excuse to drift.

**Use exactly:** 模块、接口、实现、深度、深模块、浅模块、接缝、适配器、杠杆、局部性.

**Never substitute:** 组件、服务、单元（for 模块）· API、签名（for 接口）· 边界、缝合点（for 接缝）· 层、包装器（for 模块, when you mean 模块）.

**Phrasings that fit the style:**

- 「Order intake 模块是浅的 —— 接口几乎和实现一样复杂。」
- 「定价逻辑跨接缝泄漏。」
- 「深化：一个接口，一处可测。」
- 「两个适配器撑得起这条接缝：生产用 HTTP，测试用内存实现。」

**Wins bullets** name the gain in glossary terms: *「局部性：bug 集中在一个模块」*、*「杠杆：一个接口，N 个调用点」*、*「接口收窄，实现吸收包装层」*. Don't write *「更易维护」* or *「代码更干净」* — those aren't in the glossary and don't earn their place.

**Write Chinese, not translated English.** No 翻译腔 — no 「被……所」, no 「进行一次……的操作」, no stacked 「的」. Chinese punctuation (，。、「」) in Chinese sentences; punctuation inside code, paths, and commands stays exactly as the code writes it. Put a space between a Chinese run and an adjacent Latin/number run (「`guards.ts` 收窄成 1 份 profile」), and keep that consistent across the whole report.

No hedging, no throat-clearing, no 「值得一提的是……」. If a sentence could be a bullet, make it a bullet. If a bullet could be cut, cut it. If a term isn't in the **codebase-design** glossary, reach for one that is before inventing a new one — and if it is in the glossary, use the pinned Chinese word, not a fresh translation.
