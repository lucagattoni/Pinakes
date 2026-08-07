## 2d — The screen said no, and the controls are what make that worth believing (20260807 09:07)

**The result: 6 improved, 6 regressed, 84 unchanged, over 96 answerable questions.** The
pre-registered criterion was *strictly more improvements than regressions*, so the screen is a
**no-go** and the `schema_version` bump at 2e is not taken. Per the pre-registration these numbers
are the whole report — they are not evidence for or against the hypothesis in either direction, and
they appear here and in the increment's commit message and nowhere else. The screen's own artifacts
were deliberately not committed.

**What was measured, stated exactly, because a null is only as good as its controls.** Injecting
`title > heading path` into the text that is **embedded** — the vector channel alone — moved
nothing net on this corpus at `rerank = "none"`. **The both-channel form was not tested**: the
lexical channel needs a new `chunks` column and a schema bump, which is the cost this screen
existed to decide. The dilution objection that disqualified vector-only as a *gate* applies in full
to this null: RRF fuses an injected vector channel against an unchanged BM25, so a real effect is
attenuated before it reaches a rank.

**A null result is a claim about the world only if the instrument was pointed at it, so four
controls were run before the comparison — three of which the plan did not ask for.**

| Control | Result |
|---|---|
| The uninjected index still reproduces 2c's baseline (`rerank = "local"`) | **110 of 110 rows identical**, twice — once on `main`'s binary, once on this branch with the option off |
| Both legs are the same corpus | 195 documents, 43 353 chunks, and **one sha256 over every chunk text, equal** |
| The injection actually reached the vectors | mean cosine **0.8398** between the before and after vectors of 2 000 sampled chunks; **zero** unchanged |
| The prefix was the intended string | **195 of 195** published titles, **zero** filename stems — finding 5's confound absent — and 93.2% of chunks carrying a heading path |

The third is the one that decides how to read the null. Chunk texts are byte-identical between the
legs by construction, so if the injection had silently not happened, *every* artifact in the
experiment would look exactly as it does now — same corpus, same questions, a clean flat result —
and the conclusion would be drawn from a no-op. Measuring the vectors is the only thing separating
"no effect" from "no injection", and it cost one script.

**The option-off path being a verified no-op is not a formality either.** The same binary that
carries the injection reproduced the frozen baseline row for row, which is what licenses comparing
this branch's `after` leg against a `before` leg captured on it.

**The shape of the movement is more interesting than the count, and it is not being reported as a
result.** Of the 6 improvements, 5 were `paraphrase` — the class the hypothesis targets, and the
only class with power on this corpus. Of the 6 regressions, 2 were `simple-lookup` questions that
had been at rank 1. That is what a dilution cost looks like: a prefix adds tokens to a vector whose
question needed none of them. Twelve of 96 rows moved, so the mechanism is doing something; it is
simply not doing more good than harm through one channel. **This is an observation about a
measurement that was pre-registered not to be interpreted, and it must not become the premise of a
retry** — the anti-circularity rule says a result short of the threshold is reported rather than
retried with a different injection format.

**Two things surfaced by building it that the plan had not anticipated.**

* **The refusal is a per-document failure, not an aborted run.** `assert_prefix_fits` raises a
  `ChunkingError` from inside `_index_document`, and every `PinakesError` there is already caught
  by sync's per-document handler: the transaction rolls back, the document is named in the report
  and recorded in the index for `pnk doctor`. That is the right shape — one pathological heading
  path should not cost a 195-document corpus its other 194 — and it still removes the silent
  truncation, because a refused document is not indexed at all. But "refuses the corpus" was the
  plan's phrasing, and the test written for it originally asserted a raise that never comes.
* **With injection on, *every* document is prefixed, because `skeleton()` falls back to the
  filename stem.** A document can reach the embedder with no `heading_path`; it cannot reach it
  with no title. So on an uncurated corpus the injected string is a *filename* — finding 5's
  condition, now located at the sync boundary rather than in the abstract. It is why the RFC corpus
  mints published titles before its first sync, and it is the strongest argument for the option
  defaulting `off`.

**A test that passed vacuously, caught during development and worth naming.** The assertion that
the injected prefix uses the *sidecar's* title was written over a sidecar-only edit — which is a
`RefreshMetadata` action, so it updates the row and re-embeds **nothing**. `all(...)` and
`not any(...)` over an empty list are both true, and the test was green while proving nothing. The
fix was `--rebuild` plus an explicit `assert backend.embedded` precondition. Any assertion of the
form *"everything embedded looks like X"* needs a companion assertion that something was embedded.

**`tools/two_leg_gate.py` exists because the instrument had the same gap one level up.** `5993521`
made an eval artifact *record* the chunking it was produced under; nothing *compared* it —
`graph_gate.check_identity` takes three legs shaped to the graph channel and inspects `k`,
`embedding`, `rerank`, `ranking` and `retrieval`, but not `chunking`. Two legs chunked at different
`max_tokens` therefore compared clean, which on one RFC is 63 of 1 858 chunk texts differing: a
rechunk reported as the effect under test. The new tool refuses on any header difference outside
one named key, and it excepts that key **by path**, not by block — excepting the whole `chunking`
table would hide exactly the rechunk it is there to catch.
