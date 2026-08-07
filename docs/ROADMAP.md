# Roadmap — the whole story, in order

**Audience: a human catching up.** One page: what has shipped, in what order, why, and what is left.
Everything here is a *narrative view* over records that live elsewhere — it owns no fact of its own.

| If you want | Read |
|---|---|
| the authority on whether something is built | [STATUS.md](STATUS.md) |
| the full, exact record of a release | [CHANGELOG.md](https://github.com/lucagattoni/pinakes/blob/main/CHANGELOG.md) |
| what to build next, step by step | [`plans/`](https://github.com/lucagattoni/pinakes/tree/main/plans) |
| which file owns which fact | [docs/README.md](https://github.com/lucagattoni/pinakes/blob/main/docs/README.md) |
| this page | the shape of it all, without reading the other four |

**About the dates.** Timestamps up to **20260804 11:32 are local** (Europe/Rome); from there on they
are **UTC**. They are recorded as they were written and never converted — converting invents
precision nobody measured.

---

## Where things stand right now — 20260806 20:41 UTC

- **24 releases in 12 days.** [`0.1.0`](#010--the-engine--20260725-1527) on 20260725;
  [`0.15.1`](#0151--one-clock--20260806-0051) on 20260806.
- **Latest on PyPI: `0.15.1`.** Every release from `0.2.2` on is published
  ([STATUS § Published on PyPI](STATUS.md#published-on-pypi)).
- **Two of the four named releases have shipped** — the links release across
  [`0.5.0`](#050--links-you-can-walk--20260731-1127)–[`0.6.0`](#060--links-you-can-write--20260801-1051),
  the graph release in [`0.11.0`](#the-graph-release--shipped-0110). The deep and template releases
  are unbuilt.
- **The live question is whether document metadata is retrieval context**
  ([`plans/20260805_1721-metadata-as-retrieval-context.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260805_1721-metadata-as-retrieval-context.md)).
  Three of its four scheduled steps have shipped in
  [`0.13.0`](#0130--plain-text-can-carry-a-heading-path--20260805-2101)–[`0.15.0`](#0150--a-document-says-what-it-is-called--20260805-2248);
  **what remains is the injection experiment**, the measurement the investigation was opened to
  take. Its outcome decides whether the expensive downstream work — PDF layout heuristics, paid
  title inference — is arguable at all. **It is six increments, not one** (20260806): eight
  adversarial rounds re-scoped it, recorded every decision with its rejected alternatives, and
  measured six conditions that fail silently if missed, three of them since closed. **2a, 2b and 2c
  shipped 20260806, and none of it is released yet.** The corpus carries real titles and a measured
  token reserve; the code that builds a metadata prefix — and refuses one that would overrun the
  model's window rather than letting it be truncated in silence — exists but is **dormant**, wired
  into nothing until 2d; and the golden set is authored, frozen and calibrated, with its `before` leg
  captured (110 questions, improvable pool 15). It was written by authors who had not read this
  repository, before any injection code existed, so that no number could influence the questions.
  **2d is next**: a vector-only screen, run before the `schema_version` 4 bump because that bump is
  the only irreversible step in the plan.
- **[The graph release](#the-graph-release--shipped-0110) shipped — and its channel is `off`.**
  Blocked for three days on a *corpus*, not on code; the RFC corpus cleared the reachability
  precondition, and then the retrieval gate improved **0** multi-hop questions and regressed **3**
  (p = 1.0000). `schema_version` 3 means **every existing KB rebuilds once**.
- ⚠️ **`0.11.0`'s verdict is narrower than it reads** — three of the seven edge kinds derived
  **zero** edges on the corpus it was gated against. **0.12.0 ships the check that reports it**, so a
  future corpus cannot repeat it silently.
- **[The template release](#the-template-release--ready-to-start) is unblocked** — plan written,
  reviewed, four decisions taken. Nobody has started it; `main` has moved far enough that its
  Baseline block must be re-run before any `file:line` in it is trusted.
- **[No open corrections](#open-corrections--none-live)** — the list is empty for the first
  time since it opened on 20260731. It refills from *use*, so that means nobody has run Pinakes
  lately, never that it is finished.

---

## The table

Shipped releases first, oldest to newest. **Every release number links to its expanded section
below.** Rows with no number and no date are **not built** — the project's rule is that a version
number belongs to a release only when it is cut
([why](https://github.com/lucagattoni/pinakes/blob/main/CLAUDE.md), STATUS
[§ Release roadmap](STATUS.md#release-roadmap)).

| Release | Date | Title | What it is |
|---|---|---|---|
| **[0.1.0](#010--the-engine--20260725-1527)** | 20260725 15:27 | The engine | • ULIDs, sidecars, manifest, SQLite index<br>• `pnk init` / `sync` / `search`<br>• BM25 + vector + rerank, confidence signal<br>• Markdown and text only |
| **[0.1.1](#011--research-and-plumbing--20260727-1452)** | 20260727 14:52 | Research and plumbing | • 14 graph-RAG investigations under [`docs/graph/`](graph/README.md)<br>• `Makefile`, CI free-path gate<br>• No behaviour change |
| **[0.1.2](#012--the-readme-told-the-truth--20260727-1525)** | 20260727 15:25 | The README told the truth | • Four README claims contradicted the code<br>• `[light]` install path fixed |
| **[0.1.3](#013--the-first-retrospective--20260727-1540)** | 20260727 15:40 | The first retrospective | • What v0.1 taught ([RETROSPECTIVES.md](RETROSPECTIVES.md))<br>• Three rules promoted into `CLAUDE.md` |
| **[0.1.4](#014--the-pdf-build-order--20260727-2119)** | 20260727 21:19 | The PDF build order | • `plans/…-v0.2.md`, I1–I9<br>• Four adversarial review passes before any code |
| **[0.2.0](#020--pdfs-free-path--20260728-1405)** | 20260728 14:05 | PDFs, free path | • `pypdfium2` extractor + layout pipeline<br>• 19-fixture synthetic PDF corpus<br>• Extraction cache, page provenance<br>• `[pdf]` / `[claude]` extras |
| **[0.2.1](#021--one-fact-one-home--20260728-1654)** | 20260728 16:54 | One fact, one home | • `docs/` restructured: [GUIDE](GUIDE.md), [CLI](CLI.md), [MANIFEST](MANIFEST.md), [STATUS](STATUS.md)<br>• Three stale claims fixed |
| **[0.2.2](#022--the-silent-skip-named--20260728-1849)** | 20260728 18:49 | The silent skip, named | • A file matching no `include` glob is now reported<br>• Budget core lands, inert |
| **[0.3.0](#030--it-can-spend-money--if-you-ask--20260729-0417)** | 20260729 04:17 | It can spend money — if you ask | • Paid Claude-vision extractor for scanned PDFs<br>• Ledger, caps, reservation/reconciliation<br>• Paid-path allowlist + four gates<br>• [`pnk budget`](CLI.md#pnk-budget) |
| **[0.4.0](#040--citing-a-page--20260729-0532)** | 20260729 05:32 | Citing a page | • `docs/paper.pdf:p7` citations, CLI and MCP<br>• [`pnk doctor`](CLI.md#pnk-doctor) text-yield check<br>• [VERIFICATION.md](VERIFICATION.md) + its gate |
| **[0.4.1](#041--the-sidecar-that-ate-itself--20260729-0748)** | 20260729 07:48 | The sidecar that ate itself | • A sidecar that would not parse was overwritten by a fresh one — losing a permanent ULID<br>• Data-loss bug live since v0.1 |
| **[0.5.0](#050--links-you-can-walk--20260731-1127)** | 20260731 11:27 | Links you can walk | • [`pnk links`](CLI.md#pnk-links) + `pinakes_links` traversal<br>• Reverse-scan of partner KBs<br>• Second synthetic corpus<br>• `ruamel.yaml`: sidecars round-trip properly |
| **[0.6.0](#060--links-you-can-write--20260801-1051)** | 20260801 10:51 | Links you can write | • [`pnk link`](CLI.md#pnk-link) authors a link<br>• `pnk doctor` reports link coverage as a ratio<br>• `[kb] requires_pinakes`<br>• Retrieval made deterministic |
| **[0.7.0](#070--the-measurement-that-said-no--20260801-1240)** | 20260801 12:40 | The measurement that said no | • Per-question eval artifact, stable ids<br>• Golden set 41 → 74 questions<br>• **Deliverable was a number: [the gate could not be reached on the demo KB](STATUS.md#can-the-graph-releases-gate-be-reached--yes-measured-20260804)** — the RFC corpus cleared it on 20260804 |
| **[0.7.1](#071--the-walk-stays-in-the-kb--20260801-1342)** | 20260801 13:42 | The walk stays in the KB | • `[sources] include` could escape the KB and mint sidecars outside it<br>• Three defects, all live before 0.5.0 |
| **[0.8.0](#080--our-key-not-the-sdks--20260804-0840)** | 20260804 08:40 | Our key, not the SDK's | • **Breaking (paid path):** `PINAKES_ANTHROPIC_API_KEY`, no fallback<br>• Budget defaults raised<br>• STATUS header pinned by a gate<br>• 16 doc claims corrected |
| **[0.9.0](#090--a-site-and-a-name--20260804-1228)** | 20260804 12:28 | A site, and a name | • Docs published to a MkDocs site<br>• 31 dead links found and fixed<br>• Repo renamed → project is **Pinakes**<br>• ⚠️ First upload **refused** — the rename broke trusted publishing; [since fixed](STATUS.md#published-on-pypi) |
| **[0.10.0](#0100--you-can-see-it-working--20260804-1335)** | 20260804 13:35 | You can see it working | • `pnk sync` shows live progress on a terminal<br>• `pnk doctor` no longer tells an interrupted sync to `--rebuild`<br>• Sync timestamps are UTC<br>• ✅ Released and on PyPI |
| **[0.11.0](#the-graph-release--shipped-0110)** | 20260805 07:14 | The graph release | • Structural edges at `schema_version` 3 — **every existing KB rebuilds once**<br>• `pnk doctor` reports the highest-degree hubs<br>• **The expansion channel ships `off`** — its gate improved 0 and regressed 3 |
| **[0.12.0](#0120--the-check-that-would-have-caught-it--20260805-1802)** | 20260805 18:02 | The check that would have caught it | • `pnk doctor` reports heading-path coverage<br>• Missing-backend error names an installed alternative<br>• `pnk doctor` stops printing `$HOME`<br>• `tools/measure_sync_cpu.py` |
| **[0.13.0](#0130--plain-text-can-carry-a-heading-path--20260805-2101)** | 20260805 21:01 | Plain text can carry a heading path | • `[chunking] headings = "numbered"`<br>• Measured on 980 real RFCs, 314/314 modern<br>• A `[chunking]` edit is no longer a silent no-op<br>• `tools/build_rfc_corpus.py` |
| **[0.14.0](#0140--the-tool-stops-crying-wolf--20260805-2222)** | 20260805 22:22 | The tool stops crying wolf | • Heading coverage WARNs only for `markdown` at 0%<br>• `pnk init` adopts a directory with content<br>• A `titles` nudge, never a warning<br>• The sync loop stays serial — measured |
| **[0.15.0](#0150--a-document-says-what-it-is-called--20260805-2248)** | 20260805 22:48 | A document says what it is called | • A Markdown `# ` heading becomes the title<br>• Fence-aware, `##` excluded, Markdown only<br>• No migration — existing titles are never rewritten |
| **[0.15.1](#0151--one-clock--20260806-0051)** | 20260806 00:51 | One clock | • The last three naive-local timestamps are UTC<br>• `pnk init`'s `created`, the paid extractor's pricing, `doctor`'s price age<br>• Pinned by a test running at UTC+14<br>• `CLAUDE.md` 273 → 191 lines, into two new documents |
| | | **[Open corrections](#open-corrections--none-live)** | • None live — first time since 20260731<br>• **Every one** came from *building* the RFC corpus, not from reading code<br>• None blocking |
| | | **[The graph release, staged](#the-graph-release-staged--gates-only-not-scheduled)** | • PPR channel, the `[ner]` extra<br>• Gate-only: no implementation plan exists, by design<br>• Not scheduled |
| | | **[The deep release](#the-deep-release)** | • `pnk ask --deep` — the budgeted agentic loop<br>• Only paid entry point still unbuilt |
| | | **[The template release](#the-template-release--ready-to-start)** | • Template ecosystem, `pnk upgrade`, `sqlite-vec` tier<br>• ✅ Plan written and reviewed, decisions taken<br>• Not started |

---

# Part 1 · The engine — `0.1.x`

Five releases in three days. One of them shipped code.

## 0.1.0 — The engine · 20260725 15:27

Ten increments, all at once, because there was nothing to be incremental against yet.

**What it gave you**

- [`pnk init`](CLI.md#pnk-init) — stamps a KB from a template, mints its permanent ULID.
- [`pnk sync`](CLI.md#pnk-sync) — walks your documents, mints a sidecar per file, builds
  `.pinakes/index.db`.
- [`pnk search`](CLI.md#pnk-search) — BM25 + vector cosine + RRF fusion + optional local rerank.
- [`pnk serve`](CLI.md#pnk-serve) — MCP surface for an agent.

**The decisions that never changed after this**

- **Your documents are the truth; the index is derived.** `.pinakes/` is disposable
  ([DESIGN § 2](DESIGN.md#2-anatomy-of-a-kb), [§ 3](DESIGN.md#3-storage)).
- **ULIDs are permanent.** Never renumbered, never regenerated, no migration machinery — ever.
- **Unknown manifest keys are a hard error**, not a silent default
  ([MANIFEST.md](MANIFEST.md), [DESIGN § 2.1](DESIGN.md#21-the-manifest--pinakestoml)).
- **An error carries a remedy**, not just a message.
- **Exit codes are a contract**: 0 success, 1 operational failure, 2 usage error
  ([CLI § Exit codes](CLI.md#exit-codes)).

**What it could not do:** PDFs, links, spending money.

→ The pipeline itself: [DESIGN § 4.1](DESIGN.md#41-the-free-pipeline-every-query-0). The sync
algorithm that keeps a KB from corrupting:
[DESIGN § 6.4](DESIGN.md#64-sync-semantics-the-part-that-silently-corrupts-a-kb-if-left-vague).

## 0.1.1 — Research and plumbing · 20260727 14:52

No behaviour change — the wheel's code is identical to [`0.1.0`](#010--the-engine--20260725-1527).

- **~3,000 lines of graph-RAG research** landed under [`docs/graph/`](graph/README.md): LightRAG,
  Microsoft GraphRAG, Graphiti, HippoRAG 2, fast-graphrag, Graph-R1, LinearRAG, MiniRAG and more,
  plus [`PINAKES_APPROACH.md`](graph/PINAKES_APPROACH.md) synthesising them into a gated build order.
  Six adversarial passes (27 → 7 → 8 → 5 → 1 → 0 findings).
- **A `Makefile`** where every target wraps what CI actually runs.
- **The free-path CI gate** — promised in the v0.1 plan and never shipped, because the item sat in a
  section no increment owned.

→ What the literature actually supports: [graph/GRAPH_RAG.md](graph/GRAPH_RAG.md). Three of those
projects **may never be copied from** for licence reasons — flagged in
[graph/README.md](graph/README.md).

## 0.1.2 — The README told the truth · 20260727 15:25

An audit against the shipped CLI found the README was the only surface overclaiming.

- `pnk ask --deep` was described as existing. It [does not, to this day](#the-deep-release).
- Install lines pointed at a PyPI package that returned 404.
- The headline diagram showed a `.pdf` — the one file type v0.1 could not read.

This is where the rule *"verify docs by running the commands they show"* comes from. The
`[light]`-install trap it found is
[still a caveat](STATUS.md#caveat-the-light-backend-needs-a-manifest-edit) today, and the
[GUIDE](GUIDE.md#choosing-a-backend) leads with it.

## 0.1.3 — The first retrospective · 20260727 15:40

Findings from v0.1, and three rules promoted into `CLAUDE.md`:

- Verify a release the way a stranger would — `git tag -l`, `gh release list` — never by believing
  the CHANGELOG. (The [procedure](RELEASING.md) grew out of this.)
- **Never `git merge` from inside the feature worktree.** Three commands report success and nothing
  lands.
- The README describes what ships, checked by running it.

→ Every finding since: [RETROSPECTIVES.md](RETROSPECTIVES.md).

## 0.1.4 — The PDF build order · 20260727 21:19

- [`plans/20260727_1543-v0.2.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260727_1543-v0.2.md)
  — I1–I9, reviewed over **four adversarial passes** before a line was written.
- The *read the clock, never compose a timestamp* rule, after four invented `HH:MM` stamps landed in
  the future.

---

# Part 2 · PDFs, and the first money — `0.2.0` → `0.4.1`

## 0.2.0 — PDFs, free path · 20260728 14:05

Five increments (I1–I5) — [the ledger](STATUS.md#v02-increment-ledger).

- **The extractor seam** — a protocol plus a lazy registry, so core stays torch-free and
  extractor-free. `[pdf]` and `[claude]` become opt-in extras.
- **A synthetic hard-case PDF corpus** — 19 committed fixtures across seven strata (two-column,
  tables, running heads, ligatures, scanned, pathological, baseline). Ground truth is hand-written
  from each fixture's *spec*, never from an extractor's output, which would only prove an extractor
  agrees with itself.
- **The layout pipeline** — characters → blocks → columns → reading order, with running-head
  suppression and hyphenation joining. No PDF library, no filesystem.
- **The extraction cache**, and page provenance in the index.

→ How to actually index a PDF: [GUIDE § Indexing PDFs](GUIDE.md#indexing-pdfs) — **and note it is
[off by default](STATUS.md#caveat-pdfs-are-off-by-default-but-no-longer-silently)**, which
[`0.2.2`](#022--the-silent-skip-named--20260728-1849) is about. Quality methodology:
[DESIGN § 7.1](DESIGN.md#71-pdf-extraction-quality).

## 0.2.1 — One fact, one home · 20260728 16:54

The docs were restructured for continuous development: landing an increment should edit **one** file.

- New: [`GUIDE.md`](GUIDE.md), [`CLI.md`](CLI.md), [`MANIFEST.md`](MANIFEST.md),
  [`STATUS.md`](STATUS.md),
  [`docs/README.md`](https://github.com/lucagattoni/pinakes/blob/main/docs/README.md).
- **[`STATUS.md`](STATUS.md) becomes the only place in the repo that says what is built.**
- [`DESIGN.md`](DESIGN.md) becomes rationale only. README becomes deliberately **version-free**, so
  it cannot drift again.

→ The routing table this produced — *where does a fact live* — is in
[docs/README.md](https://github.com/lucagattoni/pinakes/blob/main/docs/README.md), and it is what
tells you which file to edit when something lands.

## 0.2.2 — The silent skip, named · 20260728 18:49

[`0.2.0`](#020--pdfs-free-path--20260728-1405) shipped PDF ingest as its headline feature while the
template stamped `include = ["**/*.md", "**/*.txt"]`. So the real first-run experience was: drop in a
PDF, run sync, read `0 indexed`, get no hint why.

- **`pnk sync` now names what it skipped**, grouped by extension, with the exact glob to add.
- Only files Pinakes *could* index are reported — a wrong hint is worse than none.
- **The budget core lands, inert**: pure logic, nothing calls it, so nothing can spend.

An adversarial review found seven more defects in the fix itself, two of which handed the silence
straight back. This release is also where the **mutation-testing rule** was adopted: break the guard
on purpose, watch the right test fail, restore.

→ The gap that remains: a template change reaches **new KBs only**, so a KB created before this one
never sees the explanation. That is
[KB-UPDATES § 3](KB-UPDATES.md#3-the-gap-is-live-not-theoretical), and closing it is
[the template release](#the-template-release--ready-to-start).

## 0.3.0 — It can spend money — if you ask · 20260729 04:17

The first release with a paid code path. Four increments (I6a–I7c);
[why it was held until then](STATUS.md#cut-as-030--20260729-0417).

**What can spend, and only this**

- `pnk sync` with `[extraction] backend = "claude-vision"`, or `--extract=claude-vision`.
- Nothing else. Ever. It is an **enumerated allowlist** (`.paid-path-allowlist`), held by four gates
  — the decisive one runs the whole free path in a fresh subprocess and asserts no paid client ever
  reached `sys.modules`.

**What stands behind the money**

- Every call reserved before it is made, reconciled from the response's own usage.
- Caps that **refuse** rather than overspend. An append-only ledger; a correction is another record.
- Every free check runs before any paid one — including refusing a PDF whose text layer is already
  healthy.

**Measured live, 20260729, for €0.43** —
[the run](STATUS.md#the-measurement-run-has-been-done--20260729-0317-043)

| | Result |
|---|---|
| Scanned-PDF quality, paid path | **1.000** on every metric |
| Same, free path | **0.000** |
| Reservation accuracy | Over-reserved **11.5×** — wrong in the safe direction |
| The refusal branch | Fired for real, on a real document |

→ The design: [DESIGN § 5 Cost control](DESIGN.md#5-cost-control). The trade-off measured:
[DESIGN § 7.2](DESIGN.md#72-what-bypassing-layoutpy-on-the-paid-path-actually-costs). Day-to-day:
[GUIDE § Watching what it costs](GUIDE.md#watching-what-it-costs) and
[`pnk budget`](CLI.md#pnk-budget). To re-run the measurement yourself:
[MEASUREMENT-RUN.md](MEASUREMENT-RUN.md).

## 0.4.0 — Citing a page · 20260729 05:32

- **`path:page` citations** — `docs/paper.pdf:p7`, or `:p7-8` across a page break, on the CLI and MCP
  alike. The `p` is deliberate: `:12-480` already meant character offsets.
- **[`pnk doctor`](CLI.md#pnk-doctor) text yield** — reports pages below the fitted floor **per page,
  not per document**, because a 200-page report with eight scanned inserts is exactly the document
  worth knowing about.
- **[VERIFICATION.md](VERIFICATION.md)** — every promise, and the test that holds it, with a gate
  asserting each named test exists. It replaced the v0.2 plan's table, **61 of whose 98 test
  references did not resolve**.

→ Why offsets address the *extraction* and not the file:
[DESIGN § 4.6](DESIGN.md#46-chunking-and-tokens).

## 0.4.1 — The sidecar that ate itself · 20260729 07:48

A patch, but the most serious bug the project has had.

- A sidecar that failed to parse was dropped from the walk. The document then looked new. The mint
  path wrote a **fresh sidecar over it** — destroying its permanent ULID and every authored link.
- `pnk sync` reported success. `pnk doctor` afterwards reported everything healthy, because the
  evidence had been overwritten by the thing that destroyed it.
- **Present since v0.1.** `0.4.1` is the first release without it.

→ **`0.4.0` and earlier can still do this** — never pin one
([STATUS § Published on PyPI](STATUS.md#published-on-pypi)). The pairing algorithm it broke:
[DESIGN § 6.4](DESIGN.md#64-sync-semantics-the-part-that-silently-corrupts-a-kb-if-left-vague).

---

# Part 3 · Links — `0.5.0` → `0.7.1`

The links release was deliberately cut **twice**: an interim MINOR once the traversal surface worked,
and a final one once authoring landed. The design it implements is
[DESIGN § 6.2 Cross-KB links](DESIGN.md#62-cross-kb-links); the build order is
[`plans/20260729_0256-links-and-graph.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260729_0256-links-and-graph.md).

## 0.5.0 — Links you can walk · 20260731 11:27

- **[`pnk links`](CLI.md#pnk-links)** — what a document connects to and what connects to it. Depth
  capped at 3 server-side, fan-out capped, no query language, ever.
- **`pinakes_links`** on the MCP surface — the same traversal, for the agent this project calls its
  primary caller.
- **Reverse-scan** — `pnk sync` reads a partner KB's *committed sidecars* (never its index) and
  records what links into this one.
- **A second synthetic corpus** (`tests/partner-kb`, 21 documents) and a gate keeping both corpora
  sparse.
- **`ruamel.yaml` replaces `pyyaml`.** Comments, quoting and blank lines now survive a rewrite — and
  a silent corruption stops: under YAML 1.1 `country: NO` was read as `False` and written back as
  `false`.

**A cross-KB neighbour is terminal at any depth.** This KB holds a partner's links pointing *back*
at it, never the partner's internal ones — so expanding through one shows a systematically
incomplete slice no caller could distinguish from the whole.

→ Walk two KBs yourself:
[GUIDE § Following links between two KBs](GUIDE.md#following-links-between-two-kbs). The round-trip
guarantee and its **bounds**: [MANIFEST.md](MANIFEST.md) and [VERIFICATION.md](VERIFICATION.md). Why
ruamel:
[the decision record](https://github.com/lucagattoni/pinakes/blob/main/plans/20260731_0602-decision-ruamel-yaml.md).

## 0.6.0 — Links you can write · 20260801 10:51

- **[`pnk link <source> <target> --rel REL`](CLI.md#pnk-link)** — writes one entry into the source
  document's own sidecar and nothing else. Aliases and `self` are resolved to ULIDs **before**
  anything reaches disk, which is what makes a link mean the same thing on someone else's machine.
- **It never mints a sidecar.** A source without one is refused, with `pnk sync` as the remedy.
- **`[kb] requires_pinakes`** — a manifest can declare the oldest Pinakes that can read it, so an
  out-of-date build says so instead of reporting a typo.
- **Retrieval made deterministic.** Every tiebreak resolved to the SQLite rowid, which the schema
  says has no identity across rebuilds — so two indexes over identical sources could answer
  differently. Measured: 1 question in 41 moved. Ordering is now total; **no scored number changed**,
  which is what a tie-break-only fix should do.

→ The full reproducibility measurement:
[STATUS § Is the evaluation reproducible?](STATUS.md#is-the-evaluation-reproducible--measured-20260801-0035).
What `requires_pinakes` does and does not close:
[KB-UPDATES § 4](KB-UPDATES.md#4-compatibility-posture).

## 0.7.0 — The measurement that said no · 20260801 12:40

**This release's deliverable is a number, not a feature.**

The graph release turns its expansion channel on only if enough multi-hop questions *improve*. An
improvement can only come from a question that fails today.

| | Required | Measured |
|---|---|---|
| Multi-hop questions failing today | ≥ 7 | **1** |
| Of those, reachable without authored edges | ≥ 7 | **1** |

**So [the graph release](#the-graph-release--shipped-0110) stopped here.** No
`schema_version` bump, no forced rebuild for every KB in existence, for an edge table whose channel
could never be licensed.

Two findings behind that number, both of which outlive it:

- **`tests/demo-kb` has no tags and one flat directory** — so exactly *one* derived edge kind can
  cross a document boundary. Any result on this corpus is a claim about one directory.
- **The retrieval funnel already sees the whole corpus.** 30 candidates against ~30 chunks. A failing
  question here is a *ranking* failure, not a recall failure a channel could fix.

Also shipped: per-question eval outcomes as a committed artifact, stable question ids, and the golden
set grown 41 → 74 with a `simple-lookup` control class.

→ The full measurement, with every figure:
[STATUS § Can the graph release's gate be reached?](STATUS.md#can-the-graph-releases-gate-be-reached--yes-measured-20260804).
Current retrieval scores: [STATUS § Measured numbers](STATUS.md#measured-numbers). The multi-hop
design being tested: [DESIGN § 4.3](DESIGN.md#43-multi-hop-without-paying-for-it).

## 0.7.1 — The walk stays in the KB · 20260801 13:42

`roots` had to stay inside the KB. `include` was validated nowhere.

- A `..` pattern **indexed files outside the KB and minted sidecars beside them**.
- An absolute pattern produced a bare traceback with no remedy.
- A **symlinked directory** carried the walk out with no `..` and no absolute path anywhere.

All three live since before [`0.5.0`](#050--links-you-can-walk--20260731-1127). `pinakes.toml` is
committed and shared — cloning a KB and running sync ran *its author's* `include` against *your*
tree.

→ The increment:
[`plans/20260731_2128-source-walk-containment.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260731_2128-source-walk-containment.md).
The field it hardened: [MANIFEST.md](MANIFEST.md).

---

# Part 4 · Hardening and publishing — `0.8.0` → `0.10.0`

## 0.8.0 — Our key, not the SDK's · 20260804 08:40

**Breaking, for anyone running the paid extractor.**

- `anthropic.Anthropic()` was constructed without `api_key`, so the SDK read `ANTHROPIC_API_KEY` out
  of whatever environment it was handed. On a machine where any other tool exports it, the paid path
  had **a live key nobody aimed at it**.
- The variable is now `PINAKES_ANTHROPIC_API_KEY`, passed explicitly, with **no fallback** — a
  fallback would restore the whole defect silently.
- Budget defaults raised: `per_operation_eur` 0.05 → 0.30, `monthly_eur` 5.00 → 30.00. The old
  per-operation cap admitted **zero** rounds of any multi-call paid operation.
- A gate now pins [STATUS.md](STATUS.md)'s own header to `__version__` — it had drifted for four
  consecutive releases while every table below it was updated.
- **Sixteen documentation claims corrected** against the code, including the GUIDE saying twice that
  *"nothing here spends money, and nothing can"* three lines below the row instructing
  `--extract=claude-vision`.

→ The defaults and their validation: [MANIFEST.md](MANIFEST.md). What actually bounds spend:
[DESIGN § 5](DESIGN.md#5-cost-control) and [MEASUREMENT-RUN.md](MEASUREMENT-RUN.md).

## 0.9.0 — A site, and a name · 20260804 12:28

**Documentation only — no code path changed.**

- **[lucagattoni.github.io/pinakes](https://lucagattoni.github.io/pinakes/)** — MkDocs Material over
  the existing `docs/`, deployed on every push to `main`, built `--strict` on every PR. The strict
  build found and fixed **31 dead links and anchors**.
- Nothing in `docs/` moved: those filenames are load-bearing in code.
- **The project is `Pinakes`; everything you can type is `pinakes`.** The repository moved to
  [github.com/lucagattoni/pinakes](https://github.com/lucagattoni/pinakes). No identifier changed.

⚠️ **And then the upload was refused — 20260804 12:33. It is fixed; 0.9.0 is on PyPI.**

- Renaming the repository broke PyPI **trusted publishing**, which matches on the exact repository
  name. The OIDC token claimed `repository: lucagattoni/pinakes` while the registered publisher
  still said `Pinakes`, so PyPI answered *"valid token, but no corresponding publisher"*.
- **Nothing had been uploaded**, so the version was never burned — the same tag published once a
  project owner corrected the publisher on pypi.org and the failed job was re-run.
- **This is the release that taught the project how a good publish hides.** Three separate caches
  each said the upload had failed when it had not: the JSON endpoint still named `0.8.0` an hour
  later; `/simple/` listed no file **even cache-busted**; and `uvx --refresh` answered
  *unsatisfiable* from uv's own cache until `--no-cache`. What settles it is the workflow's
  `Publish to PyPI` log, which prints one `Uploading …` line per file and cannot be cached.
- The direction matters: a false *"it did not publish"* invites re-cutting a version PyPI will
  never accept twice.

→ The standing record: [STATUS § Published on PyPI](STATUS.md#published-on-pypi). The verification
step this rewrote: [RELEASING.md](RELEASING.md). Working install lines:
[GUIDE § Install](GUIDE.md#install).

## 0.10.0 — You can see it working · 20260804 13:35

✅ **Released and published** — tagged `v0.10.0`, on PyPI at 20260804 13:39 UTC.

- **`pnk sync` shows live progress on a terminal.** A CPU-only embedding run measured at ~2.4
  documents/minute — 300 documents ran over **two hours with nothing printed**, making a slow sync
  and a hung one look identical. One self-overwriting line, throttled to ~1/second, only on a real
  tty and only without `-q`.
- **[`pnk doctor`](CLI.md#pnk-doctor) no longer tells an interrupted first sync to `--rebuild`** — a
  remedy that would discard every embedding the interrupted run had already written. It now says
  `pnk sync`, which continues incrementally.
- **Sync timestamps are UTC**, matching the lock's. They disagreed by the local offset, in the one
  place a user weighs before `--force-unlock`ing a possibly-live sync.
- The GUIDE's first install command **did not work in a bare directory** (`uv add` needs a
  `pyproject.toml`; a KB has none), and troubleshooting offered only the destructive lock remedy.

→ [GUIDE § Install](GUIDE.md#install) and [GUIDE § Troubleshooting](GUIDE.md#troubleshooting) carry
the corrected text. The locking model: [DESIGN § 6.5 Concurrency](DESIGN.md#65-concurrency).

---

## 0.12.0 — The check that would have caught it · 20260805 18:02

- **[`pnk doctor`](CLI.md#pnk-doctor) reports what share of chunks carry a heading path, and warns
  when a whole source type carries none.** The RFC realism corpus indexed **106 806 chunks with not
  one heading path** and nothing said so — and that is what bounds 0.11.0's expansion-channel gate:
  `in-section`, `parent` and `child` all derive from `heading_path`, so **three of the seven edge
  kinds derived zero edges on the corpus the gate was measured against**. A graph result on such a
  corpus reads as *"structure does not help"* when what it measured is *"the structure was never
  extracted"*.
- **The missing-backend error names an installed alternative** instead of prescribing the ~2 GB
  `sentence-transformers` install to someone who deliberately chose `[light]`. It checks with
  `find_spec` and never by loading the backend — a check must not have the side effects of the thing
  it checks.
- **`pnk doctor` no longer prints the operator's home directory**, in the one command whose output
  is the natural thing to paste into an issue. A path genuinely outside the KB is left as printed.
- **`tools/measure_sync_cpu.py`** — the cores-busy instrument the open sync-CPU item requires before
  anything about that loop may change. **The measurement itself has not been taken.**

Two of the three retrospectives this release earned are about tests rather than code, and both are
the same defect wearing different clothes: an assertion that was satisfied by something other than
the property it named. The sampler watched the launched pid, so `-- uv run pnk sync` measured `uv`
and would have reported **0.0 cores for a saturated core** — not a broken-looking number, a
finding-looking one. And a test comparing two *differently rounded* renderings of one value passed
locally and on two CI legs, failing only on the third.

→ [RETROSPECTIVES.md](RETROSPECTIVES.md) carries all three.

---

## 0.13.0 — Plain text can carry a heading path · 20260805 21:01

- **`[chunking] headings = "numbered"`** reads a dotted-decimal outline (`1.`, `1.1.`, `2.`) into
  `heading_path` for the `text` source type. Opt-in and off by default. Until now every type but
  `markdown` recorded no `heading_path` at all — which is what left a 300-RFC corpus with 106 806
  chunks and none, and so bounds [0.11.0's gate](#the-graph-release--shipped-0110): `in-section`,
  `parent` and `child` all derive from it and derived **zero** edges there.
- **It refuses rather than guesses.** `1.` at line start is also an ordered list, so acceptance is
  decided over the whole document, and a document whose outline does not walk cleanly yields **no**
  headings rather than a partial labelling. The floor is therefore exactly the previous behaviour.
- **Measured against 980 real RFCs**, in rounds that doubled each time and re-ran every earlier fix:
  644 accepted, and **314 of 314 modern-era documents — 100% at every round size**. Two thirds of
  all rejections are documents with no numbered sections at all.
- **A `[chunking]` edit is no longer a silent no-op.** An incremental sync re-chunks a document only
  when the document changed, so editing any `[chunking]` key applied nothing and said nothing. The
  index now records what it was built under; `pnk sync` names the key that moved and
  [`pnk doctor`](CLI.md#pnk-doctor) reports `chunking coherence`.
- **`tools/build_rfc_corpus.py`** builds the realism corpus from a script instead of one machine.

The release's three retrospectives are all the same shape: something reported success while the
thing it named had not happened. A guard that could not fire. A warning that cleared itself without
the fix being applied. And two plausible predicate rules that the corpus refused — each removed a
false positive and took genuine documents with it.

→ [RETROSPECTIVES.md](RETROSPECTIVES.md), and the measurement in
[§5.4](https://github.com/lucagattoni/pinakes/blob/main/plans/20260805_1721-metadata-as-retrieval-context.md).

---

## 0.14.0 — The tool stops crying wolf · 20260805 22:22

Three changes with one theme: **a signal nobody can act on is worse than no signal**, because it
teaches the reader to skip the ones that matter.

- **[`pnk doctor`](CLI.md#pnk-doctor)'s heading coverage WARNs only for `markdown` at 0%** — the one
  case a user can fix. A KB holding a single `.py` file used to warn on every run forever, with a
  remedy amounting to *"a limit of the tool"*. The rest is reported OK with a note that separates
  three facts previously wearing the same 0%: `text` *can* carry a heading path, `text` with the
  grammar already on means those documents were **offered and refused**, and `code`/`pdf` cannot
  today.
- **[`pnk init`](CLI.md#pnk-init) adopts a directory that already has content.** Cloning a repo and
  initialising inside it is how a KB actually starts, and a `.git`, a `README.md` and a
  `pyproject.toml` made that *"not empty"*. The blanket refusal is gone; what replaces it is
  narrower and stronger — **init never overwrites a file that is already there**. An adopted
  `.gitignore` missing `.pinakes/` is flagged with the line to add, because that directory holds
  the index and the spend ledger.
- **A `titles` check** counts documents still carrying the title minted from their filename — the
  `title: rfc9110` problem. A nudge, never a warning: both committed corpora are at 100%, and the
  filename fallback is deliberate. Inference stays rejected — an RFC's first line is
  `Internet Engineering Task Force (IETF)`.

**And one question closed by measuring instead of arguing.** The first sync was suspected of using
one core of ten. It uses **five**: peak 5.0, mean 4.8, over 55 RFCs and 16 557 chunks under
`fastembed`. The loop is serial and the backend beneath it is not, so the document loop **stays
serial** — a pool sized `os.cpu_count() - 1` would have been nine workers where there was room for
two. The instrument proved itself in the same run: `uv run` sat at 0.0% while its child sustained
491.9%, which is exactly the 0.0-cores answer the pre-fix tool would have reported and nobody would
have questioned.

→ [RETROSPECTIVES.md](RETROSPECTIVES.md).

---

## 0.15.0 — A document says what it is called · 20260805 22:48

- **A Markdown document is titled by its own `# ` heading.** `rfc9110-notes.md` opening on
  `# HTTP Semantics` is now titled *HTTP Semantics* rather than *"rfc9110 notes"*.

**This began as a correction, not a feature.** The record said `sync` mints from the filename *"when
the document has no Markdown H1"* — implying it read one otherwise. It never did: `skeleton()` was
called without `title=` at both call sites, and `title=` appeared nowhere in `sync.py`. The claim
survived because the two forms usually differ only in capitalisation — `# Access restrictions`
sitting beside `title: access restrictions` reads exactly as though the heading was used, when the
value is the stem with its hyphens swapped for spaces.

That is the same shape as the chunking diagnosis corrected in 0.13.0: **a fallback described for a
mechanism that was never running.** Both were found by checking what the code does rather than what
the note says.

An H1 is structure, not inference — which is what keeps this distinct from the first-line heuristic
that remains rejected, since an RFC's first line is `Internet Engineering Task Force (IETF)`.
Markdown only, fence-aware, `##` excluded. **No migration:** titles are minted only when a sidecar
is created, so every existing KB keeps what it has, and `title` stays the user's field.

---

## 0.15.1 — One clock · 20260806 00:51

- **Every timestamp Pinakes writes is UTC.** The last three naive-local sites are gone: `pnk init`
  stamped `[kb] created` from the machine's wall clock, the paid extractor priced a document against
  a local `now`, and `pnk doctor`'s price-age check subtracted a naive local clock from a price
  table whose `as_of` is authored in UTC.

**A mixed scheme is worse than a consistent local one**, which is why this is a fix and not a
tidy-up. `sync`, `lock`, the ledger and the accountant were already UTC, so the three remaining
sites meant two stamps written into the same index no longer shared a zero point. None of them
failed loudly: a KB minted in Europe and read in California simply disagreed about when it was made.
`is_stale()` was the same defect one layer up — the code compared a UTC value correctly while its
docstring said local, a mismatch invisible on a UTC machine and silent everywhere else.

**Pinned by a test that fails on a naive clock, not merely on a wrong one.** It runs under
`TZ=Pacific/Kiritimati` — UTC+14, chosen because the naive stamp lands on a *different date* for ten
hours of every day, so the failure is loud rather than a rounding minute.

**`[budget] timezone` is untouched and is not an exception.** It decides where a *daily* or
*monthly* window starts for a user who wants their cap to reset at local midnight; the ledger still
stores UTC and converts at read time, so no local time is ever written to disk.

Also documentation, in the same release: `CLAUDE.md` went from 273 lines to 191, with the increment
procedure moving to [`BUILDING.md`](BUILDING.md) and the silently-failing contracts to
[`INVARIANTS.md`](INVARIANTS.md). **INVARIANTS is an index, not a copy** — eight of its nine facts
already had owners, so each row links its owner and only the five rules nothing else states are
written out. The relocation's real cost was its **pointers**: 21 references across the tree named
`CLAUDE.md` for content that had moved, and 13 of them sat in `src/` and `tests/`, which a
docs-only change does not look like it touches. A grep for the moved *wording* finds none of them —
the sweep has to run on the source file's own name.

---

# Part 5 · What is not built

## Open corrections — none live

**Empty as of 20260805 22:18 — the first time since this list opened on 20260731.** Owned by
[`plans/20260731_1202-open-corrections.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260731_1202-open-corrections.md).

**That is not a finish line.** The list refills from *use*: every entry it has ever held came from
**building** something — the RFC realism corpus, or the graph release measured against it — rather
than from reading code, which is what that corpus was for. An empty list means nobody has run
Pinakes lately, never that it is done.

**Nine items closed since 20260804**, and the pattern in them is worth more than the count:

| closed in | what |
|---|---|
| `0.10.0` | the interrupted-sync trio |
| `0.12.0` | the `[light]` backend error · `pnk doctor`'s home-directory leak · heading-coverage *detection* |
| `0.13.0` | **numbered plain-text headings** as `[chunking] headings` · the **silent `[chunking]` no-op** that building it exposed |
| `0.14.0` | the sync-CPU question **answered by measuring** · heading coverage's **permanent WARN** narrowed · `pnk init` **adopting** a directory with content · the `titles` nudge |

**Four of the nine were opened by the work that closed something else** — and one item's original
diagnosis turned out to be wrong and was corrected rather than quietly dropped: the Markdown heading
grammar never failed to match RFC numbering, it was **never run**, because `chunk.py` dispatches on
source type and a `.txt` file took `_plain_blocks`, which set `heading_path=None` unconditionally.
Nothing failed to match because nothing was tried.

> The list refills from use. An empty one means nobody has run Pinakes lately, never that it is
> finished.

## The graph release — shipped 0.11.0

✅ **Shipped in 0.11.0** (20260805 07:14), with its channel `off`. Blocked for three days on a
corpus, not on code; the corpus cleared the *reachability* precondition — and then the retrieval gate, run
20260804 22:52, did not pass. `expand` defaults `off` ([the numbers](STATUS.md#did-the-expansion-channel-earn-its-default--no-measured-20260804-2252)). 
**The finding is worth more than the feature.** The reachability probe found 9 failing multi-hop
questions reachable within two hops; the retrieval instrument lifted **none** of them, and the
channel displaced three answers the existing fusion already had. `reachable ≠ retrievable`, by 9
against 0.

**What it adds:** structural edges derived at sync time (sibling, parent/child, in-section,
co-located, shared-tag), an expansion channel behind `graph_channel` (default off), and
`schema_version` 3 — which forces a rebuild for every KB in existence. That forced rebuild is why
the gate was measured *before* the schema change rather than after it.

**Why it stopped, and what restarted it:** its gate was measured in
[`0.7.0`](#070--the-measurement-that-said-no--20260801-1240) and could not be reached on
`tests/demo-kb` — 1 of 18 multi-hop questions failing where 7 were needed. Re-measured on the
300-RFC corpus on 20260804: **12 failing, 9 reachable without authored edges**, against a
precondition of 7 and 7 —
[the numbers](STATUS.md#can-the-graph-releases-gate-be-reached--yes-measured-20260804),
[the decision](https://github.com/lucagattoni/pinakes/blob/main/plans/20260804_1442-decision-g3-go.md).

**What has already shipped from it:** G1 (reproducibility) and G4 (`requires_pinakes`) in
[`0.6.0`](#060--links-you-can-write--20260801-1051); G2 (the evaluation artifact and the measurement
itself) in [`0.7.0`](#070--the-measurement-that-said-no--20260801-1240); **G3, G5 and G6 all landed
in `0.11.0`**, so nothing from this build order is outstanding.

**One caveat that bounded the build, and its cause was not what was first recorded:** every chunk in
the 300-RFC corpus had an empty `heading_path`. Not because a grammar failed to match RFC section
numbering — because none was ever run: `chunk.py` dispatched on *source type*, and every type but
`markdown` took `_plain_blocks`, which sets `heading_path=None` unconditionally. So `in-section` and
`parent-child` derived **zero** edges and were never exercised, and `sibling` derived 106 506 that
changed no outcome. All six kinds were built anyway — that zero was a question for G5's gate, which
carried a `--drop sibling` arm to answer it, not a reason to drop a kind on evidence from a corpus
whose chunker had never been asked. `0.13.0` gave plain text a numbered-heading grammar — opt-in,
and that corpus's committed manifest does not ask for it, so re-running against it as published
reproduces these numbers rather than replacing them.

→ The design it would implement: [graph/PINAKES_APPROACH.md](graph/PINAKES_APPROACH.md). The build
order:
[`plans/20260729_0256-links-and-graph.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260729_0256-links-and-graph.md).

### The corpus exists — built 20260804 08:00

[`pinakes-corpus-rfc`](https://github.com/lucagattoni/pinakes-corpus-rfc) — 300 RFCs, connected by
BFS over `obsoletes`/`updates`, structured by working group, tagged from the RFC Editor's own
keywords. It lives **outside this repo** by design
([`plans/20260801_0749-realism-corpus.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260801_0749-realism-corpus.md)).

| | demo-kb | RFC corpus |
|---|---|---|
| documents | 30 | **300** |
| carrying an authored link | 27% | **53.3%** |
| worst out-degree | 2 | **86** |
| chunks | 60 | **106,806** |
| chunks with a heading path | most | **0** |

**It falsified a design premise.** *"Authored links are sparse, precious signal"* is half right:
median out-degree is **1**, but one real human-authored hub (RFC 8996 updates 86 documents in one
header) is a shape the frozen `2.0` weight was never designed for.

**It also found two things about Pinakes, not about the corpus** — the silent structural-chunking
failure above, and that 300 documents / 20 MB is already **2× past** the NumPy vector tier's 50,000
threshold ([DESIGN § 3.1](DESIGN.md#31-vector-search-what-the-tiers-actually-buy)).

→ The full comparison table:
[STATUS § The realism corpus exists](STATUS.md#the-realism-corpus-exists-and-it-falsified-a-design-premise--built-20260804-0800).

### What it settled, and what it did not — 20260804 22:52

**Settled.** Structural edges can be derived, stored and walked at corpus scale: 107,411 edges over
106,806 chunks, and the channel costs **1.02×** query latency, so the "slow at query time" risk did
not materialise. `sibling` is 99.2% of the graph's mass and is **inert in both gauges** — dropping
it changes neither reachability nor retrieval.

**Not settled — and this is the honest bound on the headline.** Three of the seven edge kinds
(`in-section`, `parent`, `child`) derived **zero** edges, because not one of the 106,806 chunks
carried a `heading_path` — the chunker was never asked for one on `.txt`, as the section above
records. Nothing failed to match because nothing was tried, which is why tightening a grammar would
have fixed nothing. So the verdict is *"the edge kinds that worked did not help this corpus"*, never
*"graph structure does not help"*. The `--drop parent-child` arm the arity decision added could say
nothing at all here, by construction.

**What would change it**, in the order the project would try them — **the first two have shipped:**

1. ✅ **Detect the silence** — `pnk doctor` reports the share of chunks carrying a `heading_path`
   (0.12.0). Detection only, as scoped; extending the grammar was left a separate decision.
2. ✅ **Make the three inert kinds derivable** — `[chunking] headings = "numbered"` gives plain text
   a heading path (0.13.0). It is **opt-in**, so it reaches a corpus only when asked: the published
   RFC corpus's manifest does not set it, while `tools/build_rfc_corpus.py` stamps it for a corpus
   built fresh. **What remains is re-running the gate against a corpus that has sections**, which
   nobody has done; the re-entry checklist is
   [`plans/20260804_1016-graph-remainder-reentry.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260804_1016-graph-remainder-reentry.md).
3. **A different channel design.** Explicitly *not* a more expensive one — G5's result licenses
   neither PPR nor the `[ner]` extra, and the pre-commitment said so before the number was known.

> **The honesty constraint held.** The questions were frozen before the probe existed and were never
> re-authored to produce failures. Nothing was tuned after the result: no weight moved, no threshold
> was revisited. `expand-in-degree` was the one leg that lifted anything, and it is **reported, never
> gated** — noticing the best-performing leg after seeing the numbers is exactly the exploratory
> fitting the pre-commitment forbids.

## The graph release, staged — gates only, not scheduled

The PPR (personalized PageRank) channel and the `[ner]` extra. **There is deliberately no
implementation plan** — a written plan for work that may never ship creates pressure to build it.

What exists is
[`plans/20260804_1016-staged-channel-gates.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260804_1016-staged-channel-gates.md):
what measurement would justify each, and what would refuse it. Decided 20260804: **PPR's gate does
not run at all on a corpus below the heading-coverage floor** — the absent input is half its
personalization vector, not one edge kind of seven.

→ The recipe and its counter-evidence:
[graph/PINAKES_APPROACH.md](graph/PINAKES_APPROACH.md) and [graph/GRAPH_RAG.md](graph/GRAPH_RAG.md).

## The deep release

**`pnk ask --deep`** — the budgeted agentic loop that escalates when free retrieval is not enough,
writing its discoveries back into sidecars.

- The **only paid entry point still unbuilt**. Adding it edits the allowlist,
  [DESIGN § 1](DESIGN.md#1-what-this-is) and [INVARIANTS.md](INVARIANTS.md) in one commit.
- No plan written. It has been described as "planned" since
  [`0.1.2`](#012--the-readme-told-the-truth--20260727-1525) — and correcting the README's claim that
  it *existed* was that release's whole point.

→ The escalation model it implements:
[DESIGN § 4.2 Escalation — "free path first"](DESIGN.md#42-escalation--free-path-first). Its
placeholder in the CLI: [CLI § Planned — not built yet](CLI.md#planned--not-built-yet).

## The template release — ready to start

✅ **Unblocked.** Plan written, reviewed, decisions taken. Nobody has started it.

**What it adds:** the template ecosystem, `pnk upgrade` migrations, and the `sqlite-vec` tier.

**The problem it solves:** a template change reaches **new KBs only**. The PDF-glob explanation
shipped in [`0.2.2`](#022--the-silent-skip-named--20260728-1849) appears in no KB created before it,
and nothing detects that divergence — so existing KBs stay PDF-blind permanently unless their owner
edits the manifest by hand. [`0.6.0`](#060--links-you-can-write--20260801-1051)'s `requires_pinakes`
closed the *diagnosis*; nothing yet closes the gap.

**State:** the plan
([`plans/20260804_1016-template-release.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260804_1016-template-release.md))
is written, adversarially reviewed (36 findings), and its four open decisions were taken by the user
on 20260804. T1–T4 are unblocked.

⚠️ Its measurements are recorded *as of a named commit*, not as properties — `main` moved twice
during the session that wrote it. **Re-run its Baseline block before trusting any line number in
it.**

→ The problem stated in full, with all four drift axes: [KB-UPDATES.md](KB-UPDATES.md) — especially
[§ 2](KB-UPDATES.md#2-the-four-drift-axes), [§ 5 `pnk upgrade`](KB-UPDATES.md#5-pnk-upgrade) and
[§ 6 Detecting template drift](KB-UPDATES.md#6-detecting-template-drift). The vector tier it would
add: [DESIGN § 3.1](DESIGN.md#31-vector-search-what-the-tiers-actually-buy). Templates:
[DESIGN § 6.1](DESIGN.md#61-templates).

---

## How this project builds

Useful context for reading anything above. The rules themselves live in
[`CLAUDE.md`](https://github.com/lucagattoni/pinakes/blob/main/CLAUDE.md), the procedures they point
at in [BUILDING.md](BUILDING.md) and [RELEASING.md](RELEASING.md).

- **One increment at a time.** Own worktree, own branch, tests in the same commit, `./check.sh`
  green, then a **fresh adversarial review** of the diff before it merges. Findings are their own
  commit, and the ones worth keeping become [retrospectives](RETROSPECTIVES.md).
- **Green is not enough.** For the most safety-critical assertions, the source is mutated on purpose
  to confirm the *right* test fails. Tests written by the reasoning that wrote the code inherit its
  blind spots.
- **Unbuilt work is named, never numbered.** For months `v0.3` meant the links release; then `0.2.2`
  shipped and the next MINOR *was* `0.3.0`. One number meant two releases, and either reading would
  have renumbered ~60 committed references ([STATUS § Release roadmap](STATUS.md#release-roadmap)).
- **Complete work never sits in `[Unreleased]`.** Hence the release cadence in the table above
  ([RELEASING.md](RELEASING.md)).
- **`CHANGELOG.md` and `RETROSPECTIVES.md` are never edited directly** — a change drops a fragment in
  [`changelog.d/`](https://github.com/lucagattoni/pinakes/blob/main/changelog.d/README.md) or
  [`retro.d/`](https://github.com/lucagattoni/pinakes/blob/main/retro.d/README.md), spliced at
  release time. Several agents work here at once, and a clean auto-merge is not a correct merge.
- **Every promise has a test, and the table naming them is gated** —
  [VERIFICATION.md](VERIFICATION.md).
