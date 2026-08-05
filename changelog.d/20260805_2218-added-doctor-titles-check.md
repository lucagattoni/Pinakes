- **`pnk doctor` reports how many documents still carry the title `sync` minted from their
  filename.** The RFC realism corpus indexed 300 sidecars titled `rfc9110` rather than *"HTTP
  Semantics"*, which made search results unreadable — and nothing said so.

  **It is always OK, never a warning.** A filename-derived title is a legitimate state: the
  fallback was kept deliberately, so warning would fire on every KB whose titles nobody has curated
  yet — most of them, and both committed corpora at 100%. An un-actionable warning that fires
  forever is how doctor output stops being read at all. This is a nudge with a count and a sample.

  **Detection, never guessing.** Inferring a title from the document's first line is rejected: an
  RFC's first line is `Internet Engineering Task Force (IETF)`, so inference would mint confidently
  wrong titles at scale into sidecars the user then commits — and a plausible wrong title is far
  harder to notice than one that is visibly a filename. `title` stays the user's field.

  The check and the minter now share one `minted_title()` rather than each carrying a copy of the
  rule, because a second copy would go quietly wrong — in the direction of reporting nothing — the
  day either changed.
