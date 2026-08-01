# The links release and the graph release — implementation plan

**Status:** revised after adversarial passes 1 (22 HIGH), 2 (26 HIGH), 3 (24 HIGH), 4 (13 HIGH),
5 (3 HIGH), 6 (2 HIGH) and 7 (6 HIGH) on L1–L8 and G1–G6; then **seven passes on L5b alone**
(8, 8, 7, 6, 7, 7, 7 HIGH) plus an adversarial code review of the implementation (5 HIGH).
**L1–L5b have shipped in 0.5.0 and L5c is closed unbuilt** — its one refusal turned out to ship
with L5b. **L6–L8 are implementable; G1–G6 are not yet.**

> ## ⚠ 20260731 — L5b is split into **L5b** and **L5c** (decision 28)
>
> Three adversarial passes returned **8, 8 and 7 HIGH** on one section. Every concern in it was
> individually settled; all the churn was at the **interfaces** between them — a quoting predicate
> that collided with the dependency removal, which collided with the import gate; a merge rule that
> collided with two different nested-deletion semantics.
>
> The seam is **what is needed to keep behaviour equivalent** versus **what pinakes chooses to
> reject on top**. Decision 26 sits in L5b, not L5c: PyYAML refuses an unknown tag cleanly today and
> ruamel accepts it, so without that check L5b alone would turn a clean `SidecarError` into a
> traceback — measured. A first attempt put it in L5c and introduced exactly that regression window.
>
> | | Scope | Breaking | Cut |
> |---|---|---|---|
> | **L5b** | The swap, and **everything needed to keep behaviour equivalent** — loader, round-trip, quoting, `ScalarBoolean` coercion, the JSON-encodability check (decision 26), stub, gates | **3**: duplicate keys, strings 1.2 resolves as numbers, `!!str` values. Plus four crashes that become named errors | **the interim MINOR** |
> | ~~**L5c**~~ | **Delivered by L5b, unbuilt.** Decision 19 shipped as a side effect of the union JSON check | — | — |
>
> L5c is independently revertible and depends on nothing in L5b — it closes a `TypeError` live on
> `main` today. **Assume both still have defects** — every pass so far has found something real, and each pass's worst finding was in the
> previous pass's fix.

**Pass 7's split of L1–L8 stands:** its L2 findings are localised, fixed and now carry tests and
mutation targets, while its G5 findings were two ways for the gate to license a default it never
measured. **G5's clauses are re-reviewed before G5 is built**, not before L1.

**Date:** written 20260729 02:52 · rewritten 03:31, 04:05, 04:27, 04:46, 05:06, 05:43, 06:03

**Source of truth:** [`docs/DESIGN.md`](../docs/DESIGN.md). Where this plan and DESIGN disagree on
anything *not* in the amendments tables, DESIGN wins and this plan has a bug.

**Section references are qualified** — `DESIGN §5` and `APPROACH §5` are different documents.

**Written against** [`docs/graph/PINAKES_APPROACH.md`](../docs/graph/PINAKES_APPROACH.md) (five
adversarial passes) and `docs/RETROSPECTIVES.md` **together with any unspliced fragments in
[`retro.d/`](../retro.d/)** — the newest findings live there until a release splices them, so
reading only the document systematically misses them.

## Baseline — `main` at `86d6db6`, 20260731 12:10

Re-verify before L6. Re-baselined at 0.5.0: everything through L5b has shipped, so the rows below
describe the tree L6 starts from, not the one the first drafts were written against.

| Fact | Value |
|---|---|
| Latest release | **0.5.0** (20260731 09:34 UTC) — `pnk links`, `pinakes_links`, reverse-scan, and the sidecar round-trip through `ruamel.yaml`. The interim cut of a release that cuts twice |
| `schema_version` | 2 |
| I8, I9 | **Shipped in 0.4.0** (20260729 03:37). Not this plan's concern; noted because the previous revision called them planned, and `docs/CLI.md` line numbers moved when I8 landed |
| Golden set | 41 questions · recall@5 0.909 · MRR 0.812 · rerank precision 0.758 · false-abstain 0.03 · false-confidence 0.25 |
| Per class | `lexical` 1.00 · `filter` 1.00 · `no-answer` 1.00 · `multi-hop` **1.00 (n=5, at ceiling)** · `paraphrase` 0.75 |
| `links` | PK is `(src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel)` — **`origin` is not in it** |
| `kb_refs` | Four columns, never written |
| `chunks.id` | The rowid. `store.py`: *"a chunk has no identity across rebuilds"* |
| Authored links | **Shipped.** demo-kb 16 links across 8 of 30 documents; partner-kb 13 across 6 of 21. Was zero in both when this plan was written |
| `eval.py` | Structurally **single-KB**: one connection, one manifest, one backend; `retrieved` is local `passage.path` strings; per-question outcomes are computed and discarded |
| Conventions | `changelog.d/` and `retro.d/` fragments — **editing `CHANGELOG.md` or `RETROSPECTIVES.md` directly is forbidden**; `tools/fragments.py --check` and `tools/shared_file_overlap.py` are `check.sh` gates |

---

## Two releases, three cuts

| Release | What it is | Rebuild? | Needs the golden set? |
|---|---|---|---|
| **the links release** | `pnk link`, `pnk links`, `pinakes_links`, reverse-scan, link coverage, the sidecar round-trip fix | **No** | **No** |
| **the graph release** | Structural edges, the expansion channel, `schema_version` 3 | Yes, once | Yes — it is the whole gate |

**The links release cuts twice** (decision 27): an interim MINOR at **L5b**, carrying L1–L5b, and
the final cut at L8. A tag is a point on `main`, so a cut at L5b ships everything merged before it.

**A third outcome exists and is planned for**, not discovered: if G2's precondition fails, G3 and G5
do not run, and G1 + G2 + G4 ship as their own release — a reproducibility measurement, a larger and
better-instrumented golden set, and a manifest forward-compatibility pre-pass. Its verification is
G6's minus the edge-dependent steps, its deliverable is not edge-hub reporting, and it is named at
the cut like any other.

**The links release changes no retrieval**, so no golden-set work is on its critical path. Pass 3
made this unavoidable: `eval.py` is structurally single-KB, and every attempt to score a cross-KB
question through it produced a class pinned at 0.00 or 1.00 by construction. Traversal correctness
is directly testable — does the traversal return the neighbour the corpus says it should — and that
is what the links release ships with. All eval work moves to the graph release, where it is the gate.

## Two tracks in parallel — the contract

**G1, G2 and G4 may be built by a second agent alongside L6/L7/L8.** Verified 20260801 00:22, not
assumed: none of the three touches a file the L-track touches, and none depends on the links work.
**G3 and G5 may not start either way** — they are gated behind G2's headroom measurement.

**That verification was too narrow, and G1 found out by landing** (proposed by the G-track,
incorporated 20260801 01:26). It compared the two tracks' *owned* files and never asked what a new
**gate** touches: the Ground rules oblige every one to edit `check.sh`,
`.github/workflows/ci.yml` and `tests/test_check_script.py`, and each is appended to at the end of
the same region. G1 also edits `src/pinakes/search.py` and `src/pinakes/store.py`, which appear in
**neither** column — reproducibility is a property of core retrieval, so no G-increment could have
avoided them. Scope it honestly: the L-track has touched none of these five so far and L7/L8 may
never add a gate, so this is where a clean auto-merge is *least likely* to be a correct one, not a
collision already in progress. Nothing here forbids the work.

| Track | Owns | Never edits |
|---|---|---|
| **L** — L6, L7, L8 | `doctor.py`, `link.py`, `linkscan.py`, `sidecar.py`, `cli.py`, `errors.py`, `tests/test_doctor.py`, `tests/test_cli_link.py`, `tests/test_sync_links.py`, `docs/CLI.md` | `eval.py`, `manifest.py`, `tests/test_eval.py`, the golden set, `baseline.json` |
| **G** — G1, G2, G4 | `eval.py`, `manifest.py`, `tests/test_eval.py`, `tests/demo-kb/eval/*`, `src/pinakes/templates/notes/eval/*`, the two new test files | `doctor.py`, `link.py`, `linkscan.py`, `sidecar.py`, `docs/CLI.md` |
| **Shared, and the reason the overlap gate is mandatory** | `docs/STATUS.md` (all six increments), `docs/DESIGN.md` (G2 §7, G4 §2.1, L-track elsewhere), `docs/MANIFEST.md` (G4 and L7), `docs/VERIFICATION.md` (all), **`check.sh` + `.github/workflows/ci.yml` + `tests/test_check_script.py`** (any increment that adds a gate — appended to at the same place), **`src/pinakes/search.py` + `src/pinakes/store.py`** (core retrieval, owned by neither track) | — |

Four rules, each closing a failure this plan or CLAUDE.md has already recorded once:

1. **G2 lands *after* L8's final cut — or amends L8 step 5 in the same commit.** Step 5 reads
   *"`make eval` unchanged … any movement is a defect."* G2 grows the golden set from 41 to ~59,
   adds a `simple-lookup` kind and rewrites `baseline.json`, so landing it first makes that premise
   false. The dangerous failure is not the false alarm: it is an executor who knows G2 explains the
   movement and therefore stops reading the number at all.
2. **Neither track assigns a release number until the other's cut has landed.** The G-track's
   fallback release and L8 both take one, and CLAUDE.md already records an agent almost numbering a
   release from a stale base (20260728). The G-track does not cut before L8 does.
3. **`python3 tools/shared_file_overlap.py --fetch --strict` before every merge, both tracks, and
   then *read* the merged state of what it names.** `changelog.d/` and `retro.d/` removed the cause
   for the two documents every change writes to; `docs/STATUS.md` has no such protection and is
   touched by all six increments. A clean auto-merge is not a correct merge.
4. **G4 and [`source-walk-containment.md`](source-walk-containment.md) both edit `manifest.py`** —
   G4 a pre-pass around `load()`, containment a check inside `_sources()`. They are genuinely
   independent and *will* merge cleanly, which is the hazard rather than the reassurance. Whichever
   lands second re-reads the merged file before pushing.

---

## Goal

A question answered in one KB can reach evidence in another **one hop out**, because a human said the
two documents were related and pinakes remembered — and the structure that makes retrieval better
when nobody has authored anything is derived for free afterwards, if and only if the golden set says
it helps.

**One hop, stated plainly** (decision 16): a cross-KB neighbour is terminal — **by policy, enforced
by an explicit suppression**, not because the query comes back empty. It does not: K's index holds
each partner document's links *that target K*, so a depth-2 hop through one would return K
documents. It is suppressed because that view is **partial** — the partner's internal links are not
in K's index and never will be — and a silently incomplete result is the failure mode this project
refuses. Multi-hop *within* a KB is unbounded to the cap; multi-hop *across* KBs is one step. This
is a **new** DESIGN §6.2 amendment (L4): §6.2's existing "honest limitation" is about link
*coverage*, not traversal depth, and the plan should not claim DESIGN already says this.

