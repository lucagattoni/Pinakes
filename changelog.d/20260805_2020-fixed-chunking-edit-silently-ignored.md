- **A `[chunking]` edit is no longer a silent no-op.** An incremental `pnk sync` re-chunks a
  document only when *the document* changed, so editing `headings`, `max_tokens` or `overlap` left
  every content hash intact, reported `unchanged`, and applied nothing — with no warning, and a
  `pnk doctor` that then reported exactly the condition the user had just tried to fix. Measured:
  `headings = "numbered"` added to a synced KB, plain `pnk sync` → `1 unchanged` and every
  `heading_path` still empty.

  The index now records which `[chunking]` settings it was built under. `pnk sync` names the key
  that moved and points at `--rebuild`; [`pnk doctor`](../docs/CLI.md#pnk-doctor) reports the same
  as `chunking coherence`. **The warning persists until the rebuild actually happens** — the first
  draft wrote the new identity at the end of every sync, so it fired once and the index then
  claimed a coherence it did not have.

  **Upgrading demands nothing.** An index built before this carries no recorded identity, and
  absence reads as *unknown*, never as *different* — a check that fired on every existing KB would
  be an unclearable warning about a setting that probably never changed. `max_tokens` and `overlap`
  have behaved this way since v0.1; `headings` is only what made it reachable, being the first
  `[chunking]` key worth flipping on an already-indexed KB.
