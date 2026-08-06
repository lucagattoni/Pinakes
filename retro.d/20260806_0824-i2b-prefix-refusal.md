## 2b — Refusing a prefix that would not fit (20260806 08:24)

**A refusal with no caller is a refusal nobody has watched fire, so this one was written to be
runnable on day one.** The manifest option that turns injection on belongs to 2d, so nothing on the
indexing path calls `assert_prefix_fits` yet. The temptation was to ship the check alone and let 2d
supply the thing that exercises it. What shipped instead is the whole prefix construction —
`metadata_prefix`, `embedding_text`, and the `unnumbered_heading_path` they read — so the refusal
measures exactly the string that will later be embedded, and every part of it is reachable from a
test today. 2d then adds one option and one call, not a mechanism.

**The additive estimate was measured rather than argued.** The check counts each distinct prefix
once, with its separator attached, and adds `chunk.token_count` rather than re-tokenising every
injected string — a document has orders of magnitude fewer heading paths than chunks. That is only
safe if the sum never *under*-counts the concatenation. The reasoning (a tokenizer that splits on
whitespace before merging cannot produce more tokens from `prefix + sep + text` than from its
parts) is sound but is the kind of reasoning that is wrong once per project, so it was run: against
`BAAI/bge-small-en-v1.5`, over **43 503 chunk/prefix pairs from 195 RFCs**, the estimate was
**exactly equal** to the concatenation's real token count every time — not merely bounding.
The same run reproduced 2a's corpus figures from an independent code path (largest prefix 68,
per-document largest median 31 / p95 51 / p99 61, longest title 32) and confirmed the refusal fires
for **195 of 195** documents at the default `max_tokens = 510` and for none at the corpus's 414.

**The reserve is checked, not the worst chunk in hand, and that was a decision.** Per-chunk pairing
is more permissive and more exact: it refuses only what would actually truncate today. It was
rejected because the two legs of an A/B comparison must chunk under the same `max_tokens` or they
are different corpora — so what has to be safe is the *setting*, not this morning's text. A
document that passes because none of its chunks happens to reach the cap would start truncating on
the next edit, mid-experiment, silently. Refusing the setting is stable across documents and across
edits to them.

**A field added to a frozen dataclass is a field somewhere else forgets to copy.** `_with_pages`
rebuilt every PDF chunk field by field to attach page numbers, so `unnumbered_heading_path` would
have arrived as `None` for PDFs only — green suite, silent gap. It now uses `dataclasses.replace`,
which cannot omit a field, and a test pins the property. The same reasoning kept the field out of
`as_row`: the stored form is the citation form, and a second column is a second thing to keep in
step with it.

**Markdown keeps whatever number its author typed, and that is the same rule rather than an
exception to it.** `## 1. Introduction` yields `1. Introduction` in both paths, because nothing
parsed a number there — `#` is syntax and is already gone, and the text after it is the author's.
Only the grammar that parsed a number is entitled to remove one. A regex over the joined string
would have been shorter, would have drifted from the grammar's own rule, and would have eaten the
`404` from `# 404 Not Found`.
