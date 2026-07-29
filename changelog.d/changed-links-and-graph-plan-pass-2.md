- **[`plans/links-and-graph.md`](plans/links-and-graph.md) rewritten after a second adversarial
  pass — six of the first pass's own fixes were wrong.** Two reviewers returned 26 HIGH, 30 MEDIUM
  and 8 LOW against the revision that pass 1 produced, roughly the 40–45% fix-induced rate
  `plans/v0.2.md`'s iteration log predicts. Still a draft; a third pass is required before any of it
  is built.

  What was wrong, and now is not:

  - **The determinism increment chose the rowid as its rebuild-stable sort key**, while `store.py`
    says two lines above the table that *"a chunk has no identity across rebuilds"*. It also framed
    the hazard as run-to-run variance, which does not exist — all three named sites are
    deterministic for a fixed index, which is why `make eval` was already byte-identical three runs
    running. The key is now `(doc_id, ordinal)`, the hazard is cross-build and cross-machine, and a
    fourth site (`_hydrate`, which has no `ORDER BY`) joins the three.
  - **A cross-KB neighbour had no way to be identified at all.** The tool contract returns `title`,
    which lives only in the local index; the fix added a title-from-sidecars mechanism and missed
    that the neighbour carried no KB identifier either, so an agent could neither fetch it nor name
    where it lived. Neighbours now carry `kb` and, for cross-KB, no `title` — which also drops a
    per-query filesystem walk of another KB that DESIGN §6.2 sanctions only at sync time.
  - **The eval gate cited a statistic the sign test does not measure.** "≥ 5 questions **net**" was
    justified with 0.5⁵ = 0.031, but the sign test counts *discordant* questions: 8 improved / 3
    regressed is also net +5 and gives p = 0.113. The gate admitted results up to eight times the
    claimed p while rejecting 4/0 at p = 0.063. It is now the exact test itself, tabulated.
  - **The gate was also unreachable.** It can only read single-KB questions, and the golden set had
    been sized "most cross-KB" — leaving ≤ 7 improvable against a 5-question threshold. The class is
    now majority single-KB, cross-KB questions get their own `kind` so `compare()` gates them
    separately, and a headroom check must pass **before** `schema_version` bumps rather than being
    reported after every KB has already been forced to rebuild.
  - **A rule invented for cross-KB scoring would have rescored the 41 questions its own exit
    criterion promised to leave untouched** — all five committed multi-hop questions are hopped. It
    was also redundant: `eval.py` has required every hop to land since the scorer was repaired. A
    cross-KB question is simply a hopped question whose later hop lands in the other KB.
  - **Banning docs-sweep increments left the docs with no owner at all** — the plan contained zero
    occurrences of `GUIDE`, `CLI.md` or `--help`, while `docs/CLI.md` and `docs/STATUS.md` both
    carry rows this work falsifies. Every increment now names its doc homes, and both releases
    regained a run-it-don't-reason-about-it verification section.

  Three decisions were taken with the user in response: cross-KB neighbours carry no title; the
  multi-hop class is majority single-KB; and G1's edge weights are **frozen** at the research
  document's priors rather than fitted against the golden set that then gates them — `calibrate.py`
  already records that circularity for the confidence thresholds and calls the result optimistic.
