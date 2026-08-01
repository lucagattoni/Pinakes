# Changelog

> ℹ️ **Version numbers below reflect the convention in use when this was written.** Unbuilt
> work is now **named, not numbered** ([STATUS.md](docs/STATUS.md)). This record is left as it was.

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.1] — 20260801 13:42

### Fixed

- **`[sources] include` can no longer walk out of the KB, or write files outside it.** `roots`
  already had to stay inside the KB; `include` was validated nowhere, and the walk's containment
  test was `candidate.relative_to(kb_root)` — purely lexical, so `docs/../../outside/x.md` *is*
  relative to the root as a string. Three measured consequences, all fixed: a `..` pattern indexed
  files outside the KB and **minted sidecars beside them**; an absolute pattern came out as a bare
  `NotImplementedError` traceback with no `error:` line and no remedy; and a **symlinked directory**
  inside the KB carried the walk out with no `..` and no absolute path anywhere in the manifest.
  An escaping or absolute pattern is now a `ManifestError` at load, matching the `roots` precedent,
  and the walk re-tests each candidate because no load-time check can see a symlink.

  **This is a behaviour change for a manifest that already carries such a pattern** — which is a
  manifest writing files outside its own KB, so the hard error is the right precedent rather than a
  softened warning. `pinakes.toml` is committed and shared: cloning a KB and running `pnk sync` ran
  *its author's* `include` against *your* tree. A pattern with `..` that lands **inside** the KB
  (`include = ["../notes/*.md"]` from `docs/`) is still accepted — what matters is where the path
  lands, not whether `..` occurs in it. `exclude` is deliberately not validated: a pattern there can
  only fail to match, never widen the walk.
- **A document reached by two legal spellings is one document.** The index key came from
  `relative_to`, which is lexical and hands back the `..` it was given, so `include =
  ["../notes/*.md"]` keyed a file as `docs/../notes/n.md`. With that file also reachable under a
  second root it was indexed once and then **failed twice** — *"appeared after the walk had already
  read this directory"* — because the sidecar found under one key was invisible under the other,
  and the unmatched-files sweep reported an indexed document as unmatched. The key now collapses
  `..` lexically. It is not *resolved*: that would follow a symlinked directory and silently re-key
  every document under it, which for an existing KB is a path change on a permanent identity.
- **`tools/link_density_gate.py` no longer dies on a root reached through a symlinked parent.**
  `census` resolved one of its two bases and not the other, so on macOS — where `/tmp` symlinks to
  `/private/tmp` — running the gate against a copy of a KB exited with a `ValueError` traceback
  instead of a verdict. It is the tool an executor is told to run against a copy.

## [0.7.0] — 20260801 12:40

