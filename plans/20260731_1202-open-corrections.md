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

**Eleven live items as of 20260804 08:30** — ten of them from building the RFC realism corpus, which is what that corpus was for. **Earlier note: one live item, raised 20260804 05:00** — the first defect the RFC realism corpus surfaced, and it
destroys user work.

**Earlier state, for the record: no live items as of 20260804 04:20.** The one item raised on 20260803 was built and merged the
same evening. Beyond it there is no Pinakes code work: the links release is complete, the graph
release is **blocked** at G2's measurement ([`20260729_0256-links-and-graph.md`](20260729_0256-links-and-graph.md)), and what
unblocks it is a corpus ([`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md)).

---

## Live

### 1 · `corpus-probe-run.md` requires a per-kind edge census and no tool emits one

**Raised by the planner against its own requirement, 20260804 09:25.**
[`20260803_2239-corpus-probe-run.md`](20260803_2239-corpus-probe-run.md) requires the run report to
carry *"a per-kind edge census — how many edges each kind derived"*, because on the RFC corpus
`in-section`, `parent` and `child` derive zero and a single reachability number would hide that.

`tools/reachable_ceiling_probe.py` emits six counts and **no edge totals at all**. The graph it
derives in memory knows them; nothing prints them. A requirement with no instrument gets improvised
at the moment it is needed, by whoever is standing there, which is how a measurement stops being
comparable between runs.

**Required:** the probe prints, and puts in `--json`, the edge count per derived kind for the run —
including the kinds that derived **zero**, which are the whole reason the requirement exists. A kind
absent from the output is indistinguishable from a kind at zero, so absent is not acceptable.

**Test:** on a fixture with no `heading_path`, the census reports `in-section: 0` **present in the
output** rather than omitted; and the census total reconciles with the edges the traversal actually
walked, so it cannot be a separately-computed number that drifts from the graph it describes.

---

### 2 · The sync lock's timestamp is UTC; every other timestamp is local

**Verified at source 20260804 08:30.** `lock.py:138` writes `datetime.now(UTC).strftime("%Y%m%d %H:%M")`; `sync.py:709` writes `datetime.now().strftime(...)`. **Identical format, no marker, different clocks.** In Europe/Rome in August a lock taken 30 seconds ago reads as **two hours old**.

**Why it is the most dangerous of these:** the age is the evidence a user weighs before `pnk sync --force-unlock`, and the documented remedy for a stale lock. A lock that looks two hours old but is live gets force-unlocked *against a running sync*.

**Required — direction settled 20260804 11:32 by the project-wide move to UTC: make both UTC.** `lock.py` is already right; `sync.py:709` and `sync.py:808` are what change. This was previously written as *prefer local for both*, on the reasoning that a human compares the manifest's stamp against a wall clock; that reasoning is superseded, and the fix is now the cheaper half. A test that sets a non-UTC `TZ`, takes a lock, and asserts the reported age is under a minute; it fails today under any non-UTC zone and passes under `TZ=UTC`, which is why the test must set the zone rather than inherit it.

---

### 3 · `strategy = "structural"` degrades to size-based chunking in silence

**Measured on the RFC corpus:** **106 806 chunks, every one with `heading_path` empty** — over 300 RFCs, the most rigidly sectioned plain text in existence. The heading grammar is Markdown-shaped; RFC section numbering is not, so nothing matches and the strategy quietly becomes size-based. Nothing warns: `grep heading src/pinakes/doctor.py` returns nothing.

**Two consequences, and the second is why this is not cosmetic.** Citations lose their heading component for the whole corpus. And `heading_path` is what `in-section`, `parent` and `child` derive from — **three of G3's seven edge kinds derive zero edges on a corpus whose headings were not recognised**, which a graph measurement would read as "structure does not help".

**Required:** a `pnk doctor` check reporting the share of chunks with an empty `heading_path`, WARN past a threshold, naming `[chunking] strategy` and the corpus's format. Detection, not a new grammar — extending the grammar to RFC numbering is a separate decision. **The check must count over chunks actually in the index**, never re-chunk a sample: a check that re-derives its own input is checking a copy.

---

### 4 · The `[light]` first-sync error prescribes the 2 GB install to a user who chose `[light]`

A first sync on a `[light]` install fails naming `sentence-transformers` — the torch dependency the extra exists to avoid — while `fastembed` is installed and visible. The manifest edit (two `provider` lines) is the actual fix and the message does not mention it, though `README.md` and `docs/GUIDE.md` both do.

**Required:** when the configured provider is missing *and* a registered alternative is installed, name the alternative and the two manifest keys to change. Test: `[light]` present, `sentence-transformers` absent → the message contains `fastembed` and `[embedding]`, and does **not** recommend installing torch.

---

### 5 · `pnk init` cannot adopt a directory that already has content

`_check_target` refuses a non-empty directory, so a KB cannot be initialised inside an existing repository — which is what [`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md) prescribes and what everyone does: create the repo, clone it, then init. A `.git`, a README and a `pyproject.toml` are already "not empty", and the message *"clear this one first"* is alarming when the directory holds the documents.

**Hit three times independently** (probe rehearsal, dogfooding KB, corpus). **Required:** a decision, then an implementation — the guard exists to stop `pnk init` scribbling over someone's directory, so the answer is probably *refuse only when the directory is already a KB, or when a name it would write already exists*, rather than a blanket emptiness test. Whatever is chosen, `docs/GUIDE.md` gets the retrofit path.

---

### 6 · The first sync is multi-hour and completely silent

~2.4 documents/minute on CPU; 300 documents ran over two hours with no output. **"Working" is indistinguishable from "hung"**, which is what makes findings 1 and 2 expensive: a user who cannot tell reaches for the remedy, and the remedies destroy work.

**Required:** periodic progress on a TTY — documents done / total and a rate. Not a spinner: the number is what distinguishes slow from stuck. Silent when not a TTY, so `--ci` and hook output stay clean.

---

### 7 · Every document is titled by its filename

All 300 sidecars carry `title: rfc9110` rather than *"HTTP Semantics"*, so search results are unreadable. `sync` mints the title from the filename when the document has no Markdown H1 — correct for Markdown, useless for anything else.

**Deliberately not worked around** by the corpus agent: hand-writing 300 titles would have hidden the finding, and editing the RFC text would have broken the licence position (verbatim reproduction is the grant). **Required:** a decision on whether a non-Markdown first line may become a title, recorded either way. This is a *quality* finding, not a defect — `title` is documented as the user's.

---

### 8 · `uv add "pinakes[light]"` fails where a KB user runs it

The documented install line needs a `pyproject.toml`; a fresh KB directory has none, so it exits `No pyproject.toml found`. **Required:** `docs/GUIDE.md` shows the form that works in a bare directory (`uv init` first, or `uvx`), since that is where a new user is standing.

---

### 9 · `pnk doctor` prints the operator's home directory

Absolute paths in output that is the natural thing to paste into an issue. **Required:** print paths relative to the KB root where they are inside it. Minor, but it is the one command whose output gets shared.

---

### 10 · Same-host lock reclaim is documented in `doctor` and not in the GUIDE

The resumed corpus sync reclaimed its own stale lock and continued incrementally — `105 unchanged`, nothing re-embedded. That is the *good* behaviour, and `docs/GUIDE.md` offers only `--force-unlock`, which is the destructive one. **Required:** GUIDE says a lock left by a dead process on this host is reclaimed automatically, and `--force-unlock` is for another host.

---

### 11 · `pnk doctor`'s model-coherence remedy destroys an interrupted sync's work

**Found by using Pinakes, not by reading it** — the RFC realism corpus, 20260804, on a first sync
of 300 documents killed at ~106 by an unrelated process death.

**Current.** `sync.py:964` writes the embedding identity keys with `set_meta` **after** the document
loop and `_scan_linked_kbs`, then commits. An interrupted first sync therefore leaves `meta`
carrying `schema_version` and nothing else, and `pnk doctor` reports:

```text
FAIL model coherence: the index does not match the configured model — embedding_dim: index
     has '(absent)', manifest says '384'; embedding_model: index has '(absent)', manifest
     says 'BAAI/bge-small-en-v1.5'; embedding_provider: index has '(absent)', manifest says
     'fastembed'.
     → Run `pnk sync --rebuild`. Embeddings are meaningless across models: a KB that silently
       returned results here would be returning garbage.
```

**Why it is a defect and not a warning.** The check cannot distinguish two states it treats
identically: *the model changed under the index* — genuinely fatal, `--rebuild` correct — and *the
first sync never finished* — benign, and `--rebuild` is **the worst available action**, discarding
every embedding that survived. On this corpus that was about an hour of CPU. A first-time user who
follows the printed remedy loses all of it, and the remedy is stated imperatively with a rationale
that makes it sound unavoidable.

**Required.** Split the two states on **absent vs different**, because they are distinguishable:

* Identity keys **absent** → the index was never completed. This is not a coherence failure; report
  it as its own check (WARN, not FAIL) whose remedy is `pnk sync` — incremental, and it keeps the
  work already done. Say that it keeps it.
* Identity keys **present and different from the manifest** → the existing FAIL, unchanged, remedy
  `pnk sync --rebuild`.
* A partial `meta` — some identity keys present, some absent — is neither, and must not silently
  fall into the benign branch. Treat it as the FAIL.

**Tests.** One per branch, and a test asserting the absent-key path's remedy does **not** contain
`--rebuild` — that string is the whole defect, and a test that only checks the check's *name* would
pass with the destructive remedy still printed.

**Do not "fix" this by writing the identity keys earlier.** They are written after the loop
deliberately; moving them would make a half-built index claim coherence with a model it was only
partly embedded under, which is the failure this check exists to catch. The defect is in the
diagnosis, not the write order.


---

## Closed — recorded so nobody reopens them

| Was | Closed by |
|---|---|
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
