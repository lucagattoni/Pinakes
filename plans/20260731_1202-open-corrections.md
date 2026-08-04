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

**Six live items as of 20260804 13:21, all unclaimed.** Every one came from *building* the RFC
realism corpus rather than from reading the code — which is what that corpus was for. The
interrupted-sync trio that stood here closed with `20260804_1218-interrupted-sync`.

The list refills from use, so an empty one means nobody has run Pinakes lately, never that it is
finished. Note what is **not** here: the links release is complete and the graph release is
**blocked** at G2's measurement ([`20260729_0256-links-and-graph.md`](20260729_0256-links-and-graph.md)),
so none of these unblocks it — the corpus does
([`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md)).

---

## Live


### 1 · `strategy = "structural"` degrades to size-based chunking in silence

**Measured on the RFC corpus:** **106 806 chunks, every one with `heading_path` empty** — over 300 RFCs, the most rigidly sectioned plain text in existence. The heading grammar is Markdown-shaped; RFC section numbering is not, so nothing matches and the strategy quietly becomes size-based. Nothing warns: `grep heading src/pinakes/doctor.py` returns nothing.

**Two consequences, and the second is why this is not cosmetic.** Citations lose their heading component for the whole corpus. And `heading_path` is what `in-section`, `parent` and `child` derive from — **three of G3's seven edge kinds derive zero edges on a corpus whose headings were not recognised**, which a graph measurement would read as "structure does not help".

**Required:** a `pnk doctor` check reporting the share of chunks with an empty `heading_path`, WARN past a threshold, naming `[chunking] strategy` and the corpus's format. Detection, not a new grammar — extending the grammar to RFC numbering is a separate decision. **The check must count over chunks actually in the index**, never re-chunk a sample: a check that re-derives its own input is checking a copy.

---

### 2 · The `[light]` first-sync error prescribes the 2 GB install to a user who chose `[light]`

A first sync on a `[light]` install fails naming `sentence-transformers` — the torch dependency the extra exists to avoid — while `fastembed` is installed and visible. The manifest edit (two `provider` lines) is the actual fix and the message does not mention it, though `README.md` and `docs/GUIDE.md` both do.

**Required:** when the configured provider is missing *and* a registered alternative is installed, name the alternative and the two manifest keys to change. Test: `[light]` present, `sentence-transformers` absent → the message contains `fastembed` and `[embedding]`, and does **not** recommend installing torch.

---

### 3 · `pnk init` cannot adopt a directory that already has content

`_check_target` refuses a non-empty directory, so a KB cannot be initialised inside an existing repository — which is what [`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md) prescribes and what everyone does: create the repo, clone it, then init. A `.git`, a README and a `pyproject.toml` are already "not empty", and the message *"clear this one first"* is alarming when the directory holds the documents.

**Hit three times independently** (probe rehearsal, dogfooding KB, corpus). **Required:** a decision, then an implementation — the guard exists to stop `pnk init` scribbling over someone's directory, so the answer is probably *refuse only when the directory is already a KB, or when a name it would write already exists*, rather than a blanket emptiness test. Whatever is chosen, `docs/GUIDE.md` gets the retrofit path.

---


### 4 · Every document is titled by its filename

All 300 sidecars carry `title: rfc9110` rather than *"HTTP Semantics"*, so search results are unreadable. `sync` mints the title from the filename when the document has no Markdown H1 — correct for Markdown, useless for anything else.

**Deliberately not worked around** by the corpus agent: hand-writing 300 titles would have hidden the finding, and editing the RFC text would have broken the licence position (verbatim reproduction is the grant). **Required:** a decision on whether a non-Markdown first line may become a title, recorded either way. This is a *quality* finding, not a defect — `title` is documented as the user's.

---

### 5 · `pnk doctor` prints the operator's home directory

Absolute paths in output that is the natural thing to paste into an issue. **Required:** print paths relative to the KB root where they are inside it. Minor, but it is the one command whose output gets shared.

---


### 6 · The first sync may be using one core of ten, and nobody has measured which

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

## Closed — recorded so nobody reopens them

| Was | Closed by |
|---|---|
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