**Nothing here can spend money.** `.paid-path-allowlist` is unchanged; the free-path gate's
*coverage* is extended per increment, which is required.

---

## Decisions taken

Dated by when each was settled, because a decision produced by a review is not one the user made
earlier.

| # | Decision | When | Consequence |
|---|---|---|---|
| 1 | A second synthetic KB is committed, deliberately sparse; the ClaudeKB realism check is optional and human-gated | 02:30–03:10 | L1, L8 |
| 2 | Two releases, cut after the links surface; names split | 02:30–03:10 | L8 — **amended by decision 27: the links release cuts twice** |
| 3 | The golden set grows and gains a `simple-lookup` class; one re-baseline | 02:30–03:10 | G2 — **amended by 12 and 14** |
| 4 | Minimum of [KB-UPDATES](../docs/KB-UPDATES.md): the `requires_pinakes` pre-pass only | 02:30–03:10 | G4 |
| 5 | `pnk link` writes forward only, into the source document's sidecar | 02:30–03:10 | L6 |
| 6 | PPR and the `[ner]` extra are out | 02:30–03:10 | — |
| 7 | Adversarial subagent passes until one comes back clean | 02:30–03:10 | Passes 1–7 done. **No pass has come back clean**, so the rule is honoured per-phase instead: L1–L8 build now, G5's clauses are re-reviewed before G5 |
| 19–27 | Recorded in [`decision-ruamel-yaml.md`](decision-ruamel-yaml.md), not here. 24 and 25 were taken and superseded the same day, by 26 and 27 | 20260731 | L5b, L5c |
| 28 | **L5b splits into L5b and L5c.** After passes returning 8, 8 and 7 HIGH on one section, the seam is *what keeps behaviour equivalent* (L5b, which keeps the interim cut) versus *what pinakes chooses to reject on top* (L5c, decision 19 alone). Decision 26 belongs to L5b: without it, L5b alone turns a clean `SidecarError` on an unknown tag into a traceback | 20260731 07:52 | L5b, L5c |
| 18 | ~~**`pnk link` ships without a comment-preserving YAML writer**~~ — **superseded 20260731 06:00 by [`decision-ruamel-yaml.md`](decision-ruamel-yaml.md)**, which measured the two premises below and found both wrong. This row is left as written; the plan's own updates are not made here | 20260729 05:58 (the user) | L6. `ruamel.yaml` as a second YAML library — core or extra — is a poor trade for one authoring command against *"core dependencies stay light"*; a later paid-extraction sync rewrites the same sidecar through `pyyaml` and destroys the comments anyway, so the guarantee would be partial either way. `test_comments_survive_a_rewrite_through_pnk_link` lands **xfail**, DESIGN §2.2 records the deferral, and `pnk link` **warns when the sidecar it is about to rewrite contains comments** — losing them silently at the moment of loss is the part that is not acceptable |
| 8 | `pinakes_search`'s `entities`/`concepts` are cut | 03:20–03:35 | RRF here is unweighted by construction |
| 9 | The eval harness is repaired before it is grown | 03:20–03:35 | Landed `b637be4`, released in 0.3.0 |
| 10 | Retrieval reproducibility is established before a finer gate depends on it | 03:20–03:35 | G1 — **reframed by 15**: measured first, fixed only if measurement says so |
| 11 | Cross-KB neighbours carry no `title` | 04:00–04:05 | L4, L5 |
| 12 | The multi-hop class is majority single-KB | 04:00–04:05 | G2 — **superseded by 14** |
| 13 | **The edge weights** are frozen at APPROACH §3's priors, committed before G2's questions are authored | 04:00–04:05 | G3, G5 |
| 14 | **The golden set gains no cross-KB questions at all.** The multi-hop class stays single-KB, and cross-KB behaviour is verified by direct traversal tests instead | 04:27 (pass 3) | L1–L7, G2. `eval.py` is single-KB in its bones — one connection, one backend, `retrieved` as local paths. A cross-KB question scored through it is 0.00 by construction (the hop can never be followed) or 1.00 by construction (it merely confirms a link L1 hand-authored). Neither can decide anything, and pass 2 already established such questions cannot respond to `graph_channel` |
| 15 | **Ordering reproducibility is measured before anything is changed.** No tiebreak is specified in advance | 04:27 (pass 3) | G1 — **built 20260801; the measurement refuted the prediction in this cell and the tiebreaks landed.** One question in 41 changed answer between an incremental sync and a `--rebuild` under ties. Read the G1 section, not this cell, before reasoning about ordering. *Superseded text:* the previous revision's three tiebreaks would have changed nothing observable: cross-document ties are already totalised by `documents.path`, and within a document rowid order *is* ordinal order in every write path that exists (`store.replace_chunks` enumerates; the rebuild carry-over in `sync.py` selects `ORDER BY ordinal`). **That is a fact about writes, and it reaches the output only through `_hydrate`'s unordered `WHERE c.id IN (…)` — an undocumented SQLite behaviour the tiebreak would have removed the dependency on.** So: measure first, and let the measurement scope the fix |
| 16 | **The traversal surface serves document-level neighbours only, and a cross-KB neighbour is terminal at any depth** | 04:46 (pass 4) | L3–L5, G3, G5. Two findings collapse into this. First, terminality is **a policy, and needs an explicit suppression in the core** — an earlier draft of this row claimed K's index has "nothing to walk" past a cross-KB neighbour, which is false: `store.py` states that *"a reverse link's source lives in another KB"*, so a reverse-scanned row is keyed on the **foreign** document and a depth-2 query from one returns K documents. The reason to stop is not emptiness but **partiality**: K only ever holds the partner's links that point *back at* K, never the partner's internal links, so expanding through a foreign document would show a systematically incomplete slice of its graph that no caller could distinguish from the whole. Second, structural nodes (tag, directory, heading, chunk) have **no `doc_id`**, so serving them would break the neighbour shape L4 pins with a test. Keeping the tool document-level means **G3 changes no released surface at all** and G5 flips no filter: the structural graph is internal to the expansion channel, permanently, and the authored graph is what `pnk links` shows |
| 17 | **Traversal `confidence` is always `unknown`** in both releases | 04:46 (pass 4) | L5, amending APPROACH §5. The calibrated thresholds are fitted per KB on the reranker score of the *top retrieved passage* for a golden-set query (`calibrate.py`). A traversal neighbour is not a retrieved passage, a cross-KB neighbour list has no single manifest whose thresholds apply, and no fitted data for a traversal signal exists. DESIGN §4.2's rule is that an absent signal is `unknown`, never invented |

---

## What this plan deliberately does NOT decide

| Question | Default | Revisit when |
|---|---|---|
| ~~Does `pnk link` gain a comment-preserving YAML dependency?~~ | **Decided 20260729 05:58 — no**, then **superseded 20260731 06:00 — yes**, on measurement. See [`decision-ruamel-yaml.md`](decision-ruamel-yaml.md) | Settled |
| ~~Does that writer become *the* sidecar writer?~~ | **Yes** — `ruamel.yaml` replaces `pyyaml` outright in L5b, so there is one writer and no fallback. The premise of the old default (that a later paid-extraction sync destroys the comments anyway) was measured and found false: nothing on the free path rewrites an existing sidecar | Settled |
| PPR, the `[ner]` extra, `pnk adopt`, `--deep`, federated query, a graph query language, migrations | Out | — |
| `pnk unlink` | Out; fix a mistyped link by editing the sidecar | A user hits it |
| Held-out eval splits | Out at this corpus size | The set is large enough that a holdout can still gate |
| The **local** source walk escaping the KB (`sync.walk_sources`, `[sources] include`) | Out — L6 review 10 fixed the *partner* side (`linkscan.sidecars_under`) and left this deliberately. It is `sync.py` and `manifest.py`, which this plan does not touch | Its own increment and PATCH release: [`source-walk-containment.md`](source-walk-containment.md) |

---

## Ground rules

- **The gate is an artifact.** `./check.sh` before every commit — **and every new gate also gets its
  own CI job**, because `ci.yml` never invokes `check.sh`. New gates and owners: link-density (L1),
  L5b's four — the AST scan, the free-path runtime check and the stub-signature test (all pytest, so
  the "`ci.yml` never invokes `check.sh`" rationale does not bite), **plus** the wheel-level
  `find_spec("yaml") is None` assertion, which is literally a new `ci.yml` step;
  traversal-caps (L3), eval reproducibility (G1).
- **A gate that cannot run says so and is still a gate**, with a test asserting the printed reason.
- **Worktree + branch per increment**, `YYYYMMDD_HHMM-<id>-<slug>`, timestamp from `date`.
- **Before merging, run `python3 tools/shared_file_overlap.py --fetch --strict`** and read the merged
  state of anything it names. A clean auto-merge is not a correct merge. Fifteen of these sixteen
  increments touch `docs/DESIGN.md` or `docs/STATUS.md` by their own Docs lines.
- **The changelog entry is a [`changelog.d/`](../changelog.d/README.md) fragment**, in the same
  commit as the code. **Never edit `CHANGELOG.md`.** Retrospective findings are a
  [`retro.d/`](../retro.d/README.md) fragment; **never edit `docs/RETROSPECTIVES.md`.** No gate
  catches a direct edit, so this is on the author.
- **Retrospectives are an input** — read `docs/RETROSPECTIVES.md` **and** `retro.d/` at the start of
  each increment.
- **Pure and I/O are separate increments** (v0.1 rule 11): L3 core, L4 provider.
- **The fixture is not the algorithm** (v0.1 rule 5).
- **No inline type suppressions** (v0.1 rule 7) — the node model (G3) is a discriminated union under
  `pyright` strict and is where the temptation will be.
- **Durability** (v0.1 rule 12): every sidecar write is rename-atomic. L6 introduces a new writer,
  and a sidecar's ULID is the one thing no later command can recompute.
- **Break the code on purpose before review.** A target that cannot be mutated is not a target.
- **Docs land in the same commit as the behaviour**, and every increment names its homes.
- **Every retrieval change reports before/after per-class numbers.** The only such increment is
  **G5**. G3 is genuinely inert under decision 16: the provider serves authored document edges, the
  structural graph is read only by the channel, and G3's exit criterion checks that `pnk links`
  output is unchanged rather than assuming it.

---

## DESIGN.md amendments

