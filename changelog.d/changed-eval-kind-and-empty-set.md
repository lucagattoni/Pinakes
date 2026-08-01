- **A golden set's `kind` is validated against the known set instead of defaulting to `lexical`.**
  An absent or unrecognised `kind` is now an error naming the six that exist. A silent default is a
  claim about how a question was authored, and a wrong one puts it into a class whose per-class
  score then measures two different things.
- **An empty golden set skips the evaluation with a printed reason, rather than failing it.** The
  `notes` template ships `questions: []` and scaffolds an empty `docs/`, so it cannot ship
  questions naming documents that do not exist — which made `make eval` fail by construction on
  every freshly `pnk init`ed KB. The committed golden set is still asserted to be non-empty, so an
  *emptied* one cannot pass quietly.
- **`pinakes.search.fused_candidates` exposes the fused candidate list** — the stage between
  retrieval and reranking. It is what a graph channel takes as its roots and what the reachability
  probe measures from; `search()` now calls it, so there is one implementation of the funnel rather
  than a measurement that can drift from it.
