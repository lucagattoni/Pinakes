- **[`plans/links-and-graph.md`](plans/links-and-graph.md) restructured after a third adversarial
  pass — the links release never needed the golden set.** Two reviewers returned 24 HIGH, and three
  of them collapsed into one root cause: `eval.py` is single-KB in its bones (one connection, one
  manifest, one backend, `retrieved` as local path strings), so a cross-KB question forced through
  it scores **0.00 by construction** — the hop can never be followed — or **1.00 by construction**,
  merely confirming a link the corpus author hand-wrote. Neither can decide anything, and pass 2 had
  already established such questions cannot respond to `graph_channel`.

  Since the links release changes no retrieval, it needs no golden-set work at all: traversal
  correctness is directly testable. Cross-KB eval is cut entirely, all measurement work moves to the
  graph release where it *is* the gate, and the plan becomes 8 + 6 increments instead of 10 + 4.

  Also corrected:

  - **The determinism increment was a provable no-op.** Its three proposed tiebreaks could never
    change an outcome: cross-document ties are already totalised by `documents.path`, and within a
    document rowid order *is* ordinal order in every write path that exists. The instability a
    rebuild could introduce is upstream, in the candidate lists that set the RRF ranks, where no
    final tiebreak reaches. It is now a *measurement* increment — establish reproducibility, fix
    only what the measurement shows.
  - **The gate's statistic had no artifact that could produce it.** An exact sign test needs
    per-question before/after pairs; `run()` discards outcomes, `write_baseline` stores aggregates,
    and `compare()` reads only those. Per-question outcomes are now a committed artifact with an
    owner.
  - **The headroom threshold was asserted, not derived, and its test could not fail.** It checked a
    number the author had committed. It now runs the questions and counts, and the number follows
    from the gate table: 7 currently-failing questions to tolerate one regression.
  - **`requires_pinakes` cannot explain a key retroactively** — a pinakes built before it has no
    pre-pass and fails on `requires_pinakes` itself. Deferring `adjacent_k`'s template stamp to that
    increment bought nothing; new keys simply stay out of the template in both releases.
  - **A neighbour's `kb` field was unspecified across three namespaces** — `[kb] name` (documented
    as free to rename), `[[links.kb]] name` (machine-local), and the ULID. Only the ULID is
    dereferenceable, which is the same reason a `pnk://` URI carries no alias. The field is now
    `kb_id`, and a test asserts `pinakes_get` actually resolves what `pinakes_links` returns.
  - **Twelve increments still told a future agent to write a `CHANGELOG.md` entry**, forbidden by
    the fragment convention that landed while this plan was being written — and no gate catches a
    direct edit. Both release procedures also omitted `tools/fragments.py --apply`, which would have
    shipped every fragment unspliced.