| § | Amendment | Lands in |
|---|---|---|
| §2.1 | `[retrieval] adjacent_k` | L3 |
| §2.1 | `[retrieval] graph_channel` | G5 |
| §2.1 | `[kb] requires_pinakes` | G4 |
| §2.2 | The comment-preserving writer **delivered**; the PyYAML deferral sentence goes; an unknown key round-trips byte-identically | L5b |
| §2.2 | An unknown key must also be **JSON-encodable** — a user-facing contract change | L5b |
| §2.2 | `links[]` round-trips unknown per-link keys | **L5b** (delivered; L6 must not break it) |
| §3 | The node model, `nodes`/`edges`, `schema_version` 3 | G3 |
| §4.1, new §4.8 | The graph channel | G5 |
| §4.7 | Publishing a KB publishes the ULIDs and relations of every KB it links to | L1 |
| §6.2 | Reverse-scan built; failure taxonomy; stale reverse edges removed | L2 |
| §6.3 | `pnk sync --scan-links` | L2 |
| §7 | The `simple-lookup` class; per-question outcomes are an artifact; a template ships no golden set | G2 |
| §6.2 | Cross-KB traversal is one hop: a neighbour in another KB is terminal | L4 |
| §8 | Command list gains `link` and `links`; every tool takes an explicit `kb` | L4, L5, L6 |
| §8 | The links-release row moves to shipped | L8 |
| §8 | **Both** graph-release rows reconciled | G6 |

## APPROACH amendments

| § | Departure | Lands in |
|---|---|---|
| §5 | The neighbour shape gains `kb_id` and loses `title` for cross-KB neighbours | L4 |
| §3 | Weights are frozen, not fitted | G3 |
| §10 | Cross-KB golden-set questions are not built (decision 14) | G2 |
| §5 | `confidence` on a traversal response is always `unknown` (decision 17) | L5 |
| §5 | Neighbours are documents only; a cross-KB neighbour is terminal (decision 16) | L4 |
| §5 | `frontier` entries gain `kb_id` and a five-valued `reason`, and include fan-out-dropped candidates, not only next hops | L3 |
| §9 | Its `expand` gate demands **false-abstain flat**; clause 3 permits the rise contributed by newly-found-at-low-confidence questions, and treats only the confidence-lost term as a regression | G5 |
| §5, §10 | `pinakes_search`'s `entities`/`concepts` parameters are not built (decision 8) | — |
| §3 | The zero-link nudge is **KB-wide**, not "warn on zero-link docs" — L1's ≤ 35% density cap guarantees a per-document nudge fires on both committed corpora by construction | L7 |

## CLAUDE.md amendments

| Rule | Amendment | Lands in |
|---|---|---|
| *"`docs/` belongs to the user … never any other key"* | A second, narrower exception: **a user-invoked authoring command** writing `links[]` to the source document's own sidecar | L6 |
| The "🚫 Unbuilt work is named" table (**not** the "Naming (fixed…)" table) in `CLAUDE.md` **and** `docs/STATUS.md` | **Only `docs/STATUS.md`'s *roadmap* row lacks `pnk links`** — both 🚫 tables already carry it, and only `CLAUDE.md`'s 🚫 table still needs the paid-extraction row dropped. Check each before editing. **Reconcile the two tables** — `CLAUDE.md` still carries the paid-extraction row that 0.4.0 retired and `docs/STATUS.md` has already dropped. Assigned to L4, which landed without doing it; **reassigned to L5b**, the cutting increment | L4 → **L5b** |
| *Landing work: always push, always release* | A release that **cuts more than once** keeps its name in the 🚫 unbuilt-work table until the **final** cut; the roadmap row carries both tags. CLAUDE.md today says to drop the name when the roadmap row is ticked, which at an interim cut deletes a name L8 needs back — the churn decision 27 was chosen to avoid | L5b |
| *Invariants that must not be broken* | A new one: **an unknown key in a sidecar round-trips byte-identically** — stronger and more testable than "untouched", and false until L5b. It excludes what pinakes normalises by design (`pnk://self/…` expansion; canonical ordering **on a minted sidecar only** — an existing file keeps the user's order), what **ruamel** normalises (block-sequence and nested-mapping **indentation**, which follows the dumper settings rather than the source; **every explicit YAML tag on a value ruamel resolves natively** — `!!int`, `!!bool`, `!!seq`, `!!map`, `!!null` and the non-specific `!` — all dropped on write; and an anchor whose value is **null or recursive**, whose anchor and alias are destroyed and whose value is nulled), and what YAML itself does not carry (CRLF, a BOM, `---`/`...` markers, and **a missing trailing newline**, which is added) | L5b |

---

## Increments — the links release

### L1–L5c — shipped ✅

**All landed and went out in 0.5.0** (L5c closed unbuilt). Their specifications were compacted away
on 20260801 00:58, once they were history rather than instructions — together they were
9,198 words, **a third of this file**, in a document two build tracks read to find out what to do
next. Nothing is lost: what they *decided* is in *Decisions taken* and
[`decision-ruamel-yaml.md`](decision-ruamel-yaml.md); what they *promise* is in *Verification*,
which still names every test by increment; what they *taught* is in
[`docs/RETROSPECTIVES.md`](../docs/RETROSPECTIVES.md); what they *did* is in
[`CHANGELOG.md`](../CHANGELOG.md) `[0.5.0]`; and the full text is in this file's git history.

| Increment | What shipped |
|---|---|
| **L1** | The `tests/partner-kb` corpus, sparse authored links in both corpora, and `tools/link_density_gate.py` (≤ 35% density, ≤ 4 worst degree) wired into `check.sh` |
| **L2** | Reverse-scan — `pnk sync --scan-links` writes inbound rows and `kb_refs`, with a freshness window, a stale-edge delete scoped to the scanned KB, and a failure taxonomy that never fails a sync on a git hook |
| **L3** | The traversal core, pure: depth counted in **logical hops**, the double cap (rows *and* token budget), `frontier` carrying a five-valued reason, `unresolved` returned rather than dropped |
| **L4** | The SQLite provider — one query per hop, never a recursive CTE — and `pnk links` |
| **L5** | `pinakes_links` on the MCP surface; traversal `confidence` is always `unknown` (decision 17) |
| **L5b** | `ruamel.yaml` replaces `pyyaml` in the sidecar: comments, quoting, blank lines and block scalars survive a rewrite, and `country: NO` stops becoming `false`. Four breaking changes, and four crashes turned into named errors. Took the **interim** cut |
| **L5c** | Closed unbuilt — decision 19 shipped inside L5b, via the JSON-encodability union check |

---

### L6 — `pnk link`

**Unblocked** — L5b delivered the comment-preserving writer, superseding decision 18. There is no
fallback path: no `pyyaml` retry, no comment-loss warning, and
`test_comments_survive_a_rewrite_through_pnk_link` lands **passing**.

**What lands.** `pnk link <src> <dst> --rel <rel>`, writing one entry into the **source document's
sidecar only**, rename-atomically.

**`<src>`:** a path relative to the KB root. **A source with no sidecar is refused** — *"run `pnk
sync` first"* — because a `links[].to` needs a doc ULID that only sync mints. **Never mint here**: if
`pnk link` builds a sidecar and calls `write()`, it overwrites a file that may already hold a
permanent ULID, which `sidecar.create()` exists to refuse (`sidecar.py:604-620` records the incident).
An **unreadable** source sidecar is a typed error and is never overwritten. `--kb` is accepted like
every other command; `--rel` is required (`_links` refuses an empty `rel`).

**`<dst>` grammar, in precedence order** — the list was previously unordered and ambiguous. Try the
`pnk://` prefix first; then `<alias>:` **only when the prefix is a declared `[[links.kb]]` name**
(a POSIX path may contain a colon, and `pnk://…` itself splits as alias `pnk`); otherwise treat the
whole string as a KB-root-relative path. An alias resolves via `linkscan.resolve_path` plus a read of
the partner's sidecar for its `id`; an absent partner path is refused here (L7 only *warns* about one
already written). **"Unresolvable" means the alias or `self` cannot be turned into a ULID pair** — a
well-formed `pnk://` to an absent target **is written**, which `tests/free_path_run.py` depends on.

**`<dst>` legacy note:** a path relative to the local KB root; `pnk://<kb-ulid>/<doc-ulid>`; or
`<alias>:<path>` where the alias is a `[[links.kb]]` name. Aliases and `self` in the `<dst>` **argument** resolve to ULIDs before the
entry is written. Note this is a different moment from `read()`, which resolves `pnk://self/…`
already on disk, and from `write()`, which matches on the **resolved** URI — three resolution points,
easy to conflate. An unresolvable `<dst>` is refused with a typed error and a remedy.

**Per-link unknown keys already round-trip — L5b delivered this, do not re-implement it.** The
paragraph here previously said they did *not*, contradicting its own heading and the DESIGN §2.2
amendment. `Link` is still a two-field frozen dataclass, but `write()` assigns only `to` and `rel`
into an existing entry and deletes nothing, so a user's own key inside a `links[]` entry survives —
verified against the shipped 0.5.0 writer. L6's job is to **not break it**, and the test below is a
regression guard rather than new behaviour.

**The first link is the common case, and it is the one L5b just fixed a crash on.** A sidecar with
`links:` and nothing under it — what a user has before their first link — read fine, then crashed
`write()` with an unhandled `TypeError`. `pnk link` reaches that shape on almost every first
invocation, so test it explicitly rather than relying on L5b's guard holding.

**Two of L5b's pinned limitations are reachable here, and one fires on the common case.**
Appending a key captures a **document-trailing comment** — measured, a foot-of-file note becomes the
introduction to the new `links:` block — and `pnk link` appends `links` on every first invocation.
Re-indentation is the second (see the test note below). What is *not* reachable is deletion:
`pnk link` only appends. L5b's pinned limitation — removing an
entry misattributes one comment and destroys another — is unreachable here: `pnk link` only appends.
`pnk unlink` stays out (see *What this plan deliberately does NOT decide*); if it ever lands, that
limitation becomes user-facing.

