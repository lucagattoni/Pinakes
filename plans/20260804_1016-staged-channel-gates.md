# The staged graph channels — gates, not plans


> ## ✅ Decisions 1–3 taken by the user, 20260804 10:16
>
> **The `authored` weight: defer, and measure it as a G5 leg.** Not kept-and-risked, not damped, not
> capped — every one of those decides a frozen weight on an *argument*, which is what decision 13
> froze the table to prevent. G3 lands with the weight table carrying an explicit *measured at G5*
> marker. This satisfies the ⚠️'s intent (that the weight not be "discovered by a gate that passes")
> rather than its literal "re-decided before G3 is built", and that reading was put to the user.
>
> **A three-edge-kinds-absent corpus: run and restrict for G3; refuse for Gate 1 / PPR.** They are
> not the same question. For G3's precondition `shared-tag` and `authored` are both strong here and
> can carry a restricted claim. For PPR the absent input is not one edge kind of seven — it is
> **half the personalization vector** APPROACH §4B specifies, so the gate does not run on a corpus
> below the heading-coverage floor.
>
> **The thresholds are committed as written, recorded as proposals.** None is derived from a
> measurement and none can be before the run — that is what a committed threshold is. The
> alternative was prose (`"does not dominate"`), which both a null result and a decisive one satisfy
> at the reader's discretion. **A wrong number is arguable; no number is not.**

**Audience: whoever is deciding whether to start either of these. Goal: executor — of a
*measurement*, not of an implementation.**

`docs/STATUS.md:260` lists *"PPR graph channel, the `[ner]` extra — each eval-gated, not
scheduled"*. This file specifies the gates. **It deliberately contains no implementation plan for
either.** A detailed plan for work that may never ship is waste, and worse, it creates pressure to
build it: a written plan looks like a commitment, and the whole point of "eval-gated rather than
scheduled" is that neither has one.

