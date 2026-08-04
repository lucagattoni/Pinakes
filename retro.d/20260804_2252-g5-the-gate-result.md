## G5 — the gate, run: `expand` ships `off` (20260804 22:52)

**HIGH — the increment's deliverable is a negative measurement, and it is a clean one.** On the RFC
realism corpus, at G5's own HEAD, against a schema-3 index rebuilt for this run:

| leg | multi-hop | improved | regressed | p |
|---|---|---|---|---|
| `off` | 7/20 | — | — | — |
| `expand`, drop `authored` | 4/20 | 0 | 3 | **1.0000** |
| `expand`, all kinds | 4/20 | 0 | 3 | **1.0000** |

**licensing p = 1.0000** (`max`, the more conservative of the two). **`expand` defaults `off`**, and
`tools/graph_gate.py` exits 1. Clause 1 fails in both runs; clause 2 fails as well —
`by_kind[multi-hop]` 0.350 → 0.200 against a 0.02 tolerance — and clause 4 fails on `recall_at_k`
for the same movement.

Lost: `content-disposition-http-takeover` (hit at rank 1 → **not found at all**),
`http-rate-limit-status-code-provenance` (rank 4 → miss), `sip-invite-2xx-retransmission-defect`
(rank 2 → miss). **Nothing was lifted.**

### `reachable ≠ retrievable` — the finding, and the plan predicted its shape

The reachability probe found **9** of the failing multi-hop questions reachable within two logical
hops *without* authored edges, which is what unblocked the graph release. The retrieval instrument
lifts **none** of them, and the channel's extra candidates displace three answers two-list fusion
already had. The plan drew this distinction itself — *"a ceiling gauge cannot rank, and an argument
cannot measure"* — and G5's whole existence is the reason it could be checked rather than assumed.
**A reachability precondition is necessary and nowhere near sufficient**, and the gap between the
two is not a small correction: it is 9 questions against 0.

The go decision also anticipated the outcome's meaning: *"If `expand` did not pass, the finding is
'graph structure does not help this corpus', and the response is a corpus or a different channel
design, never an escalation to a more expensive one."* Nothing here licenses PPR.

### Two things that make the number narrower than it looks, both stated rather than worked around

**Clause 3 passes vacuously, and clause 4 nearly so.** The RFC corpus has `[retrieval.confidence]`
commented out, so every question scores `confidence: unknown`; neither the confidence-lost nor the
newly-found-at-low term can be non-zero there. The decomposition clause 3 exists for is exercised
only by the synthetic artifacts in `tests/test_graph_channel.py` — which is precisely why the plan
insisted the gate be driven by synthetic fixtures as well as by the corpus. **A gate whose only
fixture is the real corpus can only be tested in whichever direction that corpus happens to point**,
and here two of its four clauses would never have fired.

**The `--drop parent-child` arm is inert on the gating corpus.** No chunk in the RFC corpus carries
a `heading_path`, so `parent-child` and `in-section` derive **zero** edges and dropping them changes
nothing by construction. The arm the arity decision added cannot say anything here. Its cost was
measured separately (see the ceiling fragment); its retrieval value remains unmeasured, and the
corpus that could measure it does not exist yet.

### The `--drop sibling` arm answers its question, and the answer is "neither"

The go decision added this arm to ask, *with the instrument that measures retrieval quality rather
than a reachability ceiling*, whether 99.2% of the graph's mass earns its place. On this corpus
`sibling` is 106 506 of the 107 411 non-transit structural edges, and dropping it produces
**exactly the same 4/20, the same three regressions, and the same p = 1.0000** — one question's
rank moves, and it is a miss either way.

So `sibling` neither helps nor hurts. It is 99.2% of the stored graph and it is **inert in both
gauges**: the reachability probe already found removing it cost nothing, and the retrieval
instrument now agrees. Two independent measurements, and the harm the channel does comes from
somewhere else entirely — the document-level path, `membership` transit into `co-located` (262
edges) and `shared-tag` (643) hubs, which pull whole documents' chunks into the fusion.

**With the caveat that makes it a narrower claim than it looks:** every chunk here has an empty
`heading_path`, so a "sibling" in this corpus is an adjacent arbitrary *size-slice*, not an adjacent
section. The arm has measured the value of size-slice adjacency, which is what this corpus's broken
structural chunking produced — not the value of `sibling` as designed. On a corpus whose chunker
works the question is still open.

### Five legs land on the same number; the sixth does not, and I had already written that they all did

**The full matrix**, `off` at 7/20 (recall@k 0.3500, MRR 0.421):

| leg | multi-hop | improved | regressed | p | ms/query |
|---|---|---|---|---|---|
| `off` | 7/20 | — | — | — | 2012 |
| `expand` | 4/20 | 0 | 3 | 1.0000 | 2051 |
| `expand-no-authored` | 4/20 | 0 | 3 | 1.0000 | 2106 |
| `expand-no-sibling` | 4/20 | 0 | 3 | 1.0000 | 2067 |
| `expand-no-parent-child` | 4/20 | 0 | 3 | 1.0000 | 2028 |
| `expand-no-link-distance` | 4/20 | 0 | 3 | 1.0000 | 2024 |
| **`expand-in-degree`** | **6/20** | **1** | **2** | **0.8750** | 2237 |

**MEDIUM — the process finding, and it is the file's own failure class caught in the act.** With
five of the six legs written I recorded that *"every leg lands on the same number, which is what
makes the result robust"* — a claim about six legs asserted from five, while the sixth was still
running. The sixth then came back different: in-degree salience is the only configuration that
lifts anything (`imap-utf8-two-strategies`), and the only one that regresses two rather than three.
The claim was wrong within minutes of being written, in a fragment whose subject is an assertion
satisfied by something other than the property it names. **A generalisation over N runs written
while N−1 have finished is not a measurement, it is a prediction wearing a measurement's clothes.**
The correction is recorded rather than quietly overwritten, because the tempting fix — waiting and
writing the true sentence — would have hidden how easy it was to write the false one.

**What the sixth leg does and does not license.** `expand-in-degree` at 1 improved / 2 regressed is
p = 0.8750: nowhere near the gate, and still a net loss of one question against `off`. It is
**reported, never gated** — three variables against one threshold is not a decision procedure — and
noticing that it is the best-performing leg after seeing the numbers is exactly the exploratory
fitting the pre-commitment forbids. It is a direction for a future measurement on a corpus that can
carry one, not a result.

**Latency, the other exit criterion.** `off` 2012 ms/query against `expand` 2051 — **1.02×**, so the
channel costs about 2% on a 106 806-chunk index and the "slow at query time" risk did not
materialise. In-degree salience is the expensive leg at 2237 ms (1.11×), which is the one place the
matrix's timing separates the configurations at all.

### The with/without-authored split is stronger here than on `tests/demo-kb`

All **391** of the corpus's authored links are intra-KB — every `to:` names the corpus's own KB
ULID — so unlike `tests/demo-kb`, where only 12 of 16 survive the cross-KB inertness rule, the
with-authored leg has every one in play. They still move only two questions' *ranks* and flip no
outcome, and both gated runs regress the identical three questions. The anti-circularity guard had
nothing to catch, because there was no win to be circular about.

### The pre-commitment held

*A result short of the table ships the channel `off`, with counts and p-value recorded, untuned.*
Nothing was tuned, no weight moved, no threshold was revisited after seeing the number. The
`authored` weight's *measured at G5* marker is discharged by this run as **"measured, and it changed
no outcome"** rather than by a fitted value.
