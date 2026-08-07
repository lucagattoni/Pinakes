- **Turning metadata injection on is now reported on indexes built before the option existed.**
  `chunking_drift` treats a key absent from the index as *unknown* rather than drifted — the rule
  that stops an upgrade demanding a rebuild of every KB. But `chunking_metadata` is absent from
  **every** index built before this release, and only a `--rebuild` ever stamps the chunking
  identity, so on a KB that already exists the flip was completely silent: no drift from
  `pnk sync`, nothing re-embedded, and `pnk doctor` printing `OK  chunking coherence: index matches
  the configured chunking` over vectors with no prefix in them. `store.ABSENT_MEANS` records that
  this one key's absence is *known* — no release that could have written such an index was able to
  inject, so absence proves `off`. It therefore fires only for someone who opted in, and never for
  a KB left on the default.
- **`pnk sync` names a document whose title changed while injection is on.** With
  `[chunking] metadata = "prefix"`, `title` is part of the text a document's vectors were built
  from, but a title edit is a sidecar-only change: the row is updated and nothing is re-embedded,
  and nothing repairs it later either, since the file's content hash is unchanged. The run now says
  so and names `pnk sync --rebuild`. Reported rather than repaired on purpose — repairing means
  re-extracting, which on a paid-extracted PDF would spend money in response to a typo fix.
- **A carried-forward document gets the same prefix fit check as any other.** The path that
  re-embeds *without* re-chunking had no truncation guard at all, and needs one most: its chunks
  were sized by whatever `max_tokens` built the previous index and are never re-chunked, so the
  current reserve does not bound them even in principle.
- **`pnk sync --rebuild` can no longer leave a document indexed with no vectors.** The copy-forward
  path must commit before it can detach the old index, and it did that *before* embedding — so a
  failure left an active document with chunks and zero embeddings that the caller's rollback could
  no longer undo, and the rebuild's unconditional index swap then published it. It now reads the
  old rows under the attach and writes everything afterwards, in one transaction.
- **`python -m pinakes.eval` refuses an index its manifest no longer describes.** Every
  `[chunking]` value in an eval artifact is read from `pinakes.toml` at eval time, so an eval over
  an index that was never rebuilt produces a plausible artifact labelled with settings that index
  was not built under — and for `metadata`, which changes no chunk text, hash or span, nothing else
  would reveal it. The index records what built it, so the disagreement is now caught before any
  question is scored.
