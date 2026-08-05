# Status — what ships today

**Latest release: 0.14.0** · last reviewed 20260805 22:22

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
| `pnk doctor` | shipped | environment, coherence, orphans, links, hooks, cache, heading coverage, edge hubs |
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
| Cross-KB links (`pnk link`, `pnk links`, `pinakes_links`) | **shipped 0.6.0** — `pnk sync` records what other KBs link into this one (`--scan-links`), `pnk links` and `pinakes_links` traverse (0.5.0), `pnk link` authors, and `pnk doctor` reports link coverage as a ratio and resolves cross-KB targets (0.6.0) | 0.5.0 · 0.6.0 |
| Sidecar round-trip | **shipped 0.5.0** — `ruamel.yaml` in round-trip mode at YAML 1.2: comments, quoting, block scalars and blank lines survive a rewrite, and an unknown key's value is no longer reinterpreted | 0.5.0 |
| `sqlite-vec` tier, template ecosystem | **not built** | the template release |

⚠️ **0.3.0 is the first release that can spend money — and it will not, unless you ask it to.**
Every earlier version had no paid code path at all. The only one now is the `claude-vision`
extractor, and reaching it takes a deliberate act: `EXTRACTION_BACKEND_DEFAULT` is `pypdfium2`, so
a KB spends only when its manifest says `[extraction] backend = "claude-vision"` or a command
carries `--extract=claude-vision`, **and** a real `PINAKES_ANTHROPIC_API_KEY` is in the environment. Absent
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
worked through in [KB-UPDATES.md](KB-UPDATES.md). Its `requires_pinakes` half **shipped in 0.6.0
(G4)** — a manifest can declare the oldest Pinakes that can read it, so an out-of-date build says so
instead of reporting a typo. That closes the *diagnosis*, not this gap:
nothing yet detects template drift or adopts a new default into an existing manifest.

### Caveat: the `[light]` backend needs a manifest edit

