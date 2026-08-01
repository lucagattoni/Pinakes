## G2 — The headroom measurement, and what it found (20260801 12:14)

G2 was built to answer one question: is the graph release's gate reachable at all? **It is not, on
this corpus.** The precondition needed at least 7 of the ~18 single-KB multi-hop questions to fail
today. **One fails.** G3 does not start, and the answer arrived before anything bumped
`schema_version` and forced every KB in existence to rebuild — which is the whole reason the
measurement was sequenced first.

**HIGH — the demo corpus has no tags, and one directory. The plan assumed otherwise.**
`tests/demo-kb` is thirty documents in a flat `docs/`, and not one sidecar carries a `tags` key.
With `mentions` cut (decision 6), that leaves exactly **one** structural edge kind that crosses a
document boundary: `co-located`, through a single thirty-way directory hub. `shared-tag` derives
zero edges. `sibling`, `parent`/`child` and `in-section` are all intra-document and cannot bridge
two evidence documents by construction. So the "derived structure" the graph release exists to
evaluate is, on the committed corpus, one hub — and G5's own text reasons about "the directory
layout and **tag vocabulary** of `tests/demo-kb`" as though a vocabulary existed. It does not.
Whatever G3 would derive here, a result carried by it is a claim about one directory.

**HIGH — a reachability probe on a thirty-document corpus is close to vacuous, and the reason is
not the probe.** `candidates_per_source` is 30 and the corpus has ~30 chunks, so the vector channel
already returns essentially every document with a positive cosine: the funnel *sees* the whole
corpus on every query and then cuts to `final_k = 5`. A failing question is therefore almost never
a recall failure the channel could fix by reaching further — it is a ranking failure. That is why
the probe reports `at-seed` separately from `liftable`: two of the three questions the fake backend
called liftable were already among the fused candidates and merely ranked below the cut, having
traversed no edge at all. A ceiling built from those would have read as headroom and been none.

**The numbers, real `[light]` models, `tests/demo-kb` at 20260801 12:14.** 18 multi-hop questions,
**1 failing** (`mh-withdrawn-collection-register`), liftable 1 without authored edges and 1 with,
`beyond-2-hops` 0, `membership-only` 0. Required: 7 failing **and** 7 liftable without authored
edges. It fails on the first clause by six.

**The questions were frozen before the probe ran, and were not re-authored afterwards.** Thirteen
new multi-hop chains, authored from pairs of documents that between them answer one question and
share no vocabulary on the thing that joins them, with the second hop phrased in the first
document's words. Seventeen of eighteen are answered correctly. Re-authoring them until seven fail
is fitting the question set to the gate — the circularity decision 14 removed by cutting cross-KB
questions, and undetectable once done. The honest reading is that a corpus of thirty short,
topically disjoint documents cannot produce a hard multi-hop set: picking 5 of 30 is not a
discriminating retrieval task, and the pipeline scores 0.94 on it.

**MEDIUM — the fake backend and the real models disagree about the shape of the answer, and only
one of them is the measurement.** Under the deliberately tie-heavy hashing fake the same set shows
9 failing and 3 liftable without authored edges (6 with) — the exact with/without gap the plan
predicted L1's hand-authored links would produce. Under the real models both collapse to 1. A
measurement taken on the fake would have reported a *different failure* of the precondition and
invited the wrong remedy.

**MEDIUM — `_score` read `Outcome` objects, so the artifact could not have been re-scored.** Every
metric is a function of five fields per question, but the scorer was written against the in-memory
type. Splitting `score_rows(rows)` out is what makes the committed artifact checkable offline, and
it is what `test_the_committed_41_score_exactly_their_pre_growth_values` runs on: no weights, no
network, and the 41 pre-growth questions reproduce their baseline **byte-identically** — measured
on macOS against a baseline written by CI's ubuntu runner, which is the same cross-machine
agreement G1's new CI job independently confirmed the same morning.

**LOW — the first `--fake` run silently asked for real weights.** `_fake_kb` asserted each manifest
substitution appeared exactly once; `provider = "fastembed"` appears twice (embedding and rerank),
so the assertion fired and the run aborted — correctly. Loosening it to "replace whatever is there"
would have left the rerank provider real and made an "offline" gate download a model. The expected
occurrence count is asserted per line, not assumed.
