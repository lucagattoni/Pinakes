## A plan's blocking premise was inferred, not measured — and it was wrong for two days (20260806 04:05)

**HIGH — the reason a plan gives for a blocker is reused long after the blocker is gone.**
`plans/20260805_1721-metadata-as-retrieval-context.md` said `tests/demo-kb` could not measure the
injection experiment because *"no section spans multiple chunks, so there are no continuation chunks
to rescue — the mechanism has nothing to act on"*. Measured with the real chunker and the real
tokenizer over all 30 documents: **30 of 30 sections span more than one chunk**, and **29 of the 30
continuation chunks do not contain their own heading text**. The corpus carries the exact mechanism
the plan said it lacked.

The error was an inference from the wrong mechanism. The plan's *fact* was right — the documents are
~7 lines — but it reasoned that a short document fits in one chunk. `chunk.py` splits on **paragraph
blocks first** (`Block` is "one paragraph under one heading path") and only then applies token
limits, so a 7-line document with two paragraphs yields two chunks of 27 and 31 tokens under a
120-token budget. Nothing about the token budget was ever reached.

**What makes this worth recording is that the plan's *conclusion* was right.** Use the RFC corpus —
correct. So the wrong premise cost nothing at the time and would have cost a great deal later: it is
the sentence a future agent quotes when deciding whether some *other* experiment can run on the demo
KB. A conclusion is checked when it is acted on; a reason is copied forward unexamined.

**MEDIUM — the honest reason demo-kb cannot license this is arithmetic nobody had done.** 66
answerable questions, **4 misses**, and **56 of 62 hits already at rank 1**. The whole improvable
pool on `recall@k` is 4, and the project's own `sign_test(4, 0)` returns **p = 0.0625** — so a
*perfect* result fails the p < 0.05 bar the graph channel was held to. That is a **power** limit, not
a mechanism limit, and the two have different remedies: a mechanism limit is fixed by a different
corpus, a power limit by a different metric or more questions. Writing the wrong one down sends the
next person to the wrong fix.

**MEDIUM — reasoning from a committed artifact nearly produced a confident wrong number.** The miss
count above was first read out of `tests/demo-kb/eval/outcomes.json`, whose header **predates G5** —
no `graph_channel`, no `edge_kinds`, no `retrieval.adjacent_k`, and `graph_gate.read_leg` reports its
channel as `(absent)`. Two independent reasons the number could not be trusted from that file alone:
the artifact is only rewritten under `--write-baseline`, so CI never refreshes it; and `compare()`
tolerates a **±0.02** drift, which spans 4 to 6 misses — and `sign_test(5, 0)` = 0.0312 **passes**.
The claim "a perfect result cannot license" was therefore one question wide. Re-running the eval
settled it: aggregates identical, and **all 74 rows match the committed file exactly**. The rule is
not "distrust artifacts" but **an artifact whose header does not match the current binary is
evidence about the past** — the identity check `graph_gate.check_identity` performs on legs is the
same check a reader owes any committed number.

**MEDIUM — four silent failures sat in front of an experiment costed at "~2 h rebuild + eval".** The
RFC corpus stamps no `max_tokens`, so the default **510** applies against a measured window of
**512** with 2 special tokens: **zero headroom**, and prepending anything pushes every full chunk
past the window. Embedding an over-length string raises **no warning and no error** (measured, empty
`warnings` list), and `assert_chunkable` cannot catch it because it validates `max_tokens`, never
`max_tokens + prefix`. The direction is what makes it dangerous: truncation removes text from
exactly the long chunks the hypothesis is about, biasing the result toward **no movement** — a false
negative that reads as a clean result. Separately, the lexical channel cannot be injected at all
without a new `chunks` column, rewritten FTS5 triggers and a `schema_version` bump, because
`chunks_fts` is an external-content table filled by triggers copying `new.text`.

**The estimate was not wrong about the run; it costed the run alone.** Step 2 is three increments and
a measurement, and none of the three was visible from the plan as written.

**LOW — a plan that forbids retrying below "the threshold" has to name it.** The document's
anti-circularity clause read *"a result short of the threshold is reported rather than retried"*
while nothing in it ever said what the threshold was. An unfalsifiable gate is not a gate; it was
fixed by decision rather than discovered, but it survived a full adversarial review of the plan
because the sentence *sounds* like a commitment.
