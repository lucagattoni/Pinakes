- **`tools/two_leg_gate.py` — two eval legs, paired on question id and counted by rank.**
  Compares a before and an after artifact that differ in exactly one header key (default
  `chunking.metadata`) and **refuses to compare at all** if they differ anywhere else — the check
  `graph_gate.check_identity` could not provide, because it takes three legs shaped to the graph
  channel and inspects `k`, `embedding`, `rerank`, `ranking` and `retrieval` but not `chunking`.
  Two legs chunked at different `max_tokens` therefore compared clean, and on one RFC that is 63 of
  1 858 chunk texts differing: a rechunk reported as the effect under test. It also refuses a leg
  compared against itself and legs that do not cover the same questions.
  A miss sorts after every hit, so a change that loses an answer outright is counted as the worst
  regression rather than as no movement; `no-answer` questions are excluded, having no rank to
  move. `--sign-test` layers `graph_gate.sign_test` — the same exact one-sided test, reused rather
  than rewritten — on the same comparison.
