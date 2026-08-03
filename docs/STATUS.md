# Status — what ships today

**Latest release: 0.7.1** · last reviewed 20260803 22:23

> **This file is the only place in the repo that says what is built.** Every other doc describes
> *how* something works or *why* it was designed that way, and links here for whether you can use it
> yet. When an increment lands, flip its row below — no other doc should need a version edit.
>
> "Shipped" below means **released**; an increment merged to `main` but not yet in a release says so
> explicitly. Installing from a tag and installing from `main` are different answers to "can I use
> this yet", and this file is where that difference has to be visible.

---

## The surface you can use today

| Command | State | Notes |
|---|---|---|
| `pnk init` | shipped | one template (`notes`); `--ci` writes the workflow (0.3.0) |
| `pnk sync` | shipped | `--rebuild`, `--scan-links`, `--sidecars-only`, `--index-only`, `--extract`, `--force`, `--clear-cache[=paid]` |
| `pnk search` | shipped | BM25 + vector + rerank, metadata filters, `--json` |
| `pnk doctor` | shipped | environment, coherence, orphans, links, hooks, cache |
| `pnk install-hooks` | shipped | the three-hook split; all three force `--extract=pypdfium2` (0.3.0) |
| `pnk serve` | shipped | MCP: `pinakes_search`, `pinakes_get`, `pinakes_links`, `pinakes_list_kbs` |
| `pnk budget` | shipped 0.3.0 | I6b. Day/month/operation spend, `--resolve` for an unknown outcome |
| `pnk links` | shipped 0.5.0 | L4. What a document connects to and what connects to it: `--rel`, `--direction`, `--depth`, `--query`, `--json` |
| `pnk link` | shipped 0.6.0 | L6. Writes one `links[]` entry into the source document's own sidecar. Targets: a `pnk://` URI, `<alias>:<path>`, or a path in this KB |
| `pnk ask --deep` | **not built** | the deep release |

