- **Retrieval results no longer depend on how the index was built.** Every tiebreak in the pipeline
  ultimately resolved to `chunks.id` — the rowid, which the schema says has no identity across
  rebuilds — so two indexes over byte-identical sources could return different documents for the
  same query. Measured on the golden set: one question in 41 answered differently after an
  incremental sync than after a `--rebuild`. Ordering is now total on
  `(documents.path, chunks.ordinal)` at the vector array, the BM25 cut and hydration, and the vector
  sort is stable, which additionally stops a newly added document reordering tied results elsewhere
  in the corpus. **No measured number moved**: the demo KB scores byte-identically to its committed
  baseline before and after, which is what a change that only breaks ties should do.

- **A `check.sh` gate and two CI jobs hold it there** — `tools/eval_reproducibility_gate.py` sweeps
  four kinds of corpus change (a document edited, added, removed, renamed) offline in about a
  second, and CI diffs per-question outcomes between `ubuntu-latest` and `macos-latest`, which is
  the half of the question one machine cannot answer.

- Making the BM25 cut a total order costs a join: **+11.5 ms** (23.9 → 35.4) on a synthetic
  50k-chunk corpus where every chunk matches every query term, which is the worst case rather than a
  typical one. `load_vectors`' new ordering costs nothing measurable — both query plans already
  sorted through a temp B-tree.
