- **The bounded traversal core** (L3 of the links release) — `pinakes.graph.traverse`, pure, with
  no SQLite and no I/O of its own. Depth counts logical hops rather than physical edges; fan-out is
  capped by the new `[retrieval] adjacent_k` (default 8) and applied **after** ranking, so a cap
  never selects by whatever order the edge source happened to return; the response is capped on row
  count and token budget **independently**, because the two have different remedies. Every bound is
  clamped server-side — depth at 3, fan-out at 64 — and a new gate in `check.sh` and its own CI job
  drives the shipped core at `depth=99, adjacent_k=10000` against a wide, deep fixture graph to keep
  that true. Neighbours found but not expanded come back on a `frontier` carrying one of five
  reasons in a stated precedence, and links whose target does not resolve are returned rather than
  dropped. `adjacent_k` is settable but deliberately **not** stamped into the template: a manifest
  carrying an unknown key cannot be read by an earlier pinakes at all.
