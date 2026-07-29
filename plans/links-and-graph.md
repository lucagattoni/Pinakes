# The links release and the graph release — implementation plan

**Status:** draft — revised after adversarial passes 1 (22 HIGH, 30 MEDIUM, 15 LOW) and 2 (26 HIGH,
30 MEDIUM, 8 LOW, from two independent reviewers). **Not yet implementable.** Pass 2 found that six
of pass 1's own fixes were wrong, two of them self-refuting; assume the same of this revision until
a pass comes back clean.

**Date:** written 20260729 02:52 · rewritten 03:31 (pass 1) · rewritten 04:05 (pass 2)

**Source of truth:** [`docs/DESIGN.md`](../docs/DESIGN.md). Where this plan and DESIGN disagree on
anything *not* in the amendments tables, DESIGN wins and this plan has a bug.

**Section references are qualified.** `DESIGN §5` and `APPROACH §5` are different documents.

**Written against** [`docs/graph/PINAKES_APPROACH.md`](../docs/graph/PINAKES_APPROACH.md) (five
adversarial passes), [`docs/graph/GRAPH_RAG.md`](../docs/graph/GRAPH_RAG.md)'s R1–R7, and
[`docs/RETROSPECTIVES.md`](../docs/RETROSPECTIVES.md) — which is an **input to every increment**, not
only an output (v0.1 rule 10; v0.1 lost this in 5 of 15 increments).

**No version number appears here for unbuilt work** ([CLAUDE.md](../CLAUDE.md)).

## Baseline — `main` at `44606fd`, 20260729 04:05

Re-verify before L1. `main` moved eleven commits under the first draft and two more under the
second, and a second agent is working this repo concurrently.

| Fact | Value |
|---|---|
| `schema_version` | 2 |
| Paid-extraction release | I1–I7c on `main`; **I8, I9 remain** |
| Golden set | 41 questions · recall@5 0.909 · MRR 0.812 · rerank precision 0.758 · false-abstain 0.03 · false-confidence 0.25 |
| Per class | `lexical` 1.00 · `filter` 1.00 · `no-answer` 1.00 · `multi-hop` **1.00 (n=5, at ceiling)** · `paraphrase` 0.75 |
| `links` | Exists. PK is `(src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel)` — **`origin` is not in it** |
| `kb_refs` | Exists, never written. Four columns: `kb_id, alias, path, last_scan` |
| Reverse-scan | Not implemented |
| Authored links in `tests/demo-kb/` | **Zero**, across 30 documents |
| `chunks.id` | `INTEGER PRIMARY KEY` — **the rowid**. `store.py` says outright: *"a chunk has no identity across rebuilds"* |
| `compare()` | Gates six aggregates, per class, and the question count, each at `tolerance=0.02` |

---

## Two releases, not one

| Release | What it is | Rebuild? |
|---|---|---|
| **the links release** | `pnk link`, `pnk links`, `pinakes_links`, reverse-scan, link-coverage reporting | **No** |
| **the graph release** | Structural edges, the expansion channel, `schema_version` 3 | Yes, once |

The no-rebuild property is a cut criterion (L10), not an assertion — and it survived pass 2 only
because decision 11 dropped the one feature that would have broken it.

---

## Goal

A question answered in one KB can reach evidence in another, because a human said the two documents
were related and pinakes remembered — and the structure that makes traversal useful when nobody has
authored anything is derived for free afterwards, if and only if the golden set says it helps.

**Nothing here can spend money.** `.paid-path-allowlist` is unchanged. The free-path gate's
*coverage* is extended per increment, which is required; its *allowlist* is not, which is forbidden.

---

## Decisions taken

Rows 1–7 settled with the user 20260729 02:30–03:10; rows 8–10 after pass 1, 03:20–03:35; rows
11–13 after pass 2, 04:00–04:05. Dated separately because a decision produced by a review is not a
decision the user made earlier, and pass 2 caught the first revision back-dating three of them.

| # | Decision | Consequence |
|---|---|---|
| 1 | A second synthetic KB is committed, deliberately sparse; a hand-adopted ClaudeKB corpus is an optional human-gated realism check | L2, L10 |
| 2 | Two releases, cut after the links surface, names split accordingly | L10 |
| 3 | The golden set grows to ~25 multi-hop questions and gains a `simple-lookup` class; one re-baseline | L9 — **and see decision 12, which reverses its cross-KB majority** |
| 4 | Minimum of [KB-UPDATES](../docs/KB-UPDATES.md): the `requires_pinakes` pre-pass only | G2 |
| 5 | `pnk link` writes forward only, into the source document's sidecar | L7 |
| 6 | PPR and the `[ner]` extra are out | — |
| 7 | Adversarial subagent passes until one comes back clean | Passes 1 and 2 done; **pass 3 required** |
| 8 | `pinakes_search`'s `entities`/`concepts` parameters are cut | RRF here is unweighted by construction, so the feature needs a weighting change touching every query plus its own eval |
| 9 | The eval harness is repaired before it is grown | Landed `b637be4` |
| 10 | Retrieval ordering is made reproducible before any finer gate depends on it | L1 — **reframed by pass 2**: the hazard is cross-build and cross-machine, not run-to-run |
| 11 | **Cross-KB neighbours carry no `title`.** They carry `kb`, `doc_id`, `rel`, `direction`, `distance`, `score`, and a reason | L5, L6. Amends APPROACH §5. A ULID→title map needs either a per-query walk of another KB (a query-time cross-KB read DESIGN §6.2 sanctions only at sync time) or a cache with nowhere to live — `kb_refs` has four columns and no per-document capacity — i.e. the `schema_version` bump the release exists to avoid |
| 12 | **The multi-hop class is majority single-KB**: ~18 single-KB (authored failable) and ~7 cross-KB, the latter its own `kind` | L9. Reverses decision 3's "most cross-KB". The expansion channel's gate can only read single-KB questions (L8), and "most cross-KB" left ≤7 improvable against a 5-question threshold — a gate pre-committed to failing |
| 13 | **G1's edge weights are frozen at APPROACH §3's priors**, committed before L9's questions are authored. If the gate fails, fitting is **exploratory** and cannot flip it without a newly authored question set | G1, G3. `calibrate.py` already records this circularity for the confidence thresholds and calls the result optimistic; a default-on retrieval channel is a much larger commitment than a UX heuristic |

---

## What this plan deliberately does NOT decide

