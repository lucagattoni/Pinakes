- **[`plans/links-and-graph.md`](plans/links-and-graph.md) revised after a sixth adversarial pass —
  2 HIGH, and the pass-5 fixes verified correct.** Both were narrow, and both were introduced by the
  previous round's own repairs.

  **A gate clause stated one of its two guards backwards.** Clause 4 made a *rise* in
  `confidence_coverage` a stop. A rise is an improvement — `eval.py` treats the *drop* as the
  regression, with the comment *"losing the ability to say anything is a regression too"* — and the
  metric is 1.0 in the committed baseline, so it cannot rise at all. The clause was a stop condition
  that could never fire, while the guard the same-commit re-baseline actually removes went
  unrestored. It now enumerates all six `compare()` families with the direction the code checks, and
  says which single term the re-baseline may absorb.

  **The anti-circularity guard was asserted to live in an increment it never reached.** The
  structural-edge increment says *"the guard is in G2 and G5"*; the phrase appeared in G2 and G3 and
  nowhere in G5. An engineer building G5 from G5 would compute the sign test once over all edges —
  including the links hand-authored into both corpora by an earlier increment — pass, flip
  `graph_channel` to default-on, and cut the release. The gate is now computed **twice, with and
  without authored edges**, both p-values recorded, and the channel ships `off` if only the authored
  run passes. That is the same "1.00 by construction" reasoning that removed cross-KB questions from
  the golden set three passes ago.

  Also closed: the stale-reverse-edge delete is now scoped by `origin` as well as source KB (under
  the plan's own self-listing fixture, an origin-blind delete removes the authored rows the insert
  guard exists to protect); `adjacent_k` gained the server cap its own gate asserts against;
  `pnk link`'s free-path gate edit found an owner; the version floor is verified at whichever cut
  ships it, rather than only on the path where the final increment runs; and five amendment rows
  gained a home in their increment's Docs line.