`pnk init` always stamps `provider = "sentence-transformers"` — it cannot see which extra you
installed. On a `pinakes[light]` install, set `provider = "fastembed"` in **both** `[embedding]` and
`[rerank]` before the first sync ([GUIDE](GUIDE.md#choosing-a-backend)).

---

## v0.2 increment ledger

The build order is [`plans/20260727_1543-v0.2.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260727_1543-v0.2.md). Each increment is a separate, bisectable
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
| I8 | `pnk doctor` text yield, `path:page` citations on both surfaces, the three end-to-end traces | shipped 0.4.0 |
| I9 | The verification audit (`docs/VERIFICATION.md` + its gate), the untested-check sweep, README extras, wheel-smoke assertions | shipped 0.4.0 |

**Decided 20260728 17:52 — I6–I9 accumulate, and cut as one MINOR release.** `plans/20260727_1543-v0.2.md`
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
gap was named here rather than discovered by a user, and **I8 closed it** (shipped in 0.4.0).

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
[`tools/record_claude_fixtures.py`](https://github.com/lucagattoni/pinakes/blob/main/tools/record_claude_fixtures.py). Every fixture now declares
its own `provenance`, so the set no longer makes one claim about a mixed collection
([the fixture README](https://github.com/lucagattoni/pinakes/blob/main/tests/fixtures/claude/README.md)).

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
| **0.5.0** ✅ *(the links release, interim)* | `pnk links`, `pinakes_links`, reverse-scan and the sidecar round-trip fix — no `schema_version` bump, so no rebuild. **The release cuts twice** (decision 27): this is the interim MINOR at L5b; the final cut is at L8, and the name stays in the unbuilt-work table until then. **L1 landed:** the partner corpus, sparse authored links in both, and the density gate. **L2 landed:** reverse-scan writes inbound rows and `kb_refs`, with a freshness window and `--scan-links`. **L3–L5 landed:** the bounded traversal core, `pnk links`, and `pinakes_links` on the MCP surface. **L5b landed:** `ruamel.yaml` replaces `pyyaml` in the sidecar, so a rewrite preserves comments, quoting and blank lines — and `country: NO` stops becoming `false` ([decision](https://github.com/lucagattoni/pinakes/blob/main/plans/20260731_0602-decision-ruamel-yaml.md)). |
| **0.6.0** ✅ *(the links release, final)* | `pnk link` authors a link from the command line, and `pnk doctor` reports link coverage as **linked docs / total docs** and resolves each cross-KB target through its `[[links.kb]]` entry (L6–L8). Also `[kb] requires_pinakes` (G4) and the evaluation's tie-ordering fix (G1) — no `schema_version` bump, so no rebuild. **This completes the two-cut release** decision 27 describes: 0.5.0 was the interim MINOR at L5b, this is the final cut, and the name leaves the unbuilt-work table here |
| **0.7.0** ✅ | The evaluation grows a per-question artifact (`eval/outcomes.json`), stable question ids, a validated `kind`, and an empty golden set that skips with a reason instead of failing — plus the demo KB's golden set grown 41 → 74 with a `simple-lookup` control class (G2). **Its deliverable is a measurement:** the graph release's gate could not be reached on `tests/demo-kb`, so G3 and G5 did not start then — the RFC realism corpus cleared it on 20260804 ([above](#can-the-graph-releases-gate-be-reached--yes-measured-20260804)). No `schema_version` bump, so no rebuild |
| **0.7.1** ✅ | `[sources] include` can no longer walk out of the KB or write sidecars outside it — three defects live since before 0.5.0: a `..` pattern indexed files outside and minted sidecars beside them, an absolute pattern was a bare traceback, and a symlinked directory carried the walk out with no `..` anywhere. Plus a document reached by two legal spellings is now one document, and `tools/link_density_gate.py` survives a non-canonical root |
| **0.8.0** ✅ | **Breaking, paid path only:** the Claude-vision extractor's key is `PINAKES_ANTHROPIC_API_KEY` and is passed to the SDK explicitly — no fallback to `ANTHROPIC_API_KEY`, which the SDK used to read out of whatever environment it was handed. Rename the variable in your `.env`. Also `[budget]` defaults raised (`per_operation_eur` 0.05 → 0.30, `monthly_eur` 5.00 → 30.00), a `check.sh` gate pinning `docs/STATUS.md`'s own header to `__version__`, the reachability probe refusing a golden set it cannot measure rather than absorbing it, and sixteen documentation claims corrected against the code. No `schema_version` bump, so no rebuild |
| **0.9.0** ✅ | **Documentation only — no code path changed.** `docs/` is now published as a site at [lucagattoni.github.io/pinakes](https://lucagattoni.github.io/pinakes/), built with `mkdocs build --strict` on every PR and deployed on every push to `main`; the strict build found and fixed 31 dead links and anchors in the existing docs. The repository moved to `github.com/lucagattoni/pinakes` (GitHub redirects the old URL) and prose across the repo now writes the project name **Pinakes**, while every identifier — the PyPI package, `pinakes.toml`, `.pinakes/`, `pinakes[st]`, `pinakes_search`, `requires_pinakes` — stays lowercase and unchanged. Also a per-kind edge census in `tools/reachable_ceiling_probe.py`. No `schema_version` bump, so no rebuild |
| **0.10.0** ✅ | An interrupted first sync no longer reads as a model mismatch: `pnk doctor` reports `WARN sync completeness` with remedy `pnk sync`, instead of `FAIL` with `--rebuild` — which discarded every embedding the interrupted sync had already written. `pnk sync` also prints live progress on a terminal (documents done/total and a rate, one self-overwriting line, silent when piped or `--quiet`), after a 300-document run took over two hours with no output. And `sync.py`'s timestamps are UTC, matching `lock.py`'s — the two used identical formats on different clocks, so a lock taken seconds ago could read hours old. No `schema_version` bump, so no rebuild |
| **0.11.0** ✅ *(the graph release)* | **Breaking for every existing KB: `schema_version` 3, so the first `pnk sync` after upgrading rebuilds the whole index.** There are no migrations, by design; `pnk sync --rebuild` is the remedy the refusal prints, and it is free. What it buys: a derived structural graph — a `nodes`/`edges` table over chunk, document, tag, per-document heading and directory nodes, with every shared-value relation through its hub (G3) — and `pnk doctor` reporting the highest-degree hubs (G6). **The expansion channel (`[retrieval] graph_channel`) ships `off` and its golden-set gate is why** (G5): run on the RFC realism corpus it improved 0 multi-hop questions and regressed 3, licensing p = 1.0000 ([the numbers](#did-the-expansion-channel-earn-its-default--no-measured-20260804-2252)). Nothing was tuned after seeing that. The finding is `reachable ≠ retrievable` — a reachability probe called 9 of those questions liftable and the retrieval instrument lifted none |
| **0.12.0** ✅ | **`pnk doctor` reports heading-path coverage and warns when a whole source type carries none** — the check that would have caught the RFC realism corpus indexing 106 806 chunks with not one heading path, which is what bounds 0.11.0's expansion-channel gate: three of the seven edge kinds derived zero edges on it. Total absence across a source type is the predicate, not a fitted share, and the remedy distinguishes *the chunker cannot extract one for this type* from *this Markdown uses another heading convention*. Also: the missing-backend error names an installed alternative and the two manifest lines to flip, instead of prescribing the 2 GB install a `[light]` user chose to avoid; `pnk doctor` no longer prints the operator's home directory; and `tools/measure_sync_cpu.py` measures how many cores a command keeps busy, sampling the whole process tree because watching the launched pid read 0.0 cores for a one-core load behind `uv run` |
| **0.13.0** ✅ | **Plain text can carry a heading path.** `[chunking] headings = "numbered"` reads a dotted-decimal outline into `heading_path` — opt-in, `text` only, and it **refuses rather than guesses**: the numbers must form a valid outline walk across the whole document, and if the walk fails anywhere that document yields no headings at all rather than a partial labelling. **Measured against 980 real RFCs in doubling rounds** ([§5.4](https://github.com/lucagattoni/pinakes/blob/main/plans/20260805_1721-metadata-as-retrieval-context.md)): 644 accepted overall and **314 of 314 modern-era documents, 100% at every round size**. Two clauses were added from that measurement and two more were tried and rejected by it. Also: a `[chunking]` edit is no longer a silent no-op — the index records what it was built under, and both `pnk sync` and `pnk doctor` say so — and `tools/build_rfc_corpus.py` makes the corpus reproducible instead of local to one machine |
| **0.14.0** ✅ | **`pnk doctor` stops crying wolf, and `pnk init` stops refusing the normal way to start a KB.** Heading coverage now WARNs only for `markdown` at 0% — the one case a user can act on — and reports the rest as OK with a note that separates *`text` can carry one*, *`text` was offered and refused*, and *`code`/`pdf` cannot today*. `pnk init` **adopts a directory that already has content** and never overwrites a file it finds there, so cloning a repo and initialising inside it works; an adopted `.gitignore` missing `.pinakes/` is flagged with the line to add. A new `titles` check counts documents still carrying the filename-minted title — a nudge, never a warning, because both committed corpora sit at 100%. Also settled by measurement rather than argument: **the first sync is not single-core** (peak 5.0, mean 4.8 of 10 under `fastembed`), so the document loop stays serial |
| **the graph release** ✅ **shipped 0.11.0** | Structural edges, the expansion channel (`graph_channel`, default off), `schema_version` 3 — eval-gated. All six increments landed: **G1** and **G4** in 0.6.0, **G2** in 0.7.0, **G3**, **G5** and **G6** in 0.11.0. **Its gate ran and did not pass, so `expand` ships `off`** ([the numbers](#did-the-expansion-channel-earn-its-default--no-measured-20260804-2252)) — an eval-gated feature that is built, measured and off by construction, which is the structure working rather than failing. What would change it is a corpus or a different channel design, never a more expensive one ([decision](https://github.com/lucagattoni/pinakes/blob/main/plans/20260804_1442-decision-g3-go.md)) |
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
([`plans/20260801_0749-realism-corpus.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260801_0749-realism-corpus.md)).

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

### The realism corpus exists, and it falsified a design premise — built 20260804 08:00

**[`pinakes-corpus-rfc`](https://github.com/lucagattoni/pinakes-corpus-rfc)** — 300 RFCs, a
connected cluster closed by BFS over `obsoletes`/`updates` in both directions, structured by
`wg_acronym` and tagged from the RFC Editor's own `keywords`. It lives outside this repo by design
([`plans/20260801_0749-realism-corpus.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260801_0749-realism-corpus.md)).

| Measure | demo-kb | partner-kb | RFC corpus |
|---|---|---|---|
| documents | 30 | 21 | **300** |
| carrying an authored link | 27% | 29% | **53.3%** (160/300) |
| worst out-degree | 2 | 3 | **86** |
| relation vocabulary | 2 kinds | 4 kinds | 2 (`updates` 296, `supersedes` 95) |
| chunks | 60 | — | **106 806** |
| chunks with a `heading_path` | most | most | **0** |

**The prediction recorded before any of it ran was right, and by more than expected.** The plan
said the corpus would exceed the 35% density cap and possibly the degree cap of 4. Density is
**53.3%**; worst out-degree is **86** — RFC 8996 *(Deprecating TLS 1.0 and TLS 1.1)* updates 86
documents in one header. Nothing was tuned: every rule was written down before an edge existed.

**The shape matters more than the headline.** Median out-degree is **1**, second-largest is 17. The
corpus is sparse with one real human-authored hub — not uniformly dense. So APPROACH §3's
*"authored links are sparse, precious signal"* is half right: sparse in the median, and carrying a
hub that decision 13's **2.0 undamped** weight was never designed for
([the ⚠️ on G3's weight table](https://github.com/lucagattoni/pinakes/blob/main/plans/20260729_0256-links-and-graph.md)).

**Two findings about Pinakes, not about the corpus:**

- **`strategy = "structural"` recognised no headings at all** — 0 of 106 806 chunks — because its
  grammar is Markdown-shaped and RFC section numbering is not. Silent. It costs citations their
  heading component, and it means `in-section`, `parent` and `child` would derive **zero** edges
  here.
- **106 806 chunks is 2× past the NumPy vector tier's 50 000 threshold**, and `pnk doctor` says so.
  A 300-document, 20 MB knowledge base reaches the tier ceiling — which is a smaller corpus than
  the ceiling's framing implies.

Ten friction findings from building it are in
[`plans/20260731_1202-open-corrections.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260731_1202-open-corrections.md). `pnk doctor`
reports no FAIL and five WARNs.

### Did the expansion channel earn its default? — **no, measured 20260804 22:52**

**No. `expand` ships `off`.** The graph release defaults its channel on only if an exact one-sided
sign test finds enough multi-hop questions improving. Run on the RFC realism corpus, at G5's own
HEAD, against a `schema_version` 3 index rebuilt for it:

| leg | multi-hop | improved | regressed | p |
|---|---|---|---|---|
| `off` | 7/20 | — | — | — |
| `expand`, without authored edges | 4/20 | 0 | **3** | 1.0000 |
| `expand`, all kinds | 4/20 | 0 | **3** | 1.0000 |

**Licensing p = 1.0000** — the more conservative of the two, as both runs bind. Nothing was lifted,
and the channel's extra candidates **displaced three answers two-list fusion already had**.

**The finding is `reachable ≠ retrievable`.** The reachability probe found **9** of those failing
questions reachable within two logical hops without authored edges — the measurement that unblocked
this release ([above](#can-the-graph-releases-gate-be-reached--yes-measured-20260804)). The
retrieval instrument lifts **none** of them. That gap is not a small correction: it is 9 against 0,
and it is exactly why the probe's own docstring says a high ceiling *"proves only that the gate is
not impossible"*. **A reachability precondition is necessary and nowhere near sufficient.**

**`sibling` is now inert in both gauges.** It is 106 506 of the corpus's 107 411 non-transit
structural edges, and `--drop sibling` returns the same 4/20, the same three regressions and the
same p. The reachability probe had already found removing it cost nothing; the retrieval instrument
agrees independently. The harm comes from the document-level path instead — `membership` transit
into `co-located` (262 edges) and `shared-tag` (643) hubs, which pull whole documents' chunks into
the fusion.

**Latency was not the problem.** `off` 2012 ms/query against `expand` 2051 — **1.02×** on a
106 806-chunk index.

Two bounds, both stated rather than worked around. The corpus has `[retrieval.confidence]`
commented out, so **two of the gate's four clauses could not fire on it** and are exercised only by
the synthetic fixtures in `tests/test_graph_channel.py` — a gate whose only fixture is the real
corpus can be tested solely in whichever direction that corpus points. And **no chunk in it carries
a `heading_path`**, so `parent-child` and `in-section` derive zero edges, the `--drop parent-child`
arm is inert by construction, and a "sibling" there is an adjacent arbitrary *size-slice* rather
than an adjacent section. What the arms measured is the value of size-slice adjacency on a corpus
whose structural chunking had silently degraded.

**Nothing was tuned after seeing the number** — no weight moved, no threshold revisited. The
`authored` weight's *measured at G5* marker is discharged as *"measured, and it changed no
outcome"*.

### Can the graph release's gate be reached? — **yes, measured 20260804**

**Yes on a realistic corpus; no on the synthetic one.** The graph release defaults its expansion
channel on only if an exact sign test finds enough multi-hop questions *improving*, and an
improvement can only come from a question that fails today. The precondition: **at least 7 multi-hop
questions fail, and at least 7 of those are channel-reachable within 2 logical hops without authored
edges.** The without-authored figure binds; the with-authored figure records and licenses nothing.

| | Required | `tests/demo-kb` · 20260801 | **RFC realism corpus · 20260804** |
|---|---|---|---|
| multi-hop questions failing today | ≥ 7 | 1 | **12** |
| of those, reachable **without** authored edges | ≥ 7 | 1 | **9** |
| of those, reachable with authored edges | — | 1 | 12 |
| reachable but beyond 2 hops · at-seed only | — | 0 · 0 | 0 · 1 |

**So G3 starts** ([decision](https://github.com/lucagattoni/pinakes/blob/main/plans/20260804_1442-decision-g3-go.md), 20260804 13:50). The measurement was deliberately sequenced
*before* the schema change, so a `schema_version` bump — and a forced rebuild for every KB in
existence — could not happen for an edge table whose channel might never be licensed. G1, G2 and G4
were cut as a release of their own while the answer was still no.

**Three drop runs show the 9 discriminates** rather than counting every document already in reach:
removing `co-located` costs 3 questions, removing `shared-tag` costs 6, and the two sum to exactly
9 — they lift disjoint sets. Removing `sibling` — 106 506 of 107 802 edges — costs nothing. No drop
ever raised the count. Artifacts:
[`pinakes-corpus-rfc/eval/probe`](https://github.com/lucagattoni/pinakes-corpus-rfc/tree/main/eval/probe).

**The bound on all of it: every chunk in that corpus has an empty `heading_path`.** RFC section
numbering is not Markdown-shaped, so `strategy = "structural"` degraded to size-based chunking in
silence — `in-section` and `parent-child` derived **zero** edges and were never exercised, and a
"sibling" there is an adjacent arbitrary size-slice rather than an adjacent section. The 9 is
therefore a **floor** for a corpus whose chunker works, and `sibling`'s zero is a question for G5's
gate, not a design decision. Fixing the silent degradation is a live correction.

**Why the synthetic corpus could never answer this**, which is the finding that outlived the
negative result:


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
`"fastembed"` — the edit [README.md](https://github.com/lucagattoni/pinakes/blob/main/README.md) and the [Guide](GUIDE.md#choosing-a-backend)
both call out — **and since 0.12.0 the error itself does too**: when `fastembed` is installed and
`sentence-transformers` is not, the remedy names the alternative and the two `provider` lines to
flip, instead of prescribing the ~2 GB install the `[light]` extra exists to avoid.

Verified 20260805 07:20 against **0.11.0** from the index (`uvx --no-cache --refresh --from "pinakes[light]==0.11.0" pnk --version` → `pinakes 0.11.0`): `init` → edit → `sync` →
`search` returns the document. The earlier claim that it worked unedited was wrong. **0.13.0 has
been verified to install and report its version from the index (20260805 21:06), not to complete
that four-step flow** — the flow is unchanged by this release, but saying so is not the same as
having run it.

| | |
|---|---|
| Published versions | **0.2.2, 0.3.0, 0.4.0, 0.4.1, 0.5.0, 0.6.0, 0.7.0, 0.7.1, 0.8.0, 0.9.0, 0.10.0, 0.11.0, 0.12.0 and 0.13.0.** **0.11.0 bumps `schema_version` to 3**, so the first `pnk sync` after upgrading rebuilds the whole index — free, and `pnk sync --rebuild` is what the refusal prints. 0.9.0's upload was refused on first attempt — renaming the repository broke PyPI trusted publishing, which matches on the exact repository name — and succeeded once the publisher was corrected. **0.8.0 renames the paid extractor's API key** to `PINAKES_ANTHROPIC_API_KEY`, so a KB driving the paid path from an older `.env` refuses until the variable is renamed. 0.2.0 and 0.2.1 predate publishing and are **not** on PyPI, so pinning either fails. **0.4.0 and earlier can destroy a sidecar's permanent ULID** (see 0.4.1) — 0.4.1 is the first release without it |
| First upload | 20260728 17:16 UTC · latest 20260805 21:05 UTC (0.13.0) |
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