| Question | Default | Revisit when |
|---|---|---|
| Does `pnk link` gain a comment-preserving YAML dependency? | **Ask before L7 starts.** If unavailable: **ship without it**, xfail `test_comments_in_the_sidecar_survive_a_rewrite`, and amend DESIGN §2.2 to record the deferral. L8–L10 do not depend on `pnk link` — L2's links are hand-authored — so a stalled L7 blocks only L10's cut criterion 5 | L7 is scheduled |
| Does the comment-preserving writer become *the* sidecar writer, or only `pnk link`'s? | Only `pnk link`'s, **and DESIGN §2.2 records that a later paid-extraction sync destroys the comments it preserved** (DESIGN §2.2 already says PyYAML drops comments on that write). Two writers with different formatting will churn the file | A user reports the churn, or the deep release's sidecar write-back lands |
| PPR / the `"ppr"` value | Not reserved; the config rejects anything but `"off"`/`"expand"` | APPROACH §9's `ppr` gate becomes measurable |
| The `[ner]` extra | Out. G1's node model can accept entity nodes, but adding them **is a reshape** — APPROACH §3 gives hub and entity nodes label embeddings and G1 stores none | The §9 gate fires |
| `pnk unlink` / `pnk link --list` | Out. A mistyped link is fixed by editing the sidecar | A user hits it |
| `pnk adopt`, `--deep`, federated query, a graph query language, migrations | Out | — |
| Held-out eval splits | Out at this corpus size — ~18 single-KB questions cannot be split into a trainable half and a half that can gate anything | The golden set is large enough that a split leaves a gating-capable holdout |

---

## Ground rules

- **The gate is an artifact.** `./check.sh` before every commit — **and every new gate also gets its
  own CI job**, because `ci.yml` never invokes `check.sh`; it re-implements the steps. New gates and
  owners: link-density (L2), traversal-caps (L4), two-KB eval (L8). Each is named in its increment's
  body, not only here.
- **A gate that cannot run says so and is still a gate**, with a test asserting the printed reason
  (`tests/test_check_script.py`, as `pdf-eval` has).
- **Worktree + branch per increment**, `YYYYMMDD_HHMM-<id>-<slug>`, timestamp read from `date`.
  `git fetch` and re-read `origin/main` at the start of every increment.
- **Pure and I/O are separate increments** (v0.1 rule 11): L4 core, L5 provider.
- **The fixture is not the algorithm** (v0.1 rule 5).
- **No inline type suppressions** (v0.1 rule 7). The heterogeneous node model (G1) is a discriminated
  union under `pyright` strict and is where the temptation will be.
- **Retrospectives are an input** (v0.1 rule 10): re-read them at the start of each increment; land
  findings and fixes as their own commit.
- **Durability** (v0.1 rule 12): every sidecar write is **rename-atomic**. L7 introduces a new
  sidecar writer, and the ULID a sidecar carries is the one thing no later command can recompute.
- **Break the code on purpose before review.** A target that cannot be mutated is not a target.
- **Docs land in the same commit as the behaviour.** Every increment below names its doc homes
  explicitly — `docs/README.md`'s landing checklist is the list, and pass 2 caught the previous
  revision banning sweep increments and then naming no owner at all.
