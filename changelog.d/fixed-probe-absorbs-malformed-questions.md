- **`tools/reachable_ceiling_probe.py` refuses a golden set it cannot measure, instead of
  reporting a number that looks valid.** Two malformed questions used to be absorbed in silence,
  and both moved the count the graph release's precondition binds on. A hop whose `expect` named a
  path the index does not hold resolved to no document at all and was recorded
  failing-and-unreachable — measured on demo-kb, one typo took `failing` from 9 to 10 while
  `liftable` stayed 3, deflating the ratio by a tenth with nothing in the output saying so. A
  `multi-hop` question with no `hops` yielded no verdict while still counting in the `multi-hop`
  denominator, so it could never be `failing`: 18 questions became 19 and the extra one appeared
  in no other figure. Both now stop the run with a named error listing every offending question
  and path, before a backend is loaded. The template's `eval/questions.yaml` documents `hops`
  too — it described `id`, `question`, `expect` and `kind` and never mentioned it, which is how a
  hand-written question set arrives without one.
- **The probe no longer discards `--kb` when `--fake` is given, and every output names the KB it
  measured.** `--kb <corpus> --fake` silently measured a copy of the demo KB instead and reported
  its numbers under no particular name; the two are now mutually exclusive at the argparse level.
  Both output formats carry the KB root and its kb-ulid (`kb_root`, `kb_id`, `fake_backend` in the
  JSON), so two runs against two corpora can be told apart. The closing prose no longer prints a
  hardcoded `>= 7` precondition: the threshold belongs to the measurement plan for the corpus in
  hand, and the tool measures whichever corpus `--kb` names.
