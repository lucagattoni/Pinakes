- **Per-question evaluation outcomes are a committed artifact.** `python -m pinakes.eval <kb>
  --write-baseline` now writes `eval/outcomes.json` beside `eval/baseline.json` — one row per
  question (`id`, `kind`, `hit`, `hit_rank`, `confidence`) under a header recording the models and
  retrieval settings the run used. `eval.score_rows` recomputes every metric from those rows alone,
  so a golden set's per-question history is checkable offline, with no weights and no network. Six
  aggregates cannot say *which* questions moved, and that is what a paired before/after comparison
  needs.
- **Questions carry a stable `id`.** Hand-written in the golden set and derived from the question
  text when absent, so an existing `questions.yaml` still loads. A repeated id is refused: it is
  what pairs a before row with an after row, so a duplicate silently drops a question from every
  comparison.
- **A `simple-lookup` class, and the golden set grows from 41 questions to 74.** Twenty ordinary
  factual questions as the control class a graph channel must not damage, and thirteen further
  single-KB multi-hop questions authored from corpus structure. The demo KB's baseline is rewritten
  once for the growth; the previous one is preserved as `eval/baseline-pre-growth.json`, and a test
  re-scores the committed artifact to prove the questions already in the set score exactly what
  they scored before.