- **Every retrieval change reports before/after per-class golden-set numbers.** Those increments are
  **L1, G1 and G3** — G1 included, because the moment `edges` carries structural rows the L5/L6
  provider would serve them (see G1's scope note).

---

## DESIGN.md amendments

| § | Amendment | Lands in |
|---|---|---|
| §2.1 | `[retrieval] adjacent_k` | L4 |
| §2.1 | `[retrieval] graph_channel` | G3 |
| §2.1 | `[kb] requires_pinakes` | G2 |
| §2.2 | The comment-preserving writer is delivered, or its deferral re-recorded; `links[]` entries round-trip unknown per-link keys | L7 |
| §3 | The node model, `nodes`/`edges`; `schema_version` 3 | G1 |
| §4.1, new §4.8 | The graph channel | G3 |
| §4.7 | Publishing a KB also publishes the ULIDs and relations of every KB it links to | L2 |
| §6.2 | Reverse-scan built; failure taxonomy; stale reverse edges removed on re-scan | L3 |
| §6.3 | `pnk sync --scan-links` | L3 |
| §7 | The `simple-lookup` and `cross-kb` classes | L9 |
| §8 | Command list gains `link` and `links` | L5, L7 |
| §8 | The links-release row moves to shipped | L10 |
| §8 | **Both** graph-release rows — "structural edges and the expansion channel" and "(staged) — graph channels" — are reconciled | G4 |

## APPROACH amendments

`docs/graph/PINAKES_APPROACH.md` is dated research and keeps its text; these are recorded in the
increment that departs from it, and in its header note.

| § | Departure | Lands in |
|---|---|---|
| §5 | The neighbour shape gains `kb` and loses `title` for cross-KB neighbours (decision 11) | L5 |
| §3 | Weights are frozen, not fitted (decision 13) | G1 |

## CLAUDE.md amendments

| Rule | Amendment | Lands in |
|---|---|---|
| *"`docs/` belongs to the user … never any other key"* | `pnk link` additively writes `links[]` to the source document's own sidecar, on explicit user command — a second, narrower exception: **a user-invoked authoring command**, distinct from anything `sync` does unasked | L7 |
| Naming table | The graph-release row splits; both rows gain `pnk links` | this change |

---

## Increments — the links release

### L1 — Reproducible retrieval ordering across builds and machines

**The framing pass 2 corrected.** The first revision called these "run-to-run variance". They are
not: for a fixed index and a fixed query all three sites are deterministic, which is why `make eval`
already gives byte-identical output three times running. The hazard is **cross-build** — an
incremental sync or a rebuild reassigns `chunks.id`, and G1's `schema_version` bump forces exactly
that immediately before G3's before/after measurement — and **cross-machine**.

**The key pass 2 corrected.** The first revision chose `chunk_id` "not rowid order". `chunks.id` **is**
the rowid, and `store.py` says so two lines above the table: *"a chunk has no identity across
rebuilds"*. The stable key is **`(doc_id, ordinal)`** — `doc_id` is the permanent ULID and
`UNIQUE (doc_id, ordinal)` already exists.

**Four sites, not three.** The fourth is `_hydrate`, which runs `WHERE c.id IN (…)` with **no
`ORDER BY`**; and the two later sorts' `p.path` tiebreak does *not* totalise, because two chunks of
the same document share a path — and equal fused scores between same-document chunks are ordinary,
since a chunk at lexical rank *r* and another at vector rank *r* both score exactly `1/(60+r+1)`.

**What lands.** `(doc_id, ordinal)` as the final tiebreak at all four sites.

**Out of scope, stated:** BLAS reduction order can move cosine similarities in their last bits
between machines, which shifts *near*-ties that no exact-equality tiebreak can catch. Naming it
because it is the residual reason CI and a laptop can still disagree.

**Tests.** `tests/test_search.py::test_ordering_is_unchanged_by_an_incremental_sync_then_rebuild`
(sync, capture, edit one document, sync, `--rebuild`, compare — the sequence that actually
renumbers ids; a bare rebuild of an unchanged corpus reproduces them and proves nothing);
`::test_two_same_document_chunks_at_equal_fused_score_order_by_ordinal`;
`::test_hydrate_does_not_determine_final_order`.

**Exit criteria.** The three tests green; `make eval` unchanged per class (this increment should
move nothing, and anything it moves is a finding to explain). **Docs:** none — no user-facing
surface changes.

**Mutation targets.** The tiebreak at each of the four sites, removed independently; each must fail
a named test. (The first revision claimed three tests would fail, one per site, when only one could.)

**Stands alone**, releasable independently.

---

### L2 — The partner KB, its golden set, sparse links, the density gate

**What lands.** `tests/partner-kb/` — a partner museum that transacts with the archive in
`tests/demo-kb/`: outward and inward loans, courier and condition reporting, a shared emergency
plan, a joint digitisation programme. ~18–22 documents, own `pinakes.toml` and KB ULID, own
sidecars.

**Its own golden set, with `no-answer` questions** — because `[retrieval.confidence]` is fitted by
`calibrate.py` against the scores of the *unanswerable* questions, and `eval.run` reads
`<kb_root>/eval/questions.yaml`. Without it there is nothing to fit, and without a fitted block
`search.py` returns `confidence: unknown` for every query against the partner KB, which would make
L6's calibrated-confidence claim vacuous on exactly the KB the cross-KB tests use. Pass 2 caught the
previous revision requiring the fitted block and creating none of the data it needs.

**Both corpora gain authored links, and stay sparse.** ≤ 35% of documents in each KB, weakest useful
relations (`cites`, `related`, `supersedes`), forward-only from each side.

**The density gate.** Counts **sidecar-authored (forward) links only**, and prints that it does —
after L3 the same `links` table carries `origin='reverse-scan'` rows, and a gate that forgets the
filter silently doubles apparent density. Caps **degree as well as count**: no document carries more
than 4 authored links. Reports the cross-KB/intra-KB split and the relation histogram.

**`[[links.kb]] path` resolution:** relative to the KB root, `~` expanded, absolute permitted but
**warned about by `pnk doctor`** — this repo is public by rule, and an absolute path in a committed
manifest publishes a filesystem layout. Non-existence is not an error; DESIGN §6.2 makes resolution
machine-local.

**Tests.** `tests/test_partner_kb.py::test_both_corpora_load_and_validate`;
`::test_every_sidecar_ulid_is_wellformed_and_unique_across_both_kbs`;
`::test_a_corpus_over_the_density_cap_fails_the_gate`;
`::test_a_corpus_with_a_hub_document_fails_the_gate`;
`::test_the_gate_ignores_reverse_scan_rows`;
`::test_a_search_against_the_partner_kb_reports_a_calibrated_confidence`.

**Exit criteria.** `pnk sync` and `pnk doctor` clean on both; the gate in `check.sh` **and** its own
CI job; `calibrate.py` fits the partner KB and the block is committed. **Review step** (not a test):
the corpus carries no PII, credentials or non-synthetic content.
**Docs:** `docs/MANIFEST.md` (`[[links.kb]] path` resolution + the absolute-path warning),
`docs/DESIGN.md` §4.7, CHANGELOG.

**Mutation targets.** The density comparison at its boundary; the degree cap; the `origin='sidecar'`
filter (delete it — `test_the_gate_ignores_reverse_scan_rows` must fail).

---

### L3 — Reverse-scan, `kb_refs`, and stale-edge removal

**What lands.** `pnk sync` scans each linked KB's **committed sidecars** — never its index — and
writes inbound rows with `origin = 'reverse-scan'`, recording the scan time in `kb_refs`. No schema
change.

**A reverse row must never overwrite an authored one.** The `links` PK is
`(src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel)` — **`origin` is not part of it**. So a plain
`INSERT OR REPLACE` can silently downgrade a weight-2.0 authored edge to a reverse-scanned one
whenever both exist for the same tuple: a `[[links.kb]]` entry pointing at the KB itself, two
aliases resolving to one KB, or two KBs that both author the same relation. Reverse-scan therefore
inserts with `ON CONFLICT DO NOTHING`, never `OR REPLACE`. Pass 2 found this; the previous revision
asserted "no schema change" without noticing the PK admits the collision.

**Stale reverse edges are deleted on re-scan**, scoped **per scanned `src_kb_id`** —
`_replace_links()` hardcodes `origin='sidecar'` and is scoped per *local* document, so nothing local
removes a row whose source lives elsewhere.

**Cost, because this runs on a hook.** `pnk install-hooks` puts `pnk sync` on three git hooks.
Reverse-scan is bounded by `kb_refs.last_scan` with a TTL, skipped while fresh, forced by
`--scan-links`. **Which sync modes scan:** reverse rows are index rows, so `--sidecars-only` (the
pre-commit hook) does **not** scan; `--index-only` and a full sync do.

**Concurrency.** Never take the other KB's lock. A file that vanishes or fails to parse mid-scan is
a recorded reason, retried next scan, never a deletion.

**The failure taxonomy** — unresolvable KB id, unreachable path, target document absent, sidecar
unparseable — is defined here as typed errors in `errors.py`, each with a remedy, and consumed
unchanged by L5, L6 and L10.

**Tests.** `tests/test_sync_links.py::test_inbound_rows_carry_the_other_kbs_id_as_source`;
`::test_a_reverse_row_never_overwrites_an_authored_row`;
`::test_a_linked_kb_whose_path_is_absent_is_recorded_not_raised`;
`::test_a_target_document_absent_is_recorded_with_its_reason`;
`::test_an_unparseable_sidecar_is_recorded_not_treated_as_a_deletion`;
`::test_a_removed_link_removes_its_reverse_row`;
`::test_the_delete_is_scoped_to_the_scanned_kb`;
`::test_a_fresh_kb_refs_entry_skips_the_walk`;
`::test_an_expired_ttl_forces_a_rescan`; `::test_scan_links_forces_a_rescan`;
`::test_sidecars_only_does_not_scan`;
`::test_rebuild_reconstructs_reverse_rows_from_sidecars_alone`.

**Exit criteria.** All of the above green. **Docs:** `docs/CLI.md` (`--scan-links`),
`docs/DESIGN.md` §6.2 and §6.3, `docs/STATUS.md`, CHANGELOG.

**Mutation targets.** The `src_kb_id` assignment; `ON CONFLICT DO NOTHING` → `OR REPLACE`; the
stale-row delete's scoping; the TTL check; the "sidecars, not index" selection — **whose fixture
must hold an index that contradicts the sidecars**, since a rebuild has no index to read and cannot
detect an implementation that reads it on the normal path.

---

### L4 — The traversal core, pure

**What lands.** `graph/traverse.py` over an edge-provider protocol, no SQLite. Enforces: **depth in
logical hops** (membership and hub pass-throughs depth-free); **fan-out capped at `adjacent_k`,
ranked before truncation**; **visited-edge dedup**; **responses double-capped on row count *and*
token budget**, `truncated` set when either bites; **`unresolved` returned, never dropped**.

**`adjacent_k` is a `[retrieval]` key with a code default of 8, and is NOT stamped into the `notes`
template.** `_toml.py` hard-errors on unknown keys, so a template that stamps it would make every
newly created KB unreadable to any earlier pinakes — a forward-compatibility break shipped a whole
release before `requires_pinakes` (G2) arrives to explain it. The key is settable, documented, and
absent from generated manifests until G2 lands. Pass 2 caught the previous revision naming the
hazard and stamping the key anyway.

**Tests.** `tests/test_traverse.py::test_depth_counts_logical_hops_not_physical_edges`;
`::test_fanout_keeps_the_highest_ranked_neighbours_not_the_first_k`;
`::test_a_hub_is_expanded_once_globally`; `::test_a_cycle_terminates`;
`::test_unresolved_targets_survive_to_the_caller`;
`::test_the_token_budget_sets_truncated_independently_of_the_row_cap`.

**Exit criteria.** The traversal-cap gate in `check.sh` **and** its own CI job, asserting the server
cap cannot be raised by an argument. **Docs:** `docs/MANIFEST.md` (`adjacent_k`), `docs/DESIGN.md`
§2.1, CHANGELOG.

**Mutation targets.** Rank-then-truncate ordering; the visited-edge set insertion; the `unresolved`
accumulation; the depth comparison; the token-budget check.

---

### L5 — The SQLite provider and `pnk links`

**What lands.** The provider behind L4's protocol — **a per-depth Python loop, one query per hop,
never a recursive CTE** (APPROACH §4A: ranking needs the vector array and global dedup needs shared
state, and pruning after an unbounded CTE lets the hub explosion happen first) — and a CLI surface,
because DESIGN §8 already settled that a slice queryable only over MCP does not reach end to end.

```text
pnk links <doc> [--rel R] [--direction in|out|both] [--depth N] [--query Q] [--json]
```

**The neighbour shape (decision 11), amending APPROACH §5:**

```text
{kb, doc_id, rel, direction, distance, score}     # title only for same-KB neighbours
```

A cross-KB neighbour carries **`kb` and no `title`**, with a reason. `kb` is what the previous
revision missed entirely: a neighbour arrives as a bare ULID, `as_payload` puts `kb` on the
*envelope* only, and `Passage` has no KB field — so the release's headline feature would have
returned document IDs an agent could neither fetch nor name the KB of.

**Tests.** `tests/test_cli_links.py::test_a_cross_kb_neighbour_carries_its_kb_and_no_title`;
`::test_a_same_kb_neighbour_carries_its_title`; `::test_depth_beyond_the_cap_is_served_at_the_cap`;
`::test_json_output_is_stable`;
`tests/test_traverse_provider.py::test_one_query_per_hop_not_a_recursive_cte`.

**Also lands.** `tests/free_path_run.py` gains `pnk links`; `tests/test_paid_path.py`'s surface list
gains the **new modules** (`pinakes.graph.traverse` and the provider) — it enumerates modules, not
commands, so a new subcommand alone adds nothing to it.

**Exit criteria.** `tests/test_cli.py`'s `DESIGN_COMMANDS` **and** `IMPLEMENTED` gain `links`, and
DESIGN §8's command list with them. **Docs:** `docs/CLI.md` (move `pinakes_links`/`pnk links` out of
the Planned table, document every flag and exit code), `docs/GUIDE.md` (a cross-KB walkthrough with
every command actually run), `docs/STATUS.md`, CHANGELOG.

