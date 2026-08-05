- **`[chunking] headings = "numbered"` reads a dotted-decimal outline in plain text into
  `heading_path`.** Opt-in, `"none"` by default, and **`text` only** — `markdown` already has a
  grammar, and `code` and `pdf` are out of scope by decision rather than oversight. Until now every
  source type but `markdown` took the plain-text path and recorded no `heading_path` at all, so a
  rigidly sectioned `.txt` corpus was chunked size-based however structural the manifest read. That
  is what left a 300-RFC corpus with 106 806 chunks and not one heading path — which in turn bounds
  the graph release's gate, since `in-section`, `parent` and `child` all derive from `heading_path`
  and so derived **zero** edges on the corpus that gate was measured against.

  **It refuses rather than guesses.** `1.` at line start is also an ordered list, so acceptance is
  decided over the whole document: five line-level clauses (column 0, dotted-decimal, no
  table-of-contents dot leaders, label-shaped rather than sentence-shaped, preceded by a blank
  line) and then an outline walk over every candidate. **If the walk fails anywhere, that document
  yields no headings at all** and falls back to exactly the pre-grammar behaviour — a misread
  document loses nothing it had, where a partial labelling would invent structure that was never
  there.

  **Turning it on needs `pnk sync --rebuild`.** An incremental sync re-chunks a document only when
  *the document* changed, so a manifest-only edit reports every file `unchanged` and the key does
  nothing until a rebuild. That is true of `max_tokens` and `overlap` too and is not new, but this
  is the key most likely to be flipped deliberately — so it is written on the key in
  [MANIFEST](../docs/MANIFEST.md#chunking) and logged as its own open correction, rather than left
  to be discovered.

  It is a **new key rather than a second `[chunking] strategy` value**: `strategy` is inert, and
  giving it a second value would define `structural` retroactively for every manifest already
  written. Not stamped into the template, because `_toml.py` hard-errors on an unknown key.

  Golden set unmoved, as predicted and reported rather than assumed: `recall@k` 0.9394, MRR 0.8806,
  false-abstain 0.0152 on both `main` and this change. `tests/demo-kb` is Markdown *and* omits the
  key, so two independent reasons say it cannot move — movement would itself have been the finding.
