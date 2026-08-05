# The links release and the graph release — implementation plan

**Status:** revised after adversarial passes 1 (22 HIGH), 2 (26 HIGH), 3 (24 HIGH), 4 (13 HIGH),
5 (3 HIGH), 6 (2 HIGH) and 7 (6 HIGH) on L1–L8 and G1–G6; then **seven passes on L5b alone**
(8, 8, 7, 6, 7, 7, 7 HIGH) plus an adversarial code review of the implementation (5 HIGH).
> ## ✅ CLOSED 20260805 — both releases shipped. Nothing here is live.
>
> **The links release** shipped L1–L5b in 0.5.0 and L6–L8 in 0.6.0 (20260801); L5c closed unbuilt
> because its one refusal shipped with L5b. **The graph release** shipped G1 and G4 in 0.6.0, G2 in
> 0.7.0, and **G3, G5 and G6 in 0.11.0** (20260805).
>
> **G5's gate ran and did not pass**, so `graph_channel` ships `off`: on the RFC realism corpus it
> improved 0 multi-hop questions and regressed 3, licensing p = 1.0000. Nothing was tuned after
> seeing that. The finding is `reachable ≠ retrievable` — the probe called 9 questions liftable and
> the retrieval instrument lifted none. That result **does not license** the staged PPR channel or
> the `[ner]` extra ([`20260804_1016-staged-channel-gates.md`](20260804_1016-staged-channel-gates.md)).
>
> **Read this file as a record of what was decided, never as instructions.** The live plan is
> [`20260804_1016-template-release.md`](20260804_1016-template-release.md).

**G2's headroom measurement came back negative on `tests/demo-kb` and positive on the RFC realism
corpus** — 12 multi-hop questions failing and 9 reachable without authored edges, against a
precondition of 7 and 7 ([`20260804_1442-decision-g3-go.md`](20260804_1442-decision-g3-go.md),
decided 20260804 13:50). The corpus that unblocked it is
[`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md), built in a repository of its
own.

> ## ⚠ 20260731 — L5b is split into **L5b** and **L5c** (decision 28)
>
> Three adversarial passes returned **8, 8 and 7 HIGH** on one section. Every concern in it was
> individually settled; all the churn was at the **interfaces** between them — a quoting predicate
> that collided with the dependency removal, which collided with the import gate; a merge rule that
> collided with two different nested-deletion semantics.
>
> The seam is **what is needed to keep behaviour equivalent** versus **what Pinakes chooses to
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

## Baseline — `main` at `d56bb35`, 20260803 22:18

**The G-track is open again.** L1–L8 shipped (0.5.0, 0.6.0); G1 and G4 shipped in 0.6.0; G2
shipped in 0.7.0. G2's measurement stopped the rest for three days and **passed on the RFC realism
corpus on 20260804** — 12 failing, 9 liftable without authored edges, against 7 and 7. **G3 is the
next increment to build** ([`20260804_1442-decision-g3-go.md`](20260804_1442-decision-g3-go.md)).

Read [`20260731_1202-open-corrections.md`](20260731_1202-open-corrections.md) alongside it: one of
its live items — the silent structural-chunking degradation — is required by that decision, because
it is what contaminated three of the six edge kinds in the measurement above.

| | |
|---|---|
| **G3** — the node model and the edge set | **Ready to build.** G2's precondition needed ≥ 7 failing multi-hop questions reachable without authored edges; the RFC corpus measured **9** (and 12 failing) |
| **G5** — the expansion channel and its gate | Follows G3. Its gate reads per-question movement on a class that now has **12** questions that can move, and gains a `--drop sibling` arm |
| **G6** — edge-hub reporting and the cut | Blocked through G3. It reports hubs in an edge table that does not exist |

**Do not start any of them, and do not re-author G2's questions to change the number** — that is
fitting the question set to the edge set, the circularity decision 14 removed once already. The
precondition is re-tested by re-running the probe on a corpus that can discriminate, and the probe's
answer is reported whichever way it comes back.

**The corpus is the critical path**, and it is not a Pinakes increment: see
[`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md) § *Why this is not the gate moving to fit the answer*, and
[`20260803_2239-corpus-probe-run.md`](20260803_2239-corpus-probe-run.md) for how the second measurement is run once it exists.
Re-verify this baseline before starting anything: `git log --oneline -1`,
`gh run list --branch main --limit 1`, `python3 tools/shared_file_overlap.py --fetch --strict`.

