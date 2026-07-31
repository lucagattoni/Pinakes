# The links release and the graph release — implementation plan

**Status:** revised after adversarial passes 1 (22 HIGH), 2 (26 HIGH), 3 (24 HIGH), 4 (13 HIGH),
5 (3 HIGH), 6 (2 HIGH) and 7 (6 HIGH) on L1–L8 and G1–G6; then passes 1–3 on L5b alone (8, 8, 7
HIGH). **L1–L8 are implementable; G1–G6 are not yet.**

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
> | **L5c** | The one refusal pinakes *chooses* — decision 19, non-string top-level keys | **1**: a non-string top-level key | none; rides L8 |
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

## Baseline — `main` at `64f210c`, 20260729 05:43

Re-verify before L1. `main` moved fifteen commits and cut a release under the first three drafts.

| Fact | Value |
|---|---|
| Latest release | **0.4.0** — page-citable PDFs and the verification-table gate |
| `schema_version` | 2 |
| I8, I9 | **Shipped in 0.4.0** (20260729 03:37). Not this plan's concern; noted because the previous revision called them planned, and `docs/CLI.md` line numbers moved when I8 landed |
| Golden set | 41 questions · recall@5 0.909 · MRR 0.812 · rerank precision 0.758 · false-abstain 0.03 · false-confidence 0.25 |
| Per class | `lexical` 1.00 · `filter` 1.00 · `no-answer` 1.00 · `multi-hop` **1.00 (n=5, at ceiling)** · `paraphrase` 0.75 |
| `links` | PK is `(src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel)` — **`origin` is not in it** |
| `kb_refs` | Four columns, never written |
| `chunks.id` | The rowid. `store.py`: *"a chunk has no identity across rebuilds"* |
| Authored links | **L1 landed 20260729 08:44.** demo-kb 16 links across 8 of 30 documents; partner-kb 13 across 6 of 21. Was zero in both when this plan was written |
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
| 18 | ~~**`pnk link` ships without a comment-preserving YAML writer**~~ — **superseded 20260731 06:00 by [`decision-ruamel-yaml.md`](decision-ruamel-yaml.md)**, which measured the two premises below and found both wrong. This row is left as written; the plan's own updates are not made here | 20260729 05:58 (the user) | L6. `ruamel.yaml` as a second YAML library — core or extra — is a poor trade for one authoring command against *"core dependencies stay light"*; a later paid-extraction sync rewrites the same sidecar through `pyyaml` and destroys the comments anyway, so the guarantee would be partial either way. `test_comments_in_the_sidecar_survive_a_rewrite` lands **xfail**, DESIGN §2.2 records the deferral, and `pnk link` **warns when the sidecar it is about to rewrite contains comments** — losing them silently at the moment of loss is the part that is not acceptable |
| 8 | `pinakes_search`'s `entities`/`concepts` are cut | 03:20–03:35 | RRF here is unweighted by construction |
| 9 | The eval harness is repaired before it is grown | 03:20–03:35 | Landed `b637be4`, released in 0.3.0 |
| 10 | Retrieval reproducibility is established before a finer gate depends on it | 03:20–03:35 | G1 — **reframed by 15**: measured first, fixed only if measurement says so |
| 11 | Cross-KB neighbours carry no `title` | 04:00–04:05 | L4, L5 |
| 12 | The multi-hop class is majority single-KB | 04:00–04:05 | G2 — **superseded by 14** |
| 13 | **The edge weights** are frozen at APPROACH §3's priors, committed before G2's questions are authored | 04:00–04:05 | G3, G5 |
| 14 | **The golden set gains no cross-KB questions at all.** The multi-hop class stays single-KB, and cross-KB behaviour is verified by direct traversal tests instead | 04:27 (pass 3) | L1–L7, G2. `eval.py` is single-KB in its bones — one connection, one backend, `retrieved` as local paths. A cross-KB question scored through it is 0.00 by construction (the hop can never be followed) or 1.00 by construction (it merely confirms a link L1 hand-authored). Neither can decide anything, and pass 2 already established such questions cannot respond to `graph_channel` |
| 15 | **Ordering reproducibility is measured before anything is changed.** No tiebreak is specified in advance | 04:27 (pass 3) | G1. The previous revision's three tiebreaks would have changed nothing observable: cross-document ties are already totalised by `documents.path`, and within a document rowid order *is* ordinal order in every write path that exists (`store.replace_chunks` enumerates; the rebuild carry-over in `sync.py` selects `ORDER BY ordinal`). **That is a fact about writes, and it reaches the output only through `_hydrate`'s unordered `WHERE c.id IN (…)` — an undocumented SQLite behaviour the tiebreak would have removed the dependency on.** So: measure first, and let the measurement scope the fix |
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
| §2.2 | `links[]` round-trips unknown per-link keys | L6 |
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

## CLAUDE.md amendments

