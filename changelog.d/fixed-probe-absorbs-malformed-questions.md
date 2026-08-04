- **`tools/reachable_ceiling_probe.py` refuses a golden set it cannot measure, instead of
  reporting a number that looks valid.** Six shapes of malformed question used to be absorbed in
  silence, each of them moving the count the graph release's precondition binds on: a hop whose
  `expect` named a path the index does not hold (it resolved to no document and was recorded
  failing-and-unreachable); a hop whose `expect` named a document the index holds **with no
  chunks**, which no retrieval or expansion can ever produce, so a correctly spelled path
  corrupted the verdict the same way; a `multi-hop` question with **no** `hops`, which counted in
  the multi-hop denominator, yielded no verdict and so could never be `failing`; a `multi-hop`
  question with **one** hop, measured as a single search and able to move `liftable` *upward* —
  the dangerous direction, since the precondition is a floor; a hop with an empty `query`; and a
  golden set with no `multi-hop` question at all, every figure of which would be a zero
  indistinguishable from a measured one. All now stop the run with a named error listing every
  offending question and path, before a backend is loaded, with a `did you mean` hint when a path
  differs only in case, `./` or Unicode normalisation. Measured under the offline fake backend,
  where demo-kb reads 18 multi-hop / 9 failing / 3 liftable: one mistyped hop path took `failing`
  to 10 and left `liftable` at 3; one hops-less question took the denominator to 19 and moved
  nothing else. (The real `[light]` measurement of that corpus is 18 / 1 / 1, where a single such
  question would move the binding figure by half.)
- **The template's `eval/questions.yaml` documents `hops`.** It described `id`, `question`,
  `expect` and `kind` and never mentioned the key at all, which is how a hand-written question set
  arrives without one — the trap was armed by our own scaffold.
- **The probe no longer discards `--kb` when `--fake` is given, and every output names the KB it
  measured.** `--kb <corpus> --fake` silently measured a copy of the demo KB and reported its
  numbers under no particular name; the two are now mutually exclusive at the argparse level. Both
  output formats carry the KB root — absolute and resolved, so two runs from two working
  directories cannot label two corpora identically — its kb-ulid, and whether a fake backend
  produced the numbers (`kb_root`, `kb_id`, `fake_backend` in the JSON). The closing prose no
  longer prints a hardcoded `>= 7` precondition: the threshold belongs to the measurement plan for
  the corpus in hand, and the tool measures whichever corpus `--kb` names.
