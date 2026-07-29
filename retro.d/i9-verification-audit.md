## I9 — Auditing the verification table (20260729 05:40)

**HIGH — the table that verifies everything verified nothing.** `plans/v0.2.md` ends with 98 rows,
each promising a property and naming the test that holds it, under a preamble reading *"a promise in
a section with no owner is a wish"*. **61 of the 98 test paths did not resolve.** Not because the
properties went untested — nearly all are tested, usually under a better name than the plan guessed
— but because the paths were written *before* the tests existed and implementation renamed them.

The failure is not the renaming. It is that **nothing ever read the table**, so it could drift a row
at a time for nine increments with every gate green. A table of test paths is prose until something
executes it, and prose about tests reads exactly like tests. The fix is not a better table: it is
`tests/test_verification.py`, which resolves every reference in `docs/VERIFICATION.md` and fails on
the first one that does not exist. The document can now go stale exactly once — in the commit that
breaks it.

**The audit found a real gap on its first run, which is the argument for doing it.**
`test_every_v02_check_appears` was assigned to I8, named in the table, and never written. Writing it
(as `test_every_doctor_check_is_exercised_by_a_test`) immediately found **five `pnk doctor` checks
with no test at all**: `template`, `reranker`, `model cache`, `extensions`, `links`. Link coverage is
a §6.2 promise; the reranker check exists so a health check does not download weights. Both had
shipped untested since I11.

**MEDIUM — I wrote the exact CI assertion the plan warned against, and only running it caught it.**
The plan says the core-only wheel smoke must use "a **core-only KB that does not need embeddings**,
because today's smoke KB fails on sentence-transformers long before it reaches an extractor, so the
assertion would prove nothing". I built a PDF-only KB believing that satisfied it, and it does not:
the embedding backend loads before any extractor, so `pnk sync` on a PDF-only core install still
fails on `pinakes[st]`. My `grep -q 'pinakes\['` passed — against the wrong extra. `pnk doctor` is
the only surface that reaches the extractor question on a core-only install, because it reports a
failing backend as a check and carries on. **Reading the plan's warning was not enough to avoid the
thing the plan warned about; running the command was.**

**A plan is a historical record, and correcting it would have destroyed the evidence.** The
temptation was to fix the 61 paths in place. That would have erased the only proof that predicted
test names drift — and with it the reason `tests/test_verification.py` needs to exist. The plan
keeps its predictions under a dated supersession note; the resolved mapping lives in `docs/`.