**Source:** [`docs/graph/PINAKES_APPROACH.md`](../docs/graph/PINAKES_APPROACH.md) §9 (the gate
table, `:403`), §4B (PPR's recipe, `:184-212`), §3 (`mentions` and the `[ner]` design, `:129-147`),
and [`docs/graph/GRAPH_RAG.md`](../docs/graph/GRAPH_RAG.md) §2.3 (the counter-evidence,
`:63-67`).

**Written 20260803 22:53. Revised 20260804 08:51 against `main` at `68084d3`, after an adversarial
review** — 0.8.0 shipped, the RFC realism corpus was built and measured, and every `plans/` path was
renamed. Where this file adds a clause APPROACH §9 does not have, the addition is marked **[new]**
with the hole it closes. **Where it commits a number §9 leaves to judgement, it is marked
[threshold]** — those are proposals for the planner to confirm *with the user*, and confirmed or not
they are on record **before** the run.

> **`plans/` paths moved on 20260804.** Commit `61f1975` gave every plan a `YYYYMMDD_HHMM-` prefix.
> `realism-corpus.md` → `plans/20260801_0749-realism-corpus.md`; `links-and-graph.md` →
> `plans/20260729_0256-links-and-graph.md`; `corpus-probe-run.md` →
> `plans/20260803_2239-corpus-probe-run.md`.

**Citations re-confirmed at `d06ef7e`, 20260804 09:25.** The only commit since `68084d3` touches
`docs/STATUS.md`'s PyPI table, which is below every line this file cites; all four `STATUS` line
numbers here still resolve.

**Both gates are downstream of work that has not started.** The graph release's own gate has not
been reached (`docs/STATUS.md:383` § *Can the graph release's gate be reached?*), so neither channel
below is measurable today. That is not a reason to plan them; it is a reason to write down what
would have to be true.

---

## The rule that binds both, and is not negotiable

APPROACH §9's one hard rule:

> **a graph channel that regresses simple-lookup precision stays `off` by default, whatever it does
> for multi-hop.**

It exists because of a measured counter-result, not caution: GraphRAG-Bench (ICLR 2026) and related
analyses report GraphRAG *underperforming* vanilla RAG on ordinary factual lookup, one study at
~13% on Natural Questions (`docs/graph/GRAPH_RAG.md:65-67`). The `simple-lookup` class exists in the
golden set for this and nothing else — G2 added 20 such questions, and they score 1.00 today
(`docs/STATUS.md` § *Measured numbers*). **A class at ceiling can only move down.** That is what
makes it a usable veto and it is the reason it was added before any channel existed.

### How the veto is checked — stated because `compare()` cannot check it **[new]**

The only per-class regression check in the codebase is `compare()`'s `by_kind` loop, and it is
tolerance-gated: `src/pinakes/eval.py:574` (`tolerance: float = 0.02`) and `:604` (`elif after_kind
< float(before_value) - tolerance`). **"Regresses at all" and "regresses beyond tolerance" coincide
only at the demo KB's class size.** `simple-lookup` is 20 questions there, so one lost question is
`0.05 > 0.02` and fires. On any corpus with **≥ 51 `simple-lookup` questions**, one lost question is
`1/51 < 0.02` and `compare()` says nothing — **the veto evaporates exactly as the corpus becomes the
realistic one both gates are waiting for.** The RFC corpus is 300 documents; its golden set will not
have a 20-question `simple-lookup` class.

**So the veto is evaluated on the per-question artifact, not on `compare()`:**

1. Capture `eval/outcomes.json` before and after (`eval.py:527`, `write_outcomes` — rows sorted by
   id, so a diff shows movement rather than reordering).
2. Read both with `eval.read_outcomes` (`eval.py:535`), which refuses a file that is not a
   per-question artifact rather than partially reading it.
3. Join on `OutcomeRow.id` (`eval.py:142-154`: `id`, `kind`, `hit`, `hit_rank`, `confidence`).
4. **The veto fires if any question with `kind == "simple-lookup"` that had `hit == True` before
   does not have `hit == True` after.** Not a rate. A count, and the count that fires it is **one**.
5. **Report the ids**, in the run record and in `docs/STATUS.md`. A veto that fires without naming
   what it fired on cannot be argued with or checked.

`compare()` remains the CI guard for every *other* class and every aggregate. It is **not** the
instrument for this one, and a run that reports only `compare()`'s output has not evaluated the
veto — it has evaluated something weaker that happens to agree on one corpus.

**Two things this does not license.** It does not license a *rank* veto — a question that stays a
hit but drops from rank 1 to rank 4 is not a regression under `hit`, and if that matters it is a
different, separately committed clause. And it does not license re-running until the diff comes out
clean: the artifact is captured once per configuration, and G1 already pins that a question does not
change its answer for reasons that are not retrieval (`docs/STATUS.md:312` § *Is the evaluation
reproducible?*).

---

## Gate 1 — PPR (`graph_channel = "ppr"`)

### What this gate decides — stated because the two gates below are not parallel **[new]**

**Gate 1 licenses building a PPR prototype. It does not decide a default.** PPR's default-on
decision is a *separate* gate, written into the plan that a Gate 1 pass authorises (see *What "not
scheduled" means*, clause 4), and that is where the simple-lookup veto applies — measured against
PPR, which does not exist today and cannot be measured now.

**Gate 2, by contrast, decides `mentions`' default directly**, because `mentions` is an input to an
already-licensed channel rather than a new channel of its own. The asymmetry is deliberate; it was
previously implicit, and a reader who assumed the two gates were parallel would look for a
simple-lookup measurement in Gate 1 that nothing here produces.

### Precondition — what must already be true before the question is asked

| # | Precondition | Why it is a precondition and not part of the measurement |
|---|---|---|
| P1 | G3 has landed and G5's `expand` channel is built | There is nothing to compare against otherwise |
| P2 | **`expand` passed G5's gate and ships default-on** **[new]** | APPROACH §9 asks whether *"expansion's multi-hop recall@k sits ≥ 5 points below the golden set's **channel-reachable ceiling** — the share of multi-hop questions whose evidence lies within 2 logical hops (§4A's metric) of the fused seeds, **minus what §3's membership exclusion forbids the channel to return**"* (`PINAKES_APPROACH.md:403`, in full — the clause after the dash is the definition of the term, and the probe implements it through `exclude_membership: bool = True`, `reachable_ceiling_probe.py:270`). **As written, that is satisfied most easily by an expansion that does nothing at all** — a channel that fails to improve anything sits furthest below the ceiling, and would therefore license PPR on the strength of its own failure. That is an assertion satisfied by something other than the property it names. If `expand` did not pass, the finding is *"graph structure does not help this corpus"*, and the response is a corpus or a different channel design, never an escalation to a more expensive one |
| P3 | The channel-reachable ceiling has been measured **on the same corpus, at the same HEAD, in the same run** as the expansion result | Two numbers measured at different commits do not have a gap between them |
| P4 | A per-query latency budget for PPR is **written down before the measurement** | See clause 5. A threshold chosen after seeing the number is not a threshold |
| P5 | **The per-kind edge census is on record, and the metadata side is not empty** **[new]** | See *The corpus the measurement needs*. On the only realistic corpus that exists, three of G3's edge kinds derive **zero** edges and PPR's non-chunk seeds are half-absent. A gate run without the census cannot tell a null result from an absent input |

### The measurement that would justify it

Five quantities, reported together, from one run.

**`tools/reachable_ceiling_probe.py` does not emit a ceiling and does not emit a percentage.** It
emits six counts (`Report.as_dict`, `tools/reachable_ceiling_probe.py:657-667`; `_render`,
`:889-898`): `multi_hop_questions`, `failing`, `liftable`, `at_seed_only`, `beyond_depth`,
`membership_only`. **You compute the ceiling. The formula is written here so that two implementers
cannot derive it two ways** — and they would, because whether `at_seed_only` is subtracted is the
difference of the whole finding on demo-kb, where two of the three questions the probe called
reachable had traversed no edge at all.

```
reach    = liftable − at_seed_only          # questions a channel would have to REACH, not re-rank
ceiling  = (multi_hop_questions − failing + reach) / multi_hop_questions
achieved = expand's multi-hop recall@k, same corpus, same HEAD, same run (P3)
gap      = ceiling − achieved               # in percentage points
```

**`at_seed_only` is subtracted, and this is not optional.** The probe counts at-seed questions
*inside* `liftable` deliberately — *"§9 says 'within 2 logical hops' and zero is within two"*
(`:775-782`) — and reports them separately for exactly this reason. An at-seed question is a
re-ranking, not a reach; a ceiling built on them measures the retrieval funnel.

**A reconciliation check that must pass before the gap means anything** **[new]**: the probe's
`multi_hop_questions − failing` must equal the evaluation's multi-hop hit count on the same run. The
two use different code to decide the same thing — the probe's per-hop `lands_today` (`:741`) and the
eval's per-question `hit`. They agree on demo-kb (18 − 1 = 17, against `by_kind["multi-hop"] =
0.9444` = 17/18, `tests/demo-kb/eval/baseline.json`). If they disagree on the measurement corpus,
**the instruments disagree and the gap is not computable** — stop and reconcile; do not pick one.

| Quantity | How |
|---|---|
| **the gap** | `ceiling − achieved`, by the formula above. State the four counts you derived it from, and state explicitly that `at_seed_only` was subtracted |
| **the beyond-2-hop count** | `beyond_depth`, a **count**. Questions whose every missed hop is unreachable at `DEPTH = 2` but reachable at `FAR_DEPTH = 6` (`:143`, `:146`, `:743-744`). APPROACH §9: *"if it dominates, the gate is blind to exactly what PPR's diffusion could reach"* |
| **the membership-only count** | `membership_only`, a **count**. Reachable **only** through membership edges, which §3 forbids the channel to return. APPROACH §9: *"if it dominates the gap, revisit the §3 exclusion before implementing PPR, because that is the cheaper remedy"* |
| **the at-seed count** | `at_seed_only`, already reported by the probe. Subtracted above; reported raw as well, because it is the single best evidence that a "ceiling" is a funnel artefact |
| **the per-kind edge census** | how many edges each of the seven kinds derived on this corpus (P5). **No tool prints this today** — it is derivable from `derive()`'s own structures (`:198-260`: `heading_hub`, `dir_hub`, `tag_hub`, `authored`, `by_doc`). Add it to the probe's `--json` or commit the script beside the report; do not hand-count |

> **`liftable`, `beyond_depth` and `membership_only` are mutually disjoint.** `_summarise` assigns
> each failing question to exactly one of them through an `elif` chain (`:772-786`). They are **not**
> shares of one population and they do not sum with the gap. Every clause below relating them is
> therefore a **ratio between disjoint counts**, and must be reported as one — "the beyond-2-hop
> *share*" is the wording APPROACH §9 uses and it is misleading about the arithmetic.

### The gate

PPR is **considered** — a prototype is licensed, not a default (see *What this gate decides*) — only
if all of:

1. **P2 holds.** `expand` is licensed on.
2. **`gap ≥ 5 percentage points` *and* the gap corresponds to `≥ 3 questions`.** **[threshold]** —
   the percentage alone is not a threshold on a small class: on the demo KB's 18-question
   `multi-hop` class, 5 points is **0.9 questions**, so a single residual question would pass it.
   The `≥ 5 points` half is APPROACH §9's; it occurs exactly once in the repository
   (`PINAKES_APPROACH.md:403`) with no derivation anywhere, and this file does not invent one — it
   adds a resolution floor so the clause cannot be carried by one question. The floor is deliberately
   **below** the graph release's own `≥ 7` precondition (`docs/STATUS.md:383`) only because that one
   gates a `schema_version` bump and a forced rebuild for every KB in existence, and this one gates
   writing a prototype. **Say that when you record it**, or the next reader reads the looser number
   as a loosening. **This clause and P2 together impose a floor on the corpus itself** — see *A
   quantitative requirement the qualitative properties do not imply*, and measure it with the probe
   before `expand` is built, not after.
3. **`beyond_depth < 0.5 × reach`.** **[threshold]** **[new]** — above that, the 2-hop bound is a
   constraint comparable in size to the channel, and the gate is partly blind to what PPR's
   diffusion would reach. APPROACH §9 says to *weigh* this number; making it a clause is what turns
   weighing into a decision procedure, and a clause with no number is the same weighing with a
   number beside it. **The cheaper move is already in hand:** the probe computes `FAR_DEPTH = 6`
   reachability in the same run, so `beyond_depth` **is** the answer to "what would a deeper walk
   reach" — no second probe run is needed. What is needed is the decision that raising `expand`'s
   hop bound is the honest next change. It is cheaper than PPR by every measure.
4. **`membership_only < 0.5 × reach`.** **[threshold]** **[new]** — above that, revisit §3's
   membership exclusion before implementing PPR. APPROACH §9 already says this; it is a clause here
   for the same reason.
5. **a latency budget is stated and met** **[new]**. PPR is power iteration over the edge list on
   **every query** (APPROACH §4B, `:205-209`). `expand` is a bounded per-depth loop; PPR is not
   bounded by the frontier. Without a stated budget, "it helps" licenses an unbounded per-query cost
   against a design that measures 2.25 ms/query for the whole vector tier (`docs/STATUS.md`
   § *Measured numbers*). **[threshold]** Propose: PPR's added per-query latency, stated as a
   multiple of `expand`'s, committed before the run.
6. **P5 holds, the census is on record, and no clause above is carried by an edge kind that derived
   zero edges.** **[new]** — see the corpus section.

**Why 0.5 in clauses 3 and 4, and why it is a proposal.** It is the point at which the excluded
population is half the size of the population the gate is built on; past that, what the gate cannot
see is comparable to what it can, and calling the gate's reading "the" finding overstates it. No
measurement supports 0.5 specifically, and none can before the run — that is the nature of a
committed threshold. **The planner takes it to the user, and it is on record either way.** What is
not acceptable is the previous wording, *"does not dominate"*: under it a null result and a decisive
one both pass, at the reader's discretion, in a file whose closing rule is *"Thresholds are
committed before the run."*

### Evidence that refuses it

| Signal | Threshold | Reading |
|---|---|---|
| `expand` regressed `simple-lookup` | any question lost, by the per-question veto above | **Then `expand` did not pass G5 and P2 is false.** The finding is about `expand`, not about PPR. The veto *against PPR* is evaluated at PPR's own default-on gate, which this file does not specify because PPR does not exist |
| the gap is below clause 2 | `< 5 points` **or** `< 3 questions` | Expansion suffices. APPROACH §9's own words: *"below-ceiling-but-close means expansion suffices"* |
| the beyond-2-hop count is large | `beyond_depth ≥ 0.5 × reach` | Raise `expand`'s hop bound and re-read clause 2. Cheaper, and it isolates the variable. The probe has already measured what a depth-6 walk reaches |
| the membership-only count is large | `membership_only ≥ 0.5 × reach` | Revisit §3's exclusion. Cheaper, and it may be the actual defect |
| the at-seed count is large | `at_seed_only ≥ 0.5 × liftable` | The ceiling is an artefact of the retrieval funnel. Fix the corpus or the funnel, not the channel. (This is why `reach` subtracts it — the clause is a second, louder guard on the same fact) |
| the gap clears clause 2 but is carried by questions only authored edges reach | the without-authored run alone fails clause 2 | Same circularity guard as G5's two runs. A gap only visible with authored edges is evidence a human's links help. **And on the RFC corpus `authored` is the strongest edge kind while its weight is under an open re-decision** — `plans/20260729_0256-links-and-graph.md:525-540`, and [`20260804_1016-graph-remainder-reentry.md`](20260804_1016-graph-remainder-reentry.md) C8 |
| an edge kind the reading depends on derived **zero** edges | any of the seven at 0 in the census | Not a refusal by itself; a refusal of the **generalisation**. The result is a claim about the kinds that were present, and only those. Write the restricted sentence beside the number |
| `scipy.sparse` turns out to be needed | — | Not a refusal, but a **core-dependency decision that must be taken by the user, not absorbed**. APPROACH §4B leaves it to profiling (`:208-209`); `CLAUDE.md`'s *"core dependencies stay light"* means it cannot be decided inside the increment |

### The corpus the measurement needs

**The RFC corpus now exists** — `pinakes-corpus-rfc`, 300 documents, built 20260804 08:00,
`docs/STATUS.md:342`. What follows is no longer a specification for a corpus somebody might build;
it is a checklist against a corpus you can measure — **and it does not currently pass all of it.**

`tests/demo-kb` cannot produce any of the quantities meaningfully, for three reasons:

* **no tags and one flat directory**, so exactly one derived edge kind crosses a document boundary
  — every reachability number there is a claim about one directory (`docs/STATUS.md:383`);
* **`candidates_per_source = 30` is applied *per source*** — `src/pinakes/search.py:333` (lexical)
  and `:340` (vector) — against a **60-chunk** index (`sqlite3 tests/demo-kb/.pinakes/index.db
  'select count(*) from chunks'` → 60, over 30 active documents). So up to 30 + 30 = 60 of 60 chunks
  reach fusion: the funnel already returns every document and the at-seed count swamps the ceiling.
  **The rule for sizing a replacement corpus is `chunks ≫ sources × candidates_per_source`, not
  `≫ candidates_per_source`** — a factor of the number of retrieval sources, which is the sort of
  error that sizes a corpus half as large as it needed to be. (`docs/STATUS.md:383` states this as
  *"30 against ~30 chunks"*; the figure is wrong and the conclusion is right. It is the planner's to
  correct, independently of this file);
* **17 of 18 multi-hop questions already pass** (`docs/STATUS.md`), so there is nothing for either
  channel to improve.

#### A quantitative requirement the qualitative properties do not imply **[new]**

**P2 and clause 2 conjoin into a corpus headroom floor that nothing above states, and it is
measurable with the probe alone — before `expand` is built.**

In questions rather than percentage points, the gap is
`reach − (the questions expand actually lifted)`. P2 requires `expand` to have passed G5's gate,
whose lightest row is `r = 0 / i = 5` — five improvements
(`plans/20260729_0256-links-and-graph.md:690-701`). Clause 2 then requires the gap to survive
*after* those five, on the same run (P3). So:

```
reach  ≥  5  +  max(3, ⌈0.05 × multi_hop_questions⌉)
```

— **≥ 8 on an 18-question multi-hop class, ≥ 8 on a 60-question class, ≥ 10 on a 100-question one.**

**Measure `reach` with the probe before `expand` is built.** If it is below that floor, **the PPR
gate is structurally unreachable on this corpus** — not "PPR does not help", but "this corpus cannot
be asked". Record that and stop. It is a complete outcome, it costs one probe run, and it is
available *years* earlier than the alternative, which is discovering it after `expand` has shipped.

Two caveats on the constant, stated rather than hidden: it assumes `expand` lifts questions the
probe called reachable, one improvement per question, and that it regresses none. Both are
idealisations — `expand` could improve a question the probe missed, or lift one and regress
another — so the floor is approximate. **The requirement does not depend on the constant**; it
depends on there being one, stated before the corpus is chosen rather than after the gate fails.

#### What the RFC corpus gives, and what it does not **[new]**

| Property the gate needs | On `pinakes-corpus-rfc` | Consequence |
|---|---|---|
| Size past the funnel | **106 806 chunks** over 300 documents | Passes by three orders of magnitude. Also **2× past the NumPy vector tier's 50 000 threshold**, and `pnk doctor` says so — a PPR latency budget (clause 5) would be measured on a corpus already at the tier ceiling |
| Directories that connect documents | 74 directories, **median 1 document** | `co-located` is **weak**; most directories connect nothing |
| Tags that connect documents | 585 keywords, largest bucket 34, **assigned by the RFC Editor**, not by an agent | `shared-tag` is **strong** and third-party-chosen — which makes an attribution to it a *stronger* claim than on the demo KB, not the weaker one the plan assumes |
| Headings | **0 of 106 806 chunks carried a `heading_path`**, on the corpus measured 20260804 | `in-section`, `parent` and `child` derived **zero edges**. The cause was *not* a Markdown-shaped grammar failing to match RFC section numbering, which is what was first recorded: `chunk.py` dispatched on **source type** and every type but `markdown` took the plain-text path, so no grammar ran at all. **0.13.0 shipped `[chunking] headings = "numbered"` and `tools/build_rfc_corpus.py` stamps it**, so a corpus rebuilt today carries heading paths — ⚠️ **the heading-coverage floor this gate refuses on must therefore be re-measured before it can refuse anything** |
| Authored links | 391 links, 53.3% of documents, median out-degree 1, **one hub of 86** | Strong — and the premise under `authored`'s 2.0 undamped weight is falsified by it (`plans/20260729_0256-links-and-graph.md:525-540`) |

**The heading finding changes this gate, not only G3's.** APPROACH §4B's personalization vector has
two parts, and the non-chunk part is: *"at most 5 nodes from the metadata side of the graph,
weighted by match score and damped by node specificity (1/chunk-count). Without the `[ner]` extra
there are no entity nodes — **tag and heading nodes play the phrase-node role**"*
(`PINAKES_APPROACH.md:189-192`). On this corpus **there are no heading nodes at all**, so PPR
without `[ner]` seeds its metadata side from tags alone — **half the input the recipe specifies.**

**So the second requirement PPR adds that `expand` does not** **[new]** is now measurable and
sharper: the corpus must have a **non-trivial metadata side on both legs the recipe names.**

* **[threshold]** *Tags:* enough distinct tags that the 5 non-chunk seeds are selective — propose
  **no single tag covering more than 20% of documents**, and at least 5 tags matching a typical
  query. The RFC corpus **passes** (largest bucket 34 of 300 = 11%).
* **[threshold]** *Headings:* **at least 50% of chunks carrying a non-empty `heading_path`.** The
  RFC corpus scores **0%** and **fails**.

**What Gate 1 does when a metadata leg derives nothing — decided here, before the run, not after:**

1. **The honest default is to refuse to run Gate 1 on this corpus until the chunker recognises the
   corpus's headings.** (`open-corrections` item 3 is the detection half; a grammar for RFC section
   numbering is a separate chunking decision with its own eval, and neither is a step inside this
   run.) Measuring PPR against half a personalization vector and recording the number as "PPR's
   result" is the same defect P2 exists to catch, one level down: an assertion satisfied by
   something other than the property it names.
2. **If it is run anyway**, the result is recorded as *"PPR with tag-only non-chunk seeding, heading
   nodes absent"* — in the headline, not a footnote — and it licenses a prototype for **that
   configuration only**. It is not evidence about PPR as APPROACH §4B specifies it.
3. **Never** read a null result on a corpus with zero heading nodes as "PPR does not help". It is
   "PPR with half its metadata seeds did not help here".

### A dependency that changes the gate if the template release lands first

`docs/graph/PINAKES_APPROACH.md:198-203`: under the `sqlite-vec` tier only the vector scan's top-N
carry cosine scores, which is *"precisely the top-k-only seeding HippoRAG 2 warns against"*, and
all-chunk seeding *"must be re-evaluated on that tier, not assumed."*

**So a PPR gate passed on the NumPy tier does not license PPR under the `sqlite-vec` tier.** If the
template release ships that tier ([`20260804_1016-template-release.md`](20260804_1016-template-release.md) § T6 — a sibling
scratchpad proposal, not a repository plan), this gate acquires a second leg: the same measurement
on the vec tier, or an explicit statement that PPR is NumPy-tier-only and what happens to a KB above
the threshold. **This is no longer hypothetical**: the RFC corpus is already 2× past the 50 000
threshold, so the realistic corpus is exactly the population that would land on the vec tier.

---

## Gate 2 — the `[ner]` extra and `mentions` edges

### Precondition

| # | Precondition | Why |
|---|---|---|
| N1 | G3 has landed | `mentions` is an edge kind; there is no edge table otherwise |
| N2 | **A channel is licensed on** **[new]** | APPROACH §9 says *"the active channel gains from them."* If no channel is active, `mentions` edges are inert by construction and the gate is unmeasurable — it would return "no change" and could be read either way. **Name the channel in the result** |
| N3 | **Two sync-time budgets are stated before the measurement, because there are two costs** **[new]** | §9 says *"sync time acceptable"*, which is not a threshold — and a *single* budget is not one either. §3 specifies that entity *"edges [are] hash-diffed incrementally like everything else in sync"* (`PINAKES_APPROACH.md:135`), so the standing cost is one model load plus NER over the **changed** documents, while the whole-corpus pass is a **first-sync-or-rebuild** cost. The two differ by roughly the corpus size, and whichever the measurer happened to run would decide whether the budget was met — the post-hoc-threshold failure this file exists to prevent, arriving through the denominator instead of the numerator. **State a cold budget (full rebuild, same corpus) and a warm budget (incremental, N documents changed, N stated), both as multiples of the same runs without `[ner]`, both committed before the run** |
| N4 | **The determinism question is answered before anything is derived** **[new]** | See below. It is the largest unpriced cost in the proposal |
| N5 | **The corpus's bridging population is measured, not assumed** **[new]** | See *The corpus the measurement needs*. `mentions` is justified as the class that bridges *unrelated* documents; if the corpus has no unrelated-but-entity-sharing documents, the measurement has no subject and a null result means nothing |

### N4 in full — the cost APPROACH §9's gate does not price

`mentions` edges are **derived by a model**. Everything else in the edge set is derived from the
document's own structure and is a pure function of the corpus. Three consequences, none of which is
in the gate as written:

1. **A model version change silently changes the edge set**, and therefore retrieval. Pinakes
   already has the shape for this — `documents.extraction_fingerprint` (`src/pinakes/store.py:52`)
   and the coherence refusal that names a rebuild (`docs/DESIGN.md` §3 `:245`, §4.4 `:380-386`) — but applying it to
   edges means **another index field and another refusal path**, which is `schema_version` work, not
   an extra. A `schema_version` bump means a rebuild for every KB in existence and no migration, by
   invariant. **An "extra" cannot contain that.**
2. **`tools/eval_reproducibility_gate.py` (G1) measures whether a question can change its answer for
   reasons that are not retrieval.** A model-derived edge set is a new such reason, and one that
   varies across *machines* as well as rebuilds. G1's CI job already diffs per-question outcomes
   between `ubuntu-latest` and `macos-latest` (`.github/workflows/ci.yml:230`, `:312-315`); a NER
   model that is not bit-identical across platforms would surface there as a reproducibility failure
   **attributed to the wrong cause**.
3. **The extra is not the whole cost.** APPROACH §3 is explicit that LinearRAG's wins come from a
   whole system — transformer-scale NER (a 440 MB spaCy model), sentence-level embeddings of the
   entire corpus, and query-gated spreading activation — and that *"no published ablation isolates
   the edges alone"* (`:129-133`). The gate must therefore measure the edges alone, which is the
   thing no published work has done.

**A pinned model is necessary and not sufficient.** Pinning makes the edge set reproducible *for one
pinned version*; it does not decide what happens when the pin moves, which is the schema question in
(1). **Answer it before deriving a single edge**, because the answer may be "this is a
`schema_version` bump and a coherence field", which changes what the increment is.

### The measurement that would justify it

On the licensed channel (N2), the same golden-set matrix G5 runs, with `mentions` edges **on** and
**off**, everything else frozen:

| Quantity | How |
|---|---|
| `simple-lookup` movement | **the veto class. Report it first, by the per-question artifact**, not by `compare()` — see *How the veto is checked*. Name the ids of any question that stopped being a hit |
| multi-hop movement | per-question, exact one-sided sign test on discordant pairs — the same instrument as G5's gate, for the same reason (paired binary before/after on the same questions is McNemar; "net +N" is a different quantity). **State the class size and which `i`/`r` rows it admits**: a row needs `i + r` discordant questions, so `r=5 / i=13` needs 18 |
| every other class | per-class, at `compare()`'s tolerance — the right instrument here, because these classes carry no veto and a sub-tolerance move is genuinely noise |
| sync wall-clock | cold **and** warm, on the same corpus, against N3's two stated budgets |
| the new-bridge count | `mentions` edges derived, **and the number of document pairs they connect that no other edge kind connects**, computed against the same per-kind census Gate 1 requires (P5), on the same run |

### The gate

`mentions` defaults **on** only if all of:

1. **`simple-lookup` does not regress — zero questions lost, by the per-question artifact.** Hard
   veto. This is the clause `compare()` cannot enforce above 50 questions in the class.
2. the sign test on multi-hop discordant pairs gives p < 0.05, on the licensed channel, with the
   admitted `i`/`r` rows enumerated before the run.
3. no other class regresses beyond `compare()`'s tolerance.
4. cold **and** warm sync wall-clock are within N3's two stated budgets.
5. **the new-bridge share clears a committed floor** **[threshold]** **[new]** — propose: **≥ 25% of
   the document pairs `mentions` connects are connected by no other edge kind, and ≥ 20 such pairs
   in absolute terms.** The percentage alone is satisfiable by a corpus where `mentions` connects
   four pairs and one of them is new; the absolute floor is what stops that. APPROACH §3's entire
   argument for `mentions` is that it is *"the one free edge class that bridges unrelated
   documents"* — if the bridges it adds are between documents already connected by `co-located` or
   `shared-tag`, it is not doing the thing it was proposed for, whatever the recall number says. The
   result would be a re-weighting, and a re-weighting does not need a 440 MB model download.
6. N4 is answered and its cost is paid in the same increment.

> **A trap in clause 5 on the corpus that exists** **[new]**: on the RFC corpus `co-located` is weak
> (median 1 document per directory) and `in-section`/`parent`/`child` derive **zero** edges. So the
> set of already-connected pairs is small, and the new-bridge share is **inflated by the absence of
> the other kinds** rather than by `mentions`' reach. Report the census beside the share and state
> which kinds were present when it was computed. A 90% new-bridge share against three absent kinds
> and one weak one is not the same finding as 90% against a full edge set — and it is the direction
> that flatters the extra.

### Evidence that refuses it

| Signal | Threshold | Reading |
|---|---|---|
| `simple-lookup` regresses | **one** question, by id | Hard veto |
| the improvement is carried by edges duplicating `co-located`/`shared-tag` | new-bridge share or count below clause 5's floors | The proposal's own premise is falsified. `[ner]` was justified as the class that bridges *unrelated* documents |
| the new-bridge share clears the floor only because other kinds derived nothing | any kind at 0 in the census | Not a refusal; a refusal of the **attribution**. Re-state the finding restricted to the kinds present, and say the share is an upper bound |
| the model is not reproducible across platforms | any per-question difference in G1's ubuntu/macos diff attributable to the edge set | G1's CI job goes red and the cause is the edge set. Refuse until pinned in a way that survives it |
| an SLM would be needed instead | — | **Stop.** APPROACH §3 names this boundary explicitly (`:141-147`): MiniRAG shows a 1.5–4B *local* model builds a useful entity layer, free in euros but LLM extraction all the same, *"which R1 as written forbids at any version."* That is a conscious amendment of R1 to be argued **with the user**, never a silent reinterpretation |
| the licence or size of the pinned model is unacceptable | — | Record it and stop. `plans/20260801_0749-realism-corpus.md:156` sets the precedent: *"Precondition — settle the licence before fetching anything"* |

### The corpus the measurement needs

The same corpus as PPR, plus one property PPR does not need: **entity-bearing prose whose entities
recur across documents that share no directory and no tag.** That is the exact population `mentions`
exists to bridge, and if the corpus has none, the measurement has no subject.

**[threshold]** **N5 makes this measurable before the model is ever downloaded.** Count the document
pairs that share no directory and no tag but *do* share a capitalised multi-word surface form
occurring in both — a short regex approximation of what NER would find, over the corpus you already
have. **Propose a floor of 20 such pairs.** If the approximation finds none, spaCy will not find
enough either, and the gate is unreachable on this corpus. **That is a complete outcome, and it
costs one script and no download** — which is the same shape as the graph release's own precondition
being measured before its schema bump.

`tests/demo-kb` fails this by construction — thirty short, topically disjoint synthetic documents,
written by one author, in one directory. Any entity recurrence in it is that author's vocabulary,
and the questions are that author's too.

**The RFC corpus is a better subject and is not obviously a sufficient one.** 300 RFCs share an
enormous entity vocabulary (protocol names, header fields, working groups) — but they also carry 585
editor-assigned keywords, so a large fraction of entity-sharing pairs is *already* connected by
`shared-tag`. That is precisely clause 5's population, and it is why N5 must be measured on this
corpus **before** the extra is built, not after.

---

## What "not scheduled" means operationally

1. **Neither gets a build plan, an increment, or a numbered item.** **Two entries exist and are
   deliberate:** `docs/STATUS.md:260`'s roadmap row (*"each eval-gated, not scheduled"*) and
   `docs/graph/PINAKES_APPROACH.md:418`'s §10 row, which maps research findings to releases rather
   than scheduling them (§10's own preamble, `:413`: *"Extends GRAPH_RAG.md's R-table into a build
   order"*). Nothing else is written until a gate passes. **If a third entry appears, that is the
   drift this rule exists to catch** — the rule was previously stated as if already satisfied, which
   is how a rule stops being checked.
2. **Neither gets a version number**, by `CLAUDE.md`'s naming rule: they are *the graph release,
   staged*, and the name stays until the final cut. `schema_version` numbers are schema numbers and
   are not covered by that rule.
3. **The gate outcome is recorded whichever way it goes**, dated `YYYYMMDD HH:MM`, in
   `docs/STATUS.md`, with the counts **and the per-kind edge census**. A refusal is a result and is
   worth as much as a pass — the graph release's own negative measurement is the precedent
   (`docs/STATUS.md:383`), and it is there with its numbers.
4. **A plan is written after the gate passes, never before.** The measurement decides whether there
   is work; the plan then decides how. For PPR, that plan carries the default-on gate this file
   deliberately does not specify.
5. **Thresholds are committed before the run.** Every **[new]** clause exists because a number chosen
   after seeing the result is not a gate; every **[threshold]** exists because a clause with *no*
   number is not one either — *"does not dominate"* is satisfied by a null result and a decisive one
   alike, at the reader's discretion. This project has already paid for the lesson once: the graph
   release's precondition was written down *before* the probe, which is why its failure cost one
   release instead of a forced rebuild for every KB in existence.
6. **A gate a null implementation satisfies is the defect to hunt hardest.** P2 exists because §9's
   PPR gate was one. Clause 2's question floor exists because a percentage on an 18-question class
   was another. P5 and clause 6 exist because an edge kind that derives nothing satisfies every
   clause that does not name it. **Before recording any result here, ask what a channel that did
   nothing would have scored** — and if the answer is "it would have passed", the clause is wrong,
   not the channel.
