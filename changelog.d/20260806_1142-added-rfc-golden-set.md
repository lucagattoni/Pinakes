- **A frozen golden set for the RFC realism corpus, calibrated, with its baseline captured.**
  110 questions at `tools/rfc_corpus/questions.yaml` — 32 lexical, 32 simple-lookup, 32
  paraphrase, 14 no-answer over 96 of the corpus's 195 documents. The corpus itself stays
  uncommitted and regenerable; the questions are authored rather than harvested, so they ship with
  the engine, and `tools/build_rfc_corpus.py` copies them into `<out>/eval/questions.yaml` on every
  build. `python -m pinakes.eval <out>` then needs no path flag.
  The generated manifest also stamps `[retrieval.confidence]`, fitted against the set's
  unanswerable questions. Without it every confidence is `unknown`, and the eval reports
  `false_abstain` and `false_confidence` as a vacuous 0.0 — measured here: stamping the block moved
  `confidence_coverage` from 0.0 to 1.0 and the two error rates from 0.0 to 0.0104 and 0.1429.
  `tools/verify_rfc_golden_set.py` is new: every answerable question records the sentence from its
  document that answers it, and this checks each one is really there. A wrong `expect` is otherwise
  indistinguishable from a retrieval miss.