| Capability | State | Notes |
|---|---|---|
| Markdown / text / code ingest | shipped | |
| **PDF ingest, free path** | shipped | `pypdfium2`, needs `pinakes[pdf]`. **Off by default — see the caveat below** |
| Extraction cache | shipped | `.pinakes/cache/extract/` |
| Page provenance (`page_start`/`page_end`) | shipped | in the index since 0.2.0, and surfaced in results on both surfaces since I8 |
| Extraction quality scoring | shipped | `make pdf-eval` against `tests/pdf-corpus/` |
| **PDF ingest, paid path** (scanned PDFs) | shipped 0.3.0 | I7b. `claude-vision` is a real extractor, **measured against the live API 20260729** — 1.000 on every metric over the synthetic scanned stratum, where the free path scores 0.000 ([DESIGN §9](DESIGN.md#9-known-risks)) |
| Budget estimator, caps, window aggregation | shipped 0.2.2, **inert** | I6a. The pure logic only — nothing calls it, so nothing can spend |
| Budget ledger, `pnk budget`, the accountant | shipped 0.3.0 | I6b. `ledger.jsonl`, the reservation/outcome protocol, and I6a's decisions read from it — now driven by I7b's extractor |
| `path:page` citations | shipped | I8. `docs/paper.pdf:p7` / `:p7-8`, on the CLI and MCP alike; `pnk doctor` names the pages with no text layer |
| Cross-KB links (`pnk link`, `pnk links`, `pinakes_links`) | **built** — `pnk sync` records what other KBs link into this one (`--scan-links`), `pnk links` and `pinakes_links` traverse (0.5.0), `pnk link` authors, and `pnk doctor` reports link coverage as a ratio and resolves cross-KB targets (0.6.0) | the links release |
| Sidecar round-trip | **shipped** — `ruamel.yaml` in round-trip mode at YAML 1.2: comments, quoting, block scalars and blank lines survive a rewrite, and an unknown key's value is no longer reinterpreted | the links release |
| `sqlite-vec` tier, template ecosystem | **not built** | the template release |

⚠️ **0.3.0 is the first release that can spend money — and it will not, unless you ask it to.**
Every earlier version had no paid code path at all. The only one now is the `claude-vision`
extractor, and reaching it takes a deliberate act: `EXTRACTION_BACKEND_DEFAULT` is `pypdfium2`, so
a KB spends only when its manifest says `[extraction] backend = "claude-vision"` or a command
carries `--extract=claude-vision`, **and** a real `ANTHROPIC_API_KEY` is in the environment. Absent
any one of those, 0.3.0 behaves exactly like 0.2.2.

What stands behind that rather than merely asserting it: an enumerated allowlist
(`.paid-path-allowlist`) with four gates, the decisive one running the whole free path in a fresh
subprocess and asserting no paid client ever reaches `sys.modules`; every call reserved before it is
made and reconciled from the response's own usage; and caps that refuse rather than overspend.
Measured live on 20260729, the reservation over-reserved **11.5×** — wrong in the safe direction.
See [DESIGN §5](DESIGN.md#5-cost-control) and `pnk budget`.

Since I7a (0.3.0) that is enforced rather than asserted: `.paid-path-allowlist`
names every module permitted to import a paid client — one line since I7b — and four gates in
`check.sh` and CI hold it, the decisive one running the whole free path in a fresh subprocess and
asserting no paid client reached `sys.modules`. It found two real leaks the day it landed: both
`pnk doctor` and `pnk sync` reported a backend's availability by *loading* it, so a KB configured
for `claude-vision` imported `anthropic` on commands that cannot spend (fixed in the same
increment; no version ever shipped able to spend from them).

### Caveat: PDFs are off by default (but no longer silently)

`pnk init` stamps `include = ["**/*.md", "**/*.txt"]`, so PDFs need one manifest edit: add
`"**/*.pdf"` to `[sources] include` ([GUIDE](GUIDE.md#indexing-pdfs)). The generated manifest spells
out the glob and the extra it needs, and since 0.2.2 `pnk sync` names any file it skipped for want
of a pattern instead of reporting `0 indexed` and explaining nothing. It stays off by default
because `init` cannot see whether `pinakes[pdf]` is installed, and a glob stamped without it turns
every PDF into a failed document rather than a skipped one.

⚠️ **A template change reaches new KBs only.** The explanatory line above shipped in 0.2.2 and
appears in no KB created before it, and nothing today detects or reports that divergence — so existing KBs stay PDF-blind
permanently unless their owner edits the manifest by hand. That gap, and what to do about it, is
worked through in [KB-UPDATES.md](KB-UPDATES.md). Its `requires_pinakes` half is **built (G4), on
`main`, unreleased** — a manifest can now declare the oldest pinakes that can read it, so an
out-of-date build says so instead of reporting a typo. That closes the *diagnosis*, not this gap:
nothing yet detects template drift or adopts a new default into an existing manifest.

### Caveat: the `[light]` backend needs a manifest edit

`pnk init` always stamps `provider = "sentence-transformers"` — it cannot see which extra you
installed. On a `pinakes[light]` install, set `provider = "fastembed"` in **both** `[embedding]` and
`[rerank]` before the first sync ([GUIDE](GUIDE.md#choosing-a-backend)).

---

## v0.2 increment ledger

The build order is [`plans/v0.2.md`](../plans/v0.2.md). Each increment is a separate, bisectable
landing with its own tests.

| # | Increment | State |
|---|---|---|
| I1 | Extras, the extractor seam, core-only failure | shipped 0.2.0 |
| I2 | The synthetic hard-case PDF corpus and its generator | shipped 0.2.0 |
| I3a | Extraction core, pure — chars to ordered text | shipped 0.2.0 |
| I3b | The `pypdfium2` adapter, quality metrics, two fitted floors | shipped 0.2.0 |
| I4 | The extraction cache | shipped 0.2.0 |
| I5 | PDF chunking, page provenance, backend-aware sync (`schema_version` 2) | shipped 0.2.0 |
| I6a | Budget core, pure — estimator, reservation, `prices.toml` | shipped 0.2.2 (inert) |
| I6b | Budget I/O — ledger, prompt, `pnk budget`, hooks that cannot spend | shipped 0.3.0 |
| I7a | The paid-path allowlist gate and the invariant amendments | shipped 0.3.0 |
| I7b | The paid Claude-vision extractor — request shape, validation, retries | shipped 0.3.0 |
| I7c | The completeness audit, staging, all-or-nothing commit | shipped 0.3.0 |
| I8 | `pnk doctor` text yield, `path:page` citations on both surfaces, the three end-to-end traces | **landed 20260729 04:55**, unreleased |
| I9 | The verification audit (`docs/VERIFICATION.md` + its gate), the untested-check sweep, README extras, wheel-smoke assertions | **landed 20260729 05:29**, unreleased |

**Decided 20260728 17:52 — I6–I9 accumulate, and cut as one MINOR release.** `plans/v0.2.md`
assumed a single release at I9; 0.2.0 was instead released after I5, correctly, since I1–I5 was
complete, self-contained, user-visible work the project's rule forbids leaving in `[Unreleased]`.
The remaining increments are **not** the same shape: I6a, I6b and I7a are each explicitly partial —
the budget core is pure logic nothing calls, and I6b's own title is "hooks that *cannot* spend".
They therefore stay in `[Unreleased]` until paid extraction is genuinely usable (I7b) and safe
(I7c), and that lands as **one MINOR bump — never a 0.2.x patch**, since a KB that can spend money
is new capability, not a fix. Patch releases in between remain available for work that stands alone
(0.2.1, the documentation restructure, was exactly that).

**Re-argued 20260728 23:42, once I6b was actually built — the decision stands, on a different
reason.** Its original premise was "none adds a capability a user can reach". That is now false in
one place: I6b shipped **`pnk init --ci`**, which writes a working GitHub Actions workflow for a
free KB and is gated on nothing. Held anyway, and the reason is narrow enough to be worth stating,
because it is the only thing keeping this out of a release:

> **`pnk budget` cannot produce a non-zero result on any KB in existence, and no user can change
> that.** It reads a ledger nothing writes until I7b. The project ships honestly-limited surfaces
> elsewhere — `pnk search` reports `confidence: unknown` by default and says why — but that limit
> lifts the moment *a user* calibrates. This one lifts only when *we* ship an increment. Making it
> the headline of a MINOR would ship a command whose output nobody can affect.

**Superseded 20260729 by I7b landing — that reason has now expired, and one narrower one remains.**
A user with a key can run a paid extraction today, so `pnk budget` reports real numbers and nothing
in this release is structurally vacuous any more. What holds it is no longer honesty about an empty
command but **safety**: I7c adds the completeness audit and the all-or-nothing commit, without
which a partially-extracted document can land in the index as though it were whole. Shipping a
spender before the thing that makes its output trustworthy is the wrong order, and it is the only
remaining reason.

The trade is unchanged and still named: `pnk init --ci` waits, and a user who wants it today can
copy the workflow out of [CLI.md](CLI.md#pnk-init).

**Trigger — if I7c slips or is deferred, cut the paid-extraction release immediately**,
documenting the audit's absence plainly. This is a bet on I7c landing soon, not a standing policy,
and it expires if that bet stops paying. (Its *number* is assigned when it is cut, per the naming
rule below — naming a number here is exactly the habit that rule exists to stop.)

### Cut as 0.3.0 — 20260729 04:17

Every reason for holding had expired by the time I7c landed: the budget command was no longer
structurally vacuous (I7b gave it real numbers to report) and the audit that makes a paid
extraction trustworthy was on `main`. The remaining question was never about the code — pushing the
tag publishes to PyPI, which cannot be re-uploaded or truly withdrawn, so it took a human saying
yes. That yes was given on 20260729 and the release was cut the same hour.

**It is a MINOR, never a patch**, and the reason is the ⚠️ above: a KB that can spend money is new
capability. What shipped is I6a–I7c together — the budget core and its ledger, `pnk budget`, the
paid-path allowlist and its four gates, the Claude-vision extractor, and the completeness audit
with all-or-nothing commit — plus the live measurement behind every number in
[DESIGN §9](DESIGN.md#9-known-risks).

**What it deliberately did not include.** `path:page` citations were still index-only and not
surfaced in results; the release therefore read scanned pages it could not yet cite precisely. That
gap was named here rather than discovered by a user, and **I8 has since closed it** (landed
20260729 04:55, unreleased at the time of writing).

### The measurement run has been done — 20260729 03:17, €0.43

Steps (a)–(d) of [MEASUREMENT-RUN.md](MEASUREMENT-RUN.md), against the live API with
`claude-opus-5`, for **€0.43** — a tenth of the €4.23 worst case, which is itself a measurement of
how conservative the reservation is.

| What it settled | Result |
|---|---|
| Scanned quality — the reason the paid path exists | **1.000** char recall, order fidelity, word coverage; **0.000** junk. Free path: **0.000** on all four ([DESIGN §9](DESIGN.md#9-known-risks)) |
| The free-vs-paid delta on text-layer twins | Identical on 3 of 4. On a bordered table the paid path reads order **better** (+0.119) and adds **29% junk** ([§7.2](DESIGN.md#72-what-bypassing-layoutpy-on-the-paid-path-actually-costs)) |
| `PROMPT_TOKENS` | Measured 571 against an estimated 300 — **wrong in the unsafe direction**, now 700 |
| `PAGE_TOKEN_CEILING` | Measured ~1,574/page against a 6,000 ceiling. **Deliberately not lowered**: the corpus rasters are synthetic, and a real 300-DPI scan is the case they cannot represent |
| Reservation accuracy | Over-reserved **11.5×** on the first live call ($0.3515 → $0.0306). Safe, and exactly why reconciliation exists |
| The refusal branch | Fired for real. `headers-repeating.pdf` was refused twice, recorded as a document failure, and the other four extracted normally |

## The fixtures are now half recorded — 20260729 03:36, €0.26

The gap the measurement run left open is closed as far as it can be. Four branches — `happy`,
`short-slice`, `refusal`, `truncated` — carry bodies captured from the live API by
[`tools/record_claude_fixtures.py`](../tools/record_claude_fixtures.py). Every fixture now declares
its own `provenance`, so the set no longer makes one claim about a mixed collection
([the fixture README](../tests/fixtures/claude/README.md)).

The authored bodies were right about every branch's control flow and wrong about the response shape
in five ways no passing test could have revealed: the API returns the model **alias**
(`claude-opus-5`, not a dated snapshot), a text block carries `citations`, a response carries five
more top-level fields, `usage` carries seven more, and a refusal bills **1** output token rather
than 0. A sixth finding was a defect — a refusal arrives with a structured `stop_details` naming a
`category` and an `explanation`, and the extractor discarded both.

**What remains authored, permanently.** Ten fixtures encode the API *misbehaving* — a body that
violates the schema it was constrained to, a page array short of the slice, a leaked internal tag —
or a failure that cannot be induced without abusing a live service (429, 500, timeout). Each names
its own reason in `provenance.why_not_recorded`. This is not a backlog item: those bodies are
unobtainable by construction, and calling them "not yet recorded" would misdescribe them.

**One open question the recording raised.** `refusal-then-success` models a retry that has never
been observed to succeed — the same bytes refused twice with identical `stop_details`, which is
what a content-policy decision on fixed input should do. If that generalises, the refusal retry
spends a full input billing (~€0.04/slice) for nothing. It is n=1 on one document: enough to
record, not enough to change what the code spends.

✅ **The `0.3` collision is resolved — see [the naming rule](#release-roadmap)
below.** Unbuilt work no longer carries a version number anywhere, so nothing competes for `0.3.0`
and this release can be numbered whenever it is cut.

---

## Release roadmap

> # 🚫 Unbuilt work is named, never numbered
>
> **A version number belongs to a release when it is cut — never before.**
>
> Bodies of work that do not exist yet are referred to **by name**:
>
> | Name | What it is |
> |---|---|
> | **the graph release** | Structural edges, the expansion channel — each eval-gated |
> | **the deep release** | `pnk ask --deep` |
> | **the template release** | Template ecosystem, `pnk upgrade`, the `sqlite-vec` tier |
>
> **Never write `v0.4` for something unbuilt** — not in docs, not in `--help`, not in an error
> message, not in a code comment. Decided 20260729 00:09.
>
> **Why.** For months the docs used `v0.3` to mean the cross-KB links release. Then 0.2.2 shipped and
> the *next* MINOR was numerically 0.3.0 — so one number meant two different releases, and picking
> either one meant renumbering ~60 committed references, research records included. A number
> promised years ahead is a promise about ordering that the ordering itself keeps breaking. A name
> never collides, never needs renumbering, and says what the work *is* rather than when it arrives.
>
> Historical records (`CHANGELOG.md`, `docs/RETROSPECTIVES.md`, `plans/`, the dated research in
> `docs/graph/`) keep the numbers they were written with — they are records of what was decided at a
> time, and rewriting them would falsify that. Each carries a header note pointing here.

Rationale for the ordering is in [DESIGN §8](DESIGN.md#8-delivery-plan).

| Release | Adds |
|---|---|
| **0.2.0** ✅ | Free PDF ingest, extraction cache, page provenance in the index, extraction-quality scoring |
| **0.2.1** ✅ | Documentation restructure — one fact one home; three stale-claim fixes |
| **0.2.2** ✅ | `pnk sync` names files skipped for want of an `include` glob; budget core (inert) |
| **0.3.0** ✅ | Budget machinery, the opt-in paid Claude-vision extractor (I6–I7c) |
| **0.4.0** ✅ | `path:page` citations on both surfaces, `pnk doctor` text yield (I8); the verification table and its gate (I9) |
| **0.4.1** ✅ | A sidecar that will not parse is no longer overwritten by a freshly minted one, and no longer aborts the whole sync — data loss present since v0.1 |
| **0.5.0** ✅ *(the links release, interim)* | `pnk links`, `pinakes_links`, reverse-scan and the sidecar round-trip fix — no `schema_version` bump, so no rebuild. **The release cuts twice** (decision 27): this is the interim MINOR at L5b; the final cut is at L8, and the name stays in the unbuilt-work table until then. **L1 landed:** the partner corpus, sparse authored links in both, and the density gate. **L2 landed:** reverse-scan writes inbound rows and `kb_refs`, with a freshness window and `--scan-links`. **L3–L5 landed:** the bounded traversal core, `pnk links`, and `pinakes_links` on the MCP surface. **L5b landed:** `ruamel.yaml` replaces `pyyaml` in the sidecar, so a rewrite preserves comments, quoting and blank lines — and `country: NO` stops becoming `false` ([decision](../plans/decision-ruamel-yaml.md)). **L6 has since landed on `main`, unreleased:** `pnk link`, the authoring command — it goes out at the final cut, not in 0.5.0. **Next: L7** (`pnk doctor`'s link coverage), then L8 and that cut |
| **0.6.0** ✅ *(the links release, final)* | `pnk link` authors a link from the command line, and `pnk doctor` reports link coverage as **linked docs / total docs** and resolves each cross-KB target through its `[[links.kb]]` entry (L6–L8). Also `[kb] requires_pinakes` (G4) and the evaluation's tie-ordering fix (G1) — no `schema_version` bump, so no rebuild. **This completes the two-cut release** decision 27 describes: 0.5.0 was the interim MINOR at L5b, this is the final cut, and the name leaves the unbuilt-work table here |
| **0.7.0** ✅ | The evaluation grows a per-question artifact (`eval/outcomes.json`), stable question ids, a validated `kind`, and an empty golden set that skips with a reason instead of failing — plus the demo KB's golden set grown 41 → 74 with a `simple-lookup` control class (G2). **Its deliverable is a measurement:** the graph release's gate cannot be reached on this corpus, so G3 and G5 do not start ([above](#can-the-graph-releases-gate-be-reached--measured-20260801-1214)). No `schema_version` bump, so no rebuild |
| **0.7.1** ✅ | `[sources] include` can no longer walk out of the KB or write sidecars outside it — three defects live since before 0.5.0: a `..` pattern indexed files outside and minted sidecars beside them, an absolute pattern was a bare traceback, and a symlinked directory carried the walk out with no `..` anywhere. Plus a document reached by two legal spellings is now one document, and `tools/link_density_gate.py` survives a non-canonical root |
| *the graph release* | Structural edges, the expansion channel (`graph_channel`, default off), `schema_version` 3 — eval-gated. **⚠️ Blocked: its gate was measured on 20260801 and cannot be reached on this corpus** ([above](#can-the-graph-releases-gate-be-reached--measured-20260801-1214)) — 1 of 18 multi-hop questions fails where 7 were needed. Its three finished increments have all shipped: **G1** (reproducibility, and the tie-ordering defect it found) and **G4** (`requires_pinakes`) in 0.6.0, **G2** in 0.7.0. **What is left — G3, G5 and G6 — does not start**, and cannot until a corpus exists that can discriminate: `tests/demo-kb` has no tags and one directory, so exactly one derived edge kind crosses a document boundary, and the funnel already returns every document before any channel could reach further. **The unblocking work is a corpus, not code** ([`plans/realism-corpus.md`](../plans/realism-corpus.md)) |
| *the graph release, staged* | PPR graph channel, the `[ner]` extra — each eval-gated, not scheduled |
| *the deep release* | `pnk ask --deep` |
| *the template release* | Template ecosystem, `pnk upgrade` migrations, the `sqlite-vec` tier |

The order is a dependency order, not a schedule. Anything unreleased may be resequenced; only the
✅ rows are facts.

## Measured numbers

Re-measure and re-date these whenever retrieval or extraction changes; never carry one forward
unverified.

| Metric | Value | Measured |
|---|---|---|
| questions | 74 | 20260801 12:14, demo KB, `[light]` models |
| recall@5 | 0.939 | 20260801 12:14 |
| MRR | 0.881 | 20260801 12:14 |
| rerank precision | 0.849 | 20260801 12:14 |
| false-abstain | 0.015 | 20260801 12:14 |
| **false-confidence** | **0.25** | 20260801 12:14 — one no-answer question in four still gets a confident answer |
| NumPy vector tier | 2.25 ms/query at 50k×384, 77 MB resident | 20260725 13:49 |

Per class, same run: `lexical` 1.00, `simple-lookup` 1.00, `filter` 1.00, `no-answer` 1.00
(abstained correctly), `multi-hop` 0.944, `paraphrase` 0.75.

⚠️ **These numbers moved on 20260801 because the golden set grew from 41 questions to 74, not
because retrieval changed.** G2 added 20 `simple-lookup` questions and 13 single-KB multi-hop ones
and re-baselined once. `eval/baseline-pre-growth.json` preserves the 41-question figures with the
ids they covered, and re-scoring the committed per-question artifact over exactly those 41
reproduces every one of them **byte-identically** — so nothing already in the set moved. The
previous run of record was 20260729 03:23: recall@5 0.909, MRR 0.812, rerank precision 0.758,
false-abstain 0.03. **Those numbers had themselves moved for a non-retrieval reason** — the scorer
was wrong before them: a multi-hop question was scored as a single-shot search of its last hop's
query, `hops_followed` reached no metric, and recall@5 rose 0.879 → 0.909 when the class started
requiring every hop to land.

**Twice now the headline numbers have moved without retrieval changing.** Say which it was, in the
commit and here, or the next reader credits a scorer fix to the ranker.

**Paraphrase is still the only class with real room in it**, and the `multi-hop` class remains close
to ceiling even after tripling in size — 17 of 18. That is a fact about the corpus, not about the
questions: thirty short, topically disjoint documents make "retrieve 5 of 30" undemanding. Nothing
should be tuned against this corpus until it is larger and its documents are less separable —
which is now the binding constraint on the whole graph release, not a caveat
([`plans/realism-corpus.md`](../plans/realism-corpus.md)).

The false-confidence figure is fitted and scored on the same 74-question set (8 of them no-answer,
unchanged by G2's growth — so the calibrated thresholds were re-fitted after it and came back
identical), so treat it as a floor rather than an estimate. Publishing it is the point:
[DESIGN §4.2](DESIGN.md#42-escalation--free-path-first) commits to measuring the heuristic's cost
rather than assuming it away.

### Is the evaluation reproducible? — measured 20260801 00:35

The graph release gates on an exact per-question sign test, so it was worth knowing whether a
question can change its answer for reasons that have nothing to do with retrieval. The golden set
was run against the demo KB, a document edited, the index re-synced incrementally, then rebuilt,
then built again from scratch — comparing **per-question outcomes**, not aggregates, at each step.

| Comparison | Real `[light]` models | A low-dimensional tie-heavy fake |
|---|---|---|
| the same index, evaluated twice | identical | identical |
| an incremental sync vs `--rebuild` | identical | **1 of 41 questions differed** |
| `--rebuild` vs a from-scratch sync | identical | identical |

**The shipped models were reproducible, and only by luck.** 384-dimensional cosines almost never
tie exactly; underneath them every tiebreak in the pipeline resolved to `chunks.id`, the rowid,
which the schema says outright has no identity across rebuilds. So the property held because the
corpus did not exercise it, which is not a property at all.

Ordering is now total on `(documents.path, chunks.ordinal)` at the three places that decide it —
the vector array's row order, the BM25 cut, and hydration — plus a stable `argsort`, which covers a
fourth case the others do not: NumPy's introsort partitions over the whole array, so adding
documents reordered tied entries elsewhere in **500 of 500** random tie-heavy arrays.

**The numbers above did not move.** The real-model golden set scores byte-identically to the
committed baseline before and after, which is what a change that only breaks ties should do — and
is why this increment rewrites no baseline. Held by `tools/eval_reproducibility_gate.py` (a
`check.sh` gate and its own CI job, sweeping four kinds of corpus change),
`tests/test_search_reproducibility.py`, and a CI job that diffs per-question outcomes between
`ubuntu-latest` and `macos-latest` — the half a single machine cannot answer.

### Can the graph release's gate be reached? — measured 20260801 12:14

**No, on this corpus.** The graph release defaults its expansion channel on only if an exact sign
test finds enough multi-hop questions *improving*, and an improvement can only come from a question
that fails today. The precondition was: **at least 7 of the ~18 single-KB multi-hop questions fail,
and at least 7 of those are channel-reachable without authored edges.**

| | Required | Measured |
|---|---|---|
| multi-hop questions failing today | ≥ 7 | **1** |
| of those, reachable within 2 logical hops, **without** authored edges | ≥ 7 | 1 |
| of those, reachable **with** authored edges (records nothing, licenses nothing) | — | 1 |
| reachable but beyond 2 hops | — | 0 |
| reachable only through membership edges | — | 0 |

**So G3 does not start.** No `schema_version` bump, no forced rebuild for every KB in existence for
an edge table whose channel could never be licensed — which is the whole reason this measurement
was sequenced before the schema change rather than after it. G1, G2 and G4 are cut as a release of
their own.

Two findings sit behind that number, and both outlive it:

* **`tests/demo-kb` has no tags at all, and one flat directory.** With `mentions` cut, that leaves
  exactly **one** derived edge kind that crosses a document boundary — `co-located`, through a
  single thirty-way directory hub. `shared-tag` derives zero edges for want of any tag;
  `sibling`, `parent`/`child` and `in-section` are intra-document and cannot bridge two evidence
  documents by construction. Any future result on this corpus is a claim about one directory.
* **The retrieval funnel already sees the whole corpus.** `candidates_per_source` is 30 against
  ~30 chunks, so the vector channel returns essentially every document with a positive cosine and
  the pipeline then cuts to `final_k = 5`. A failing question here is a **ranking** failure, not a
  recall failure a channel could fix by reaching further. The probe reports an `at-seed` share
  separately for that reason: under a tie-heavy fake backend, two of three questions it called
  reachable were already among the fused candidates and had traversed no edge at all.

The thirteen new multi-hop questions were authored from corpus structure and **frozen before the
probe ran**. They are not re-authored to produce failures: fitting the question set to the edge set
is the circularity that cutting cross-KB questions removed once already, and it is undetectable
afterwards. Held by `tools/reachable_ceiling_probe.py`, whose own tests pin that it needs no schema
change and that its count moves when an edge kind is removed — a reachability probe answering
"reachable" for everything is the failure mode it exists to avoid.

## Published on PyPI

**[`pinakes` is on PyPI](https://pypi.org/project/pinakes/).** `uv add "pinakes[light]"` installs,
and needs **one manifest edit before it can sync**: `pnk init` stamps
`provider = "sentence-transformers"` whatever extras you have, so a `[light]` install fails with
*"the `sentence-transformers` backend is not installed"* until `provider` is changed to
`"fastembed"` — the edit [README.md](../README.md) and the [Guide](GUIDE.md#choosing-a-backend)
both call out. Verified 20260801 13:46 against **0.7.1** from the index (`uvx --refresh --from "pinakes[light]==0.7.1" pnk --version` → `pinakes 0.7.1`): `init` → edit → `sync` →
`search` returns the document. The earlier claim that it worked unedited was wrong.

| | |
|---|---|
| Published versions | **0.2.2, 0.3.0, 0.4.0, 0.4.1, 0.5.0, 0.6.0, 0.7.0 and 0.7.1.** 0.2.0 and 0.2.1 predate publishing and are **not** on PyPI, so pinning either fails. **0.4.0 and earlier can destroy a sidecar's permanent ULID** (see 0.4.1) — 0.4.1 is the first release without it |
| First upload | 20260728 17:16 UTC · latest 20260801 11:46 UTC (0.7.1) |
| Extras available | `st`, `light`, `pdf`, `claude` — all four |
| `requires-python` | `>=3.13` |

`PUBLISH_TO_PYPI` is now `true` (set 20260728 17:15 UTC), so **every tag publishes from here on**.
**Two caches sit between a successful publish and seeing it**, and both read as "the upload
failed": `https://pypi.org/pypi/pinakes/json` is CDN-cached and still named 0.6.0 minutes after
0.7.0's files were listed on `https://pypi.org/simple/pinakes/`, and **uv keeps its own index
cache** — `uvx --from "pinakes[light]==0.7.0"` reported the version unresolvable until
`--refresh`. Check `/simple/`, and add `--refresh` before concluding anything (20260801 12:43).
Tagging stays safe by construction: version/tag agreement, the build and an isolated wheel smoke
test all run before the upload step is reached.

Install lines are in the [GUIDE](GUIDE.md#install). Installing from git still works and remains what
you want for unreleased work sitting on `main`.
