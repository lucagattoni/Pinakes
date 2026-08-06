- **`tools/build_rfc_corpus.py` curates real titles and reserves room for an injected prefix.**
  Each document's sidecar is now minted by the builder *before the first sync*, carrying the title
  published at `https://www.rfc-editor.org/rfc/rfc<N>.json` — without it every `.txt` RFC falls
  back to its filename stem, so the corpus was titled `rfc9110` throughout. A document whose
  metadata carries no title keeps the stem and is named, in the run's output and in `corpus.json`.
  The generated manifest stamps `[chunking] max_tokens = 414` rather than the default 510, leaving
  96 tokens for the `title > heading_path` prefix the injection experiment prepends to the embedded
  and indexed text; the default leaves zero headroom against the model's 512-token window, so the
  prefix would have been truncated away silently. An existing `pinakes.toml` is no longer
  overwritten by a re-run — it holds the KB's permanent id and, once calibrated, its fitted
  confidence thresholds.
