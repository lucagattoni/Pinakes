# The graph release — implementation plan

**Status:** draft — no adversarial pass yet

**Date:** written 20260729 02:52

**Source of truth:** [`docs/DESIGN.md`](../docs/DESIGN.md). Where this plan and DESIGN disagree on
anything *not* listed in the amendments table below, DESIGN wins and this plan has a bug.

**Written against** [`docs/graph/PINAKES_APPROACH.md`](../docs/graph/PINAKES_APPROACH.md) (six
adversarial passes; §10 is the build order this plan expands), the R1–R7 findings in
[`docs/graph/GRAPH_RAG.md`](../docs/graph/GRAPH_RAG.md), and
[`docs/RETROSPECTIVES.md`](../docs/RETROSPECTIVES.md).

**No version number appears in this plan.** Unbuilt work is named, never numbered
([CLAUDE.md](../CLAUDE.md), [STATUS](../docs/STATUS.md#release-roadmap)). Increment IDs are `G1`–`G12`
and name work inside this plan, not a release.

**Baseline:** the paid-extraction release, `main`, clean. That release does not exist yet — I7c is
in flight and I8–I9 follow — so **increment G1 begins by re-reading the baseline**, not by assuming
it. `schema_version` is 2 today and G9 bumps it to 3; if a paid-extraction increment bumps it first,
G9 takes the next number and the amendments table below is wrong until corrected.

---

## Goal

A question answered in one KB can reach evidence in another, because a human said the two documents
were related and pinakes remembered. The release ships the **authoring surface** (`pnk link`), the
**traversal surface** (`pinakes_links`, reverse-scan), and the **structural edge fabric** that makes
traversal useful when nobody has authored anything — each free, each measured against a golden set
that can actually tell whether it helped.

**Nothing here can spend money.** No paid entry point is added, `.paid-path-allowlist` is untouched,
and the four gates in `check.sh` must stay green throughout without amendment. The graph release is
the first body of work since the budget machinery landed that is free end to end, and that is a
property to verify rather than assume — see G12's verification.

---

## Decisions taken

Settled by the user 20260729 02:30–02:50. Each is load-bearing below.

| # | Decision | Consequence |
|---|---|---|
| 1 | **A second synthetic KB is committed, and it is deliberately sparse.** A hand-adopted ClaudeKB corpus is an optional, human-gated realism check that is reported but never committed | G1. CI can gate cross-KB behaviour reproducibly; §3's "authored links are sparse, precious signal" is honoured by the corpus rather than contradicted by it |
| 2 | **One release, with an internal cut point after the links surface (end of G8).** If the expansion channel stalls or fails its gate, the links half ships alone | G8. The cut criteria are written *before* G5 starts, not discovered at G8. Precedent: 0.2.0 was cut at I5, mid-plan, for exactly this reason |
| 3 | **The golden set grows to ~25 multi-hop questions, most of them cross-KB**, plus a `simple-lookup` class; the baseline is re-cut **once**, with the shift explained | G4. At today's n=5 one question is 20 points against §9's 5-point gate; at n=25 it is 4. Cross-KB questions are naturally multi-hop, so the demo corpus grows only modestly |
| 4 | **This release absorbs the minimum of [KB-UPDATES](../docs/KB-UPDATES.md): the `requires_pinakes` pre-pass and rebuild guidance.** `pnk upgrade` stays template-release work | G10, landing beside G9's `schema_version` bump — the moment every existing KB is forced to rebuild is the moment a version-compatibility message earns its place |
| 5 | **`pnk link` writes forward only, directly, into the source document's sidecar.** The reverse side is computed by reverse-scan (DESIGN §6.2) | G5. No inverse-relation vocabulary is invented, no second file can disagree, and a link has one home. `pnk sync` already writes sidecars unasked; the user typed the semantics here |
| 6 | **PPR (§4B) and the `[ner]` extra (§3) are out of this plan.** §10 lists them as staged and eval-gated, not scheduled | Neither is specified below. §4B already holds HippoRAG 2's measured recipe and §9 holds the gate; if the gate fires, that earns its own plan |
| 7 | **The plan is adversarially reviewed by fresh subagents until a pass is clean**, before G1 begins | The reviewer must not be the author. CLAUDE.md's own finding: tests and plans written by the reasoning that wrote the code inherit its assumptions |

**Derived, not chosen.** `schema_version` bumps to 3 when the edge tables land (G9) and every KB
rebuilds — the no-migration invariant, not a decision. The plan file is
`plans/graph-release.md` because a number is not available for unbuilt work.

---

## What this plan deliberately does NOT decide

Named so that a later increment does not quietly absorb them:

- **PPR / the `ppr` channel value** — decision 6. `[retrieval] graph_channel` is specified below as
  `"off" | "expand"`; the `"ppr"` value is added by the plan that implements it, not reserved here.
- **The `[ner]` extra and `mentions` edges** — decision 6. The node model in G9 is written so that
  entity nodes can be added without reshaping it, and that is the whole accommodation.
- **`pnk adopt`** — template-release work (§8, §10). G1 hand-authors its corpus; no adoption
  machinery is built or designed.
- **`pnk ask --deep`, the write-back, `origin: deep`** — the deep release. The sidecar link schema is
  **not** extended with a provenance field here.
- **Federated / fan-out query** — DESIGN §6.2's stated limitation stands. A question must start in
  one KB and travel a link. G4's eval scores exactly that, and no more.
- **A graph query language, a graph database, migrations** — §7, permanently.

---

## Ground rules (apply to every increment)

- **The gate is an artifact, not a list of commands.** `./check.sh` passes immediately before every
  `git commit`, and every new gate is added *to that script*. New gates and their owners:
  link-density (G1), two-KB eval (G4), traversal-cap (G6).
- **A gate that cannot run must say so and still be a gate.** The two-KB eval needs both corpora
  synced; it skips with a printed reason if a corpus is absent, never silently, and a test asserts
  the printed reason.
- **Worktree + branch per increment**, `YYYYMMDD_HHMM-g<N>-<slug>`. Another agent is working this
  repo concurrently — `git fetch` and re-read `origin/main` at the start of every increment, per
  CLAUDE.md's landing rules.
- **No inline type suppressions** (v0.1 rule 7). The traversal core's node-kind unions are the
  temptation here; narrow with an explicit kind check, never a cast.
- **The fixture is not the algorithm** (v0.1 rule 5). The link corpus in G1 is authored from an
  institutional scenario, never generated by walking the edge deriver; a traversal test's expected
  neighbour set is written by hand from the corpus, never by calling the traversal.
- **Retrospectives are an input.** Re-read `docs/RETROSPECTIVES.md` at the *start* of each
  increment; land findings and fixes as their own commit.
- **Break the code on purpose before review.** For each increment's 3–5 most safety-critical
  assertions, mutate the source, confirm the *right* test fails, restore. Per-increment targets are
  named below; a green suite proves the tests ran, never that they can detect the defect.
- **Every retrieval change reports before/after golden-set numbers in its commit message**
  (CLAUDE.md). G11 is the only increment that changes retrieval; G9's edges are inert until it.
- **Docs land with the code**: the surface's doc home, `--help`, `docs/STATUS.md`'s row and the
  CHANGELOG `[Unreleased]` line in the same commit as the behaviour.

---

## DESIGN.md amendments

This plan takes the design past what §8's graph rows say. Every divergence is here; anything not in
this table is a bug in the plan.

| § | Amendment | Lands in |
|---|---|---|
| §3 Storage | Adds the node model and the `nodes` / `edges` tables; `schema_version` 3 | G9 |
| §4.1 | The free pipeline gains an optional third channel into RRF, default off | G11 |
| §4 (new §4.8) | The graph channel: bounded expansion, depth in *logical* hops, fan-out caps, visited-edge dedup, membership exclusion | G11 |
| §6.2 Cross-KB links | "Reverse links are computed by scanning" becomes built rather than designed; the failure taxonomy gains the `unresolved` reason strings the tool returns | G2 |
| §7 Quality | The golden set gains a `simple-lookup` class and grows its multi-hop class; per-class reporting is the gate's unit | G4 |
| §8 Delivery plan | The graph rows move from planned to shipped; the staged row is unchanged | G12 |

**Not amended, deliberately:** §2.2 (the sidecar link schema is already correct and gains no field),
§5 (no paid path is added), §9's risk table (nothing here changes the risk posture — the loop stays
with the caller, R6).

---

## Increments

### Phase 1 — measure before you build (G1–G4)

Nothing in this phase changes what a query returns. It builds the corpus and the instrument, because
every gate downstream is meaningless without them.

---

### G1 — The partner KB: a second synthetic corpus, sparse by design

**What lands.** `tests/partner-kb/` — a synthetic corpus for a partner museum that genuinely
transacts with the archive in `tests/demo-kb/`: outward and inward loans, courier and condition
reporting, a shared emergency plan, a joint digitisation programme. ~18–22 documents, its own
`pinakes.toml` with a fresh KB ULID, its own sidecars.

Why a partner museum and not an arbitrary second corpus: `tests/demo-kb/docs/loans-inward.md` and
`loans-outward.md` already exist, so the cross-institution links are the ones the scenario *forces*,
not ones invented to give the traversal something to walk.

**Both corpora gain authored links, and stay sparse.** The demo KB has **zero** today — every
sidecar lacks a `links:` key, so `pnk doctor` reports `none authored (0 of N documents linked)`.
That is the missing corpus for the highest-trust edge class, and it is missing single-KB as well as
cross-KB. Links are authored on **≤ 35% of documents in each KB**, of the weakest useful kind
(`cites`, `related`, `supersedes`), forward-only from each side — §3's finding is that real authored
links are scarce, and a tidy dense synthetic graph would validate the code while hiding exactly the
failure mode the research predicts.

`[[links.kb]]` entries in both manifests map each KB's ULID to a local path.

**Tests.** Both corpora load and validate; every sidecar ULID is well-formed and unique across both
KBs; the partner corpus contains no PII, credentials or non-synthetic content (this repo is public);
`pnk sync` indexes both cleanly.

**New gate (`check.sh`).** *Link density*: fails if either corpus exceeds 35% linked documents, so a
later increment cannot quietly make the graph unrealistically dense to help a metric.

**Mutation targets.** The density gate's comparison; the cross-KB ULID uniqueness assertion.

---

### G2 — Reverse-scan and `kb_refs`: DESIGN §6.2 made real

**What lands.** `pnk sync` scans each linked KB's **committed sidecars** (`docs/**/*.pnk.yaml`) —
never its index, which is gitignored and absent in a fresh clone — and writes inbound edges as
`links` rows with `origin = 'reverse-scan'`, caching the scan in `kb_refs`.

The schema has carried `origin IN ('sidecar', 'reverse-scan')` and an empty `kb_refs` table since
v0.1 (`store.py:103`). Nothing has ever written the second value. **No schema change is needed**,
which is what makes the G8 cut point a release that requires no rebuild.

**Failure modes are recorded, never dropped** (§6.2): an unresolvable KB id, an unreachable path, a
`pnk://` target whose document no longer exists. Each carries a reason string, and those strings are
the same ones `pinakes_links` returns as `unresolved` in G6 — one vocabulary, defined here.

**Tests.** Two-KB fixture: inbound rows appear with the right origin and direction; a linked KB
whose path does not exist degrades to a recorded reason rather than an exception; a stale `kb_refs`
entry re-scans; `--rebuild` reconstructs reverse rows from sidecars alone.

**Mutation targets.** The `src_kb_id` assignment (a reverse edge whose source KB is wrong is
indistinguishable from an outbound one — the comment on `store.py:101` says exactly this); the
scan's "sidecars, not index" path selection.

---

### G3 — The traversal core, pure (rule 11: the pure half)

**What lands.** `graph/traverse.py` — bounded neighbour expansion over an edge-provider protocol,
with no SQLite in it. The SQLite provider is a thin adapter. This is what makes G4's eval and G6's
tool call the *same* code rather than two implementations that drift.

The rules it enforces, all from §4A and §5:

- **Depth counts logical hops** — chunk-or-doc to chunk-or-doc. Membership edges and hub-node
  pass-throughs are depth-free. Counted in physical edges, `chunk→doc→doc→chunk` would strand the
  highest-trust authored edges beyond depth 2, which cannot be the intent.
- **Per-node fan-out capped** at `adjacent_k`, neighbours ranked before truncation.
- **Visited-*edge* dedup**, so a hub expands once globally rather than once per encounter.
- **`unresolved` is returned, never dropped**, carrying G2's reason strings.
- **`truncated` is set** whenever a cap bit, so a caller narrows instead of paging.

**Tests.** Hand-authored expected neighbour sets over G1's corpus — written from the corpus, never
by calling the traversal. A hub with more neighbours than `adjacent_k` truncates and says so; a
diamond-shaped link graph visits the shared node once; a cycle terminates; depth is counted in
logical hops (the test that fails if physical-edge counting creeps back in).

**Mutation targets.** The depth comparison; the `adjacent_k` truncation; the visited-edge set
insertion (deleting it must fail a test, not merely slow one down).

---

### G4 — Two-KB eval, the grown golden set, and one re-baseline

**What lands.** The eval harness learns a second KB, the golden set grows, and the baseline is
re-cut exactly once.

**How a cross-KB question is scored — the honest part.** Pinakes has no fan-out query and this
release does not add one (§6.2). So a cross-KB question is scored as **the loop the design tells
callers to run**: search the origin KB, take one traversal hop with G3's core, and ask whether the
union covers `expect`. Anything more generous would measure a federated retrieval pinakes
deliberately does not build.

- `expect` entries accept a `pnk://` URI or a `<kb-alias>:<path>` form; an entry that resolves to
  nothing **fails loudly** rather than scoring zero and looking like a retrieval miss.
- The `multi-hop` class grows to ~25, most of them cross-KB.
- A new `simple-lookup` class (~20) covers single-document factual questions in both lexical and
  paraphrase phrasings, sized so the class sits *below* ceiling — `lexical` is already at 1.0, and a
  class pinned at ceiling can only ever show damage.
- CI's `eval` job (`ci.yml:77`) syncs both KBs.

**The re-baseline, and its safeguard.** Growing a question set moves every aggregate, and the repo
rule says a shift in `make eval` is a defect to explain, not a tuning opportunity. The explanation
here is legitimate — the denominator changed — so it is made verifiable: **the commit reports the
original 41 questions' scores computed under the new harness, and they must be identical.** A change
in the old subset is a defect in the harness, not a consequence of growth. The previous
`baseline.json` is preserved beside the new one.

**Tests.** Cross-KB expectations resolve; an unresolvable expectation fails loudly; the one-hop
scoring rule is exercised with a question whose evidence is only reachable through a link; per-class
reporting covers the new class.

**Mutation targets.** The old-subset equality assertion; the unresolvable-expectation failure path.

---

### Phase 2 — the authoring and agent surface (G5–G8) · **cut point at G8**

---

### G5 — `pnk link`: forward-only sidecar authoring

**What lands.** `pnk link <src> <dst> --rel <rel>`, writing one entry into **the source document's
sidecar only**. Aliases and `self` resolve to ULIDs **on write** (MANIFEST.md already specifies
this), so what reaches disk survives being shared.

Invariants it must not break: it never modifies a source document under `docs/`; it never
regenerates a ULID; unknown sidecar keys round-trip untouched.

**Tests.** A link round-trips through `pnk sync` into the `links` table; `pnk://self/…` is expanded
on write; an alias is resolved to a ULID on write; a target that does not exist is refused with the
reason; the source document's bytes are unchanged; a sidecar carrying unknown user keys keeps them.

**Mutation targets.** The alias→ULID resolution (a plan that writes an alias to disk is the failure
MANIFEST.md warns about); the source-document immutability assertion.

---

### G6 — `pinakes_links`: the typed, capped agent tool

**What lands.** The §5 contract, exactly:

```text
pinakes_links(kb, doc_id, rel?, direction?, depth?=1, query?)
  → { neighbours: [{doc_id, title, rel, direction, distance, score}],
      frontier:   [{doc_id, rel}],
      unresolved: [{target, reason}],
      confidence, truncated }
```

- **Server-capped `depth` ≤ 3** regardless of what the caller asks. Deliberately one more than the
  automatic channel's 2: an agent spending its own turn on an explicit probe has judged the hop
  worth it.
- **No query-language argument, ever.**
- **With `query`:** fan-out and `score` use similarity to it, and `confidence` carries the same
  calibrated signal class as `pinakes_search`. **Without `query`:** edge weight and link distance
  rank, and `confidence` is `unknown` — the calibrated signal is fitted on query-relevance scores
  and a query-less listing has nothing to be confident about.
- **Tool description carries the loop hints**, labelled by origin: "prefer refining the query over
  raising k" is Graph-R1's learned behaviour; "take one hop and look before asking for depth 3" is
  ours.

**New gate (`check.sh`).** *Traversal caps*: asserts the server cap cannot be raised by an argument.

**Tests.** `depth=99` is served at 3; response caps set `truncated`; `confidence` is `unknown`
without `query` and calibrated with it; `unresolved` survives to the caller.

**Mutation targets.** The server-side depth clamp; the `confidence = unknown` branch.

---

### G7 — `pinakes_search` dual-level keywords

**What lands.** Optional `entities=[]` / `concepts=[]` parameters: entity-ish terms boost the FTS5
side, concept-ish terms the embedding side. The caller's agent does the split in its own reasoning —
LightRAG's one genuinely useful query-side idea, obtained without its LLM call.

Absent both parameters, behaviour is byte-identical to today. That is the test that matters.

**Tests.** Omitting both changes nothing; each parameter moves its own channel's ranking and not the
other's; empty lists are not treated as filters.

**Mutation target.** The no-parameters passthrough (a regression here silently changes every
existing caller's results).

---

### G8 — `pnk doctor` link reporting, the docs sweep, and **the cut point**

**What lands.** `doctor.py:520`'s `"{n} cross-KB (unchecked until the graph release)"` becomes a real
check: cross-KB targets resolve or are reported dangling with a reason. Link coverage (linked docs /
total) is reported as the ceiling on cross-KB answers it is (§6.2), and a zero-link document count is
a nudge — the proven pressure short of a hard gate (§3).

Docs sweep for everything in Phase 2: `docs/CLI.md` (`pnk link`, and `pinakes_links` out of the
Planned table), `docs/MANIFEST.md`, `docs/GUIDE.md` (a cross-KB walkthrough, every command actually
run), `docs/STATUS.md` rows.

**The cut point — criteria, written now.** Ship Phase 2 as a release when all of these hold:

1. G1–G8 are merged to `main`, each green, with CI green on the merge.
2. `make eval` shows the original 41-question subset unmoved (G4's safeguard).
3. No `schema_version` bump has occurred — an existing KB gains the surface by upgrading and
   re-syncing, with no rebuild.
4. `pnk doctor` on both corpora is clean.

The release is a MINOR under the SemVer table. **Check `origin/main` for the number before assigning
it** — another agent may have cut a release since this plan was written. Cutting here is the default,
not the fallback: the project rule is that complete self-contained work never lingers in
`[Unreleased]`, and Phase 2 is complete and self-contained whether or not Phase 3 ever ships.

---

### Phase 3 — structure and the channel (G9–G12)

---

### G9 — The node model and the edge set (`schema_version` 3)

**What lands.** §3's heterogeneous node model and its derived edges, computed at sync, stored in
`.pinakes/index.db`. Inert: nothing reads them until G11.

Nodes: **chunk**, **document**, **tag**, **heading-path** (*scoped per document* — a global
"Introduction" hub would weld every document into one noise clique), **directory**. Entity nodes are
out of scope (decision 6) and the model is shaped so they can be added without reshaping it.

Every shared-value relation goes **through its hub node**, never as materialised pairwise edges —
that is what keeps edge counts linear instead of O(members²) and gives G11's visited-edge dedup a
single node to expand once.

| Edge | Connects | Weight |
|---|---|---|
| membership | chunk ↔ doc | 1.0 (transit plumbing, not signal) |
| `sibling` | chunk ↔ chunk (adjacent ordinal) | 1.0 |
| `parent` / `child` | chunk ↔ chunk (`heading_path` prefix) | 1.0 |
| `in-section` | chunk ↔ heading node (per-doc) | 1/section-size |
| `co-located` | doc ↔ directory node | 1/dir-size |
| `shared-tag` | doc ↔ tag node | 1/tag-degree |
| authored | doc ↔ doc (sidecar `links`) | 2.0 |

**Hub damping is not optional**, and applies to every shared-value hub — tag, directory and
`in-section` alike. `sibling` and `parent`/`child` stay at 1.0 because adjacency and hierarchy are
not shared-value relations. Weights are **starting points to be fitted against the golden set**, not
measured constants, and the code must make that easy to change.

`schema_version` → **3**. Every KB rebuilds; no migration.

**Tests.** Edge counts are linear in members for a shared tag, not quadratic; a per-document heading
hub does not connect two documents; damping divisors are the hub's degree; a `schema_version` 2
index is refused with the rebuild remedy.

**Mutation targets.** The damping divisor (replace with 1.0 — a test must fail); the per-document
scoping of heading nodes; the `schema_version` refusal.

---

### G10 — `requires_pinakes` and rebuild guidance

**What lands.** The minimum of [KB-UPDATES](../docs/KB-UPDATES.md) (decision 4), landing beside the
bump that makes it matter. `[kb]` gains `requires_pinakes`, read in a **pre-pass before strict
manifest validation** — a manifest from a newer pinakes must be able to say so *before* the strict
validator rejects its unknown keys. The `schema_version` 3 refusal tells the user exactly what to
run.

Out of scope, explicitly: `pnk upgrade`, `--apply`, template drift detection, tomlkit.

**Tests.** A manifest requiring a newer pinakes is refused with the version in the message, not with
an unknown-key error; the pre-pass runs before strict validation; an absent `requires_pinakes` is not
an error.

**Mutation target.** The pre-pass ordering (move it after strict validation — the version message
must stop appearing).

---

### G11 — The expansion channel, default off, and the gate

**What lands.** `[retrieval] graph_channel = "off" | "expand"`, default `"off"`. When `"expand"`:
take the fused top-*k* as roots, expand with G3's core to depth ≤ 2, rank, and feed the result into
the existing RRF as a **third** input. An empty edge set means an empty third channel and RRF fuses
two lists exactly as it does today — the degradation path is the current behaviour, tested as such.

Ranking follows the node model's asymmetry: **chunk** neighbours rank by cosine against the query
embedding (in-process, NumPy tier); **non-chunk** nodes carry no content embedding, pass through by
edge weight, and contribute their member chunks — **minus the root's own document**, §3's membership
exclusion, because intra-document structure is already sibling/parent-child/in-section's job and the
channel exists to surface cross-document connections.

Also evaluated in the same matrix, both cheaper than everything else here: **in-degree over the
`links` table as a zero-cost salience prior**, and the **link-distance rerank**.

**The gate (§9), and the pre-commitment.** `expand` defaults on only if multi-hop recall@k rises,
simple-lookup is unchanged, and false-abstain is flat. **A channel that regresses simple-lookup
precision stays `off` by default, whatever it does for multi-hop.** If the gate fails, the increment
still lands — the channel ships, off, with the numbers recorded — and it is not tuned until it
passes. That is the pre-commitment; deleting it is how eval theatre starts.

Commit message carries before/after numbers for every class.

**Tests.** An empty edge set reproduces today's results byte-for-byte; the membership exclusion holds
(a same-document chunk reachable only through membership never appears); depth is capped at 2;
`"off"` is genuinely off — no traversal query is issued.

**Mutation targets.** The membership exclusion; the default value of `graph_channel`; the empty-edge
degradation path.

---

### G12 — Edge-hub reporting, docs sweep, release

**What lands.** `pnk doctor` reports the highest-degree edge hubs, so a user can see when a tag has
become meaningless glue (§3). DESIGN amendments from the table above. `docs/STATUS.md` rows flipped.
CHANGELOG assembled. Release cut, tagged, pushed, GitHub release created from the CHANGELOG section.

**Verify, never assume, that the release happened**: `git tag -l`, `gh release list`, and
`git merge-base --is-ancestor` before writing release notes. `make release-check` **before** pushing
the tag — a tag now publishes to PyPI and a version cannot be re-uploaded.

---

## Verification of the whole

Run after G12, before the release:

1. `./check.sh` green on all three CI legs.
2. **The free path is still free**: `.paid-path-allowlist` is byte-identical to its pre-G1 state, and
   the subprocess gate confirms no paid client reaches `sys.modules` on a full two-KB sync, link,
   search and traverse.
3. **Golden set**: the original 41 questions score identically to the G4 re-baseline; the new classes
   are reported per class; the gate decision for `graph_channel` is recorded with its numbers.
4. **A fresh KB works**: `pnk init`, add a document, `pnk link` to a second KB, sync, search,
   traverse — run, not reasoned about.
5. **An existing KB upgrades**: a `schema_version` 2 KB is refused with a remedy that works.
6. **Every command in `docs/GUIDE.md` is executed** as written, install line included.
7. `pnk doctor` clean on both corpora.

---

## Risks specific to this sequencing

| Risk | Why it is real | Mitigation |
|---|---|---|
| The synthetic link corpus is unrealistically clean | I author both the links and the questions that traverse them; §3 says real link graphs are sparse and weak | The ≤35% density gate (G1); links of the weakest useful kind only; the optional ClaudeKB realism check |
| The re-baseline hides a regression | Growing a question set moves every aggregate, which is exactly what a regression looks like | G4's safeguard: the original 41 must score identically under the new harness |
| The channel fails its gate and the release lands with its centrepiece off | Genuinely possible — one study in the GraphRAG-Bench line measured graphs *costing* ~13% on simple lookup | Decision 2's cut point: Phase 2 ships on its own merit. G11 pre-commits to shipping the numbers rather than tuning to the gate |
| ~25 multi-hop questions is still a small sample | 4 points per question against a 5-point gate is measurable, not robust | Report per-class counts beside per-class scores so nobody reads 0.84 as precise; the gate decision names its own uncertainty |
| A concurrent agent lands conflicting work | One is building I7c right now, in its own worktree | `git fetch` and re-read `origin/main` at the start of every increment; check the release number against `origin/main` before assigning it |
| The baseline moves under the plan | I7c, I8, I9 have not landed; `schema_version` may bump before G9 | G1 begins by re-reading the baseline; the amendments table is corrected before G9, not after |

---

## Iteration log

| When | What |
|---|---|
| 20260729 02:52 | Written. Seven decisions taken with the user; no adversarial pass yet |
