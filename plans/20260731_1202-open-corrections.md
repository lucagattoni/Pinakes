# Open corrections

**Audience: an implementing agent. Goal: executor.** Every live item names the file, the current
text and the required text. Nothing here is a judgement call — if an item reads as a question, that
is a defect in this file; say so rather than choosing.

Restructured 20260801 11:30, after the 0.6.0 release: **nine of the original twelve items were
already closed**, most of them as a side effect of the work that closed something else. A list where
two thirds of the entries are done is one nobody reads to the bottom, so the live items are first and
the closed ones are a table.

**Documentation items are no longer here.** Since the ownership decision (20260801 01:24,
`CLAUDE.md`) every `docs/**`, `plans/**`, `README.md`, `CLAUDE.md` and `CHANGELOG.md` correction is
the planner's, and this file held six. They were closed as part of that ownership, not by an
implementer. What remains below is code and tooling.

**Five live items as of 20260805 19:15.** Every one came from *building* — the RFC realism
corpus, the graph release measured against it, or the grammar built on top of both — rather
than from reading the code. **Three are decided and unbuilt**; one waits on a measurement
nobody has taken. Items 4 and 5 are the newest and share a shape worth noticing: **both were
opened by the work that closed something else**, and both are about a signal the tool fails to
give.

The list refills from use, so an empty one means nobody has run Pinakes lately, never that it is
finished. Note what is **not** here: **both releases in
[`20260729_0256-links-and-graph.md`](20260729_0256-links-and-graph.md) have shipped** — the links
release in 0.5.0–0.6.0, the graph release in 0.11.0 — so that plan is closed and nothing here
unblocks it. What the graph release's own gate established is narrower than it looks, and item 4
below is why: `expand` ships `off` because it did not earn its default *on a corpus where three of
the seven edge kinds derived zero edges*.

---

## Live




### 1 · `pnk init` cannot adopt a directory that already has content

