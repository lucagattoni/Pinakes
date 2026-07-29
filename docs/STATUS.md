# Status — what ships today

**Latest release: 0.2.2** · last reviewed 20260728 19:16

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
| `pnk init` | shipped | one template (`notes`); `--ci` writes the workflow (on `main`, unreleased) |
| `pnk sync` | shipped | `--rebuild`, `--sidecars-only`, `--index-only`, `--extract`, `--force`, `--clear-cache[=paid]` |
| `pnk search` | shipped | BM25 + vector + rerank, metadata filters, `--json` |
| `pnk doctor` | shipped | environment, coherence, orphans, links, hooks, cache |
| `pnk install-hooks` | shipped | the three-hook split; all three force `--extract=pypdfium2` (on `main`, unreleased) |
| `pnk serve` | shipped | MCP: `pinakes_search`, `pinakes_get`, `pinakes_list_kbs` |
| `pnk budget` | on `main`, unreleased | I6b. Day/month/operation spend, `--resolve` for an unknown outcome |
| `pnk ask --deep` | **not built** | the deep release |

| Capability | State | Notes |
|---|---|---|
| Markdown / text / code ingest | shipped | |
| **PDF ingest, free path** | shipped | `pypdfium2`, needs `pinakes[pdf]`. **Off by default — see the caveat below** |
| Extraction cache | shipped | `.pinakes/cache/extract/` |
| Page provenance (`page_start`/`page_end`) | shipped in the **index** | not yet surfaced in results — I8 |
| Extraction quality scoring | shipped | `make pdf-eval` against `tests/pdf-corpus/` |
| **PDF ingest, paid path** (scanned PDFs) | on `main`, unreleased | I7b. `claude-vision` is a real extractor, **measured against the live API 20260729** — 1.000 on every metric over the synthetic scanned stratum, where the free path scores 0.000 ([DESIGN §9](DESIGN.md#9-known-risks)) |
| Budget estimator, caps, window aggregation | shipped 0.2.2, **inert** | I6a. The pure logic only — nothing calls it, so nothing can spend |
| Budget ledger, `pnk budget`, the accountant | on `main`, unreleased | I6b. `ledger.jsonl`, the reservation/outcome protocol, and I6a's decisions read from it — now driven by I7b's extractor |
| `path:page` citations | **not built** | I8 |
| Cross-KB links (`pnk link`, `pinakes_links`) | **not built** | the graph release |
| `sqlite-vec` tier, template ecosystem | **not built** | the template release |

**Nothing in the shipped surface can spend money.** The only paid code path is the `claude-vision`
extractor, and it is **in no release** — it landed with I7b and exists on `main` only. Installing
from PyPI gets a build with no way to spend, whatever the manifest says. **Installing from `main`
does not**: there, a KB configured for `claude-vision` can bill a real key. See
[DESIGN §5](DESIGN.md#5-cost-control).

Since I7a (on `main`, unreleased) that is enforced rather than asserted: `.paid-path-allowlist`
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

⚠️ **A template change reaches new KBs only.** I9's line will not appear in any KB created before
it, and nothing today detects or reports that divergence — so existing KBs stay PDF-blind
permanently unless their owner edits the manifest by hand. That gap, and what to do about it, is
worked through in [KB-UPDATES.md](KB-UPDATES.md) (a proposal; no increment assigned).

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
| I6b | Budget I/O — ledger, prompt, `pnk budget`, hooks that cannot spend | on `main`, unreleased |
| I7a | The paid-path allowlist gate and the invariant amendments | on `main`, unreleased |
| I7b | The paid Claude-vision extractor — request shape, validation, retries | on `main`, unreleased |
| I7c | The completeness audit, staging, all-or-nothing commit | on `main`, unreleased |
| I8 | `pnk doctor` text yield, `path:page` citations on both surfaces | **planned** |
| I9 | Docs sweep, template, CI | **planned** |

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

### Both reasons have now expired — 20260729, I7c landed

The audit, the staging and the all-or-nothing commit are on `main`. **Nothing in this file argues
against cutting the paid-extraction release any more**, and the project's own rule says complete
work does not sit in `[Unreleased]`.

It is **not** cut automatically, and the reason is not doubt about the code: `PUBLISH_TO_PYPI` is
`true`, so pushing the tag publishes to PyPI, and a PyPI version cannot be re-uploaded or truly
withdrawn. That is a decision with a one-way door in it, so it takes a human saying yes — which is
the same rule that governs every other irreversible outward-facing action here, not a special case
for releases.

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

**What is still not established**, and belongs in any release notes: the fixtures behind
`tests/fixtures/claude/` are **still authored from the documented response shape**, not replaced
with these recordings. The live run agreed with them on every branch it exercised — including the
refusal — but it did not exercise all of them, and swapping them in is its own piece of work.

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
> | **the paid-extraction release** | Budget machinery, the opt-in paid Claude-vision extractor, `path:page` citations (I6–I9) |
> | **the graph release** | `pnk link`, `pinakes_links`, cross-KB traversal, structural edges |
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
| *the paid-extraction release* | Budget machinery, the opt-in paid Claude-vision extractor, `path:page` citations (I6–I9) |
| *the graph release* | `pnk link`, `pinakes_links`, cross-KB traversal, link-coverage reporting, free structural edges — build order in [`graph/PINAKES_APPROACH.md`](graph/PINAKES_APPROACH.md) §10 |
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
| recall@5 | 0.879 | 20260725 18:55, demo KB, `[light]` models |
| MRR | 0.774 | 20260725 18:55 |
| rerank precision | 0.727 | 20260725 18:55 |
| false-abstain | 0.03 | 20260725 18:55 |
| **false-confidence** | **0.25** | 20260725 18:55 — one no-answer question in four still gets a confident answer |
| NumPy vector tier | 2.25 ms/query at 50k×384, 77 MB resident | 20260725 13:49 |

The false-confidence figure is fitted and scored on the same 41-question set (8 of them no-answer),
so treat it as a floor rather than an estimate. Publishing it is the point:
[DESIGN §4.2](DESIGN.md#42-escalation--free-path-first) commits to measuring the heuristic's cost
rather than assuming it away.

## Published on PyPI

**[`pinakes` is on PyPI](https://pypi.org/project/pinakes/).** `uv add "pinakes[light]"` works —
verified 20260729 01:01 by installing the published wheel into an empty venv and running
`init` → `sync` → `search`.

| | |
|---|---|
| Published version | **0.2.2 only.** 0.2.0 and 0.2.1 predate publishing and are **not** on PyPI, so pinning either fails |
| First upload | 20260728 17:16 UTC |
| Extras available | `st`, `light`, `pdf`, `claude` — all four |
| `requires-python` | `>=3.13` |

`PUBLISH_TO_PYPI` is now `true` (set 20260728 17:15 UTC), so **every tag publishes from here on**.
Tagging stays safe by construction: version/tag agreement, the build and an isolated wheel smoke
test all run before the upload step is reached.

Install lines are in the [GUIDE](GUIDE.md#install). Installing from git still works and remains what
you want for unreleased work sitting on `main`.
