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

**Six live items as of 20260805 08:15.** Every one came from *building* — the RFC realism corpus, or the graph release measured against it — rather than from reading the code.
**Three are in flight** on branches not yet landed: the `[light]` first-sync error, `pnk doctor`'s absolute paths, and the sync CPU measurement. **Two need a planner decision before anyone builds them** (`pnk init` adoption, and titles), and they say so in their own text.

The list refills from use, so an empty one means nobody has run Pinakes lately, never that it is
finished. Note what is **not** here: the links release is complete and the graph release is
**blocked** at G2's measurement ([`20260729_0256-links-and-graph.md`](20260729_0256-links-and-graph.md)),
so none of these unblocks it — the corpus does
([`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md)).

---

## Live



### 1 · The `[light]` first-sync error prescribes the 2 GB install to a user who chose `[light]`

A first sync on a `[light]` install fails naming `sentence-transformers` — the torch dependency the extra exists to avoid — while `fastembed` is installed and visible. The manifest edit (two `provider` lines) is the actual fix and the message does not mention it, though `README.md` and `docs/GUIDE.md` both do.

**Required:** when the configured provider is missing *and* a registered alternative is installed, name the alternative and the two manifest keys to change. Test: `[light]` present, `sentence-transformers` absent → the message contains `fastembed` and `[embedding]`, and does **not** recommend installing torch.

---

### 2 · `pnk init` cannot adopt a directory that already has content

`_check_target` refuses a non-empty directory, so a KB cannot be initialised inside an existing repository — which is what [`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md) prescribes and what everyone does: create the repo, clone it, then init. A `.git`, a README and a `pyproject.toml` are already "not empty", and the message *"clear this one first"* is alarming when the directory holds the documents.

**Hit three times independently** (probe rehearsal, dogfooding KB, corpus).

**DECIDED 20260805 13:13 — refuse only what would actually be overwritten** ([`20260805_1313-decisions-init-titles-and-grammar.md`](20260805_1313-decisions-init-titles-and-grammar.md)). Drop the blanket emptiness test; keep the `pinakes.toml` and not-a-directory refusals; add a refusal naming any file `init` would write that already exists. The accepted cost is the loss of a cheap typo-catcher. `docs/GUIDE.md` gets the retrofit path.

---


### 3 · Every document is titled by its filename

All 300 sidecars carry `title: rfc9110` rather than *"HTTP Semantics"*, so search results are unreadable. `sync` mints the title from the filename when the document has no Markdown H1 — correct for Markdown, useless for anything else.

**Deliberately not worked around** by the corpus agent: hand-writing 300 titles would have hidden the finding, and editing the RFC text would have broken the licence position (verbatim reproduction is the grant).

**DECIDED 20260805 13:13 — keep the filename fallback, and report it** ([`20260805_1313-decisions-init-titles-and-grammar.md`](20260805_1313-decisions-init-titles-and-grammar.md)). The first-line heuristic is **rejected**: an RFC's first line is `Internet Engineering Task Force (IETF)`, so it would mint confidently wrong titles at scale into sidecars the user then commits, which is worse than a filename that is visibly a filename. **Required:** a `pnk doctor` check reporting documents whose `title` equals the filename stem *as minted* — detection, never guessing, and a nudge rather than a FAIL. `title` stays the user's field.

---

### 4 · `pnk doctor` prints the operator's home directory

Absolute paths in output that is the natural thing to paste into an issue. **Required:** print paths relative to the KB root where they are inside it. Minor, but it is the one command whose output gets shared.

---


### 5 · The first sync may be using one core of ten, and nobody has measured which

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

### 6 · Numbered plain-text headings are not detected, and the graph result is bounded by it

**Decided by the user 20260805: detection first (shipped), then an opt-in grammar. This is the
second half.** `chunk.py` runs heading detection for `markdown` only; every other source type takes
`_plain_blocks`, which records no `heading_path` at all. So a rigidly sectioned `.txt` corpus is
chunked size-based however structural the manifest says it is.

**Why it is not cosmetic.** `heading_path` is what `in-section`, `parent` and `child` derive from.
On the RFC corpus those three of seven edge kinds derived **zero** edges — and that is the corpus
the expansion channel's gate was measured against. The honest reading of that gate is *"the edge
kinds that worked did not help this corpus"*, never *"graph structure does not help"*
([`20260804_1442-decision-g3-go.md`](20260804_1442-decision-g3-go.md)).

**Required:** numbered-heading detection for plain text behind a **new `[chunking] strategy`
value**, opt-in — never a change to what `structural` does today. `manifest.py` already has the
extension point: `CHUNK_STRATEGIES = ("structural",)`, validated by `table.choice(...)`.

**Two of the four blocking questions are DECIDED 20260805 13:13** ([`20260805_1313-decisions-init-titles-and-grammar.md`](20260805_1313-decisions-init-titles-and-grammar.md)):

* **Scope: the `text` source type only.** Markdown is not in scope because it already works —
  `chunk.py` dispatches on source type and `markdown` already takes `_markdown_blocks`.
  **`pdf` is disabled here, never dismantled:** nothing built for PDF is removed, narrowed or
  weakened, and a PDF is extracted, chunked and indexed exactly as it is today. It simply does not
  gain this grammar yet, and the precondition for extending it is **strong structure detection**.
  If building this seems to require changing existing PDF behaviour, that is a spec defect — stop
  and report it.
* **`requires_pinakes`: a floor is set, explicitly.** Without one an older Pinakes rejects the new
  value as an *unknown value*, which reads as a typo — the exact confusion G4 exists to prevent.
  A build below the floor must produce the floor message, **not** the unknown-value message. The
  accepted cost is that older builds cannot read a KB using the value; they would have refused it
  anyway, with a worse message.

**Two remain the planner's, and are still open:**

1. **The value's name.**
2. **False positives, written before the rule is fitted.** `1.` at line start is also an ordered
   list. The predicate must be stated first and tested against the RFC corpus second, never derived
   from it.

**The eval risk is unusually well bounded, and that is worth using.** `tests/demo-kb` is Markdown,
so a plain-text-only grammar **cannot** move the golden set — which makes `CLAUDE.md`'s "changing
retrieval needs eval justification" provable rather than arguable here. Run it anyway and report
before/after: **no movement is the expected result, and movement would itself be the finding.**

**Re-running the graph gate afterwards is a separate decision.** It costs ~2 h of CPU embedding plus
a `schema_version` 3 rebuild, and the anti-circularity discipline is not optional if it happens —
questions stay frozen, nothing is tuned after seeing a number, and `expand-in-degree` stays
reported, never gated.

---

## Closed — recorded so nobody reopens them

| Was | Closed by |
|---|---|
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
