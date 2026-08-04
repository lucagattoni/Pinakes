- **`tools/reachable_ceiling_probe.py` now prints, and includes in `--json`, a per-kind edge
  census** — how many edges each of `sibling`, `parent-child`, `in-section`, `co-located`,
  `shared-tag` and `authored` derived for the run. Every kind is a key even at `0`, whether it
  derived nothing on the corpus (no `heading_path`, no tags) or was removed with `--drop`: a kind
  absent from the output was indistinguishable from a kind at zero, and the RFC realism corpus
  measurement needs to tell them apart (`plans/20260731_1202-open-corrections.md` item 1,
  `plans/20260803_2239-corpus-probe-run.md`). The census is read directly off the same `Graph`
  the traversal walks — no table is re-queried and no relation is recomputed — so it cannot drift
  from the edges a run actually derived.
