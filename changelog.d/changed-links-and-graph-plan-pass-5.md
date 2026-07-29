- **[`plans/links-and-graph.md`](plans/links-and-graph.md) revised after a fifth adversarial pass —
  3 HIGH, down from 13.** All three sat on the seams the fourth pass opened, and one of them was a
  decision resting on a false premise.

  **Terminality is a policy, not an emptiness.** The plan justified making cross-KB neighbours
  terminal by claiming KB *K*'s index has nothing to walk past one. `store.py` says the opposite in
  a comment on the table itself — *"a reverse link's source lives in another KB"* — so a
  reverse-scanned row is keyed on the **foreign** document and a depth-2 query from one returns real
  results. The conclusion survives on a better reason: K holds only the partner's links that point
  *back at* K, never its internal ones, so expanding through a foreign document shows a
  systematically incomplete slice that no caller can distinguish from the whole. The consequence for
  the build is sharper than the wording — terminality now needs an **explicit suppression**, a test
  fixture that actually contains the back-link rows (without them the test passes against an
  implementation with no guard at all), and a mutation target, none of which the plan had.

  **Whether authored `doc ↔ doc` edges are in the expansion channel was never stated**, while the
  orientation rule, the reachability probe and the gate's pessimism argument each depended on the
  answer. They are — the research's own argument for counting depth in logical hops is that physical
  counting would strand them. Stating it exposed a circularity the plan had already refused once:
  the gate could be satisfied by hand-authored links bridging hand-authored questions, the same
  "1.00 by construction" shape that got cross-KB eval cut. Reachability and the gate are now both
  reported **with and without** authored edges, and a gate that passes only *with* them is recorded
  as such rather than counted as evidence that derived structure helps.

  **The previous fix disarmed a guard it wasn't aiming at.** Re-baselining in the same commit as
  turning the channel on silences every metric in `baseline.json`, including `false_confidence` —
  which is sensitive to the channel by the same mechanism and is *not* covered by the per-class
  clause, because a no-answer question can stay a clean non-hit while flipping to HIGH confidence.
  One flip is 0.125 against a 0.02 tolerance. A fourth gate clause makes a rise in
  `false_confidence` or `confidence_coverage` a stop rather than a re-baseline.

  Also: `frontier` reasons went from four to five (the two response caps are independently
  observable, so they cannot share one) with a stated precedence and an amendment row; the traversal
  core is now generic over a provider-supplied node identity, so one implementation serves both the
  document surface and the structural channel instead of the graph release needing a second
  expander; and the conditional third release has a stated shape rather than being discovered at the
  cut.