| Rule | Amendment | Lands in |
|---|---|---|
| *"`docs/` belongs to the user … never any other key"* | A second, narrower exception: **a user-invoked authoring command** writing `links[]` to the source document's own sidecar | L6 |
| The "🚫 Unbuilt work is named" table (**not** the "Naming (fixed…)" table) in `CLAUDE.md` **and** `docs/STATUS.md` | Both files' links-release rows gain `pnk links`. **Reconcile the two tables** — `CLAUDE.md` still carries the paid-extraction row that 0.4.0 retired and `docs/STATUS.md` has already dropped. Assigned to L4, which landed without doing it; **reassigned to L5b**, the cutting increment | L4 → **L5b** |
| *Landing work: always push, always release* | A release that **cuts more than once** keeps its name in the 🚫 unbuilt-work table until the **final** cut; the roadmap row carries both tags. CLAUDE.md today says to drop the name when the roadmap row is ticked, which at an interim cut deletes a name L8 needs back — the churn decision 27 was chosen to avoid | L5b |
| *Invariants that must not be broken* | A new one: **an unknown key in a sidecar round-trips byte-identically** — stronger and more testable than "untouched", and false until L5b. It excludes what pinakes normalises by design (`pnk://self/…` expansion; canonical ordering **on a minted sidecar only** — an existing file keeps the user's order), what **ruamel** normalises (block-sequence and nested-mapping **indentation**, which follows the dumper settings rather than the source; the non-specific `!` tag), and what YAML itself does not carry (CRLF, a BOM, `---`/`...` markers) | L5b |

---

## Increments — the links release

### L1 — The partner KB, sparse links, the density gate

**What lands.** `tests/partner-kb/` — a partner museum that transacts with the archive in
`tests/demo-kb/`: loans in and out, courier and condition reporting, a shared emergency plan, a joint
digitisation programme. ~18–22 documents, own `pinakes.toml` and KB ULID, own sidecars.

**No golden set is needed for it** (decision 14). It exists to be linked to and traversed, and both
are tested directly.

**Both corpora gain authored links, and stay sparse.** The demo KB has zero today. ≤ 35% of
documents in each KB, weakest useful relations, forward-only from each side.

**Two of those links exist to be fixtures for L2** (pass 7), and are authored here rather than
invented there: at least one **`pnk://self/<doc>` link inside a *partner* sidecar** — the form that
resolves to the wrong KB if a partner scan reuses the local `owner=` (L2), so the corpus itself
carries the trap — and at least one **partner link targeting a third KB ULID that no corpus
provides**, which is what L2's third-KB filter and L7's dangling-target WARN both need. Neither
requires a third corpus; a well-formed ULID that resolves to nothing is the whole fixture.

**Each corpus's intra-KB authored links must be non-empty**, and the gate asserts it rather than
leaving it to how the corpus happened to be written (pass 7). G3 resolves an authored edge by
looking `(kb_id, doc_id)` up in the local `nodes` table, and a cross-KB row's `src_kb_id` is foreign
(`store.py:101`) — so it resolves to nothing and contributes **no channel edge**. A corpus whose
authored links are all cross-KB therefore makes G5's with- and without-authored edge sets identical,
its two runs return the same p-value, and `test_the_gate_is_computed_with_and_without_authored_edges`
passes while discriminating nothing — a guard that cannot fire, written into `docs/STATUS.md` as
though it had.

**The density gate reads the committed sidecars, not the index** — it must run in `check.sh`, which
never builds one. It counts forward-authored links, caps **degree** at 4 per document as well as
count, and reports the cross-KB/intra-KB split and the relation histogram. (The previous revision
described an `origin='sidecar'` filter and a test that reverse-scan rows are ignored; a sidecar
cannot contain a reverse-scan row, and L1 lands before L2 creates one anywhere.)

**`[[links.kb]] path` resolution:** relative to the KB root, `~` expanded, absolute permitted but
**warned** by `pnk doctor` (L7) — this repo is public by rule and an absolute path in a committed
manifest publishes a filesystem layout. Non-existence is not an error.

**Tests.** `tests/test_partner_kb.py::test_both_corpora_load_and_validate`;
`::test_every_sidecar_ulid_is_wellformed_and_unique_across_both_kbs`;
`::test_a_corpus_over_the_density_cap_fails_the_gate`;
`::test_a_corpus_with_a_hub_document_fails_the_gate`;
`::test_the_gate_runs_without_an_index`.

**Exit criteria.** `pnk sync` and `pnk doctor` clean on both; the gate in `check.sh` **and** its own
CI job. **Review step** (not a test): no PII, credentials or non-synthetic content.
**Docs:** `docs/MANIFEST.md`, `docs/DESIGN.md` §4.7, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The density comparison at its boundary; the degree cap; the per-document
grouping that makes degree distinguishable from count.

---

### L2 — Reverse-scan, `kb_refs`, and stale-edge removal

**What lands.** `pnk sync` scans each linked KB's **committed sidecars** — never its index — and
writes inbound rows with `origin='reverse-scan'`, recording alias, resolved path and scan time in
`kb_refs` (DESIGN §3 defines all four columns; nothing writes any of them today). No schema change.

**The scan reads the partner's `pinakes.toml`, and only its `pinakes.toml`** (pass 7). A sidecar
carries `id`, `title`, `tags`, `created`, `links`, `provenance` — and *not* the KB it belongs to
(`sidecar.py:37`), so "sidecars alone" cannot supply `links.src_kb_id`, cannot key `kb_refs.kb_id`,
and cannot even locate the sidecars: they live under the partner's `[sources] roots`, which need not
be `docs/`. Three rules follow, and each is load-bearing:

1. `src_kb_id` and `kb_refs.kb_id` come from the partner's **`[kb] id`**, never from the local
   manifest's declared `[[links.kb]] id`. When the two disagree, that *is* the "unresolvable KB id"
   failure — recorded, not guessed at.
2. Sidecars are enumerated from the partner's **`[sources] roots`**. DESIGN §6.2's `docs/**/*.pnk.yaml`
   is an illustration, not a guarantee.
3. **Partner sidecars are read with `owner=<the partner's kb id>`.** Both existing `read_sidecar`
   call sites hard-code `owner=manifest.kb.id` (`sync.py:387`, `sync.py:1116`), and reusing either
   would expand a partner's `pnk://self/<doc>` to the **local** KB — minting phantom rows claiming
   the partner links to local documents it never named. This exact defect was found and fixed once
   already (`docs/RETROSPECTIVES.md`: *"a sidecar copied into another KB would silently retarget its
   link at the new KB"*), and L1 hand-authors `self`-form links into the partner corpus precisely so
   the fixture exists.

**Only the partner's links that target *this* KB are recorded.** A partner link to a third KB is
read and discarded; without the filter the local index accumulates a foreign graph it can never
complete. Stated in the Goal since the first draft and owned by no test until now.

**A reverse row never overwrites an authored one.** `origin` is not in the `links` PK
(`store.py:103-111`), so a plain `INSERT OR REPLACE` would flip an authored row's `origin` to
`'reverse-scan'` whenever the tuples collide — dropping it out of `doctor`'s authored-only coverage
count and out of L1's and L7's population, which is the consequence a test can actually assert.
Insert with `ON CONFLICT DO NOTHING`. The collision is reachable **only** when a manifest lists
itself as a `[[links.kb]]`: an authored row's `src_kb_id` is always the local KB (`sync.py:1135`),
and `manifest._reject_duplicates` already refuses two aliases resolving to one KB
(`manifest.py:500-518`), so the second case earlier revisions cited does not exist.

**The scan runs after the document loop in `_run`, and both orders are safe — for different
reasons.** Authored-then-reverse is safe because of `DO NOTHING`; reverse-then-authored is safe only
because `_replace_links` uses `INSERT OR REPLACE` (`sync.py:1134`), which reclaims the tuple and
rewrites `origin` to `'sidecar'`. Making that writer a `DO NOTHING` too — the symmetric-looking
"fix" — would silently undercount coverage forever, so both orders get a test.

**Stale reverse edges are deleted on re-scan**, scoped **per scanned `src_kb_id` *and*
`origin = 'reverse-scan'`** — both, because under the self-listing fixture the scanned `src_kb_id`
*is* the local KB, and an origin-blind delete would remove the authored rows the
`ON CONFLICT DO NOTHING` insert exists to protect.

**The delete is deferred until its KB's walk completed, and shares the walk's transaction** (pass 7).
A delete scoped to a whole `src_kb_id` removes every reverse row for that partner up front, and they
return only if every one of its sidecars is then re-read successfully — so a vanished file, an
unparseable sidecar or a path that becomes unreachable mid-walk *is* a mass deletion, which
contradicts this increment's own "never a deletion" rule. Two of the four failure modes produce it.
So: accumulate the partner's rows in memory, and run delete-then-insert for that `src_kb_id` in one
transaction **only when its walk finished without an aborting failure**. A partner whose walk did not
finish keeps the rows it had, and records a reason. (`_replace_links`'s delete-then-insert is per
*document* inside `_apply`'s transaction — that precedent does not carry to a per-KB delete.)

**A delisted KB's rows are deleted too** (pass 7). The per-scanned-KB predicate never fires for a
partner no longer in `[[links.kb]]`, and nothing else in `src/` deletes from `links` except
`_replace_links`, which filters `origin = 'sidecar'` — so disconnecting a partner, or correcting a
`[[links.kb]] id`, would strand its reverse rows until someone happened to `--rebuild`, with
`pnk links --direction in` serving them the whole time. One extra statement per sync:
`DELETE FROM links WHERE origin='reverse-scan' AND src_kb_id NOT IN (<manifest link ids>)`, and the
same for `kb_refs`.

**Cost, because this runs on a hook.** Bounded by `kb_refs.last_scan` with a TTL — **a code constant,
not a manifest key**, stated here because "how stale may a cross-KB link be" is user-visible and the
previous revision left it to the implementer — forced by `--scan-links`. `--sidecars-only` (the
pre-commit hook) does **not** scan; reverse rows are index rows, and `_run` returns before the index
is opened (`sync.py:730`). `--sidecars-only --scan-links` together is **refused with a remedy**
rather than silently resolved.

**The TTL's clock is `sync()`'s injected `now`, not a fresh `datetime.now()`** — `stamp` is already
injectable (`sync.py:562`), which is the only thing that makes `test_an_expired_ttl_forces_a_rescan`
writable. `last_scan` is `TEXT` in `%Y%m%d %H:%M`: **minute resolution, local, no zone**, so the TTL
is stated in whole minutes and a `last_scan` in the future counts as **expired**, never as fresh.
(`--rebuild` is not in tension with any of this: it calls `store.create` on a fresh file, so
`kb_refs` is empty and there is nothing to skip on.)

**Concurrency.** Never take the other KB's lock. `sidecar.write` is rename-atomic, so a concurrent
*pinakes* writer cannot hand the scanner a half-written file; the residual races are a vanished file
and a human's non-atomic editor. Each sidecar is therefore **read once** — a failure is a recorded
reason, not a retry loop on a hook path that already holds the local lock.

**A partner's deleted document keeps contributing.** `documents.state='deleted'` is a soft delete and
the orphaned sidecar is deliberately kept (`sync.py:259` — *"orphaned sidecar (kept; remove with
`pnk doctor --prune`)"*), so a sidecars-not-index scan still reads it. That is an accepted
consequence of the rule, not a defect: **L7 reports it**, L2 does not prevent it.

**The failure taxonomy** — unresolvable KB id, unreachable path, target document absent, sidecar
unparseable — is constructed as typed errors in `errors.py` for their message and remedy, and
**consumed unchanged by L4, L5 and L7**. They are never *raised*: the scan continues past each one.

**They are also never recorded in `failures`** (pass 7). `SyncReport.ok` is `not self.failures`
(`sync.py:217`), so a `store.record_failure` would make `pnk sync` exit non-zero on every
post-commit and post-merge hook for an unreachable partner — contradicting L1's *"non-existence is
not an error"* and L7's *absent linked-KB path → WARN*. Nothing in `src/` ever deletes from
`failures` either, so one unreachable partner would add a row per sync forever and `pnk doctor` would
report the running total. Instead the scan gets its own `SyncReport` field — printed, and **not**
counted by `ok`. `kb_refs` gains no reason column; `pnk doctor` (L7) re-derives severity from the
manifest.

**Tests.** `tests/test_sync_links.py::test_inbound_rows_carry_the_other_kbs_id_as_source`;
`::test_a_self_link_in_a_partner_sidecar_resolves_to_the_partner_not_the_local_kb`;
`::test_a_partner_link_to_a_third_kb_is_not_recorded`;
`::test_a_reverse_row_never_overwrites_an_authored_row` (fixture: a manifest listing itself);
`::test_an_authored_row_reclaims_a_tuple_a_reverse_scan_already_wrote`;
`::test_kb_refs_records_alias_path_and_scan_time`;
`::test_each_failure_mode_is_recorded_with_its_reason` (four cases);
`::test_an_unreachable_linked_kb_does_not_fail_the_sync`;
`::test_a_failed_scan_leaves_the_previous_reverse_rows_in_place`;
`::test_a_removed_link_removes_its_reverse_row`; `::test_the_delete_is_scoped_to_the_scanned_kb`;
`::test_delisting_a_linked_kb_removes_its_reverse_rows_and_kb_ref`;
`::test_a_fresh_kb_refs_entry_skips_the_walk`; `::test_an_expired_ttl_forces_a_rescan`;
`::test_a_last_scan_in_the_future_counts_as_expired`;
`::test_scan_links_forces_a_rescan`; `::test_sidecars_only_does_not_scan`;
`::test_sidecars_only_with_scan_links_is_refused`;
`::test_rebuild_reconstructs_reverse_rows_from_sidecars_alone`.

**Exit criteria.** All green; `pnk doctor` clean. **Docs:** `docs/CLI.md` (`--scan-links`),
`docs/DESIGN.md` §6.2 and §6.3, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The `src_kb_id` assignment; **the `owner=` passed to a partner's
`read_sidecar`** (point it at the local KB and the `self`-resolution test must fail); the third-KB
filter; `DO NOTHING` → `OR REPLACE`; the delete's scoping **and its `origin` filter** (drop the
filter and the self-listing fixture must fail); the `NOT IN` delisting clause; **the "walk completed"
guard** (delete unconditionally and the partial-scan test must fail); the TTL check; the
future-`last_scan` comparison; the "sidecars, not index" selection — **whose fixture must hold a
partner index that contradicts the partner's sidecars**. Build that fixture with `store.create()`
plus direct `INSERT`s: syncing the partner for real would drag an embedding backend into a test that
needs none.

---

### L3 — The traversal core, pure

**What lands.** `graph/traverse.py` over an edge-provider protocol, no SQLite. **Depth in logical
hops**; **fan-out capped at `adjacent_k`, ranked before truncation**; **visited-edge dedup**;
**responses double-capped on row count *and* token budget**; **`unresolved` returned, never dropped**.

**Both ranking modes are specified here**, because APPROACH §5 defines two and no previous revision
owned either: **with `query`**, neighbours rank by similarity to it; **without**, by edge weight then
link distance, deterministically tie-broken on `(kb_id, doc_id)`. The core stays pure by taking
similarity as a **provider-supplied score per candidate** — the provider embeds and scores, the core
only ranks, caps and dedups.

**The core is generic over node identity**, so one implementation serves both the document provider
(L4) and G5's structural expansion — and G5 uses this core rather than writing a second expander,
which is why its caps fall under this increment's gate. Two consequences, stated because an opaque
key cannot carry them implicitly: terminality is a **provider-set flag on the candidate**, not a
KB-id comparison inside the core, and a `frontier` entry carries the opaque `node_key`, which each
surface projects into its own shape. A candidate carries an opaque `node_key` the provider defines
and totally orders — `(kb_id, doc_id)` for documents, `(kind, key)` for structural nodes — and the
core's dedup and tie-break use only that. Without this, G5 would need a second expander outside
L3's traversal-cap gate.

**`frontier` is defined here and produced here**, not in the MCP layer — it is core work, and the
previous revision left APPROACH §5's other half unowned. A frontier entry is
`{kb_id, doc_id, rel, reason}` — a neighbour *discovered and not expanded* — and `reason` is one of
**five**, because five distinct mechanisms stop an expansion and they mean different things to a
caller: `terminal` (a cross-KB neighbour, never expandable at any depth — decision 16), `depth` (the
hop limit), `fanout` (the `adjacent_k` cap), `rows` and `tokens` (the two response caps, which L3
already requires to be independently observable on `truncated`, so they cannot share one reason).
**Precedence when several apply is that order**, stated because it is otherwise the implementer's
choice: a cross-KB neighbour dropped by the fan-out cap reports `terminal`, since retrying with a
larger cap cannot help. A caller that cannot tell `fanout` from `terminal` retries a hop that can
never succeed.

This departs from APPROACH §5's `[{doc_id, rel}]` and from its "unexpanded **next hops**" wording — a
fan-out-dropped candidate is not a next hop — and carries an amendment row.

**`adjacent_k`** is a `[retrieval]` key, code default 8, **server-capped at 64** — the traversal-cap
gate drives it with `adjacent_k=10_000` and needs a maximum to assert against, which no earlier
revision defined — documented — and **not stamped into the
`notes` template**, in this release or the next. `_toml.py` hard-errors on unknown keys, and
`requires_pinakes` (G4) **cannot help retroactively**: a pinakes built before G4 has no pre-pass and
fails on `requires_pinakes` itself. Deferring the stamp to G4 buys nothing, so the key stays
settable-but-unstamped until a release deliberately accepts the break.

**Tests.** `tests/test_traverse.py::test_depth_counts_logical_hops_not_physical_edges`;
`::test_fanout_keeps_the_highest_ranked_neighbours_not_the_first_k`;
`::test_ranking_without_a_query_uses_edge_weight_then_distance`;
`::test_ranking_with_a_query_uses_provider_supplied_similarity`;
`::test_a_frontier_entry_carries_the_reason_it_was_not_expanded` (five cases);
`::test_terminal_outranks_fanout_when_both_apply`;
`::test_a_cross_kb_neighbour_is_frontier_terminal_at_every_depth` — **its fixture must contain the
back-link rows that make the hop walkable** (a partner document with links targeting the local KB,
in both directions), or the test passes against an implementation with no suppression at all;
`::test_a_hub_is_expanded_once_globally`;
`::test_a_cycle_terminates`; `::test_unresolved_targets_survive_to_the_caller`;
`::test_the_token_budget_sets_truncated_independently_of_the_row_cap`.

**Exit criteria.** The traversal-cap gate in `check.sh` **and** its own CI job. Its predicate,
stated rather than left as a name: it drives the core with a caller asking for `depth=99` and
`adjacent_k=10_000` against a fixture graph, and fails if either exceeds the server cap or if
`truncated` is unset when a cap bit.
**Docs:** `docs/MANIFEST.md`, `docs/DESIGN.md` §2.1, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** Rank-then-truncate ordering; the visited-edge set; the `unresolved`
accumulation; the depth comparison; the token-budget check; **the cross-KB suppression** — delete it
and the terminality test must fail, which it can only do against the back-link fixture above.

---

### L4 — The SQLite provider and `pnk links`

**What lands.** The provider — **a per-depth Python loop, one query per hop, never a recursive CTE**
— and a CLI surface, because DESIGN §8 settled that a slice queryable only over MCP does not reach
end to end.

```text
pnk links <doc> [--kb K] [--rel R] [--direction in|out|both] [--depth N] [--query Q] [--json]
```

`--depth` defaults to 1, server-capped at 3. `--kb` is DESIGN §8's required explicit KB argument,
defaulting to the configured KB.

**The neighbour shape**, amending APPROACH §5:

```text
{kb_id, doc_id, rel, direction, distance, score, terminal, title?}
```

**Every neighbour is a document** (decision 16). Tag, directory, heading and chunk nodes have no
`doc_id` and never appear here — they are internal to the expansion channel, in this release and
after it. That is what lets G3 add a whole structural graph without touching this contract, and it
is why there is no filter to flip later. `terminal` is true for a cross-KB neighbour, which is never
expandable at any depth.

**`kb_id` is the KB ULID, never a name or alias.** Three namespaces exist — `[kb] name` (documented
as free to rename), `[[links.kb]] name` (machine-local), and the ULID (canonical) — and only the
ULID is dereferenceable and portable, which is the same reason a `pnk://` URI carries no alias.
`title` is present for same-KB neighbours and **absent** for cross-KB ones, with a reason.

**Tests.** `tests/test_cli_links.py::test_every_neighbour_is_a_document`;
`::test_a_cross_kb_neighbour_is_marked_terminal`;
`::test_a_cross_kb_neighbour_carries_its_kb_ulid_and_no_title`;
`::test_kb_id_is_a_ulid_not_a_name`; `::test_a_same_kb_neighbour_carries_its_title`;
`::test_depth_beyond_the_cap_is_served_at_the_cap`; `::test_json_output_shape_is_pinned`;
`tests/test_traverse_provider.py::test_one_query_per_hop_not_a_recursive_cte`.

**Also lands.** `tests/free_path_run.py` gains `pnk links`; `tests/test_paid_path.py`'s **module**
list gains `pinakes.graph.traverse` and the provider — it enumerates modules, not commands.
`DESIGN_COMMANDS` and `IMPLEMENTED` in `tests/test_cli.py` gain `links`, and `docs/CLI.md:233`'s
Planned row is split so `pnk link` and `pinakes_links` stay listed.

**Docs:** `docs/CLI.md`, `docs/GUIDE.md` (a cross-KB walkthrough, every command run),
`docs/DESIGN.md` §6.2 (cross-KB traversal is one hop) and §8, `docs/STATUS.md`, the "🚫 Unbuilt work is named" table in **both** `CLAUDE.md` and `docs/STATUS.md` (the links-release
row in each gains `pnk links`; not the "Naming (fixed…)" table), a `changelog.d/` fragment.

**Mutation targets.** The `kb_id` field; the ULID-not-name selection; the depth clamp; the per-hop
loop replaced by one unbounded query.

---

### L5 — `pinakes_links`

**What lands.** APPROACH §5's contract on the MCP surface:
`pinakes_links(kb, doc_id, rel?, direction?, depth?=1, query?)`, `depth` server-capped at 3, no
query-language argument ever, **score and frontier on every return**, and the loop hints in the tool
description, labelled by origin.

**One boundary rule.** A neighbour is *reachable* iff its KB is one the **server was pointed at**
(`Server.kbs`; `roots` is a constructor parameter, not an attribute) — a server-invocation property, not a manifest one. Unreachable neighbours
still return `kb_id`, `doc_id`, `rel` and a reason.

**Confidence is always `unknown`** (decision 17), amending APPROACH §5. Thresholds are fitted **per
KB** on the reranker score of the top *retrieved passage* for a golden-set query; a traversal
neighbour is not a retrieved passage, a cross-KB list has no single manifest whose thresholds apply,
and no fitted data for a traversal signal exists. Reporting `low`/`medium`/`high` here would be the
invented signal DESIGN §4.2 exists to forbid. Calibrating traversal needs its own fitted set and is
not in either release.

**Tests.** `tests/test_serve.py::test_the_tools_are_namespaced` (existing; its exact-set assertion
gains `pinakes_links`);
`::test_pinakes_links_reports_unknown_confidence_with_and_without_a_query`;
`::test_pinakes_links_returns_score_and_frontier_on_every_return`;
`::test_a_neighbour_outside_the_served_kbs_returns_its_kb_id_and_a_reason`;
`::test_pinakes_get_resolves_a_neighbour_returned_by_pinakes_links` (the test that makes "fetchable"
mean something); `::test_depth_is_capped_server_side`;
`::test_pinakes_search_and_get_payloads_are_unchanged`.

**Exit criteria.** `free_path_run.py`'s MCP handshake **invokes** `pinakes_links`; today it asserts
`if not tools` and never calls one.
**Docs:** `docs/CLI.md` (MCP tool table), `docs/GUIDE.md`, `docs/DESIGN.md` §8 (every tool takes an
explicit `kb`), `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The unconditional `unknown`; the served-KB boundary check; the depth clamp.

---

### L5b — `ruamel.yaml` replaces `pyyaml` in the sidecar

**The swap, and everything needed to keep behaviour equivalent** — decision 26 included, because
ruamel's widened acceptance would otherwise turn a clean `SidecarError` into a traceback. L5c adds
the one refusal pinakes *chooses* (decision 19). Split after three adversarial passes returned 8, 8 and
7 HIGH on a single section: every concern was individually settled and all the churn was at the
interfaces between them.

**Read [`decision-ruamel-yaml.md`](decision-ruamel-yaml.md) first** — it owns the rationale, the
measurements and decisions 19–27. This section is instructions only.

**Precondition met** — L5 merged at `d40e305`. Branch `YYYYMMDD_HHMM-l5b-ruamel-sidecar`, from the
clock, own worktree.

**Every decision below is made. Nothing here is delegated** — if a sentence reads as a question,
treat it as a defect in this plan and say so rather than choosing.

**Three breaking changes, all consequences of the library**: a duplicate key becomes a hard error
(was silent last-wins); a string field YAML 1.2 resolves as a number (`1e3`, `1E3`, `0o17` in
`title`, `created`, `tags[]`, `links[].to`, `links[].rel`) now fails `_optional_str`; and an
`!!str`-tagged value is refused. It is **the only *working* tag that breaks**, not the only tag that
works: `!!int`, `!!float`, `!!bool`, `!!seq` and `!!map` all work today and keep working — verified. Separately, **four
shapes whose current unhandled `TypeError` becomes a named error** — `!!binary`, `!!set`,
`!!timestamp`, a bare date. Those are a fix, not a break, and the changelog lists them apart.

**This increment takes the interim MINOR cut** (decision 27): it is the complete data-integrity
story and must not be left half-landed, because the JSON check above is what stops L5b's own
widened acceptance becoming a crash.

**What lands.**

1. **`pyproject.toml`** — `pyyaml>=6.0` moves from `[project.dependencies]` to
   `[dependency-groups] dev`; `ruamel.yaml>=0.19` (a **dot**, not a hyphen) takes its place.
   Regenerate `uv.lock` in the same commit: every gate runs `--frozen`.

2. **The loader** — a module-level private constant in `sidecar.py`, built once. One instance
   serves both `load` and `dump`, interleaved, verified. Constructing one per call costs 399 µs
   against 282 µs. Concurrency is not a concern: `lock.py` serialises the writers.

   ```python
   _YAML = YAML()  # round-trip, YAML 1.2
   _YAML.preserve_quotes = True
   _YAML.width = 4096
   ```

   Both settings are load-bearing. Do not comment `width` as restoring parity with PyYAML — it
   exceeds it.

3. **`sidecar.py`.**
   - `Sidecar` gains `original: CommentedMap | None = field(default=None, compare=False,
     repr=False)` — typed, not `Any`; the stub in item 6 makes `CommentedMap` nameable.
   - `write()` **reconciles known keys into the existing document**. Exactly:
     - **A scalar** (`id`, `title`, `created`) — assign it to the existing key.
     - **A mapping** (`provenance`) — merge **key-by-key at every depth**, never replacing a mapping
       node that already exists. One level is not enough: `with_extraction_provenance` builds a plain
       `dict` for `extraction`, and ruamel stores a comment as the **preceding key's** trailer, so a
       comment describing a *sibling* of `extraction` lives inside that node and dies with it.
     - **`links` reconciles by `to`, never by position.** Match each existing entry to the new one
       with the same `to` URI and update its `rel` in place; append entries whose `to` is new;
       delete entries whose `to` is gone. Positional matching silently **misattributes the user's
       comments onto different links** when the list is reordered, and deletes them when it shrinks —
       measured, and worse than the mapping-key limitation below because the prose then describes
       the wrong data. `tags` is a list of plain strings with no per-entry comments, so it is
       replaced wholesale. A comment on a *deleted* link entry is still lost; that is pinned.
     - **Nested deletion has two rules, and they differ.** Inside `provenance`, a key absent from
       the new mapping **is deleted** — `without_extraction_provenance` returns a provenance without
       `extraction`, and an assign-and-recurse merge would leave the stale paid claim in place,
       silently failing the `--force` reversal DESIGN §2.2 treats as an invariant. Inside a
       `links[]` entry, **nothing is deleted**: only `to` and `rel` are assigned, because `_links()`
       surfaces only those two and a delete-what-is-missing merge would destroy the unknown per-link
       keys DESIGN §2.2 requires to round-trip.
     - **A top-level key that left `present`** — delete it, and only it. `present` names top-level
       known keys and governs nothing nested.
     - **A key not previously in the document** — **append it at the end**, never insert it among
       existing keys. `provenance` first appears on a paid extraction. The trade-off is measured and
       accepted: appending puts it *after* the user's unknown keys, which is not `write()`'s
       canonical order and makes a larger diff, but inserting it at the canonical position would
       land it between the last known key and the first unknown one — and ruamel binds a comment to
       its **preceding** key, so the comment introducing that unknown key would end up above
       `provenance` instead. A larger diff is preferable to a misplaced comment in the increment
       whose purpose is not to misplace comments.
       `test_provenance_first_appearing_is_appended_and_moves_no_comment`.
   - **The user's key order is untouched.** Canonical ordering is for minting only.
   - **Quote ambiguous scalars pinakes writes** (decision 23), keyed on *the value being
     assigned*, never on `original is None`. Predicate: `ruamel.yaml.resolver.VersionedResolver`
     at `(1, 1)` **and** `(1, 2)` — anything not resolving to `tag:yaml.org,2002:str` in **both** is
     emitted `SingleQuotedScalarString`. **Do not import `yaml.resolver.Resolver` here**: item 1
     removes `pyyaml` from the runtime dependencies, so a user's install has no `yaml` module and
     the first sidecar write would `ImportError` — and item 7's AST gate is built to fail on exactly
     that import, so the increment could not be green and correct at once. The PyYAML leg is also
     redundant: measured over 38 probe values, there is no case where PyYAML 1.1 resolves non-`str`
     while both ruamel versions resolve `str`. Prove it rather than assume it, in `tests/` where
     `pyyaml` *is* installed:
     `test_packaging.py::test_the_two_resolver_union_covers_pyyaml_1_1`.
     `resolve()` returns a `Tag` in 0.19, not `str`; `Tag.__eq__` against the tag string works. Scalars pinakes did not author are left as the user wrote them.
     **Note the self-cancelling evidence:** item 5 migrates the last 1.1 sidecar reader in this repo
     to ruamel, so after L5b the justification rests on *external* readers and on `pnk link --rel
     no`, not on anything here. `test_a_minted_title_that_looks_like_a_boolean_is_quoted` reads its
     result back **through PyYAML** precisely because nothing else keeps that honest.
   - **Refuse an `extra` or `provenance` mapping that will not JSON-encode** (decision 26), at
     `read()`. **Encode the assembled mapping, not each value separately** — measured, a per-value
     check accepts `{123: v, abc: w}` and the `sorted()`-equivalent `TypeError` survives, because
     the failure is a comparison *between* keys. Call
     `json.dumps(dict(extra), sort_keys=True, ensure_ascii=False)` and the same for `provenance`,
     mirroring what `_metadata()` hands `store.dumps_metadata`. **This is
     equivalence, not a new choice:** PyYAML refuses an unknown tag today as a clean `SidecarError`
     (`ConstructorError` is a `YAMLError`); ruamel accepts it, so without this check L5b alone turns
     that clean error into an unhandled `TypeError` from `json.dumps` out of `pnk sync` — measured.
     Use **exactly the call `store.dumps_metadata` makes** — `json.dumps(value, sort_keys=True,
     ensure_ascii=False)` — so the check and the thing it protects cannot disagree. Do not add
     `allow_nan=False`: the store does not, and a stricter check would refuse what the index would
     have accepted. The remedy names the key and the offending type, and says the index stores
     metadata as JSON.
     **What `sort_keys=True` does and does not catch.** It catches **mixed**-type keys, at any
     depth. A **uniformly** non-string-keyed mapping is accepted and silently coerced — measured,
     `{1: a, 2: b}` becomes `{"1": "a", "2": "b"}`, nested or not. Do not write that it "catches
     non-string keys nested below the top level"; it does not, and an executor testing a uniform
     case would find it green and conclude the check is broken. L5c's decision 19 is top-level only,
     so a uniformly int-keyed **nested** mapping is covered by neither increment. Identical today
     under PyYAML, so not a regression — a stated residual, alongside `.nan`/`.inf`, which encode as
     `NaN`/`Infinity` that no conforming JSON reader accepts.
     **Documented widening:** a **custom-tagged** mapping or sequence (`!custom {a: 1}`) is
     `ConstructorError` under PyYAML and a `CommentedMap` after, so it is now accepted. Not `!!map`
     or `!!seq` — those were never refused, and a reader checking the claim against them concludes
     it is false.
   - `DuplicateKeyError` (from **`ruamel.yaml.constructor`**) is caught before `YAMLError` and given
     a pinakes message; ruamel's own ends with `To suppress this check see: <URL>`.
   - **Coerce ruamel's scalar subclasses at the `_metadata()` boundary in `sync.py`**, not in the
     sidecar. `ScalarBoolean` subclasses `int` (Python forbids subclassing `bool`), and ruamel
     returns one for any boolean carrying an **anchor or an alias** — both `flag: &a true` and
     `same: *a` — so it is JSON-encodable —
     the JSON check three bullets above will pass it — and lands in the index as `1` where PyYAML wrote `true`. Map
     `ScalarBoolean` → `bool`; leave `ScalarInt`/`ScalarFloat`/`ScalarString`, which already encode
     as their base types. **Walk mappings and sequences recursively** — `_metadata()`
     (`sync.py:1276`) is a shallow spread, so a one-level coercion leaves
     `{"nested": {"inner": 0}, "list": [1], "provenance": {"paid": 1}}` measured. A top-level-only
     fixture is green on the defective version, which is the same increment-shaped blind spot this
     section has now hit three times. `test_sync.py::test_an_anchored_boolean_is_indexed_as_true_not_one`.
   - `with_/without_extraction_provenance` become `dataclasses.replace`. **Name the aliasing they
     create:** `replace` shares one `original` node between the pre- and post-extraction `Sidecar`,
     and `_mapping()` returns the **live** loaded node, so `sidecar.provenance is
     document["provenance"]` for a freshly-read sidecar — merging a mapping into itself, which is a
     silent no-op rather than a crash. `read()` therefore stores `original` and builds `provenance`
     and `extra` as **copies**.

4. **`eval.py`** — a reused `YAML(typ="safe")`, with the same duplicate-key mapping.
   `load_questions` has no `try/except`, so a duplicate key in a user's golden set would otherwise
   escape `make eval` uncaught.

5. **`tools/link_density_gate.py`** migrates too — a shipped gate, not a fixture writer. Left on
   PyYAML it counts sidecars the product now refuses, and `check.sh:105` says keeping those
   populations identical is why the gate exists. It closes the scalar-resolution and duplicate-key
   divergence only. **After L5b** the gate diverges: `typ="safe"` refuses the
   custom-tagged mappings and sequences L5b accepts, and accepts the JSON-unencodable shapes L5b
   refuses. **After L5c** it additionally accepts the non-string top-level keys L5c refuses. Neither reaches the committed corpora;
   state it rather than implying parity.

6. **`tests/free_path_run.py` migrates.** It does `import yaml` at `:146` and **writes a sidecar**
   through `yaml.safe_dump` at `:160`. Measured, the harness's module list already contains
   `['yaml', 'yaml._yaml', 'yaml.composer', …]`, so item 7's runtime gate is **red on day one**; and
   after the swap this is the only place in the repo that writes a sidecar through PyYAML — exactly
   the divergence the gate exists to forbid. Replace the three `safe_load`/`safe_dump` calls with
   `pinakes.sidecar.read`/`write`, which is what L6 needs anyway. Mutation target: restore the
   `import yaml` → the runtime gate fails.

7. **`stubs/ruamel/yaml/{__init__,comments,error,constructor,resolver,scalarstring}.pyi`.** pyright's
   `include` spans `src/`, `tests/` and `tools/`, and a stub overrides the real package for all
   three, so **every symbol any of them touches must be declared or that file stops type-checking**.
   The list, complete: `YAML` (`__init__` with `typ=`, `load`, `dump`, `preserve_quotes`, `width`),
   `CommentedMap`, `CommentedSeq`, `TaggedScalar`, `YAMLError`, `DuplicateKeyError`,
   `SingleQuotedScalarString`, `VersionedResolver`, **`ScalarBoolean`** (item 3's coercion needs
   `isinstance`; re-exported from `ruamel.yaml.constructor`) and **`ScalarNode`**
   (`VersionedResolver.resolve` is `(self, kind, value, implicit)` and `kind` is a node class;
   re-exported from `ruamel.yaml.resolver`). **Not** `Resolver` — item 3 forbids importing it.
   Declare only what is used; a symbol declared in the wrong module is pyright-green and an
   `ImportError` at runtime, which is why item 7's signature test exists.

8. **Three tests, in two named files.** Neither gate alone suffices: the AST scan sees lazy and
   function-scoped imports but not dynamic ones; the runtime check sees transitive and dynamic
   imports but only what the run actually executes.
   - `tests/test_packaging.py::test_no_module_under_src_imports_pyyaml` — walk every `.py` under
     `src/pinakes` with `ast.parse`, and for each `Import`/`ImportFrom` compare the **root** module
     name: `name.split(".")[0] == "yaml"`. **A substring test false-positives on all four ruamel
     forms**, including `from ruamel import yaml`, which is legal and which `sidecar.py` may use.
     For `ImportFrom`, require `node.level == 0` too, or a relative `from .yaml import x` trips it.
     Also flag `importlib.import_module("yaml")` and `__import__("yaml")` with a **literal**
     argument. A computed argument is out of reach of both gates, and `pinakes.eval` is not in the
     free path's import graph — say so rather than claiming the pair is exhaustive.
   - `tests/test_paid_path.py::test_the_free_path_run_never_loads_yaml` — **this file, not
     `test_packaging.py`**: it already owns `FREE_PATH_RUN` and the subprocess harness. Predicate
     `name == "yaml" or name.startswith("yaml.")`, never a substring — the module list contains
     `pydantic_settings.sources.providers.yaml`.
   - `tests/test_packaging.py::test_every_symbol_the_ruamel_stub_declares_matches_inspect_signature`
     — import each declared symbol from the module the stub declares it in, and compare **callables**
     against `inspect.signature`. `preserve_quotes` and `width` are *instance* attributes, not class
     attributes, so `inspect.signature` does not apply and `getattr(YAML, "width")` raises: assert
     those two by setting them on an instance. A stub that **omits** a real parameter (`output`,
     `plug_ins`, `transform`) is not a mismatch — no minimal stub could pass otherwise; a stub that
     **declares one that does not exist** is.


**Tests.** Every comment test **compares file bytes** — `CommentedMap.__eq__` ignores comments, so
an equality assertion can never detect their loss.

`test_sidecar.py`: `::test_an_unknown_key_round_trips_byte_identically`;
`::test_a_comment_inside_provenance_extraction_survives_a_re_extraction` (comment on the **last key
of the nested map** — the only position that reproduces it);
`::test_a_comment_inside_the_links_block_survives_a_rewrite`; `::test_comments_survive_a_rewrite`;
`::test_quoting_style_survives_a_rewrite`;
`::test_a_value_with_spaces_past_eighty_columns_is_not_folded`;
`::test_block_scalars_and_blank_lines_survive_a_rewrite`;
`::test_yaml_1_1_scalars_are_no_longer_corrupted`;
`::test_the_users_key_order_is_preserved_on_rewrite`;
`::test_a_minted_sidecar_still_uses_canonical_order`;
`::test_provenance_first_appearing_is_appended_and_moves_no_comment`;
`::test_a_minted_title_that_looks_like_a_boolean_is_quoted` (assert it reads back as a string
**through PyYAML**); `::test_a_duplicate_key_is_refused_without_ruamels_suppression_url`;
`::test_a_string_field_that_yaml_1_2_resolves_as_a_number_is_refused`;
`::test_a_json_unencodable_extra_value_is_refused_with_a_remedy` (`!!binary`, `!!set`,
`!!timestamp`, bare date, unknown tag, tagged **key**, and **`{1: a, b: c}` — a nested mixed-key
mapping, which only `sort_keys=True` catches**); `::test_a_double_bang_str_value_is_refused`;
`::test_a_tagged_scalar_in_a_known_field_is_refused_with_a_remedy` (it bypasses the JSON check and
would otherwise surface as ``"`title` must be a string, found TaggedScalar"`` — a ruamel class name
with no remedy);
`::test_a_tagged_mapping_is_accepted_because_it_serialises`;
`::test_reordering_links_does_not_move_their_comments`;
`::test_a_two_space_indented_sequence_is_reindented` (pins ruamel's normalisation);
`::test_the_original_document_is_excluded_from_equality`;
`::test_deleting_a_commented_key_loses_one_comment_and_misattributes_another` (pins the limitation);
`::test_with_extraction_provenance_preserves_comments`;
`::test_without_extraction_provenance_preserves_comments`.

`test_sync.py::test_an_anchored_boolean_is_indexed_as_true_not_one` — the fixture nests the anchored
boolean **inside a mapping, inside a list, and inside `provenance`**, and asserts an alias too; a
top-level-only fixture passes on the shallow version;
`test_sync.py::test_a_tagged_sidecar_is_refused_at_read_not_crashed_in_json` (the regression this
check exists to prevent — without it, L5b turns today's clean `SidecarError` into a traceback);
`test_partner_kb.py::test_every_committed_sidecar_round_trips_through_read_and_write` (copy into
`tmp_path` first; **50/51**, already true on `main`, so it is a fixture-churn net, not evidence for
ruamel — assert the `pnk://self/` expansion explicitly);
`test_packaging.py::test_pyyaml_is_dev_only_never_core_and_never_an_extra` (absent from core, absent
from every extra, **present in dev** — the `pillow` precedent);
`::test_ruamel_yaml_is_a_core_dependency`; `::test_the_two_resolver_union_covers_pyyaml_1_1`;
`::test_no_module_under_src_imports_pyyaml` (AST);
`::test_every_symbol_the_ruamel_stub_declares_matches_inspect_signature`;
`test_paid_path.py::test_the_free_path_run_never_loads_yaml` (runtime).

Owned by decision 23 but landing in **L6**:
`test_cli_link.py::test_a_rel_that_looks_like_a_boolean_is_quoted`.

**Mutation targets.** Delete `preserve_quotes` → the quoting test fails. Delete `width` → the
spaced-long-value test fails. Make the known-key merge one level deep → the nested-comment test
fails. Restore `sorted(extra)` on the original-document path → the key-order test fails. Drop the
mint-quoting predicate → the boolean-title test fails. Drop the `ScalarBoolean` coercion, **or make it one level deep**, → the
anchored-boolean test fails. Drop the JSON check → the tagged-sidecar test fails. Drop
`sort_keys=True` from it → the mixed-key test fails. Reconcile `links` by index instead of by `to` → the
comment-misattribution test fails. Replace the AST scan with an import walk → the lazy-import test
fails. Revert one `replace()` to a hand-enumerated constructor → a comment test fails.

**Known limitation, pinned not fixed.** Deleting a key misattributes its leading comment to the next
key *and silently deletes that key's own comment*. Reachable via `without_extraction_provenance`.

**Docs.** `DESIGN.md` §2.2 — the deferral becomes a delivery, and §2.2 is where the *rationale*
lives. Read `docs/KB-UPDATES.md` §5 first: it already argues for `tomlkit` in core on this same
trade. · `MANIFEST.md` — *"unknown keys round-trip untouched"* → byte-identically, with the
exclusions. · `CLAUDE.md` — the new invariant. · `VERIFICATION.md`. · `STATUS.md`. · `GUIDE.md` —
its `links:` example (`docs/GUIDE.md:426-428`) uses an indentation ruamel **re-indents**, so it is the counter-example
to the invariant, not a typo. · `check.sh:109` — the comment says *"it needs PyYAML"*; item 5
falsifies it, but the `uv run` invocation stays, because ruamel is a dependency too. ·
`check.sh:9` — explains `--extra-search-path stubs` as being about a missing `py.typed`; ruamel
ships one, so the second stub exists for a different reason. · `ci.yml`'s link-density job comment.
· `MANIFEST.md` again — the JSON-encodability bound on *"your unknown keys round-trip untouched"*
is a user-facing contract change, not a wording fix. · A `changelog.d/` fragment carrying the
**three** breaking lines above **and, listed separately, the four crashes that become named
errors**.

A [`retro.d/`](../retro.d/README.md) fragment: the stub hazard, and the third instance of the
increment-shaped blind spot (both in the decision record's last section).

**Amend, do not delete.** `test_malformed_sidecars_are_rejected`'s `{id: x, : }` fixture becomes
`{id: x` — an unclosed flow map, which both libraries reject. **This must land here**: ruamel parses
the old fixture, so without the swap L5b lands with a red suite. It is the 872nd test in the
prototype's 871/872. The case exists for **branch coverage** of the parse error.

**Not touched:** `plans/v0.1.md` and `plans/v0.2.md` name PyYAML and go stale. `plans/` is
historical.

**Resolved, do not re-open:** ruff's `per-file-ignores` glob `"stubs/*.pyi"` **does** match a nested
`stubs/ruamel/yaml/__init__.pyi` — verified, no change needed.

**Verification before the interim cut.**

1. `./check.sh` green — including `ty check`, which behaves differently from pyright on stubs; 0
   pyright errors with **no suppression added anywhere**.
2. Green on all three CI legs — this changes `[project.dependencies]` and `uv.lock`.
3. **Add the assertion to `ci.yml`'s `build` job in this increment** — it asserts neither today, so
   the step is otherwise unfalsifiable: after installing the wheel, `import ruamel.yaml` succeeds
   and `importlib.util.find_spec("yaml")` is `None`.
4. `.paid-path-allowlist` byte-identical; the free-path gate green.
5. `make eval` unchanged.
6. Each new gate fails when its protection is removed.
7. `fragments.py --apply` splices L1–L5b's fragments; the CHANGELOG section covers all of them.
8. **Every command in `docs/GUIDE.md` runs as written, install line included.** This increment
   changes the runtime dependency set, so the install line is the single most likely thing to be
   wrong, and CLAUDE.md requires verifying docs by running them.
9. **`store.SCHEMA_VERSION` is still 2** — no bump, no rebuild.
10. **`pnk doctor` exits 0 on `tests/demo-kb` and `tests/partner-kb`.** L5b rewrites the sidecar
    reader and doctor reads every sidecar in both corpora — the cheapest end-to-end check there is.

**The cut itself** follows CLAUDE.md's release procedure in full: `fragments.py --apply`, bump
`__version__`, a dated `[x.y.z] — YYYYMMDD HH:MM` section **with its link definition and the
repointed `[Unreleased]` compare**, merge **from the primary checkout**, `make release-check`
*before* pushing the tag, then the GitHub release — and verify with `git tag -l`, `gh release list`
and `git merge-base --is-ancestor`. **A tag publishes to PyPI**, and PyPI does not allow re-uploading
a version.

**Then sweep the three documents a release stales**: `docs/STATUS.md`'s *Published on PyPI* table and
its roadmap row, and **`README.md`'s install lines** — which matter more at this cut than any before
it, because the dependency set changed. Verify by querying the index and installing what the docs
show, not by reading them; the JSON endpoint is CDN-cached, so cross-check `/simple/pinakes/`.

**The falsifiable exit criterion:** every committed sidecar still round-trips, no sidecar that
errors cleanly today crashes instead, and the suite is green.

The list above **is** the interim cut's verification — do not resolve it against L8's numbering.
L8's step 2 needs `pnk link`, its step 4 names `pnk link` in the free-path gate, and its step 8 is
the ClaudeKB corpus-realism check (decision 1); all three stay with L8.

---

### L5c — refuse non-string top-level keys

**Decision 19 alone.** Separated from L5b because it is the one change that is *pinakes choosing to
reject more*, rather than keeping behaviour equivalent across the library swap — so it is
independently revertible, and it closes a bug that exists **today**, not one L5b creates.

**One breaking change:** a non-string top-level key (`123: v`) is refused. It works today, unless
mixed types make `sorted()` raise — so the single-key case is the breaking one.

**What lands.** Refuse non-string top-level keys at `read()`, before `Sidecar` is constructed. **Top
level only**; nested user maps stay unconstrained, and L5b's `sort_keys=True` already catches nested
non-string keys. The remedy names the offending key and says pinakes partitions top-level keys into
its own and the user's, so each must be a string.

**Why it is not in L5b.** It makes `extra: dict[str, Any]` honest and closes a `TypeError` live on
`main` today — `id: X` plus `123: v` plus `abc: w` reads fine and dies in `sorted()`. Neither
depends on ruamel. Reverting it leaves L5b correct.

**Tests.** `test_sidecar.py::test_a_non_string_top_level_key_is_refused_with_a_remedy`;
`::test_a_single_non_string_key_is_refused_too` (it writes back fine today);
`test_doctor.py::test_a_non_string_top_level_key_is_reported_not_crashed`.

**Mutation target.** Drop the string-key check → the non-string-key test fails.

**Docs.** `docs/CLI.md` — `pnk doctor`'s new refusal class. · `MANIFEST.md`, `VERIFICATION.md`,
`STATUS.md`. · A `changelog.d/` fragment carrying the one breaking line.

**No cut** — L5b took the interim one. This rides the final cut at L8.

---

### L6 — `pnk link`

**Unblocked** — L5b delivered the comment-preserving writer, superseding decision 18. There is no
fallback path: no `pyyaml` retry, no comment-loss warning, and
`test_comments_in_the_sidecar_survive_a_rewrite` lands **passing**.

**What lands.** `pnk link <src> <dst> --rel <rel>`, writing one entry into the **source document's
sidecar only**, rename-atomically.

**`<dst>` grammar:** a path relative to the local KB root; `pnk://<kb-ulid>/<doc-ulid>`; or
`<alias>:<path>` where the alias is a `[[links.kb]]` name. Aliases and `self` resolve to ULIDs **on
write**. An unresolvable `<dst>` is refused with a typed error and a remedy.

**Per-link unknown keys round-trip.** `Link` is a two-field frozen dataclass; top-level unknown keys
survive via `extra`, per-link keys do not.

**Tests.** `tests/test_cli_link.py::test_an_alias_is_resolved_to_a_ulid_on_write`;
`::test_self_is_expanded_on_write`; `::test_each_dst_grammar_resolves`;
`::test_an_unresolvable_dst_is_refused_with_its_remedy`;
`::test_a_link_round_trips_through_sync_into_the_links_table`;
`::test_unknown_keys_inside_a_link_entry_survive_a_rewrite`;
`::test_the_write_is_atomic_under_an_interrupted_rename`;
`::test_the_source_document_is_byte_identical_afterwards`;
`::test_comments_in_the_sidecar_survive_a_rewrite` (**passing**, on L5b's writer);
`::test_every_other_line_of_the_sidecar_is_byte_identical_after_a_link_is_added`.

**Exit criteria.** `DESIGN_COMMANDS`, `IMPLEMENTED`, DESIGN §8's command list and CLAUDE.md's
`docs/`-ownership amendment all land here.
**Docs:** `docs/CLI.md`, `docs/GUIDE.md`, `docs/MANIFEST.md`, `docs/DESIGN.md` §2.2,
`docs/STATUS.md`, a `changelog.d/` fragment.

**Also lands.** `tests/free_path_run.py` gains `pnk link` — L8's verification step 4 checks that the
gate covers it, and no earlier revision assigned the edit.

**Mutation targets.** The alias→ULID resolution; the per-link `extra` merge; the atomic rename.

---

### L7 — `pnk doctor`: link coverage and cross-KB resolution

**What lands.** `doctor.py`'s `"cross-KB (unchecked until the links release)"` becomes a real check.
Link coverage counts **authored links only** — the same population as L1's gate, so the number a
user reads and the number the gate enforces cannot differ. Highest-degree authored targets reported.
**Zero authored links KB-wide** is a WARN nudge — not a per-document count, which L1's ≤ 35% cap
guarantees would fire on both committed corpora by construction.

**Severity:** absent linked-KB path → WARN; a `pnk://` target absent from a KB that did resolve →
WARN with the count; a malformed `pnk://` in a committed sidecar → FAIL; an absolute
`[[links.kb]] path` → WARN.

**Tests.** `tests/test_doctor.py::test_link_coverage_counts_authored_links_only`;
`::test_a_dangling_cross_kb_target_warns_with_a_reason`; `::test_a_malformed_pnk_uri_fails`;
`::test_an_absolute_linked_kb_path_warns`; `::test_a_kb_with_no_authored_links_nudges`.

**Docs:** `docs/CLI.md` (doctor's checks), `docs/STATUS.md`, a `changelog.d/` fragment.

---

### L8 — Verification of the whole, and the links release's **final** cut

**Two cuts, not one** (decision 27). **L5b** takes the **interim** cut and runs steps 1, 3, 4, 5, 6
and 7 below; step 2 needs `pnk link`, and step 8 is the ClaudeKB corpus-realism check, which L8
keeps. L8 takes the
**final** cut and runs all eight. `tools/fragments.py --apply` runs at *each* cut and deletes what it
consumes, so the interim cut's CHANGELOG section carries L1–L5b and the final one carries L6–L8 —
neither carries both.

**Verification** — run, not reasoned about:

1. `./check.sh` green on all three CI legs; CI green on the merge.
2. A fresh KB works: `pnk init`, add a document, `pnk link` to a second KB, `pnk sync`, `pnk search`,
   `pnk links` — executed. (If L6 was deferred, the link is hand-authored and that is recorded.)
3. Every command in `docs/GUIDE.md` runs as written, install line included.
4. `.paid-path-allowlist` byte-identical; the free-path gate covers `pnk link`, `pnk links` and an
   MCP handshake that **invokes** `pinakes_links`.
5. `make eval` unchanged — this release touches no retrieval, so any movement is a defect. L5b
   swapped the loader `load_questions` uses; the swap was measured inert on both committed
   `questions.yaml`, so movement here would mean that measurement was wrong.
6. **`store.SCHEMA_VERSION` is still 2.**
7. `pnk doctor` exits 0 on both corpora — "clean" means no FAIL. WARNs are possible and do not
   block; the zero-link nudge is KB-wide (L7), so it does not fire on a corpus with any authored
   links at all.
8. The ClaudeKB realism check is **run, or declined in writing**.

**The cut.** `python3 tools/fragments.py --apply` (splices `changelog.d/` and `retro.d/`, deleting
what it consumes — a release that skips it and runs it later splices into the wrong version), bump
`__version__`, move `[Unreleased]` into a dated section **and add its link definition at the foot,
repointing `[Unreleased]`'s compare** (`fragments.py --apply` splices entries and does not touch the
footer), commit, **merge from the primary checkout**,
push, `make release-check`, tag, push the tag, create the GitHub release. Then `git tag -l`,
`gh release list` and `git merge-base --is-ancestor` to verify it happened.
**Check `origin/main` for the number first** — 0.3.0 shipped mid-plan, and I8/I9 may cut another.

---

## Increments — the graph release

### G1 — Is the eval reproducible? (measure, then decide)

**Measure before fixing** — decision 15. The previous revision specified tiebreaks at three sites
and pass 3 showed they were a provable no-op: cross-document ties are already totalised by
`documents.path` (`UNIQUE`), and within a document rowid order *is* ordinal order in every write
path that exists (`replace_chunks` enumerates; the rebuild carry-over selects `ORDER BY ordinal`).
The instability a rebuild *could* introduce is upstream — in `_lexical`'s `ORDER BY score` and
`_vector`'s unstable `argsort`, which set the RRF ranks that determine the fused scores. A final
tiebreak cannot reach it.

**What lands.** A test that runs the golden set, edits a document, re-syncs, `--rebuild`s, and
compares **per-question outcomes** (not just aggregates), plus the same across two machines' CI legs.
If it is already reproducible, that is the finding and nothing else changes. If it is not, the fix
is scoped by what the measurement shows and lands here with per-class numbers.

**Tests.** `tests/test_search_reproducibility.py::test_outcomes_survive_an_incremental_sync_and_rebuild`;
`::test_outcomes_are_identical_across_repeated_runs`.

**Exit criteria.** The reproducibility gate in `check.sh` **and** its own CI job. A written statement
of what was measured, in `docs/STATUS.md`.
**Docs:** `docs/STATUS.md`, a `changelog.d/` fragment, and a `retro.d/` fragment if the measurement
contradicts the previous revision's assumptions.

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
| authored | doc ↔ doc | 2.0 — **read from `links`, not copied into `edges`**, so an authored link has one home. The channel unions it in by resolving each `links` row's `(kb_id, doc_id)` pair to its `doc` node via `nodes(kind='doc', key=<ulid>)`; `pnk doctor` reports the `origin='sidecar'` subset, and the difference between the two populations is stated in L7 rather than discovered |

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

### G4 — `requires_pinakes`

**What lands.** `[kb] requires_pinakes`, read in a **pre-pass before strict manifest validation**, so
a manifest from a newer pinakes can say so before the strict validator rejects its unknown keys.

**What it does not do.** It cannot explain a key retroactively: a pinakes built before this
increment has no pre-pass and fails on `requires_pinakes` itself. It only ever helps for keys added
*after* it ships — which is why `adjacent_k` and `graph_channel` stay out of the template in both
releases (L3), rather than being deferred to this increment as if it licensed them.

**Tests.** `tests/test_manifest_compat.py::test_a_manifest_requiring_a_newer_pinakes_names_the_version`;
`::test_the_pre_pass_runs_before_strict_validation`;
`::test_an_absent_requires_pinakes_is_not_an_error`.

**Exit criteria.** The floor is read from `pinakes.__version__`, and **the shipped message naming the
released number is verified at whichever cut ships this increment** — G6 normally, the fallback
release if G3/G5 do not run. Naming only G6 would leave it unverified on the path where G6 never
happens.
**Docs:** `docs/MANIFEST.md`, `docs/DESIGN.md` §2.1, `docs/KB-UPDATES.md`, `docs/STATUS.md`, a
`changelog.d/` fragment.

**Mutation target.** The pre-pass ordering.

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
`reverse-scan` row is hand-authored too — by the partner KB's human. It is inert today (a foreign
`src_kb_id` resolves to no local `doc` node), and saying so here is what keeps it inert.

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
   (`eval.py:233`) and the regression is a no-answer question *becoming* a hit**. The arithmetic is
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
   (`eval.py:325`) — and that is desirable, since it ratchets those guards up. What it may not do is
   swallow a regression. Rewriting `baseline.json` disarms *every* guard in it, so all six of
   `compare()`'s families are named here with the direction `eval.py` actually checks:

   | Metric | A regression is | Verdict |
   |---|---|---|
   | `false_abstain` | a rise | the only term the re-baseline may absorb, and only its newly-found-at-low-confidence part |
   | `false_confidence` | a **rise** | **stop** |
   | `by_kind` | a per-class drop, **or a class vanishing** (`eval.py:304-313`) | **stop** — discharged by clause 2 |
   | `recall_at_k`, `mrr`, `rerank_precision` | a drop | **stop** |
   | `confidence_coverage` | a **drop** | bookkeeping — cannot move under a channel-only change |
   | question count | a drop | bookkeeping — the set does not resize when a default flips |

   **`by_kind` was the omitted one, and it is the only family a channel actually moves** (pass 7).
   The two now marked bookkeeping cannot fire here: `_confidence()` returns `UNKNOWN` only for no
   passages, an absent `[retrieval.confidence]`, `rerank != "local"`, or a fingerprint mismatch
   (`search.py:409-427`) — all manifest properties, and a third RRF input cannot make a non-empty
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
| Link coverage reported as the ceiling | DESIGN §6.2 | L7 | `test_link_coverage_counts_authored_links_only` |
| The zero-link nudge | APPROACH §3 | L7 | `test_a_kb_with_no_authored_links_nudges` |
| Absolute linked-KB paths are a publication hazard | DESIGN §4.7 | L7 | `test_an_absolute_linked_kb_path_warns` |
| Aliases never inside a `pnk://` URI | DESIGN §2.2 | L6 | `test_an_alias_is_resolved_to_a_ulid_on_write` |
| Comment-preserving sidecar writer | DESIGN §2.2 | **L5b** | `test_comments_survive_a_rewrite` |
| An unknown key round-trips **byte-identically** | decision-ruamel-yaml | L5b | `test_an_unknown_key_round_trips_byte_identically`, `test_every_committed_sidecar_round_trips_through_read_and_write` |
| `extra` is no longer corrupted by YAML 1.1 | decision-ruamel-yaml | L5b | `test_yaml_1_1_scalars_are_no_longer_corrupted` |
| The user's key order survives a rewrite | decision-ruamel-yaml | L5b | `test_the_users_key_order_is_preserved_on_rewrite` |
| A duplicate key is a hard error, not a silent last-wins | decision-ruamel-yaml | L5b | `test_a_duplicate_key_is_refused_without_ruamels_suppression_url` |
| A non-string top-level key is refused | decision 19 | **L5c** | `test_a_non_string_top_level_key_is_refused_with_a_remedy`, `test_a_single_non_string_key_is_refused_too` |
| `extra`/`provenance` values are JSON-encodable | decision 26 | **L5b** | `test_a_json_unencodable_extra_value_is_refused_with_a_remedy`, `test_a_tagged_sidecar_is_refused_at_read_not_crashed_in_json` |
| Every scalar pinakes writes survives a 1.1 **and** a 1.2 reader | decision 23 | L5b, L6 | `test_a_minted_title_that_looks_like_a_boolean_is_quoted`, `test_a_rel_that_looks_like_a_boolean_is_quoted` |
| A comment inside a nested known-key block survives | decision-ruamel-yaml | L5b | `test_a_comment_inside_provenance_extraction_survives_a_re_extraction` |
| `src/` never imports `pyyaml` again | decision 21 | L5b | `test_no_module_under_src_imports_pyyaml` (AST), `test_the_free_path_run_never_loads_yaml` (runtime) — neither alone suffices |
| A custom-tagged mapping is accepted, being serialisable | decision 26 | **L5b** |
| An anchored or aliased boolean is indexed as `true` | pass 4 | L5b | `test_an_anchored_boolean_is_indexed_as_true_not_one` |
| An `!!str` value is refused | decision 26 | L5b | `test_a_double_bang_str_value_is_refused` | `test_a_tagged_mapping_is_accepted_because_it_serialises` |
| The links release cuts twice | decision 27 | L5b, L8 | L5b's verification list; L8's step 1 |
| The ruamel stub describes the real library | decision 20 | L5b | `test_every_symbol_the_ruamel_stub_declares_matches_inspect_signature` |
| Unknown per-link keys round-trip | DESIGN §2.2 | L6 | `test_unknown_keys_inside_a_link_entry_survive_a_rewrite` |
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

| When | What |
|---|---|
| 20260729 02:52 | Written. Seven decisions with the user; no adversarial pass |
| 20260729 03:31 | **Pass 1** — 22 HIGH. Three findings were live defects on `main`, fixed there first (`b637be4`, released in 0.3.0). Release split in two; `entities`/`concepts` cut |
| 20260729 04:05 | **Pass 2** — 26 HIGH. Six of pass 1's fixes were wrong, two self-refuting. Decisions 11–13 |
| 20260729 04:27 | **Pass 3** — 24 HIGH across two reviewers. Three collapsed into one root cause: **the links release never needed the golden set**, and forcing cross-KB questions through a structurally single-KB harness produced a class pinned at 0.00 or 1.00 by construction. Cross-KB eval cut entirely (decision 14); all eval work moved to the graph release; the determinism increment became a *measurement* after its proposed fix was shown to be a provable no-op (decision 15); the per-question artifact the sign test needs was found to exist nowhere and given an owner; twelve increments were still instructing a future agent to edit `CHANGELOG.md`, forbidden by a convention that landed while this plan was being written. **Pass 4 required** |
| 20260729 04:46 | **Pass 4** — two reviewers, **13 HIGH, down from 24**, and no self-refuting fixes for the first time. Five findings collapsed into decision 16: the traversal surface serves **documents only**, so structural nodes (which have no `doc_id`) never reach the pinned neighbour shape, G3 becomes genuinely inert, and G5 flips no filter. Cross-KB neighbours are terminal, and the Goal was a one-hop claim all along (the *reason* this pass gave was wrong — see 05:06). Also: `frontier` was contract text with no owner and no definition, now L3's with stated reasons; G5's clause 3 conflicted with `compare()`, a hard CI gate, so turning the channel on re-baselines in the same commit; the headroom precondition measured failure without reachability, and APPROACH §9's channel-reachable ceiling comes back as an in-memory probe; the node identity scheme spanned five incompatible id spaces and is now specified; and G1/G2/G4 have a stated fallback if the precondition fails. **Pass 5 required**, scoped to these seams |
| 20260729 05:06 | **Pass 5** — **3 HIGH, down from 13.** All three on the pass-4 seams. Decision 16's *conclusion* survived but its *premise* did not: the plan claimed K's index has nothing to walk past a cross-KB neighbour, and `store.py` says a reverse link's source lives in another KB — so the hop is walkable and terminality is a policy needing an explicit suppression, which no test or mutation target had. The real reason to stop is partiality, not emptiness, and the user reconfirmed on the corrected basis. Whether authored `doc ↔ doc` edges are in the channel was never stated while three things depended on it — they are, and stating it exposed a circularity (the gate satisfiable by hand-authored links bridging hand-authored questions) now guarded by reporting reachability and the gate with and without them. And the clause-3 remedy had disarmed `compare()`'s guard on `false_confidence`, which clause 4 restores. **Pass 6 required** |
| 20260729 06:03 | **Pass 7** — two reviewers, **6 HIGH** (4 on L2, 2 on G5), and the verdict on each half was *not implementable as written*. Both halves failed the same way: a rule that was correct in its conclusion and unenforced in its mechanism. **L2** deleted every reverse row for a partner before re-walking it, so any mid-walk failure was the mass deletion the same section forbids; a delisted partner's rows were unreachable by the only delete that existed; the scan could not compute `src_kb_id` from sidecars at all (a sidecar does not carry its KB's ULID), and the natural workaround — reusing the local `owner=` — re-creates a defect already fixed once, silently retargeting a partner's `self` links at us; and the failure taxonomy's only recording channel makes `pnk sync` exit non-zero on a git hook. **G5** made the *without*-authored run binding while shipping the *with*-authored configuration, so a channel that helps only through hand-authored links and does nothing in its shipped form passes three green clauses and becomes the default; G2's headroom threshold never said which of its two reachability numbers counted, so the schema could be bumped irreversibly on the one that licenses nothing; and clause 4 promised six `compare()` families, named five, and the one it omitted (`by_kind`) is the only one a channel actually moves — while two it did name cannot fire at all. Also: the gate had no code home, its *before* leg was taken across a schema bump and a forced rebuild, and nothing forbade re-authoring the questions until the probe passed. Every claim was verified against the source before being accepted; two of pass 6's own justifications were false about the code (a "weight-2.0" column that does not exist, and an alias collision `manifest._reject_duplicates` already refuses). **Pass 8 not required for L1–L8**: L2's findings are localised and now testable, and the build proceeds. G5's clauses are re-reviewed before G5, not before L1 |
| 20260729 05:43 | **Pass 6** — **2 HIGH**, both narrow, and the pass-5 fixes verified correct. Gate clause 4 stated one of its two guards backwards: it made a *rise* in `confidence_coverage` a stop, but a rise is an improvement and the metric is 1.0 in the baseline — so the clause could never fire while the guard the re-baseline actually removes (a drop) stayed unrestored. It now names all six `compare()` families with the direction `eval.py` checks. And the anti-circularity guard was asserted to live in G5 and appeared only in G2 and G3, so an engineer building G5 would have computed the sign test once over all edges including L1's hand-authored links, passed, and flipped the default. G5 now computes it twice and ships `off` if only the authored run passes. **Pass 7 required**, scoped to G5's clauses and L2's delete |
| 20260731 06:25 | **Decision 18 superseded; L5b inserted.** The swap was prototyped against the real suite (871/872 pass) before being specified, which corrected four of the decision's own claims and surfaced a live bug on `main`: a non-string top-level key reads fine and kills `write()` in `sorted()`. Decisions 19–22 |
| 20260731 07:10 | **Pass 1 on L5b — 8 HIGH, *not implementable as written*.** Two findings changed the design: 1.1 → 1.2 runs **both** ways (`1e3`, `0o17` sync today and hard-error after), and an unknown YAML tag becomes an unhandled `TypeError` out of `pnk sync`. Three of the specifying pass's own measurements fell — PyYAML *does* fold at 80, minted output matches 49/57 shapes not 7/7, and `cast(Any, instance)` satisfies pyright. `write()`'s spec permitted rebuilding known keys wholesale, destroying nested comments, with no test covering it. Decisions 23–25 |
| 20260731 07:45 | **Pass 2 — 8 HIGH, and two of pass 1's decisions fell.** Decision 25 was impossible: L1–L4 are already on `main`, so any tag at L5b ships them whatever it is named — replaced by 27, the links release cutting twice. Decision 24's tag detector refused the harmless `!!str` and missed `!!binary`/`!!set`/`!!timestamp`, which already crash `pnk sync` — replaced by 26, one JSON-encodability rule. The pass-1 gate was wrong twice (loads `pypdfium2`; blind to the lazy import that is its whole justification), the key merge was one level deep with both its tests passing on the defect, and indentation turned out not to be preserved — the counter-example being a line the same pass had filed as a cosmetic typo |

| 20260731 07:52 | **Pass 3 — 7 HIGH**, and the worst was introduced by the commit that existed to remove ambiguity. Decision 23's disambiguated predicate named `yaml.resolver.Resolver`, running inside `write()` — while item 1 removes `pyyaml` from the runtime dependencies and item 7 adds a gate built to fail on that exact import, so the increment could not be green and correct at once. Measured redundant as well: over 38 probes there is no value PyYAML 1.1 calls non-`str` that both ruamel versions call `str`. Two more the plan had never considered: a boolean carrying an **anchor** returns `ScalarBoolean`, an `int` subclass, which passes decision 26 and lands in the index as `1` where PyYAML wrote `true`; and the known-key merge rule demanded nested deletion (`provenance` must lose `extraction`, or `--force` silently fails) while forbidding it (a `links[]` entry must keep its unknown keys) in one sentence. Reconciling `links` **by position** was measured to misattribute the user's comments onto different links on reorder and delete them on shrink — now keyed on `to`. Also: `CLAUDE.md`'s release rule tells an interim cut to drop a release name L8 needs back; the signature gate cannot reach `preserve_quotes`/`width`, which are instance attributes; the AST predicate as written false-positives on `from ruamel import yaml`; and the compaction two commits earlier had split the releases table with a paragraph, so the graph-release row rendered as literal text |
| 20260731 08:05 | **L5b split into L5b and L5c (decision 28).** Not a finding — a response to the trajectory. Three passes on one section returned **8, 8 and 7 HIGH**, and each pass's worst finding was in the previous pass's *fix*: pass 3's was a predicate the disambiguation commit had introduced, which imported `pyyaml` into `src/` while the same increment removed it from the runtime dependencies and added a gate against exactly that import. Every concern in the section was individually settled; the churn was at the **interfaces** between eight of them bundled into one increment. The seam is *what the library does* (L5b — the swap, the round-trip, quoting, the `ScalarBoolean` coercion, the stub, the gates; two breaking changes, both intrinsic to ruamel; no cut) versus *what pinakes chooses to reject* (L5c — decisions 19 and 26; two more breaking changes; takes the interim cut). L5c is independently revertible, and L5b's exit criterion becomes falsifiable in one sentence: every committed sidecar still round-trips and the suite is green |
| 20260731 08:18 | **The split's seam was wrong, and moving one decision fixed it.** Asked to confirm L5b was ready, I checked instead of asserting, and found two defects. **L5b alone would have landed with a red suite** — the `{id: x, : }` fixture amendment had been carved into L5c, but ruamel *parses* that fixture, so the test fails the moment the swap lands; it is the 872nd test of the prototype's 871/872. And **L5b alone was a regression**: PyYAML refuses an unknown tag today as a clean `SidecarError`, ruamel accepts it, so without decision 26 the sidecar reaches `json.dumps` and `pnk sync` exits on an unhandled `TypeError` — measured. Decision 26 was therefore never "a refusal pinakes chooses"; it is **required to keep behaviour equivalent**, and it moves into L5b along with the interim cut. L5c reduces to decision 19 alone — 32 lines, the one change that genuinely adds a refusal, depends on nothing in L5b, and closes a `TypeError` live on `main` today |
| 20260731 08:00 | **Independent review of L5b — five findings, one of which changed the code.** Decision 26's check was specified over *values*; measured, a per-value check **accepts** `{123: v, abc: w}` and the `TypeError` survives, because the failure is a comparison *between* keys. It now encodes the **assembled mapping**, mirroring what `_metadata()` hands `store.dumps_metadata`. Three were false claims headed for the changelog: `sort_keys=True` catches **mixed**-type keys only — a *uniformly* int-keyed mapping is accepted and silently coerced at any depth, covered by neither increment and now a stated residual; `!!str` is the only **working** tag that breaks, not the only tag that works (`!!int`, `!!float`, `!!bool`, `!!seq`, `!!map` all survive); and the documented widening is for **custom**-tagged collections, since `!!map` and `!!seq` were never refused. The record's decision 23 still named `yaml.resolver.Resolver` two commits after the plan removed it — the exact neighbourhood miss the convention added this morning exists to catch. Also: `ScalarBoolean` arrives via an **alias** as well as an anchor, so the coercion test asserts both |
| 20260731 08:12 | **Pass 4 — 6 HIGH, but the seam and L5c both cleared.** The reviewer enumerated every shape under both libraries and confirmed **no shape regresses at L5b** and that reverting L5c leaves L5b correct; it **found nothing wrong in L5c**. What it found in L5b was worse than a wording defect: **`tests/free_path_run.py` already imports PyYAML and writes a sidecar with `yaml.safe_dump` at `:160`**, so the runtime gate is red on day one and, after the swap, that line is the only PyYAML sidecar writer left in the repo — the exact divergence the gate exists to forbid. The section had reasoned carefully about false positives and never checked the true positive. **The `ScalarBoolean` coercion was one level deep**, and `_metadata()` is a shallow spread, so a nested or `provenance`-held anchored boolean still indexes as `1`; both the named test and the mutation target passed on the defect — the third instance of the same increment-shaped blind spot in one section. The stub list was declared *complete* and omitted `ScalarBoolean` and `ScalarNode`, both of which the increment's own code needs. Item 5's divergence paragraph still attributed L5b's changes to L5c. And the interim cut — the project's first cut of this release, publishing to PyPI — claimed L8 steps it never listed: the GUIDE install line (which this increment changes), `SCHEMA_VERSION == 2`, and `pnk doctor` exiting 0 on both corpora, plus no cut procedure and no three-document stale sweep. Also: the verification table named a renamed test, and `tests/test_verification.py` hard-fails on an unresolvable one; the 871/872 figure predates L5 and the suite now collects **1027**, so the one falsifiable exit criterion rested on a number from a different tree |
