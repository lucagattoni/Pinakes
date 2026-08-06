- **The per-question eval artifact records the chunking it was produced under.** `eval.header`
  promises "every setting that can move a row" and did not include `[chunking]` — the one setting a
  before/after comparison is least able to notice going wrong. Two legs chunked under different
  `max_tokens` are two corpora: measured on one RFC, 63 of 1 858 chunk texts differ between 510 and
  480, and `tools/eval_reproducibility_gate.py` exists because *one* question in 41 moved across a
  rebuild. `max_tokens`, `overlap` and `headings` now travel with every artifact. No row gained a
  field, so `OUTCOMES_SCHEMA` is unchanged and an older artifact still reads.
