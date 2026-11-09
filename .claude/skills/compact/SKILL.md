---
name: compact
description: Compact docs/TODO.md by archiving completed items to docs/TODO-archive.md. Use at session end or when TODO.md grows past ~350 lines to keep context lean.
---

Archive completed items from `docs/TODO.md` to `docs/TODO-archive.md`, replacing them with one-line summaries. This keeps the context window lean since TODO.md is loaded every prompt.

## Pre-check

Before making any changes, report stats and get user confirmation:

```bash
wc -l docs/TODO.md
grep -c '\[x\]' docs/TODO.md
grep -c '\[ \]' docs/TODO.md
grep -c '~~.*~~.*✅' docs/TODO.md
```

Report: total lines, `[x]` count, `[ ]` count, strikethrough count, completed ratio, and recommendation.

- If total lines < 300 AND completed ratio < 50%, say **"No compaction needed"** and stop.
- Otherwise, present what will be archived and wait for user confirmation.

## Compaction Rules

### Rule 1: Fully-completed subsections
If a subsection header has ✅ and all items under it are `[x]`, archive the entire subsection (header + items).
Replace with: `**<range> complete** (<N> items archived) — <brief summary>`

### Rule 2: The `## Completed` section
Move all items from `## Completed` to the archive file.
Replace with: `_<N> items archived to docs/TODO-archive.md (<date>). Sections: <section list>._`

### Rule 3: Contiguous `[x]` blocks in mixed subsections
If a subsection starts with a contiguous block of `[x]` items followed by `[ ]` items, archive the `[x]` block.
Replace with: `_<N> items complete (<summary>) — see archive_`
**Keep** `[x]` items that are interleaved with `[ ]` items — they provide context for pending work.

### Rule 4: Execution Order strikethrough
Replace consecutive `~~strikethrough~~ ✅` lines with a single summary: `<range>. _(summary)_`

### Rule 5: Nested `[x]` under pending parents
`[x]` items nested under a `[ ]` parent item **stay in place** — they show sub-task progress within active work.

## Archive Format

Append to `docs/TODO-archive.md` (create if it does not exist).

**File header** (only when creating new):
```markdown
# Robot Buddy — TODO Archive

Completed items moved from `docs/TODO.md` during periodic compaction.
This file is not loaded into Claude Code context. See `docs/TODO.md` for active work.
```

**Each batch**:
```markdown
---

## Archived <YYYY-MM-DD>

### <Original Section Header>
<archived items verbatim>
```

Items are preserved verbatim — no lossy summarization in the archive.

## Post-check

After compaction:
1. Count `[ ]` items in TODO.md — must match the pre-check count exactly.
2. Report: lines removed, new total, items archived, archive file location.
3. If `[ ]` count changed, **revert immediately** — something went wrong.

## Rules

1. **NEVER remove `[ ]` (pending) items** — only `[x]` and strikethrough items are archived.
2. **NEVER modify** the "How to Use This File", "Future Development & R&D", "Model Assignment Guide", or "Efficiency Notes" sections.
3. Always preserve section headers and structural separators (`---`).
4. Always ask for confirmation before proceeding.
5. The archive is **append-only** — never modify previously archived batches.
6. Include the date in each archive batch header.