## Two releases, three cuts

| Release | What it is | Rebuild? | Needs the golden set? |
|---|---|---|---|
| **the links release** | `pnk link`, `pnk links`, `pinakes_links`, reverse-scan, link coverage, the sidecar round-trip fix | **No** | **No** |
| **the graph release** | Structural edges, the expansion channel, `schema_version` 3 | Yes, once | Yes — it is the whole gate |

**The links release cut twice** (decision 27): an interim MINOR at **L5b** carrying L1–L5b — 0.5.0,
20260731 — and the final cut at L8 — **0.6.0, 20260801**, which is where its name left the
unbuilt-work table. A tag is a point on `main`, so the interim cut shipped everything merged before
it. One cut remains in this plan — the graph release's, at G6 — and it is **blocked**, not pending.

**The third outcome fired.** It was planned for rather than discovered: G2's precondition failed on
20260801 12:14, so G3 and G5 do not run and the finished increments ship without them. G1 and G4 had
already gone out in 0.6.0, so that release was **G2 alone — 0.7.0**, and its deliverable is a
measurement rather than a feature. **The graph release's own cut, at G6, has not happened and cannot
be scheduled**; the name stays in `CLAUDE.md`'s unbuilt-work table until it does.

**Planning the failing branch before running the measurement is what made the negative result
cheap.** It cost one release with a real deliverable in it, instead of a `schema_version` bump that
forces every KB in existence to rebuild for an edge table whose channel could never be licensed.

**The links release changes no retrieval**, so no golden-set work is on its critical path. Pass 3
made this unavoidable: `eval.py` is structurally single-KB, and every attempt to score a cross-KB
question through it produced a class pinned at 0.00 or 1.00 by construction. Traversal correctness
is directly testable — does the traversal return the neighbour the corpus says it should — and that
is what the links release ships with. All eval work moves to the graph release, where it is the gate.

## The open track is G3 — and what the parallel run taught

**The L-track is finished** (0.6.0). **The G-track reopened on 20260804**, when the RFC realism
corpus cleared G2's precondition ([`20260804_1442-decision-g3-go.md`](20260804_1442-decision-g3-go.md)). **G3 is the increment to pick up**, then G5, then G6 — one
per branch, never batched. [`20260731_1202-open-corrections.md`](20260731_1202-open-corrections.md)
is where standalone code work is listed and is worth reading first: its structural-chunking item is
a precondition of trusting any later measurement on any corpus.

Three things the parallel run established that outlive it, and that apply to any future split:

1. **Ownership by *file* is not enough — ask what a new gate touches.** The first contract compared
   the tracks' owned files and passed. G1 then edited `check.sh`, `.github/workflows/ci.yml` and
   `tests/test_check_script.py`, which the Ground rules oblige *every* new gate to append to at the
   same place, plus `src/pinakes/search.py` and `src/pinakes/store.py`, which belonged to neither
   column because core retrieval belongs to neither track.
2. **`docs/STATUS.md` is touched by every increment** and has none of the protection `changelog.d/`
   and `retro.d/` gave the other two shared documents. Both G1's and G4's proposals rewrote the same
   roadmap row; applied independently, the second would have silently deleted the first's sentence.
   `python3 tools/shared_file_overlap.py --fetch --strict` before every merge, then *read* what it
   names.
3. **A verification step written against one track's assumptions goes stale when the other lands.**
   L8's step 5 says `make eval` must be unchanged; G2 rewrites `baseline.json` deliberately. That is
   noted at the step itself, not only here — the place an executor is actually standing.

## Goal