`_check_target` refuses a non-empty directory, so a KB cannot be initialised inside an existing repository — which is what [`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md) prescribes and what everyone does: create the repo, clone it, then init. A `.git`, a README and a `pyproject.toml` are already "not empty", and the message *"clear this one first"* is alarming when the directory holds the documents.

**Hit three times independently** (probe rehearsal, dogfooding KB, corpus).

**DECIDED 20260805 13:13 — refuse only what would actually be overwritten** ([`20260805_1313-decisions-init-titles-and-grammar.md`](20260805_1313-decisions-init-titles-and-grammar.md)). Drop the blanket emptiness test; keep the `pinakes.toml` and not-a-directory refusals; add a refusal naming any file `init` would write that already exists. The accepted cost is the loss of a cheap typo-catcher. `docs/GUIDE.md` gets the retrofit path.

---


### 2 · Every document is titled by its filename

All 300 sidecars carry `title: rfc9110` rather than *"HTTP Semantics"*, so search results are unreadable. `sync` mints the title from the filename when the document has no Markdown H1 — correct for Markdown, useless for anything else.

**Deliberately not worked around** by the corpus agent: hand-writing 300 titles would have hidden the finding, and editing the RFC text would have broken the licence position (verbatim reproduction is the grant).

**DECIDED 20260805 13:13 — keep the filename fallback, and report it** ([`20260805_1313-decisions-init-titles-and-grammar.md`](20260805_1313-decisions-init-titles-and-grammar.md)). The first-line heuristic is **rejected**: an RFC's first line is `Internet Engineering Task Force (IETF)`, so it would mint confidently wrong titles at scale into sidecars the user then commits, which is worse than a filename that is visibly a filename. **Required:** a `pnk doctor` check reporting documents whose `title` equals the filename stem *as minted* — detection, never guessing, and a nudge rather than a FAIL. `title` stays the user's field.

---


### 3 · The first sync may be using one core of ten, and nobody has measured which

**Raised 20260804 13:10, from the RFC corpus run.** 300 documents took over two hours at ~2.4
documents/minute. `sync.py:1863` embeds one document at a time — `backend.embed([chunk.text for
chunk in chunks])` inside a serial loop over documents — so *the loop* is single-threaded whatever
the backend does underneath.

**Measure before changing anything.** Both backends thread internally: `fastembed` runs ONNX
Runtime and `sentence-transformers` runs torch, and both default to multiple intra-op threads. So
there are two very different worlds and the fix is opposite in each:

* **The backend already saturates the machine** → the loop is fine, and the win is a bigger batch
  (embedding several documents' chunks in one `embed()` call), not processes.
* **The backend is effectively single-core** → the loop is the bottleneck and a process pool over
  documents is worth it.

**Required first:** a measurement, recorded in the item — cores actually busy during a sync of ≥50
documents, per backend. `ps -o %cpu` on macOS reports **per core**, so `98%` on a 10-core box is one
core; `750%` is seven. Nothing else in this item may be built before that number exists.

**The instrument landed 20260805 17:36 (`1511be4`); the measurement has not been taken.** Run
`tools/measure_sync_cpu.py --interval 1 -- uv run pnk sync --kb <path> --rebuild` against a corpus of
≥50 documents — **not** `tests/demo-kb`, whose 30 short documents cannot saturate anything.

**Two things about the number it returns, both measured rather than assumed.** It samples the whole
**process tree**: the first version watched only the launched pid, so `uv run` — which burns nothing
while its child does the work — reported **0.0 cores for a one-core load that read 1.0 directly**.
That wrong answer would not have looked broken; it would have looked like this item's finding. And
`%cpu` is a **decaying average over up to a minute** (`man ps`), not an instantaneous reading, which
suits a steady-state multi-minute sync but means a *low* peak is much weaker evidence of an idle
machine than a high peak is of a busy one.

**Then, only if the measurement says single-core:** parallelise the document loop, sized
`os.cpu_count()` less one or two. **Do not stack a process pool on top of a threaded backend** — N
processes each opening an N-thread ONNX session oversubscribe the CPU and typically run *slower*
than serial; if processes are used, pin the per-process thread count to 1.

**Bounds.** Ordering is not free: document ULIDs, the ledger and `.pinakes/` writes must stay
deterministic and single-writer, so only the embedding is a candidate — never the store writes.

**Test:** a sync of a fixture corpus produces a byte-identical index under the parallel and serial
paths, and the parallel path is opt-out (a flag or a manifest key) so a machine that regresses can
go back without a downgrade.

**Explicitly out of scope: `tools/reachable_ceiling_probe.py`.** It is genuinely single-core (~33
minutes per variant, pure-Python graph construction and BFS) and it was considered and rejected —
it runs a handful of times in the project's life, so the complexity would cost more than the
minutes it returns. Recorded so the analysis is not redone.

---


### 4 · The heading-coverage check WARNs forever on `code` and `pdf`

**Shipped in 0.12.0 and immediately in need of this correction.** `_heading_coverage` (`doctor.py`)
returns `Status.WARN` when *any* source type sits at 0%. `code` and `pdf` can never carry a
`heading_path` today — `chunk.py` runs heading detection for `markdown` only — so **a KB containing
one `.py` file or one PDF warns on every `pnk doctor` run, forever**, with a remedy that says it is
a limit of the tool. It did not surface in verification because both committed corpora are pure
Markdown at 100%.

**DECIDED 20260805 18:25 by the user** ([§6](20260805_1721-metadata-as-retrieval-context.md)).

**Required:** WARN **only** when `markdown` sits at 0%. Every other source type reports OK with a
note, and **the note names the cause, not just the number** — *"the chunker extracts headings for
`markdown` only"* — so a reader is not sent to edit documents that are not the problem.

**Why:** an un-actionable warning that cannot be cleared is how doctor output stops being read *at
all*, which costs the actionable warnings too. `markdown` at 0% is the opposite case: real, fixable,
and exactly the defect the check was built for.

**The accepted cost, stated:** the zero-heading-paths condition that bounds the graph release's gate
becomes quieter on `text` and `pdf` corpora. It is still reported — percentage and note are printed
— just not as a WARN. When `[chunking] headings` (item 4) ships, a `text` corpus becomes fixable and
this can be re-judged.

**Test:** a corpus with `markdown` at 100% and `code` at 0% is **OK with a note**; a corpus with
`markdown` at 0% is **WARN**. Both are needed — a test for only the first passes if the check is
deleted outright.

---

### 5 · A `[chunking]` edit is a silent no-op until `--rebuild`

**Found 20260805 19:15 while building the numbered-heading grammar, by running the thing rather
than reading it.** An incremental `pnk sync` re-chunks a document only when *the document* changed.
A manifest-only edit changes no content hash, so every file reports `unchanged` and the new setting
does nothing — with no warning, no hint, and a `pnk doctor` that then reports exactly the condition
the user just tried to fix.

**Measured**, on a two-section `.txt` KB:

| | result |
|---|---|
| `headings = "numbered"` added, plain `pnk sync` | `1 unchanged` · every `heading_path` still empty |
| same manifest, `pnk sync --rebuild` | `1 indexed` · `1. Introduction`, `1. Introduction > 1.1. Scope`, `2. Terminology` |

**The mechanism is shared by every `[chunking]` key** — `max_tokens` and `overlap` too, which is
why this is a general item rather than a defect in the new grammar. It is **pre-existing and was
not introduced by the grammar**; the grammar is what made it visible, being the first key a user has
a reason to flip on a KB that is already indexed. Documented on the key
([MANIFEST § `[chunking]`](../docs/MANIFEST.md#chunking)) so it is not discovered the hard way, but
documentation is not the fix.

**Required:** `pnk sync` must **notice** rather than rely on the user having read a warning. The
shape that fits what is already there: record the chunking identity in `meta` beside the embedding
identity `sync.py` already writes, and report a mismatch the way `pnk doctor` reports model
coherence — a named check with `pnk sync --rebuild` as its remedy.

**Two constraints on doing it, both learned here:**

* **A missing `meta` key must not read as a mismatch.** Every KB indexed before this exists has no
  chunking identity recorded, and a first upgrade that demands a full rebuild of every KB is a cost
  nobody agreed to. Absent means *unknown*, which is a different thing from *different* — this is
  the same distinction the interrupted-sync fix already had to make between a *missing* embedding
  identity and a *wrong* one.
* **WARN, not FAIL, and never an automatic rebuild.** A rebuild is the user's call: it is free in
  money and expensive in time, and the interrupted-sync retrospective is the record of what
  happens when a remedy discards work the user did not offer.

---

## Closed — recorded so nobody reopens them

| Was | Closed by |
|---|---|
| Numbered plain-text headings were not detected, so a rigidly sectioned `.txt` corpus was chunked size-based however structural the manifest read — which is what left the 300-RFC corpus with 106 806 chunks and not one `heading_path`, and so bounds the graph release's gate | `[chunking] headings = "numbered"`, 20260805. Opt-in, `text` only, a **new key** so `strategy` stays inert and `structural` gains no retroactive meaning. **The design is that it refuses rather than guesses:** five line-level clauses and then an outline walk over the whole document, and if the walk fails anywhere that document yields **no headings at all** — exactly the pre-grammar behaviour, never a partial labelling. The predicate was written in full *before any corpus was consulted*, and the tests are written against its clauses rather than against a corpus. Golden set unmoved as predicted (`recall@k` 0.9394, MRR 0.8806, both sides). **Still outstanding: the measurement against the RFC corpus**, which is a separate step and needs a corpus that is not in this repo |
| `pnk doctor` printed the operator's home directory — absolute paths in the one command whose output is the natural thing to paste into an issue | Landed 20260805 (`293bf37`). A `_de_homed` helper strips the KB root's prefix from any message or remedy `doctor.py` forwards. The scope is what makes it right: `store.py`, `sidecar.py` and `ledger.py` all build their text from an absolute path because `manifest.root` is resolved, so the fix sits at the forwarding boundary rather than in each raiser. A path genuinely **outside** the KB — the model cache, a linked KB, a packaged `prices.toml` — is left exactly as printed |
| The `[light]` first-sync error prescribed the 2 GB install to a user who chose `[light]` — `sentence-transformers` missing, `fastembed` sitting right there, and the message offered only the torch install the extra exists to avoid | Landed 20260805 17:31 (`43cef55`). `BackendMissingError` takes an `alternative`; `embed.py` finds it with `find_spec` and **never by loading it**, the same reasoning `CLAUDE.md` pins for the paid extractor — a check must not have the side effects of the thing it checks. When an alternative exists the remedy names only the manifest edit, per this item's own test. Its retrospective is the durable part: the pre-existing test looked environment-independent and was not — it blocked only `sentence_transformers`, leaving this checkout's transitively-installed `fastembed` genuinely importable, so both tests now monkeypatch `find_spec` and **name their precondition instead of inheriting `site-packages`** |
| `strategy = "structural"` degraded to size-based chunking in silence — a 300-RFC corpus indexed **106 806 chunks with every `heading_path` empty**, and nothing said so. Three of the seven edge kinds derive from `heading_path`, so they derived **zero** edges on the corpus the graph release's gate was measured against | Detection shipped 20260805 (`_heading_coverage` in `doctor.py`). **This item's own diagnosis was wrong and is corrected here:** it said the Markdown heading grammar "is Markdown-shaped; RFC section numbering is not, so nothing matches", which describes a regex failing to match. What actually happens is `chunk.py:131` — `blocks = _markdown_blocks(text) if kind == "markdown" else _plain_blocks(text)`. `_markdown_blocks` is **never called** for a `.txt` file, and `_plain_blocks` sets `heading_path=None` unconditionally (`chunk.py:254`). **Nothing failed to match because nothing was tried**, which is why tightening a grammar would have fixed nothing. Its evidence line — *"`grep heading src/pinakes/doctor.py` returns nothing"* — has been false since G6. The remaining half, an opt-in grammar for numbered plain text, is live below |
| `pnk doctor`'s model-coherence remedy destroyed an interrupted sync's work — a first sync killed mid-run leaves `meta` with no embedding identity, which read as a model *mismatch* and printed `pnk sync --rebuild`, discarding every embedding already written | 20260804 13:21. `search.py` raises a new `IncompleteIndexError` only when **none** of the identity keys are present; `doctor.py` reports it as its own check, `sync completeness`, WARN, remedy `pnk sync`. A *partial* `meta` falls through to `CoherenceError` — a missing key never equals the expected value — so it can never land in the benign branch. Write order deliberately unchanged: moving the identity write earlier would let a half-built index claim coherence with a model it was only partly embedded under |
| The sync lock's timestamp was UTC while every other stamp was local — identical format, no marker, different clocks, so in summer a lock taken 30 seconds ago read as two hours old | 20260804 13:21. `sync.py`'s `stamp` and `_estimate_only`'s price clock both use `datetime.now(UTC)`, matching `lock.py`. Pinned by tests that run under a non-UTC timezone — the first draft used the file's own `run()` helper, which hardcodes `now=`, and would have passed whichever clock the code used |
| The first sync was multi-hour and completely silent — ~2.4 documents/minute, 300 documents over two hours with no output, so "working" was indistinguishable from "hung" | 20260804 13:21. `SyncOptions.progress` is called `(done, total)` after each document; the CLI wires a throttled, self-overwriting line on a TTY when not `--quiet`. An adversarial review caught the closing newline firing only at `done >= total`, so a `[budget]` cap or any early exit left a `\r`-terminated line for the report to print onto — `finish()` is now called unconditionally in a `finally` |
| `uv add "pinakes[light]"` failed in the one place a KB user runs it — a knowledge-base directory has no `pyproject.toml`, so the documented install line exits `No pyproject.toml found` | 20260804 13:10. `docs/GUIDE.md` leads with the two forms that work in a bare directory — `uv init` first, or `uvx` with no install at all. The plain `uv add` lines stay, since a KB inside an existing project is the other real case |
| Same-host lock reclaim was documented in `pnk doctor` and not in the GUIDE, which offered only `--force-unlock` — the destructive remedy — for a symptom the safe path already handles | 20260804 13:10. The GUIDE's troubleshooting row now says a lock left by a dead process **on this host is reclaimed automatically** by re-running `pnk sync`, and bounds `--force-unlock` to another host. It also says to check the process rather than the age, because the lock's clock is UTC and an older KB's manifest is local |
| `corpus-probe-run.md` required a per-kind edge census and no tool emitted one | Shipped 20260804. `edge_census()` reads the count off the same in-memory `Graph` the traversal walks — no re-query, no parallel computation — and always returns every kind, **including the zeroes**, since a kind absent from the output is indistinguishable from a kind at zero. Its own review caught the first version counting hub buckets of one, which would have made `co-located` and `shared-tag` unable to report 0 on any populated corpus — the exact case it exists to surface |
| `docs/STATUS.md`'s header was not gated and drifted four releases — it read `0.4.1` while the roadmap, the PyPI table and `__version__` all said `0.7.1` | `tools/status_header_gate.py`, 20260803 22:43. Parses line 3 for the exact `**Latest release: x.y.z**` shape and compares it against `pinakes.__version__`; a missing, moved or reformatted line fails as loudly as a wrong version. Wired into `check.sh` with its own CI job carrying a negative check |
| `tools/link_density_gate.py` died with a `ValueError` on a non-canonical root — every `/tmp` path on macOS, and running it against a copy is exactly what an executor is told to do | 0.7.1. `census` resolves the root once, so the denominator and the `relative_to` share one base |
| `tools/fragments.py` spliced **two `### Added` headings** into one section, and filed a `Fixed:` entry under `Added` — silent, and it lands in an artifact that cannot be re-uploaded | Fixed with a test (`tests/test_fragments.py`). `_merge_into_section` reuses an existing `### Category` heading, bounded to the anchor's own section so an older release's heading is never written into |
| The local source walk escaped the KB: a `..` in `[sources] include` minted sidecars outside it, an absolute pattern was a bare `NotImplementedError`, and a symlinked directory carried the walk out with no `..` anywhere. Live since before 0.5.0 | 0.7.1, as its own increment. **A fourth defect was found by a test written to pin *correct* behaviour** — a legal `..` landing inside the KB kept the `..` in the document key, so one file reachable two ways indexed once and failed twice |
| `sidecar.py`'s docstring overstated the 1.1 → 1.2 fix | Now says *"three of the four"*, and that `0755` becomes int **755** |
| `CHANGELOG.md` `[0.5.0]` stated one break twice, once over-broadly | One statement, carrying the *uniformly-keyed nested mapping* precision |
| `docs/MANIFEST.md`'s `rel` row credited the user, not `pnk link` | Fixed on the L6 branch |
| `docs/STATUS.md`'s verified-install claim omitted the manifest edit | Rewritten and re-verified against **0.6.0** from the index, 20260801 11:10 |
| Both 🚫 rows listed link-coverage reporting, which shipped in v0.1 | Moot: the links-release row left both tables at the final cut |
| The plan's baseline said 0.4.0 and a stale `main` | Re-baselined at `6421cb1`, 20260801 |
| The verification table named two tests that do not exist | Repointed; `tests/test_verification.py` green |
| L6 named two tests L5b already owned | L6 shipped with distinct names |
| The iteration log was out of chronological order | Sorted, and now in `20260801_0102-links-and-graph-log.md` — 25 rows, verified sorted |
| L6 review 7's freshness test never entered the freshness branch | Review 8b closed it the other way; the prescribed fix would now pin behaviour review 8 replaced |
| L7 shipped without two of its four Docs items | Both fixed before the 0.6.0 tag. **The rule it earned:** the last step before declaring an increment done is to re-read its own Docs list and grep for each sentence the plan quotes |

---

## Not to be fixed — recorded so nobody tries

- **A sidecar carrying its own `%YAML 1.1` directive** is parsed at 1.1, so `country: NO` becomes
  `False`. Frozen in 0.5.0; a `changelog.d/` fragment already recorded it.
- **An integral `!!float`** keeps its tag and gains quotes on rewrite. Same fragment.
- **A uniformly non-string-keyed nested mapping** is accepted and coerced. A stated residual in
  `docs/MANIFEST.md`'s bounds table, not a defect.
- **The `v0.5.0` tag annotation** says "Three breaking changes". Tag annotations are not cleanly
  rewritable and the tag is published; the release body and CHANGELOG are the corrected records.
- **A raw NUL byte reaches user-facing output** from a hand-written `[[links.kb]] path` using the
  `\u0000` escape — unreachable from `argv`, which cannot carry one. Sanitising the path into the
  message would cost the *name what the author wrote* property L6 review 9 exists to protect.