**The graph release's gate was measured and cannot be reached on this corpus.** The expansion
channel defaults on only if enough multi-hop golden-set questions *improve*, and an improvement can
only come from one that fails today: 7 were needed, **1 fails**. So the structural edge set and its
`schema_version` 3 bump do not start, and this release is the evaluation work that measured it.
Numbers, and the two findings behind them, in
[`docs/STATUS.md`](docs/STATUS.md#can-the-graph-releases-gate-be-reached--measured-20260801-1214).

### Added

- **Per-question evaluation outcomes are a committed artifact.** `python -m pinakes.eval <kb>
  --write-baseline` now writes `eval/outcomes.json` beside `eval/baseline.json` — one row per
  question (`id`, `kind`, `hit`, `hit_rank`, `confidence`) under a header recording the models and
  retrieval settings the run used. `eval.score_rows` recomputes every metric from those rows alone,
  so a golden set's per-question history is checkable offline, with no weights and no network. Six
  aggregates cannot say *which* questions moved, and that is what a paired before/after comparison
  needs.
- **Questions carry a stable `id`.** Hand-written in the golden set and derived from the question
  text when absent, so an existing `questions.yaml` still loads. A repeated id is refused: it is
  what pairs a before row with an after row, so a duplicate silently drops a question from every
  comparison.
- **A `simple-lookup` class, and the golden set grows from 41 questions to 74.** Twenty ordinary
  factual questions as the control class a graph channel must not damage, and thirteen further
  single-KB multi-hop questions authored from corpus structure. The demo KB's baseline is rewritten
  once for the growth; the previous one is preserved as `eval/baseline-pre-growth.json`, and a test
  re-scores the committed artifact to prove the questions already in the set score exactly what
  they scored before.

### Changed

- **A golden set's `kind` is validated against the known set instead of defaulting to `lexical`.**
  An absent or unrecognised `kind` is now an error naming the six that exist. A silent default is a
  claim about how a question was authored, and a wrong one puts it into a class whose per-class
  score then measures two different things.
- **An empty golden set skips the evaluation with a printed reason, rather than failing it.** The
  `notes` template ships `questions: []` and scaffolds an empty `docs/`, so it cannot ship
  questions naming documents that do not exist — which made `make eval` fail by construction on
  every freshly `pnk init`ed KB. The committed golden set is still asserted to be non-empty, so an
  *emptied* one cannot pass quietly.
- **`pinakes.search.fused_candidates` exposes the fused candidate list** — the stage between
  retrieval and reranking. It is what a graph channel takes as its roots and what the reachability
  probe measures from; `search()` now calls it, so there is one implementation of the funnel rather
  than a measurement that can drift from it.

## [0.6.0] — 20260801 10:51

### Added

- **`pnk link <source> <target> --rel REL` authors a link** from the command line, writing one
  `links[]` entry into the source document's own sidecar and nothing else. The target takes three
  forms, tried in order: a `pnk://` URI (`pnk://self/…` included), `<alias>:<path>` naming a
  declared `[[links.kb]]`, or a path in this KB. Aliases and `self` are resolved to ULIDs **before**
  anything reaches disk, which is what makes a link mean the same thing on someone else's machine.
  The rewrite goes through the round-trip writer, so comments, quoting, blank lines, key order and
  unknown keys — including one inside a `links[]` entry — all survive.
- **It never mints a sidecar.** A source that has none is refused with `pnk sync` as the remedy: a
  `links[].to` needs a ULID only sync mints, and writing a fresh one over a file that may already
  hold a permanent one is the unrecoverable case. An unreadable source sidecar is reported and left
  exactly as it is; the write itself is rename-atomic.
- **An alias resolves through the partner's own `[kb] id`**, and a disagreement with the local
  `[[links.kb]] id` is refused rather than guessed — one of the two names the wrong KB, and what
  would be written is permanent. A well-formed `pnk://` URI whose target is *not* on this machine is
  written, because both ULIDs are already in it.
- **Running the same `pnk link` twice writes nothing the second time** and says so. Two different
  relations to one target remain two entries; a document linking to *itself* is refused.
- **A symlinked document can be linked, and a symlinked sidecar is written through** rather than
  replaced by a regular file. Everything above the final path component is resolved and the
  component itself is not, so a symlinked *file* — which `pnk sync` does index — is accepted, while
  a symlinked *directory* cannot carry a link out of the KB, and an absolute path whose ancestor is
  a symlink (macOS `/tmp`, or any checkout behind one) is no longer refused as "outside this KB".

- **`[kb] requires_pinakes` — a manifest can declare the oldest pinakes that can read it.** Unknown
  keys are a hard error by design, so a KB written by a newer pinakes previously failed on the first
  key this build had never heard of and reported it as a typo, when the real problem was an
  out-of-date pinakes. The floor is read in a pre-pass **before** strict validation — after it, the
  parse has already died on the unknown key and the field would be unreachable in exactly the case
  it exists for. A floor only (`">=0.5.0"`): a KB is readable by the version that wrote it or any
  newer one, so there is no ceiling to express and no specifier grammar to parse. Absence means no
  floor declared, never a refusal, and `pnk init` does not stamp the field — a fresh KB carries no
  key an older pinakes would choke on, so a stamped floor would lock out readers for no gain.

### Changed

`pnk doctor` reports link coverage as the **ratio** DESIGN §6.2 promises — `8 of 30 documents
linked (27%)` — rather than an edge count, and resolves cross-KB targets instead of declaring them
unchecked. A target whose own KB is on this machine and does not have the document is now a WARN
with a count; one whose KB is *not* here is counted and left alone, because an index that cannot
see a KB has no standing to call its documents missing.

A new **linked KBs** check reads `[[links.kb]]` from the manifest alone, so it runs on a freshly
cloned KB with no index — which is exactly when a committed absolute `path` matters. Four outcomes:
a path that names no path at all, a KB absent from this machine, an absolute path (warned even when
it resolves, because it publishes one machine's layout), and everything fine.

A KB where nothing links to anything is now a WARN nudge rather than a silent OK.

`pnk doctor` on a KB with no index now says *"not built yet, so the link checks did not run"* rather
than only *"not built yet"*. Every index-backed check is produced from one place, so an absent index
silently removed them all — including link coverage, which is the check a reader consults after
authoring links. A report that stops listing a check reads as nothing to report about it.

### Fixed

- **`tags:` or `provenance:` written with nothing under them** were rewritten to `tags: []`
  and `provenance: {}` on any sidecar rewrite, against the byte-identity promise. Reachable before
  now only from a paid PDF extraction; `pnk link` would have reached it on a first link.


Four tests that build an unreadable directory now skip where the process bypasses directory
permissions (root, as in CI's container) instead of asserting against a precondition they could not
construct, and a test asserting `pathlib`'s exact "unacceptable pattern" wording now asserts the
property it meant. No shipped behaviour changes.

- **Retrieval results no longer depend on how the index was built.** Every tiebreak in the pipeline
  ultimately resolved to `chunks.id` — the rowid, which the schema says has no identity across
  rebuilds — so two indexes over byte-identical sources could return different documents for the
  same query. Measured on the golden set: one question in 41 answered differently after an
  incremental sync than after a `--rebuild`. Ordering is now total on
  `(documents.path, chunks.ordinal)` at the vector array, the BM25 cut and hydration, and the vector
  sort is stable, which additionally stops a newly added document reordering tied results elsewhere
  in the corpus. **No measured number moved**: the demo KB scores byte-identically to its committed
  baseline before and after, which is what a change that only breaks ties should do.

- **A `check.sh` gate and two CI jobs hold it there** — `tools/eval_reproducibility_gate.py` sweeps
  four kinds of corpus change (a document edited, added, removed, renamed) offline in about a
  second, and CI diffs per-question outcomes between `ubuntu-latest` and `macos-latest`, which is
  the half of the question one machine cannot answer.

- Making the BM25 cut a total order costs a join: **+11.5 ms** (23.9 → 35.4) on a synthetic
  50k-chunk corpus where every chunk matches every query term, which is the worst case rather than a
  typical one. `load_vectors`' new ordering costs nothing measurable — both query plans already
  sorted through a temp B-tree.


- Two behaviours found in 0.5.0 after it was published, recorded here because they can only change
  in a later release. A sidecar carrying its own **`%YAML 1.1` directive** is still parsed at 1.1,
  so `country: NO` becomes `False` in the index and `false` on disk on any rewrite — the
  cross-document version leak was fixed before release and tested, this same-file case was not.
  And an **integral `!!float`** keeps its tag *and* gains quotes on rewrite (`f: !!float 3` →
  `f: !!float '3'`), against the note that the tag itself is not written back; the locking test
  asserts `!!int` and `!!seq` only.

## [0.5.0] — 20260731 11:27

### Added

- **A second synthetic corpus, sparse authored links across both, and a gate that keeps them
  sparse** (L1 of the links release). `tests/partner-kb/` is a partner museum that transacts with
  the archive in `tests/demo-kb/` — loans both ways, courier and condition reporting, a shared
  emergency plan, a joint digitisation programme. 21 documents, its own KB ULID and manifest, and
  no golden set: cross-KB behaviour is verified by traversing it, not by scoring it. Both corpora
  gain forward-authored links (the demo KB had none), and `tools/link_density_gate.py` — in
  `check.sh` and its own CI job — caps the share of documents carrying links, caps any one
  document's degree separately (density alone permits a single hub wired to everything), and
  requires at least one same-KB link per corpus. It reads the committed sidecars and never an
  index, so it runs where no index exists and counts the same population `pnk doctor` reports.
  Nothing about retrieval changes: the golden-set numbers are identical.

- **`pinakes_links` on the MCP surface** (L5 of the links release) — the same traversal `pnk links`
  performs, for the agent this project calls its primary caller. `depth` is capped at 3 server-side
  and there is no query language, ever; `score` and `frontier` come back on every call, not only
  when something interesting happened. **`confidence` is always `unknown`**: the signal is
  calibrated per KB on the reranker score of a retrieved *passage*, a traversal neighbour is not
  one, and a list spanning two KBs has no single manifest whose thresholds apply — reporting
  low/medium/high would be an invented signal. A neighbour in a KB **this server was not pointed
  at** is returned with `reachable: false`, its ids and a reason, because omitting it would hide a
  link that exists; reachability is a property of the server invocation, not of a manifest. The
  free-path gate's MCP handshake now **calls** the tool rather than only listing it — listing walks
  signatures and docstrings, so a tool whose body imported a paid client would have listed
  perfectly and never been seen.
- **One traversal projection, shared by `pnk links --json` and `pinakes_links`**
  (`pinakes.graph.present`). The two answered the same question through two hand-written copies of
  the same dict literals and had already drifted — the MCP `frontier` carried a `distance` the CLI's
  did not, `scored_by_query` reached only one of them, and `unresolved` dropped the `kb_id` its
  sibling lists carried. Nothing failed, because nothing compared them. **`direction` is now keyed
  by `(node, rel)` rather than by node**: given `a --related--> b` and `b --cites--> a`, asking about
  `a` reported the citation as running *from* `a` — backwards, on both surfaces, since L4. One
  relation written from both ends now reads `both`. **An unrecognised `direction` is refused**
  (`TraversalError`) instead of running neither query and returning a confident empty answer;
  `DIRECTIONS` had been defined and never enforced, and only `argparse` was catching it on the CLI.
  **An empty answer now says whether your own arguments emptied it** — `direction="out"` on a
  document whose only link is inbound used to advise "No links from here, search instead", which
  tells an agent to stop traversing a graph it is standing in.
- **A neighbour's `direction` no longer changes with `depth`.** The `both` merge is decided inside
  one expansion and never across them: direction is relative to the node being expanded, so an edge
  found while expanding an unrelated parent was rewriting a row already returned from the start
  document. `pnk links` prints `<->` for a relation written from both ends. An unknown `direction`
  is now refused *before* a query loads the embedding backend, rather than after cosining the whole
  KB to answer a call that could never succeed. And a document whose links all point at documents
  the KB no longer has is no longer told it has no links — the payload was listing them under
  `unresolved` in the same breath — on both surfaces, and worded without a direction, because a
  deleted document keeps its outbound `links` rows and "this document's links point at…" would
  then credit a link to whichever end did not write it. When the caller also narrowed the walk,
  the narrowing is reported first: a live neighbour may sit one dropped argument away, and sending
  them to full-text search instead is the worse of the two wrong answers. `pnk links` says the same
  three things in the same order, so a person and an agent get the same account of an empty walk.

- **`pnk links` — what a document connects to, and what connects to it** (L4 of the links release),
  over a SQLite provider for L3's traversal core. One query per hop in a Python loop, never a
  recursive CTE: the caps live in the core, and a recursive query would have to re-implement depth,
  fan-out and dedup in SQL to honour them. Takes a ULID or the path `pnk search` prints; filters by
  `--rel` and `--direction`; `--depth` is server-capped at 3; `--query` ranks neighbours by
  similarity instead of by edge, and is the only mode that loads a model at all. Every neighbour is
  a document, and `kb_id` is always a ULID — never `[kb] name`, which is free to rename, and never a
  `[[links.kb]]` alias, which means nothing elsewhere. A neighbour in another KB is **terminal**:
  returned, never expanded, at any depth, and carrying no `title`, because this index holds that
  KB's links and not its documents. Links whose target is missing come back under `unresolved` and
  never as neighbours — the two lists are disjoint.

- **`pnk sync` now records what other knowledge bases link *into* this one** (L2 of the links
  release). For each `[[links.kb]]`, it reads that KB's **committed sidecars** — never its index,
  which is gitignored, absent in a fresh clone, and unreadable without holding a second KB's lock —
  and writes the entries targeting this KB as inbound rows, filling `kb_refs` for the first time
  since the column existed. Only links targeting *this* KB are kept: a partner's link to a third KB
  is discarded rather than recorded as a graph this index could never complete. A partner's own
  `[kb] id` is what identifies it, and a mismatch with the `[[links.kb]] id` declared here scans
  nothing rather than guessing which is right. Replacing a partner's rows is all-or-nothing and
  happens only after a complete walk, so a sidecar that will not parse mid-scan leaves the
  previously known edges alone instead of deleting them; a KB dropped from `[[links.kb]]` has its
  rows and `kb_refs` entry removed, which nothing else would ever have done. The scan is bounded by
  a one-hour freshness window because `pnk sync` runs on `post-commit` and `post-merge`, and
  **`--scan-links`** ignores it. Every failure — unreachable path, id mismatch, unparseable
  sidecar, a target this KB does not have — is reported with a remedy and **does not fail the
  sync**: a partner that is simply not on this machine must not block every commit. The partner's
  own `[sources]` is honoured in full — `exclude` included, which matters because the shipped
  template stamps one — and a `roots` entry that has vanished, points outside the partner KB, or
  uses a pattern the walker rejects is a reported failure rather than a walk that quietly finds
  nothing and deletes what it had.

- **The bounded traversal core** (L3 of the links release) — `pinakes.graph.traverse`, pure, with
  no SQLite and no I/O of its own. Depth counts logical hops rather than physical edges; fan-out is
  capped by the new `[retrieval] adjacent_k` (default 8) and applied **after** ranking, so a cap
  never selects by whatever order the edge source happened to return; the response is capped on row
  count and token budget **independently**, because the two have different remedies. Every bound is
  clamped server-side — depth at 3, fan-out at 64 — and a new gate in `check.sh` and its own CI job
  drives the shipped core at `depth=99, adjacent_k=10000` against a wide, deep fixture graph to keep
  that true. Neighbours found but not expanded come back on a `frontier` carrying one of five
  reasons in a stated precedence, and links whose target does not resolve are returned rather than
  dropped. `adjacent_k` is settable but deliberately **not** stamped into the template: a manifest
  carrying an unknown key cannot be read by an earlier pinakes at all.

### Changed

- **`ruamel.yaml` replaces `pyyaml` for reading and writing sidecars.** A rewrite now preserves
  comments, quoting style, block scalars and blank lines, because `write()` reconciles the known
  keys *into the document that was read* rather than rendering a fresh one. `pyyaml` leaves
  `[project.dependencies]`; the dependency count is unchanged.

  This also fixes a silent corruption that had nothing to do with comments. `Sidecar.extra` is
  documented as *"round-tripped untouched"* and was not: under YAML 1.1, `country: NO` was read as
  `False` and written back as `false`, `shelf: 0755` became `493`, `confirmed: yes` became `true`
  and `duration: 1:30` became `90`. YAML 1.2 reads them as the strings they visibly are.

  **Four breaking changes**, all consequences of the library. A **duplicate key** is now a hard
  error rather than silent last-wins — which of the two values was meant is not recoverable, and
  ruamel's own message ends with a URL for switching the check off that pinakes deliberately does
  not pass on. A **string field that YAML 1.2 resolves as a number** (`1e3`, `1E3`, `0o17` in
  `title`, `created`, `tags[]`, `links[].to`, `links[].rel`) is refused. And an **`!!str`-tagged
  value** is refused — the only *working* tag that changes behaviour; `!!int`, `!!float`, `!!bool`,
  `!!seq` and `!!map` still load to the same values they always did, though the tag itself is not
  written back (`!!int 3` comes back as `3`). And **a non-string key at the
  top level, or a mapping mixing string and non-string keys at any depth, is refused** — the index
  stores metadata as JSON, and a sidecar with `1: a` at the top level used to crash `pnk sync` from
  inside the index writer instead. A *uniformly* non-string-keyed **nested** mapping is still
  accepted and silently coerced (`outer:` / `  2: b` becomes `{"2": "b"}`), as it was before.

  **Separately, four shapes whose unhandled `TypeError` becomes a named error** — `!!binary`,
  `!!set`, `!!timestamp` and a bare date all crashed `pnk sync` out of `json.dumps` before, and are
  now refused at `read()` with a remedy. That is a fix, not a break.

  **A documented widening:** a *custom*-tagged mapping or sequence (`!custom {a: 1}`) was a parse
  error and is now accepted, because it serialises. Not `!!map`/`!!seq`, which were never refused.

  **One regression, named rather than fixed.** A sidecar whose value contains a *self-referential*
  anchor (`mine: &x` with `b: *x` inside it) used to crash `pnk sync` with `Circular reference
  detected` when the index serialised it. It is now silently read as `null`, and the anchor and
  alias do not survive the next write. Pathological input, and the only place this change trades a
  loud failure for a quiet one — which is the direction that matters, so it is written down.

  **A reused anchor name is refused**, as it was before the swap. The new parser accepts it and
  resolves every alias to the *last* anchor of that name — so `a: &dup 1`, `b: &dup 2`, `c: *dup`
  would have made `c` equal 2 — reporting it only as a warning on stderr.

  **A `links:`, `tags:` or `provenance:` key with nothing under it no longer crashes a write.**
  `links:` alone — what a sidecar carries before its first link is added — raised an unhandled
  error out of `pnk sync`, including the write that follows a paid extraction.

## [0.4.1] — 20260729 07:48

### Changed

- **[`plans/links-and-graph.md`](plans/links-and-graph.md) revised after a sixth adversarial pass —
  2 HIGH, and the pass-5 fixes verified correct.** Both were narrow, and both were introduced by the
  previous round's own repairs.

  **A gate clause stated one of its two guards backwards.** Clause 4 made a *rise* in
  `confidence_coverage` a stop. A rise is an improvement — `eval.py` treats the *drop* as the
  regression, with the comment *"losing the ability to say anything is a regression too"* — and the
  metric is 1.0 in the committed baseline, so it cannot rise at all. The clause was a stop condition
  that could never fire, while the guard the same-commit re-baseline actually removes went
  unrestored. It now enumerates all six `compare()` families with the direction the code checks, and
  says which single term the re-baseline may absorb.

  **The anti-circularity guard was asserted to live in an increment it never reached.** The
  structural-edge increment says *"the guard is in G2 and G5"*; the phrase appeared in G2 and G3 and
  nowhere in G5. An engineer building G5 from G5 would compute the sign test once over all edges —
  including the links hand-authored into both corpora by an earlier increment — pass, flip
  `graph_channel` to default-on, and cut the release. The gate is now computed **twice, with and
  without authored edges**, both p-values recorded, and the channel ships `off` if only the authored
  run passes. That is the same "1.00 by construction" reasoning that removed cross-KB questions from
  the golden set three passes ago.

  Also closed: the stale-reverse-edge delete is now scoped by `origin` as well as source KB (under
  the plan's own self-listing fixture, an origin-blind delete removes the authored rows the insert
  guard exists to protect); `adjacent_k` gained the server cap its own gate asserts against;
  `pnk link`'s free-path gate edit found an owner; the version floor is verified at whichever cut
  ships it, rather than only on the path where the final increment runs; and five amendment rows
  gained a home in their increment's Docs line.

- `plans/links-and-graph.md` revised after adversarial pass 7 (6 HIGH across two reviewers), and
  the `pnk link` YAML question settled. L1–L8 are now implementable; G1–G6 are not — G5's gate
  clauses are re-reviewed before G5 is built. L2 was rewritten around four defects: a per-KB delete
  that turned any mid-walk failure into the mass deletion the same section forbids, a delisted
  partner whose rows no delete could reach, a scan that could not compute `src_kb_id` from sidecars
  at all (a sidecar does not carry its KB's ULID) and whose natural workaround would re-target a
  partner's `self` links at the local KB, and a failure taxonomy whose only recording channel makes
  `pnk sync` exit non-zero on a git hook. G5 was rewritten around two: the gate made the
  *without*-authored run binding while shipping the *with*-authored configuration, and G2's headroom
  threshold never said which of its two reachability numbers licensed an irreversible
  `schema_version` bump.

### Fixed

- **0.4.0 shipped without the three-document post-release sweep** — the rule added to `CLAUDE.md`
  eight minutes before it was cut. `docs/STATUS.md` still read *"Latest release: 0.3.0"*, its
  *Published on PyPI* table still listed *"0.2.2 and 0.3.0"*, and the roadmap had no 0.4.0 row while
  the 0.3.0 row still described `path:page` citations as unreleased — they shipped in 0.4.0. Swept,
  with the upload time taken from the index (0.4.0, 20260729 03:37 UTC).

  **A caveat the rule needs, learned while checking this one:** `https://pypi.org/pypi/<pkg>/json`
  is CDN-cached, and a query moments after an upload can return the *previous* release list. The
  first check here reported 0.4.0 missing from an index that already had it — which would have
  turned a correct release into a false alarm, or worse, licensed a re-upload attempt. Query with
  cache-busting, and cross-check `https://pypi.org/simple/<pkg>/`, before concluding a publish
  failed.

  The release itself was correct end to end: tag `v0.4.0`, `__version__` agreeing, wheel smoke test
  green, GitHub release published, and the `Publish to PyPI` step succeeded with its
  *"Explain why nothing was published"* fallback skipped.

- **`pnk sync` no longer destroys a sidecar it cannot parse, and no longer aborts over one.** A
  sidecar that failed to load — a hand-edited `links[]` entry with one wrong character in a ULID is
  the cheapest way there — was dropped from the walk, which made its document look like one that
  had never been ingested, and the mint path then wrote a freshly minted sidecar **over** it. The
  document's permanent ULID and every authored link went with it, `pnk sync` reported success with
  no failures, and `pnk doctor` afterwards reported every sidecar readable and no duplicate ids,
  because the evidence had been overwritten by the thing that destroyed it. Minting now refuses
  where a file already exists, and names the parse error rather than merely the existence. A second
  path had the opposite fault: for an *already-indexed* document whose sidecar breaks while its
  content is unchanged — the likeliest way a user meets this at all — the error escaped `sync()`
  entirely, so one hand-broken file aborted the whole corpus with no failures row and no commit.
  Both now record a failure and let the run continue. One consequence to know about: because
  `--sidecars-only` can now fail, a `pre-commit` hook blocks a commit that stages a document whose
  sidecar will not parse. Present since v0.1.

## [0.4.0] — 20260729 05:32

### Added

- **A docs change now audits its neighbourhood, not its diff.** Before landing any documentation
  edit, the surrounding claims are re-read against four questions: is this **consistent** with the
  other docs, does its **logic** still hold, has it been **superseded** by a decision taken since,
  and is it **outdated** against the code, the package index or the clock.

  The rule exists because whatever made the line you came to fix go stale almost certainly reached
  its neighbours too, and reading the diff cannot show that. Measured on 20260729: a one-line PyPI
  correction was requested, and sweeping around it found five more stale claims — a shipped release
  still listed as unbuilt in two separate tables, an install block missing the headline capability
  of the last two releases, a README sentence implying a feature that is not built, a runbook still
  described as producing numbers the project "admits it lacks" after the run had happened, and a
  design note reading "no increment assigned" for work a plan had since assigned. Every one was a
  single-line edit; none was visible from the change that prompted the sweep.

  Full rule in [`docs/README.md` § Conventions](docs/README.md#conventions), with a one-line pointer
  from `CLAUDE.md`'s Docs section.

- **`path:page` citations, on the CLI and the MCP surface in the same increment** (I8). A PDF
  passage cites `docs/paper.pdf:p7`, or `docs/paper.pdf:p7-8` when the chunk straddles a page break.
  The `p` is deliberate: `:12-480` already meant character offsets, so a bare `:12-13` would have
  been a page range and a character range in one syntax. Non-paged sources are unchanged.
- **`pnk search --json` and `pinakes_search` carry `page_start`/`page_end`** as separate integers
  beside the rendered `citation` (both `null` for a source with no pages), so nothing has to parse a
  citation back apart.
- **`pinakes_get` is page-aware**: `page_start`/`page_end` read one range, page boundaries come back
  marked by a `[page N]` line, and the payload reports `page_count`. A PDF is served from the
  extraction cache — the same text the index was built from — never by re-extracting.
- **`pnk doctor` gains a `text yield` check**, reporting **per page, never per document**: the
  median non-whitespace characters per page, then the pages below the fitted floor by path *and*
  page (`docs/scan.pdf p4-9`). A document-level median stays silent on a 200-page report with eight
  scanned inserts, which is exactly the document worth knowing about. Its remedy names the paid
  extractor and says that it spends.
- **Three end-to-end traces** (`tests/test_pdf_trace.py`): a table-cell word across six hops from
  extraction to the agent surface, every filter dimension actually selecting PDF rows, and one paid
  slice's cost from estimate through reservation, the response's own `usage`, reconciliation and
  into what `pnk budget` prints.

- **`docs/VERIFICATION.md`** — every promise this project makes, and the test that holds it, with
  `tests/test_verification.py` asserting each named test exists. It replaces `plans/v0.2.md`'s
  verification table as the *lookup*: that table wrote its test paths before the tests existed, and
  implementation renamed most of them, so **61 of its 98 references did not resolve**. The
  properties were almost all tested — under better names — but a table whose paths cannot be
  resolved verifies nothing, which is the failure its own preamble warns about. The plan keeps its
  predictions as the record of what was intended.
- **`pnk doctor` now proves its own checks are tested** —
  `tests/test_doctor.py::test_every_doctor_check_is_exercised_by_a_test`. Adding a check is one
  line, and nothing about that line requires a test to exist.
- **`pnk sync --help` is asserted to state each dangerous flag's *limit*, not only its capability**
  — `--force` widens no cap, `--yes` raises none, `--clear-cache` never touches the ledger,
  `--estimate-only` generates nothing.
- **CI's wheel smoke asserts the two files the spending guards read** (`prices.toml`, `floors.toml`)
  are present in the built wheel, and that a core-only install names the extra it needs rather than
  producing a traceback.

### Changed

- **[`plans/links-and-graph.md`](plans/links-and-graph.md) restructured after a third adversarial
  pass — the links release never needed the golden set.** Two reviewers returned 24 HIGH, and three
  of them collapsed into one root cause: `eval.py` is single-KB in its bones (one connection, one
  manifest, one backend, `retrieved` as local path strings), so a cross-KB question forced through
  it scores **0.00 by construction** — the hop can never be followed — or **1.00 by construction**,
  merely confirming a link the corpus author hand-wrote. Neither can decide anything, and pass 2 had
  already established such questions cannot respond to `graph_channel`.

  Since the links release changes no retrieval, it needs no golden-set work at all: traversal
  correctness is directly testable. Cross-KB eval is cut entirely, all measurement work moves to the
  graph release where it *is* the gate, and the plan becomes 8 + 6 increments instead of 10 + 4.

  Also corrected:

  - **The determinism increment was a provable no-op.** Its three proposed tiebreaks could never
    change an outcome: cross-document ties are already totalised by `documents.path`, and within a
    document rowid order *is* ordinal order in every write path that exists. The instability a
    rebuild could introduce is upstream, in the candidate lists that set the RRF ranks, where no
    final tiebreak reaches. It is now a *measurement* increment — establish reproducibility, fix
    only what the measurement shows.
  - **The gate's statistic had no artifact that could produce it.** An exact sign test needs
    per-question before/after pairs; `run()` discards outcomes, `write_baseline` stores aggregates,
    and `compare()` reads only those. Per-question outcomes are now a committed artifact with an
    owner.
  - **The headroom threshold was asserted, not derived, and its test could not fail.** It checked a
    number the author had committed. It now runs the questions and counts, and the number follows
    from the gate table: 7 currently-failing questions to tolerate one regression.
  - **`requires_pinakes` cannot explain a key retroactively** — a pinakes built before it has no
    pre-pass and fails on `requires_pinakes` itself. Deferring `adjacent_k`'s template stamp to that
    increment bought nothing; new keys simply stay out of the template in both releases.
  - **A neighbour's `kb` field was unspecified across three namespaces** — `[kb] name` (documented
    as free to rename), `[[links.kb]] name` (machine-local), and the ULID. Only the ULID is
    dereferenceable, which is the same reason a `pnk://` URI carries no alias. The field is now
    `kb_id`, and a test asserts `pinakes_get` actually resolves what `pinakes_links` returns.
  - **Twelve increments still told a future agent to write a `CHANGELOG.md` entry**, forbidden by
    the fragment convention that landed while this plan was being written — and no gate catches a
    direct edit. Both release procedures also omitted `tools/fragments.py --apply`, which would have
    shipped every fragment unspliced.

- **[`plans/links-and-graph.md`](plans/links-and-graph.md) revised after a fourth adversarial pass —
  13 HIGH, down from 24, and the first pass with no self-refuting fix.** Five findings collapsed
  into one decision: **the traversal surface serves documents only.** Tag, directory, heading and
  chunk nodes have no `doc_id` and cannot be expressed in the neighbour shape the plan pins with a
  test, so they stay internal to the expansion channel permanently. That makes the structural-edge
  increment genuinely inert rather than aspirationally so, removes a released-payload change nobody
  owned, and deletes a filter-flip whose conditionality was undecided in a way that broke either
  reading.

  **Cross-KB traversal is one hop, and the plan now says so.** KB *K*'s `links` table holds its own
  outbound rows and its inbound ones, never a third KB's outbound rows — so a depth-2 hop *through*
  a cross-KB neighbour has nothing to walk without opening that KB's index, which DESIGN §6.2
  forbids. The Goal had been claiming more than the data model can deliver; a cross-KB neighbour is
  now terminal at any depth, and `frontier` says so rather than leaving a caller to retry a hop that
  can never succeed.

  Also closed:

  - **`frontier` was contract text with no owner and no definition** — half of the pair the research
    says an agent's loop consumes. It belongs to the pure core, and an entry now carries *why* it
    was not expanded: `depth`, `fanout`, `rows`/`tokens`, or `terminal`. A caller that cannot tell
    `fanout` from `terminal` retries forever.
  - **The channel's gate conflicted with `compare()`, which is a hard CI gate.** Five misses
    becoming hits, two at low confidence, is 0.030 against a 0.02 tolerance — CI red on a channel
    the gate had just blessed. Turning the channel on now re-baselines in the same commit, with the
    rise decomposed so that only *lost* confidence counts as a regression.
  - **The go/no-go for the graph release measured the wrong quantity.** It counted questions that
    currently fail, but a question can only be lifted if its evidence is reachable in the edge set —
    and with `mentions` cut, the authoring rule ("evidence split across two documents with no shared
    vocabulary") actively selects for pairs the remaining edges cannot bridge. The research's own
    channel-reachable ceiling comes back as an in-memory probe that needs no schema change, so the
    decision happens **before** every KB in existence is forced to rebuild.
  - **The node identity scheme spanned five incompatible id spaces** and was never written down —
    including a chunk key that would have used the rowid the storage layer documents as having no
    identity across rebuilds. Specified, with an orientation rule, because a `src`-only damping
    query silently drops half of every symmetric relation.
  - **The graph release now has a stated fallback**: if the precondition fails, the three increments
    that do not depend on structural edges ship on their own rather than stranding finished work.

- **[`plans/links-and-graph.md`](plans/links-and-graph.md) revised after a fifth adversarial pass —
  3 HIGH, down from 13.** All three sat on the seams the fourth pass opened, and one of them was a
  decision resting on a false premise.

  **Terminality is a policy, not an emptiness.** The plan justified making cross-KB neighbours
  terminal by claiming KB *K*'s index has nothing to walk past one. `store.py` says the opposite in
  a comment on the table itself — *"a reverse link's source lives in another KB"* — so a
  reverse-scanned row is keyed on the **foreign** document and a depth-2 query from one returns real
  results. The conclusion survives on a better reason: K holds only the partner's links that point
  *back at* K, never its internal ones, so expanding through a foreign document shows a
  systematically incomplete slice that no caller can distinguish from the whole. The consequence for
  the build is sharper than the wording — terminality now needs an **explicit suppression**, a test
  fixture that actually contains the back-link rows (without them the test passes against an
  implementation with no guard at all), and a mutation target, none of which the plan had.

  **Whether authored `doc ↔ doc` edges are in the expansion channel was never stated**, while the
  orientation rule, the reachability probe and the gate's pessimism argument each depended on the
  answer. They are — the research's own argument for counting depth in logical hops is that physical
  counting would strand them. Stating it exposed a circularity the plan had already refused once:
  the gate could be satisfied by hand-authored links bridging hand-authored questions, the same
  "1.00 by construction" shape that got cross-KB eval cut. Reachability and the gate are now both
  reported **with and without** authored edges, and a gate that passes only *with* them is recorded
  as such rather than counted as evidence that derived structure helps.

  **The previous fix disarmed a guard it wasn't aiming at.** Re-baselining in the same commit as
  turning the channel on silences every metric in `baseline.json`, including `false_confidence` —
  which is sensitive to the channel by the same mechanism and is *not* covered by the per-class
  clause, because a no-answer question can stay a clean non-hit while flipping to HIGH confidence.
  One flip is 0.125 against a 0.02 tolerance. A fourth gate clause makes a rise in
  `false_confidence` or `confidence_coverage` a stop rather than a re-baseline.

  Also: `frontier` reasons went from four to five (the two response caps are independently
  observable, so they cannot share one) with a stated precedence and an amendment row; the traversal
  core is now generic over a provider-supplied node identity, so one implementation serves both the
  document surface and the structural channel instead of the graph release needing a second
  expander; and the conditional third release has a stated shape rather than being discovered at the
  cut.

### Fixed

- **`docs/README.md` still told every increment to write its `[Unreleased]` entry into
  `CHANGELOG.md`** — the edit the fragment convention had just forbidden. `CLAUDE.md` gained
  `changelog.d/` and `retro.d/` in the same change that introduced them, and the routing table that
  `CLAUDE.md`'s own build order defers to ("the docs are built so an increment touches few files")
  was left pointing at the old procedure. Two documents disagreed about a rule that exists to stop
  two agents disagreeing.

  It matters more than a stale line usually would, because nothing catches it: `tools/fragments.py
  --check` validates the fragments that exist and has no opinion about a commit that edited
  `CHANGELOG.md` directly, so an agent following the checklist would have landed the violation
  green.

  The landing checklist now ends in a `changelog.d/` fragment and a `retro.d/` one, the fact-routing
  table says where each of those two documents is *written* as distinct from where it is *read*, and
  the index warns that anything unreleased is still sitting in its fragment directory rather than in
  the document — which is also the answer to why "re-read `RETROSPECTIVES.md` before each increment"
  can quietly miss the newest findings.

- **`pnk doctor` crashed on a KB whose PDFs name an extraction backend this install does not know**
  — a KB written by a newer pinakes, or one whose extra has since been uninstalled.
  `is_paid_backend` raises on an unrecognised name, and a health check may not be the thing that
  fails on an unhealthy KB. It now reports them, exactly as the §4.4 coherence check already did.
- **A KB whose PDFs are all paid-extracted no longer gets a permanent `text yield` warning** whose
  remedy would have spent money. They are skipped deliberately, and the check now says so.
- **`pinakes_get` reports an out-of-range page bound as the bound the caller passed**, not as a
  range it never asked for: `page_start=5` on a two-page document said "pages 5-2 is not a range
  within it".

- **Six claims that 0.3.0 falsified, including one plain factual error about PyPI.**
  `docs/STATUS.md` said *"Published version: **0.2.2 only**"* while 0.3.0 had been on the index for
  three hours — and that row is a fact about PyPI, not about this repo, so nothing in the release
  procedure was ever going to notice. Verified against the index and by installing: 0.2.2 and 0.3.0
  are both published, all four extras (`st`, `light`, `pdf`, `claude`) resolve, `requires-python` is
  `>=3.13`, and `uv add "pinakes[light,pdf]"` into an empty venv gives `pinakes 0.3.0`.

  The others were the release's own shadow:

  - The **naming table** still listed *the paid-extraction release* among "bodies of work that do
    not exist yet". It shipped as 0.3.0. The **roadmap** still had it italicised and unticked,
    directly under three ticked rows.
  - **`README.md`'s install block** offered only `[st]` and `[light]`, so a new reader could not
    discover PDF ingest — the headline capability of the two most recent releases — from the
    quickstart at all.
  - **`README.md` claimed a capability that is not built.** *"Cross-KB answers are capped by how
    well your KBs are linked"* implies cross-KB answers exist; the addressing ships, the traversal
    is the links release. Now says so, and points at the roadmap.
  - **`docs/README.md`** still described `MEASUREMENT-RUN.md` as *"how do I get the numbers this
    project admits it lacks"* and routed to it *"while the numbers are still missing"*. The run
    happened on 20260729 and `STATUS.md` carries its results.
  - **`KB-UPDATES.md`** said *"no increment assigned"* in three places; its `requires_pinakes` half
    is now assigned to G4 in `plans/links-and-graph.md`.

  **`CLAUDE.md` gains the rule**, because the release procedure is where this is preventable: a
  release makes three documents stale the instant it publishes — STATUS's PyPI table, STATUS's
  roadmap, and README's install lines — and they are swept in the release commit, verified by
  querying the index and installing what the docs show rather than by reading them.

- **`pinakes_get` on a PDF crashed with an unhandled traceback.** It read the source file with
  `read_text(encoding="utf-8")`, which raises `UnicodeDecodeError` — a `ValueError`, so the
  surrounding `except OSError` never caught it. PDFs are now served as their extracted text, and the
  decode failure has an explicit branch for the case a binary source is somehow recorded with no
  extraction backend.
- **The `stale_extraction` marker reached neither surface.** It was computed in `search.py` and
  dropped by both the CLI and the MCP renderer. The plan's own amendment row said I8 would take it
  "to the agent surface and not only the CLI", which understated the gap by half. Both surfaces now
  carry it — marked, never withheld.
- **The shipped `notes` template told every new KB that "no shipped code path spends money"**, which
  stopped being true when 0.3.0 shipped the paid extractor. The `[budget]` comment now says what the
  caps are for and that they bind only once you opt in.
- **`docs/GUIDE.md` said the paid extractor was "built but in no release yet"** — also untrue since
  0.3.0 — and still listed `path:page` citations as missing.

- **Five `pnk doctor` checks had no test at all** — `template`, `reranker`, `model cache`,
  `extensions` and `links`. Found by the coverage test above on the first run it did.
- **Three `⏳ pending amendment` notes in `docs/DESIGN.md` §9 still said work was unbuilt** that
  shipped in 0.3.0: the ledger fields and the price-staleness WARN (I6b), the cap arithmetic over a
  running total (I6a/I6b), and the measured free-vs-paid delta, which had been sitting in the row
  above them since the 20260729 measurement run.
- **`README.md` named neither PDF extra.** `pinakes[pdf]` and `pinakes[claude]` now appear in the
  quickstart, with the paid one's cost stated plainly and **all three** `[budget]` caps named —
  raising one and hitting the next is the discovery path those caps exist to prevent. `make budget`
  joined the Development target list.

## [0.3.0] — 20260729 04:17

### Added

- **Two agents can no longer quietly overwrite each other's shared-document edits.** Several agents
  work in this repo at once, and the collision has two shapes — only one of which anybody notices.
  `git merge` conflicting is the loud one. The quiet one is `git merge` **succeeding** because the
  two edits landed on different lines: git merges edits that do not overlap textually, never edits
  that agree, so two agents can state contradictory things in one file with every command reporting
  success. Both shapes were hit on 20260729, when three parallel branches edited `CHANGELOG.md`,
  `docs/STATUS.md` and `docs/DESIGN.md` inside one hour.

  Two complementary answers:

  - **`tools/fragments.py` removes the cause** for the two documents every change must write to. A
    change now adds `changelog.d/<category>-<slug>.md` or `retro.d/<slug>.md` instead of editing
    `CHANGELOG.md` or `docs/RETROSPECTIVES.md`, and the fragments are spliced in at release time by
    one actor with nothing else running. Two agents cannot conflict in separate files, so for these
    documents the conflict class stops existing rather than being managed. The category lives in the
    **filename**, where it cannot drift from the content. Existing `[Unreleased]` prose is left
    exactly where it is — adoption needs no migration commit, which would itself have collided.
  - **`tools/shared_file_overlap.py` reports what remains.** It names the files this branch touches
    that the default branch has touched too since they diverged, marking the high-contention ones.
    Generic, so it covers `docs/STATUS.md` and `docs/DESIGN.md`, which are living documents that
    fragments do not suit. Offline and advisory in `check.sh`; `--fetch --strict` is a gate before
    merging.

  Both are stdlib-only and import nothing from this project, so CI's `build` job runs them before
  the package builds.

- **[`plans/links-and-graph.md`](plans/links-and-graph.md) — the build order for the links release
  and the graph release, in fourteen increments (L1–L10, G1–G4).**
  `docs/graph/PINAKES_APPROACH.md` had settled *what* to build and *why* across five adversarial
  passes, but its build order (§10) was a single table row; nothing sequenced it, tested it, or
  named what it breaks. **Draft — pass 1 done, pass 2 required; do not implement from it yet.**

  Ten decisions were taken with the user. Four came from reading the code first, and three more
  from an adversarial review that found the first draft citing a gate that does not apply to the
  work it was gating:

  - **A second synthetic KB is committed, deliberately sparse.** `tests/demo-kb/` has thirty
    documents and **zero authored links** — every sidecar lacks a `links:` key, so the
    highest-trust edge class has no corpus behind it at all, single-KB as well as cross-KB. The
    density gate caps **degree as well as document count**, and counts forward-authored links only,
    because reverse-scan materialises the inbound side and counting both would double every
    corpus's apparent sparsity.
  - **The golden set grows to ~25 multi-hop questions**, and the new ones must be *harder*, not
    merely more numerous: repairing the scorer left `multi-hop` at **1.00 on five questions**, and a
    class at ceiling can only ever show damage.
  - **Two releases, not one.** A cut after the links surface would otherwise ship under a name that
    `CLAUDE.md` and `docs/STATUS.md` both define as including structural edges. Nothing in L1–L10
    bumps `schema_version`, so **the links release needs no rebuild**.
  - **`pnk link` writes forward only**, into the source document's sidecar; the reverse side is
    computed by reverse-scan, which DESIGN §6.2 has specified since v0.1 and nothing has ever
    implemented — `store.py` carries the `reverse-scan` origin value, unused.
  - **`pinakes_search`'s `entities`/`concepts` parameters are cut.** RRF here is unweighted by
    construction, so the feature needs a weighting change that touches every query plus its own
    eval, and it is orthogonal to links and edges.
  - **Retrieval ordering is made deterministic first** (L1). Three sources of run-to-run variance
    are live — an FTS `ORDER BY` with no secondary key, an unstable `argsort`, and a fusion
    truncation with no tiebreak — and the `schema_version` bump reassigns rowids immediately before
    the measurement the channel's gate depends on.
  - **The expansion channel's gate is given a threshold for the first time.** APPROACH §9 states
    none for `expand`; the "≥ 5 points" figure the first draft quoted belongs to the `ppr` row,
    which this plan excludes. The gate is now stated in **questions, not percentages** — ≥ 5 net,
    because under an exact sign test five discordant results in one direction is the smallest
    outcome with p < 0.05.

  PPR and the `[ner]` extra stay out. Neither release adds a paid entry point;
  `.paid-path-allowlist` is unchanged, though the free-path gate's *coverage* is extended per
  increment, since it enumerates surfaces by name.

- **Four Claude-vision fixtures are now recorded from the live API**, and every fixture declares its
  own `provenance` — `recorded` naming when, which model and what was sent, or `authored` naming
  why a recording is not obtainable. The blanket "hand-authored, not captured" disclaimer is gone,
  because a single claim over a mixed set is wrong about every fixture it does not describe
  ([the fixture README](tests/fixtures/claude/README.md), 20260729 03:36, €0.26).

  `tools/record_claude_fixtures.py` is what captured them. It spends real money and needs a real
  key, so it is a developer tool and never a product entry point: no `pnk` subcommand reaches it,
  no test imports it, CI never runs it, and it lives outside `src/` where the paid-path gate scans.
  Its `--at` flag is required and has no default — the timestamp is read off the clock, never
  composed.

  Ten fixtures stay authored **permanently**, not pending: they encode the API misbehaving (a body
  violating the schema it was constrained to, a short page array, a leaked internal tag) or a
  failure that cannot be induced without abusing a live service (429, 500, timeout).

- **The completeness audit, staging, and the all-or-nothing commit (I7c)** — three things that
  make a paid extraction trustworthy rather than merely possible.

  The **audit** computes `word_coverage` per page against pypdfium2's native layer and *reports*
  it. Report-only on purpose: the re-extraction loop it would drive needs a floor, and the pair
  that floor must be fitted against is (native layer → Claude output), which does not exist until
  the first real runs produce it. Pages with no usable native layer are **exempt and reported as
  exempt with their denominator** — scoring a scanned page zero would make the exact case the paid
  path exists for look like its worst failure. Outliers are named against the document's own
  median, so the measure needs no constant nobody has fitted.

  **Staging** writes each validated page under `cache/extract/partial/` as its slice completes, so
  an interrupted run does not re-pay for pages it already has. Resume granularity is the **slice**,
  never the page: its pages were transcribed together, and a page transcribed with different
  neighbours is a different extraction. The staging area is cleared only *after* the complete entry
  is written — the reverse loses every staged page to a crash in between.

  **All-or-nothing:** a partially extracted document writes no cache entry and lands in `failures`,
  while its staged pages survive for the next run. `on_exceed` is honoured at the **corpus** level
  — `partial` means "index fewer documents", never "index part of one", which would be the silent
  truncation §4.6 exists to prevent. It was parsed and validated since v0.1 and read by nothing
  until now.

- **Paid PDF extraction: the Claude-vision backend (I7b)** — `src/pinakes/extract/claude.py`, the
  first and only module on `.paid-path-allowlist`. Reached only when the manifest says
  `backend = "claude-vision"` or `pnk sync --extract=claude-vision` does, and **every free step
  runs before any paid one**: page count, encryption, the per-request size limit, the context
  window, and the free extractor's own text yield against I3b's fitted floor — a PDF whose text
  layer is already healthy is refused outright, because paying to re-read text you already have is
  the likeliest way to lose money by accident. `--force` overrides it; with no fitted floor
  installed it refuses to spend at all rather than proceeding without its guard.

  A request is a five-page slice, never a whole document and never a single page. **Two retry
  budgets, not one**: six token-billed calls per slice, and inside each of those two transport
  backoffs for 429/5xx — one shared counter would let two early 429s silently consume the
  schema-retry budget. The branch order is load-bearing: a refusal is handled before `content` is
  read at all, a context-window failure is hard with no retry, `max_tokens` is checked *before*
  schema validation (a truncated body is invalid JSON and would otherwise be retried identically
  three times, all paid), and then the page-count assertion that refuses to map a four-page
  response onto a five-page slice — the failure that would shift every citation in a document with
  nothing downstream able to see it.

  Failures are classified by whether they **billed**, never by HTTP status: 429, 5xx, 4xx and
  pre-response connection errors void their reservation; a timeout or a mid-response failure leaves
  it open as `unknown outcome`, because the server may have generated. Every call — including every
  retry — takes its own reservation and writes its own ledger pair.

  Driven end to end by `tests/fixtures/claude/`, **with `anthropic` not installed**, which is what
  proves the registry seam rather than asserting it. Those fixtures are hand-authored to the
  documented response shape, not captured from a live API, and their README says so.

- **`pnk sync --estimate-only`** — prices what a paid run would cost and exits, extracting nothing.
  **A network call, not an offline estimate**: it measures the real first-slice request with the
  vendor's own token counter, so it needs a key. It generates nothing and bills no output, and it
  refuses on a free backend rather than reporting €0.00.

- **Budget I/O: the ledger, `pnk budget`, and hooks that cannot spend (I6b)** —
  `.pinakes/ledger.jsonl` is append-only, one atomic sub-4KB `O_APPEND` write per record, fsynced.
  Three record kinds keyed by `call_id`: a **reservation** written *before* the call, then exactly
  one **reconciliation** or **void**. A void closes a reservation at zero and is written **only
  when no response was received** — never from a bare `finally`, which cannot tell "the call never
  happened" from "the call returned and then something else raised", and in the second case would
  record €0 for money that left the account, permanently, in a file nothing can edit. A reservation
  with neither successor is reported as `unknown outcome`, never dropped and never counted as zero.

  Every line carries `cost_usd`, the `usd_per_eur` rate and the price table's `as_of`; EUR is
  computed at read time. Two identifiers, `operation_id` and `call_id`, because one word for both
  made `per_operation_eur` ambiguous by a factor of forty. **No query text and no document
  content** — asserted by running a sentinel through the call protocol and grepping the whole file.

  `pnk budget` shows day and month spend against their caps with the rate behind each total (and
  says so when a window spans two), the reconciled/voided/unknown counts, and the exact
  `pnk budget --resolve <call_id> --actual <eur>` line that closes a timeout — an **append**, never
  an edit. `pnk doctor` gains a price-table age check and an unknown-outcome check that warns past
  a quarter of a window. `make budget` wraps the command.

  I6a's pure arithmetic is now wired to a real ledger by `budget/accountant.py`, and the wiring is
  tested rather than assumed: a KB holding €4.99 of a €5.00 month refuses the next call with an
  untouched per-operation cap. **Nothing calls any of it yet** — the paid extractor is I7b.

- **`pnk init --ci`** — writes `.github/workflows/pinakes.yml`, designed in DESIGN §6.3 and never
  built in v0.1. It refuses to overwrite an existing workflow, the same trust rule `install-hooks`
  applies to a foreign git hook.

- **The paid-path allowlist gate (I7a)** — `.paid-path-allowlist` names every module under `src/`
  permitted to import a paid-API client, and `check.sh`, CI and `tests/test_paid_path.py` all read
  that one file, so three copies cannot drift. It ships **empty**: the gate lands before
  `src/pinakes/extract/claude.py` exists, because a gate arriving in the same increment as the thing
  it guards has never once refused that thing — v0.1 promised this check under a heading with no
  increment number, so nobody owned it and it never shipped.

  Four gates: every listed path exists and lives under `src/`; no paid-client import outside the
  list; `anthropic` never in `[project.dependencies]`; and the one that matters — a **full free-path
  run** (`init`, `sync`, `search`, `doctor`, an MCP handshake, over a free KB *and* a
  `claude-vision`-configured one) in a fresh subprocess, asserting no paid client reached
  `sys.modules`. Each gate has a test that makes it *fail*, including the path-exclusion trap an
  entry of `claude.py` implemented as a prefix match would open. The runtime gate skips with a
  printed reason where `pinakes[claude]` is absent — with the package missing, the assertion is true
  by construction and proves nothing — and runs for real on CI's `[light,pdf,claude]` leg.

  This replaces the unconditional `grep` that lived only in CI's `build` job. Unconditional admits
  no exceptions, so it would have turned `main` red on every commit from I7b onward.

### Changed

- **[`plans/links-and-graph.md`](plans/links-and-graph.md) rewritten after a second adversarial
  pass — six of the first pass's own fixes were wrong.** Two reviewers returned 26 HIGH, 30 MEDIUM
  and 8 LOW against the revision that pass 1 produced, roughly the 40–45% fix-induced rate
  `plans/v0.2.md`'s iteration log predicts. Still a draft; a third pass is required before any of it
  is built.

  What was wrong, and now is not:

  - **The determinism increment chose the rowid as its rebuild-stable sort key**, while `store.py`
    says two lines above the table that *"a chunk has no identity across rebuilds"*. It also framed
    the hazard as run-to-run variance, which does not exist — all three named sites are
    deterministic for a fixed index, which is why `make eval` was already byte-identical three runs
    running. The key is now `(doc_id, ordinal)`, the hazard is cross-build and cross-machine, and a
    fourth site (`_hydrate`, which has no `ORDER BY`) joins the three.
  - **A cross-KB neighbour had no way to be identified at all.** The tool contract returns `title`,
    which lives only in the local index; the fix added a title-from-sidecars mechanism and missed
    that the neighbour carried no KB identifier either, so an agent could neither fetch it nor name
    where it lived. Neighbours now carry `kb` and, for cross-KB, no `title` — which also drops a
    per-query filesystem walk of another KB that DESIGN §6.2 sanctions only at sync time.
  - **The eval gate cited a statistic the sign test does not measure.** "≥ 5 questions **net**" was
    justified with 0.5⁵ = 0.031, but the sign test counts *discordant* questions: 8 improved / 3
    regressed is also net +5 and gives p = 0.113. The gate admitted results up to eight times the
    claimed p while rejecting 4/0 at p = 0.063. It is now the exact test itself, tabulated.
  - **The gate was also unreachable.** It can only read single-KB questions, and the golden set had
    been sized "most cross-KB" — leaving ≤ 7 improvable against a 5-question threshold. The class is
    now majority single-KB, cross-KB questions get their own `kind` so `compare()` gates them
    separately, and a headroom check must pass **before** `schema_version` bumps rather than being
    reported after every KB has already been forced to rebuild.
  - **A rule invented for cross-KB scoring would have rescored the 41 questions its own exit
    criterion promised to leave untouched** — all five committed multi-hop questions are hopped. It
    was also redundant: `eval.py` has required every hop to land since the scorer was repaired. A
    cross-KB question is simply a hopped question whose later hop lands in the other KB.
  - **Banning docs-sweep increments left the docs with no owner at all** — the plan contained zero
    occurrences of `GUIDE`, `CLI.md` or `--help`, while `docs/CLI.md` and `docs/STATUS.md` both
    carry rows this work falsifies. Every increment now names its doc homes, and both releases
    regained a run-it-don't-reason-about-it verification section.

  Three decisions were taken with the user in response: cross-KB neighbours carry no title; the
  multi-hop class is majority single-KB; and G1's edge weights are **frozen** at the research
  document's priors rather than fitted against the golden set that then gates them — `calibrate.py`
  already records that circularity for the confidence thresholds and calls the result optimistic.

- **pinakes is on PyPI, and every install line in the docs now says so.** `PUBLISH_TO_PYPI` was set
  `true` at 20260728 17:15 UTC and **0.2.2 uploaded 108 seconds later** — the first and, so far,
  only published version: 0.2.0 and 0.2.1 predate publishing and cannot be installed by pin.

  Verified rather than assumed, per the repo's own rule that docs are checked by running what they
  show: `pinakes[light]` was installed from the published wheel into an empty venv and driven
  through `init` → `sync` → `search` (20260729 01:01). All four extras (`st`, `light`, `pdf`,
  `claude`) resolve from the index, and `requires-python` is `>=3.13`.

  Every `git+https://…` install line becomes `uv add "pinakes[st]"`; the MCP `uvx` example loses its
  git URL; the README gains a PyPI version badge; and `docs/STATUS.md`'s *Not published yet* section
  is now *Published on PyPI*, carrying the published-version caveat. One git install line is kept on
  purpose, relabelled — it is how a contributor installs unreleased work sitting on `main`.

  **`CLAUDE.md` gains the consequence, because it changes how releases must be done:** a tag is no
  longer a safe rehearsal. It publishes, and PyPI does not allow re-uploading a version, so
  `make release-check` runs *before* pushing a tag rather than after.
- **🚫 Unbuilt work is named, never numbered — a project-wide convention, and a rule other agents
  will meet in `CLAUDE.md`.** A version number now belongs to a release only when it is cut. Unbuilt
  bodies of work are **the paid-extraction release**, **the links release**, **the graph release**,
  **the deep release** and **the template release**; increment IDs (`I7b`, `I8`) are unaffected,
  since they name work inside a written plan rather than a release.

  **The links release was split out of the graph release on 20260729**, while sequencing
  [`plans/links-and-graph.md`](plans/links-and-graph.md): `pnk link`, `pnk links`, `pinakes_links`
  and reverse-scan need no `schema_version` bump and no rebuild, while structural edges and the
  expansion channel need both. Shipping the first half under a name defined as including the second
  would have reintroduced exactly the ambiguity this convention exists to end — one name meaning two
  releases — three days after it was adopted. The naming tables in `CLAUDE.md` and `docs/STATUS.md`
  carry both rows, and `docs/graph/PINAKES_APPROACH.md` keeps its single-release §10 with a header
  note, since it is dated research rather than a live specification.

  **Why now.** `docs/` and `docs/graph/` had used `v0.3` for months to mean the cross-KB links
  release. Once 0.2.2 shipped, the *next* MINOR was numerically 0.3.0 — so one number meant two
  different releases, and resolving it either way meant renumbering ~60 committed references,
  research records included. `docs/STATUS.md` had flagged this as blocking the next release. A name
  cannot collide, never needs renumbering, and says what the work *is* rather than when it arrives.

  Applied across every live surface — `docs/STATUS.md` (which carries the rule and the mapping),
  `DESIGN.md` §8, `CLI.md`, `MANIFEST.md`, `GUIDE.md`, `KB-UPDATES.md`, `docs/README.md`,
  `docs/graph/README.md` and `PINAKES_APPROACH.md` — and, because a convention that stops at the
  docs is not a convention, in **user-facing output** too: `pnk search`'s escalation note now reads
  "planned for the deep release", and four `pnk doctor` messages name the template and graph
  releases instead of `v0.5`/`v0.3` (`tests/test_cli_search.py` updated with them). Internal
  docstrings in `manifest.py` and `sidecar.py` follow.

  **Historical records keep their numbers.** `CHANGELOG.md`, `docs/RETROSPECTIVES.md`, `plans/` and
  the dated research in `docs/graph/` are records of what was decided at a time; rewriting them would
  falsify that. Each now opens with a one-line note saying the numbering convention has changed and
  pointing at `docs/STATUS.md`.

- **`PROMPT_TOKENS` was measured and was wrong in the unsafe direction** — 571 against an estimated
  300, so the one term of the "worst case" that no page count compensates for was understating
  itself by 1.9×. Now 700. `PAGE_TOKEN_CEILING` was measured too (~1,574/page against a 6,000
  ceiling) and **deliberately left alone**: the corpus rasters are synthetic, and a real 300-DPI
  scan is exactly the case they cannot represent.

- **The paid extractor is measured against the live API** (20260729, `claude-opus-5`, €0.43). On
  the scanned stratum it scores 1.000 char recall, order fidelity and word coverage with 0.000
  junk, where the free path scores 0.000 on all four — the first evidence that the feature does
  what it exists for. DESIGN gains a new §7.2 for the free-vs-paid delta: identical on three of
  four text-layer twins, and on a bordered table the paid path reads order better (+0.119) while
  adding 29% junk. Neither path is simply better, and a caller who cares about tables should be
  told rather than left to infer it.

- **`pnk sync --clear-cache` prices what it is about to destroy**, in euros, joined from the
  ledger on each entry's own `call_ids` — not its `operation_id`, which prices a whole *run* and
  would attribute every document's spend to each of them. A count answers "how many"; only the
  euros answer "is this worth re-paying for".

- **`--force`'s scope is stated in full, in `--help`.** It overrules exactly two refusals — paying
  for a PDF whose free text layer is already healthy, and (only with an explicit free `--extract`)
  overwriting a paid extraction. It never widens a budget cap, the stale-price refusal, the
  missing-floor refusal, or the no-terminal abort.

- **The extraction cache records the `operation_id` and `call_ids` behind a paid entry** — the join
  key back to `ledger.jsonl` that DESIGN §6.3 promised and left `null` until something could
  populate it. Consequently `pnk sync --yes --clear-cache` now refuses a cache holding paid entries
  and names `--clear-cache=paid`: I6b's guard was correct from the day it landed and had no real
  data to fire on until now.

- **All four machine-driven callers force the free extractor.** The three git hooks and
  `pnk init --ci`'s workflow now write `pnk sync --extract=pypdfium2` explicitly, print one line
  saying so, and carry the same line as a comment in what they generate. All four are
  non-interactive: without the flag, a KB configured for a paid backend would abort on every commit
  for want of a terminal to confirm from; with a `--yes` in the hook it would spend afresh on every
  commit. The test **executes** each hook against a `claude-vision` KB and asserts the free backend
  extracted and no ledger was written, with a control that strips the flag and shows the same hook
  failing — asserting the string is *present* passes on a hook that never runs.

- **`--yes` no longer authorises destroying paid cache entries.** `pnk sync --yes --clear-cache` in
  a cron job could have thrown away paid extractions unattended, which is exactly what that
  guarantee claims to forbid. Clearing a cache holding paid entries non-interactively now requires
  `--clear-cache=paid` as well, which no hook and no generated workflow writes. `--yes`'s `--help`
  now states what it authorises: this run's prompts, no cap raised.

- **CLAUDE.md's paid-path invariant is now an enumerated allowlist**, rather than "no paid API call
  outside `pnk ask --deep`", matching DESIGN §1 and `.paid-path-allowlist`. DESIGN §1's prose covers
  paid LLM *work* (reasoning **and** PDF extraction), its decisions table no longer reads "Claude for
  reasoning only", §8's v0.2 row states both extraction paths, and §9 gains four risk rows:
  allowlist erosion, unbounded spend across invocations, price-table staleness, and the scanned-page
  audit blind spot.
- `pytest` runs with `-rs` in `check.sh` and CI, so a skipped gate prints its reason instead of
  reading as a pass.
- `pyright` now type-checks `tools/` alongside `src/` and `tests/`.
- Gate 4's runtime check matches paid modules on a dotted-prefix boundary against
  `google.generativeai` in full, not on the bare root `google` — which would have made
  `google.protobuf` (transitive via onnxruntime and grpc) a paid client and failed the flagship
  safety gate for an unrelated reason on some future CI leg.

### Fixed

- **A refusal discarded the reason the API gave for it.** A refusal arrives with a structured
  `stop_details` naming a `category` and an `explanation`; the extractor recorded the bare sentence
  "the model refused the request", leaving an operator unable to tell a policy category from a
  malformed PDF. `refusal_reason` now surfaces both, defensively — details missing or the wrong
  shape still degrade to the plain sentence, because this runs on the failure path where a raise
  would turn one refused document into a crashed run.

  Found only by recording: the authored fixture had no `stop_details` at all, so nothing in the
  test suite could have pointed at it. Recording also settled that the authored bodies were right
  about every branch's control flow and wrong about the response shape in five ways — the API
  returns the model **alias** rather than a dated snapshot, a text block carries `citations`, a
  response carries five more top-level fields, `usage` carries seven more, and a refusal bills
  **1** output token rather than 0.

- **A reconciliation test asserted a property of its fixture rather than of the code.** It compared
  the reconciled input-token count against the literal `30_300` — the authored body's number — so
  recording a real response broke it while the code under test was correct. It now reads the count
  from the fixture and requires it to differ from the pre-call estimate, which is what actually
  proves the reconciliation read the response.

- **The multi-hop class measured nothing about hopping, and two of its five questions asked about
  one document while demanding another.** `Outcome.hops_followed` was computed for every scripted
  question and read by no metric — not `recall_at_k`, not `by_kind`, nothing CI compares. Deleting
  the hop loop outright left `by_kind["multi-hop"]` bit-identical, which is the definition of a
  vacuous metric ([DESIGN §7](docs/DESIGN.md#7-quality)). A multi-hop question was in effect a
  single-shot search of its last hop's query.

  That hid a second defect in the golden set itself. Three questions named their *last* hop's
  document in `expect`; two named their *first*, so the scorer ran a query about brittle-paper
  conservation and demanded the annual report. Nothing caught the disagreement, because `hops` fed
  no metric that could notice.

  A hit now requires **every** hop to land its own document by its own query, and `expect` is
  exactly the union of the hops' documents — asserted for the committed set, so the two
  inconsistent questions cannot come back.

  **The numbers moved because the scorer was wrong, not because retrieval changed** (no retrieval
  code was touched): recall@5 0.8788 → 0.9091, MRR 0.7737 → 0.8116, rerank precision 0.7273 →
  0.7576, `by_kind["multi-hop"]` 0.80 → 1.00. Stricter scoring, higher score — because the two
  inverted questions had been asked about the wrong document all along. `false_abstain` (0.0303),
  `false_confidence` (0.25) and `confidence_coverage` (1.0) are unchanged. Baseline re-cut
  20260729 03:23, `[light]` models, three identical consecutive runs.

  Two gaps in the comparator closed alongside it, both of which let a real regression pass green:
  `compare()` wrote `by_kind` into every baseline and **never read it back**, so a change lifting
  one class and dropping another by the same amount moved the aggregate by almost nothing; and the
  question count was written and never compared, so a golden set that silently lost its hard
  questions would have scored *better*.

- **`HashingBackend`, the "cheap deterministic embedder" the eval tests rank with, was not
  deterministic.** It hashed each word with `hash()`, which Python randomises per process for `str`
  unless `PYTHONHASHSEED` is set — and nothing sets it, nor can a `conftest.py`, since the value is
  read before the interpreter starts. Which words collided in the 64-dimensional space therefore
  changed from run to run. Measured before the fix: **one failure in 40 runs**; after switching to
  `zlib.crc32`, **zero in 60**. A fake that cannot reproduce itself cannot tell a real regression
  from its own noise.

- **Five docs still called the paid extractor a stub, or unbuilt, after I7b built it.**
  `docs/STATUS.md` contradicted itself within eight lines — one row correctly read "`claude-vision`
  is a real extractor", while the paragraph below still explained that nothing can spend money
  *because it is a stub*. `extract/claude.py` is 945 lines of working adapter.

  The conclusion was right and the reason was wrong, which is the more dangerous shape: nothing in a
  **released** build can spend, but that is now because I7b is unreleased, not because the code is
  absent. The distinction matters to anyone installing from `main` — there, a KB configured for
  `claude-vision` can bill a real key. Each claim now says "built, but in no release yet" and
  `STATUS.md` spells out that PyPI and `main` differ on exactly this point.

  Also corrected in `docs/GUIDE.md` (the `[claude]` extra, the scanned-PDF row, and the
  troubleshooting entry) and `docs/MANIFEST.md`'s `[extraction] backend`. `docs/CLI.md` needed no
  change — it had already moved `pnk budget`, `--estimate-only` and `--clear-cache=paid` out of its
  Planned table.

- **The budget accountant handed out a `PaidCall` instead of a context manager (I6b review).** That
  put the void-vs-unknown decision and the closing write back in the caller's hands — undoing the
  one guarantee `budget/ledger.py` exists to enforce, for the caller it was written for (I7b's
  retry loop).

- **A ledger line with a `usd_per_eur` of `0` crashed `pnk budget`.** Every euro figure is a
  division computed lazily, so the `DivisionByZero` escaped the malformed-line counting whose whole
  purpose is that one bad line cannot take the report down. Rates are validated positive at parse
  time.

- **The first reservation a KB ever wrote was not durable.** `fsync` on the file does not make its
  *directory entry* durable, so a crash could lose it entirely while every later record survived.

- **`pnk doctor` was blind to hooks inside a git worktree**, where `.git` is a file pointing
  elsewhere: both hook checks read `root/.git/hooks` directly rather than through
  `hooks.hooks_dir`, which has resolved that since v0.1. It reported "0 of 3 installed" on a KB
  whose hooks were installed and running.

- **`pnk budget` printed its windows in `[budget] timezone` and its operation list in the machine's
  local zone**, and `pnk doctor` printed a raw 28-digit `Decimal` division as a euro amount.

- **The paid extraction fingerprint omitted the model (I7b review)** — so changing
  `[extraction] model` hit a cache entry a *different* model had written, with no miss and no
  stale marker. The registry's fingerprint contract now carries the configured model; free
  backends ignore it, so no existing index goes stale.

- **A paid call's reconciliation recorded the reserved amount rather than what it cost (I7b
  review)** — the protocol's shape was right and its content was the estimate again, so every
  budget window would have charged worst-case forever with a reconciliation record present to make
  it look settled.

- **A transport failure would have crashed a whole sync.** `TransportError` and
  `RequestTooLargeError` sat outside `PinakesError`, so an exhausted 429 or an oversized page
  escaped the per-document isolation that keeps one broken PDF from blocking a corpus.

- **`pnk init --ci` explained the git hooks instead of the workflow it had just written** — one
  shared notice with a subject baked into it, printed by two callers.

- **`pnk budget` truncated its operation list silently**, and `--clear-cache`'s bare form parsed to
  a value named `free` — which reads as "clear only the free entries" when both spellings clear the
  whole cache. The list now says how many it is not showing, and the bare form is `all`.

- **`pnk doctor` and `pnk sync` imported the paid API client on a KB configured for
  `claude-vision`.** Both reported a backend's availability by *loading* it —
  `doctor._extraction` on every run, and `sync._missing_pdf_extra` when building the "matched no
  `include` pattern" hint for a skipped `.pdf` — and the registry's factory imports the client. Two
  commands that cannot spend therefore pulled `anthropic` into a free-path process.

  Found by the new gate rather than by reading, and each confirmed by mutation: restoring either one
  alone puts `anthropic` back in `sys.modules`. Availability now resolves through
  `importlib.util.find_spec` against a `(module, extra)` pair declared on the registry entry, which
  for a top-level module adds nothing to `sys.modules`. No released version could spend from either
  path — `claude-vision` is a stub — so the effect was a needless import, never a charge.

## [0.2.2] — 20260728 18:49

### Fixed

- **A file that matched no `include` pattern was skipped in silence — including, in a KB made by
  `pnk init`, every PDF.** 0.2.0 shipped free PDF ingest as its headline feature while the `notes`
  template stamped `include = ["**/*.md", "**/*.txt"]`, so the actual first-run experience was:
  drop in a PDF, run `pnk sync`, read `0 indexed`, and get no hint that a missing glob was the
  reason. The mixed case was worse — Markdown indexed, PDFs dropped, the run reporting success —
  because nothing prompted anyone to look.

  `pnk sync` now names what it skipped, grouped by extension, with the exact glob that would pick
  the commonest up and a pointer to `exclude` for silencing it instead:

  ```text
  0 indexed, 0 renamed, 0 metadata-only, 0 unchanged, 0 removed
  1 file(s) matched no `include` pattern: .pdf (1) — add "**/*.pdf" to `[sources] include` to index them, or `exclude` them to silence this.
  ```

  **Only files pinakes could actually index are reported**, and the test is the one indexing itself
  applies: whether the first 8 KB decode as UTF-8 (`_index_document` reads every non-PDF source with
  `read_text(encoding="utf-8")`), plus `.pdf`, binary on purpose and indexable through
  `pinakes[pdf]`. An image or an archive beside your notes never appears — suggesting a glob for one
  would hand back a remedy that produces a `UnicodeDecodeError` failure row when followed, and a
  wrong hint is worse than none. Deciding by decodability rather than an extension allowlist also
  covers `.rst`, `.org`, `.tex` and every other text format without a list anyone has to maintain,
  since `chunk.source_type` already falls back to `"text"` for an unknown suffix. Silent too,
  deliberately: anything `exclude` already names, sidecars, and anything under a dotted path segment
  (`.git/`, `.DS_Store`).

- **The `notes` template now spells out the PDF glob and the extra it needs** (plan decision 6,
  pulled forward from I9 — the defect was live in a released version, and the plan had already
  reversed itself on the same reasoning for I7a's allowlist gate). PDFs stay **off** by default:
  `init` cannot see whether `pinakes[pdf]` is installed, and a glob stamped without it turns every
  PDF into a *failed* document rather than a skipped one. Off, but no longer undiscoverable.

  An independent adversarial review caught two defects that each handed the silence straight back,
  plus five smaller ones — all fixed here:

  - **The probe read a fixed 8 KB prefix and decoded it in one go**, so a multi-byte character
    straddling the boundary raised `UnicodeDecodeError` on a perfectly valid document — about two
    times in three for CJK, Cyrillic or Greek prose. A non-English corpus therefore got exactly the
    pre-fix behaviour: PDF beside the notes, `0 indexed`, no explanation. Now decoded incrementally,
    which holds a partial trailing character instead of failing on it.
  - **With more than one `[sources] root`, matched and unmatched were not disjoint.** The unmatched
    pass ran inside the per-root loop, testing each file against a matched-set the later roots had
    not contributed to yet — so a document indexed via root B was *also* reported as having no
    pattern, and swapping the two roots in the manifest made it disappear. Now a second pass, after
    every root's include walk.
  - `pnk sync --quiet` never printed the line, and the git hooks `docs/GUIDE.md` recommends run
    exactly that — leaving the project's own documented workflow as the one place the fix could not
    reach. `-q` prints only problems, and this is one; it now goes to stderr.
  - The suggested glob was lowercased, so `Report.PDF` was told to add `"**/*.pdf"` — which
    `pathlib` glob, case-sensitive on POSIX whatever the filesystem does, will not match. Suffixes
    are now grouped as they appear on disk.
  - An unmatched `.pdf` now names `pinakes[pdf]` when the extractor is genuinely not importable:
    adding the glob alone on a core-only install turns a skipped file into a *failed* one, the same
    trap the binary exclusion exists to avoid.
  - Probing is capped per root (`MAX_PROBED_PER_ROOT`), because a `node_modules/` under a root is
    thousands of `open()` calls per sync — a network round trip each on an SMB or NFS mount — to
    produce advice nobody wants. Truncation is stated (`500+ file(s)`), never silent.
  - A symlinked source root resolving outside the KB raised an uncaught `ValueError` out of the
    walk; ties in the extension ranking no longer let `(no extension)` take the hint slot from a
    real suffix; and "and N more" now says "extension(s)", since it counts extensions while the
    number beside it counts files.

  Tests: 22 cases across `tests/test_sync.py` and `tests/test_init.py`, each confirmed to fail
  against the code before its fix by mutating the source and watching the right one break. One of
  them — the PDF-extra hint — was first written as a self-consistency check that agreed with itself
  under every extras leg and survived deleting the feature; it now forces the extractor missing.

### Changed

- **The per-increment workflow now requires mutating the source to prove the tests can detect a
  defect**, not merely that they pass (`CLAUDE.md`). Two consecutive increments produced the same
  class of finding: I5 tested paid-extraction protection down one of the four code paths that reach
  the decision, and I6a's timezone conversion — the entire reason `window.py` exists — passed all 35
  tests with the conversion deleted, because every fixture was constructed in the zone being
  converted to. Tests written by the reasoning that wrote the code inherit its blind spots, so the
  cheap counter is to break the guard, watch the right test fail, and restore.

### Added

- **I6a of the v0.2 build order: budget core, pure (rule 11 — the pure half of the money
  machinery).** `src/pinakes/budget/` — no I/O, no `anthropic` import, asserted by an AST-based
  import-graph test over every file in the package. This is the accountant and the estimator;
  reading `ledger.jsonl`, `pnk budget`, and actually spending are I6b's job.

  **`prices.toml` ships as package data**, exactly like `extract/floors.toml` (verified: it is
  present inside a real built wheel, not only this source checkout). Every price is a TOML
  *string*, not a bare number — `prices.toml` is entirely project-controlled, never
  user-authored, so parsing via `Decimal(the_string)` directly removes the float intermediary
  altogether rather than reconstructing it from `str(float(...))` the way a user-authored manifest
  number has to. Seeded: `claude-opus-5` at $5.00 / $25.00 per MTok, `usd_per_eur = 1.08`, both
  carrying the same `as_of`. `prices.py` mirrors `floors.py`'s `load_floors()` shape precisely,
  including a new `PricesMissingError` for a missing/unreadable/malformed file and
  `UnknownModelPriceError` naming the models a document's own manifest could actually ask for.

  **`estimate.py` estimates over *requests*, never a whole document and never a single page**
  (decision 8): worst case per request = `(K * page_tokens + prompt_tokens) * input_price +
  max_tokens * output_price`, and a document is `ceil(pages / K)` requests. `K = 5` is a semantic
  constant (hashed into the paid extractor's own request-shape version in I7b, not a tuning knob).
  `page_tokens` is a conservative ceiling of 6,000 until I7b measures the real figure;
  `prompt_tokens = 300` and `max_tokens = 8,000` are measured module constants, not afterthoughts a
  real worst case could omit. No cache-write multiplier: the shared prefix is a few hundred tokens
  against the model's own cache minimum, so it very likely cannot be cached at all. A context-window
  precheck (1,000,000 tokens on `claude-opus-5`) runs before the estimate is even produced — cheap,
  and under the shipped constants (30,300 tokens per request) it never fires, but it names the exact
  limit rather than letting a real 400 response discover it. A stale `as_of` (older than
  `[budget] max_price_age_days`) refuses to estimate at all, naming the remedy. Verified directly
  against `plans/v0.2.md`'s own worked examples: 200 pages resolves to exactly 40 requests and
  $14.06 reserved; a single 5-page slice resolves to exactly $0.3515 — both to the last digit the
  plan states.

  **`reserve.py` is the pure accountant.** `reserve(reserved_eur, caps, spent) -> Decision` checks
  one call's cost against all three ceilings — `per_operation_eur`, the new `daily_eur`, and
  `monthly_eur` — in order, and refuses before any call is made if `spent.window + reserved` would
  exceed any of them; the refusal names which window and by how much. `reserve_document(estimate,
  caps, spent, confirm_above_eur=...) -> DocumentDecision` is the whole-document precheck run
  before the first call: unlike `reserve`, it names *every* blocked window at once, prints the
  computed estimate, the complete `[budget]` manifest edit that would admit this run (each blocked
  cap's minimum sufficient value, rounded up to the cent), and one line stating that raising a cap
  is a permanent, ongoing exposure — a one-run `--extract=<backend>` override is not.
  `confirm_above_eur` is evaluated once, against the whole-document estimate, never per slice: a
  20-page document whose *per-request* cost sits below the threshold but whose *document total*
  clears it is still flagged, exactly as the design says. All display amounts (never the internal
  comparisons, which stay full-precision `Decimal` throughout) are rounded to the cent for a human
  to actually read — an early version printed
  `€0.3254629629629629629629629630`, fixed before this was ever exercised by a test.

  **`window.py` aggregates ledger records into day/month totals**, in `[budget] timezone` — reading
  the ledger file itself is I6b's job, so this only ever takes an in-memory list. The
  reservation/reconciliation/void rule a draft of this design never stated, now pinned down and
  tested: a pair is one record, attributed to the *reservation's* own timestamp (never the
  outcome's); a reconciliation supersedes the reservation's amount in place, never adding to it; an
  unreconciled reservation counts at its reserved amount, so an in-flight or crashed call consumes
  headroom rather than vanishing; a void (I7b) closes a reservation at zero. Verified directly
  against a genuine midnight-straddling pair, a month-end-straddling pair, and a real DST
  spring-forward transition (`Europe/Berlin`, 2026-03-29) — all three attributed correctly. The
  `operation` window total is supplied by the caller (its own running tally for the current
  invocation), never aggregated from the historical ledger — a call from an *earlier* operation
  today must not bleed into a fresh one's own count.

  **`manifest.py`'s `[budget]` block moves from `float` to `Decimal` end to end** — a reservation
  compared against a float-derived cap is a representation error wearing a different hat, and the
  boundary tests this increment adds assert exact equality at the cent. `_toml.py` gains
  `Table.decimal()`, parsing a TOML number via `Decimal(str(the_parsed_float))`, never
  `Decimal(the_parsed_float)` directly — verified empirically that the latter reproduces the exact
  binary value a literal like `0.05` only approximates
  (`Decimal("0.05000000000000000277555756156289135105907917022705078125")`), not the clean decimal
  a human wrote. `[budget]` gains `daily_eur` (default 1.00 — a burst limiter between the
  per-operation and monthly caps) and `max_price_age_days` (default 30).

  **`check.sh` gains a `prices-toml-parses` gate**: `as_of` must exist and parse as
  `YYYYMMDD HH:MM`, failing the build if not. Deliberately *not* a staleness gate — a wall-clock
  check would fail a quiet weekend with no code change at all; staleness itself is a runtime
  refusal (`estimate_document`, above) and belongs to `pnk doctor` as a WARN, not to CI.

  **Tests, `tests/test_budget_core.py`** (35 cases): the exact boundary for each of the three
  windows (`spent + reserved == cap` proceeds, one cent more refuses, parametrised over all three);
  a case where the operation cap passes but the month's does not; `test_reservation_bounds_every_
  usage_table` (hand-written hypothetical usages, the worst-case reservation never below any of
  them); the midnight/month-end/DST attribution trio; reservation/reconciliation/void semantics;
  `test_the_refusal_names_all_three_windows`; `test_an_unaffordable_document_is_refused_before_
  the_first_call` (a spy asserting zero calls made); `test_confirmation_is_once_per_document_not_
  per_slice`; `test_confirm_threshold_and_hard_cap_are_independent_boundaries` (a request landing
  exactly at the hard cap is still allowed *and* still confirmable — design pass 3's finding);
  a stale `as_of`, a missing `prices.toml`, a malformed one, and one missing a required field, each
  a named startup error rather than a silent zero; `test_the_context_window_precheck_names_its_
  limit`; `test_prices_are_installed_package_data`; the import-graph test. `tests/test_manifest.py`
  gains exact-`Decimal` parsing coverage for `[budget]` (rejecting the float-comparison trap
  directly: `Decimal("0.05") == 0.05` is `False` in Python, so an existing test written the wrong
  way would have silently stopped proving anything). `tests/test_check_script.py` gains a check
  that the new gate's own snippet is genuinely present in `check.sh` — nothing else would notice if
  it were quietly deleted, since neither `ruff` nor `pyright` parse shell.

  **An independent adversarial review before this reached a commit found two real defects and
  three test-coverage gaps, all fixed here** (a `docs/RETROSPECTIVES.md` entry is owed once the
  parallel documentation pass reaches it — recorded here in full for now, per this round's scope):

  - `prices.py`'s malformed-file handling caught TOML *syntax* errors but not value-level ones:
    `Decimal(str(x))` raises `decimal.InvalidOperation`, not the `ValueError` `floors.py`'s
    `float(x)` raises for the same mistake, so a one-typo price (a European "5,00", an unfilled
    "TBD") or a wrong-shaped `models` table crashed uncaught instead of raising the documented
    `PricesMissingError`. Both exceptions are now caught.
  - `window.py`'s entire reason to exist — converting a differently-zoned input into `[budget]
    timezone` before comparing — was completely unexercised: every test constructed
    `reserved_at`/`now` already in the target zone, where `.astimezone()` is a no-op, so mutating
    the conversion away entirely still passed every test. A new test aggregates a UTC-stamped
    record against a Berlin-configured window (2026-03-15 23:30 UTC is the *next* calendar day,
    00:30, in Berlin) and catches exactly that regression.
  - `estimate_document` had no validation on `pages`/`pages_estimated`: `pages=0` divides by zero
    computing `per_request_eur`, and a negative `pages_estimated` produced a *negative*
    `total_eur` — the one direction a budget guard must never move, since it understates real
    spend rather than overstating it. Both now raise `ValueError` before any arithmetic runs.
  - `Table.decimal()`'s default path returned early, skipping its own `minimum` check — unlike
    `integer()`/`number()`, which validate their defaults for free by sharing one code path with
    the parsed value — so a below-`minimum` default would have silently passed. Restructured to
    check `minimum` on both paths.
  - `reserve_document`'s "every blocked window is named" claim and `reserve()`'s "first breach
    wins, in order" claim were each tested only where every window breached at once (or where
    only one *could*), so neither a partial breach nor a genuine two-window tie was ever
    exercised. `confirm_above_eur`'s exact boundary (`>`, not `>=`) had only an incidental test,
    never a dedicated one. Three new tests pin all of this down.
  - Two low-severity fixes: `ContextWindowExceededError`'s remedy suggested lowering a
    "`[chunking]`-equivalent slice size K" that does not exist as a configurable knob (`K` is a
    fixed constant); and a cap lowered mid-window below already-recorded spend printed a negative
    "headroom €-X.XX" in a refusal message, now rendered as "already €X.XX over cap" instead.

  Documentation for this increment landed separately, immediately after — see *Documentation* below.

### Documentation

- **[`docs/KB-UPDATES.md`](docs/KB-UPDATES.md) — what happens to a KB somebody already has when
  pinakes changes.** A design note, decided but **not built and not assigned to an increment**. The
  build plans had specified three drift axes and never asked about the fourth: an index schema, an
  embedding model and a PDF extractor each drift *detectably* and are remedied by rebuilding derived
  state, which is free — while a manifest and a template drift **silently**, and the remedy touches
  a file the user owns, so it cannot borrow the same shape.

  The gap is live rather than theoretical: I9's `**/*.pdf` template line will reach new KBs only, so
  every KB created before it stays PDF-blind permanently; and `doctor`'s sole drift signal compares
  declared version strings (`doctor.py:135`) while I9 as drafted changes template content without
  bumping `1.0` — a rule with no gate, lapsed before shipping.

  A compatibility asymmetry nobody designed on purpose is recorded with its evidence: **sidecars are
  forward-compatible** (unknown keys preserved under `extra`, `sidecar.py:35`) while **the manifest
  is not** (unknown keys are a hard error, `_toml.py:184`) — demonstrated against `main`, where a
  future `[budget]` key is refused with a remedy blaming a *typo* for what is version skew.

  Decisions recorded: downgrade is unsupported and refuses loudly; strictness is unchanged;
  `[kb]` gains `requires_pinakes` so the refusal can name the version, read in a **pre-pass** before
  validation or it is unreachable in the one case it exists for; `pnk upgrade --apply` may write to
  `pinakes.toml` via `tomlkit` (MIT, zero dependencies, 197 KB) with comments preserved, but never
  touches `docs/`, never renumbers a ULID and never re-chunks as a side effect; and a CI gate hashes
  the template directory minus an ignore-list, so a content change without a version bump fails at
  commit time rather than in a user's KB.
- **The docs now describe I6a, and the shipped-vs-merged distinction they lacked.** I6a's own
  implementation deliberately left `docs/` untouched while a parallel restructuring pass was in
  flight (that pass became `0.2.1`); this reconciles the two.

  `docs/DESIGN.md` §5 replaces its "⏳ pending amendment" placeholder with the real rationale: the
  first spender is the paid PDF extractor rather than `pnk ask --deep`, three independent windows
  instead of one cap, why a *request* (a fixed page slice) is the estimation unit rather than a
  document or a page, the reservation/reconciliation/void aggregation rule, why money is `Decimal`
  end to end, and why price staleness is a runtime refusal rather than a CI gate.
  `docs/MANIFEST.md` documents `daily_eur` and `max_price_age_days` with their real defaults (read
  from `manifest.py`, then verified against it), states that all three caps are checked and that a
  refusal names every blocked one at once, and notes the exact-`Decimal` parsing.

- **`docs/STATUS.md` said "Installed version: 0.2.0" while the package was already `0.2.1`** — the
  one file whose entire job is being right about what ships. Now `0.2.1`, and it gained the
  distinction it was missing: an increment merged to `main` but not released reads **"on `main`,
  unreleased"**, never "shipped", because installing from a tag and installing from `main` are
  different answers to "can I use this yet". `docs/README.md`'s landing checklist says so too.

- **The I6–I9 version target is decided** (`docs/STATUS.md`): they accumulate in `[Unreleased]` and
  cut as one MINOR release once paid extraction is usable (I7b) and safe (I7c) — never a `0.2.x`
  patch, since a KB that can spend money is new capability. I6a, I6b and I7a are each explicitly
  partial and none passes the SemVer table alone. **The number itself is left unassigned and the
  reason is recorded**: `v0.3` is already committed across the docs, `docs/graph/` included, as the
  cross-KB links release, so taking `0.3.0` for paid extraction cascades through the whole roadmap.
  That is a roadmap decision rather than a documentation one. Forward roadmap rows are relabelled as
  ordered scope rather than assigned numbers, since pre-assigning a version years ahead is what
  created the collision.

- `docs/README.md` gains the rule this round produced the hard way: **check what has landed on
  `main` before assigning a release number** — an I6a worktree nearly reasoned about "0.2.1 vs
  0.3.0" from a stale base while a parallel pass had already shipped `0.2.1`.

- `docs/RETROSPECTIVES.md` gains I6a's entry: the timezone conversion whose every test passed with
  the conversion deleted, an except-tuple inherited from a sibling module that parsed with `float`
  where this one parses with `Decimal`, missing validation at the one boundary where a wrong sign
  understates spend, and three true-but-untested assertions.

## [0.2.1] — 20260728 16:54

### Added

- **A documentation structure built for continuous development.** Each fact now has exactly one
  home, so landing an increment edits one file instead of four. New:
  [`docs/GUIDE.md`](docs/GUIDE.md) (how to use it, task by task — install, first KB, PDFs, search,
  calibration, git hooks, MCP setup, troubleshooting), [`docs/CLI.md`](docs/CLI.md) (every command,
  flag and exit code, plus a *Planned* table naming the increment behind each unbuilt surface),
  [`docs/MANIFEST.md`](docs/MANIFEST.md) (every manifest and sidecar field with its default, read
  from `manifest.py` rather than restated), [`docs/STATUS.md`](docs/STATUS.md) (**the only place in
  the repo that says what is built**, carrying the v0.2 increment ledger and the measured numbers),
  [`docs/README.md`](docs/README.md) (the index, a *where does a fact live* routing table, and a
  *landing a new increment* checklist) and [`docs/graph/README.md`](docs/graph/README.md) (an index
  for the fifteen research documents, with each project's licence and the three that may never be
  copied from).
- Every command in `docs/GUIDE.md` was **run against 0.2.0 before it was written up**, per the
  repo's own rule that docs are checked by running what they show. That is how the two caveats below
  were found.

### Fixed

- **`docs/DESIGN.md` §4.6 stated a span invariant that is false for PDFs.** `plans/v0.2.md`
  assigned the correction to I5, which shipped in 0.2.0 without it, so the released design claimed
  every citation "can be located exactly in the original file". It cannot for a PDF: the offsets
  address the *pinned extraction*, not the file, and what a PDF citation locates is a page. The
  invariant is now stated as `chunk.text == indexed_text[char_start:char_end]` with the two source
  types' consequences distinguished.
- **`pnk search --source-type` help hid a working filter.** It read "markdown, text or code" while
  `chunk.source_type` has returned `"pdf"` since I5 — the filter worked and was undiscoverable.
- The `notes` template's `[budget]` comment promised "nothing spends money before v0.4", which
  `plans/v0.2.md` decision 2 falsified by moving the first paid path into v0.2. It is now
  version-free and points at `docs/STATUS.md`.
- `docs/DESIGN.md`'s status line still read "v0.1.1 shipped", two releases stale. The document no
  longer carries a version at all — it is rationale, and `docs/STATUS.md` owns release state.
- The README described v0.1: no mention of PDF ingest, no `[pdf]`/`[claude]` install lines, a KB
  diagram with the one file type v0.1 could not read removed from it, and `make corpus` /
  `make pdf-eval` undocumented. It is now **deliberately version-free**, so it cannot drift again.

### Changed

- `docs/DESIGN.md` is specification and rationale only. Its manifest and sidecar field tables moved
  to `docs/MANIFEST.md`, its release table to `docs/STATUS.md` (the *why this order* reasoning
  stays), and its §10 iteration log to `docs/RETROSPECTIVES.md`, where all project history now
  lives. 879 → 783 lines with nothing lost.
- Three DESIGN sections whose amendments belong to unshipped increments (§5 budget, §4.7 agent
  surface, §9 scanned OCR) now carry dated **⏳ pending** notes naming the increment, rather than
  either describing unbuilt behaviour or silently contradicting the plan.

### Known issues surfaced (not fixed here)

- **A PDF dropped into a fresh KB is silently skipped.** `pnk init` stamps
  `include = ["**/*.md", "**/*.txt"]`, so v0.2's headline feature is off by default and sync reports
  `0 indexed` explaining nothing. Adding the commented-out `**/*.pdf` line is `plans/v0.2.md`
  decision 6, owned by I9; documented as a caveat in `docs/STATUS.md` and `docs/GUIDE.md` meanwhile.
- **I6–I9 have no version target.** The plan cuts 0.2.0 at the end of I9; it was released after I5.
  Recorded as an open question in `docs/STATUS.md`.

## [0.2.0] — 20260728 14:05

### Added

- **I1 of the v0.2 build order: extras, the extractor seam, and an honest core-only failure.**
  `pyproject.toml` gains `[pdf]` (pypdfium2) and `[claude]` (the Anthropic SDK, requiring `[pdf]`)
  as opt-in extras — core stays torch-free and now extractor-free too. `src/pinakes/extract/`
  is a new package: an `Extractor` protocol, the `ExtractedText`/`ExtractionContext` types that
  will cross the seam for every backend to come, and an open, lazily-importing registry (mirroring
  `embed.py`'s) holding `pypdfium2` and `claude-vision` as honest stubs that name the increment
  that implements them (I3b, I7b) — plus a working `fake` backend for later increments to test
  against without either extra installed. `chunk.source_type` maps `.pdf` → `"pdf"`, and
  `pnk sync` routes a PDF through the registry instead of crashing on `read_text`: extraction
  failures record a `failures` row at stage `extract`, isolated from every other document, with
  the remedy printed once rather than once per file. The manifest gains `[extraction]`
  (`backend`, `model`), validated against the registry without importing anything, and
  `pnk sync --extract=BACKEND` overrides it for one run. `pnk doctor` gains a `pdf extractor`
  check. CI's `check` job is now a three-leg matrix (`[light]`, `[light,pdf]`,
  `[light,pdf,claude]`), and `check.sh` gains an `extras-not-core` gate.
- **I2: the synthetic hard-case PDF corpus and its generator.** `tests/pdf-corpus/` holds 19
  committed fixtures across seven strata (two-column, tables, headers/footers, ligatures &
  hyphenation, scanned, pathological, baseline) totalling 59 pages and 266 KiB of PDF against a
  2 MiB budget (216 KiB of it the scanned stratum, against 1.5 MiB), each paired with a
  hand-authored `.expected.txt` written from the fixture's *spec* — never from an extractor's
  output, which would only prove an extractor agrees with itself. No real-world PDF is committed:
  a dependency-free PDF writer (`pdfwriter.py`) emits raw content streams using the base-14 fonts,
  so no layout engine hides the coordinates under its own decisions. The three scanned fixtures
  raster `baseline-12p`'s own pages via pypdfium2 + Pillow and reuse its ground truth verbatim,
  making free-vs-paid extraction directly comparable on identical content. `make corpus`
  regenerates in place; `check.sh` gains a `corpus-regenerates` gate where the sixteen text-layer
  fixtures must reproduce **byte-identically** and the three scanned ones within a stated pixel
  tolerance (>300 pixels differing by >32 levels is a failure — an absolute count, derived in the
  test's own docstring, because a whole-page mean would accept arbitrary reflow). Pillow joins the
  dev dependency group only, never core and never an extra, and `pdf_runnable()` grows the third
  half of its environment check to match.
- **I3a: the free extraction pipeline's pure, structural half.** `src/pinakes/extract/layout.py`
  turns pdfium's character-level text into ordered, de-furnished text with no PDF library and no
  filesystem access (asserted by an import-graph test): `blocks_from_chars` groups characters into
  line-level blocks from geometry alone — including splitting same-height text into separate
  blocks at a column-sized gap, not a single line spanning the page; `reading_order` clusters
  blocks into columns by `x0` gap and orders top-to-bottom within each; `strip_running_heads`
  suppresses a line recurring, digits normalised, on `>= T` of pages (never fewer than two, or a
  one-page document would see every line as "100% recurring" and suppress itself whole);
  `join_hyphenation` joins a trailing hyphen or U+00AD into a lowercase continuation, skipping
  transparently over suppressed running heads but never joining into a heading, and can join
  across a page boundary. `extract/textpolicy.py` carries the one string policy both extraction
  backends will run — ligature expansion, NFC, whitespace collapse — versioned separately
  (`TEXT_POLICY_VERSION`) from `LAYOUT_VERSION` so a change to either is never invisible to the
  other's fingerprint. `assemble()` runs the whole pipeline and emits the seam's `ExtractedText`,
  normalising each block *before* computing its offset — never after, since normalisation changes
  length. Forty-two table-driven tests check three properties per `assemble()` case, not two:
  join-identity and contiguous coverage are one property and its corollary, so a third,
  content-anchored assertion (a sentinel placed on one page, and no other, must fall inside that
  page's span, and every non-empty page must carry one) is what actually catches a wrong page
  number.
- **I3b: the pypdfium2 adapter, the extraction-quality metrics, and the two fitted floors.**
  `extract/pdfium.py` is a thin I/O reader: guards a file's size at 256 MB before ever opening it,
  translates pdfium's own refusals into a named `ExtractionError` (corrupt/malformed header,
  password-protected, no pages at all), turns pdfium's character-level text API into I3a's
  `CharSpan`s, and hands the whole document to `layout.assemble()`. `slice_pages(path, first,
  last)` is I7b's future request unit, clamping its own range since `import_pages` raises outright
  on an out-of-range index rather than tolerating one. `extract/quality.py` scores a free-path
  extraction against `tests/pdf-corpus/`'s ground truth on five metrics — `char_recall`,
  `order_fidelity`, `junk_rate`, `pair_adjacency`, `word_coverage` — each carrying its own
  numerator and denominator rather than a bare float, so a stratum with nothing to measure reports
  `null`, never an indistinguishable `0.0`. `make pdf-eval` (`check.sh`, and CI as its own job in
  this commit, not deferred to I9) extracts and scores every fixture, compares each stratum
  against a committed `tests/pdf-corpus/baseline.json` with a tolerance, and re-fits both floors to
  check neither has drifted. Two floors are fitted from the corpus, not guessed, and ship as
  package data (`extract/floors.toml`, beside I6a's future `prices.toml`) with `fitted_on`: the
  running-head threshold *T* (0.666667 — the midpoint of the lowest recurrence any genuine running
  head reaches across the headers-footers stratum and the highest recurrence anything else
  reaches, `tests/pdf-corpus/spec.py::KNOWN_RUNNING_HEAD_SIGNATURES` stating which is genuine per
  fixture) and the text-yield floor (65.75 non-whitespace characters per page — the midpoint of
  the scanned stratum's yield, 0, and the lowest real document's).

  Verifying the adapter against real PDFs — the first time in this project real pdfium output ever
  reached I3a's pure pipeline — surfaced six defects the hand-built fixtures in `test_extract_layout.py`
  never could: `_LINE_TOLERANCE` (2.0) was too tight for real descender depth, silently splitting
  g/y/q/j onto phantom one-character lines; the geometric word-gap heuristic inserted a space
  between nearly every letter pair, since real intra-word kerning gaps and inter-word gaps overlap
  (now removed — word breaks come from the source stream's own space characters); `reading_order`'s
  column clustering read a caption spanning two columns as that column's own last line rather than
  after both (fixed with a width-based spanning-block detection, `_SPANNING_WIDTH_FRACTION`); a
  `Tj` string authored with an embedded line break duplicated the newline `assemble()` already
  inserts between blocks; a soft hyphen sitting mid-block (not at a block boundary) was never
  removed by any existing code path (`textpolicy.normalise` now drops U+00AD unconditionally,
  wherever it falls); and I2's `pdfwriter.py` wrote a *partial* ToUnicode CMap that made pdfium
  misreport an unrelated, unmapped character as U+FFFE — fixed by filling in an identity mapping
  for every printable ASCII byte, not only the one needing an override. The `hyphenation-soft`
  fixture is restructured to a two-page layout (the same shape `hyphenation-page-break` already
  used safely) after finding that pdfium's own text-extraction reconstruction misreads an ordinary
  hyphen as U+FFFE whenever the text-showing operation ending in it is immediately followed by
  another one starting lowercase *on the same page* — and its own ground truth had a typo
  ("archive" + U+00AD + "al" spells "archiveal", not "archival"). All six are recorded in
  `docs/RETROSPECTIVES.md`.

  **A known, accepted limitation:** `reading_order`'s column detection is geometric, not
  structural, so the free path reads a table column by column, not row by row.
  `pair_adjacency` measures this directly for the tables stratum, though this corpus's own tables
  are small enough that even the wrong reading order keeps a label and its value within the
  metric's 80-character window — a disclosed limitation of this corpus's diagnostic power, not of
  the metric's design. There is no `word_coverage` floor yet (decision 12, `plans/v0.2.md`): the
  correct pair to fit it against is (native layer → Claude's output), and no Claude output exists
  before I7b.
- **I4: the extraction cache.** `extract/cache.py` — one JSON file per
  `.pinakes/cache/extract/<content_hash>-<fingerprint>.json`, storing the whole `ExtractedText`
  (text, page spans, per-page provenance) a call returns, so a cache hit and a cache miss are the
  same shape to every caller. `_index_document`'s PDF branch now calls the cache instead of the
  extractor directly; the extractor is only ever loaded — importing pypdfium2, say — on an actual
  miss, never on a hit. Invalidation is by key alone (a changed `content_hash` or a changed
  `fingerprint`, e.g. a fitted-threshold update); any entry that fails to parse — missing,
  truncated, an unrecognised schema — is a miss, never a crash. `operation_id`/`call_ids` are
  already part of the schema, always `null` today, as the future join key to `ledger.jsonl`
  (I6b/I7c) — so no cache migration is needed once a paid backend exists to populate them.

  After a fully successful sync (never after one with failures; for `--rebuild`, only once its
  atomic swap has landed), entries whose `content_hash` matches no active document are swept —
  except entries a paid backend wrote (`operation_id` is not `None`), which are only ever
  reported, never deleted automatically: a soft-deleted or un-sidecarred document is not an
  "active document," and sweeping away a paid extraction with no prompt and no printed cost is
  the one mistake this cache must not make. `pnk sync --clear-cache` empties `cache/extract/`
  entirely (paid or free, active or orphaned) after confirming — it prints the entry count and
  bytes and requires a `y`; `--yes` skips the prompt for cron use — and never touches
  `ledger.jsonl`, the same guarantee `--rebuild` already gives. `pnk doctor` gains an "extraction
  cache" check: entry count, bytes, `orphans/entries`, and paid orphans (`Status.WARN` when any
  paid orphan or unreadable entry exists) reported separately.

  **Tests, `tests/test_extract_cache.py` (no `pypdfium2` needed — a plain callable stands in for
  the extractor):** a hit never calls `extract` at all, not even lazily; a changed content hash, a
  changed fingerprint, a truncated file, a wrong schema version, and a missing required field each
  miss rather than crash; two KBs holding the same PDF get two cache files; a paid orphan survives
  the sweep and is reported while its free twin is removed; a corrupt entry is left alone, not
  swept, since a paid entry can't be ruled out for a file that can't be read. `tests/test_sync.py`
  adds the integration wiring: a plain second sync of an unchanged PDF never reaches the cache at
  all (pairing's own `Skip` returns first), so the reuse test uses `--rebuild`, which forces every
  document back through `_index_document` — proving a real cache hit (the entry's mtime is
  unchanged) rather than merely proving pairing's pre-existing skip; a fully successful sync
  evicts a deleted document's entry; `--clear-cache` preserves the ledger, aborts without `--yes`,
  and is a no-op (not a prompt) on an empty cache.
- **I5: PDF chunking, page provenance, and a backend-aware sync (`schema_version` 2 — a v0.1 or
  pre-I5 index refuses to open, naming `pnk sync --rebuild`).** `chunk_document(kind="pdf")` looks
  up each chunk's page span against the extractor's own per-page character spans and stores it as
  1-indexed `page_start`/`page_end` — no new block-splitting algorithm, since the existing
  blank-line block detection already produces a block spanning two pages whenever
  `join_hyphenation` (I3a) joined a word across one; `heading_path` stays `None` for every PDF
  chunk, since a PDF has pages, not headings. `documents` gains `extraction_backend` /
  `extraction_fingerprint`, populated only for PDFs; `ExtractorEntry` gains a `paid: bool` field
  (`claude-vision` alone is `True`) so a coherence or pairing decision can ask "is this backend
  paid" from the registry alone, never by importing the client.

  **Decision 9 — a paid extraction is never silently downgraded.** `pairing.py`'s decision table
  grows three backend-aware rows: a free-recorded, paid-effective document is always stale,
  regardless of hash; a paid-recorded, free-effective, **unchanged**-hash document is skipped —
  not by a hook, not by `--rebuild`, not by an explicit free `--extract` — and the run says once
  which paths were protected; the same document with a **changed** hash is neither a silent Skip
  nor a silent overwrite but a `failures` row naming the paid remedy (decision 14), since letting
  the hash win would overwrite paid text with a free extractor's empty output on an image-only PDF,
  and letting the backend win would describe a file that no longer exists, forever. `pnk sync`
  gains `--force`, meaningful only together with an explicit free `--extract`: the one combination
  that overwrites a paid extraction, printing what it discarded first (`--force` alone changes
  nothing). A paid extraction under `--index-only` is refused with a remedy naming a normal sync,
  since recording it requires writing into `docs/`, which `--index-only` must never do.

  **Provenance lives in the sidecar, because `--rebuild` reads its `before` from a brand-new,
  empty database** (`docs/DESIGN.md` §6.4) — a backend recorded only in `index.db` is invisible at
  exactly the moment a rebuild needs it. The sidecar's existing `provenance` block gains an
  additive `extraction: {backend, fingerprint, extracted, content_hash}`, written only when a
  genuinely fresh paid extraction happens (or `--force` clears a stale one), never for the routine
  free case. `index.db`'s two extraction columns are the sidecar's cache, reseeded from it.
  `content_hash` here is the file's own hash *at the time of that paid extraction* — narrower than
  the general change-detection hash `docs/DESIGN.md` §2.2 already refuses to store, and the one
  fact that lets a later sync answer "has this changed since" **directly**, without depending on
  whether `extract/cache.py`, or any prior local index, still happens to hold the answer.

  A rebuild does not depend on `extract/cache.py` to honour this: before the new database exists,
  sync reads the *old* `index.db` (still on disk until the atomic swap) for every paid-recorded
  document, keyed on `doc_id` alone — this table's own primary key, therefore unique by
  construction, and the one identifier a renamed sidecar still carries unchanged — and copies its
  row, chunks and embeddings straight across via SQLite's `ATTACH DATABASE`, at the file's *old*
  content_hash. If that still matches the current file, the document is simply protected; if it
  does not, the stale row is copied forward anyway alongside a `failures` entry, so a changed paid
  document survives a rebuild exactly as it survives a normal sync (decision 14) rather than
  vanishing from the index the instant one runs. A rename reaches this same guarantee a different
  way: `pair()`'s `Adopt`/`Rename` rows never touch the same-path comparison a normal sync uses, so
  a sync also checks whether *this same connection* already holds an active row for the document's
  own `doc_id` at its unchanged content_hash, before `extract/cache.py` is ever consulted at all.

  **Per-document extraction coherence** (`docs/DESIGN.md` §4.4, decision 13): every query
  re-derives each distinct recorded backend's current, client-free fingerprint and compares. A
  mismatch on a **free** backend refuses the query, naming the stale paths (the text can be
  silently wrong, and re-extracting is free). A mismatch on a **paid** backend never refuses —
  the text is still correct, merely older — but marks every affected `Passage.stale_extraction`
  and warns in `pnk doctor`. An unrecognised backend name is skipped, never a reason to refuse an
  otherwise-healthy KB. `pnk doctor` also gains three by-path gap reports: documents awaiting a
  paid extraction, paid extractions the manifest no longer asks for, and a paid document whose
  file has changed since.

  **Caught by an independent adversarial review before this ever reached a commit** (full detail:
  `docs/RETROSPECTIVES.md`): the original design protected a paid extraction only via `pair()`'s
  same-path comparison or `--rebuild`'s own copy-forward — any *other* pairing outcome (a rename,
  or a document adopted some other way) fell through to a cache lookup alone, which cannot tell
  "just renamed" or "just cloned" apart from "genuinely changed" — all three look identical as a
  cache miss. Fixed by moving the change-decision itself onto the sidecar's own recorded
  content_hash (above), with a same-connection lookup added for the rename case and the
  doc_id-keyed rebuild lookup extended to the changed-hash case — three fixes, described in the
  two paragraphs above rather than as a separate, later correction. A `sidecar_hash` staleness bug
  (a fresh paid-provenance write left the very next sync one `RefreshMetadata` cycle away from
  settling) was found and fixed the same pass.

  **Tests:** `tests/test_chunk_pdf.py` proves the span invariant, the never-drop guarantee, and
  page monotonicity over the corpus's 15 extractable fixtures, plus a dedicated two-page-chunk
  case against the `hyphenation-page-break` fixture. `tests/test_pairing.py` and
  `tests/test_sync.py::test_backend_drift` (six named cases, addressable as
  `test_backend_drift[changed_hash]` etc.) cover the decision table in isolation and end to end;
  `test_a_rebuild_preserves_paid_provenance` and `test_a_rebuild_after_clear_cache_still_
  preserves_it` cover the two rebuild cases specifically — the second constructed, and confirmed
  by deliberately reverting the `ATTACH DATABASE` mechanism first, to fail without it.
  `test_a_rebuild_never_lets_a_free_twin_inherit_the_paid_ones_backend`,
  `test_a_rename_after_clear_cache_does_not_falsely_claim_content_changed`,
  `test_a_fresh_clone_with_no_local_cache_or_index_fails_honestly_not_falsely`,
  `test_a_rebuild_keeps_a_changed_paid_document_searchable_but_flagged` and
  `test_three_consecutive_paid_syncs_settle_after_the_first` each cover one review finding above,
  every one confirmed to fail against the pre-fix code first. A working *paid* test backend stands
  in for `claude-vision`, whose own loader remains an honest I7b stub throughout.
  `tests/test_search.py` covers both coherence outcomes and asserts `"anthropic" not in
  sys.modules` after a query, in a subprocess, over a KB holding a paid document.
  `tests/test_doctor.py` covers the extraction-coherence WARN and all three by-path gap reports,
  including that "paid extraction not requested" stays green — it names the protection working,
  not a problem.

### Fixed

- **`main` had been CI-red since I2's first scanned-corpus run — through I3a and I3b — on a
  cross-platform rendering bug nobody had checked GitHub Actions for.** `test_scanned_regeneration_
  within_tolerance` failed deterministically on the `check (light pdf)` / `check (light pdf
  claude)` jobs with the identical signature every time: `scanned-clean: 8006 pixels differ by >32
  levels`. `pdfwriter.py` wrote every text fixture as `/BaseFont /Helvetica` with no embedded font
  program, relying on the PDF reader's own substitution — and pypdfium2's prebuilt binaries
  substitute a *different* font per platform (macOS has a real Helvetica; `ubuntu-latest` doesn't).
  Same word-wrap, same layout, different glyph outlines, so the scanned stratum (rasterized through
  pdfium at fixture-generation time) baked in whatever glyphs the generating machine's pdfium
  substituted. Confirmed directly, not just theorized: an `ubuntu:24.04` Docker container
  reproduced CI's exact number (8,006 px) on the first try, and a diff heatmap showed every changed
  pixel sitting exactly on a glyph edge — same text, same positions, different anti-aliasing.
  Measured cross-platform noise across all ten scanned pages ranged 507-8,262 px, which ruled out
  simply raising `MAX_CHANGED_PIXELS`: the test's own docstring establishes its detection target as
  a single moved word, plausibly smaller than that noise floor, so a threshold wide enough to
  absorb it would likely have gone blind to the exact defect class the test exists to catch. Fixed
  at the root: `pdfwriter.py` now embeds a subsetted, real TrueType font
  (`tests/pdf-corpus/fonts/LiberationSans-Subset.ttf`, SIL OFL 1.1 — the project's first and only
  third-party binary asset, chosen for Helvetica/Arial metric compatibility so none of
  `generate.py`'s hand-placed coordinates needed to change) instead of a bare base-14 name, so
  every platform rasterizes the same glyph outlines. Re-ran the same Docker reproduction after the
  fix: 0 pixels changed across every scanned page, not merely under tolerance. `Font` drops its now
  always-"Helvetica" `base_font` field; `_font_object` gained a real `/FontDescriptor`/`/FontFile2`/
  `/Widths` embed, derived from the subset's own hmtx/head/hhea/OS2 tables (documented, reproducible
  commands in `tests/pdf-corpus/fonts/README.md`) rather than assumed. All nineteen fixtures were
  regenerated; no `.expected.txt` changed, confirming the font swap altered no extracted character.

## [0.1.4] — 20260727 21:19

### Added

- **`plans/v0.2.md`**, the reviewed build order for the PDF-extraction release (I1–I9): a free
  `pypdfium2` extractor, an opt-in paid Claude-vision extractor, and the budget machinery that
  ships with the first thing that can spend. Reviewed over four adversarial passes (7 HIGH/19
  MEDIUM/8 LOW, 5/18/8, 12/31/17, then three narrow methods — code-reality, arithmetic,
  promise-ledger — at 19/39/23) before implementation began.
- **A CLAUDE.md rule: read the clock, never compose a timestamp.** Run `date "+%Y%m%d %H:%M"` and
  paste the result — session context carries a date but never a time, so an invented `HH:MM` lands
  in the future about half the time, as four stamps in an early plan draft did.

## [0.1.3] — 20260727 15:40

### Added

- **A post-v0.1 housekeeping retrospective** in [`docs/RETROSPECTIVES.md`](docs/RETROSPECTIVES.md),
  covering the release-that-never-happened, the docs-only merge that turned `main` red, the merge
  run from inside a worktree that silently landed nothing while leaving a tag off-`main`, the four
  README claims that contradicted the code, and the promised CI gate that no increment owned.
- Three rules promoted into `CLAUDE.md` from those findings: verify a release the way a stranger
  would (`git tag -l`, `gh release list`, `merge-base --is-ancestor`) rather than believing the
  CHANGELOG; never `git merge` from inside the feature worktree, where three successive commands
  report success while nothing lands; and the README describes what ships, checked by running the
  commands it shows.

## [0.1.2] — 20260727 15:25

### Fixed

- **README accuracy.** An audit against the shipped CLI found the README to be the only surface
  overclaiming — `cli.py` and the CHANGELOG both say "planned for v0.4" where the README said
  "exists". Corrected: `pnk ask --deep` is now stated as planned rather than shipped; the budget
  ledger is future tense (`[budget]` is parsed and validated today, consumed by nothing); the
  install lines no longer point at a PyPI package that returns 404, and give a working
  install-from-source instead; the headline KB diagram no longer shows a `.pdf`, which is the one
  file type v0.1 cannot ingest (that lands in v0.2); and the design-review line now says four
  externally *verified* claims, two of which proved false, rather than "four factual errors".
- **A `[light]` install no longer walks into a wall.** `pnk init` always stamps the
  sentence-transformers backend, so the documented `[light]` path failed at the first `pnk sync`.
  The README now says to set `provider = "fastembed"` first. (The underlying asymmetry — `init`
  cannot see which extra is installed — is left for a `--backend` flag rather than papered over.)
- `docs/DESIGN.md`'s status line said "ready to implement" two releases after shipping, and §8
  listed the PyPI release as delivered when nothing has been published.
- The `[0.1.1]` CHANGELOG heading had no matching link definition, so it rendered as literal text,
  and `[Unreleased]` still compared against `v0.1.0`.

### Added

- README **Development** section (`make install` / `check` / `demo` / `eval`) — the Makefile shipped
  in 0.1.1 without its README counterpart, which the repo's own docs rule requires.
- README and `docs/DESIGN.md` §8 now point at [`docs/graph/`](docs/graph/); ~3,000 lines of research
  shaping v0.3 were reachable only from the CHANGELOG. §8 also gains the `v0.3.x` row for the
  eval-gated PPR channel and `[ner]` extra.

## [0.1.1] — 20260727 14:52

Documentation, tooling and release plumbing. No change to installed behaviour: the wheel's code is
identical to 0.1.0.

### Added

- **Graph-integration research** under [`docs/graph/`](docs/graph/) — fourteen investigation docs
  (LightRAG, microsoft/graphrag, Graphiti, HippoRAG 2, fast-graphrag, Graph-R1, LinearRAG,
  datastax/graph-rag, code-graph-rag, MiniRAG, Youtu-GraphRAG, LogicRAG, and ClaudeKB as the
  in-house precedent) plus `GRAPH_RAG.md`, the research record, and `PINAKES_APPROACH.md`, which
  turns them into a gated build order: free structural edges at sync, a staged expansion→PPR graph
  channel behind `graph_channel` (default off), a typed and capped `pinakes_links` returning score
  plus frontier, and a budgeted `--deep` loop whose discoveries are written back to sidecars. The
  synthesis passed six adversarial review passes (27→7→8→5→1→0 findings).
- **`Makefile`** — every target wraps the command CI actually runs, so a green `make check` locally
  means what it means on the runner. `make help` lists them.
- **A close-out on [`plans/v0.1.md`](plans/v0.1.md)** — "What the build taught", written against the
  15 shipped increments and the 52 retrospective findings: where the plan proved right, where it was
  wrong and whether planning could have caught it, what happened to each named risk, twelve rules
  for the next plan, and the list of what in it is now stale. The headline: no finding invalidated
  any plan-level decision, and every expensive miss was *machinery* — gate mechanism, test fidelity,
  warning policy, metric denominators, write durability — in a plan that specified algorithms
  closely and machinery barely at all.
- **CI gate: the free path stays free.** `plans/v0.1.md` promised a check that no paid-API client is
  imported in `src/` and it never shipped, because the item sat in a section with no increment
  number and so no increment owned it. Now enforced, and verified in both directions — it passes on
  the current source and catches a planted `import openai`.

### Changed

- The PyPI upload in the release workflow is **gated on the `PUBLISH_TO_PYPI` repository variable**
  and skipped rather than attempted while it is unset. Version/tag agreement, build and the
  isolated wheel smoke test still run on every tag, so tagging is always safe and never produces a
  red run for a reason the maintainer already knows about.
- `CLAUDE.md`: the increment workflow is no longer v0.1-specific, and a new *Landing work* section
  records the standing rule — always push to `origin/main`, always cut the release once the work
  passes the SemVer table, never let complete work sit in `[Unreleased]`.
- `test_version_is_set` asserts the version's *shape* (SemVer, never the `0.0.0` placeholder)
  instead of a hard-coded literal, which made every release edit a test for no functional reason.

### Fixed

- Red `main`: `ruff format --check` covers Python fenced blocks **inside Markdown**, so a docs-only
  merge failed the Format gate. The snippet is reformatted, and `CLAUDE.md` now says plainly that a
  docs-only commit is still subject to the full gate.

## [0.1.0] — 20260725 15:27

### Added

- **I1** — package skeleton: `errors.py` (`PinakesError` carries a message *and* a remedy, so no
  failure path strands the user), and `cli.py` rebuilt as argparse subparsers declaring the whole
  v0.1 command surface up front. Unimplemented commands name the increment that will land them.
  Exit codes are a contract: 0 success, 1 operational failure, 2 usage error.
- `ty` added as a dev dependency and fast type pre-check; `pyright` strict remains the gate
  (measured comparison in `docs/RETROSPECTIVES.md`).
- **I2** — identity: `ids.py` (ULID minting and strict parsing behind `KbId`/`DocId` NewTypes) and
  `uri.py` (`pnk://<kb-ulid>/<doc-ulid>`). Aliases are rejected inside a URI with an error naming
  where they do belong; `pnk://self/…` parses to an unresolved `ParsedUri` that *cannot* be
  formatted, so expanding it against the owning KB is enforced by the type system rather than by
  discipline. Lowercase IDs are rejected rather than normalised.
- ruff `BLE` ruleset enabled (blind `except Exception`), after I2's retrospective found two.
- **I3** — manifest: `manifest.py` parses and validates `pinakes.toml` (DESIGN §2.1) into frozen
  dataclasses, plus `find_kb_root` git-style walk-up. Unknown keys are a hard error, not a silent
  default — as is the retired `top_k`, which is rejected by name. Cross-key invariants are checked
  at read time: widths must narrow (`final_k <= fusion_top_k <= candidates_per_source`),
  `confirm_above_eur <= per_operation_eur` (or the confirmation prompt is unreachable),
  `overlap < max_tokens`, ordered confidence thresholds, and `fitted_for` required whenever
  thresholds are present. `[budget]` is validated from v0.1 though nothing consumes it until v0.4.
- **I4** — storage: `store.py` creates and opens `.pinakes/index.db` (DESIGN §3) — documents,
  chunks, FTS5 external-content index with its triggers, float32 vector BLOBs, links, kb_refs,
  failures and meta. `connect_rw` (WAL, foreign keys on) and `connect_ro` (`mode=ro`, so the MCP
  server cannot write even by mistake); a `schema_version` mismatch refuses to open and instructs a
  rebuild rather than migrating. `load_vectors` returns one contiguous float32 array with chunk ids
  in row order, and rejects any stored vector whose width disagrees with the manifest.
- Error pickling now preserves the exact subclass (I1 rebuilt through the base class, so an
  `except StoreError` across a process boundary would have missed it).
- **I5** — sidecars: `sidecar.py` reads, validates and writes `<file>.pnk.yaml` (DESIGN §2.2).
  Unknown keys round-trip untouched — the file belongs to the user, and normalising away their
  fields is data loss; `self` and alias links are resolved to ULIDs on read, so what reaches disk
  survives being shared; a hand-broken `id` errors with "restore the original", never a renumber.
  `find_duplicate_ids` reports every path claiming a shared id, for §6.4's hard error.
- Sidecar writes are atomic (write beside, then rename): a truncated sidecar would lose the
  document's permanent ULID and every inbound link with it.
- **I6** — chunking: `chunk.py` splits Markdown on headings and paragraphs (fenced code kept
  whole) and plain text on blank lines, counting tokens through a `TokenCounter` protocol so the
  logic is testable without model weights. Oversize text is split — sentences, then words, then
  characters for an unbroken run — **never trimmed**, and `assert_chunkable` refuses a `max_tokens`
  the model would have to truncate. Heading lines are included in their first chunk so heading-only
  words stay searchable, and every chunk satisfies `text == source[char_start:char_end]`.
- **I7** — backends: `embed.py` defines `EmbeddingBackend` and `Reranker` protocols behind open
  registries with lazy imports, so a core-only install never pulls torch and a missing backend fails
  naming the exact extra. sentence-transformers and fastembed implementations; fastembed is forced
  onto the shared `HF_HOME` cache rather than its `$TMPDIR` default, and `max_seq_length` is derived
  from the loaded tokenizer. `dim` disagreeing with the manifest is a hard error. Model-marked tests
  exercise real weights and skip when they are not cached.
- **I8a** — sync pairing: `pairing.py` implements DESIGN §6.4's two-phase algorithm as a pure
  function over two snapshots — no filesystem, no SQLite, no clock — returning actions for the sync
  driver to execute. Covers every row of the table plus the compound cases: adoption beats deletion
  so a rename+edit keeps its id and emits no delete; duplicate content is reported rather than
  guessed unless a sidecar breaks the tie; a sidecar disagreeing with the index wins, because
  `docs/` is the truth and the index is derived; one id in two sidecars raises rather than
  renumbering. Orphaned sidecars and moved-without-sidecar cases are reported, never acted on.
- **I8b** — `pnk sync` is real: walks the sources (never ingesting a sidecar as a document), runs
  §6.4 pairing, and applies each document in its own transaction so one unreadable file is recorded
  in `failures` and the run continues, exiting non-zero. `--rebuild` builds beside the index,
  checkpoints, closes, renames, and removes the old `-wal`/`-shm` — `ledger.jsonl` is never touched.
  `--sidecars-only [--stage]` is the pre-commit half (mints ids for staged files and `git add`s
  them); `--index-only` is the post-commit half and never writes into `docs/`. `sync.lock` records
  pid/host/start-time: a live holder means a quiet exit 0, a dead one is reclaimed with a warning,
  another host is refused with `--force-unlock`.
- **I9** — retrieval: `search.py` runs the §4.1 pipeline — metadata filters (tags from the sidecar
  metadata, path prefix, source type, mtime range), FTS5 BM25 with user text escaped so it can never
  be FTS syntax, NumPy cosine, RRF (k=60), optional local rerank, then the §4.2 confidence signal.
  Queries refuse to run against an index built by a different model. Confidence is `unknown` unless
  thresholds exist **and** `fitted_for` names the reranker actually in use; query-term coverage is a
  tiebreak, never a gate.
- **I10** — `pnk init` and `pnk search` are real. `init` stamps a KB from the packaged `notes`
  template (jinja2, `StrictUndefined`, so a template typo fails at render rather than becoming an
  empty manifest key), mints its permanent ULID, and writes the `.gitignore` that keeps the index
  and ledger off any remote. The template ships `[retrieval.confidence]` **commented out**:
  thresholds fitted on someone else's corpus are not a calibration. `search` runs the free pipeline
  with the full filter set, human or `--json` output, and an escalation note that names `pnk ask
  --deep` as *planned for v0.4* rather than implying it exists.
- pytest now treats warnings as errors, which immediately surfaced a deprecated
  `importlib.abc.Traversable` import and several leaked SQLite handles in the tests.
- **I11** — `pnk doctor`: environment (SQLite version, FTS5, loadable extensions), backend and
  weights, template drift, index coherence, calibration validity, orphaned sidecars, duplicate ids,
  dangling links and link coverage, recorded failures, the 50k-chunk NumPy-tier threshold, a held
  sync lock, and hook status. Every non-OK check carries a remedy. `--prune` is the only thing that
  changes anything, and it prints every path before removing it.
- **I12** — `pnk install-hooks` writes the §6.3 three-hook split: `pre-commit` mints ids for staged
  documents and stages the sidecars (so a document and its permanent id land in one commit),
  `post-commit`/`post-merge` update the index only and never dirty the tree. An existing hook that
  is not ours is left untouched and printed with the line to add; a hook that cannot find `pnk`
  warns and exits 0, because a hook that fails every commit only teaches `--no-verify`.
- **I13** — `pnk serve`: an MCP server exposing `pinakes_search`, `pinakes_get` and
  `pinakes_list_kbs`, namespaced so they cannot collide with another KB server an agent has loaded.
  It answers only about the KBs named on its command line; no tool argument accepts a filesystem
  path, and `pinakes_get` resolves a document ULID through the index. Passages come back inside a
  delimited evidence field stating they are text to reason about, never instructions to follow.
  Indexes are opened read-only and re-opened when a `stat()` shows the file was swapped.
- **I15** — CI (ruff, ty, pyright strict, pytest with warnings as errors, model-backed tests, a
  golden-set evaluation gated against the committed baseline, and a wheel smoke test that runs
  `pnk init` from the built artifact to prove templates are packaged), a release workflow that runs
  only on a `v*` tag and refuses one that disagrees with `__version__`, and the version moved to a
  single source of truth.
- **I14** — the scoreboard: a 30-document synthetic demo KB (invented institute, invented
  policies — nothing harvested), a 41-question golden set spanning lexical, paraphrase, filter,
  scripted multi-hop and no-answer cases, `pinakes.eval` (recall@k, MRR, rerank precision,
  false-abstain, false-confidence, confidence coverage, baseline comparison) and
  `pinakes.calibrate`, which prints a `[retrieval.confidence]` block and never writes one.
  Measured with the real `[light]` models: recall@5 0.879, MRR 0.774, rerank precision 0.727,
  **false-confidence 0.25** — the heuristic's real cost, now visible instead of assumed.
- Repository bootstrap: Apache-2.0 licence, `pyproject.toml` (uv, Python 3.13+, ruff, pyright
  strict, pytest), README, project conventions in `CLAUDE.md`, and a CLI stub that exits non-zero
  on every unimplemented command rather than implying it worked.
- `docs/DESIGN.md` — full architecture specification, reviewed across seven adversarial passes
  (58 findings resolved: 11 high, 32 medium, 15 low). Covers the KB directory format, SQLite schema,
  two-phase sync semantics, WAL concurrency policy, budget accounting by pre-call reservation,
  cross-KB linking via ULID-addressed sidecars, and the v0.1–v0.5 delivery plan.

- `plans/v0.1.md` (20260725 10:04) — implementation plan for the v0.1 vertical slice: 15 ordered
  increments (I1–I15) with per-increment tests and exit criteria, decisions table (argparse,
  jinja2-rendered manifests, `notes` template, open backend registry), and whole-slice acceptance
  checks. Adversarially reviewed across 5 passes, 28 findings resolved (3 high, 10 medium, 15 low).

### Changed

- Timestamp convention (20260725 13:49): every date in the CHANGELOG, design iteration log,
  retrospectives and "verified on" claims now carries `HH:MM` (local, 24h). Existing date-only
  stamps backfilled, and the four external claims in `docs/DESIGN.md` (sqlite-vec exhaustive KNN,
  fastembed's reranker registry, fastembed's `$TMPDIR` cache default, SQLite 3.53.1 + FTS5 +
  loadable extensions on uv-managed CPython 3.13) were **re-verified** at that time rather than
  having a time invented for them.

- Design pass 6 (implementation-readiness, 20260725 09:28): the local reranker moves from v0.5 into
  v0.1 with `BAAI/bge-reranker-base` as the default and a `[rerank]` manifest block; `pnk search`
  added explicitly to the v0.1 scope; git hooks split so `pre-commit` mints and stages sidecars
  while `post-commit`/`post-merge` touch only the index; `sync.lock` gains pid/host liveness with
  dead-lock reclaim and `--force-unlock`; the sidecar's redundant `content_hash` field is dropped.
- Design pass 7 (surfaced by the v0.1 plan review, 20260725 09:52): fastembed backend forced onto
  the shared `HF_HOME` cache (upstream defaults to `$TMPDIR`); `documents.sidecar_hash` added so
  sidecar-only edits re-index; soft delete now removes chunks/embeddings; rename+edit resolution
  stated (sidecar adoption wins over deletion).

**The v0.1 vertical slice is usable end to end**: `pnk init` → `pnk sync` → `pnk search`, plus
`pnk doctor`, `pnk install-hooks` and `pnk serve`, with a golden-set scoreboard and CI.

Measured on the demo KB with the `[light]` models: recall@5 0.879, MRR 0.774, rerank precision
0.727, false-abstain 0.03, **false-confidence 0.25**. That last number is the honest cost of the
confidence heuristic on a corpus of 30 documents and 8 no-answer questions — reported rather than
hidden, which is what §4.2 committed to.

Not in this release, by design: PDF ingest (v0.2), cross-KB links (v0.3), `pnk ask --deep` and the
budget ledger (v0.4), the `sqlite-vec` tier and template ecosystem (v0.5). Their schema ships now
where it could not be retrofitted — ULIDs, sidecars for every document, `[[links.kb]]`, `[budget]`.

[Unreleased]: https://github.com/lucagattoni/Pinakes/compare/v0.7.1...HEAD
[0.7.1]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.7.1
[0.7.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.7.0
[0.6.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.6.0
[0.5.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.5.0
[0.4.1]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.4.1
[0.4.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.4.0
[0.3.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.3.0
[0.2.2]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.2.2
[0.2.1]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.2.1
[0.2.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.2.0
[0.1.4]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.4
[0.1.3]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.3
[0.1.2]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.2
[0.1.1]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.1
[0.1.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.0