A question answered in one KB can reach evidence in another **one hop out**, because a human said the
two documents were related and Pinakes remembered — and the structure that makes retrieval better
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
| 19–27 | Recorded in [`20260731_0602-decision-ruamel-yaml.md`](20260731_0602-decision-ruamel-yaml.md), not here. 24 and 25 were taken and superseded the same day, by 26 and 27 | 20260731 | L5b, L5c |
| 28 | **L5b splits into L5b and L5c.** After passes returning 8, 8 and 7 HIGH on one section, the seam is *what keeps behaviour equivalent* (L5b, which keeps the interim cut) versus *what Pinakes chooses to reject on top* (L5c, decision 19 alone). Decision 26 belongs to L5b: without it, L5b alone turns a clean `SidecarError` on an unknown tag into a traceback | 20260731 07:52 | L5b, L5c |
| 18 | ~~**`pnk link` ships without a comment-preserving YAML writer**~~ — **superseded 20260731 06:00 by [`20260731_0602-decision-ruamel-yaml.md`](20260731_0602-decision-ruamel-yaml.md)**, which measured the two premises below and found both wrong. This row is left as written; the plan's own updates are not made here | 20260729 05:58 (the user) | L6. `ruamel.yaml` as a second YAML library — core or extra — is a poor trade for one authoring command against *"core dependencies stay light"*; a later paid-extraction sync rewrites the same sidecar through `pyyaml` and destroys the comments anyway, so the guarantee would be partial either way. `test_comments_survive_a_rewrite_through_pnk_link` lands **xfail**, DESIGN §2.2 records the deferral, and `pnk link` **warns when the sidecar it is about to rewrite contains comments** — losing them silently at the moment of loss is the part that is not acceptable |
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
| ~~Does `pnk link` gain a comment-preserving YAML dependency?~~ | **Decided 20260729 05:58 — no**, then **superseded 20260731 06:00 — yes**, on measurement. See [`20260731_0602-decision-ruamel-yaml.md`](20260731_0602-decision-ruamel-yaml.md) | Settled |
| ~~Does that writer become *the* sidecar writer?~~ | **Yes** — `ruamel.yaml` replaces `pyyaml` outright in L5b, so there is one writer and no fallback. The premise of the old default (that a later paid-extraction sync destroys the comments anyway) was measured and found false: nothing on the free path rewrites an existing sidecar | Settled |
| PPR, the `[ner]` extra, `pnk adopt`, `--deep`, federated query, a graph query language, migrations | Out | — |
| `pnk unlink` | Out; fix a mistyped link by editing the sidecar | A user hits it |
| Held-out eval splits | Out at this corpus size | The set is large enough that a holdout can still gate |
| The **local** source walk escaping the KB (`sync.walk_sources`, `[sources] include`) | Out — L6 review 10 fixed the *partner* side (`linkscan.sidecars_under`) and left this deliberately. It is `sync.py` and `manifest.py`, which this plan does not touch | Its own increment and PATCH release: [`20260731_2128-source-walk-containment.md`](20260731_2128-source-walk-containment.md) |

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
| *Invariants that must not be broken* | A new one: **an unknown key in a sidecar round-trips byte-identically** — stronger and more testable than "untouched", and false until L5b. It excludes what Pinakes normalises by design (`pnk://self/…` expansion; canonical ordering **on a minted sidecar only** — an existing file keeps the user's order), what **ruamel** normalises (block-sequence and nested-mapping **indentation**, which follows the dumper settings rather than the source; **every explicit YAML tag on a value ruamel resolves natively** — `!!int`, `!!bool`, `!!seq`, `!!map`, `!!null` and the non-specific `!` — all dropped on write; and an anchor whose value is **null or recursive**, whose anchor and alias are destroyed and whose value is nulled), and what YAML itself does not carry (CRLF, a BOM, `---`/`...` markers, and **a missing trailing newline**, which is added) | L5b |

---

## Increments — the links release

### L1–L5c — shipped ✅

**All landed and went out in 0.5.0** (L5c closed unbuilt). Their specifications were compacted away
on 20260801 00:58, once they were history rather than instructions — together they were
9,198 words, **a third of this file**, in a document two build tracks read to find out what to do
next. Nothing is lost: what they *decided* is in *Decisions taken* and
[`20260731_0602-decision-ruamel-yaml.md`](20260731_0602-decision-ruamel-yaml.md); what they *promise* is in *Verification*,
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

### L6–L8 — shipped ✅ *(0.6.0, the links release's final cut)*

Specifications compacted 20260801 10:55, once built — 3009 words, the same treatment L1–L5c had. What
they *decided* is in *Decisions taken*; what they *promise* is in *Verification*, which still names
every test by increment; what they *taught* is in
[`docs/RETROSPECTIVES.md`](../docs/RETROSPECTIVES.md); what they *did* is in
[`CHANGELOG.md`](../CHANGELOG.md) `[0.6.0]`. Full text in this file's git history.

| Increment | What shipped |
|---|---|
| **L6** | `pnk link <source> <target> --rel REL` — one `links[]` entry into the source document's own sidecar and nothing else. Three target grammars tried in order (`pnk://` URI, `<alias>:<path>`, a path in this KB), aliases and `self` resolved to ULIDs **before** writing. Rename-atomic, and no lock: atomicity prevents a torn file, not a lost update. **16 review rounds**, the last several spent on one containment rule that took four spellings to state correctly |
| **L7** | `pnk doctor` reports link coverage as the **ratio** DESIGN §6.2 promises — linked docs / total docs — not an edge count; resolves each cross-KB target through its `[[links.kb]]` entry; and checks the declared linked KBs themselves (unresolvable, absent, absolute). Every new finding is a WARN with a remedy |
| **L8** | Verification of the whole, and the final cut. Seven of eight steps ran green. **Step 8, the ClaudeKB realism check, was declined in writing** — it needs a real knowledge base and this repo forbids committing one. [`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md) is what gives it something to be run against |

**The one L-finding worth carrying into the G stages**, because it cost four merges: *`main` was red
while local `check.sh` was green.* Six tests asked the operating system to produce an error and then
asserted on the answer — `chmod(0o000)`, a 300-character filename, an embedded NUL — which tests the
platform, not the guard. They now raise `PermissionError`/`OSError`/`ValueError` directly, which is
what each guard's contract actually says it catches. **`gh run list --branch main` belongs in the
merge sequence, right after the push** — not in the next increment's verification, which is where it
was and why four merges landed on a red default branch.

---

## Increments — the graph release

### G1 — Is the eval reproducible? ✅ shipped in 0.6.0

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

### G2 — Per-question outcomes, the grown golden set, one re-baseline ✅ landed 20260801 12:14

**Outcome: the precondition failed.** 18 multi-hop questions, **1 failing** against the 7 required;
reachable-without-authored 1 against the 7 required. G3 does not start. The golden set grew 41 → 74
(20 `simple-lookup`, 13 new multi-hop), `eval/outcomes.json` is committed beside the baseline,
`kind` is validated, an empty set skips with a reason, and `eval/baseline-pre-growth.json` preserves
the 41-question numbers — over which the committed artifact re-scores byte-identically, so nothing
already in the set moved. The spec below is left as written; it is what was built against.


**Read this first — G2 is a measurement wearing a feature's clothes.** The artifact, the questions,
the `kind` validation and the empty-set skip are the deliverables; the **output** is a stop/go on the
entire graph release. If the headroom precondition fails, **G3 does not start** — no
`schema_version` bump, no forced rebuild for every KB in existence — and G1/G2/G4 ship as their own
release instead. Build it expecting the answer to be *no*, and it will be honest either way.

**Four traps, in the order you will hit them:**

1. **Freeze the multi-hop set before the probe runs.** If the probe fails, the questions are *not*
   re-authored until it passes. Re-authoring is fitting the question set to the edge set — the
   circularity decision 14 removed once already, and undetectable afterwards.
2. **Two reachability numbers, and only one binds.** With-authored and without-authored. The
   **without**-authored figure is the precondition; the other is recorded and licenses nothing.
   Reporting one number is the documented way to clear a gate that has not been met.
3. **Failing is necessary and nowhere near sufficient.** A question can fail today and still be
   unliftable, because its evidence documents are not connected within 2 logical hops of the fused
   seeds. Measure both; a failure count alone can pass with zero reachable questions.
4. **The probe must be shown to fail.** A reachability probe that answers "reachable" for everything
   is the vacuous case — this project's recurring defect, an assertion satisfied by something other
   than the property it names. Mutate the edge derivation and confirm the number moves.

**Operational, from the L-track's 0.6.0 experience — none of it is in the spec below:**

- **`gh run list --branch main` immediately after every push.** `main` was red for four merges
  because local `check.sh` was green and nobody looked. It belongs in the merge sequence, not in the
  next increment's verification.
- **Before declaring the increment done, re-read this section's own Docs list** and grep for each
  sentence it quotes. L7 shipped without two of its four, both asserting the opposite of what it
  built, through two review rounds.
- **`tools/fragments.py` splices duplicate `###` headings** and mis-files an entry whose text starts
  with a category name (`20260731_1202-open-corrections.md` item 2). Check the spliced CHANGELOG section, or fix
  the tool first — G2 adds fragments like any increment.
- **A new gate touches `check.sh`, `.github/workflows/ci.yml` and `tests/test_check_script.py`** —
  the three files both tracks append to at the same place. `check.sh` also gained a `nul-scan` gate
  on 20260801; read its merged state rather than trusting a clean auto-merge.
- **Do not undo G1's ordering.** `load_vectors`' `(documents.path, chunks.ordinal)` row order, the
  stable `argsort`, the lexical tiebreak and hydration's `ORDER BY` are what make a per-question
  sign test mean anything. Without them one question in 41 changes answer between an incremental
  sync and a `--rebuild`, and every such flip would be attributed to the channel.

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

**Precondition: G2's headroom measurement passed.** It failed on `tests/demo-kb` (20260801 12:14 —
1 of 18 multi-hop questions failing, 7 required) and **passed on the RFC realism corpus** (20260804 —
**12 failing, 9 reachable without authored edges**). **This increment starts** ([`20260804_1442-decision-g3-go.md`](20260804_1442-decision-g3-go.md)).

**Build all six derived kinds as specified below.** The corpus measured `sibling` contributing zero
and `in-section`/`parent-child` contributing nothing at all, but that corpus had an empty
`heading_path` on every chunk, so three kinds were never exercised and `sibling` there meant an
adjacent arbitrary *size-slice*. **Kind selection is G5's gate to decide, not this increment's** —
G5 carries a `--drop sibling` arm for exactly that.

**One requirement this adds to what follows:** the derived kind set must be selectable at eval time,
so the arm is a flag rather than a rebuild.

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

> ⚠️ **The premise under `authored`'s weight has been falsified by real data (20260801 14:02,
> incorporated 20260804 04:45).** APPROACH §3's *"authored links are sparse, precious signal — plan
> for scarcity"*, inherited from ClaudeKB, is what justifies `authored` at **2.0 undamped** while
> every structural hub is divided by its degree. Measured on the IETF corpus, counting only the
> forward relations [`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md) authorises: **53.3% of documents carry a
> link** against a 35% cap, and the **worst out-degree is 86** against a cap of 4 — RFC 8996
> *(Deprecating TLS 1.0 and TLS 1.1)* updates 86 documents in one header. Real, human-authored, in
> the canonical index.
>
> A document with 86 authored edges at weight 2.0 is exactly the noise clique hub damping exists to
> prevent, in **the one edge class that has none**. This is not a `tools/link_density_gate.py`
> question: it bears on this weight table and on G5's with-authored run, and it must be re-decided
> before G3 is built rather than discovered by a gate that passes. **It does not license changing
> the weight now** — G3 was blocked when this was written, nothing had been measured against a real
> corpus end to end, and
> a weight changed on an argument rather than a measurement is the thing decision 13 froze the table
> to prevent.
>
> **Resolved 20260804 10:16 — defer, and measure it as a G5 leg.** Keeping it, damping it or capping
> out-degree all decide a frozen weight on an argument; only a measurement does not. G3 may
> therefore be built with this table as frozen, carrying a *measured at G5* marker on the `authored`
> row. That satisfies this warning's intent — that the weight not be discovered by a gate that
> passes — rather than its literal "re-decided before G3 is built", and the user took the reading
> ([`20260804_1016-graph-remainder-reentry.md`](../plans/20260804_1016-graph-remainder-reentry.md)).

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

### G4 — `requires_pinakes` ✅ shipped in 0.6.0

`[kb] requires_pinakes` — a compatibility floor read in a **pre-pass before strict validation**, so a
manifest written by a newer Pinakes names the version it needs instead of failing as a typo. The
ordering is the feature: read after strict validation, the field is unreachable in the only case it
exists for. A floor only — no ceiling, no bare version — and an absent one is not an error.

**Its exit criterion is not discharged by any test** and needs a home at the cut: the shipped message
names `pinakes.__version__`, so *the released number appearing in it* is verified at whichever
release ships this increment. Spec compacted 165 words on 20260801 02:00 — full text in git history;
rows in [`docs/VERIFICATION.md`](../docs/VERIFICATION.md).

---

### G5 — The expansion channel, default off, and its gate ✅ built; **gate run 20260804 22:52, did not pass**

**Its deliverable is a measurement, and the measurement is negative.** `expand` ships `off`;
licensing p = 1.0000; nothing lifted and three questions regressed
([`docs/STATUS.md`](../STATUS.md#did-the-expansion-channel-earn-its-default--no-measured-20260804-2252)). The pre-commitment held — nothing tuned, no weight moved, no
threshold revisited after seeing the number. **G6 shipped in 0.11.0, and the graph release is complete.** The spec below is left as
written: it is what was built against.

**Follows G3.** G2's precondition is met on the RFC realism corpus — the multi-hop class has **12**
failing questions to move, not one ([`20260804_1442-decision-g3-go.md`](20260804_1442-decision-g3-go.md)).

**Added by that decision: the gate runs a `--drop sibling` arm and reports it beside the headline.**
On the corpus that unblocked this plan, `sibling` was 106 506 of 107 802 edges and changed no
outcome in either variant — but on a corpus whose chunker works a "sibling" is an adjacent
*section*, not an adjacent size-slice, so the finding does not transfer. The arm exists to answer,
with the instrument that measures retrieval quality rather than a reachability ceiling, whether
99.2% of the graph's mass earns its place. **The arm reports; it does not gate.** A release is not
blocked on its result.

**A second arm: `--drop parent-child`, and a measured ceiling before this gate runs.** That kind is
derived transitively — every ancestor path joined to every descendant path, *a·d* rows, projected at
5.8×–53.5× the chunk count — and **the only corpus it has run against derived zero of them**, because
every chunk there had an empty `heading_path`. So its cost is a projection, not a measurement.
Before this gate runs: derive against a corpus whose chunker populates `heading_path`, and record
edges per chunk, wall-clock and index growth. If that ceiling is alarming, the immediate-parent
variant is the arm to *measure*, never the default to switch to first ([`20260804_1844-decision-parent-child-arity.md`](20260804_1844-decision-parent-child-arity.md)).


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

**Follows G3 and G5.** It reports hubs in the edge table G3 builds, and cuts the release G5's gate
licenses. **Its verification steps are
not blocked and should not be lost** — steps 1–5 and 8 below are the standing shape of any release
cut in this project, and `docs/RELEASING.md` is where a cut that is actually happening reads from.

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
| Every scalar Pinakes writes survives a 1.1 **and** a 1.2 reader | decision 23 | L5b, L6 | `test_a_minted_title_that_looks_like_a_boolean_is_quoted`, `test_a_rel_that_looks_like_a_boolean_is_quoted` |
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
| The gate cannot be reached ⚠️ **materialised, then cleared** | Improvements come only from questions that both currently fail **and** are channel-reachable — and the authoring rule ("no shared vocabulary") selects against reachability once `mentions` is cut | G2 measured **both**, in memory, before G3 bumped the schema. It failed on `tests/demo-kb` (1 of 18) and G1/G2/G4 shipped on their own, exactly as this row prescribed; the RFC realism corpus then cleared it on 20260804 (12 failing, 9 liftable). **The mitigation worked — no KB was ever forced to rebuild for an edge table whose channel might not be licensed** |
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

**Moved to [`20260801_0102-links-and-graph-log.md`](20260801_0102-links-and-graph-log.md)** on 20260801 00:58 — 5,274 words of process history, a fifth of this file, none of it an instruction. Every decision it narrates is in *Decisions taken*; every promise, in *Verification*.