**Mutation targets.** The cross-KB `kb` field (drop it — a test must fail); the depth clamp; the
per-hop loop replaced by a single unbounded query.

---

### L6 — `pinakes_links`

**What lands.** The same core on the MCP surface. `depth` server-capped at 3 — one more than the
automatic channel's 2, because an agent spending its own turn on an explicit probe has judged the
hop worth it. No query-language argument, ever.

**One boundary rule, not two.** A neighbour is *reachable* iff its KB is one the **server was
pointed at** (`serve.py`'s `roots`) — a server-invocation property, not a manifest property. The
previous revision used the manifest criterion in L5 and the server criterion in L6 and claimed they
were the same; they differ whenever a served KB lists a `[[links.kb]]` the server was not given.
Unreachable neighbours still return `kb` + `doc_id` + `rel` and a reason, so the agent knows what it
cannot see. DESIGN §4.7 stands unamended: nothing reads outside the served set.

**Confidence.** With `query`, the same calibrated class as `pinakes_search`; without it, `unknown`.

**Tests.** `tests/test_serve.py::test_the_tool_set_has_four_tools` (**new** — the existing
`test_the_tools_are_namespaced` keeps its name and its `kb_` invariant, which the previous revision
would have buried by renaming it);
`::test_pinakes_links_reports_unknown_confidence_without_a_query`;
`::test_pinakes_links_returns_score_and_frontier_on_every_return`;
`::test_a_neighbour_outside_the_served_kbs_returns_its_kb_and_a_reason`;
`::test_depth_is_capped_server_side`;
`::test_pinakes_search_and_get_payloads_are_unchanged`.

**Exit criteria.** `free_path_run.py`'s MCP handshake **invokes** `pinakes_links`, not only
`list_tools()` — today it asserts `if not tools` and never calls one, so a cut criterion about
covering the tool would otherwise be satisfiable while proving nothing about its body.
**Docs:** `docs/CLI.md` (MCP tool table), `docs/GUIDE.md`, `docs/STATUS.md`, CHANGELOG.

**Mutation targets.** The `confidence = unknown` branch; the served-KB boundary check; the depth
clamp.

---

### L7 — `pnk link`

**Blocked on a decision** with a stated default (see *does NOT decide*). L8–L10 do not depend on it.

**What lands.** `pnk link <src> <dst> --rel <rel>`, writing one entry into the **source document's
sidecar only**, rename-atomically.

**The `<dst>` grammar, which the previous revision left undefined** for the release whose whole
point is cross-KB authoring: a path relative to the local KB root; `pnk://<kb-ulid>/<doc-ulid>`; or
`<alias>:<path>` where the alias is a `[[links.kb]]` name. Aliases and `self` resolve to ULIDs **on
write**. A `<dst>` that resolves to nothing is refused with its reason.

**Per-link unknown keys round-trip.** `Link` is a two-field frozen dataclass and the writer emits
`{"to":…, "rel":…}` only; top-level unknown keys survive via `extra`, per-link keys do not.

**Tests.** `tests/test_cli_link.py::test_an_alias_is_resolved_to_a_ulid_on_write`;
`::test_self_is_expanded_on_write`; `::test_each_dst_grammar_resolves`;
`::test_an_unresolvable_dst_is_refused_with_its_reason`;
`::test_a_link_round_trips_through_sync_into_the_links_table`;
`::test_unknown_keys_inside_a_link_entry_survive_a_rewrite`;
`::test_the_write_is_atomic_under_an_interrupted_rename`;
`::test_the_source_document_is_byte_identical_afterwards`;
`::test_comments_in_the_sidecar_survive_a_rewrite` (xfail if the dependency is declined).

**Exit criteria.** `DESIGN_COMMANDS`, `IMPLEMENTED`, DESIGN §8's command list, and CLAUDE.md's
`docs/`-ownership amendment all land here. **Docs:** `docs/CLI.md`, `docs/GUIDE.md`,
`docs/MANIFEST.md` (`links[].to` written by `pnk link`), `docs/DESIGN.md` §2.2, `docs/STATUS.md`,
CHANGELOG.

**Mutation targets.** The alias→ULID resolution; the per-link `extra` merge; the atomic rename.
*Not* the source-document immutability assertion — there is no code to mutate.

---

### L8 — The two-KB eval harness

**What lands.** The harness learns a second KB.

- `expect` accepts `pnk://` or `<kb-alias>:<path>`; an entry resolving to nothing **fails loudly**.
- A new `kind`, `cross-kb`, so `compare()` gates cross-KB questions **separately** from single-KB
  multi-hop. Without it the gate G3 needs would have to be counted by hand out of a mixed class —
  while the same gate advertised itself as "enforced by `compare()`, not by reading".
- `eval.py` **validates `kind`** against the known set instead of `str(item.get("kind","lexical"))`;
  a typo currently creates a silent new class that `compare()` then gates.
- `Makefile` defines `DEMO_KB` and uses it in four places; `.github/workflows/ci.yml` **does not use
  the variable at all** and hardcodes `tests/demo-kb` in five places, including the `eval` job. Nine
  sites, not the four the previous revision budgeted.

**Scoring, simplified.** The previous revision invented an "all of `expect`" rule for hopped and
cross-KB questions. It was both redundant and self-contradicting: `eval.py` has required
`hops_followed == len(question.hops)` since `b637be4`, and all five committed multi-hop questions
*are* hopped — so the rule would have rescored the very 41 the increment promises to leave
untouched. **Dropped. A cross-KB question is simply a hopped question whose later hop lands in the
other KB**, and the existing per-hop semantics carry it unchanged. What L8 adds is only the ability
for a hop's `expect` to name a document in another KB, resolved through L4's core.

**Tests.** `tests/test_eval_cross_kb.py::test_a_pnk_uri_expectation_resolves`;
`::test_an_unresolvable_expectation_fails_loudly`;
`::test_a_cross_kb_question_misses_when_the_link_is_removed`;
`::test_an_unknown_kind_is_refused`;
`tests/test_eval.py::test_the_committed_41_score_exactly_the_baseline` (**a test**, over the
committed baseline file — the previous revision proposed a number pasted into a commit message by
the person who wrote the code, which is unfalsifiable).

**Exit criteria.** The two-KB eval gate in `check.sh` **and** its own CI job, skipping with a printed
reason when a corpus is absent, with a test asserting that reason. **Docs:** `docs/DESIGN.md` §7,
CHANGELOG.

**Mutation targets.** The cross-KB expectation resolver; the unresolvable-expectation failure path;
the `kind` validator.

---

### L9 — The golden set grows, one re-baseline, and the measurability precondition

**What lands.** ~18 **single-KB** multi-hop questions (13 new), ~7 `cross-kb` questions, and ~20
`simple-lookup` — the mix decision 12 flipped.

**Why the mix flipped.** The expansion channel's gate can only read single-KB questions: the harness
resolves a cross-KB hop through L4's core directly, and G3's channel lives inside `search()`, which
cannot return another KB's chunks in any case. With "most cross-KB" the gate had ≤7 improvable
questions against a 5-question threshold — a 71% flip rate, i.e. a gate pre-committed to failing.

**The new single-KB questions must be failable.** `multi-hop` is at 1.00 on the five committed
questions, and a class at ceiling can only show damage. They are authored from **corpus structure** —
evidence genuinely split across two documents with no shared vocabulary — not by probing what today's
pipeline gets wrong, which would encode current failures as the specification.

**Exit criteria, and the precondition for starting G1.** The observed per-question pass/fail of the
new single-KB subset is **committed as data** at authoring time, and:

> **At least 8 of the ~18 single-KB multi-hop questions must currently fail.**

Five improvements with zero regressions is the smallest result the G3 gate can license (see G3), so
fewer than 8 failing means the gate cannot be reached and the corpus cannot decide the channel. If
that holds after authoring, **G1 does not start**: bumping `schema_version` and forcing every KB in
existence to rebuild for an edge table whose channel can never be licensed is the wrong order. The
previous revision reported this at G3 — after the bump.

**The re-baseline.** Once, here, per-class before/after in the commit message, previous
`baseline.json` preserved beside the new one.

**Also lands.** `src/pinakes/templates/notes/eval/questions.yaml` — today `questions: []`, which
`eval.run` rejects outright, so a freshly `pnk init`ed KB fails `make eval` by construction. DESIGN
§7 says the golden set lives with the demo KB *and with each template*.

**Tests.** `tests/test_eval.py::test_the_committed_golden_set_is_well_formed` and
`::test_evaluating_the_demo_kb_produces_every_metric` both carry exact five-kind sets and gain the
two new kinds; `::test_the_single_kb_multi_hop_subset_has_headroom` asserts the precondition against
the committed authoring-time data. **Not** written: a test asserting particular questions fail — that
would freeze today's defects as a requirement.

**Docs:** `docs/DESIGN.md` §7, `docs/STATUS.md` (measured numbers, re-dated), CHANGELOG.

---

### L10 — `pnk doctor`, verification of the whole, and the links release cut

**What lands.** `doctor.py`'s `"cross-KB (unchecked until the links release)"` becomes a real check.
Link coverage is reported as the ceiling on cross-KB answers it is, **counting authored links only**,
the same population as L2's gate — the two numbers a user sees must not silently differ. Zero-link
documents are a nudge. Highest-degree *authored* link targets are reported.

**Severity:** absent linked-KB path → **WARN** (resolution is machine-local); a `pnk://` target
absent from a KB that did resolve → **WARN** with the count; a malformed `pnk://` in a committed
sidecar → **FAIL**; an absolute `[[links.kb]] path` → **WARN** (public-repo hazard).

**Tests.** `tests/test_doctor.py::test_link_coverage_counts_authored_links_only`;
`::test_a_dangling_cross_kb_target_warns_with_a_reason`;
`::test_a_malformed_pnk_uri_fails`; `::test_an_absolute_linked_kb_path_warns`.

**Verification of the whole** — run before the cut, not reasoned about:

1. `./check.sh` green on all three CI legs; CI green on the merge.
2. **A fresh KB works**: `pnk init`, add a document, `pnk link` to a second KB, `pnk sync`,
   `pnk search`, `pnk links` — executed.
3. **Every command in `docs/GUIDE.md` runs as written**, install line included.
4. `.paid-path-allowlist` byte-identical to its pre-L1 state; the free-path subprocess gate covers
   `pnk link`, `pnk links`, and an MCP handshake that **invokes** `pinakes_links`.
5. The committed 41 score exactly the baseline (by test).
6. **`store.SCHEMA_VERSION` is still 2.**
7. `pnk doctor` clean on both corpora.
8. The ClaudeKB realism check is **run or explicitly declined, in writing** — decision 1 makes it the
   mitigation for this plan's highest-consequence risk, and a mitigation with no owner is a wish.

**The cut.** Bump `__version__`, move `[Unreleased]` into a dated section, commit, **merge from the
primary checkout**, push, `make release-check`, tag, push the tag, create the GitHub release. Then
`git tag -l`, `gh release list` and `git merge-base --is-ancestor` to verify it happened.
**Check `origin/main` for the number before assigning it.**

---

## Increments — the graph release

### G1 — The node model and the edge set (`schema_version` 3)

**Precondition:** L9's headroom check passed. Otherwise this increment does not start.

**What lands.** APPROACH §3's heterogeneous node model and derived edges. Nodes: **chunk**,
**document**, **tag**, **heading-path** (scoped per document), **directory**. Every shared-value
relation goes through its hub node.

**Scope note — "inert" is not free.** L5's provider and L6's tool read through the same core, so the
moment `edges` carries structural rows, `pnk links` would start returning tag and directory
neighbours in a *released* surface. The provider therefore **filters to authored edges** by default,
and G3 is what widens it. This is why G1 counts as a retrieval change and reports golden-set numbers.

**Weights are frozen (decision 13)**, committed before L9's questions were authored, and applied at
read: the `edges` table stores structure only, and the damping divisor is
`SELECT count(*) FROM edges WHERE hub = ?` on an indexed column — **not** a stored `degree`, which is
derived state inside derived state and goes stale on the paths G1 would otherwise have to remember
(a soft-deleted document, a dropped tag, a changed heading path).

| Edge | Connects | Weight at read |
|---|---|---|
| membership | chunk ↔ doc | 1.0 — transit plumbing, not signal |
| `sibling` | chunk ↔ chunk (adjacent ordinal) | 1.0 |
| `parent` / `child` | chunk ↔ chunk (`heading_path` prefix) | 1.0 |
| `in-section` | chunk ↔ heading node (per-doc) | 1/section-size |
| `co-located` | doc ↔ directory node | 1/dir-size |
| `shared-tag` | doc ↔ tag node | 1/tag-degree |
| authored | doc ↔ doc | 2.0 |

Composition across a hub is the **product of both spokes**.

**Edge removal.** `documents.state = 'deleted'` is a soft delete. A soft-deleted document's edges
are removed, its nodes reaped when they reach degree zero, and a stale edge must never let G3's
channel surface deleted content.

`schema_version` → **3**. Every KB rebuilds; no migration.

**Tests.** `tests/test_edges.py::test_a_shared_tag_produces_linear_not_quadratic_edges`;
`::test_a_heading_hub_never_connects_two_documents`;
`::test_sibling_edges_join_adjacent_ordinals`;
`::test_parent_and_child_follow_heading_path_prefixes`;
`::test_weight_across_a_hub_is_the_product_of_both_spokes`;
`::test_a_soft_deleted_document_leaves_no_edges`;
`::test_a_dropped_tag_lowers_the_hub_divisor`;
`::test_the_provider_serves_only_authored_edges_until_the_channel_is_on`;
`::test_a_schema_version_2_index_is_refused_with_its_remedy`.

**Exit criteria.** Per-class golden-set numbers reported and unchanged (the provider filter is what
should keep them so — a change here means the filter leaks). Sync wall-clock on both corpora reported
before and after. **Docs:** `docs/DESIGN.md` §3, `docs/STATUS.md`, CHANGELOG.

**Mutation targets.** The degree divisor replaced by 1.0; the per-document scoping of heading nodes;
the authored-only provider filter; the soft-delete edge removal; the `schema_version` refusal.

---

### G2 — `requires_pinakes` and the version floor

**What lands.** `[kb] requires_pinakes`, read in a **pre-pass before strict manifest validation** —
a manifest from a newer pinakes must be able to say so before the strict validator rejects its
unknown keys. `adjacent_k` and `graph_channel` may be stamped into the `notes` template **from this
increment onward**, and not before.

The floor is read from `pinakes.__version__`; G4 verifies the shipped message names the released
number. Out of scope: `pnk upgrade`, `--apply`, template drift, tomlkit. Rebuild *guidance* is
already shipped — `IndexSchemaError` prints the remedy.

**Tests.** `tests/test_manifest_compat.py::test_a_manifest_requiring_a_newer_pinakes_names_the_version`;
`::test_the_pre_pass_runs_before_strict_validation`;
`::test_an_absent_requires_pinakes_is_not_an_error`;
`::test_the_template_stamps_the_new_keys`.

**Docs:** `docs/MANIFEST.md`, `docs/DESIGN.md` §2.1, `docs/KB-UPDATES.md` (mark axis 4 shipped),
CHANGELOG.

**Mutation target.** The pre-pass ordering.

---

### G3 — The expansion channel, default off, and its gate

**What lands.** `[retrieval] graph_channel = "off" | "expand"`, default `"off"`, with its home in
`manifest.py`, `docs/MANIFEST.md` and the template. When `"expand"`: the fused top-*k* as roots,
expanded to depth ≤ 2, ranked, fed into RRF as a third input; an empty edge set degrades to today's
two-list fusion exactly.

Chunk neighbours rank by cosine; non-chunk nodes pass through by edge weight and contribute their
member chunks, **excluding same-document chunks reachable *only* through their own document's
membership edges** — excluded from the output **and from the fan-out budget**. (A same-document
chunk also reachable by `sibling` or `in-section` is *not* excluded; the previous revision's prose
said "minus the root's own document", which is broader than APPROACH §3.)

**One configuration is gated; the rest are reported.** In-degree salience and the link-distance
rerank are measured in the same matrix but **not** part of the gate — three variables against one
threshold with no correction is not a decision procedure. The gate is evaluated for expansion alone,
at frozen weights.

**The gate.** On the **single-KB multi-hop** class (now its own `kind`, so `compare()` sees it), with
frozen weights, `expand` defaults **on** only if all three hold:

1. The **exact one-sided sign test on discordant questions** gives p < 0.05. Concretely:

   | questions that regressed | improvements needed | net |
   |---|---|---|
   | 0 | 5 | 5 |
   | 1 | 7 | 6 |
   | 2 | 9 | 7 |
   | 3 | 10 | 7 |

2. No class regresses beyond `compare()`'s tolerance — which is 0.02, not zero. At L9's class sizes
   one question always exceeds it, so in practice this is "no class loses a question"; the previous
   revision said "at all … enforced by `compare()`", which is literally false.
3. `false_abstain` does not rise **among questions that were already hits**. Its numerator requires a
   hit, so converting five misses into low-confidence hits *raises* it — the previous revision's
   clause 3 would have vetoed exactly the win clause 1 demands.

**Why the sign test, and why not "net".** Paired binary before/after on the same questions is
McNemar, whose exact form is the sign test on discordant pairs. The previous revision said "≥ 5
questions **net**" and justified it with 0.5⁵ = 0.031 — but *net* is not the sign test's statistic.
8 improved / 3 regressed is also net +5 and gives p = 0.113; 20/15 is net +5 and gives p ≈ 0.25. The
gate as written admitted results four to eight times the claimed p, while rejecting 4/0 at p = 0.063.

**The pre-commitment.** A result short of the table ships the channel **`off`**, with the counts and
the p-value recorded, and it is not tuned. Fitting the weights afterwards is exploratory and cannot
flip the gate without a newly authored question set (decision 13). And **a test asserts the channel
does something**: with `"expand"` and a non-empty edge set it must surface a document two-list fusion
does not return — otherwise a channel broken into returning nothing produces the same blessed outcome
as one that honestly did not help.

**Tests.** `tests/test_graph_channel.py::test_expand_surfaces_a_document_fusion_alone_does_not`;
`::test_an_empty_edge_set_reproduces_two_list_fusion_exactly`;
`::test_off_issues_no_traversal_query`;
`::test_a_chunk_reachable_only_by_membership_never_appears`;
`::test_a_same_document_chunk_reachable_by_sibling_is_not_excluded`;
`::test_membership_neighbours_do_not_consume_the_fanout_budget`.

**Docs:** `docs/DESIGN.md` §4.1 and new §4.8, `docs/MANIFEST.md`, `docs/STATUS.md`, CHANGELOG.

**Mutation targets.** The membership exclusion at both points; `graph_channel`'s default; the
empty-edge degradation path; the third-channel RRF contribution.

---

### G4 — Edge-hub reporting, verification of the whole, and the graph release cut

**What lands.** `pnk doctor` reports the highest-degree **structural** edge hubs, so a user can see
when a tag has become meaningless glue.

**Tests.** `tests/test_doctor.py::test_edge_hubs_are_reported_highest_degree_first`;
`::test_a_kb_with_no_edges_reports_none`.

**Verification of the whole**, before the cut:

1. `./check.sh` green on all three legs; CI green on the merge.
2. A fresh KB works end to end, including `pnk links` with the channel on and off.
3. **An existing `schema_version` 2 KB is refused with a remedy that works** — run it.
4. Every command in `docs/GUIDE.md` runs as written.
5. `.paid-path-allowlist` byte-identical; the free-path gate green on the full two-KB surface.
6. The gate's decision, counts and p-value are recorded in `docs/STATUS.md` whichever way it went.
7. Sync wall-clock and edge counts reported for both corpora.
8. `pnk doctor` clean on both.

**The cut.** As L10, and `make release-check` **before** pushing the tag: a tag publishes to PyPI and
a version cannot be re-uploaded.

**Docs:** `docs/DESIGN.md` §8 (**both** graph-release rows reconciled), `docs/STATUS.md`, CHANGELOG.

---

## Verification — every promise has an owner

v0.1 rule 8: *a promise in a section with no owner is a wish.*

| Promise | Source | Owner | Checked by |
|---|---|---|---|
| Reverse links computed by scanning committed sidecars | DESIGN §6.2 | L3 | `test_rebuild_reconstructs_reverse_rows_from_sidecars_alone` |
| Each failure mode reported with a reason, never dropped | DESIGN §6.2 | L3 | four named taxonomy tests |
| Dangling cross-KB targets surfaced to the user | DESIGN §6.2 | L10 | `test_a_dangling_cross_kb_target_warns_with_a_reason` |
| Link coverage reported as the ceiling | DESIGN §6.2 | L10 | `test_link_coverage_counts_authored_links_only` |
| Aliases never inside a `pnk://` URI | DESIGN §2.2 | L7 | `test_an_alias_is_resolved_to_a_ulid_on_write` |
| Comment-preserving sidecar writer | DESIGN §2.2 | L7 | `test_comments_in_the_sidecar_survive_a_rewrite`, or an amended §2.2 |
| Unknown keys round-trip | DESIGN §2.2 | L7 | `test_unknown_keys_inside_a_link_entry_survive_a_rewrite` |
| Sidecar writes are rename-atomic | v0.1 rule 12 | L7 | `test_the_write_is_atomic_under_an_interrupted_rename` |
| Server reaches only its configured KBs | DESIGN §4.7 | L6 | `test_a_neighbour_outside_the_served_kbs_returns_its_kb_and_a_reason` |
| Publishing a KB publishes its links' ULIDs | DESIGN §4.7 | L2 | the amendment, plus `test_an_absolute_linked_kb_path_warns` |
| Typed verbs, hard caps, no query language | APPROACH §5 | L4, L6 | `test_depth_is_capped_server_side` |
| Score + frontier on every return | APPROACH §5 | L6 | `test_pinakes_links_returns_score_and_frontier_on_every_return` |
| Double cap: rows **and** token budget | APPROACH §5 | L4 | `test_the_token_budget_sets_truncated_independently_of_the_row_cap` |
| `confidence` unknown without `query` | APPROACH §5 | L6 | `test_pinakes_links_reports_unknown_confidence_without_a_query` |
| A neighbour is identifiable and fetchable | decision 11 | L5 | `test_a_cross_kb_neighbour_carries_its_kb_and_no_title` |
| Depth in logical hops | APPROACH §4A | L4 | `test_depth_counts_logical_hops_not_physical_edges` |
| Per-depth Python loop, not a recursive CTE | APPROACH §4A | L5 | `test_one_query_per_hop_not_a_recursive_cte` |
| Visited-edge dedup | APPROACH §4A | L4 | `test_a_hub_is_expanded_once_globally` |
| Membership excluded from output **and** budget | APPROACH §3 | G3 | three named tests |
| Hub damping on every shared-value hub | APPROACH §3 | G1 | `test_a_shared_tag_produces_linear_not_quadratic_edges` |
| Weight across a hub is the product of spokes | APPROACH §3 | G1 | `test_weight_across_a_hub_is_the_product_of_both_spokes` |
| Heading nodes scoped per document | APPROACH §3 | G1 | `test_a_heading_hub_never_connects_two_documents` |
| Hierarchy edges derived by prefix | APPROACH §3 | G1 | `test_parent_and_child_follow_heading_path_prefixes` |
| Edge-hub reporting in `pnk doctor` | APPROACH §3 | G4 | `test_edge_hubs_are_reported_highest_degree_first` |
| Authored links are sparse | APPROACH §3 | L2 | the density gate and its negative tests |
| Per-class gating | DESIGN §7 | shipped `b637be4` | `test_a_per_class_regression_is_caught_when_the_aggregate_hides_it` |
| Golden set: multi-hop, cross-KB and simple-lookup classes | APPROACH §9 | L9 | `test_the_committed_golden_set_is_well_formed` |
| The gate is reachable before the schema bumps | this plan | L9 | `test_the_single_kb_multi_hop_subset_has_headroom` |
| A channel regressing simple lookup stays off | APPROACH §9 | G3 | `compare()` plus gate clause 2 |
| The golden set lives with each template too | DESIGN §7 | L9 | the template's own `questions.yaml` |
| Free path stays free | CLAUDE.md | L5, L6, L7 | the subprocess gate, extended per increment |
| No `schema_version` bump before the links release | this plan | L10 | verification step 6 |
| The ClaudeKB realism check happens or is declined in writing | decision 1 | L10 | verification step 8 |

---

## Risks

| Risk | Why it is real | Mitigation |
|---|---|---|
| The synthetic corpus is unrealistically clean | One author writes the corpus, the links and the questions that traverse them | Density and degree caps with negative tests; weakest-useful relations only; **frozen weights** (decision 13) so at least the weights are not also fitted to it; the ClaudeKB check, owned by L10 |
| The gate cannot be reached | Five improvements with zero regressions needs ≥8 currently-failing single-KB questions | L9's headroom precondition, checked **before** G1 bumps the schema |
| The gate is reached by chance | ~18 questions is a small sample | An exact test, one gated configuration, no post-hoc tuning |
| The channel fails its gate | One GraphRAG-Bench-line study measured graphs *costing* ~13% on simple lookup | The links release ships first and stands alone |
| Frozen weights understate the channel | Unfitted priors may fail a gate tuned weights would pass | Pre-committed: fitting is exploratory and needs a new question set to license a re-gate |
| A concurrent agent lands conflicting work | `main` moved thirteen commits under two drafts, and a second worktree is active now | `git fetch` and re-read `origin/main` at every increment |
| Reverse-scan on a hook is unbounded | `pnk sync` runs on three git hooks | TTL, `--scan-links`, and `--sidecars-only` does not scan |
| A reverse row overwrites an authored one | `origin` is not in the `links` PK | `ON CONFLICT DO NOTHING`, with a test |
| Cross-KB reads race the other KB's sync | The advisory lock is per-KB | Never take the other lock; a torn read is a recorded reason |
| G1's edge derivation is slow at scale | It runs on every sync, on a hook path | Wall-clock reported before and after on both corpora, as an exit criterion |
| A YAML dependency creeps in | DESIGN §2.2 assigns the writer; CLAUDE.md says core deps stay light | Undecided, with a default that unblocks the chain without adding one |

---

## Iteration log

| When | What |
|---|---|
| 20260729 02:52 | Written. Seven decisions with the user; no adversarial pass |
| 20260729 03:31 | **Pass 1** — three reviewers: 22 HIGH, 30 MEDIUM, 15 LOW. Three findings were live defects on `main` and were fixed there first (`b637be4`). Release split in two; `entities`/`concepts` cut; the eval gate given a threshold |
| 20260729 04:05 | **Pass 2** — two reviewers: 26 HIGH, 30 MEDIUM, 8 LOW. **Six of pass 1's fixes were themselves wrong**, two self-refuting: L1 chose the rowid as its rebuild-stable key while `store.py` says a chunk has no identity across rebuilds; the "all of `expect`" rule rescored the 41 questions its own exit criterion protects; the gate cited a statistic the sign test does not measure; the cross-KB `title` fix needed either a per-query filesystem walk or the schema bump the release exists to avoid; a neighbour had no `kb` field and so could not be dereferenced at all; and the docs owner was deleted with the sweep it correctly banned. Decisions 11–13 taken with the user. **Pass 3 required** |