**Tests.** `tests/test_cli_link.py::test_an_alias_is_resolved_to_a_ulid_on_write`;
`::test_a_first_link_into_a_null_links_value_does_not_crash`;
`::test_a_rel_that_looks_like_a_boolean_is_quoted` (decision 23 — `pnk link --rel no` writes into an
**existing** sidecar, so a bare `rel: no` reads back as `False` under YAML 1.1; the verification
table already assigns this test here, and L6's list omitted it);
`::test_self_is_expanded_on_write`; `::test_each_dst_grammar_resolves`;
`::test_an_unresolvable_dst_is_refused_with_its_remedy`;
`::test_a_link_round_trips_through_sync_into_the_links_table`;
`::test_unknown_keys_inside_a_link_entry_survive_through_pnk_link`;
`::test_the_write_is_atomic_under_an_interrupted_rename`;
`::test_the_source_document_is_byte_identical_afterwards`;
`::test_comments_survive_a_rewrite_through_pnk_link` (**passing**, on L5b's writer);
`::test_no_line_outside_the_links_block_changes_when_a_link_is_added` (**renamed** — the old name
claimed byte-identity the invariant excludes: appending to a 2-space-indented `links:` block
re-indents every line of it, and the committed corpora happen to use 0-indent sequences, so a fixture
copied from them would be green while the promise in the name was false);
`::test_an_indented_links_block_is_reindented_when_a_link_is_added` (pins that exclusion);
`::test_a_document_trailing_comment_is_captured_when_the_first_link_is_appended` (pins the
limitation above, at the CLI).

**Exit criteria.** `DESIGN_COMMANDS` and `IMPLEMENTED` (`tests/test_cli.py:17`), `docs/CLI.md`'s
*Planned — not built yet* row for `pnk link` moving into a real section, and CLAUDE.md's
`docs/`-ownership amendment. **Not "DESIGN §8's command list" — there is no such list**: §8 is a
why-this-order section that opens *"What has actually shipped is STATUS.md"*, and L4 and L5 were
given the same amendment and landed without executing it.
**Docs:** `docs/CLI.md`; `docs/GUIDE.md` — **diff its printed output against the real output**, not
just run it (an L5 example survived a full increment because it ran fine and printed something else);
`docs/MANIFEST.md` — specifically line ~241, *"It is the one place a machine writes into `docs/`"*,
which `pnk link` falsifies and which an executor updating the field table would not notice;
`docs/DESIGN.md` §2.2; `docs/STATUS.md` — the roadmap row moves *Cross-KB links* from **partly
built** to built; a `changelog.d/` fragment.

**Also lands.** `tests/free_path_run.py` gains `pnk link`. Note L5b rewrote that file off PyYAML
onto `pinakes.sidecar.read`/`write`, so it no longer looks as it did when this line was written.

**Mutation targets.** The alias→ULID resolution; the per-link key preservation; the atomic rename;
the `rel` quoting predicate.

---

### L7 — `pnk doctor`: link coverage and cross-KB resolution

**Precondition: L6 must be merged to `main` first.** Not a preference — `linkscan.why_unresolvable`
does not exist on `main`, and `linkscan.resolve_path` still returns a bare `Path` there. Both of
this increment's cross-KB severities are written against the L6 signatures. Branch from `main`
*after* the merge, never from the L6 branch. Nothing else here depends on L6: it touches neither
`doctor.py` nor `tests/test_doctor.py`, so the three broken tests and the four doc claims below are
the same on `main` and at the L6 tip — checked, 20260801 00:02.

**What lands.** Two things in `src/pinakes/doctor.py`:

1. **The coverage ceiling DESIGN §6.2 promises** — *"`pnk doctor` reports it (linked docs / total
   docs)"*. The `origin = 'sidecar'` **filter** is shipped in `_links`; the **metric** is not. The
   shipped check prints an *edge* count (`16 links, 4 cross-KB`) and prints a ratio only in its zero
   branch — on `tests/demo-kb` those 16 edges come from 8 of 30 documents, so the ceiling the
   §6.2 row is tabled against, 27%, is never printed. Add `COUNT(DISTINCT src_doc_id)` over the same
   filter and print the ratio in **both** branches. Verify the filter; **build** the metric.
2. **`"cross-KB (unchecked until the links release)"`** becomes a real check: each cross-KB
   target is resolved through the `[[links.kb]]` entry naming its KB, via `linkscan.resolve_path`
   — which answers **`Path | None`** (L6 review 8, 20260731). `None` means the text names no path
   at all; `linkscan.why_unresolvable(root, raw)` gives the reason, and returns the reason
   *alone*, because the caller already holds the path. Never fall back to the declared text as a
   filesystem base: review 8 measured that shape walking a same-named decoy directory in the
   working directory and deleting every inbound reverse row.

**Where each check lives.** `_links` is yielded from *inside* `_index`, which returns at its first
branch when `.pinakes/` is absent. Anything needing only the manifest must not live there, or it
never fires on a freshly cloned KB — exactly when a committed absolute path is a hazard.

| Check | Home | Needs |
|---|---|---|
| coverage ratio, dangling-internal, cross-KB resolution | `_links`, as today | the index |
| every `[[links.kb]]` entry — unresolvable, absent, absolute (four cases, below) | a new `_linked_kbs(manifest)` returning **one** `Check` named `"linked KBs"`, appended in `diagnose` immediately after `_template(manifest)` | the manifest only |

**`_linked_kbs` returns one `Check`, always** — with no `[[links.kb]]` declared, `Status.OK` and
`"none declared"`, never an absent check. That is not cosmetic: a check `diagnose` *always* produces
is one `test_every_doctor_check_is_exercised_by_a_test` can see, so it needs no entry in that test's
`conditional` map and the coverage guard keeps working by construction. Status is the worst across
the entries; the detail names how many are declared, how many resolvable, and one clause per problem
class carrying the offending aliases.

**`why_not_a_kb` supplies the reason, and it raises — wrap it.** It answers five cases (no such
directory / not a directory / no `pinakes.toml` there / `pinakes.toml` is itself a directory / it is
a symlink to nothing), and it raises `OSError` on an unreadable parent (`~root` is mode 0700 on
macOS) and on `ENAMETOOLONG`. Its docstring names **this increment as its third caller**:
`linkscan.scan_one` and `link._via_alias` each place it inside an `except OSError`, and
`_linked_kbs` must do the same. A diagnostic command reporting a traceback is the one outcome
`pnk doctor` may not have. The totality argument that applies to `resolve_path` deliberately does
not transfer here — there is no value it could return for *"I could not tell"* that a caller would
not have to branch on anyway.

**The detail string, exactly.** `_links` builds `f"{linked} of {active} documents linked
({linked / active:.0%}), {len(targets)} links, {external} cross-KB"` — `{:.0%}` matching
`tools/link_density_gate.py`'s `render`, so the two read alike — then appends, each only when
non-zero and in this order: `f"; {n} dangling inside this KB"`, **wording unchanged**, and
`f"; {n} cross-KB unresolved"`. The zero branch keeps its `"none authored"` wording and gains the
same `0 of {active}` ratio.

**Doctor's number is as of the last sync.** It counts index rows where L1's gate counts sidecar
files, so one `pnk link` without a re-sync makes them disagree — measured on a copy of the committed
corpus: gate 17, doctor 16. Say so in the detail line. Do **not** write that they cannot differ.

**Severity.** Zero authored links KB-wide → WARN nudge (not per-document: L1's ≤ 35% cap guarantees
that would fire on both committed corpora by construction — an amendment to APPROACH §3, tabled
above). Cross-KB target absent from a KB that did resolve → WARN with the count. **Four
`[[links.kb]] path` cases, not two** — `resolve_path` answers `None`, an absent directory, or a
real one: unresolvable (`~someone/kb`, an embedded NUL) → WARN carrying `why_unresolvable`'s
reason; absent on this machine → WARN; absolute → WARN; resolvable and present → OK. Nothing here
is FAIL — `cli.py`'s `doctor` exits
non-zero only on `Status.FAIL`, and none of these is a broken KB. **Every new WARN carries a
remedy**: `test_every_problem_carries_a_remedy` runs on a fixture that cannot reach these checks, so
it will not catch a missing one.

**Do not call `linkscan.scan` to answer any of this.** It returns a `skipped_fresh` row whose
`kb_id` is the **locally declared** `[[links.kb]] id`, not the partner's own — safe today only
because `sync` `continue`s before reading it. `ScannedKb.kb_id`'s docstring names `pnk doctor` as
the reader that would take one for the other. Read the manifest, and resolve with `resolve_path`.

**Not a check here: a malformed `pnk://`.** It never reaches the `links` table — `sidecar._links`
raises `SidecarError` at read, and doctor's *sidecars* check already reports it FAIL. A test named
for it would pass against that pre-existing check while the new one went unexercised. Do not write
one. (It also holds only for sidecars under the local `[sources] roots`; a malformed URI in a
*partner's* sidecar surfaces as a linkscan failure at sync time, not here.)

**Three committed tests break, not two** — all in `tests/test_doctor.py`:

| Test | Why |
|---|---|
| `test_link_coverage_is_reported_even_when_nothing_is_linked` | asserts `Status.OK` where zero becomes WARN — update |
| `test_a_cross_kb_link_is_counted_and_declared_unchecked` | asserts the literal string this increment retires — update |
| `test_a_dangling_link_inside_this_kb_is_a_warning_naming_how_many` | asserts `"1 dangling inside this KB"` while the detail *prefix* changes — it survives only because the suffix wording above is held fixed. Re-run it; do not edit it |

**Both meta-guards run on a fixture that declares no `[[links.kb]]`.**
`test_every_doctor_check_is_exercised_by_a_test` builds its set from `diagnose()` on that fixture,
and `test_every_problem_carries_a_remedy` runs on it too. The "one `Check`, always" rule above is
what keeps the first one honest — do **not** instead add `"linked KBs"` to its `conditional` map,
which would exempt the check from the guard rather than expose it to it. The second guard stays
blind either way, because on that fixture the check is `OK` and carries no problem: that is why
*"every new WARN carries a remedy"* is stated as a requirement here rather than left to it.

**Tests.** `tests/test_doctor.py::test_link_coverage_counts_authored_links_only`;
`::test_link_coverage_reports_the_ratio_not_the_edge_count`;
`::test_a_dangling_cross_kb_target_warns_with_a_reason`;
`::test_an_absolute_linked_kb_path_warns`;
`::test_a_linked_kb_absent_from_this_machine_warns`;
`::test_a_linked_kb_path_that_resolves_to_nothing_warns_with_the_reason`;
`::test_a_kb_with_no_authored_links_nudges`.

**Docs.** Four files carry claims this increment falsifies, and none is optional:

- `docs/CLI.md` — doctor's checks, **and** the `pnk link` section's *"`pnk doctor`'s cross-KB check
  is not built yet"*, which an executor told to update "doctor's checks" will not open.
- `docs/MANIFEST.md` — the *"`path` is stored but **not yet read by anything**"* paragraph: already
  false since 0.5.0 (`linkscan.resolve_path` reads it), and it states L7's absolute-path warn in the
  future tense.
- `docs/VERIFICATION.md` — the two rows naming the retired tests, plus a row per new test.
  `tests/test_verification.py` hard-fails on an unresolvable name, so renaming a test without editing
  the table is a red gate; editing the test in place leaves the table asserting a falsehood that
  nothing catches.
- `docs/STATUS.md`, and a `changelog.d/` fragment.

---

### L8 — Verification of the whole, and the links release's **final** cut

**Two cuts, not one** (decision 27). **L5b** took the **interim** cut, running the steps that
existed then; L8 takes the **final** cut and runs all eight below. `tools/fragments.py --apply` runs
at *each* cut and deletes what it consumes, so the interim cut's CHANGELOG section carries L1–L5b and
the final one carries everything spliced after it — L6–L8, plus any fragment landed on `main` since
the interim cut.

**Verification** — run, not reasoned about:

1. `./check.sh` green on all three CI legs; CI green on the merge.
2. A fresh KB works, **in this order**: `pnk init` → **set `provider = "fastembed"` in both
   `[embedding]` and `[rerank]`** → add a document → **`pnk sync`** (which mints the sidecar and its
   ULID) → `pnk link` to a second KB → **`pnk sync` again** (which carries the link into the `links`
   table) → `pnk search` → `pnk links` — executed. The manifest edit is not optional: `pnk init`
   stamps `sentence-transformers` in both tables, all three CI legs are `[light]`, and without it
   `pnk sync` exits 1 before `pnk link` is ever reached. `docs/GUIDE.md` documents the same two lines
   — cite it rather than inventing wording. `pnk link` cannot precede the first sync: there is no
   sidecar to write into and no ULID to link from, and it says so and exits 1.
3. Every command in `docs/GUIDE.md` runs as written, install line included.
4. `.paid-path-allowlist` byte-identical; the free-path gate covers `pnk link`, `pnk links` and an
   MCP handshake that **invokes** `pinakes_links`.
5. `make eval` unchanged — this release touches no retrieval, so any movement is a defect. L5b
   swapped the loader `load_questions` uses; the swap was measured inert on both committed
   `questions.yaml`, so movement here would mean that measurement was wrong. **If G2 has landed
   first, this step is void as written** — it grows the set from 41 to ~59 and rewrites
   `baseline.json` deliberately. Either it lands after this cut, or the commit that lands it amends
   this step (the two-tracks contract, rule 1). Do not run the step and reason past a difference.
6. **`store.SCHEMA_VERSION` is still 2.**
7. **`pnk sync` both corpora first**, then `pnk doctor` on each, and paste each `links:` line — it
   must name a coverage ratio *and* a count. Unsynced, `.pinakes/` is absent (it is gitignored, so
   that is their committed state), `_index` returns at its first branch and **no link check runs at
   all**: a bare exit-0 would prove nothing about L7. `make demo` syncs `tests/demo-kb`; nothing
   syncs `tests/partner-kb`. "Clean" means no FAIL — WARNs are possible and do not block, and the
   zero-link nudge is KB-wide (L7), so it does not fire on a corpus with any authored links at all.
   Then run `pnk doctor` once on an **unsynced** copy: still exit 0, and it must say the link checks
   could not run.
8. The ClaudeKB realism check is **run, or declined in writing**. It cannot be run against this
   repo — the only KBs here are synthetic by rule — so a declination is the honest answer until
   the corpus in [`realism-corpus.md`](realism-corpus.md) exists. Record the declination and its
   reason; do not leave the step silent.

**The final cut's sweep — decision 27's exception inverted.** The links release's name is dropped
from the 🚫 unbuilt-work table **here and only here**: `CLAUDE.md` and `docs/STATUS.md`'s mirrored
table both. Then four edits, each already *partly* done by L6 — read the row before rewriting it:

- `docs/STATUS.md`'s **`pnk link` command row**, still reading "on `main`, unreleased".
- `docs/STATUS.md`'s ***Cross-KB links*** row — L6 already moved it to **built**; its tail still says
  `pnk link` is "on `main` and unreleased" and that "what remains is `pnk doctor`'s link coverage
  (L7)".
- `docs/STATUS.md`'s **Release roadmap**: a new row for the final version, and the `0.5.0` row's
  tail, which still reads "the final cut is at L8 … **Next: L7**, then L8 and that cut".
- The *Published on PyPI* table and `README.md`'s install lines, as at any release.

Verify by querying the index, not by reading. Step 3 carries L5b's wording in full — diff
the GUIDE's printed output rather than running it, and test against the **built wheel**, since
`uvx --from "pinakes[light]"` resolves from the index and would validate the previous release.

**The cut.** `python3 tools/fragments.py --apply` (splices `changelog.d/` and `retro.d/`, deleting
what it consumes — a release that skips it and runs it later splices into the wrong version), bump
`__version__`, move `[Unreleased]` into a dated section **and add its link definition at the foot,
repointing `[Unreleased]`'s compare** (`fragments.py --apply` splices entries and does not touch the
footer), commit, **merge from the primary checkout**,
push, `make release-check`, tag, push the tag, create the GitHub release. Then `git tag -l`,
`gh release list` and `git merge-base --is-ancestor` to verify it happened.
**Check `origin/main` for the number first** — this plan's own interim cut took 0.5.0, and another
agent may cut again before L8 lands.

---

## Increments — the graph release

### G1 — Is the eval reproducible? ✅ built 20260801, on `main`, unreleased

**The answer was no, and only luck hid it.** Under ties, one question in 41 changed answer between
an incremental sync and a `--rebuild`: every tiebreak in the pipeline resolved to `chunks.id`, the
rowid, which `store.py` says has no identity across rebuilds. Real 384-dimensional cosines almost
never tie, so the property held because the corpus never exercised it. Ordering is now total on
`(documents.path, chunks.ordinal)` at the three sites that decide it, plus a stable `argsort`.
**No number moved** — the golden set scores byte-identically to the committed baseline.

Held by `tests/test_search_reproducibility.py`, `tools/eval_reproducibility_gate.py` (a `check.sh`
gate with its own CI job) and a two-OS per-question diff. Measurement and numbers:
[`docs/STATUS.md`](../docs/STATUS.md#is-the-evaluation-reproducible--measured-20260801-0035);
lessons: `retro.d/g1-eval-reproducibility.md`. Spec compacted 202 words on 20260801 02:00 — full text
in git history.

---

### G2 — Per-question outcomes, the grown golden set, one re-baseline

**What lands, and why it is one increment.** G5's gate is an exact sign test, which needs
**per-question before/after pairs**. Nothing can produce them today: `run()` discards outcomes
(`metrics, _ = evaluate(...)`), `write_baseline` stores aggregates, and `compare()` reads only those.
So the artifact and the questions that populate it land together.

- **Per-question outcomes become a committed artifact** beside `baseline.json`: one row per question
  — id, kind, hit, hit_rank, confidence. **Questions have no id today**, so `questions.yaml` gains a
  stable `id` per entry in this increment; pairing before/after needs one and nothing else supplies
  it. This is what a sign test reads, and what makes "which
  questions flipped" answerable at all.
- **~18 single-KB multi-hop questions** (13 new), and **~20 `simple-lookup`**. **No cross-KB
  questions** (decision 14).
- `eval.py` **validates `kind`** against the known set instead of defaulting silently.
- The template's `eval/questions.yaml` is `questions: []`, which `eval.run` rejects outright, so a
  freshly `pnk init`ed KB fails `make eval` by construction. Fixed by making an empty set a
  **skip with a printed reason**, not an error — the template scaffolds an empty `docs/`, so it
  cannot ship questions naming documents that do not exist.

**The new questions must be failable**, authored from **corpus structure** — evidence genuinely split
across two documents with no shared vocabulary — not by probing what today's pipeline gets wrong.

**The headroom precondition, derived rather than asserted.** G5's gate needs, with *r* regressions,
*i* improvements: (0,5), (1,7), (2,9), (3,10). Improvements can only come from questions that
currently fail. So the corpus must supply at least **7** currently-failing single-KB multi-hop
questions to tolerate one regression, and 9 to tolerate two. The precondition is:

> **At least 7 of the ~18 single-KB multi-hop questions currently fail, AND at least 7 of those are
> channel-reachable *without authored edges*** — both measured by running them. The with-authored
> reachability figure is recorded and licenses nothing.

**The "without authored edges" qualifier is the whole precondition** (pass 7). The probe produces two
numbers and an earlier revision stated one threshold, so an engineer would have cleared it on the
larger. With-authored reachable = 9 and without-authored = 3 is exactly the shape L1's hand-authored
links produce: G3 starts, `schema_version` bumps to 3, every KB in existence is forced to rebuild —
the precise cost this precondition exists to avoid — and only then does the without-authored run turn
out to be incapable of five improvements. G5's licensing rule and this threshold must name the same
run, or the precondition guards nothing.

**The multi-hop set is frozen before the probe runs.** If the precondition fails, G3 does not start
and the questions are **not** re-authored until it passes — that is fitting the question set to the
edge set, the same circularity decision 14 removed by cutting cross-KB questions, and it would be
undetectable afterwards.

**Failing is necessary and nowhere near sufficient**, which the previous revision missed. A question
can only be *lifted* if its evidence documents are connected in the derived edge set within ≤ 2
logical hops of the fused seeds. With `mentions`/`[ner]` cut (decision 6), every surviving
structural edge connects things already near each other — same document, directory or tag — and
APPROACH §3 names `mentions` as *"the one free edge class that bridges unrelated documents"*. So
this increment's own authoring rule ("no shared vocabulary") actively selects for pairs the
remaining edge set **cannot** bridge. You could pass a failure-count check with 18 questions of
which zero are reachable, bump `schema_version`, force every KB in existence to rebuild, and only
then discover the gate was unreachable.

APPROACH §9 already names the right instrument — the **channel-reachable ceiling** — and the
previous revision dropped it because it appeared in the `ppr` row. It comes back here, as an
**in-memory probe**: derive the edge set in memory from the committed corpora, with no schema change
and no rebuild, and report the share of multi-hop questions whose evidence lies within 2 logical
hops of the fused seeds, minus what the membership exclusion forbids — **computed twice, with and
without authored edges**, because a corpus reachable only through links its own author wrote cannot
tell you whether derived structure helps. That probe is throwaway
measurement code, not the G3 deriver, and it is what makes the stop/go sound.

All five committed multi-hop questions score 1.00, so every failure must come from the 13 new ones —
a 54% authored-failure rate, and **7 is the point at which the gate becomes conceivable, not the
point at which it has slack**: with exactly 7 failing, the one-regression branch requires all 7 to
flip.

**If the precondition does not hold, G3 does not start** — bumping `schema_version` and forcing every
KB in existence to rebuild, for an edge table whose channel could never be licensed, is the wrong
order.

**And then G1, G2 and G4 ship as a release on their own**, named at the cut. They stand alone: a
reproducibility measurement, a larger and better-instrumented golden set, and a manifest
forward-compatibility pre-pass. The project's rule is that complete self-contained work never
lingers in `[Unreleased]`, and "the graph release did not happen" is not a reason to strand three
finished increments. G6's verification then drops the *edge-dependent clauses* of steps 2, 3, 6 and 7 — the fresh-KB
end-to-end run in step 2 still happens, without the channel — and the release does not carry G6's
edge-hub reporting, which has nothing to report.

**The re-baseline.** Once, here, per-class before/after in the commit message, the previous
`baseline.json` preserved.

**Tests.** `tests/test_eval.py::test_the_committed_golden_set_is_well_formed` and
`::test_evaluating_the_demo_kb_produces_every_metric` gain `simple-lookup`;
`::test_per_question_outcomes_round_trip`; `::test_an_unknown_kind_is_refused`;
`::test_the_reachable_ceiling_probe_needs_no_index_schema_change`;
`::test_an_empty_question_set_skips_with_a_reason`;
`::test_the_committed_41_score_exactly_their_pre_growth_values` (over the preserved baseline).

**Docs:** `docs/DESIGN.md` §7 (including the "and with each template" clause, which the template's
committed `questions: []` has always falsified — the amendment records that a template ships no
golden set and says why), `src/pinakes/templates/notes/eval/questions.yaml` (its header enumerates
the kinds and goes stale the moment `kind` is validated), `docs/STATUS.md`, a `changelog.d/`
fragment.

---

### G3 — The node model and the edge set (`schema_version` 3)

**Precondition:** G2's headroom measurement passed.

**What lands.** APPROACH §3's node model — **chunk**, **document**, **tag**, **heading-path**
(scoped per document), **directory** — with every shared-value relation through its hub node.

**Node identity, specified because five node kinds span incompatible id spaces** and the previous
revision named a `nodes` table it never described. A node is `(kind, key)`:

| kind | key |
|---|---|
| `doc` | the document ULID |
| `chunk` | `<doc-ulid>:<ordinal>` — **not** `chunks.id`, which `store.py` says has no identity across rebuilds |
| `tag` | the tag string |
| `heading` | `<doc-ulid>:<heading_path>` — scoped per document, so no global "Introduction" hub exists |
| `dir` | the directory path relative to the KB root |

`nodes(id INTEGER PRIMARY KEY, kind TEXT, key TEXT, UNIQUE(kind, key))` mints surrogate ids;
`edges(src INTEGER, dst INTEGER, kind TEXT)` references them, indexed on **both** `src` and `dst`.

**Orientation, stated because the divisor depends on it.** A hub spoke is **one row** with the hub
always as `src`, so the damping divisor is well defined. The non-hub kinds are symmetric or
bidirectional and are also stored once, with an explicit rule: `sibling` as lower→higher ordinal,
`parent`/`child` as parent→child, `membership` as doc→chunk, **`authored` as the direction the
sidecar wrote it** (a reverse-scanned row keeps the foreign document as `src`, exactly as `links`
stores it). The provider therefore queries
`src = ? OR dst = ?` for those kinds and `src = ?` for hub kinds — the distinction is part of the
edge-kind table, not left to the implementer, because a `src`-only query silently drops half of
every symmetric relation.

**Damping at read.** The divisor is `SELECT count(*) FROM edges WHERE src = ? AND kind = ?` on an
indexed column, and it is well defined precisely because hub spokes always carry the hub as `src`.
No stored `degree` — that would be derived state inside derived state.

**Weights are frozen** (decision 13), committed before G2's questions were authored.

| Edge | Connects | Weight at read |
|---|---|---|
| membership | chunk ↔ doc | 1.0 — transit plumbing, not signal |
| `sibling` | chunk ↔ chunk (adjacent ordinal) | 1.0 |
| `parent` / `child` | chunk ↔ chunk (`heading_path` prefix) | 1.0 |
| `in-section` | chunk ↔ heading node (per-doc) | 1/section-size |
| `co-located` | doc ↔ directory node | 1/dir-size |
| `shared-tag` | doc ↔ tag node | 1/tag-degree |
| authored | doc ↔ doc | 2.0 — **read from `links`, not copied into `edges`**, so an authored link has one home. The channel unions it in by resolving both ends of a `links` row — `(src_kb_id, src_doc_id)` and `(dst_kb_id, dst_doc_id)` — to `doc` nodes via `nodes(kind='doc', key=<doc-ulid>)`. **A `doc` node is keyed on the document ULID alone, so only a *local* document has one**: any end whose `kb_id` is not this KB resolves to nothing and that edge never enters the channel. Measured on the committed corpus, `tests/demo-kb` carries 12 intra-KB and 4 cross-KB authored links, so a quarter of its authored edges are inert here — state that number wherever the with/without-authored comparison is reported, because it is what the comparison is actually over; `pnk doctor` reports the `origin='sidecar'` subset, and the difference between the two populations is stated in L7 rather than discovered |

Composition across a hub is the **product of both spokes**.

**Authored edges are in the channel** — APPROACH §4A's whole argument for counting depth in logical
hops is that physical counting "would strand the highest-trust authored edges beyond depth 2", so
the channel traverses them. The previous revision left this unstated while three things depended on
it, and stating it exposes a circularity the plan has already refused once elsewhere: **G5's gate
could be satisfied by L1's hand-authored links bridging G2's hand-authored questions** — the same
"1.00 by construction" shape decision 14 used to cut cross-KB questions. The guard is in G2 and G5:
reachability and the gate are both reported **twice, with and without authored edges**, and a gate
that passes only *with* them is recorded as such rather than counted as evidence that structure
helps.

**Edge removal.** `documents.state='deleted'` is a soft delete: a soft-deleted document's edges are
removed and hub nodes reaching degree zero are reaped, so the channel can never surface deleted
content.

**The released traversal surface never sees these edges — not in G5, not later** (decision 16). Every
neighbour `pnk links` and `pinakes_links` return is a document; a tag, directory, heading or chunk
node has no `doc_id` and cannot be expressed in the shape L4 pins with a test. The structural graph
is read only by G5's channel. There is no filter to flip, no released payload to amend, and no
`--rel` flag spanning two vocabularies. This is what makes "inert" true rather than aspirational.

`schema_version` → **3**. Every KB rebuilds; no migration.

**Tests.** `tests/test_edges.py::test_a_shared_tag_produces_linear_not_quadratic_edges`;
`::test_a_hub_spoke_is_stored_once_not_twice`; `::test_a_heading_hub_never_connects_two_documents`;
`::test_sibling_edges_join_adjacent_ordinals`;
`::test_parent_and_child_follow_heading_path_prefixes`;
`::test_weight_across_a_hub_is_the_product_of_both_spokes`;
`::test_a_soft_deleted_document_leaves_no_edges`; `::test_a_dropped_tag_lowers_the_divisor`;
`::test_the_traversal_surface_returns_no_structural_nodes`;
`::test_a_symmetric_edge_is_reachable_from_both_ends`;
`::test_a_chunk_node_key_survives_a_rebuild`;
`::test_a_schema_version_2_index_is_refused_with_its_remedy`.

**Exit criteria.** `pnk links --json` on both corpora is byte-identical to a fixture **captured at
G2's HEAD and committed in this increment** — after the bump there is no pre-G3 index and no binary
that can read the new one, so the comparison is only executable against a stored artifact. Sync
wall-clock and edge counts reported for both corpora, and whether derivation is incremental or full
is decided here (`--sidecars-only`, the pre-commit hook, does **not** derive edges).
**Docs:** `docs/DESIGN.md` §3, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The divisor replaced by 1.0; the per-document scoping of heading nodes; the
one-row-per-spoke convention; the `src = ? OR dst = ?` orientation for symmetric kinds; the
soft-delete removal; the `schema_version` refusal.

---

### G4 — `requires_pinakes` ✅ built 20260801, on `main`, unreleased

`[kb] requires_pinakes` — a compatibility floor read in a **pre-pass before strict validation**, so a
manifest written by a newer pinakes names the version it needs instead of failing as a typo. The
ordering is the feature: read after strict validation, the field is unreachable in the only case it
exists for. A floor only — no ceiling, no bare version — and an absent one is not an error.

**Its exit criterion is not discharged by any test** and needs a home at the cut: the shipped message
names `pinakes.__version__`, so *the released number appearing in it* is verified at whichever
release ships this increment. Spec compacted 165 words on 20260801 02:00 — full text in git history;
rows in [`docs/VERIFICATION.md`](../docs/VERIFICATION.md).

---

### G5 — The expansion channel, default off, and its gate

**What lands.** `[retrieval] graph_channel = "off" | "expand"`, default `"off"`. When `"expand"`: the
fused top-*k* as roots, expanded to depth ≤ 2, ranked, fed into RRF as a third input; an empty edge
set degrades to today's two-list fusion exactly. **No traversal surface changes** (decision 16): the
structural graph feeds the channel and nothing else, so `pnk links` and `pinakes_links` return
exactly what they returned in the links release.

Chunk neighbours rank by cosine; non-chunk nodes pass through by edge weight and contribute their
member chunks, **excluding same-document chunks reachable *only* through their own document's
membership edges** — excluded from the output **and from the fan-out budget**. A same-document chunk
also reachable by `sibling` or `in-section` is not excluded.

**The gate is computed twice — with and without authored edges** (the guard G3 promises and no
earlier revision delivered here). Authored `doc ↔ doc` links are in the channel, and L1 hand-authored
them into both corpora while G2 hand-authored the questions that traverse them: a gate passed only
*with* authored edges is evidence that a human's links help, not that derived structure does. Both
counts, both p-values, and an explicit statement of which of the two licensed the default go in the
commit message and `docs/STATUS.md`. **If the gate passes only with authored edges, `expand` still
ships `off`** — the same "1.00 by construction" reasoning that cut cross-KB questions in decision 14.

**And it must pass in both — the two runs answer different questions** (pass 7). The
*without*-authored run is the anti-circularity guard; the *with*-authored run is **the configuration
that actually ships**, since G3 unions `links` into the channel at read time. An earlier revision
made only the without-authored run binding, which licensed a wrong default through three green
clauses: without-authored p = 0.031 while with-authored improves 3 and regresses 3 is entirely
consistent, leaves `by_kind["multi-hop"]` unchanged so clause 2 stays quiet, and ships `expand` on by
default for every user while doing nothing in its shipped form. **Both runs must reach p < 0.05, and
the more conservative of the two is reported as the licensing number.**

**"Without authored edges" means every `links`-derived edge, regardless of `origin`.** A
`reverse-scan` row is hand-authored too — by the partner KB's human.

**Cross-KB rows are inert in the channel in *both* directions, and only one was ever stated.** A
`reverse-scan` row has a foreign `src_kb_id`; an `origin='sidecar'` row pointing *out* has a foreign
`dst_kb_id`. Neither end resolves to a local `doc` node (G3), so neither edge exists in the channel
at all. The *with*-authored run therefore measures **intra-KB authored links only** — 12 of
`tests/demo-kb`'s 16. Say so where both numbers are reported: a reader who assumes all 16 are in
play will read the with/without gap as smaller evidence of circularity than it is.

**Three legs, and the *before* leg is measured at G5's own HEAD** (pass 7): `graph_channel = "off"`,
then `"expand"` without authored edges, then `"expand"` with them. G2's artifact owns the row
*schema*, never the row *values* — G3 bumps `schema_version` and forces a rebuild between the two
increments, and G1 exists precisely because a rebuild's effect on per-question outcomes is unmeasured.
Comparing across it would attribute every rebuild-induced flip to the channel, and at ~18 questions
against a 5-improvement threshold two spurious flips are a third of the required signal. The
artifact's header therefore carries its `graph_channel` setting and edge-set variant, because
otherwise a before file and an after file are indistinguishable on inspection.

**The gate is an artifact, not a paragraph** (pass 7). `tools/graph_gate.py` reads two per-question
artifacts and two baselines, and prints the counts, both p-values and a clause-by-clause verdict.
Without it the three gate tests below have no subject and the Verification table's promises have no
checker.

**One configuration is gated.** In-degree salience and the link-distance rerank are measured in the
same matrix and **reported**, not gated — three variables against one threshold is not a decision
procedure. The matrix runner, what it varies and where its results are recorded land here.

**The matrix runner also records, per improved question, which edge kind carried the lifting path**
(pass 7) — because the with/without-authored split neutralises only one of the author's two bridging
mechanisms. Once `mentions` is cut (decision 6), the surviving cross-document edges are `co-located`
(doc ↔ directory) and `shared-tag` (doc ↔ tag), and the directory layout and tag vocabulary of
`tests/demo-kb` were written by the same author as L1's links and G2's questions. So a
without-authored run can still pass for a circular reason: the author filed the two evidence
documents in one folder. APPROACH §3 says as much — *"every structural edge above connects things
that are already near each other"*. No redesign; the runner already walks the paths.
`docs/STATUS.md` records that a result carried entirely by `shared-tag`/`co-located` over an
author-chosen vocabulary is a **weaker claim** than one carried by `sibling`/`in-section`.

**The gate.** On the single-KB `multi-hop` class, at frozen weights, over the three legs above,
`expand` defaults **on** only if all four hold:

1. The **exact one-sided sign test on discordant questions** gives p < 0.05 **in both the with- and
   without-authored runs**:

   | regressed | improvements needed | net |
   |---|---|---|
   | 0 | 5 | 5 |
   | 1 | 7 | 6 |
   | 2 | 9 | 7 |
   | 3 | 10 | 7 |

   **The criterion is p < 0.05 on the discordant pairs; the table is its first four rows**, not a
   closed list. r=4 needs i=12 (p = 0.0384) and r=5 needs i=13 (p = 0.0481) — both significant, both
   absent above, and "short of the table" would have shipped them off.

2. No class regresses beyond `compare()`'s `tolerance=0.02` — which at these class sizes means "no
   class loses a question", **except `no-answer`, where `by_kind` is the *non-hit* rate
   (`evaluate()`'s `if kind == "no-answer": … sum(1 for o in group if not o.hit)`) and the
   regression is a no-answer question *becoming* a hit**. The arithmetic is
   unaffected; the gloss was inverted.
3. `false_abstain` does not rise **among questions that were already hits**. Its numerator requires a
   hit, so converting misses into low-confidence hits raises it — an unqualified clause would veto
   the win clause 1 demands.

   **`compare()` has no such carve-out, and it is a hard CI gate.** Five misses becoming hits, two
   of them at LOW confidence, is 2/66 = 0.030 against `tolerance=0.02` — CI red on a channel this
   gate just blessed. So **turning the channel on re-baselines in the same commit**, with the rise
   decomposed into "newly-found questions reported at low confidence" and "previously-found
   questions that lost confidence", and only the second treated as a regression. A second
   re-baseline is legitimate here precisely because a default was deliberately changed; G2's "once"
   applies to growing the set, not to shipping a new default.

4. **The re-baseline absorbs no *regression* other than the decomposed `false_abstain` term.** It
   necessarily absorbs the *improvements* too — `write_baseline` rewrites the whole dict
   (`path.write_text(json.dumps(metrics.as_dict(), …))`, one statement, no merge) — and that is
   desirable, since it ratchets those guards up. What it may not do is
   swallow a regression. Rewriting `baseline.json` disarms *every* guard in it, so all six of
   `compare()`'s families are named here with the direction `eval.py` actually checks:

   | Metric | A regression is | Verdict |
   |---|---|---|
   | `false_abstain` | a rise | the only term the re-baseline may absorb, and only its newly-found-at-low-confidence part |
   | `false_confidence` | a **rise** | **stop** |
   | `by_kind` | a per-class drop, **or a class vanishing** (`compare()`: *"the class vanished from the golden set"*) | **stop** — discharged by clause 2 |
   | `recall_at_k`, `mrr`, `rerank_precision` | a drop | **stop** |
   | `confidence_coverage` | a **drop** | bookkeeping — cannot move under a channel-only change |
   | question count | a drop | bookkeeping — the set does not resize when a default flips |

   **`by_kind` was the omitted one, and it is the only family a channel actually moves** (pass 7).
   The two now marked bookkeeping cannot fire here: `_confidence()` returns `UNKNOWN` only for no
   passages, an absent `[retrieval.confidence]`, `rerank != "local"`, or a fingerprint mismatch —
   all manifest properties, plus a `no reranker score` branch carrying `pragma: no cover` because
   reranking having run means a score exists — and a third RRF input cannot make a non-empty
   `fused` empty — so coverage is pinned at the committed 1.0. Pass 6 corrected that row's
   *direction* and left it inert for a different reason. They stay in the table as bookkeeping so a
   later reader does not mistake them for live guards and reason from a check that can never fire.

   `false_confidence` matters most and is **not** covered by clause 2: `by_kind["no-answer"]` is
   hit-based, so a no-answer question can stay a clean non-hit while flipping to HIGH. One flip is
   0.125 against a 0.02 tolerance. `confidence_coverage` is the one an earlier draft got backwards —
   it is 1.0 in the baseline and *cannot rise*, so "a rise is a stop" was a condition that could
   never fire while the guard the re-baseline actually removes (a drop, `eval.py`: *"losing the
   ability to say anything is a regression too"*) went unrestored. Before/after for every row goes in
   `docs/STATUS.md` and the commit message. This clause exists because the clause-3 remedy opened
   the hole it closes.

**Why the sign test, and why not "net".** Paired binary before/after on the same questions is
McNemar, whose exact form is the sign test on discordant pairs. "≥ 5 net" is a different quantity:
8 improved / 3 regressed is also net +5 and gives p = 0.113.

**The pre-commitment.** A result short of the table ships the channel **`off`**, with counts and
p-value recorded, untuned. Fitting afterwards is exploratory and cannot flip the gate without a newly
authored question set. And **a test asserts the channel does something**: with `"expand"` and a
non-empty edge set it must surface a document two-list fusion does not return — otherwise a channel
broken into returning nothing produces the same blessed outcome as one that honestly did not help.

**Tests.** `tests/test_graph_channel.py::test_expand_surfaces_a_document_fusion_alone_does_not`;
`::test_an_empty_edge_set_reproduces_two_list_fusion_exactly`;
`::test_off_issues_no_traversal_query`;
`::test_a_chunk_reachable_only_by_membership_never_appears`;
`::test_a_same_document_chunk_reachable_by_sibling_is_not_excluded`;
`::test_membership_neighbours_do_not_consume_the_fanout_budget`;
`::test_pnk_links_output_is_unchanged_with_the_channel_on`;
`::test_the_gate_is_computed_with_and_without_authored_edges` — **and asserts the two derived edge
sets differ in cardinality**, without which it discriminates nothing;
`::test_a_rise_in_false_confidence_stops_the_gate`;
`::test_a_drop_in_confidence_coverage_stops_the_gate`;
`::test_the_gate_requires_both_runs_to_pass`;
`::test_a_class_vanishing_stops_the_gate`.
The last four drive `tools/graph_gate.py` with **synthetic** artifacts — a gate whose only fixture is
the real corpus can only be tested in whichever direction the corpus happens to point.

**Exit criteria.** Per-class before/after numbers and the gate's counts and p-value in the commit
message and `docs/STATUS.md`. Query-time latency reported with the channel on and off — the double
cap bounds response size, not time, and this runs on every query.
**Docs:** `docs/DESIGN.md` §2.1 (`graph_channel`), §4.1 and new §4.8, `docs/CLI.md`, `docs/MANIFEST.md`,
`docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The membership exclusion at both points; `graph_channel`'s default; the
empty-edge degradation path; the third-channel RRF contribution; the false-abstain decomposition.

---

### G6 — Edge-hub reporting, verification, and the graph release cut

**What lands.** `pnk doctor` reports the highest-degree structural edge hubs.

**Tests.** `tests/test_doctor.py::test_edge_hubs_are_reported_highest_degree_first`;
`::test_a_kb_with_no_edges_reports_none`.

**Verification** — run, not reasoned about:

1. `./check.sh` green on all three legs; CI green on the merge.
2. A fresh KB works end to end, including `pnk links` with the channel on and off.
3. **A `schema_version` 2 KB is refused with a remedy that works** — executed.
4. Every command in `docs/GUIDE.md` runs as written.
5. `.paid-path-allowlist` byte-identical; the free-path gate green on the full two-KB surface.
6. The gate's decision, counts and p-value recorded in `docs/STATUS.md`, whichever way it went.
7. Sync wall-clock, edge counts and query latency reported for both corpora.
8. `pnk doctor` clean on both.

**The cut.** As L8, beginning with `python3 tools/fragments.py --apply`.

**Docs:** `docs/CLI.md`, `docs/DESIGN.md` §8 (**both** graph-release rows reconciled),
`docs/STATUS.md`, a `changelog.d/` fragment.

---

## Verification — every promise has an owner

| Promise | Source | Owner | Checked by |
|---|---|---|---|
| Reverse links computed by scanning committed sidecars | DESIGN §6.2 | L2 | `test_rebuild_reconstructs_reverse_rows_from_sidecars_alone` |
| `kb_refs` records alias, path and scan time | DESIGN §3 | L2 | `test_kb_refs_records_alias_path_and_scan_time` |
| Stale reverse edges are removed on re-scan | DESIGN §6.2, amended | L2 | `test_a_removed_link_removes_its_reverse_row`, `test_the_delete_is_scoped_to_the_scanned_kb` |
| Each failure mode reported with a reason | DESIGN §6.2 | L2 | `test_each_failure_mode_is_recorded_with_its_reason` |
| A partner's `self` link resolves to the partner, not to us | pass 7 | L1 corpus, L2 | `test_a_self_link_in_a_partner_sidecar_resolves_to_the_partner_not_the_local_kb` |
| Only the partner's links targeting *this* KB are recorded | Goal | L2 | `test_a_partner_link_to_a_third_kb_is_not_recorded` |
| A partial scan deletes nothing | pass 7 | L2 | `test_a_failed_scan_leaves_the_previous_reverse_rows_in_place` |
| A delisted KB's reverse rows and `kb_refs` row go with it | pass 7 | L2 | `test_delisting_a_linked_kb_removes_its_reverse_rows_and_kb_ref` |
| A link-scan failure never fails the sync on a hook | pass 7 | L2 | `test_an_unreachable_linked_kb_does_not_fail_the_sync` |
| An authored row reclaims a tuple a reverse scan wrote | pass 7 | L2 | `test_an_authored_row_reclaims_a_tuple_a_reverse_scan_already_wrote` |
| Dangling cross-KB targets surfaced | DESIGN §6.2 | L7 | `test_a_dangling_cross_kb_target_warns_with_a_reason` |
| Coverage counts authored links only | DESIGN §6.2 | L7 | `test_link_coverage_counts_authored_links_only` |
| Coverage is reported **as the ceiling** — linked docs / total docs, not an edge count | DESIGN §6.2 | L7 | `test_link_coverage_reports_the_ratio_not_the_edge_count` |
| The zero-link nudge, KB-wide | APPROACH §3, amended | L7 | `test_a_kb_with_no_authored_links_nudges` |
| Absolute linked-KB paths are a publication hazard | DESIGN §4.7 | L7 | `test_an_absolute_linked_kb_path_warns` |
| A linked KB absent from this machine is reported, not an error | DESIGN §6.2 | L7 | `test_a_linked_kb_absent_from_this_machine_warns` |
| A `[[links.kb]] path` that resolves to nothing is reported with its reason | L6 review 8 | L7 | `test_a_linked_kb_path_that_resolves_to_nothing_warns_with_the_reason` |
| Aliases never inside a `pnk://` URI | DESIGN §2.2 | L6 | `test_an_alias_is_resolved_to_a_ulid_on_write` |
| Comment-preserving sidecar writer | DESIGN §2.2 | **L5b** | `test_comments_survive_a_rewrite` |
| An unknown key round-trips **byte-identically** | decision-ruamel-yaml | L5b | `test_an_unknown_key_round_trips_byte_identically`, `test_every_committed_sidecar_round_trips_through_read_and_write` |
| `extra` is no longer corrupted by YAML 1.1 | decision-ruamel-yaml | L5b | `test_yaml_1_1_scalars_are_no_longer_corrupted` |
| The user's key order survives a rewrite | decision-ruamel-yaml | L5b | `test_the_users_key_order_is_preserved_on_rewrite` |
| A duplicate key is a hard error, not a silent last-wins | decision-ruamel-yaml | L5b | `test_a_duplicate_key_is_refused_without_ruamels_suppression_url` |
| A non-string top-level key is refused | decision 19 | **L5b** (shipped) | `tests/test_sidecar.py::test_a_non_string_key_at_the_top_level_is_refused`, `::test_a_key_that_is_not_a_string_is_refused_as_a_key` |
| `extra`/`provenance` values are JSON-encodable | decision 26 | **L5b** (shipped) | `tests/test_sidecar.py::test_a_json_unencodable_extra_value_is_refused_with_a_remedy` (this row named a second, sync-level test that was never written; the behaviour is what the surviving one asserts) |
| Every scalar pinakes writes survives a 1.1 **and** a 1.2 reader | decision 23 | L5b, L6 | `test_a_minted_title_that_looks_like_a_boolean_is_quoted`, `test_a_rel_that_looks_like_a_boolean_is_quoted` |
| A comment inside a nested known-key block survives | decision-ruamel-yaml | L5b | `test_a_comment_inside_provenance_extraction_survives_a_re_extraction` |
| `src/` never imports `pyyaml` again | decision 21 | L5b | `test_no_module_under_src_imports_pyyaml` (AST), `test_the_free_path_run_never_loads_yaml` (runtime) — neither alone suffices |
| A custom-tagged mapping is accepted, being serialisable | decision 26 | L5b | `test_a_tagged_mapping_is_accepted_because_it_serialises` |
| An anchored or aliased boolean is indexed as `true` | pass 4 | L5b | `test_an_anchored_boolean_is_indexed_as_true_not_one` |
| An `!!str` value is refused | decision 26 | L5b | `test_a_double_bang_str_value_is_refused` |
| A comment on a `tags` entry survives | user, 20260731 | L5b | `test_a_comment_on_a_tags_entry_survives_a_rewrite` |
| The links release cuts twice | decision 27 | L5b, L8 | L5b's verification list; L8's step 1 |
| The ruamel stub describes the real library | decision 20 | L5b | `test_every_symbol_the_ruamel_stub_declares_matches_inspect_signature` |
| Unknown per-link keys round-trip | DESIGN §2.2 | L6 | `test_unknown_keys_inside_a_link_entry_survive_through_pnk_link` |
| Sidecar writes are rename-atomic | v0.1 rule 12 | L6 | `test_the_write_is_atomic_under_an_interrupted_rename` |
| Server reaches only its configured KBs | DESIGN §4.7 | L5 | `test_a_neighbour_outside_the_served_kbs_returns_its_kb_id_and_a_reason` |
| Every tool takes an explicit `kb` | DESIGN §8 | L4, L5 | the CLI grammar and the tool signature |
| A neighbour is identifiable **and fetchable** | decision 16 | L5 | `test_pinakes_get_resolves_a_neighbour_returned_by_pinakes_links` |
| Typed verbs, hard caps, no query language | APPROACH §5 | L5 | `test_depth_is_capped_server_side` |
| Score + frontier on every return | APPROACH §5 | L3 core, L5 surface | `test_pinakes_links_returns_score_and_frontier_on_every_return` |
| Double cap: rows **and** token budget | APPROACH §5 | L3 | `test_the_token_budget_sets_truncated_independently_of_the_row_cap` |
| Both ranking modes, with and without `query` | APPROACH §5 | L3 | two named tests |
| `confidence` is `unknown`, always | decision 17, amending APPROACH §5 | L5 | `test_pinakes_links_reports_unknown_confidence_with_and_without_a_query` |
| `unresolved` returned, never dropped | APPROACH §5, DESIGN §6.2 | L3 | `test_unresolved_targets_survive_to_the_caller` |
| Depth in logical hops | APPROACH §4A | L3 | `test_depth_counts_logical_hops_not_physical_edges` |
| Per-depth Python loop, not a recursive CTE | APPROACH §4A | L4 | `test_one_query_per_hop_not_a_recursive_cte` |
| Visited-edge dedup | APPROACH §4A | L3 | `test_a_hub_is_expanded_once_globally` |
| Membership excluded from output **and** budget | APPROACH §3 | G5 | three named tests |
| Hub damping on every shared-value hub | APPROACH §3 | G3 | `test_a_dropped_tag_lowers_the_divisor` |
| Hub edges stay linear, not quadratic | APPROACH §3 | G3 | `test_a_shared_tag_produces_linear_not_quadratic_edges` |
| One row per spoke | this plan | G3 | `test_a_hub_spoke_is_stored_once_not_twice` |
| Weight across a hub is the product of spokes | APPROACH §3 | G3 | `test_weight_across_a_hub_is_the_product_of_both_spokes` |
| Heading nodes scoped per document | APPROACH §3 | G3 | `test_a_heading_hub_never_connects_two_documents` |
| Hierarchy edges derived by prefix | APPROACH §3 | G3 | `test_parent_and_child_follow_heading_path_prefixes` |
| Edge-hub reporting | APPROACH §3 | G6 | `test_edge_hubs_are_reported_highest_degree_first` |
| Authored links are sparse | APPROACH §3 | L1 | the density gate and its negative tests |
| The eval is reproducible enough to gate on | decision 15 | G1 | `test_outcomes_survive_an_incremental_sync_and_rebuild` |
| Per-question outcomes exist as an artifact | this plan | G2 | `test_per_question_outcomes_round_trip` |
| The gate is reachable before the schema bumps | this plan | G2 | the headroom measurement |
| A template ships no golden set, and DESIGN §7 says so | DESIGN §7, amended | G2 | `test_an_empty_question_set_skips_with_a_reason` |
| `frontier` carries why a neighbour was not expanded | APPROACH §5 | L3 | `test_a_frontier_entry_carries_the_reason_it_was_not_expanded` |
| A cross-KB neighbour is terminal at any depth | decision 16 | L3, L4 | `test_a_cross_kb_neighbour_is_frontier_terminal_at_every_depth` |
| The traversal surface returns documents only | decision 16 | L4, G3 | `test_the_traversal_surface_returns_no_structural_nodes` |
| The channel-reachable ceiling is measured before the schema bumps | APPROACH §9 | G2 | the in-memory probe |
| In-degree salience and link-distance rerank evaluated | APPROACH §4A, §10 | G5 | the matrix runner and its recorded results |
| A channel regressing simple lookup stays off | APPROACH §9 | G5 | `compare()` plus gate clause 2 |
| The re-baseline absorbs only `false_abstain` | this plan | G5 | `test_a_rise_in_false_confidence_stops_the_gate`, `test_a_drop_in_confidence_coverage_stops_the_gate` |
| The gate is not satisfiable by hand-authored links alone | decision 14's reasoning | G5 | `test_the_gate_is_computed_with_and_without_authored_edges` |
| Free path stays free | CLAUDE.md | L4, L5, L6 | the subprocess gate, extended per increment |
| No `schema_version` bump before the links release | this plan | L8 | verification step 6 |
| The ClaudeKB realism check happens or is declined | decision 1 | L8 | verification step 8 |

---

## Risks

| Risk | Why it is real | Mitigation |
|---|---|---|
| The synthetic corpus is unrealistically clean | One author writes the corpus, the links and the questions | Density and degree caps with negative tests; **frozen weights**; the ClaudeKB check, owned by L8 |
| The gate cannot be reached | Improvements come only from questions that both currently fail **and** are channel-reachable — and the authoring rule ("no shared vocabulary") selects against reachability once `mentions` is cut | G2 measures **both**, in memory, before G3 bumps the schema; if either fails, G3 does not start and G1/G2/G4 ship on their own |
| The gate is reached by chance | ~18 questions is a small sample | An exact test, one gated configuration, no post-hoc tuning |
| Frozen weights understate the channel | Unfitted priors may fail a gate tuned weights would pass | Pre-committed: fitting is exploratory and needs a new question set |
| A concurrent agent lands conflicting work | `main` moved fifteen commits and cut a release under three drafts | `shared_file_overlap.py --fetch --strict` before every merge, and read what it names |
| Reverse-scan on a hook is unbounded | `pnk sync` runs on three git hooks | TTL, `--scan-links`, and `--sidecars-only` does not scan |
| A reverse row overwrites an authored one | `origin` is not in the `links` PK | `ON CONFLICT DO NOTHING`, with a self-referencing fixture |
| Cross-KB reads race the other KB's sync | The advisory lock is per-KB | Never take the other lock; a torn read is a recorded reason |
| Edge derivation is slow at scale | It runs on every sync, on a hook path | Wall-clock and edge counts reported, as a G3 exit criterion |
| The channel is slow at query time | It runs on every query when on | Latency reported on and off, as a G5 exit criterion |
| ~~A YAML dependency creeps in~~ | Superseded: `ruamel.yaml` **replaces** `pyyaml`, so the count is unchanged | L5b's AST scan and runtime check together prove `src/` never imports `pyyaml` again |
| A hand-written stub drifts from ruamel | pyright validates against the stub, not the library | A **signature** comparison against `inspect.signature`. An import-verification test is not enough: a stub declaring a parameter ruamel does not have is pyright-green and `TypeError`s at runtime |

---

## Iteration log

**Moved to [`links-and-graph-log.md`](links-and-graph-log.md)** on 20260801 00:58 — 5,274 words of process history, a fifth of this file, none of it an instruction. Every decision it narrates is in *Decisions taken*; every promise, in *Verification*.
