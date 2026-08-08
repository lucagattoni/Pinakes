- **`tools/graph_gate.py` compares the `chunking` block, so two legs chunked differently can no
  longer be judged against each other.** It checked `k`, `embedding`, `rerank`, `ranking` and
  `retrieval` and not `chunking` — the block `eval.header` records precisely so a leg can say what
  it was built under. A rechunk between legs is not noise but two corpora: rows paired on `id` were
  produced by searching different texts, and the movement is reported as whatever was under test.
  Measured, `max_tokens` 510 against 480 moves 63 of 1 858 chunk texts on one RFC, and
  `tools/eval_reproducibility_gate.py` exists because one question in 41 moved across a plain
  rebuild. Nothing under `chunking` is excepted here, unlike `tools/two_leg_gate.py`, where
  `chunking.metadata` is the independent variable; this gate's is `graph_channel`.
