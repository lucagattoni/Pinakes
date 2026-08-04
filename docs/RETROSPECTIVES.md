# Retrospectives

> ℹ️ **Version numbers below reflect the convention in use when this was written.** Unbuilt
> work is now **named, not numbered** ([STATUS.md](STATUS.md)). This record is left as it was.

One section per increment of the project's build plans (`plans/`), written during that increment's
retrospective review (the workflow is in [`CLAUDE.md`](../CLAUDE.md)). Only findings worth keeping
land here: a real defect the review caught, or a fact that would be expensive to rediscover. Fixes
themselves live in the commits; this file records *what was learned*.

Every heading and claim here carries `YYYYMMDD HH:MM` (local, 24h) — several increments can
land in one day, and a bare date loses their order.

Severity follows the design review's scale: **HIGH** — wrong behaviour or false confidence;
**MEDIUM** — would block or mislead; **LOW** — worth remembering, not urgent.

The seven **pre-implementation** design review passes are at the foot of this file:
[Design review passes 1–7](#design-review-passes-17-pre-implementation).

## Start here — by what you are about to touch

Added 20260801 01:11. Forty-odd sections in date order is an archive, not something anyone reads
before starting work — so this table is the way in. It is keyed on **what you are about to do**, not
on when the lesson was learned, and it is deliberately short: only the classes that have recurred.
A rule that hardened into a standing instruction lives in [`CLAUDE.md`](../CLAUDE.md); this file is
where the evidence for it is.

| About to… | Read | Because |
|---|---|---|
| **write a test** | I2, L3–L4, L5, L5b | The recurring defect of this whole project: *an assertion satisfied by something other than the property it names*. A test that could not fail; a field with no assertion is a field that can be a constant; a tidy fixture defeats a mutation test; test the **discriminating** case, not the two sides separately; a fixture can be right for the wrong reason and hide the defect it was written for |
| **claim a test is mutation-verified** | L5b, L3–L4 | *"Mutation-verified" is a per-assertion claim, never a per-commit one.* A failing test proves the mutant is caught, never that it is caught for the stated reason — under `-x`, or when the failure lands on an earlier assertion, the one encoding the claim never runs |
| **touch a sidecar or any YAML** | I5, L5b | Writes must be rename-atomic. An explicit empty value was silently deleted on round-trip. Swapping a YAML library is not a swap; `existing[:] = keep` wipes ruamel's comment metadata outright; a comment before a sequence entry belongs to the entry **above** it; a warning is not an error, and a library that downgrades one is changing behaviour |
| **add a gate or a check** | I7a, L3–L4, the eval-harness section | A gate that has never been shown to fail is a claim, not a check. A gate that never reads the artifact it guards is checking a copy. The free-path gate was defeated by its own harness. The exit criterion was the thing nobody ran |
| **write an error message** | L3–L4, I8 | An error message is part of the interface; a remedy inside one is a **claim**, and it was false. A fix applied to one surface is half a fix |
| **change retrieval** | I9, the eval-harness section, I6 | Three defects under one green suite. Overlap could push a chunk past `max_tokens`; heading text landed in no chunk at all |
| **edit a doc, a plan or an exclusion list** | L5b, I9, the shared-file section | An exclusion list is a set of claims, and claims rot. A fix instruction can carry its own defects. Four silent `str.replace` no-ops in one session — an edit that does not match is an edit that did not happen. A clean auto-merge is not a correct merge |
| **cut a release** | the post-v0.1 housekeeping section | A CHANGELOG entry and a `__version__` are only claims: 0.1.0 had both for two days with no tag, no release and nothing published. Verify with `git tag -l`, `gh release list`, and the index itself |
| **trust CI** | the cross-platform scanned-fixture section | `main` was CI-red for three pushes and nobody noticed. Green proves the tests ran, never that they can detect the defect |

**The pattern across all of them**, and the reason this file is worth keeping: the worst finding of a
review pass is usually inside the *previous* pass's fix. That has held from I5 through L6's thirteen
rounds, and it is why a fix is re-reviewed rather than assumed.

## I1 — Package skeleton, errors, CLI dispatch (20260725 13:40)

**MEDIUM — `PinakesError` could not be pickled, so an error crossing a process boundary raised
`TypeError` instead of reporting itself.** `Exception.__reduce__` replays `self.args` through
`type(self)`, but every subclass here takes its own constructor arguments (`NotImplementedYetError`
takes a command name and an increment), so rebuilding blew up on the missing `remedy` keyword.
Confirmed by probe before fixing, not reasoned about. Fixed with an explicit `__reduce__` routing
through a module-level helper. *Lesson: an exception class with a non-`(message,)` constructor is
unpicklable by default — the failure only surfaces under xdist/multiprocessing, i.e. exactly when
something else has already gone wrong.*

**MEDIUM — the subcommand dispatch target sat on the public namespace attribute `run`.** Any future
command declaring `--run` would have silently overwritten the function `main()` then calls. Moved to
a reserved `_runner` dest with a test asserting no public namespace attribute is ever callable.
*Lesson: `set_defaults` shares one namespace with every option; anything the framework itself
dispatches on must be underscore-reserved.*

**LOW (reference) — measured `ty` 0.0.63 against `pyright` strict on a 6-defect probe.** pyright
caught 6/6; ty caught 1/6 (the `str | None` → `len` error, with better diagnostics); ruff caught the
unused import. ty currently has no strict mode: it accepts unannotated defs and `Any` leakage, which
is precisely what `pyright` strict is in this project for. Decision (user): keep pyright as the gate,
add `uv run ty check` as a fast pre-check. *Worth re-measuring when ty leaves beta — the gap is a
missing feature, not a design difference.*

## I2 — ULID identity and `pnk://` URIs (20260725 14:05)

**MEDIUM — a test that could not fail.** `test_an_unresolved_uri_cannot_be_formatted` asserted
`not hasattr(parsed, "__str__") or "pnk://" not in str(parsed)`. Every object has `__str__`, so the
first clause is always false and the second only checked a dataclass repr — the test would have
passed even if `ParsedUri` had grown a full URI renderer. Replaced with a precise structural
assertion (`"__str__" not in ParsedUri.__dict__`, present on `PnkUri`) that names the static
guarantee as primary. *Lesson: a green test asserting a tautology is worse than no test — it buys
false confidence, and `hasattr(x, "__dunder__")` is almost always one.*

**MEDIUM — a docstring claimed more than had been verified.** `ids.py` said python-ulid rejects the
ambiguous Crockford letters `I`, `L`, `O`, `U`; only `I` and `U` had actually been probed. All four
are now probed and the claim is stamped with the time of that probe. *Lesson: when writing "verified
X", the set being claimed must be the set that was run — a partially-probed claim reads identically
to a fully-probed one.*

**MEDIUM — two `except Exception` blocks** wrapped calls whose only expected failure was
`InvalidIdError`, so a `TypeError` from a future refactor would have been re-raised as "this is not
a valid KB ULID". Narrowed, and ruff's `BLE` ruleset enabled so the class of mistake cannot be
written again.

**LOW — internal helpers were public.** `parse_kb_id_for_uri`/`parse_doc_id_for_uri` took an odd
`(raw, segment)` pair and had no business in the module's API; renamed to `_kb_segment`/`_doc_segment`.

**LOW — the scheme is matched case-sensitively** while the `self` sentinel is not. Deliberate (URIs
are machine-written, `self` is hand-typed) but undocumented; now stated in the module docstring and
covered by a test.

## I3 — Manifest parsing and KB root discovery (20260725 14:25)

**MEDIUM — an explicit empty value silently became the default.** `timezone = ""` in `[budget]` read
back as `"UTC"`, because the accessor ended in `or "UTC"`. Same shape accepted `name = ""` and
`model = ""` outright. All three confirmed by probe. Empty strings are now rejected with a named
key, and the default only applies when the key is *absent*. *Lesson: `value or default` conflates
"missing" with "empty", and for user configuration those mean opposite things — one is silence, the
other is a mistake worth reporting.*

**MEDIUM — narrowing by `assert`.** Two call sites used `assert value is not None` to convince the
type checker, and a `_require` fallback built a `Path` out of a table name for an error that could
never fire. Python strips asserts under `-O`, so the "guarantee" was a comment with syntax. Replaced
with three explicit accessors — `string` (required, returns `str`), `optional_string`, `string_or` —
which give the type checker what it needs without a runtime claim. *Lesson: when a type checker
needs an assertion, the API shape is usually wrong; fixing the signature beats asserting.*

**MEDIUM (docs) — the required/optional split existed only in code.** `[chunking]`, `[retrieval]`,
`[rerank]` and `[budget]` are optional with documented defaults while `[kb]`, `[sources]` and
`[embedding]` are mandatory — a user-facing contract that `docs/DESIGN.md` §2.1 never stated. Added
there in the same change, per the repo's docs rule.

**LOW — a test caught a real error-message defect.** Validation errors read
`[<root>.retrieval]`; the table path is meant to name what the user would type. The failing test was
fixed in the source, not the assertion.

## I4 — SQLite storage, FTS5 triggers, vector loading (20260725 14:45)

**MEDIUM — `load_vectors` peaked at roughly twice the array it returned.** It collected every
embedding into a list and `vstack`ed it: measured 669 MB for 200k×384, where the result is 307 MB.
At 1M chunks that is ~3.4 GB against the ~1.5 GB §3.1 states, so the design's own memory claim was
wrong for its only shipping tier. Now counts first and fills a preallocated array, with a test
asserting peak < 1.6× the result. *Lesson: "load it all into one contiguous array" has two
implementations that differ by a factor of two, and only one of them matches what the design
promises.*

**MEDIUM — a non-database file produced a raw `sqlite3.DatabaseError`.** `PRAGMA journal_mode` is
the first statement to touch the file, so it failed before any schema check could run, and the user
got `file is not a database` with no remedy. Opening is now wrapped. *Lesson: the friendly check
ran second; the pragma that configures the connection is what actually opens the file.*

**MEDIUM — chunk insertion restarted ordinals at 0 on every call**, so a second call for the same
document hit the `UNIQUE (doc_id, ordinal)` constraint. The operation is really a wholesale replace
— re-chunking must not leave old chunks searchable — so it now deletes first and is named for that.
Both this and the one above were caught by tests written in the same increment.

**MEDIUM — pickling collapsed every error subclass to `PinakesError`.** I1's `__reduce__` fix
rebuilt through the base class, so `StoreError` came back as `PinakesError` and any `except
StoreError` on the far side would miss it. Now rebuilds the original class via `__new__`, keeping
message and remedy. *Lesson: a fix that makes an object survive a round trip is not the same as one
that makes it survive intact — check identity, not just contents.*

**LOW — `DOCUMENT_STATES`/`LINK_ORIGINS` duplicated the DDL's `CHECK` constraints** with nothing
tying them together. A test now fails if they drift.

## I5 — Sidecars (20260725 14:55)

**HIGH — sidecar writes were not atomic.** `path.write_text` truncates before it writes, so a crash
or full disk mid-write leaves a truncated sidecar — and the one thing a sidecar carries that cannot
be recomputed is the document's permanent ULID. Losing it breaks every inbound `pnk://` link, and no
later command can repair it, because nothing else knows what the id was. Now writes to a sibling
temporary and `os.replace`s over the target. *Lesson: "the truth is in files" makes every file write
a durability question; the ones holding unrecoverable identity deserve rename-based atomicity.*

**MEDIUM — an explicit empty value was silently deleted on round-trip.** `tags: []` and
`provenance: {}` vanished, because `write` tested truthiness. This is exactly the lesson I3 recorded
one increment earlier — absent and empty are different statements — and I repeated it in a module
whose entire contract is "do not lose what the user wrote". The `Sidecar` now records which known
keys the file carried. *Lesson: a recorded lesson only helps if it is re-read while writing the next
thing that could break the same way; the pattern to watch for is any `if value:` guarding output.*

**MEDIUM — a hedged test assertion.** `assert made.title == "my research notes.md" or made.title ==
"my research notes"` accepted either answer because I had not checked which one `Path.stem` gives.
Two plausible values means the test asserts nothing about the one that is correct. Pinned to the
real value. *Lesson: an `or` in an equality assertion is the tautology smell from I2 wearing a
different hat.*

**LOW — `KNOWN_KEYS` could drift from what `write` emits**, which would be silent data loss for a
key the module claims to understand. A round-trip test now asserts every known key comes back.

## I6 — Structural chunking (20260725 15:10)

**HIGH — overlap could push a chunk past `max_tokens`.** The carried-over tail was prepended
unconditionally, so `overlap = 9` with `max_tokens = 10` produced 12-token chunks (probed). Those
are exactly the chunks the model truncates at encode time, silently — the failure §4.6 exists to
prevent, reintroduced by the feature meant to improve context. The carry is now dropped when it
would breach the limit, and a parametrised test sweeps the whole `(max_tokens, overlap)` matrix.
*Lesson: the earlier test used `overlap=5, max_tokens=15` and passed; one comfortable ratio proves
nothing about the boundary. Sweep the matrix when two parameters interact.*

**HIGH (design, found by a test) — heading text landed in no chunk at all.** Headings were consumed
as pure structure, so a word appearing only in a heading was unsearchable: the FTS index sees chunk
text and nothing else. `heading_path` looked like it covered this, but it is a separate column that
v0.1 never searches. Headings are now part of the first chunk beneath them, and `docs/DESIGN.md`
§4.6 says so. *Lesson: "the information is still recorded somewhere" is not the same as "the
information is still retrievable"; check which column the query path actually reads.*

**MEDIUM — sentence splitting silently gave up on text without punctuation.** A long run with no
`.!?;:` produced one oversize piece that was emitted whole. Now falls back to words, then to
characters for a genuinely unbroken run (a hash, a base64 blob).

**LOW — piece offsets came from a running total** that `finditer`'s empty end-of-string match could
desynchronise from the source. Now taken from `match.start()`, so spans are exact by construction
rather than by accounting.

**LOW (test-design) — a stand-in counter can be wrong in the direction that hides the bug.** The
word-counter says a 400-character unbroken run is one token; every real tokenizer disagrees. The
character-cut path needed a token-dense counter to be exercised at all.

## I7 — Embedding backends and reranker (20260725 15:35)

**MEDIUM — a fake that could never disagree.** The test backend was registered as
`FakeBackend(section.dim)`, so it reported whatever width the manifest claimed — making the
dim-mismatch check, the one guard against storing incomparable vectors, impossible to test. Pinned
to a fixed width. *Lesson: second time in three increments that a stand-in was wrong in exactly the
direction that hides the bug (I6's word-counter was the first). A fake that derives its answer from
the input under test asserts nothing.*

**MEDIUM — an assertion guessed at a real model's behaviour.** `count_tokens("retrieval augmented
generation") > 3` was written before any model had been run; the real BPE count is exactly 3, and
the test failed the moment weights were cached. Rewritten to assert the *relationship* (longer text
→ more tokens) rather than a number I had invented. *Lesson: when a test crosses into a real
dependency, assert properties, not remembered values.*

**Verified against real weights** (not inferred): fastembed's `BAAI/bge-small-en-v1.5` gives
`dim=384`, `max_seq_length=512` derived from the tokenizer's truncation config, normalised float32
vectors (self-cosine 1.0), and it wrote to `~/.cache/huggingface/hub` rather than
`$TMPDIR/fastembed_cache`. `BAAI/bge-reranker-base` ranked a relevant passage above an irrelevant
one, `-0.28` vs `-7.85`.

**LOW (reference, matters for I14) — reranker scores are raw logits, not probabilities.** They came
back around `-0.28` and `-7.85`, not in `[0, 1]`. The illustrative thresholds in §2.1
(`low_below = 0.31`, `high_above = 0.62`) read like normalised scores; calibration must either fit
against the logit scale or squash it first. Recorded now so I14 does not quietly fit thresholds to
the wrong scale.

## I8a — Sync pairing core (20260725 15:50)

**MEDIUM — a model-test guard checked the wrong half (found in I7, surfaced here).** The
`model`-marked tests skipped when weights were absent, but not when the *backend* was absent. Model
weights live in a shared machine-wide cache, so a worktree without the `light` extra installed still
saw them, ran the test, and failed with `BackendMissingError` instead of skipping. Only noticed
because a second worktree had a different install set. Now both halves are checked. *Lesson: a skip
condition is a claim about the environment, and machine-wide state (a shared cache) is not evidence
about the local one.*

**Design note, not a defect — `DuplicateIdsError` raises rather than returning an action.**
`plans/20260725_1317-v0.1.md` lists it among `pair()`'s return values. Raising is better: the condition is fatal
for the whole run, and an action every caller must remember to inspect is one a caller will
eventually forget. Recorded because it is a deliberate divergence from the reviewed plan.

**What the exhaustive table bought.** Writing one test per §6.4 row, then the compound cases the
table cannot express, is what forced the two decisions the design left implicit: a sidecar
disagreeing with the index wins (`docs/` is truth, the index is derived), and a whole-picture rule
must be order-independent — asserted directly by pairing the same snapshot walked forwards and
backwards.

## I8b — `pnk sync`, locking, and the rebuild swap (20260725 16:20)

**HIGH — the rebuild swap left the old database's `-wal`/`-shm` behind.** Design pass 2 fixed the
missing checkpoint; this is the other half nobody had noticed. SQLite names the companions after the
*path*, not the inode, so after `os.replace` they sit beside the **new** index claiming to be its
write-ahead log — the exact corruption the checkpoint was added to prevent, reintroduced by the
rename that followed it. They are now removed after the swap. *Lesson: an atomic rename is atomic
for one file; a WAL database is three files with correlated names, and correctness arguments about
"the file" quietly skip the other two.*

**MEDIUM — a read-only SQLite connection creates `-wal` and `-shm` itself.** This masked the bug
above: the test read the index before asserting the companions were gone, and the read created them.
Worth knowing beyond this test — §4.7 says the MCP server opens the index read-only "so it cannot
write", which remains true of the *data*, but the server does create files in `.pinakes/`. Any
future check that treats "no companions present" as evidence of a clean shutdown is wrong.

**MEDIUM — a leaked connection inside a test helper.** The helper was a generator, and a caller
using `next()` left it suspended, so its `finally: close()` never ran. The symptom appeared in an
unrelated assertion about rebuild. Now returns a list and closes immediately. *Lesson: a generator
with cleanup in `finally` only cleans up if it is exhausted; for a fixture-shaped helper, return the
list.*

**LOW — ty caught a loose test shim pyright had been told to ignore.** The monkeypatched
`__import__` took `*args: object`; pyright was silenced with an inline ignore, ty flagged the real
mismatch. Typing the shim to `__import__`'s actual signature satisfied both and deleted the
suppression. *First time the "fast pre-check" found something the gate had been told to skip —
noted, since I1's decision assumed ty would only ever be faster, not different.*

## I9 — Retrieval pipeline (20260725 16:55)

**MEDIUM — vector search padded its candidate list with zero-similarity passages.** `argsort` returns
every row, so a query sharing no direction at all with a passage still ranked it, and with nothing
better available those passages reached the user. Real models rarely produce an exact zero, so this
would have hidden until a sparse or domain-shifted corpus hit it. Non-positive cosines are now
dropped. *Lesson: "return the top N by similarity" is only sane while similarity means something;
N is a cap, not a quota to fill.*

**MEDIUM (design gap, decided here) — the design said the filter set included "date", and no date
column existed.** Documents carry `mtime`; a sidecar's `created` is optional, and filtering on an
optional field silently excludes every document that lacks it — worse than having no filter. The
filter is now `mtime`, and §4.1 says so. *Lesson: when the design names a filter dimension, check
which column actually holds it for **every** row, not just the well-formed ones.*

**LOW — `sqlite3.Row` hands back `Any`, which erased types through the whole hydration path.** Rows
are now narrowed once into a small frozen dataclass instead of being cast field by field at each use
— pyright strict was the thing that made this visible.

**Worth recording: FTS5 escaping is not optional.** `AND`, `OR`, `NEAR`, `*`, `"` and a bare
apostrophe are all parser syntax; a user typing `it's` would otherwise crash the query. Quoting each
word as a literal and joining with `OR` keeps recall — an implicit `AND` drops a passage for one
missing word, which is exactly the recall the vector half is there to provide.

## I10 — `pnk init`, the `notes` template, `pnk search` (20260725 17:15)

**MEDIUM — warnings were being printed and ignored.** Turning `filterwarnings = ["error"]` on
immediately produced two real problems that had been sitting in the summary: `importlib.abc.
Traversable` is deprecated and **removed in Python 3.14**, so this project would have broken on the
next Python it claims to support; and several tests leaked SQLite handles, surfacing as
`ResourceWarning` raised from wherever the garbage collector happened to run — never the test that
leaked. *Lesson: a warning nobody has to act on is a warning nobody reads. Making them errors cost
one afternoon of cleanup and bought a Python upgrade.*

**MEDIUM (process) — I committed with a failing gate.** The last edit before committing introduced a
`reportUnusedFunction` on an autouse fixture; I had run pyright before that edit, not after. Fixed
in the retrospective commit. *Lesson: the gate belongs immediately before `git commit`, not
"recently" — and "recently" is exactly what it felt like at the time.*

**LOW — the test fixture violated a manifest invariant I had written myself.** Setting
`max_tokens = 60` while leaving `overlap = 64` was rejected by I3's cross-key validation. Pleasant
confirmation that the check earns its place: the first thing it caught was its own author.

**Design note — the template ships `[retrieval.confidence]` commented out.** `plans/20260725_1317-v0.1.md` had
already decided this, and building it made the reason concrete: `pnk init` cannot know anything
about the corpus the user is about to add, so any threshold it wrote would be a number with no
provenance. `confidence: unknown` until they fit their own is the only honest default.

## I11 — `pnk doctor` (20260725 17:35)

**MEDIUM — ty found a second real defect hiding behind a `pyright: ignore`.** I had typed a dict as
`dict[Path, object]` and silenced the resulting argument-type complaint rather than fixing the
annotation. That is the same shape as I8b's finding, and it is now a pattern: **an inline
suppression is where a type error goes to be forgotten.** Every `pyright: ignore` in `src/` has been
removed as of this increment; the two that existed were both hiding something real, not appeasing a
checker that was wrong.

**Worth stating — doctor is where several design promises stop being rhetorical.** §3.1's linear
scan ceiling, §6.2's link-coverage ceiling, §4.2's `unknown` confidence, §6.4's orphan reporting and
§6.5's lock are all "we will tell you rather than pretend" commitments. None of them is honest
unless something actually prints them, and until this increment none of them did. The test that says
every non-OK check must carry a remedy is the one enforcing the spirit of it: a report that says
"problem" without saying "do this" is just anxiety.

**Design note — an uncalibrated KB is a WARN, not a FAIL.** Reporting `confidence: unknown` is the
honest behaviour the design chose, so a KB doing exactly that is not broken; it is uninformative,
and the warning says so with a pointer to §4.2 and §7.

## I12 — `pnk install-hooks` (20260725 17:50)

**Confirmed end to end, with a real commit: the three-hook split does what design pass 6 claimed.**
`docs/note.md` and `docs/note.md.pnk.yaml` land in the *same* commit, and `git status` is clean
afterwards. That was the whole argument for splitting the hooks, and it is now a test rather than a
paragraph.

**LOW — the pre-commit half needs no embedding backend at all**, which only became obvious when a
subprocess `pnk` ran without the test's fake registered and the sidecar half still worked. That is
the right shape: minting an id is cheap and belongs before the commit; embedding is slow and belongs
after it. Worth recording because it means a KB whose backend is not installed can still commit
documents with correct, permanent ids — the failure is deferred to indexing, exactly where §4.5 says
a core-only install should feel it.

**LOW (test hygiene) — a "tree is clean" assertion failed on files the fixture never committed.**
The hooks were fine; the setup was. An assertion about cleanliness is only meaningful from a clean
starting point.

**HIGH (process) — I committed with red gates for the second time, and now understand why.** The
pattern `uv run pyright 2>&1 | tail -1 && git commit …` reports the exit status of `tail`, which is
always 0. Both checkers were failing and the commit went through looking green. This is not
carelessness that can be fixed by resolving to be careful: the shell was reporting success. Added
`check.sh`, which runs every gate under `set -e`, and pointed `CLAUDE.md` at it. *Lesson: if a
safety check is a pipeline, the thing you are checking is the last command in the pipe. Make the
gate a script that exits non-zero, and the mistake becomes unavailable.*

## I13 — `pnk serve` (MCP) (20260725 18:15)

**The boundary is testable, so it is tested.** §4.7's claim is that an agent cannot reach outside
the KBs the server was pointed at. Three tests hold it: `pinakes_get` refuses a path, a traversal
string and an unknown ULID identically; a KB that exists on disk but was not passed on the command
line is unreachable and the error says arguments select by name or ULID *never by path*; and a
document deleted since it was indexed cannot be fetched.

**MEDIUM — `stat()`-based staleness detection works, and the test proves the thing the design
argued about.** After a `--rebuild` swap the server returns the *new* documents. The design's
reasoning (an open handle pins the old inode, so `meta.build_id` read through it would report the
old build forever) is now backed by a test that would fail if someone "simplified" it back.

**LOW — pyright strict flags decorator-registered functions as unused.** `@mcp.tool()` returns
something pyright cannot tie back to the name, so all three tools looked dead. Rather than
suppressing it, they are now registered in an explicit loop — which also makes the set of exposed
tools one readable line instead of three annotations. *A suppression would have been the third one
this session that turned out to be hiding something; making the code say what it means was cheaper.*

**LOW — another leaked connection, caught by warnings-as-errors from I10.** A `Server` built inline
inside a `pytest.raises` block was never closed. This is the third leak that setting only found;
before I10 it would have been invisible.

## I14 — Demo KB, golden set, eval harness, calibration (20260725 19:00)

**HIGH — the two error rates were a flattering zero, and it took looking at real numbers to see
it.** The first eval run reported `false_abstain: 0.0` and `false_confidence: 0.0`. Both were
vacuous: the demo KB had no fitted thresholds, so confidence was *always* `unknown`, so neither
error could ever be counted. A CI gate on false-confidence would have passed forever, and passed
loudest exactly when calibration was missing. Added `confidence_coverage` to the metrics, and made a
drop in it a regression in its own right. *Lesson: a perfect score on an error rate is a claim that
deserves the same suspicion as a failing one — check the denominator before believing the ratio.*

**HIGH — the first threshold formula made `low` unreachable.** `low_below = min(answerable)` came
out at -9.885 on real logits, a floor almost nothing falls below, so the system could essentially
never abstain and false-abstain was zero *by construction*. Both thresholds are now fitted from the
**unanswerable** distribution — the only outcomes known absolutely — with `low_below` its median and
`high_above` a high percentile. Only visible because the fit was run against real reranker scores
rather than a fake's tidy 0-to-1 range.

**The measured cost of the confidence heuristic, stated plainly: false-confidence is 0.25.** One
no-answer question in four still gets a confident answer, because the score distributions genuinely
overlap (answerable -9.9..7.9, unanswerable -8.3..-2.7). §4.2 promised this would be measured rather
than assumed; it is now in `docs/DESIGN.md`'s risk table with its date and models. Two caveats are
recorded with it: eight no-answer questions is a small sample, and the thresholds are fitted on the
same set they are scored against, so it is a floor rather than a measurement.

**MEDIUM — the test fixture copied `.pinakes/` and ran the 64-dimensional fake against a
384-dimensional index.** I4's stored-vector width check refused it, which is exactly right and
briefly baffling. Generated state is now excluded from the copy. *A good sign for the guard: the
first thing it caught was a developer, not a user.*

**LOW — ruff caught `assert ... or True` in my own test.** The tautology lesson from I2, third
appearance, this time found by a linter rather than by reading. `SIM222` earns its place.

## I15 — CI, packaging, 0.1.0 (20260725 19:30)

**MEDIUM — the version lived in two places.** `pyproject.toml` and `__init__.py` each carried it,
which is one place to forget on every release. Hatch now reads it from the module, and the release
workflow refuses a tag that disagrees with it — a mismatched tag is the kind of thing nobody notices
until an install pulls the wrong thing.

**The wheel smoke test earned its place immediately.** `pnk init` reads its template through
`importlib.resources`, so a packaging mistake is invisible in the source tree and total after
install. Running `pnk init` from the *built wheel* — and asserting the manifest, the golden-set stub
and the `.gitignore` all appear — is the only check that would have caught it.

**Publishing is left as a human step, on purpose.** The release workflow runs on a `v*` tag and
nothing else, and PyPI trusted publishing has to be configured in the PyPI UI first. Neither the tag
nor the publish happens automatically from a merge: an irreversible, outward-facing action should
need someone to mean it.

**§8's v0.1 sentence, walked item by item: 17/17 present.** The plan asked for that walk explicitly
at this increment rather than trusting the accumulated sense that everything got done.

---

## Post-v0.1 release housekeeping (20260727 15:35)

Not an increment — a session that merged the graph research, closed out the v0.1 plan, and cut the
releases that had never been cut. Recorded because four of its findings are the kind that cost more
to rediscover than to write down, and one is a mistake made *in this session* by the person writing
this.

**The 0.1.0 release existed in every artifact except the ones that matter.** `__version__` said
`0.1.0`, the CHANGELOG had a dated `[0.1.0]` section, and its footer linked
`releases/tag/v0.1.0` — while `git tag -l` was empty, no GitHub release existed, and PyPI returned
404. The release workflow fires only on a `v*` tag, so nothing had ever been built or published.
*Lesson: a version number is a claim, and a claim in a CHANGELOG is the easiest kind to believe.
Verify a release the way a stranger would — `git tag -l`, `gh release list`, the package index —
never by reading the file that asserts it.*

**A docs-only merge turned `main` red.** `ruff format --check .` formats Python fenced blocks
*inside Markdown*, so an igraph snippet in a research doc failed the Format gate. The instinct that
a documentation change cannot break the build is wrong in this repo, and the gate is the only
arbiter. Now stated in `CLAUDE.md` and in the README's Development section.

**Merging from inside the feature worktree silently does nothing, and the tag lands off-`main`.**
Running `git merge --ff-only <branch>` while `cwd` is that branch's own worktree merges the branch
into itself — "Already up to date" — and the subsequent `git push origin main` reports "Everything
up-to-date" because the local `main` ref never moved. The `git tag` that followed pointed at a
commit reachable only from the branch, so `v0.1.2` existed, was pushed, and was **not an ancestor of
`main`**. Both commands *succeeded*; nothing failed loudly. *Lesson: merge from the primary
checkout, and before creating a release assert the lineage —
`git merge-base --is-ancestor vX.Y.Z main`.*

**The README was the only surface that lied.** An audit against the running CLI found four claims
contradicting the code: `pnk ask --deep` described as existing (it is a v0.4 plan), a budget ledger
described as tracking spend (nothing writes one), install lines pointing at a PyPI package that
404s, and the headline KB diagram built on a `.pdf` — the one file type v0.1 cannot ingest.
`cli.py` and the CHANGELOG were scrupulous in the same places, both saying "planned for v0.4".
*Lesson: prose drifts toward the design and away from the build, because the design is what the
author is thinking about. The check that works is running the commands the README shows.* The
documented `[light]` install had the same shape: co-equal in the README, broken at the first `sync`
because `pnk init` always stamps sentence-transformers.

**A promise in a section with no increment number belongs to nobody.** `plans/20260725_1317-v0.1.md` asked for a
CI grep gate keeping paid-API clients out of `src/` under "Verification of the whole". No increment
owned it, so it never shipped — while the invariant it guards is the one `CLAUDE.md` calls
non-negotiable. Now enforced, and verified in both directions: it passes on the current source and
catches a planted `import openai`. *Lesson: every promised check carries an increment number and a
path, or it is a wish.*

## Planning v0.2 (20260727 17:00)

**A review pass is a change, and a change needs its own review.** Adversarial pass 2 over
`plans/20260727_1543-v0.2.md` returned 5 HIGH — and **four of the five were created by pass 1's own fixes**, not
survivals of pass 1's findings. Pass 1 correctly rejected a per-page cost estimate as an
order-of-magnitude under-reservation against whole-document requests; the shape it introduced
instead was quadratic in input and stopped fitting the model's context window at ~166 pages, so a
100-page document reserved ~$375 and the feature failed closed with a refusal no user could satisfy.
*Lesson: never implement from the revision that a review produced. Two passes are the floor for a
document of this size, and each pass reviews the previous pass's fixes, not only the original.*

**A threshold that only exists in `tests/` protects nobody.** Both fitted floors — the one that
triggers paid re-extraction and the one that stops a paid run on an already-healthy PDF — were
committed to `tests/pdf-corpus/baseline.json`, which no wheel installs, while three runtime
consumers on a user's own KB depended on them. The fail-closed rule was also stated for one floor
and not the other, so the guard against paying to re-extract a healthy PDF was silently disabled
everywhere. *Lesson: a value a user's runtime reads is package data, and every fail-closed rule is
stated and tested once per consumer, not once per document.*

**An append-only ledger needs a way to say "this never happened".** Every paid call wrote a
reservation before the call and a reconciliation after, with an unreconciled reservation counted at
its reserved amount. A call that *raised* — timeout, 429, 5xx — therefore left spend that nothing
could ever close, in a file `CLAUDE.md` forbids editing: a handful of transient failures would lock
a user out of a monthly budget permanently. *Lesson: a two-state protocol over an append-only log
needs a third state. Reserve → reconcile **or void**.*

**Timestamps were composed instead of read.** Four "verified on 20260727 17:34" claims were written
at 17:00 — 34 minutes in the future. Session context carries a date but never a time, so any `HH:MM`
not read from the clock is invented, and an invented one lands in the future about half the time. A
timestamp exists to say how fresh a verified claim is, so a fabricated one is a false evidence claim
rather than a formatting slip. *Lesson: run `date "+%Y%m%d %H:%M"` and paste the result; one call
covers a batch of edits. Now a rule in CLAUDE.md.*

## Planning v0.2, pass 3 (20260727 20:23)

**Three review passes, and each one's largest source of new HIGHs was the previous pass's fixes.**
Pass 2 found that four of its five HIGHs were created by pass 1's repairs; pass 3 found the same of
five of its twelve. Reviewing a plan is a change to the plan, and a change needs its own review.
*Lesson: budget for the review of the review. A plan is not ready because the last pass was clean —
it is ready when a pass over the **current** text is clean.*

**What broke the cycle was method, not effort.** Five of pass 3's twelve HIGHs were found only by
checking the plan against `src/` and against arithmetic — never by reading the plan, however
adversarially. `--rebuild` discards the index and reads its "before" snapshot from the *empty* new
database (`sync.py:231-241`), so a guarantee recorded only in `index.db` was invisible to the one
command that most needed it. A trace test asserted "exactly one chunk contains this offset" while
`chunk.py:239-269` prepends the carried overlap and takes `start` from the *carried* piece, so
chunk *n+1* begins inside chunk *n* whenever a block splits. A filter test named `tags` as a column;
it is `json_each` over a `NOT NULL DEFAULT '{}'` field, so the assertion was true by schema for
every row and would have passed on a corpus with no tags at all. A raster gate promised "a moved
word must fail" against a threshold its own arithmetic puts about four lines of text away. And the
docs sweep enumerated README *additions* while four sentences already in the README are falsified
by the release — the same defect, and the same count, as the audit at 0.1.2.
*Lesson: a consistency pass cannot find a claim that is internally consistent and externally false.
Run three narrow passes instead of one wide one — code-reality (resolve every claim about `src/`
against the file), arithmetic (recompute every stated number), and promise-ledger (walk every
enumerated bound, flag, floor, gate and amendment asking "which increment makes this true, and
which test proves it"). Each found HIGHs the wide pass missed.*

**A threshold you cannot fit yet is not a threshold — ship the metric, defer the loop.** Two passes
each tried to fit the completeness audit's floor, and each picked a pair that was not the pair it is
applied to, because the applied pair needs paid model output that does not exist at fitting time.
The second attempt would have fitted over a population including a fixture the reader contract
requires to *raise*, landing the floor near zero and leaving the audit inert on every installed
copy. *Lesson: when a threshold's correct fitting data cannot exist yet, that is the finding. Ship
the measurement, report it, and let the release that produces real data fit the number.*

**"Bypasses module X" is a claim about an import graph, and it was false.** The paid extractor was
documented as bypassing `layout.py` — while calling `normalise()`, which lives in it. The version
constant covering that module was then deliberately excluded from the paid fingerprint, so a
whitespace or ligature change would have missed every *free* cache entry and silently **hit** every
paid one, with the coherence check unable to see it. *Lesson: when two consumers share one stage,
version that stage separately rather than arguing about which of them "really" runs it.*

## Planning v0.2, pass 4 — three narrow passes (20260727 20:57)

**Splitting one wide review into three narrow ones is what finally found the structural defects.**
Passes 1–3 were each a thorough adversarial reading, and each one's largest source of new HIGHs was
the previous pass's fixes. Pass 4 ran instead as a *code-reality* pass (resolve every claim about
`src/` against the file), an *arithmetic* pass (recompute every stated number), and a
*promise-ledger* pass (walk every enumerated flag, floor, gate, constant and amendment row, asking
only "which increment makes this true, and which test proves it"). Together they returned 19 HIGH —
and almost none of them were things a fourth general reading would have caught.
*Lesson: a reviewer reading for coherence finds incoherence. Defects that are internally consistent
and externally false need a pass that leaves the document: to the source, to a calculator, or to a
checklist. Run those as separate passes, because each is a different kind of attention.*

**A review pass's own fixes are the highest-risk text in the document.** Four of pass 2's five HIGHs
came from pass 1's fixes; five of pass 3's twelve came from pass 2's; and two of pass 4's came from
*inside* pass 3's fixes — a `pnk budget` ordering bug fixed by assigning the edit to an increment
that lands earlier, and a missing-amendment-row sweep that added a row for one copy of a sentence
and missed two others. The arithmetic pass caught the sharpest case: pass 3 replaced a raster
tolerance that could not detect a moved word with a different tolerance that also could not detect a
moved word. *Lesson: never ship the revision a review produced. Re-review the fixes specifically,
and prefer a method that cannot be fooled by the same reasoning that produced them.*

**"The code already does X" is a claim, and this project keeps getting it wrong.** Verified against
`src/`: `write_sidecar` runs only for newly minted documents, so a plan built on "sync writes the
sidecar" had no write path for the case it cared about; `pnk init --ci` was designed in DESIGN and
never built, while an increment was written to modify it; CI installs `--extra light` and runs the
model tests in the `check` job, so a new matrix leg would triple them rather than skip them; and
`--index-only`, which the hooks run, is contractually forbidden from writing into `docs/` at all.
*Lesson: every plan sentence about existing behaviour carries a `file:line`, or it is a guess.*

**A threshold needs enough data to have chosen it.** The running-head threshold `T` was documented
as fitted over a stratum of 3-page fixtures — where per-document recurrence can only be 1/3, 2/3 or
1, so every `T` in (1/3, 2/3] reproduces the corpus identically. The value was real, the fit was
not. *Lesson: state a fitted threshold's resolution alongside its value. If the corpus cannot
distinguish 0.4 from 0.6, "fitted" is a claim the data does not support — enlarge the fixture or
call it a chosen constant.*

## I1 — extras, the extractor seam (20260727 22:28)

**An explicit, textual exit criterion is not met just because the surrounding tests feel thorough.**
The plan's own words were "the `filterwarnings` probe and both marker predicates get named tests" —
the probe got tests; `pdf_runnable()`/`paid_runnable()` did not, and nothing caught it until the
review grepped for their names and found only their own definitions. Twenty-odd other tests passing
made the increment *feel* covered. *Lesson: when a plan states a test-coverage exit criterion in so
many words, grep for the named thing before calling the increment done — a feeling of thoroughness
is not the same claim as a named test existing.*

**A synthetic probe path that doesn't mirror the real call site's resolution semantics passes on the
easy case and is silently wrong on the common one.** `doctor._could_match_pdf` checked whether
`sources.include` could ever match a PDF by testing patterns against a probe path prefixed with the
root's own name (`"docs/__pdf_probe__.pdf"`) — but `walk_sources` applies each pattern via
`root.glob(pattern)`, where `root` is *already* resolved, so a pattern is relative to it, never to
the KB root. The bug was invisible in-repo because the one test written for it used `**/*.pdf`,
which happens to match regardless of the extra prefix; a bare `*.pdf` — an equally ordinary
manifest — silently reported `OK: not installed (no .pdf in include)` on a KB that would, in fact,
fail its very next `pnk sync`. *Lesson: a synthetic probe is only as good as its fidelity to the real
resolution path, and one test shape that happens to tolerate an error is not evidence the error
doesn't exist — test the shape closest to the literal documented example, not only the most generic
one.*

**The docs-in-the-same-commit rule missed two files because neither is named a "user-facing
surface."** DESIGN.md and CLAUDE.md were amended correctly in the same commit that made CI a
three-leg matrix; README.md's and the Makefile's own `make install` comments, both reading "as CI
does," were not — the exact class of drift a 0.1.2 audit already caught once for this project
(above). Neither file is a flag, a manifest key, or a `--help` string, so neither felt like it was in
scope. *Lesson: "describes CI/build behaviour in prose" is as much a user-facing surface as a CLI
flag — grep README.md and the Makefile for the thing that changed, not only `cli.py` and
`DESIGN.md`.*

## I2 — the synthetic PDF corpus (20260727 23:43)

**HIGH — a gate rendered at a resolution that made its own threshold unreachable.** The scanned
stratum's tolerance is "more than 300 pixels differing by more than 32 levels", derived for a page
rastered at 150 dpi. The comparison called `page.render(scale=1.0)` — pdfium's default of 1 px per
*point*, i.e. **72 dpi** — which downsamples the stored 150 dpi image ~2× before diffing. That
shrinks the page from 2,105,025 px to 485,316 and a moved word's delta from several hundred pixels
to well under a hundred: the gate would have passed exactly the change it exists to catch, while its
docstring claimed a 2× margin. The docstring also named A4 (1240×1754) for a corpus that is US
Letter throughout, so *both* factors in the derivation were wrong and they partly cancelled, which is
why the number still looked plausible. *Lesson: a tolerance is meaningless without the resolution it
is measured at — state both, and assert the comparison runs at the fixtures' own. When a derived
constant is checked, re-derive it from the code that consumes it, not from the prose that
introduced it.*

**HIGH — `textwrap` invented a hyphen the ground truth then rendered as a phantom space.**
`textwrap.wrap(..., break_long_words=False)` leaves `break_on_hyphens=True`, so it split the
existing compound "spine-out" across two lines; the ground truth joins lines with a space, yielding
"spine- out" — a string no correct extractor could ever produce, in the one file whose entire job is
to be what a correct extractor produces. The same word appears correctly in 16 other places in the
corpus, so the corpus contradicted itself. *Lesson: when a helper's default silently edits content,
the edit shows up wherever the content is re-joined by a different rule. Hyphenation is exercised
deliberately here by fixtures that place their own hyphens; it must never arrive by accident.*

**HIGH — the soft-hyphen fixture's ground truth dropped the first four words of its own page.** The
expected text began "cooperation agreement…" while the page reads "The clerk filed the coopera-
tion agreement…". Written by hand while thinking about the *joined word*, not about the page. Every
automated check still passed: the fixture had a ground truth, the counts matched, the bytes
regenerated. *Lesson: nothing in a corpus's own test suite can tell you a ground truth is wrong —
only reading it beside the page can. Budget for that reading explicitly; "the tests are green" is
not evidence about the one thing tests cannot check.*

**MEDIUM — two claims with no enforcement, in a file full of enforcement.** "Pillow is dev-only,
never core, never an extra" was stated in the commit message, in `conftest.py` and in a test
docstring — and adding Pillow to `[project.dependencies]` left the whole suite green, while the
structurally identical claim for pypdfium2/anthropic *is* tested. Separately,
`pdf_runnable()`'s three-part predicate had a test walking false→false→false→false→true that never
turned the corpus clause off once both libraries were on, so deleting that clause entirely still
passed. *Lesson: for an N-part predicate, assert each part is individually load-bearing by turning
it off from the all-true state — a monotonic walk up to true proves only the last flip mattered.*

**LOW — the same quantity was stated twice, differently, and neither figure was right.** The commit
message said ~440 KB (that is `du`'s block-rounded disk usage of the whole directory), the CHANGELOG
said ~370 KB (unreconstructable), and the budgeted quantity — the PDF bytes `test_byte_budget` sums
— is 266 KiB. *Lesson: when a number appears in two documents, both are guesses unless one of them
was measured; measure once and paste the same figure.*

## I3a — extraction core, pure: chars to ordered, de-furnished text (20260728 00:52)

**HIGH — column clustering compared each candidate to the wrong reference point, letting drift
accumulate past its own threshold.** `reading_order` grouped blocks into columns by comparing each
new block's `x0` to the *last-placed* member of the current column, not the column's start. Sorted
by `x0`, each step can individually stay under `_COLUMN_GAP` while the column's accepted range walks
steadily rightward — so a genuine third column, far enough from the first to be its own column, could
still merge into the second's cluster one small step at a time. Caught with a reproduction script
laying out three real columns and reading the wrong (merged) order back. *Lesson: "cluster by gap"
needs a fixed anchor — the cluster's start, not its most recent member — or the gap check bounds a
single step while saying nothing about total drift.*

**HIGH — y-band clustering by `round()` put a hard wall at every half-integer.** `strip_running_heads`
grouped running-head candidates into y-bands with `round(block.y0)`. Two renderings of one genuine
running head at 750.4 and 750.6 pt — sub-point jitter, far smaller than any real layout difference —
round to 750 and 751: two distinct, non-recurring signatures, each individually under the suppression
threshold even though the line recurs on every page. Fixed with tolerance-based clustering (shared
anchors, `abs(y0 - anchor) <= _RUNNING_HEAD_Y_TOLERANCE`) matching `_LINE_TOLERANCE`'s own approach
elsewhere in the same file. *Lesson: `round()` is a clustering method with an invisible discontinuity
at every `.5`; anything claiming "the same, allowing for rendering jitter" needs a tolerance compare,
never a shared rounding function, or the false-boundary cases won't show up until real PDFs hit them.*

**HIGH — the import-purity test only recognised `import X`, not `from X import Y`.** `_imported_names`
walked `ast.ImportFrom` nodes and recorded `node.module` only. `from pinakes.extract import layout` —
the exact style `layout.py` itself already uses for its own dependency on `ExtractedText` — resolves
to the module name `pinakes.extract`, plus the *separately* recorded name `layout`; the check for
`"extract.layout"` matched neither, so `textpolicy.py` could have imported `layout.py` this way and
`test_textpolicy_is_pure_and_does_not_import_layout` would have stayed green. Fixed by folding
`ImportFrom.names` into fully-qualified names (`f"{module}.{alias.name}"`) alongside the bare module.
*Lesson: an import-graph test written against `ast.Import` habits misses `ast.ImportFrom` entirely
unless it's built and then attacked with the exact style the file under test itself uses.*

**MEDIUM — a page's dominant font size was voted on by character, not by line, so a verbose heading
could out-vote the body size it was meant to be measured against.** `_mode_font_size` originally took
one entry per *character* in `blocks_from_chars`; a short body line has few characters, a heading with
a long title has many, and counting per-character let a sufficiently wordy heading tip the "mode" size
to its own, inverting `line_size > body_size` for the very line it should have flagged as a heading.
Fixed to take one entry per *line* (`[max(c.font_size for c in line) for line in lines]`). *Lesson:
"most common value" needs its unit stated explicitly — voting by the wrong unit of measurement
produces a plausible-looking answer that is wrong in exactly the cases with more text, which are also
the cases most likely to be headings.*

**MEDIUM — a symmetric rule was checked on one side only, twice, in different functions.**
`join_hyphenation` skipped a block as a join source when it was `suppressed`, but not when it was
itself a `heading` — so a heading ending in a hyphen could be joined into as a *source*, even though
the same function already refuses to join *into* a heading as a continuation. Separately, `assemble`
silently produced a truncated document if a block's `page_index` ever fell outside `range(len(pages))`
— a caller bug that should be loud (I3b's future pdfium adapter is the only caller that will ever
construct `page_index`), rather than a quietly shorter `ExtractedText` with no error at all. Both fixed
in the same pass: the heading check now runs both ways, and `assemble` raises `RuntimeError` on an
unplaced block. *Lesson: when a function enforces "never X across a boundary," check both directions
explicitly — a docstring that says "either side" is a claim, not a guarantee, until both sides have a
test — and prefer a loud failure over a silently smaller correct-shaped result whenever "silently
smaller" is a shape invariants alone can't distinguish from correct.*

**LOW — fixing the "no filesystem access" gap introduced a fragile substring check, caught before it
shipped.** Extending the import-purity test to also assert no `os`/`pathlib`/`io` import used the same
`marker in name` substring style already used for PDF libraries (`"pypdfium2" in name`). Re-deriving
what that check would actually match against layout.py's real imports first — rather than trusting
that it passed — showed `"io" in name` matches `typing.Optional` and `collections.abc.Iterable`
(`...t-i-o-n...`), neither of which touches a filesystem; the check would have false-positived the
moment either was ever imported. Fixed to match on the module boundary (`name == module or
name.startswith(f"{module}.")`) before it was ever committed. *Lesson: two-letter module names are not
safe substring needles — `os`/`io` collide with ordinary English inside almost any longer identifier
— so "does this file import X" must match on the dotted-name boundary, never bare containment.*

## I3b — the pypdfium2 adapter, extraction-quality metrics, and the two fitted floors (20260728 03:06)

**HIGH — an empty page list is not an empty request; it is pypdfium2's spelling of "every page."**
`slice_pages(path, first, last)` clamped `last` to the document's own last page but never validated
that `first` still fell before it. Whenever `first > last` after clamping — a reversed range, or a
`first` entirely beyond the document — `range(first, last_clamped + 1)` is empty, and an empty list
is falsy in Python: pypdfium2's own `import_pages` treats a falsy `pages` argument identically to
`pages=None`, its own spelling of "import every page." Verified directly against the real 12-page
`baseline-12p.pdf`: `slice_pages(5, 2)`, `slice_pages(100, 200)` and `slice_pages(20, 30)` each
silently returned all 12 pages, no exception. `slice_pages` is stated as I7b's future paid-path
request unit; a future off-by-one computing a page window (the last window of a document whose
length isn't a multiple of the window size is the obvious candidate) would have silently sent the
*entire* document to a paid API instead of a small slice — a cost-control failure, not merely a
wrong answer, in a project whose one hard invariant is that the free path stays free and spending is
never accidental. Fixed with explicit validation (`first >= 0`, `first <= last_clamped`) before the
range is ever built, raising `ValueError`. *Lesson: an empty collection is not automatically "no
items requested" to the function receiving it — some APIs (documented or not) treat empty/`None`
identically as "unfiltered," and a range-clamping function must validate the range is still
non-empty itself, not merely non-negative.*

**MEDIUM — "wide relative to the page" and "spans multiple columns" are not the same fact, and only
one of them is safe to test for.** `reading_order`'s spanning-block detection was measured against
exactly one fixture (`two-column-b.pdf`'s caption, 79% of the page's content span, against a 42%
maximum for any genuine column line) and shipped as a fixed fraction, `_SPANNING_WIDTH_FRACTION =
0.6`. An independently-constructed asymmetric layout — a narrow sidebar beside a much wider main
column, a real and common shape, not a contrived one — put the main column's own lines at 77% of
the page's content span with nothing in it actually overlapping the sidebar at all; the
width-fraction test misread every line of the wider column as spanning and interleaved the two
columns line by line, silently, with no error. Fixed by replacing the global-width test with a
geometric one: a block is spanning only if its own `x1` reaches at or past the *next* column's own
`x0` — genuinely bridging into that column's territory, which the caption does (its `x1` passes the
right column's `x0`) and the wide sidebar-adjacent column does not (there is nothing to its own
right to reach into). Both the original caption case and the new asymmetric-column case are now
committed regression tests. *Lesson: a measurement taken from one fixture is a fact about that
fixture, not evidence the derived threshold generalises — check whether the underlying mechanism the
threshold approximates (here, "does this block's own geometry actually overlap another column's")
can be tested directly instead, before shipping the approximation.*

**MEDIUM — a fitting function that raises on a missing upper bound but silently guesses at a missing
lower bound is not applying one policy, it is applying two, only one of which is stated.**
`fit_running_head_threshold` raised loudly when no true-positive recurrence was ever observed, but
silently fell back to `max_true_negative = 0.0` when no true-negative was ever observed — and a
*lower* fallback threshold makes `strip_running_heads` more aggressive, so this fallback was
assuming the best case (no decoy content ever recurs) with no evidence for it, dormant only because
the current corpus happens to have 76 true negatives. Made symmetric: both empty cases now raise.
Refactored the pure midpoint arithmetic out of the corpus-walking function
(`threshold_from_fractions`, taking fraction lists directly) specifically so both raise paths are
covered by a direct unit test, not only reachable in principle through a synthetic corpus directory.
*Lesson: check every "if empty, fall back to X" for whether X is a measured true value (`0.0`
non-whitespace characters *is* the true yield of a page with no native text layer — the sibling
floor's own fallback, left alone) or merely a plausible-sounding guess standing in for missing data —
only the former is safe to leave silent.*

**MEDIUM — every extraction-quality metric whitespace-flattens its input by design, which means a
duplicated-newline regression is invisible to the very gate meant to catch regressions.** The
`\r`/`\n`-character fix (dropping embedded line-break characters that were duplicating `assemble()`'s
own inter-block separator) shipped with zero regression coverage anywhere in the suite: reverting it
and re-running every test file, plus the real `make pdf-eval` gate end to end, produced zero
failures, because `score_document`'s own documented design whitespace-flattens both extraction and
ground truth before scoring *any* of the five metrics. Added a structural test asserting the raw,
unflattened extraction contains no `"\n\n"` — verified to actually fail against the reverted code
before being trusted. *Lesson: "every metric flattens whitespace by design" is a correct, deliberate
choice for what those metrics should measure, and also a standing blind spot for anything whose only
symptom is whitespace — a fix in that category needs its own structural test, in a file that doesn't
flatten, or it ships permanently unguarded.*

**LOW, bundled — three findings from the same review, each small alone.** `slice_pages` with a
negative `first` leaked a raw `pdfium.PdfiumError` instead of the module's own `ExtractionError`
(resolved by the same upfront validation as the HIGH finding above, which now catches it before
pdfium is ever reached). `test_check_script.py`'s guard test asserted three substrings existed
*somewhere* in `check.sh`, which stayed green even after deliberately replacing the real `make
pdf-eval` call with a no-op while leaving the explanatory comment above it untouched — rewritten to
match the actual `if`/`then`/`else`/`fi` block and assert *where* each string falls (inside `then`,
absent from `else`), verified to fail against the gutted version before being trusted. `Rate`'s
`numerator`/`denominator` were typed `float` though every call site produces an `int` (character,
word, and pair counts, and sums of the same) — corrected to `int`, the type they actually are, with
no behavioural effect found. *Lesson, shared: "does this test still pass if I break the thing it
claims to guard" is a cheap, five-minute check worth running on every new test before trusting it —
two of these three would have shipped a false sense of coverage without it.*

## Cross-platform scanned-fixture rendering — `main` CI-red since I2, unnoticed for three pushes (20260728 08:13)

**HIGH — `./check.sh` passing locally was silently substituted for "CI is green," and nobody was
checking which one had actually been verified.** I2's merge, I3a's merge, and I3b's merge each
pushed to `main` believing the suite was green, because each one *was* green — on macOS, the only
platform any of them had run on. `gh run list` (prompted by the user asking to check GitHub
Actions, not by any check of my own) showed all three runs had actually failed on
`check (light pdf)` / `check (light pdf claude)`, with the identical signature every time:
`test_scanned_regeneration_within_tolerance` — `scanned-clean: 8006 pixels differ by >32 levels`.
Three consecutive merges landed on a red `main` and every one of them was reported to the user as
successfully shipped. *Lesson: "the local gate is green" and "CI is green" are different claims —
one is evidence for the other, not a substitute for it, and the project's own standing rule (check
actual CI status before building on top of a branch) applies with equal force to checking it after
pushing to one.*

**Root cause, confirmed empirically rather than assumed.** Every text fixture referenced `/BaseFont
/Helvetica` with no embedded font program (`pdfwriter.py`, since I2), relying on the PDF reader's
own substitution for a font it doesn't have. pypdfium2 ships platform-specific prebuilt binaries;
macOS has a real Helvetica installed, `ubuntu-latest` does not, so pdfium substitutes a different
font on each — metrically compatible (identical word-wrap, identical line breaks) but with
different glyph outlines. The scanned stratum rasterizes `baseline-12p` through pdfium *at
fixture-generation time*, baking whichever platform generated it into the committed PDF, so CI's
own regeneration (on a different platform) could never match. Confirmed, not theorized: a Docker
`ubuntu:24.04` container reproduced CI's exact number (8,006 px) on the first attempt, and a diff
heatmap of the two renders showed every changed pixel sitting exactly on a glyph edge — same text,
same word positions, same line breaks, different anti-aliasing. Measuring all ten scanned pages
found cross-platform noise ranging 507-8,262 px depending on how much text and how much the
contrast reduction already suppressed it (`scanned-low-contrast` came in far lower than
`scanned-clean`, consistent with the tolerance test's own documented noise-floor behavior).

**The obvious fix (raise the tolerance) was rejected on evidence, not instinct.** The measured
noise ceiling (8,262 px) sits far closer to the test's stated detection target — a single moved
word, "a small fraction of a page" per the test's own docstring — than to the documented
whole-page-shift signal (33,451 px) the 300 px threshold was originally sized against. Raising
`MAX_CHANGED_PIXELS` above the noise ceiling would have unblocked CI immediately, but a real
single-word regression is plausibly smaller than 8,262 px, meaning a tolerance wide enough to
absorb cross-platform noise would very likely also have absorbed exactly the class of regression
this test exists to catch — silently, with no way to tell from a green gate. Presented three
options (raise the tolerance / scope the test to one platform / embed a real font) with honest
pros and cons rather than picking unilaterally, since it's a public-repo, shared-CI-affecting
change to a previously "verified" threshold. Fixed at the root instead: `pdfwriter.py` now embeds
a subsetted TrueType font (`tests/pdf-corpus/fonts/LiberationSans-Subset.ttf`, SIL OFL 1.1 —
Liberation Sans specifically for its Helvetica/Arial metric compatibility, so none of
`generate.py`'s hand-placed coordinates needed to change) instead of a bare base-14 name, so every
platform rasterizes the same outlines regardless of what fonts it has installed. Re-running the
identical Docker reproduction after the fix measured 0 pixels changed across every scanned page —
not merely under tolerance, bit-for-bit identical. *Lesson: when a tolerance-based test's noise
floor turns out to be closer to its detection target than expected, re-measure what the tolerance
would need to become and check that against the smallest real regression it's meant to catch,
before touching the number — a gate that still passes is not evidence it still catches anything.*

**MEDIUM, from independent review — the fix itself shipped with no regression test.** An
adversarial re-verification (independently reproducing the pre-fix failure and the post-fix 0-pixel
result in its own Docker run, and re-deriving the subset font byte-for-byte from a genuine Debian
package to confirm `tests/pdf-corpus/fonts/README.md`'s recipe is real) found that nothing in the
diff would have caught a future revert to bare base-14 fonts: the only guard was the pre-existing
tolerance test, whose whole failure mode *is* passing locally and only failing on a second platform
— exactly what let this bug live unnoticed for three merges. Fixed with a platform-independent test
(`test_text_fixtures_embed_a_font_program`) asserting every non-scanned fixture's committed bytes
contain `/FontFile2` and never a bare `/BaseFont /Helvetica` — verified to actually fail against
`89d4fb5`'s committed fixtures before being trusted, and deliberately written with no `pypdfium2`
dependency so it runs even on the `[light]`-only CI leg. The same pass found `_font_widths`'
`first_char` hardcoded at `0x20` with no symmetric downward extension (unlike `last_char`), which
would have indexed `_ASCII_WIDTHS` negatively for a hypothetical `differences` code below `0x20` —
unreachable today (grepped every `Font(...)` call site) but fixed to be symmetric regardless. *Lesson:
"the existing test would have caught this eventually, on some other platform" is not the same claim
as "this increment shipped its own regression test" — a fix for a bug that was invisible on one
platform needs a check that doesn't depend on which platform runs it.*

## I4 — the extraction cache (20260728 10:28)

**MEDIUM — a filename collision between a real cache entry and its own in-flight write.** Every
scanning function (`survey`, `total_stats`, `clear_all`) globs `*.json`; `_write`'s atomic-write
temp file was originally suffixed `.json` too (`.tmp-<random>.json`, meant to land beside the final
name before `os.replace`). Verified directly: `pathlib.Path.glob("*.json")` matches dot-files,
unlike shell globbing, so that temp name was scanned as a real entry by every one of them. The
window only opens on an uncatchable kill (SIGKILL, OOM, power loss — `_write`'s own
`except BaseException` already cleans up anything else), but inside it a stray file could be
double-counted in `pnk doctor`'s totals forever (unreachable via the keyed `entry_path()` lookup, so
a fresh real entry gets written alongside it, never replacing it) and, worse, misclassified as a
*paid* orphan if the abandoned write happened to carry an `operation_id` — read by the one thing
this module exists to protect. Fixed by suffixing the temp file `.tmp`, never `.json`, so it can
never match the glob regardless of the leading-dot question. *Lesson: when several functions all
key off "does the filename match this pattern," a temp/staging file used by the same module needs
its own, deliberately non-matching pattern — matching the final name's extension by habit (`.json`
in, `.json` out) is exactly how a temp file becomes indistinguishable from a real one.*

**LOW-MEDIUM, no live trigger today — a JSON round-trip validated key structure but not value
types.** `_read`'s reconstruction of `per_page_provenance` did `dict(page) for page in provenance`
with no check that a page's values were actually strings, unlike `page_spans` three lines above
(`int(span[0])`, `int(span[1])`) — the same rigor wasn't applied to both fields reading from the
same untrusted JSON. Verified directly: a hand-written entry with `{"confidence": None}` was
accepted as a clean cache hit, silently degrading `ExtractedText.per_page_provenance`'s declared
`Mapping[str, str]`. No live writer currently populates a non-empty `per_page_provenance` (`pdfium.py`
and the `fake` backend both rely on the dataclass default), so this was unreachable in practice —
but the cache exists precisely to survive untrusted/older/hand-edited files, and I5/I7b are exactly
the increments that will start writing real provenance. Fixed with `_string_mapping`, validating
every key and value before trusting the entry. *Lesson: "no code currently writes the bad shape" is
a fact about today's callers, not a property of the format — a cache that reads its own JSON back
should validate every field it reconstructs the same way, not just the ones a current caller happens
to populate.*

**LOW — two verified-true claims shipped with no regression test.** A cache-write failure
(`chmod 0o500` on the cache directory, reproduced directly) correctly returns the extraction result
without raising, matching the `contextlib.suppress(OSError)` comment's claim — but nothing asserted
it. Two documents sharing one `content_hash` within a single KB correctly keep their shared cache
entry after one of them is deleted (eviction keys on the hash, which is still claimed by the
survivor) — only the cross-*KB* duplicate case had a test. Both were already correct; both now have
a test, one of which (the write-failure case) was verified to actually exercise the `except OSError`
branch by checking no cache file was created afterward, not merely that no exception propagated.
*Lesson: an already-true claim without a test is one refactor away from becoming a false one with no
signal — "this works" and "this is tested" are different sentences even when both are honestly true
today.*

**Reviewed and found correct, not a defect:** `pnk sync --clear-cache` (bare, no argument) deleting
paid cache entries along with everything else is the *intended* I4 behavior, not a gap — the plan's
own text ("removed only by an explicit `--clear-cache=paid`") describes a narrower, paid-preserving
variant that lands with I7c's ledger reader, which can price what it would be destroying; building
selective removal before that reader exists would mean guessing at a cost nothing can yet compute.
Confirmed live: an injected paid orphan was removed by `pnk sync --clear-cache --yes` along with
every other entry, consistent with `clear_all`'s own docstring and `docs/DESIGN.md`'s description.

## I5 — PDF chunking, page provenance, and a backend-aware sync (20260728 13:59)

**CRITICAL — decision 9's "never silently downgraded" guarantee held for a same-path sync and for
`--rebuild`, and silently did not for everything in between: a rename, or a document's first sync
on a machine that never extracted it.** The initial design protected a paid extraction two ways:
`pairing.py`'s own comparison when a document keeps its path, and `--rebuild`'s copy-forward from
the old index. Neither covers `Adopt`/`Rename` outside a rebuild, which instead fell through to
`_extract_for_index`'s only remaining signal — an `extract/cache.py` hit. A cache *miss* was then
read as "content changed", which is a false equivalence: a `--clear-cache` immediately before a
rename, or the first sync of a KB whose paid PDFs were extracted on a different machine (`docs/`
committed, `.pinakes/` gitignored — the ordinary shape of a clone), miss the cache identically
without the file having changed at all. Confirmed live, both ways: (1) paid-index a PDF,
`--clear-cache`, rename it with its sidecar travelling, sync — landed a `PaidExtractionRequiredError`
falsely claiming changed content, and left the index describing the *old*, now-nonexistent path,
since the failed transaction rolled back before the rename could be recorded; (2) paid-index a PDF,
`rm -rf .pinakes` (index *and* cache, simulating a fresh clone), first sync — identical false
failure on a document that had never changed at all. An independent adversarial review (a fresh
subagent, unanchored on this increment's own design reasoning) found and reproduced both.

Fixed by moving the "has this changed" decision off the cache entirely: the sidecar's own
`provenance.extraction` gained a fourth field, `content_hash` — the file's hash *at the moment of
that specific paid extraction*, distinct from the general change-detection hash `docs/DESIGN.md`
§2.2 already refuses to store, since this one changes only when a fresh paid extraction runs.
Comparing it directly against the current file's hash answers "changed?" without consulting any
cache or index at all. Getting the actual *text* without paying again is a separate question, now
answered in a fixed order: this same sync's own connection (covers a rename — the row is still
there under its old path), the old index during a `--rebuild` (unchanged from the original design,
now keyed on `doc_id` rather than `content_hash`+`path`, since a rename's action only ever carries
its *current* path and the old index's row still has the old one), then `extract/cache.py`. Only
when none of the three has an answer does it fail — and now with a *new*, distinct error
(`PaidExtractionUnavailableError`) naming the file unchanged but its text simply not present on this
machine, never conflated with "content changed" (`PaidExtractionRequiredError`) again. The
cross-machine case (2) is not solved by this — there is genuinely no durable, shared home for a
paid extraction's text yet — but the failure is now honest about which situation it is, which
`docs/DESIGN.md` §9 records as an accepted, disclosed limitation rather than a silently discovered
one. *Lesson: a mechanism justified as "the answer must not depend on the cache" (the `--rebuild` +
`--clear-cache` case this increment was explicitly designed around) needs that property checked
against every path that can reach the same decision, not just the one path the design started
from — `pairing.py`'s own decision table has four ways into "paid, free-effective, unchanged", and
only one of them was ever traced all the way through.*

**HIGH — `--rebuild` turned "a paid document's content changed" into "the document vanishes from
the index", where a normal sync leaves it stale but searchable.** `pair()`'s `PaidExtractionRequired`
action (decision 14) can only ever fire against a populated `before`, so it can never fire during a
rebuild at all (`before` is empty by construction) — meaning a changed-hash paid document reaching
`--rebuild` fell through to `_extract_for_index`'s ordinary raise, caught by `_apply`'s generic
exception handler, which never inserted a row for it in the first place. Confirmed live: paid-index
a PDF, change its bytes, `pnk sync --rebuild` — `report.ok` correctly `False`, but the document was
gone from the rebuilt index entirely (zero chunks), not merely flagged. A normal (non-rebuild) sync
hitting the identical case leaves the *old* row, chunks and embeddings untouched instead. Fixed by
extending the rebuild copy-forward to the changed-hash case too: the stale row is copied forward at
its *old* content_hash regardless of whether the current file still matches, and a `failures` entry
is recorded only when it does not — so a rebuild now reaches the same outcome a normal sync already
gives this exact case, rather than a harsher one purely as a side effect of which command happened
to run. *Lesson: `--rebuild` is documented as "free, deterministic, cron-safe" — exactly the
description that invites treating it as interchangeable with a normal sync. Any new failure mode
this increment gives normal sync a considered answer for needs the identical question asked of
`--rebuild` explicitly, since its empty `before` makes "the same case" arrive by a structurally
different path that is easy to reason about in isolation and forget to reconcile.*

**MEDIUM — a fresh paid-provenance write left the very next sync one `RefreshMetadata` cycle away
from settling.** `_index_document` decides `sidecar_hash` from the walk, before it rewrites the
sidecar with fresh `provenance.extraction` a few lines later in the same call — so the hash it
writes into `documents.sidecar_hash` was already stale the moment the write happened. Confirmed
live: three consecutive syncs of a freshly paid-extracted PDF produced `embedded=1`, then
`refreshed=1` (unexpected — nothing the user did changed), then finally `skipped=1`. Fixed by
recomputing `sidecar_hash` from the file just written, whenever a write happened, before it reaches
the `documents` INSERT. *Lesson: any function that both decides a hash-like value from an earlier
read *and* has the power to invalidate that exact read later in its own body needs the value
recomputed after the write, not carried from before it — "I already have this value" stops being
true the moment code between the read and its use can change what it should have been.*

**Caught live, during the adversarial review itself, not by this increment's own author:** two
different documents can share one `content_hash` with only one of them ever paid-extracted (a
second document minted later for identical bytes gets its own ordinary free extraction). The
original rebuild copy-forward keyed its survivor lookup on `content_hash` alone, which would have
let the free twin's own rebuild incorrectly inherit the paid one's chunks, embeddings and backend
label. Found and fixed inline by the reviewing subagent (re-keying on `(content_hash, path)`, later
superseded by the `doc_id` keying above once the rename/clone findings required a broader
redesign), with its own regression test. *Lesson: a value that is "usually unique in practice" is
not a key — `content_hash` was never meant to identify one document, only to detect whether one
had changed; this table's actual primary key was sitting right there the whole time.*

## I6a — budget core, pure (20260728 17:52)

**HIGH — every test of the timezone conversion that is this module's entire reason to exist would
have passed with the conversion deleted.** `window.py` aggregates ledger records into day/month
totals in `[budget] timezone`, converting both `now` and each record's `reserved_at` before
comparing. Every test — including the midnight, month-end and DST-transition trio written
specifically to exercise attribution — constructed both values *already in the target zone*, where
`.astimezone()` is a no-op. The adversarial review mutated `local_now = now.astimezone(timezone)` to
`local_now = now`, and separately the per-record conversion, and **both mutations passed all 35
tests**. The real case is ordinary, not exotic: a ledger storing UTC timestamps (the obvious choice
for I6b) read under a non-UTC `[budget] timezone` — 23:30 UTC on the 15th is 00:30 on the *16th* in
Berlin, so either mutation silently files the spend under the wrong day. Fixed by adding a test that
aggregates a UTC-stamped record against a Berlin window. *Lesson: a test whose fixture is built in
the same units the code converts to cannot detect a missing conversion. Exercising a transformation
requires input where the transformation actually changes something — three tests that carefully
varied the clock while holding the timezone constant proved nothing about the timezone at all.*

**MEDIUM — an exception hierarchy copied from a sibling module inherited the wrong exception
types.** `prices.py` was deliberately modelled on `extract/floors.py`, including its
`except (TOMLDecodeError, KeyError, TypeError, ValueError)` around parsing. But `floors.py` parses
with `float(x)`, which raises `ValueError` on bad input, while `prices.py` parses with
`Decimal(str(x))`, which raises `decimal.InvalidOperation` — **not** a `ValueError` subclass
(`InvalidOperation → DecimalException → ArithmeticError`). A single-character price typo (a European
`"5,00"`, an unfilled `"TBD"`) therefore escaped as a bare `InvalidOperation` instead of the named
`PricesMissingError` the module's own docstring promises, and the test claiming to cover this only
ever exercised a TOML *syntax* error. *Lesson: when mirroring a module's error handling, the except
clause travels with the parsing call it was written for. Changing `float` to `Decimal` changes which
exceptions are possible, and an inherited except tuple is a claim about the old code.*

**MEDIUM — validation absent at the one boundary where a wrong sign inverts the guarantee.**
`estimate_document` accepted any `pages`/`pages_estimated`: `pages=0` produced `requests=0` and made
`per_request_eur` raise on a zero division, and a negative `pages_estimated` produced a **negative**
`total_eur`. Every other failure mode in the module — unknown model, missing prices, stale prices,
oversize request — had a named error, but the one that would make a budget guard *understate* spend
had none. Not reachable from any caller in this increment, since nothing calls it yet; guarded at
the source rather than trusting a caller that does not exist to be written correctly. *Lesson: for
a component whose whole job is bounding a number, the input validation that matters most is
whichever one lets the number move in the safe-looking direction.*

**LOW, worth keeping — three assertions that were true but untested, in the same shape.**
`reserve_document`'s "every blocked window is named" was only ever tested with all three windows
breaching at once (so "always names all three" would also have passed); `reserve`'s "first breach in
order wins" was only tested where a single window *could* breach (two of three caps were set to a
generous 100 in every case); and `confirm_above_eur`'s strict `>` boundary was asserted only
incidentally. All three were verified correct by hand and none was a defect — but a regression in
any would have been invisible. *Lesson: a passing test suite says nothing about the claims it never
puts under tension; the boundary cases worth writing are the ones where two plausible
implementations disagree.*

Also fixed: `Table.decimal()`'s default path returned before its own `minimum` check, so a
below-minimum default would pass silently — `integer()`/`number()` avoid this for free by sharing
one code path between default and parsed value, which is why the bug was invisible by analogy.
`ContextWindowExceededError`'s remedy told the user to lower a `[chunking]`-equivalent slice size
that does not exist as configuration (`K` is a fixed constant). Every fix in this increment was
confirmed to fail against the pre-fix code before landing.

## I7a — the paid-path allowlist gate (20260728 19:25)

**HIGH — the gate found two live paid-client imports on the free path, in code that had shipped.**
`doctor._extraction` reported whether the configured extractor was available by calling
`load_extractor(backend)`, and `sync._missing_pdf_extra` did the same to decide whether a skipped
`.pdf` still needed an extra. The registry's factory imports the client (`extract/__init__.py`'s
`_import`), so on a KB whose `[extraction] backend` is `claude-vision`, both `pnk doctor` and
`pnk sync` pulled `anthropic` into a free-path process — doctor on *every* run. Neither was
reachable from any test, because every test KB is configured for `pypdfium2`. Nothing could
actually spend (the extractor is an I7b stub), so the cost was an import rather than a charge —
but the invariant CLAUDE.md calls non-negotiable was already false when the gate arrived to check
it. *Lesson: "does the free path import a paid client" is a question about a **running process**,
not about the source text. A grep over `src/` was green the whole time both leaks existed, because
neither leak is an import statement — it is an ordinary function call that reaches one.*

**HIGH — the gate's own paid KB was silently never paid.** The free-path runner configures a second
KB for `claude-vision`, since that is the only configuration where the two probes above fire. It
did so with `text.replace('backend = "pypdfium2"', ...)` against a manifest template that has **no
`[extraction]` section at all** — so the replace matched nothing, the KB stayed on the free
backend, and the gate would have passed whether or not the leaks existed. Caught only because the
run printed `pdf extractor: pypdfium2 importable` for a KB that was supposed to say
`claude-vision`. Fixed by appending the section rather than replacing, by making every manifest
rewrite a `_replace_once` that raises when it matches nothing, and by loading the manifest back
through the real parser and asserting `extraction.backend` is what was asked for. *Lesson:
`str.replace` returns the string unchanged when it matches nothing and reports it to no one — the
perfect way to build a test fixture that does not test what its name says. A fixture whose whole
purpose is to be in an unusual state must be **read back through the parser** and checked.*

**MEDIUM — two of the first six mutations survived, and both survivals were the finding.**
Mutating `is_backend_installed` to `return True` passed the entire suite: its only two callers are
tested with it monkeypatched, so nothing exercised the function itself. And
`test_a_directory_entry_fails_gate_1` asserted only a non-zero exit — which gate 2 produced anyway
by reporting the planted import, so the test stayed green with gate 1's directory branch deleted.
Fixed with three direct tests (including one whose probe module *raises on import*, so a
regression to importing errors rather than fails quietly) and by asserting gate 1's specific
message. *Lesson: a function whose every caller stubs it out has no test, only agreement; and an
assertion on an exit code cannot tell which of two gates produced it.*

**MEDIUM — the runtime checker would have flagged `google.protobuf` as a paid client.** Matching
`sys.modules` names by root (`name.split(".")[0] in {"anthropic", …, "google"}`) makes every
`google.*` module a hit, and protobuf arrives transitively with onnxruntime, grpc and much of the
ML ecosystem. Not triggered on this platform today — verified, zero `google.*` modules in a
free-path run — which is exactly what makes it dangerous: it would have fired first on some other
CI leg, on a change having nothing to do with money, and the obvious repair for a safety gate that
cries wolf is to weaken the gate. Now matched on a dotted-prefix boundary against
`google.generativeai` in full. *Lesson: for a gate whose failure mode is "someone turns it off",
the false-positive direction is as load-bearing as the true-positive one — and a latent false
positive is worse than an active one, because it lands on an unrelated change.*

**LOW, worth keeping — gate 2 cannot see a dynamic import, and that is deliberate.**
`extract/__init__.py` calls `__import__("anthropic", …)` inside the `claude-vision` factory, which
no import-statement grep will ever match, and it is not on the allowlist. Exempting the registry
would exempt the one file where an accidental static import is most likely; the dynamic call only
runs when a caller has explicitly *selected* a paid backend, which is an allowlisted entry point.
The limit is written into the gate's own docstring, and gate 4 is what covers the direction gate 2
cannot: no spelling of an import hides from `sys.modules`. *Recorded so the next reader does not
"fix" gate 2 by widening the allowlist.*

Also: `pnk doctor` no longer proves a paid backend's *adapter* constructs, only that its library is
locatable — the necessary price of not importing it, and worth remembering at I7b, when
`_load_claude_vision` stops being a stub. Every fix above was confirmed to fail against the pre-fix
code: 10 mutations planted, 10 detected, including both fixes made during this review.

## I6b — budget I/O: the ledger, `pnk budget`, hooks that cannot spend (20260728 23:27)

**HIGH — the accountant handed out a `PaidCall` object, undoing the one guarantee the ledger module
exists to provide.** `budget/ledger.py`'s whole argument is that a void may only be written when no
response was received, and that this is enforced by `paid_call` being a context manager rather than
a convention someone remembers. `Accountant.open_call` then wrote the reservation and *returned the
object*, putting both the void/unknown decision and the closing write back in the caller's hands —
and the caller it was written for is I7b's retry loop, the most branch-heavy code in the release.
Its own test left a permanent `unknown outcome` behind and asserted nothing about it. Now a context
manager delegating to `ledger.paid_call`. *Lesson: an invariant enforced by a control-flow construct
is only enforced where that construct is actually used. A convenience wrapper one layer up is
exactly where it gets quietly opted out of, and "the module below guarantees it" stops being true
the moment a caller can hold the handle.*

**MEDIUM — a single bad character in the ledger could take `pnk budget` down entirely.** Every euro
figure is `cost_usd / usd_per_eur`, computed in a property called long after parsing, from inside
the summing loop. A line with `usd_per_eur` of `"0"` therefore raised `DivisionByZero` out of a
read-only reporting command — defeating the malformed-line counting whose entire purpose is that no
one bad line can do that. The parse-time checks covered *type* (a JSON number is refused, so no
`float` gets in) but not *domain*. Rates are now validated positive at parse time, where a failure
is a counted malformed line. *Lesson: validation placed at the parse boundary only protects what is
computed at the parse boundary. A derived value computed lazily elsewhere needs its inputs checked
where they enter, not where they are used.*

**MEDIUM — `fsync` on the file does not make the file's name durable.** The reservation is written
before the call precisely so a crash during the call cannot lose it, and each write is fsynced. But
creating a file and fsyncing its contents leaves the *directory entry* unsynced, so the very first
reservation a KB ever writes — the one before its first paid call — could vanish on a crash while
every later one survived. The parent directory is now fsynced on creation only. *Lesson: durability
claims have to name what is durable. "The write is fsynced" is a claim about bytes; "the record
survives a crash" additionally requires the file to still have a name.*

**MEDIUM — both hook checks read `root/.git/hooks` directly, so they were blind in a git worktree.**
Inside a worktree or submodule `.git` is a *file* pointing elsewhere; `hooks.hooks_dir` has resolved
that since I12, and `doctor` never used it. Every hook read as absent, so `pnk doctor` reported "0 of
3 installed" and I6b's new machine-driven-spend check would have reported "no hooks installed, so no
automatic sync runs" on a KB whose hooks were installed and running. Worth more than its size here:
this project's own CLAUDE.md mandates a worktree for *every* change, so the layout the check is blind
on is the one it is developed in. *Lesson: a helper that already handles a case is not the same as
using it — the second reader of `.git` reintroduced the bug the first one had solved.*

**LOW, worth keeping — one report, two clocks.** `pnk budget` computes its windows in
`[budget] timezone` and printed the recent-operations list in the *machine's* local zone, unlabelled.
On a KB synced from two machines the same operation renders at two different times, and the day a
call is filed under would not match the timestamp beside it. *Recorded because the fix is trivial and
the class of bug is not: a report that derives one number from configuration and another from
ambient state looks consistent on the machine it was written on.*

**LOW, second pass — two flags that read as the opposite of what they do.** `pnk budget` listed the
five most recent operations and stopped, with no line saying how many it had not shown — the
silent-cap failure this plan's own ground rules name ("if a workflow bounds coverage, `log()` what
was dropped"). And `--clear-cache`'s bare form parsed to the value `free`, which reads as "clear only
the free entries" when both spellings clear the *whole* cache; `argparse` validates `const` against
`choices`, so a private sentinel is not available and the bare form has to be a real, honest word.
It is now `all`, and the value names what is being authorised rather than what is removed.

**LOW, third pass — the notice `init --ci` printed described a file it had not written.**
`FREE_BACKEND_NOTICE` began "hooks run `pnk sync --extract=pypdfium2` …" and was printed by two
callers: `install-hooks`, which writes hooks, and `init --ci`, which writes a workflow. So `pnk init
--ci` announced `.github/workflows/pinakes.yml` and then explained what the *hooks* do. Every test
asserted the flag and the phrase "can never spend", both of which were present and correct. Found
only by running the command the docs tell a user to run — the constant is now subject-less and each
caller supplies its own ("each hook …", "it …"). *Lesson: a shared string with a subject baked in is
correct for exactly one caller. The tests all checked the part that was shared; the part that was
wrong was the part no assertion mentioned.*

Also: `doctor` printed `cost_eur` — a `Decimal` division — with a bare f-string, putting all 28
significant digits into a health-check line; the `--resolve` record's `operation` field was
documented as a value it never takes. Every fix above was confirmed to fail against the pre-fix
code: 14 mutations planted over the implementation (14 detected), and 5 more reverting each review
fix in turn (5 detected), the last of which found that the formatting fix had no test at all until
one was written for it.

---

## I7b — the paid Claude-vision extractor (20260729 00:24)

**HIGH — the reconciliation recorded the *reserved* amount, which makes the whole
reservation/reconciliation protocol a no-op.** `_billed_call` closed each successful call with
`cost_usd=reserved_eur * usd_per_eur` — the estimate again, not what the response said it cost. The
shape was perfect: a reservation, then a reconciliation superseding it, exactly as I6b's protocol
requires, with a ledger pair per call and every test about *pairing* passing. What it superseded the
reservation with was the reservation. Every window would have charged worst-case forever, `pnk
budget` would have reported an estimate as spend, and the reconciliation record's presence is
precisely what would have made it look settled. Fixed with `actual_cost_usd`, derived from the
response's own usage and the model's price. *Lesson: I6b's tests could only ever check that a
reconciliation **exists** and supersedes; that it carries the **right number** is a claim only the
increment that produces the number can make. A protocol test and a value test look alike and are
not — and every mutation I planted over the retry logic passed straight through this, because the
bug was in the one line none of them touched.*

**HIGH — one bad PDF would have crashed a 1,000-document sync.** `TransportError` and
`RequestTooLargeError` were plain `Exception`s. `sync` isolates each document behind
`except (PinakesError, OSError, ValueError)`, so an exhausted 429, a 500, or an oversized page
would have escaped that handler and taken the entire run down — the exact opposite of the
per-document isolation §6.4 promises and `pnk sync`'s own "one broken PDF cannot block a
1,000-document corpus". Not caught by any test, because every test called `extract_slice` directly
and asserted `pytest.raises(TransportError)`, which passes identically whichever base class it has.
*Lesson: an exception's **type** is part of its contract with a caller several layers up, and a
test that catches the exception it just raised cannot see that contract at all.*

**MEDIUM — two mutation survivors, both the finding.** A cap check hoisted out of the transport
retry loop survived because every attempt inside that loop voids at zero: nothing the loop does
moves the total, so the omission looks harmless. It is not — between a 429 and its backoff another
process syncing the same KB can spend the headroom, and the retry would go out anyway. And the
per-slice semantic budget survived because every test used a single slice, where "per slice" and
"per document" are the same number; that was a defect I had found and fixed while writing the loop
and then never put under tension. *Lesson: a bound that is only ever exercised at N = 1 is not
tested, it is agreed with.*

**MEDIUM — the module imported `pypdfium2` at module scope, which §4.4 cannot afford.** The
fingerprint path reaches this module on *every query*, on whatever install the user has, so a
top-level `pdfium` import made a coherence check on a `claude-vision` KB fail outright on a
core-only install. Caught by `test_coherence_never_imports_a_paid_client` — a test written in I2 for
a different reason, which happened to be the exact shape of this mistake. *Recorded because it is
the second time this project has been saved by an import-graph test that nobody wrote for the case
that caught them.*

**LOW, worth keeping — the gate refused the commit, which is the gate working.**
`.paid-path-allowlist` shipped empty at I7a specifically so that its first real entry would be
*earned*, and it was: the commit creating `claude.py` failed until the line was added. Its test then
turned out to assert only "0 exempt paths", which would have passed on any addition at all, so it
now pins the expected contents — widening an allowlist is how a gate like this one dies. Two dead
exception classes (`TruncatedResponseError`, `RefusalError`) were also removed: the `stop_reason`
branches replaced them and nothing ever raised either.

**LOW, second pass — `--estimate-only` demanded an API key from a KB with nothing to estimate.**
The transport was built before the walk, so a KB with no PDFs failed on a missing key instead of
reporting nothing. Built on the first PDF now. Also cleaned up in the same pass: an unreachable
`except RequestTooLargeError` around `slice_pages` (only `build_request` raises it, and by then the
call is committed — the size question belongs before anything is built), and a repeated
`"claude-vision"` literal where the module already imports the constant.

**HIGH, fourth pass — the paid fingerprint omitted the model, so changing it reused another
model's text.** The plan states the inputs as "(backend name, **model id**, prompt version, schema
version, request-shape version…)" and I wrote every one of those except the model. The cache key is
`<content_hash>-<fingerprint>`, so editing `[extraction] model` would have hit an entry a
*different* model wrote, with no miss, no warning and no stale marker — the §4.4 machinery intact
and looking at the wrong key. The plan names two tests for exactly this
(`test_changing_the_model_misses_the_cache`, `test_changing_k_misses_the_cache`) and I had written a
placeholder for the first that only asserted two unrelated fields were non-empty, which is how it
stayed invisible through three review passes and fifteen mutations. Fixing it meant threading
`[extraction] model` through the registry's `FingerprintInputs` contract — two real callers, `sync`
and the §4.4 coherence check — plus a test that the *free* backend's key is unperturbed by the new
parameter, or every existing free KB's index would have gone stale the day it was added. *Lesson: a
test written to a name from the plan, but not to the claim behind the name, is worse than a missing
test — the plan's checklist reads as satisfied. The tell was there in the placeholder's own body:
it asserted things that could not fail.*

**MEDIUM, fifth pass — three of the plan's named tests had no implementation at all.** Auditing
the plan's test list against the file (prompted by pass 4, since the same failure mode was in play)
found the multi-slice document, the oversize-slice split, and the no-floor-installed refusal all
missing — the first being where the slice-window arithmetic and the short final slice actually meet
a real PDF, and where an off-by-one either drops pages or sends the whole document to a paid API.
Writing them found nothing broken, which is the useful outcome to record: the code was right and
unwitnessed. Two of them also had to be *sized from the fixture* rather than from a constant — a
hard-coded byte threshold either never splits or recurses straight to the single-page failure, and
which one it does is a property of the corpus, not of the code. `slice_windows` and `slice_bytes`
lost their underscores in the process: they are the two things a reader most wants to check.

**LOW, sixth pass — nothing drove `pnk sync` itself.** Every test exercised a piece: the slice
loop, the ledger pairing, the cache's join key, the accountant's windows. The pieces were wired
together across four modules, and "each part works" is not the claim "the parts are connected" —
which is the seam an increment is most likely to get wrong. One end-to-end test now runs a real
`pnk sync` over a paid KB and checks the whole chain: the document indexed under `claude-vision`,
the ledger's call reconciled, and the cache entry carrying the `operation_id`/`call_ids` that §6.3
left `null` until this increment. It passed first time — but writing it introduced the pass's
one real defect, and only the `[claude]` leg saw it: the test swapped the registry entry and then
called `unregister_extractor`, which *deletes*. There is no undo for a name the package registers
at import, so two unrelated tests later in the session lost `claude-vision` entirely. Fixed with a
`registered_entry` accessor and a re-register in the `finally`. *Lesson: a test that mutates
process-global state needs to restore the previous value, not remove its own — and a suite that
only ever runs on one CI leg will not show you which.*

**MEDIUM, seventh pass — the `[light]` leg's green was partly an artefact, and I had not really
run that leg at all.** `uv run --extra light` does **not** prune extras a previous
`--extra pdf --extra claude` installed, so "all three CI legs pass" was one leg run three times. A
real `uv sync --frozen --extra light` — what CI actually does — then showed the paid suite failing
*on its own* while passing in a full run: `tests/test_extract.py` leaves a fake `pypdfium2` in
`sys.modules`, and two `--estimate-only` tests were quietly relying on it. The underlying cause was
mine: `_estimate_only` imported `page_count` before the walk, so a KB with no PDFs demanded the
`[pdf]` extra to be told it had nothing to estimate — the same defect as pass 2's transport, one
line above where I had fixed it. *Lesson: `uv run --extra X` is not `uv sync --extra X`; verifying a
matrix means reproducing what the matrix does, not asking for the same set three times. And a suite
that only ever runs after its neighbours cannot tell you what it depends on.*

**LOW, third pass — markdown emphasis reached a terminal.** `--estimate-only`'s help text carried
`**A network call**`, which argparse renders as literal asterisks: the emphasis was written for
CLI.md and pasted into a surface that has no renderer. Now checked against every command's
*rendered* `--help` output rather than argparse's internals — the artefact a user actually sees.
Backticks are deliberately allowed, since `[extraction] backend` reads fine in a terminal and is
the convention this CLI already used; flagging those too would have been a style crusade over
pre-existing text rather than a defect.

Also: `stubs/anthropic.pyi` joins `stubs/pypdfium2.pyi`, because the strict type gate runs on the
`[light]` leg where the package is absent. It records the one relationship easy to get wrong from
memory — `APIConnectionError` is a *sibling* of `APIStatusError`, and `APITimeoutError` a subclass
of the former — because checking them in the wrong order classifies every timeout as a plain
connection failure, which is the difference between recording €0 and admitting a possible charge.
18 mutations planted in total, 18 detected once the survivors got tests.

---

## I7c — the completeness audit, staging, all-or-nothing (20260729 02:38)

**MEDIUM — three of ten mutations survived, and all three were the same shape: a rule with no test
that it *fires*, only that it exists.** Clearing staging after the complete entry is written had no
test that staging is ever cleared at all — and stale staging is not litter, because its key is
`<content_hash>-<fingerprint>`: a later run of the same document would find it, skip slices, and
serve text from a superseded extraction silently and for free. Stopping the corpus at the first cap
breach had no test that drove `sync`; the `on_exceed` tests build a `SyncReport` by hand, so they
can check what a stop *means* but never whether the loop stops. And keeping staging out of the
cache root had nothing asserting that `survey`, `total_stats` and `clear_all` cannot see it.
*Lesson: the tests I wrote were about the rules I was thinking about while writing the code, which
is exactly the increment-shaped blind spot this project keeps rediscovering. Mutation found all
three in one pass because a mutation asks the question the test forgot: not "is the rule stated"
but "would anything notice if it stopped being true".*

**MEDIUM — the audit's own fixtures measured nothing.** `word_coverage` tokenises on `[a-zA-Z]+`,
so forty words of `f"{seed}{index}"` collapse to **one** distinct word: every page scored 1.00, the
dropped-content test found no outlier, and the fixture could not have failed whatever the code did.
Caught only because that test failed for a *different* reason first. *Lesson: a fixture built for a
metric has to survive that metric's own tokeniser — and "the test passes" would have hidden this
completely if the assertion had been slightly weaker.*

**MEDIUM, second pass — the audit made the very mistake it was written to avoid, one branch
later.** A page above the yield floor whose text holds no *significant* words — a table of figures,
which is an ordinary PDF page, not an exotic one — gives `word_coverage` a denominator of zero. I
scored it **1.0**: full preservation claimed for something never checked, and it drags the median
*up*, making the genuine outliers look less unusual. Six lines earlier the module argues at length
that a scanned page must be exempt rather than zero, for exactly the same reason in the other
direction. Now both are exempt. The fix then exposed a *second* worthless fixture:
`_significant_words` keeps only words of four characters or more, so `prose("a")`'s three-letter
words were never measurable either — that test had been passing purely on the 1.0 default it was
supposed to be testing around. `prose` now asserts its own output is measurable. *Lesson: a default
that makes "unmeasurable" indistinguishable from "perfect" hides broken fixtures as effectively as
it hides broken code — and I wrote the argument against it into the docstring of the function that
did it.*

**LOW, second pass — one feature, two standards for the same question.** `_is_budget_refusal`
identifies a refusal by exception *type*, with a comment saying an error string is prose and prose
gets reworded. Twelve lines later `SyncReport.ok` decided which failure was the budget's by
comparing that same prose. It now matches on the path, which is structural.

**LOW — `on_exceed` had been parsed, validated and read by nothing since v0.1.** A manifest key with
a `choice()` validator, a default, a template comment and a documented meaning, wired to no
behaviour at all. It now decides whether a budget stop is a failure. *Recorded because validation is
what made it invisible: a key that round-trips through the parser looks implemented from every angle
except the one that matters.*

**LOW — the interruption I first scripted was not one the caller isolates.** The test double raised
`AssertionError` when its script ran out, which `sync` does not catch, so it escaped the
per-document handler and failed the *test* rather than the document. Replaced with a timeout — a
real interruption, and one the caller actually handles. *A test double's failure mode is part of the
test: if it fails in a way production cannot produce, the path under test never runs.*

**LOW, and the second time in one session — I composed a timestamp instead of reading one.** This
entry's heading was written `03:04` moments after `date` had printed `02:38`. CLAUDE.md's rule is
already explicit ("read the clock; never compose a timestamp"), and knowing the rule is evidently
not the same as running the command: the failure is that composing *feels* like recalling. Caught
both times only by diffing the two numbers on screen.

Also: another agent, working independently, found that I7b's own docs contradicted themselves —
`STATUS.md` said "claude-vision is a real extractor" in one row while the prose eight lines below
still explained that nothing can spend *because it is a stub*. I had updated the table and left the
paragraph justifying it. Seven review passes over I7b did not catch it. 15 mutations planted here,
15 detected once the survivors got tests.

---

---

## The eval harness: three defects under one green suite (20260729 03:23)

Found while planning the links and graph releases, whose whole gate rests on this harness. All
three were live on `main` and all three passed every test.

**HIGH — the `multi-hop` class measured nothing about hopping.** `Outcome.hops_followed` was
computed for every scripted question and read by no metric — not `recall_at_k`, not `by_kind`,
nothing `compare()` looks at. **Deleting the hop loop outright left `by_kind["multi-hop"]`
bit-identical.** A multi-hop question was a single-shot search of its last hop's query wearing a
label. The one guard was `assert any(outcome.hops_followed > 0 …)` — an `any()` over five questions,
on a field that fed nothing.

**HIGH — and that hid a defect in the golden set itself.** Three of the five questions named their
*last* hop's document in `expect`; two named their *first*. So the scorer ran a query about
brittle-paper conservation and demanded the annual report. Nothing could catch the disagreement,
because `hops` fed no metric that could notice it. The fix makes `expect` exactly the union of the
hops' documents and asserts it for the committed set.

**The numbers moved because the scorer was wrong, not because retrieval changed.** recall@5
0.8788 → 0.9091, MRR 0.7737 → 0.8116, rerank precision 0.7273 → 0.7576, `by_kind["multi-hop"]`
0.80 → 1.00. Stricter scoring, higher score — because the two inverted questions had been asked
about the wrong document all along. **A metric that improves when you make it stricter is telling
you it was measuring something else.**

**MEDIUM — `compare()` wrote `by_kind` into every baseline and never read it back.** A change
lifting one class and dropping another by the same amount moves the aggregates by almost nothing;
CI was green through it. The question count had the same shape: written, never compared, so a
golden set that silently lost its hard questions would have scored *better*.

**MEDIUM — the "cheap deterministic embedder" was not deterministic.** `HashingBackend` hashed each
word with `hash()`, which Python randomises per process for `str` unless `PYTHONHASHSEED` is set —
and nothing sets it, nor can a `conftest.py`, since the value is read before the interpreter starts.
Which words collided in the 64-dimensional space changed run to run: **one failure in 40 runs**
before, **zero in 60** after switching to `zlib.crc32`. It surfaced only because a newly written
test tripped over it once. A fake that cannot reproduce itself cannot tell a real regression from
its own noise (v0.1 rule 5).

**The transferable lesson.** All three survived because the tests asserted that the machinery *ran*,
never that it could *detect*. The mutation pass is what caught them: four mutants — `hit` ignoring
hops, the `by_kind` comparison, the question-count check, and the golden-set consistency assertion —
were introduced deliberately and all four killed a named test. Green proves the tests ran; only
breaking the code on purpose proves they can see.

## Shared-file contention tooling (20260729 04:06)

**HIGH — `git status --porcelain`'s leading space is significant, and a helper doing `.strip()` on
the whole output silently ate it.** The overlap gate's `git()` wrapper returned
`proc.stdout.strip()`, which is correct for `merge-base` and `symbolic-ref` and wrong for
`status --porcelain`: a modified file is reported as `` M CHANGELOG.md`` with the status in columns
0–1, so stripping the output removed the first line's leading space and the path parsed one
character short — `HANGELOG.md`. It matched nothing, and the gate reported **"no overlap" with total
confidence**. Exactly the one failure a contention gate cannot have.

Two things about how it was caught, both worth keeping:

- **The tests drive real `git` against real temp repositories, not a mocked `subprocess`.** The gate
  is almost entirely a set of claims *about git's behaviour* — what `diff A...B` means, which commit
  `merge-base` picks, how `status --porcelain` spells a rename — and a mock asserts the author's
  belief about each of those rather than the behaviour. A mocked test would have returned
  `" M CHANGELOG.md"` from a fake and passed with the bug present.
- **The mutation pass re-introduced this exact bug deliberately** and confirmed the right test
  fails. `git()` is now documented as trailing-newlines-only, with the reason, because the next
  person to "tidy" it back to `.strip()` will find nothing obviously wrong.

**MEDIUM — a clean auto-merge is not a correct merge, and only the loud half of that was being
managed.** Three parallel branches edited `CHANGELOG.md`, `docs/STATUS.md` and `docs/DESIGN.md`
inside one hour on 20260729. `CHANGELOG.md` conflicted and was resolved by hand; the other two
merged **silently**, because the edits landed on different lines. Git merges edits that do not
overlap textually, never edits that agree — so two agents can leave one document contradicting
itself with every command reporting success, and no conflict resolution however careful would
surface it.

The response is deliberately in two layers, because one does not cover the other's cases:

- `changelog.d/` and `retro.d/` **remove the cause** for the two documents every change must write
  to — separate files cannot conflict, so for those the class stops existing.
- `tools/shared_file_overlap.py` **reports what remains**, which is the living documents
  (`docs/STATUS.md`, `docs/DESIGN.md`) that fragments do not suit, because they are edited in place
  rather than appended to.

**MEDIUM — splicing produced two `### Added` headings under one `## [Unreleased]`, and only
cutting a release revealed it.** The tool inserted each rendered `### Category` block under the
anchor without looking at what was already there, so a section that already carried an `### Added`
from unmigrated prose ended up with two. Keep a Changelog expects one heading per category, and a
reader scanning for "what was added" stops at the first. Fixed by merging into an existing heading
when there is one, bounded to the anchor's own section so a *shipped* release's `### Added` is never
written into.

Worth keeping for the reason it was missed: `test_apply_leaves_existing_unreleased_prose_exactly_
where_it_was` was written deliberately, and it passed — leaving existing prose alone is correct. The
case it did not imagine is that the existing prose has *its own category headings*. A test written
by the reasoning that wrote the code inherits its assumptions, which is the same increment-shaped
blind spot `CLAUDE.md` already names; here the escape was dogfooding, not mutation testing, because
the mutation pass only ever perturbs cases somebody already thought of.

Separately, and pre-existing: `[Unreleased]` had accumulated **seven** category headings by hand
over several days — two `### Added`, three `### Changed`, two `### Fixed`. Consolidated when cutting
0.3.0, with a check that every non-heading line survived the regrouping.

**LOW — the fragment tool takes `--repo` so its tests can drive the real artifact.** Importing a
`tools/` script from a test needs `sys.path` surgery that `pyright` and `ty` then cannot resolve —
`ty` failed the build on exactly that. Running it as a subprocess follows the precedent
`tests/test_paid_path.py` set for `tools/paid_path_gate.py`, and tests the same artifact `check.sh`
runs, argument parsing included.

## I8 — Page citations on both surfaces, and `pnk doctor`'s text yield (20260729 04:55)

**HIGH — `pinakes_get` on a PDF crashed, and no test could have caught it.** `document()` read the
source with `read_text(encoding="utf-8")` inside a `try` guarded by `except OSError`.
`UnicodeDecodeError` is a `ValueError`, so the guard never applied and the traceback escaped through
the MCP surface. It survived since v0.1 because no test ever called `pinakes_get` on a PDF — the
serve suite's KB is two markdown files, and every PDF test lives in a module that never builds a
server. A gap between two test modules is invisible to both.

**HIGH — the plan's `page_start == p` assertion is wrong, and would have failed on correct code.**
The I8 draft specifies that every chunk covering the traced offset "reports `page_start == p`". A
chunk that straddles a page break starts on the *earlier* page, so a word on the later one
legitimately sits inside a chunk whose `page_start` is smaller — which I5 explicitly allows and
which the citation renders as `p1-2`. The trace asserts `page_start <= p <= page_end` instead. The
draft had already corrected "exactly one chunk" to "at least one" for the same fixture; the page
assertion needed the same correction and did not get it.

**MEDIUM — the `stale_extraction` row understated its own gap by half.** DESIGN §4.7's pending
amendment said the marker "today reaches the CLI's `Passage` but stops there", so I8 would carry it
to the agent surface. It reached the CLI's `Passage` *object* and was then dropped by the CLI
renderer too — computed in `search.py`, surfaced nowhere. A field that exists in a dataclass reads,
at review time, like a field that is displayed.

**MEDIUM — the free per-page yield lived inside the only module allowed to import `anthropic`.**
`survey_free_yield` measures what *pypdfium2* got out of a page; nothing about it is paid. But it
sat in `extract/claude.py`, so `pnk doctor` — a free command — could not consume it without
importing the paid path to ask a free question, against CLAUDE.md's own "never probe a backend by
loading it". Moved to `extract/pageyield.py`. The alternative, a second per-page loop in `doctor.py`,
would have been a second definition of a measurement that decides whether to spend money.

**A dead statistic in a shipped template.** The `notes` template's `[budget]` comment told every new
KB that "no shipped code path spends money" — written when that was true, still shipping three
releases later. `docs/GUIDE.md` said the paid extractor was "built but in no release yet". Both are
the same failure as the four README claims found at 0.1.2: prose drifts toward the design, because
the design is what you are thinking about while writing it. Neither was in the increment's scope;
both were found by reading the files the increment touched for other reasons.

**Mutation testing found the test whose name was stronger than its assertion.** Twelve of thirteen
mutations were detected. The survivor deleted `pnk doctor`'s unmeasured-document tally, and
`test_a_swept_cache_entry_is_counted_as_unmeasured_rather_than_as_a_pass` stayed green — because
that test sweeps the *whole* cache and reads a branch that counts documents rather than the tally.
The mixed case, where some documents measure and others do not, is the one the tally exists for, and
it had no test. Its name claimed the general property; its body tested the degenerate one.

### The review pass over I8's own diff

Three defects, all in `pnk doctor`'s new check, all found by reading it adversarially rather than
by any test:

**HIGH — the health check crashed on an unhealthy KB.** `is_paid_backend` raises
`BackendUnknownError` on a name it does not recognise, and the check passed it every PDF's recorded
backend. A KB indexed by a newer pinakes, or with an extra since uninstalled, would make `pnk
doctor` itself raise — the one command someone runs *because* their KB is in a state they do not
understand. §4.4's coherence check has carried the identical guard, with the identical comment,
since I5; the new code was written beside it and did not copy it.

**MEDIUM — a KB whose PDFs are all paid-extracted got a permanent, unclearable warning**, with a
remedy (`pnk sync`) that on those documents *spends money*. The check deliberately skips
paid-extracted documents, then reported the resulting empty measurement through the branch meant
for a swept cache. Skipped-on-purpose and lost look identical to a counter.

**LOW — a single out-of-range page bound was reported as a backwards range.** `page_start=5` on a
two-page document read "pages 5-2 is not a range within it", because the bounds were validated
after the omitted one was defaulted. It describes a range the caller never asked for, and reads as
pinakes' mistake rather than a bad argument. Found by running the tool, not by reading it.

**What the tests could not have caught.** All three needed either a KB state no fixture builds
(an unknown backend name, wholly paid extraction) or a human reading an error message. The
increment's own tests were green throughout, and so was a sixteen-mutation pass — mutation only
perturbs cases somebody already thought of, which is the same limit that let the fragment tooling
ship a duplicate-heading bug at the 0.3.0 release.

## I9 — Auditing the verification table (20260729 05:40)

**HIGH — the table that verifies everything verified nothing.** `plans/20260727_1543-v0.2.md` ends with 98 rows,
each promising a property and naming the test that holds it, under a preamble reading *"a promise in
a section with no owner is a wish"*. **61 of the 98 test paths did not resolve.** Not because the
properties went untested — nearly all are tested, usually under a better name than the plan guessed
— but because the paths were written *before* the tests existed and implementation renamed them.

The failure is not the renaming. It is that **nothing ever read the table**, so it could drift a row
at a time for nine increments with every gate green. A table of test paths is prose until something
executes it, and prose about tests reads exactly like tests. The fix is not a better table: it is
`tests/test_verification.py`, which resolves every reference in `docs/VERIFICATION.md` and fails on
the first one that does not exist. The document can now go stale exactly once — in the commit that
breaks it.

**The audit found a real gap on its first run, which is the argument for doing it.**
`test_every_v02_check_appears` was assigned to I8, named in the table, and never written. Writing it
(as `test_every_doctor_check_is_exercised_by_a_test`) immediately found **five `pnk doctor` checks
with no test at all**: `template`, `reranker`, `model cache`, `extensions`, `links`. Link coverage is
a §6.2 promise; the reranker check exists so a health check does not download weights. Both had
shipped untested since I11.

**MEDIUM — I wrote the exact CI assertion the plan warned against, and only running it caught it.**
The plan says the core-only wheel smoke must use "a **core-only KB that does not need embeddings**,
because today's smoke KB fails on sentence-transformers long before it reaches an extractor, so the
assertion would prove nothing". I built a PDF-only KB believing that satisfied it, and it does not:
the embedding backend loads before any extractor, so `pnk sync` on a PDF-only core install still
fails on `pinakes[st]`. My `grep -q 'pinakes\['` passed — against the wrong extra. `pnk doctor` is
the only surface that reaches the extractor question on a core-only install, because it reports a
failing backend as a check and carries on. **Reading the plan's warning was not enough to avoid the
thing the plan warned about; running the command was.**

**A plan is a historical record, and correcting it would have destroyed the evidence.** The
temptation was to fix the 61 paths in place. That would have erased the only proof that predicted
test names drift — and with it the reason `tests/test_verification.py` needs to exist. The plan
keeps its predictions under a dated supersession note; the resolved mapping lives in `docs/`.

## A sidecar that would not parse was replaced by a freshly minted one (20260729 07:26)

**HIGH — the one failure the design says is unrecoverable, shipped since v0.1 and live in 0.4.0 on
PyPI.** `walk_sources` dropped a sidecar it could not read (`except PinakesError: continue`,
`sync.py:385`) so that one bad file would not stop the walk. That was right. What it did not
account for is that the *document* then matches DESIGN §6.4's "new path, no sidecar" row — and the
mint path wrote a freshly minted sidecar over the file still holding the document's permanent ULID.
Every inbound `pnk://` link points at the id that was destroyed, and there is no migration
machinery by design.

Three things made it invisible:

* **`pnk sync` reported success.** `report.ok` was true, `failures` empty, `1 indexed`.
* **`pnk doctor` afterwards reported `sidecars: N readable`, `duplicate ids: none`, `failures:
  none`** — every check green, because the unparseable file no longer existed. The skip site's own
  comment said *"reported by `pnk doctor`"*; that safety net could never fire, because syncing
  repairs the symptom by destroying the evidence.
* **The module that owns the risk had already named it.** `sidecar.write`'s atomic-rename comment
  calls ULID loss *"the one failure in this module that no later command could repair"* — and then
  handed the file to a caller that overwrote it deliberately. A guard written against a *torn*
  write says nothing about a *deliberate* one.

**How it was found, and what that says.** Not by a test — by hand-authoring L1's partner corpus
with one deliberately unresolvable link, syncing it, and noticing that `pnk doctor` reported 10
links where the density gate had just counted 13. The discrepancy was three links, all on one
document, and that document's sidecar had a new ULID and a `created` stamp from the sync. **A
second, independent count of the same population is what exposed it**; every check that read only
the post-sync state agreed with itself. L7 requires the gate's number and doctor's number to be
the same population for a different reason — so that a user and CI cannot disagree — and this is
the argument for computing both at all.

**The fix, and one guard that was removed for failing its own mutation test.** Minting goes through
a new `sidecar.create`, which refuses where a file exists; the refusal lives at the write rather
than in the caller, because "the only caller that reaches it" is a property of today's code. A
matching guard added to the `--index-only` branch of `_mint` proved **undetectable by mutation** —
deleting it changed no observable behaviour, only which of two `SidecarError`s was reported,
because the indexing path re-reads the sidecar for its metadata and *that* read refuses first. It
was removed rather than kept, and `_mint`'s docstring records why, so a later reader does not
"restore the missing check". A guard that cannot be mutated is not a guard; keeping it would have
been the kind of decoration this project's mutation step exists to catch.

**The adversarial pass found the bigger half.** The fix as first written covered only the case
where the document is *absent from the index* — a fresh KB, a fresh clone, a `--rebuild`. For a
document already indexed whose content is unchanged, pairing yields `RefreshMetadata`, and that
branch sits **outside** `_apply`'s per-document `try`, so `_refresh_metadata`'s re-read of the
sidecar raised straight through `_apply`, the action loop and `sync()`. One hand-broken file aborted
the entire corpus: no `failures` row, no `set_meta`, no commit, and every document after it
unprocessed — contradicting this module's own opening promise and `docs/CLI.md`'s "failures are
recorded, the run continues". That is the *likeliest* route in: edit a link by hand, re-sync. Three
paths existed for one cause (`Mint`, `Reembed`, `RefreshMetadata`) and each behaved differently;
they now report identically. **The lesson is about where the first fix stopped**: it was written
against the reproduction, and the reproduction was a fresh KB because that is what a corpus author
happens to have. A fix aimed at a repro covers the repro's path.

**Two smaller things the same pass caught, both about honesty rather than correctness.** The refusal
said only "already exists, so a freshly minted sidecar cannot be written over it" — which reads like
a pinakes bug (*of course* it exists) and says nothing about the character the user mistyped, while
DESIGN, the changelog and the commit message all claimed it named the parse error. The walk has to
swallow that error to keep walking, so the mint path now re-reads the one file to recover it. And
the remedy said "repair the file rather than deleting it — it holds the permanent ULID", which is
false for the second shape the tests deliberately parametrise over: `id: not-a-ulid` has no ULID to
repair *to*, and a user in a blocked pre-commit was being told not to do the only thing that
unblocks them.

**What the tests are parametrised over, and why.** Two unrelated parse failures — a malformed link
URI and a malformed `id`. The defect is *any* `PinakesError` from `read_sidecar` reaching the mint
path, and a test written only against a bad link would have gone quiet the moment link parsing
moved.

## L1 — The partner corpus and the density gate (20260729 08:47)

**HIGH — the gate did not gate the one shape it was built for.** `degrees` was keyed by *basename*
(`path.name`), so two documents sharing a filename in different folders collapsed to one key and the
later-sorted one **overwrote** the earlier. Demonstrated against the shipped gate: a degree-6
hub — 50% above the cap of 4 — behind `docs/aaa/policy.md` exited 0 and was reported as *"worst
degree 1 (policy.md)"*. Density alone permits one hub wired to everything; the degree cap exists
separately *precisely* to catch that, and a basename key is the single way it cannot. Now keyed by
path relative to the KB root. The committed corpora are flat, so nothing in this repo would ever
have exercised it — the fixture had to be built to find it.

**HIGH — the gate counted sidecars where it meant documents**, and was wrong in both directions.
An orphaned sidecar (which `pnk sync` deliberately keeps) inflated the denominator: 8 of 10 real
documents linked read as 27% and passed a 35% cap. A document whose sidecar had not been minted was
invisible, so the gate reported nonsense on any KB where sync had not run. Documents now come from
`[sources] include`, which is what the word means.

**HIGH — two documents kept a privacy claim the increment made false.** `README.md` still said
*"The sole KB here is a small synthetic corpus"* and `CLAUDE.md` *"The only KB here is the synthetic
demo corpus"*, while `DESIGN.md` was updated in the same commit to "the two synthetic corpora". The
repo contradicted itself about what had been committed, in the section a reader consults **because**
they are worried about exactly that. The *audit-the-neighbourhood* rule exists for this and I applied
it to DESIGN alone — the file I was already editing — which is the failure mode the rule describes.

**A claim that was true by coincidence, stated as if by construction.** The gate's docstring,
`check.sh` and the changelog all said it "counts the same population `pnk doctor` reports". The
*link* counts are the same population, by construction. The *document* counts are not: doctor counts
indexed documents, the gate counts files matching `include`. They agree on the committed corpora and
nothing makes them. The wording now says which half is guaranteed.

**Two gates and no test that either still exists.** L1 added a `check.sh` gate and a CI job and
asserted neither, so deleting either left the suite green — in a repo that already has
`test_check_sh_declares_the_pdf_quality_guard`, written for that exact failure. The convention was
there; I did not apply it. Both are pinned now, and CI's negative step additionally greps for the
message rather than accepting any non-zero exit, since a crash, a missing corpus, or `uv` itself
falling over all satisfy the weaker check.

**What the corpus taught about relations.** `counterpart` was used both as a reciprocated 1:1
pairing (inward loan ↔ outward loan) and as a loose association (courier requirements → outward
loan). A later increment reading `counterpart` as a pairing would be misinformed by its own fixture.
Now `governs`.

**The `self`-form fixture is not a fixed point of the product's own writer.** `sidecar.write`
resolves `self` to a ULID on write, so anything that reads and rewrites that file destroys the trap
L2 needs — and `pnk link` (L6) writes exactly that key. The test catches it, but a long way from the
cause, so the hazard is named in the test rather than left to be rediscovered.

**Mutation, twice.** Seven targets before the review, seven after the gate was rewritten. Two
mutations *appeared* to survive and were worth more than the ones that failed: the first had not
applied at all — a `str.replace` searching for `'self'` where the source says `"self"`, the exact
no-op `conftest._rewrite` refuses, met in my own mutation harness, which now asserts the
substitution happened. The second was real: nothing asserted that the report prints the cap **in
force** rather than the module default, so `--max-density 0.1` printed "27% of the 35% cap" and then
failed the corpus in the next line.

**And the verification gate caught its own author.** Renaming
`test_the_committed_split_is_what_pnk_doctor_counts` (misnamed — it never consulted `pnk doctor`)
turned `tests/test_verification.py` red until `docs/VERIFICATION.md` was updated with it. That is
I9 working on the first increment after it shipped.

## L2 — Reverse-scan (20260730 16:51)

**One root cause behind all three HIGH findings: I bypassed `manifest.load` and kept none of what
it was doing.** The bypass is right — a partner may run a newer pinakes whose manifest mentions keys
this one has never heard of, and refusing to read a neighbour's inbound links over that would make
every connected KB a version dependency of every other. But `load` is not only a parser; it is also
the place that rejects an absolute `[sources] roots`, rejects `..` in one, and validates the include
patterns. Reading the TOML directly removed all of it and replaced none of it, and the partner's
manifest is **input this KB does not control**. Every one of the three failures below is that same
sentence.

**A partner renaming its own `docs/` silently deleted every inbound row it had.** A `roots` entry
that is not a directory was a quiet `continue`, so the walk yielded zero sidecars, reported
`complete=True`, and the caller did exactly what it is written to do with a complete walk: delete
and replace. Reproduced — rows 1 → 0, `link_scan` empty, `last_scan` stamped fresh, so the retry was
suppressed for a full window too. This is precisely the mass deletion the `complete` flag exists to
prevent, arriving through the one door the flag was not watching, and **no "successful walk" test
could ever have caught it** because they all leave the partner's sidecars where they are. A missing
root is now a walk failure with a reason.

**The partner's `exclude` was ignored, while a comment claimed otherwise.** `sidecars_under`'s
docstring said a document "whose document was excluded" contributes nothing; it read only `roots`
and `include`. The shipped `notes` template stamps `exclude = ["**/drafts/**"]`, so this is not an
exotic configuration — it is the shape of every KB `pnk init` creates, and the scan was recording
inbound links from documents the partner's own KB does not contain.

**A partner's manifest could crash `pnk sync` on a git hook.** The `sidecars_under` call sat
*outside* the `try`, and `Path.glob` raises on patterns `manifest.load` would have rejected —
`NotImplementedError` for a non-relative pattern, `ValueError` for an empty one. Both escaped
`sync()` entirely. The module's central promise is "nothing here raises", precisely so a partner
that is merely broken cannot block a commit; the one call that could raise was the one left outside.

**Two tests that could not fail, both of mine.** `test_the_partner_is_never_locked` asserted the
partner had no `.pinakes/` — on a fixture where the partner was never synced, so the directory had
never existed. It proved nothing was created and nothing whatever about locking; it now holds the
partner's real `SyncLock` while the local sync runs. And a test asserting no SQLite connection was
left open re-asserted pre-existing `sync()` behaviour (`_run`'s `finally: close()` always releases
it), so no L2-shaped defect could have made it fail. Deleted rather than kept: a test that cannot
fail is worse than no test, because it is counted.

**A failed local run blamed the partner.** `known_documents` is read from the index, so a document
that failed to index *this run* is absent from it — and a genuine inbound link was then reported as
pointing at a document this KB does not have. It does have it; it failed to index it. The local
picture is now passed as `None` on a failed or budget-stopped run, which suppresses that check
without touching the rows, since the rows come from the partner and owe nothing to our state.
`_run` already guards `active_content_hashes` on `report.ok` for the same class of reason — the
precedent was there.

**Dead code that credited itself with someone else's work.** `ScanResult.delisted` and the
`known_kb_ids` parameter were computed every sync, complete with a docstring explaining that the
rows "are removed" — by a function that never read either. The sweep is `store.forget_reverse_links`,
which takes the manifest's ids directly. Removed, along with the `SELECT DISTINCT` that fed it.

**Mutation: 11 targets before the review, 5 more after, all detected.** The one apparent survivor
was equivalent code rather than a gap — taking `src_kb_id` from the declared id instead of the
partner's own is indistinguishable wherever a row is written, *because* the mismatch guard refuses
first. The guard is what carries the weight, so the test asserts what makes the assignment moot: a
mismatched id writes no rows and no `kb_refs` entry.

**And a test premise of mine was wrong, which the failure said plainly.** `_replace_links` only runs
for a document that gets an action, so the reverse-then-authored ordering needs the document to
actually change — a second sync skips everything and rewrites nothing. Worth keeping because it is a
fact about when authored links are re-asserted at all, not just about this test.

## L3–L4 — The traversal core and `pnk links` (20260730 18:06)

**Four HIGH findings, all in the properties the increment's own prose claimed loudest.** That is
the pattern worth keeping: the module docstring argued at length for double-capping, precedence and
server-side clamping, and each of those three was where the defect was. Writing the argument down
appears to have substituted for checking it.

**The response was half-capped.** `max_rows` and `token_budget` gated `neighbours`; the `frontier`
was appended to unconditionally. Measured: a caller asking for **one** row received **1,000**
frontier entries — and the frontier is the part an agent parses to decide what to ask next. Now
capped, and ordered so that entries about nodes you did *not* get come first: capping without that
ordering let the `depth` notes of accepted nodes fill the whole budget and crowd out every `rows`
note, so a caller asking for 2 of 5 was told nothing about the 3 it missed.

**"Every bound is clamped server-side" was true of two of the four.** `max_rows=10**9` returned
3,660 rows with an empty `truncated`. Three documents said otherwise. Once this is reachable over
MCP the caller supplying `max_rows` is the untrusted party, so the sentence was not merely
inaccurate.

**A frontier entry contradicted the answer beside it.** A node dropped by fan-out at one hop and
reached at another kept its `fanout` entry — while sitting in `neighbours` and having been
expanded. `FrontierEntry`'s own docstring says "discovered and **not** expanded". Stale drops are
now retracted at return; `terminal` and `depth` are kept, because those describe accepted nodes
deliberately not expanded, which is the contract rather than a contradiction of it.

**Half the stated precedence was inverted.** The row and token checks ran before terminality was
consulted, so a terminal neighbour dropped by the row cap reported `rows` — inviting a retry with a
*smaller* request, which cannot help. Of the ten pairs the declared order implies, five were
backwards and exactly one was tested: the one the code happened to honour.

**The gate had three separate ways of being vacuous, and its docstring was an essay about gates
that cannot fail.**

* It passed against a `traverse()` that returned an empty `Result` — every check was one-sided, so
  zero neighbours satisfied all of them. Now equalities.
* It imported `MAX_DEPTH` and `MAX_ADJACENT_K` from the code it gates and compared them with
  themselves. Raising the caps to 10 and 150 moved the walk and the gate still passed, while
  `docs/MANIFEST.md` went on promising 64. The documented numbers are now literals in the gate — a
  second copy, which is the only thing that makes a silent change show up.
* It had no negative check, in a repo where the *immediately preceding* increment added one to its
  sibling job and a test that guards it. Added, with a `--expect-depth` override so CI can drive
  the gate into failure on purpose and assert the stated reason.

**Two more the same pass found.** The row cap truncated by parent-expansion order while ranking was
per-parent, so a top-ranked neighbour behind a low-ranked parent lost to a worthless one in front of
it — the same mistake as truncate-then-rank, one level up. And node-level row dedup silently dropped
a second distinct relation to the same target, in a module whose contract is that a fact about the
graph is returned rather than dropped; rows are now deduped per **edge** while expansion stays per
**node**.

**A dead sort term with a docstring defending it.** `_rank` sorted by `(-weight, distance,
node_key)` and explained that a nearer neighbour of equal weight ranks higher. `_rank` is called
with one hop's candidates, so `distance` was constant in every sort. Removing it changed nothing —
which is how it was found, and is the argument for deleting rather than believing prose.

**A test that could not hold its name.** `test_depth_counts_logical_hops_not_physical_edges` had no
hub in its fixture and its own docstring conceded the core never sees one; it was a second copy of
the clamp test wearing a larger claim, and `docs/VERIFICATION.md` cited it for a promise it could
not carry. Renamed to what it actually checks. The logical-hop promise belongs to the provider that
composes hubs.

**And new behaviour shipped without tests.** `[retrieval] adjacent_k` and `_toml.integer(maximum=)`
had none — the commit message's claim that a value above the cap is *refused* rather than clamped
was asserted and never executed, against this project's own rule that tests ship in the increment
that introduces the behaviour.

**A process failure worth recording separately.** L4 was built in L3's worktree while L3's
adversarial review was still reading it, so the reviewer found the tree dirty with a parallel
increment's work and had to run every probe against a copy. It cost the review nothing this time
because L4 added files rather than editing `traverse.py`, but that was luck. One increment, one
worktree, and the review finishes before the next one starts.

**Four silent `str.replace` no-ops this session**, one of which spliced a new import into the middle
of an existing one and produced a nonsense symbol. It is the same failure `conftest._rewrite` exists
to refuse, met in editing rather than in a fixture. Non-trivial edits now go through a tool that
errors when its anchor does not match.

## L5 — `pinakes_links` on the MCP surface (20260731 11:29)

### The defect was in the field nobody thought to assert

L5's own mutation pass killed all three of the targets the plan named. An adversarial review then
mutated **eight more** payload fields and watched every one survive the full 887-test suite. Two of
those were real defects, not merely untested:

- **`direction` was keyed by node, while a row is `(node, rel)`.** Given `a --related--> b` and
  `b --cites--> a`, asking about `a` reported the citation as running *from* `a` — the opposite of
  what someone wrote. Shipped in L4, copied verbatim into L5, wrong on both surfaces. The provider's
  own docstring argued the case for the key it used: *"Keyed by node, because a node reached both
  ways is still one neighbour"* — true of the node, irrelevant to the row.
- **`DIRECTIONS` was defined and never enforced.** `edges_of` tests `in ("out", "both")` and
  `in ("in", "both")`, so `direction="outbound"` ran neither query and returned a confident empty
  answer with a "no links from here" hint. `argparse` `choices` covered the CLI; the MCP surface,
  the one an untrusted model types into, had nothing.

**The lesson that generalises: a field with no assertion is a field that can be a constant.** Ask of
each one, "which mutation would this catch?" — not "is it correct?". `scored_by_query`, the field
L3's docstring calls load-bearing, could be frozen to `True`; `unresolved`, whose contract says
"returned, never dropped", could be frozen to `[]`.

**A tidy fixture defeats a mutation test.** Three fields survived even after tests were written for
them, because the KB-backed fixtures were too clean: the fake embedding backend's vectors are
orthonormal, so every cosine is exactly 1.0 and deleting `round()` changes nothing; nothing hit a
response cap, so `truncated` could be frozen empty; no frontier entry sat past distance 1. The fix
was to build the dataclasses directly and take the fixture out of the question.

**Two copies of one payload had already drifted** — the MCP `frontier` carried a `distance` the
CLI's did not, `scored_by_query` reached only one of them, `unresolved` dropped a `kb_id` its
sibling lists carried. Neither failed, because nothing compared them. They now share
`pinakes.graph.present`, and a test asserts both surfaces project the same keys.

**Calling a tool is not the same as exercising it.** The free-path gate was strengthened to *invoke*
`pinakes_links` rather than only list it — but the fixture KB had one document and no links, so the
whole neighbour projection never executed. A `raise SystemExit` planted in that loop never fired.
The fixture now authors one intra-KB and one unreachable-KB link, and the same probe fires.

**The fix for a wrong answer produced a differently wrong answer, and the tests written with it
could not see that either.** Keying `directions` by `(node, rel)` was right; merging to `both`
across *expansions* was not. `directions` accumulates over the whole walk, so an edge discovered
while expanding an unrelated parent rewrote a row already emitted from the start — and a row's
`direction` then changed with `--depth`, to exactly the untruth the fix was written to remove. Both
new direction tests ran at `depth=1`, where the start is the only parent, so neither could reach it.
A second adversarial pass found it by varying the one parameter the tests held fixed.

The generalisation: **when a fix adds a rule, test the axis the rule is defined over.** The rule was
about *which expansion* a direction came from, and every test pinned a single expansion.

**A third pass found no new defect in the traversal itself, and four in what surrounded it.** The
`(node, rel)` scheme was probed against a reciprocal pair, a mutual same-rel pair, each `direction`,
a self-loop, a 3-cycle, a node reached at two different hops by different relations, a node reached
by two parents in one hop with opposite directions, and a node dropped by fan-out then re-reached —
all correct. What was still wrong sat one layer out: an assignment nobody asserted, a message worded
from the wrong end, a branch ordered ahead of a better one, and an assertion satisfied by a
substring.

Two of those are worth naming as patterns:

- **`assert "-> related: b" in output` passed on `<-> related: b`.** A substring assertion over
  rendered text will match a *longer* glyph containing the shorter one, so dropping the outbound
  arrow entirely left the test green. Match whole lines when asserting on human output.
- **Splitting `f(x, scores=s)` into `f(x); f.scores = s` moved a value out of the type checker's
  reach.** The construction was covered by the tests that built providers directly; the assignment
  was covered by nothing, and deleting it disabled query ranking with every gate green. When a
  refactor turns an argument into a mutation, the mutation needs its own assertion at its own call
  site — and there were two call sites.

**Left for the graph release** (L3 core, predating this increment, found while probing): a node
dropped by fan-out at hop 1 and re-reached at hop 2 is emitted with `distance: 2` although it is one
authored hop from the start; and a self-loop (`a --sameas--> a`) is dropped entirely — not a
neighbour, not unresolved, not on the frontier.

**A fix applied to one surface is half a fix.** Round 3 gave `pinakes_links` the rule that a
narrowed walk reports the narrowing before it reports dangling links — and left `pnk links` branching
on `unresolved` alone, in the same commit, so the CLI told a user their links "resolve to nothing"
about a document with a live neighbour one dropped `--rel` away. Both the docs and the changelog
described the MCP behaviour as though it were both. The two surfaces now share
`present.is_filtered` and `present.arrow`, which is the only way this stops recurring: the rule has
to live in one place, not be applied twice.

**A remedy in an error message is a claim, and it was false.** The dangling-links hint sent the
caller to `pnk doctor` — but `doctor._links` inspects only the *destination* side of local sidecar
rows, so when the missing endpoint is the link's **source** (a deleted document whose outbound rows
survive the soft delete) doctor reports `links: OK` and contradicts the message that sent you there.
Dropped the clause; extending that check belongs to L7, which owns doctor's link coverage.

Four review rounds, each finding real defects in the previous round's fix, then converging: 11
findings, then 11 with one HIGH, then 7 with none, then 5 with none. What the last two rounds found
was never the traversal — it was the layer around it: an assignment nobody asserted, an assertion
satisfied by a substring, a message worded from the wrong end, a branch ordered ahead of a better
one, and a rule applied to one of two surfaces.

**The rule two rounds were spent getting right had no test that could detect its inversion.** Round
5 found the shipped behaviour correct on both surfaces and the precedence — *filter before dangling
before "no links"* — freely reversible with the suite green. The cause was a fixture that could not
make both conditions true at once: `--rel` narrows `provider.unresolved` as well as the neighbours
(`edges_of` receives the same `rel`), so a rel-filtered call leaves `unresolved` empty and the
branch being out-ranked never competes. `--direction` is the lever that does it — an outbound link
that dangles and an inbound one that is live. The assertion that named the defect in its own message
(*"one dropped argument away from a live neighbour"*) was the vacuous one.

**Test the discriminating case, not the two sides separately.** A precedence rule is only observable
where both branches are eligible; a fixture that satisfies one at a time asserts the wording of each
and the order of neither.

## L5b — `ruamel.yaml` replaces `pyyaml` in the sidecar (20260731 11:29)

### Swapping a YAML library is not a swap

**The plan predicted three failures precisely, and all three landed as written** — which is worth
recording because it is the first increment in this project where that happened. It named the 872nd
test (`{id: x, : }`, which ruamel parses, so the case fell through to the `id` check and the
parse-error branch had been asserting nothing), the free-path gate being red on day one, and the
`ScalarBoolean` coercion being insufficient at one level.

**The free-path gate was defeated by its own harness, and I wrote the defect.** `_author_links` in
`tests/free_path_run.py` — added in L5 to close a coverage hole — wrote a sidecar through
`yaml.safe_dump`. That put `yaml` into the very module list the gate inspects, and it was also the
last PyYAML sidecar *writer* in the repo: a fixture written by one library and read by another,
which is exactly the divergence the gate exists to forbid.

**`existing[:] = keep` wipes ruamel's comment metadata outright.** Reconciling a sequence by
rebuilding a keep-list destroys `CommentedSeq.ca.items` entirely — every comment in the block, not
just the removed entry's — while `del existing[index]` shifts the survivors. Measured: `{}` against
`{0: '# first', 1: '# third'}`. Both merge functions had it.

**A comment before a sequence entry belongs to the entry above it**, exactly as it does for a
mapping key. The plan pins the deletion limitation for mapping keys; it is broader than that. After
deleting the middle of three commented links, `# first` stays correct, `# second` reattaches to the
*third* link, and `# third` disappears. The surviving links are all correct; the prose beside one of
them is not.

**"Unobservable" was the wrong conclusion; "observable only where something else is broken" was the
right one.** The plan's *"assign a known key only when its value actually changed"* looked untestable
— every known-key value is the node read out of the document and written straight back, so a write
of an unchanged document is already a no-op. Two attempts at a test passed against the mutated
source and I wrote that no mutation of it could fail. A reviewer then removed the rule and the
committed corpora stopped round-tripping: the short-circuit was **masking** the duplicate-link
defect below, not proving its own redundancy. Once that was fixed the rule really was unobservable
— but the claim was true by accident for two commits, and the difference is exactly what an
adversarial pass is for.

**`-x` makes a mutation look like it was caught by the wrong test.** Two links mutations appeared to
be killed only by an unrelated pre-existing test; without `-x` both were also killed by the test
written for them. Run the mutation pass without early exit, or the report is about test ordering.

**A merge key must be the identity the storage layer already uses.** Reconciling `links` on `to`
alone looked sufficient and is undefined the moment two links point at one document with different
relations — which `_links()` accepts and the index stores as two rows, its primary key including
`rel`. Measured on the version that had it: dropping an *unrelated* third link rewrote the first
link's `rel` to the second's and deleted the second, leaving one row carrying the wrong relation
under the other's comment. The index's own `PRIMARY KEY` was the answer, and it was already written
down in `store.py`.

**A recursive rule needs a depth bound as much as a base case.** "A key absent from the new mapping
is deleted" is required at the top of `provenance` — or `--force` leaves a false paid claim behind —
and destructive one level down, where `with_extraction_provenance` builds a plain four-key
replacement and the user's own `reviewed_by` sits beside `content_hash`. One sentence, two opposite
correct answers, distinguished only by depth.

**The exit criterion was the thing nobody ran.** The plan's one falsifiable sentence — *every
committed sidecar still round-trips* — had no test, and running it by hand found a `pnk://self/…`
entry in `partner-kb` being deleted, rebuilt without its unknown per-link keys, and moved to the end
of its block. `_links()` expands `self` on read, so the loaded entry's raw `to` never equals
anything in the reconciliation set. The docs bounded the invariant with "`pnk://self/…` expansion",
which reads as *the URI text changes* and not *the entry is rebuilt* — a documented exclusion that
quietly covered a defect.

**Quoting was applied on the path that was tested and not on the path that ships.** Decision 23's
predicate reached the merge branch and the mint, but not the branch taken when a key **first
appears** — which is the branch `pnk link` will follow on a sidecar that has no `links:` yet, i.e.
almost all of them. Three quoting mutations survived the whole suite.

**An error message is part of the interface.** Three of this increment's breaking changes surfaced
as `TaggedScalar`, `ScalarFloat` and `OctalInt` — ruamel class names, from a library the user never
chose, with no remedy. The type is not what they need; "quote it, or drop the tag" is.

**A fix instruction can carry its own defects, and two of pass 6's did.** Keying `links` on the
`(to, rel)` pair made the pair the *entire content* of an entry, so no matched entry was ever
updated and every `rel` edit became a delete plus an append — landing straight in the comment
misattribution the rule was written to avoid. And "positional fallback among equal pairs" was too
vague to implement; what I wrote from it used a `set`, which collapses two identical entries: three
links in, one out. The final rule needed three explicit clauses — resolve before comparing,
multiplicity never a set, assign `rel` in place — each naming the shipped version that got it wrong.

**"Exactly the call being protected" was true of the call and false of the argument.** The
JSON-encodability check ran `json.dumps(extra, sort_keys=True, ensure_ascii=False)` — the same
function `store.dumps_metadata` calls — over `extra` alone. `_metadata()` hands that function
`{"tags": …, "provenance": …, **extra}`. A uniformly int-keyed `{1: a}` sorts perfectly on its own
and becomes mixed the moment the string keys join it, so `pnk sync` still crashed. Checking the
parts is not checking the whole, and the docstring asserting otherwise is what made it look done.

**Two tests could not observe what they claimed, for the same reason.** A plain read-write of an
unchanged document short-circuits before the merge runs, so a `wanted` that deduplicates survived
`test_two_identical_link_entries_both_survive` and a `set`-based collapse was invisible. Any test of
reconciliation has to *change* something first, or it is testing the short-circuit.

**A warning is not an error, and a library that downgrades one is changing behaviour.** A reused
anchor name raised `ComposerError` — a `YAMLError` — before the swap, and after it the document
loads, every alias resolves to the **last** anchor of that name, and the only signal is a
`ReusedAnchorWarning` on stderr. Three consequences, none visible in a passing suite: the value
silently changes; `read()`'s `except YAMLError` never sees it, because a `Warning` is not one; and
under this project's `filterwarnings = ["error"]` it escapes as a bare warning traceback rather than
a named error. Promoting it at the load makes the outcome independent of whatever warning filters
the calling program happens to have set — which is the right place for a property of the file
format to live.

**An exclusion list is a set of claims, and claims rot.** Every bound on the byte-identity
invariant — indentation, `!!` tags, anchors, CRLF, BOM, document markers — was prose in a table
until it was pinned by a test. Writing those tests measured two behaviours that were *not on the
list at all*: a plain (non-recursive) anchor on an **empty** value is destroyed, where the list
named only the self-referential case; and a file with **no trailing newline** gains one. Both are
byte changes to a file nobody edited, which is exactly what the invariant claims does not happen.
A bound stated only in prose cannot notice the library moving under it, and cannot be wrong out loud.

It also falsified a changelog line I had written: *"`!!int`, `!!float`, `!!bool`, `!!seq` and
`!!map` keep working — verified"*. Verified of **loading**; the tag itself is dropped on write, so
`!!int 3` comes back as `3`. True of the value, false of the invariant, and the word "verified" is
what made it read as covering both.

**A gate that has never been shown to fail is a claim too.** The AST scan now proves it sees all
four shapes of a planted import — including the function-scoped one an import walk cannot reach —
and does not fire on any of the four legal `ruamel` forms, every one of which contains "yaml". The
stub signature test proves it can fail: writing `transform` into the expected set failed it,
because `transform` belongs to `dump` rather than `__init__`.

**"PyYAML left the runtime" is true of what pinakes declares and false of what a user's machine
has.** Measured on a built wheel: bare, `yaml` is absent; `pinakes[light]` has it, transitively from
`huggingface_hub`. `starlette` and `uvicorn` list it too, but only under an extra they do not pull.
So the CI assertion is correctly scoped to the bare wheel — pinakes never asks for PyYAML — and the
consequence is the part worth remembering: **`import yaml` will succeed in a real install**, so a
stray import in `src/` would quietly work instead of failing loudly. That is what makes the AST scan
load-bearing rather than a second belt.

**The worst defect in this increment was a rule the plan itself wrote.** *"One instance, reused
rather than reconstructed per call"*, justified by 282 µs against 399 µs. ruamel keeps the `%YAML`
directive from the last `load()` **on the instance** and applies it to every later load *and* dump:
read a sidecar carrying `%YAML 1.1`, then write an unrelated one that never did, and it comes back
with the directive injected and `country: NO` rewritten to `false`. The exact corruption this
increment exists to remove, reintroduced *across documents*, in exchange for 117 microseconds — and
freshly minted sidecars are contaminated the same way. Nothing softer fixes it: resetting `version`
after the load still emits the directive, pinning it up front is overwritten by the next load. A
performance justification measured in microseconds should be read as an argument that the
optimisation does not matter.

**A gate that never reads the artifact it guards is checking a copy.** The stub-signature test
listed the symbols in a hand-written Python dict, checked them with `hasattr`, and compared against
hardcoded signature supersets — so a stub declaring a parameter ruamel does not have was green under
pytest *and* pyright, which is the single failure decision 20 exists to catch. It parses the `.pyi`
files with `ast` now.

**A fixture can be right for the wrong reason and hide the defect it was written for.** The
two-links-sharing-a-`to` test edited the *first* entry, and entries are walked in descending index
order — so the single-pass form it was meant to catch happened to produce the correct answer.
Editing the *second* entry is the discriminating case: its fallback claims the link the first was
owed exactly, and both relations end up swapped under the wrong comments. Two of this increment's
tests have now needed the *specific* case rather than a representative one.

## `main` was red for four merges, and local `check.sh` could not have known (20260801 06:05)

Four tests written across L6 and L7 passed on macOS and failed on CI, so `2314dea` (L6) and
`ed01b00` merged onto a red `main` and stayed there until L8's verification step 1 looked.

**Two causes, one shape: a test that cannot build its precondition does not skip — it asserts the
wrong thing.**

- **`chmod(0o000)` is not a portable way to deny a read.** Three fixtures built an "unreadable
  directory" that CI read anyway: `pnk link` reported `no pinakes.toml there` where the test
  demanded `Permission denied`, and `'docs/locked/x.md' is not a document in this KB` where it
  demanded `cannot be read`.

  **The first fix was wrong, and its wrongness is the lesson.** It probed whether permissions are
  enforced and skipped when they are not — reasoning that CI runs as root. CI is *not* root: the
  probe reported permissions enforced, did not skip, and the run failed identically. Whatever that
  runner does with a mode-000 directory, `is_file()` neither succeeded nor raised `EACCES`.

  Skipping was the wrong shape regardless. It disables the guard **exactly where it broke** — the
  environment the test could not model is the one that most needed testing. The refusal is now
  *injected*: `Path.is_file` raises `PermissionError`, which is precisely what the guard exists to
  catch, on every platform and with no filesystem semantics in the way. A test for "an `OSError`
  becomes a `PinakesError`" should raise an `OSError`, not arrange for the operating system to.
- **Two more of the same shape, found only by pushing the fix and watching CI again.** A
  300-character filename asserted to produce `ENAMETOOLONG` — the length at which a filesystem
  says that is a property of the filesystem, and on CI the name was simply not a document. And an
  embedded NUL in an `include` pattern asserted to raise from `resolve()` — on CI it raised
  nothing, so the test asserted a problem that never occurred. Both now raise the error directly.

  **Every one of these tests asked the operating system to produce an error, and then asserted on
  the answer.** That is a test of the platform, not of the guard. The guard's contract is "an
  `OSError`/`ValueError` from this call becomes a `PinakesError`" — so the test should raise one.

- **`pathlib`'s wording is not a contract.** A test asserted
  `Unacceptable pattern: PosixPath('.')`, which CPython renders as `Unacceptable pattern: ''` on
  other versions. The increment's promise is that the pattern *the author wrote* is named and the
  other `include` entries survive; that is what it asserts now. Third instance in two increments of
  asserting a phrase where the property was meant.

**The process failure is the larger one.** `./check.sh` was green before each merge, and green on
one developer machine is not green on the three-leg CI matrix — different OS, different Python
patch, different privileges. The project rule already says to check whether the latest run on the
default branch actually succeeded; it was not checked after either merge, and the second merge
landed on top of the first failure without noticing it.

**`gh run list --branch main` belongs in the merge sequence, after the push**, not in the next
increment's verification step. A red default branch blocks the release either way — finding it two
merges later only makes the bisect longer.

## G1 — Is the eval reproducible? (20260801 00:52)

Decision 15 said measure before fixing, and the measurement paid for itself twice: once by finding a
real defect, and once by contradicting the fix that was nearly written for it.

**HIGH — the eval was reproducible by luck, and the luck was invisible.** Running the golden set,
editing a document, re-syncing, rebuilding and comparing *per-question* outcomes: the real `[light]`
models agreed everywhere. A low-dimensional fake disagreed on one question in 41 between an
incremental sync and a `--rebuild`. Both facts are the same fact — 384-dimensional cosines almost
never tie exactly, and every tiebreak underneath resolved to `chunks.id`, the rowid, which
`store.py`'s own schema comment says has no identity across rebuilds. A property that holds because
the corpus never exercises it is not a property, and G5's sign test was about to be built on it.
The fix is total ordering on `(documents.path, chunks.ordinal)` at three sites plus a stable
`argsort`; **no measured number moved**, which is the right outcome for a change that only breaks
ties, and is why this increment rewrites no baseline and needs no amendment to L8 step 5.

**HIGH — the fixture was the algorithm, in the one place that judges the algorithm.** The first
version of the tests used eight dimensions, reasoning "fewer dimensions, more ties". Swept against
the genuine pre-fix code, eight and sixteen dimensions both reported **zero** differences across all
four perturbations: collapse the space far enough and every candidate ties, so the ordering
underneath stops reaching the top-k at all. The relationship is not monotonic — 32 caught two
perturbations, 64 caught one, 128 caught two. Had the sweep not been run, G1 would have shipped a
green gate, a green test suite and a live defect, all three agreeing. The sweep is recorded in the
gate's own `DIM` docstring rather than the conclusion alone, because the next person's intuition
will be the same as this one's.

**HIGH — the mutation harness deleted the thing it was measuring.** The first mutation run restored
each mutation with `git checkout -- <file>`. The fix was uncommitted, so the first restore reverted
it; every later mutation then failed to apply to code that no longer had the target, and the suite
ran green against **original** code four times while reporting "0 failures" as though the mutations
had been survived. It read exactly like a well-tested change. Two rules fall out. *Restore from a
copy of the mutated-from state, never from `HEAD`* — `git checkout` restores to the last commit,
which is a different thing from "undo my mutation" whenever the work is uncommitted. And *a mutation
harness must assert that its mutation applied*: the rewritten one fails loudly if the target string
is not found exactly once, which is what turned three silent no-ops into an error.

**MEDIUM — a stable sort needed its own test, and the obvious one was vacuous.** `kind="stable"`
changes nothing a repeated run can observe: on a fixed input array NumPy's introsort is
deterministic. It changes what happens when the array *grows*, because partitioning depends on the
whole array — measured at 500 of 500 random tie-heavy arrays reordering their original entries. The
first test written for it used four tied chunks and passed under the mutation, because NumPy uses an
insertion sort below roughly sixteen elements and insertion sort is stable whatever `kind` says. A
fixture can be too small to contain the behaviour it is named after.

**What the increment ended up asserting, and at which level.** Three end-to-end tests state the
property G5 needs, over the committed corpus and questions; four site tests each drive one ordering
decision directly and are the mutation targets — one mutation, one failing test, verified for all
four. The two levels are not redundant: the end-to-end tests can only observe ties the corpus
happens to contain, which is precisely how the defect survived three releases.

### The adversarial pass over G1's own diff (20260801 01:25)

Six findings, four of them real defects in work that was already green.

**HIGH — a gate advertised a field it had retired.** `_plant` rewrote the reranker's *model* name
and left `[retrieval.confidence] fitted_for` naming the real one, so `_confidence` short-circuited
and all 41 questions scored `unknown`. Both the gate's docstring and the tests claimed to compare
the confidence label. Naming the reranker was not enough either: the committed thresholds were
fitted on a real cross-encoder's logits and sit below every score the fake can emit, so the label
became a constant `high` — still unable to move. Thresholds inside the fake's range give
35 medium / 5 high / 1 low, and the field is finally live. **The class of defect matters more than
the instance:** a fixture that rewires half of a calibrated pair silently disables the thing it was
calibrated for, and nothing fails.

**HIGH — the plan still asserted what the measurement disproved.** Decision 15 says a final tiebreak
would be *"a provable no-op"* because cross-document ties are totalised by `documents.path` and
rowid order is ordinal order. Both premises are true about **writes** and irrelevant to the
**output**: `documents.path` cannot separate two chunks of the same document, and an incremental
sync by definition does not rewrite the files it did not touch, so rowid order stops matching corpus
order at the first re-chunked file. The plan is an executor doc; leaving that cell intact would have
licensed a G2–G5 executor to skip a tiebreak for a reason this increment measured to be false.

**MEDIUM — half the gate's sweep has never observed anything.** Of its four perturbations, *added*
and *removed* report zero differences against the genuine pre-fix code at every width swept
(8/16/32/64/128), while *edited* and *renamed* bite. `--inject-difference` cannot reveal this: it
corrupts all four alike. The gate now states it. **A gate's own justification is a claim like any
other** — this one said "it sweeps four ways where the tests exercise one", and two of the four were
along for the ride.

**MEDIUM — the contract's file table was checked against the wrong question.** It compared the two
tracks' *owned* files and never asked what a new gate touches. Every gate edits `check.sh`,
`ci.yml` and `tests/test_check_script.py`, which both tracks append to at the end of the same
regions; and G1 necessarily edits `search.py` and `store.py`, which the table lists under neither
track, because reproducibility is a property of core retrieval. Widened, with the reason.

**LOW, and recorded rather than fixed —** making the BM25 cut total costs a join: +11.5 ms on a
50k-chunk corpus where every chunk matches every term. That is the worst case a planner can be
given, the correctness is not optional, and the number now sits in `docs/STATUS.md` so a later
change can argue with it.

**What the pass confirmed, having tried to break it:** `bm25()` still resolves with the alias
present and returns byte-identical rows; the join multiplies nothing (both sides unique); the
`load_vectors` reordering costs nothing measurable; `graph/provider.py`, the other caller, reduces
to a per-document max and is order-independent; the four site tests each fail against pre-fix code;
and the artifact paths, cache keys and macOS wheels in the cross-machine job all resolve.

## L6 — `pnk link` (20260801 01:41)

**Every review commit on this increment found defects in the one before it, and most of them found
the previous commit's own fix or claim** rather than something it had missed — `3ce150e` (review 1's
containment fix had traded one defect for two), `986faf3` (review 2's fix was right; its stated
justification was not), `7b3f0a3` (the escaping-error class sat one line above the `try` added for it),
`9c8f667` (the totality fix re-anchored the walk on the working directory), `cdee8d8` (the test for
an untested branch entered it, but its assertion held either way), `dbebd8b` (a severity asserted,
not measured), and the last three, which took four goes at one containment rule.

No total is given, deliberately. Three drafts stated one and all three were wrong, because it
changes depending on whether `8b` and `9b` count as rounds of their own — and the last wrong figure
was introduced *by the commit correcting the one before it*. `git log main..HEAD` is the answer, and
it cannot go stale. What follows is the state after all of them, not a log:
the rule is to rewrite to the current state rather than layer corrections, and earlier drafts of
this fragment broke it four times — describing a concurrency
scenario a later round had disproved, calling every self-link a typo after the fix for the other
case existed, counting the rounds that had happened when it was written rather than the ones that
had, and asserting a safety property (*"`Path.resolve()` is safe at both call sites"*) that was
wrong twice over: `strict=False` suppresses `OSError`, not the `ValueError` an embedded NUL raises,
and there are six `Path.resolve()` sites across the two modules rather than two.

### One defect class, six instances, and why fixing it at the call site produced them

**HIGH.** `cli.main` catches `PinakesError`. Anything else is a traceback on a user's terminal — or
on an unattended `post-commit` hook. Six calls in this increment's blast radius raised something
else:

1. `Path("~nosuchuser/x.md").expanduser()` raises `RuntimeError`, on `<source>` in `link.py`. It
   bought nothing either: a `~` that *does* expand lands in `$HOME` and is refused by the
   containment check on the next line. Copying a call across a boundary copies its justification
   too, and `linkscan`'s need for it (a `[[links.kb]] path` may be `~/kbs/partner`) did not survive
   the trip.
2. `Path.is_file()` ignores `ENOENT`, `ENOTDIR`, `EBADF` and `ELOOP` and **raises everything else**
   — so an unreadable parent directory (`EACCES`) and an over-long name (`ENAMETOOLONG`) on the
   same source path.
3. The `is_file()`/`is_dir()` pair one branch over, in `_via_alias`: a partner KB directory this
   user cannot read raised `PermissionError`.
4. `resolve_path`, on the line immediately above the `try` just added for (3).
5. The same three, in the module `link.py` calls into. `linkscan.scan_one`'s docstring promises
   *"Never raises: every failure comes back in `issues`"*, and all of them sat in the three lines
   that ran before any handling did — so `pnk sync` on a hook became a traceback. There since L2.
6. `resolve_path` again, bare in `scan()`'s freshness branch — which **plain `pnk sync` takes**, so
   a partner path that stopped resolving crashed every `git commit` inside the TTL. The branch had
   no test at all.

Fixes 1–5 each wrapped the instance in front of them and stopped. What closed the class was moving
the guarantee into `resolve_path` itself — a guarantee three call sites each have to remember is a
function with the wrong contract — which then *removed* the wrappers fixes 4 and 5 had added.

**The first version of that fix introduced a worse defect than the one it closed**, and this is the
part worth keeping. `resolve_path` was made *total*: on text no filesystem call accepts it returned
`Path(raw)`, the declared text, so an error could still name what the author wrote. That value is
**relative**, and five consumers use it as a filesystem base — `(path / MANIFEST_NAME).is_file()`,
`why_not_a_kb`, `partner_sources`, `sidecars_under`, `_doc_id_of`. So the walk silently re-anchored
on the process's **working directory**: the precise thing `resolve_path`'s own first paragraph says
it exists to prevent, reintroduced four paragraphs below by the round that wrote it.

With a directory of that literal name in the CWD holding a readable `pinakes.toml`, `pnk sync`
walked the decoy, found nothing, stamped the scan `complete` — and `replace_reverse_links` deleted
every inbound row the real partner had, with `report.ok` true and no issue raised. That is the real
consequence, and it is silent data loss.

**Round 8 also claimed `pnk link` would write the decoy's ULID into the real sidecar, permanently.
It would not, and round 9 reproduced the refusal.** `_document_in` compares an absolute
`joined.parent.resolve()` against the *relative* `root`, which can never be `is_relative_to`, so it
fires before any sidecar is read — `'docs/one.md' is outside \`partner\``, which tells the user the
path they typed correctly is wrong and names neither the KB path nor the expansion failure. A
message defect, not corruption.

Three things kept that overstatement alive for a round. The true account was already in the tree —
`link.py`'s own comment describes the misleading refusal — so the increment carried both versions
at once. The regression test's docstring asserted the severe reading, and under the round-7
mutation it failed on its *first* assertion, so the two that encoded the severe claim were never
reached: **a test that fails proves the mutation is caught, never that it is caught for the stated
reason.** And the claim was written from the mechanism (a relative base re-anchors the walk →
therefore the walk completes) rather than from running it. That is the same "prose written from the
design" failure as the two documentation defects below, in a commit message and a retrospective —
the two places where being wrong is hardest to notice later, because nothing executes them.

The answer is `None`, not a fallback value: text that names no path yields no path, and pyright
makes every caller say what it does instead — a type-checked obligation rather than a remembered
one, which is the same lesson one level up. The declared text is still what the message names; it
was always available as `linked.path`, which every caller already held. **A total function is not
automatically a safe one** — totality only moves the failure from a raise to a return value, and a
return value that is the wrong *kind* of thing is harder to notice than an exception.

Four tests fail against the round-7 shape, verified by mutation — including the two written for
it, though one of those for a different reason than its docstring gave (above).

**A defect class is not closed until it has been searched for**, and the search is mechanical: list
every call in the module that touches the filesystem and ask of each which errno it swallows.

`Path.resolve()` belongs on that list and was wrongly excused twice. `strict=False` suppresses
`OSError`; it does not suppress the `ValueError` raised for an embedded NUL, which `tomllib`
accepts in a manifest and `pathlib` will not open. Enumerated rather than excused, there are six
sites: `_document_in` (`link.py:298`) resolves a path built from user text and is now guarded and
tested; `resolve_path` (`linkscan.py:178`) is the fix above; and `sidecars_under` has four —
`anchor`, the `roots` entry, the pattern probe and the per-candidate check — all inside the
caller's `except (OSError, ValueError, NotImplementedError, PinakesError)`.

The enumeration is the point: *"safe at both call sites"* named neither the number nor the reason,
so it could not be checked without redoing the work — whereas a count with line numbers is wrong
the moment it drifts, and says so. It has drifted twice already: round 8 corrected an earlier
version that called two of the `sidecars_under` sites partner-controlled when one is not, round
10's own fix added the fifth site, making "four" stale in the same commit that relied on it; and
round 13's added the sixth the same way.

### The containment check took three spellings, and the first two were each wrong in one direction

**HIGH.** `_document_in` decides whether a path names a document in this KB.

* `joined.resolve()` — the original — follows the **final** symlink before checking, so a symlinked
  *document* was refused as "outside this KB", with a remedy repeating the path the user had typed
  correctly. `pnk sync` indexes such a file, `pnk doctor` calls its sidecar readable and `pnk links`
  traverses it; only `pnk link` said it was not there, and nothing could link it in either
  direction.
* `os.path.normpath` — round 1's fix — follows **nothing**, so a symlinked *directory* under `docs/`
  passed containment: the write went out of the KB through it, and in the other direction minted a
  **permanent** `pnk://` to a ULID this KB will never index, because `Path.glob` does not recurse a
  symlinked directory. It simultaneously refused a legitimate *absolute* path whose ancestor is a
  symlink — the ordinary shape on macOS (`/tmp` → `/private/tmp`) and behind any symlinked checkout
  — because `manifest.load` resolves the root, so a verbatim comparison could never match it.
* `joined.parent.resolve() / joined.name` is right in both directions. The directory chain is
  followed, so an escape through it is caught and a symlinked ancestor lands inside; the final
  component is left alone, so the document's own symlink is irrelevant — which is correct, because
  `Path.glob` *does* yield a symlinked file.

`normpath` must also not run first: it collapses `docs/link-to-elsewhere/../x.md` to `docs/x.md`
textually, turning an escaping path into one that looks contained. `resolve()` on the parent
collapses `..` after following the links it sits behind.

**The docstring was wrong for longer than the code.** Two drafts justified the check with "what
decides membership is the path under `[sources]`" — a rule the check has never implemented, since it
compares against the KB *root*. Round 2 quoted that sentence as the lesson and left it in place;
round 3 found it still there. The residual it was papering over is now stated instead: a document
inside the root but outside `[sources]` can be linked, and the link will not resolve until that
document is ingested. Answering the `[sources]` question properly means re-implementing
`walk_sources` including its globs, and refusing a "link it now, ingest it next" order of work that
costs nothing.

### Two documentation claims the code contradicted, in prose written from the design

**HIGH.** The new `pnk link` section told the reader that a `pnk://` URI pointing at a KB not on
this machine is fine because *"`pnk doctor` reports a dangling target; `pnk links` lists it under
`unresolved`"*. Neither happens. `doctor.py` filters its dangling list to this KB — the cross-KB
check is **L7, the next increment** — and `provider.py`'s `unresolved` carries a docstring
explicitly refusing to widen: *"a cross-KB target cannot be checked from here without the other KB,
and reporting one as unresolved on that basis would be asserting something this index has no
standing to know."* A reassurance was invented for the one case the section was telling the reader
not to worry about, and half of it described something the design had already declined to build.

The replacement prose then made the same mistake twice more, which is the finding worth keeping.
Round 1's fix illustrated the missing lock with a `post-commit` hook firing a paid extraction — a
scenario `hooks.py` structurally prevents. Round 2's fix replaced that with "the one sync that
rewrites an existing sidecar is a paid extraction", which `sync.py`'s `--force`-plus-free-`--extract`
override falsifies, and which this increment's own edits to DESIGN, MANIFEST and CLAUDE.md all name
the carve-out for. **A correction is a diff and earns the same verification as the line it
replaces**; three rounds of unverified prose about the same paragraph is what happens otherwise.

### Fixtures that were representative rather than discriminating

**MEDIUM, four times.** A test can be green because the code is right or because the input never
reaches it, and the two look identical from the outside.

* `test_no_line_outside_the_links_block_changes_when_a_link_is_added` used a sidecar with a
  *populated* `tags:` list, which `write()` short-circuits as unchanged and therefore never touches.
  It could not have failed. Meanwhile `tags:` and `provenance:` written with nothing under them were
  being rewritten to `tags: []` and `provenance: {}` on every `pnk link` — two lines changed outside
  the block, in the increment whose test says none are, against a promise stated as byte-identity.
  Reachable before L6 only from a paid PDF extraction, which is why L5b's sweep missed it; `pnk
  link` reaches it on a *first* link, the common case. The sibling
  `test_a_known_key_with_a_null_value_does_not_crash_the_writer` parametrises exactly these three
  keys and asserts only `"id:" in text`: it pins the absence of a crash and nothing about the value.
* The embedded-NUL test put its NUL in the *filename* — `docs/a\x00b.md` — where only the parent is
  resolved, so it never reached the guard it was written for and passed against the ordinary "not a
  document" refusal. Moved into a directory component. Caught by mutation, not by review.
* `assert "outside" in message` against a fixture named `outside.md`, and `assert "partner" in
  message` against a `tmp_path` ending in `/partner`. Both were satisfied by the interpolated path,
  so the *reason* could have vanished from the wording with the test still green — proven by
  rewording the error and watching all 29 pass. Fixtures renamed, phrases asserted.
* **A fixture stops reaching its guard when a later fix gets there first, and nothing says so.**
  The ordering test for the containment check was retargeted twice — once when the static refusal
  was added, once when that learned to resolve the prefix — because each fix caught its input
  earlier, leaving the test green and its guard unexercised. Both times the mutation found it and
  the reading did not. **Re-run the whole mutation battery after every fix, not only a mutant for
  the fix itself**: a fix can silently disarm a test written for something else.
* The test written for the freshness branch — the branch a finding had just called untested —
  asserted only `report.ok`, which holds whether that branch runs or not. Proven by forcing
  `is_stale` to return `True`: the branch never ran and the test still passed. A skipped-fresh row
  carries no issue, so `link_scan` is the assertion that discriminates. Found by a reviewer, not by
  the round that wrote it, in the commit whose message called its other two fixes mutation-verified
  — **"mutation-verified" is a per-assertion claim, not a per-commit one.**

### A docstring claiming a safety property its function cannot have

**MEDIUM.** `_doc_id_of`'s `owner` argument was documented as preventing the `pnk://self/…`
retargeting defect. It cannot: only `.id` is returned, so `owner` never reaches an observable —
measured both ways, the mutation is caught by no test and the output against a partner sidecar
carrying the exact retargeting shape is byte-identical. The protection is real but lives in
`linkscan.scan_one`, which keeps the links it reads. A plausible rationale attached to the correct
line is harder to catch than a wrong line, because reviewing it means re-deriving the claim rather
than reading the code.

### Mutation testing: a killed run poisons everything after it

**HIGH, methodological.** The first mutation run blew a two-minute timeout and was killed
mid-mutation, so its `finally` never restored the source. The next run's pattern then failed to match
the already-mutated file, reported "pattern not found", skipped — and that guard stayed disabled for
all ten mutants that followed. The signature is unmistakable once known: **one unrelated test failing
on every mutant**, including mutations that cannot reach it.

Two things made it recoverable: the disabled guard had its own test, so the failure was loud, and
`./check.sh` had been green minutes earlier, which dated the contamination. The fix is a **baseline
snapshot taken before the first mutation and asserted after every restore** — not `git diff --quiet`,
useless in the increment's own worktree where the source is legitimately dirty. Scope the run to the
modules under test, too: the full-suite run is what blew the timeout that caused this.

Every fix was mutation-tested against the test written for it, and **three escaped**, each in a
different way that "green" could not distinguish. The NUL guard had a test whose input never
reached the line. The containment-ordering test stopped reaching its branch twice, when a later fix
caught its fixture earlier. And review 14's `next()` guard had no test at all: the `""` and `"."`
written for it raise at the `glob()` *call*, not at the step, so the guard one line down was never
executed — which review 14's own commit message called "eleven mutants, each killed by the right
test", and this paragraph called "all but one".

The method is now: mutate every behaviour in the function, not the ones the diff touched. **That
standard was stated before it was met.** The sweep that first claimed it covered three behaviours;
an independent 47-mutant pass over the whole of `sidecars_under` and `scan_one` killed 33 and left
14 alive — 2 provably equivalent, 12 unpinned. Every one of the 12 was checked and the code is
right in each, so they are coverage rather than defects, and they are listed rather than closed:
the two halves of the `exclude` disjunction (a deliberate mirror of `sync._excluded`), the
`continue` that bounds a pre-walk escape, `.resolve()` on `anchor` and on `base`, the `is_file()`
and sidecar-suffix skips, the two `sorted()` calls, `partner_sources` raising, and
`LinkTargetMissingError`'s count.

Naming them is the point. A number for the battery is unverifiable afterwards — the runs leave no
artefact — but *which* behaviours are unpinned is checkable by anyone who repeats the sweep, and
that is what a later reader needs.

One mutant is genuinely equivalent: substituting the locally declared `[[links.kb]] id` for the
partner's own when writing an alias target changes nothing, because the refusal above has already
established the two are equal. Saying so is part of the result — the rule is enforced by that
refusal, which *is* caught, and the docstring records it so nobody simplifies the variable away on
the grounds that they are the same.

### Green expires at the next keystroke

**HIGH.** `./check.sh` ran green, then a docstring was reworded to 101 characters, then the increment
was committed. Under `set -e` a failing `ruff check` means the eleven gates after it never ran either:
the increment's own verification stopped at gate two, unnoticed, because the earlier green run was
still in mind. The rule already says green-before-review; what this adds is that the run has to be the
*last* thing before the commit, including after an edit to a comment.

### A containment rule argued in prose and implemented for half its inputs

**HIGH.** `sidecars_under` reads a *partner's* `[sources]`, and its docstring says why that input is
untrusted: *"without the same check here, a partner manifest could point the walk at any directory
on this machine, and `roots = ["/"]` would be an unbounded walk on a `post-commit` hook."* The check
existed for `roots`. `include` is exactly as partner-controlled and had none, so
`include = ["../../outside/*.md"]` walked out of the partner KB and this one recorded inbound links
from files the partner does not own — `complete` true, so `sync` persisted them.

**The line that looks like the guard is not one.** `candidate.relative_to(root)` ran on every match,
and `relative_to` is *purely lexical*: `docs/../../outside/planted.md` is relative to the root as a
string, returning `docs/../../outside/planted.md` rather than raising. A `..` is only collapsed by
resolving, which is what the `roots` branch does one block above and this one did not. Two spellings
of the same rule, ten lines apart, one of them not implementing it.

**The fix then took four goes, and every wrong one came from spelling the rule differently from
the place that already had it right.** `link._document_in` resolves the *parent* and leaves the
final component: the directory chain is followed, so `..` collapses and an escape through a
symlinked ancestor is caught, while the document's own symlink is irrelevant. That is the rule.
Each attempt reinvented it:

1. **Per candidate, after globbing.** Correct about what to refuse, but it refuses the *results*:
   `glob` has already enumerated and stat'd the whole tree by the time the first match is
   inspected, so `include = ["../../../../**/*.md"]` still walked the machine on every
   `post-commit`. And an escape sets `complete` false, so no `last_scan` is written and the TTL
   cannot suppress the retry either — unbounded, forever.
2. **Refuse any pattern containing `..`, before globbing.** Bounded, and wrong in the other
   direction: `../notes/*.md` stays inside the KB and the partner's own `walk_sources` ingests it.
   This KB called a legitimate manifest an escape and then never refreshed that partner again.
   Refusing a partner's valid configuration is the same defect as accepting an invalid one.
3. **Resolve the prefix before the first glob component.** Defeated by a pattern that *starts* with
   one: `*/../../../outside/**/*.md` has an empty prefix, so the check passed unconditionally and
   the `..` ran inside `glob` — attempt 1's defect, reachable again. It also refused a *fixed*
   pattern naming a symlinked document, because with no glob component the "prefix" is the whole
   path and resolving it whole follows the final symlink: `include = ["alpha.md"]` refused while
   `include = ["*.md"]`, reaching the same file, was accepted.
4. **Join the whole pattern and apply `_document_in`'s spelling to it.** A glob component is just a
   name that does not exist, which `resolve()` collapses lexically, so one `resolve()` answers it
   with no enumeration. Ten patterns measured — a `..` staying inside, a directory genuinely named
   `a..b`, a literal bracket, two escapes, one behind a leading glob, a symlinked directory under a
   glob, a symlinked document by both spellings, and an absolute — all correct, escapes refused in
   0.12ms without touching a 3000-file tree. **None of the ten contained `**` followed by `..`.**
5. **Drop `**` from the probe.** `**` matches *zero* or more components while `Path.parts` counts
   it as one, so keeping it let a following `..` cancel it and the probe landed one level below
   where the walk goes. `**/../../**/*.md` probed inside the KB and walked the directory containing
   it, recursively — linear in the outside tree, and silent, because an escape is only noticed once
   a candidate is yielded and that pattern matched none. Dropping it is exact rather than merely
   conservative: each component `**` expands to is one a following `..` then pops, so the
   zero-expansion is the highest the walk can reach.

   Attempt 4's measurement was real and its ten patterns were all correct. It was the *sampling*
   that was wrong — ten hand-chosen inputs, none of which combined the two tokens whose interaction
   is the whole difficulty. A table of cases proves the cases in it, and reads like proof of the
   rule.

An absolute pattern is refused separately, because `glob` cannot walk one *wherever it points* —
including at this KB's own `docs/`. It had been folded into the escape message, which was simply
false for that case.

The lesson is not about paths. **Three of the four attempts were written by reasoning about the
problem afresh instead of copying the spelling from the function twenty lines away that had solved
it.** A rule implemented twice is a rule with two behaviours; the fix was to make the third
implementation textually identical to the first two and say so in all three.

Each attempt was found by mutating its predecessor, and **three of them disarmed an existing
test**: a fix that catches its input earlier leaves the older test green with its guard
unexercised. By the last round two guards written in *earlier* increments had gone dead this way —
L2's `roots` containment check, whose test was satisfied by the substring "outside the KB" that the
new per-candidate check also emits, and `scan_one`'s own `except` around the walk, whose only
input (`include = ["/etc/**/*.md"]`) the absolute branch now answers first. Both were found by
mutating behaviours *this increment never touched*.

So the rule is stronger than "re-run the battery after every fix": **the battery is over the whole
function, not the diff** — and a promise worth a guard is pinned directly (here, by making the walk
raise) rather than through an input that some later fix can intercept. Running it that way in the
next round found three more unpinned behaviours: the sidecar existence check, which predates L6
(`7570a69`), and the `*`/`**` boundary and the `next()` guard, **both written two rounds earlier by
this increment** (`425d106`). The sharper reading is the second one — the code least likely to be
pinned is not the oldest, it is what a recent fix added while attention was on the defect it
closed.

**The fix for "one bad entry is not the end of the partner" was itself incomplete, one line either
side of where it landed.** `probe.parent.resolve()` sat above it unguarded, so an embedded NUL in
any but a pattern's final component still raised out of the function; and `Path.match("")` sat
below it, so an empty `exclude` entry did the same — a case the new guard's own comment cited by
name as its reason for being scoped tightly, and then did not handle. Both produced the outcome the
commit had just declared impossible. **A guard placed by reasoning about one call is a guard for
one call**; the same mechanical sweep that closes an escaping-error class — list every call that
can raise, ask what each does with bad input — is what this needed, and it is the third time in
this increment that lesson has been relearned rather than applied.

One more from the same sweep: the containment predicate was fooled by a trailing `..`, because
`Path("/kb/..").is_relative_to("/kb")` is lexically *true*. The final component is left unresolved
so a symlinked *document* stays readable, and `..` is never a document.

**`sync.walk_sources` has the identical shape for the *local* manifest** and is not fixed here: it
is the user's own configuration rather than a partner's, and changing the engine's document walk is
not this increment's to do. Reported instead, and now scoped as its own increment and PATCH release
in `plans/20260731_2128-source-walk-containment.md` — which measured a third defect this pass had not: an
**absolute** local `include` is a raw `NotImplementedError` out of `cli.main`, the same escaping-
error class L6 spent four passes closing on the partner side.

### Smaller things

- **`pnk link A A` wrote a self-loop**, which says nothing and would return the document as its own
  neighbour. Refused now — and worded for both ways of arriving, because only the ULID is known here:
  the target really is this document, or it is a *different* file carrying the same id, which is a KB
  fault in its own right. "would link to itself" told someone who had named two different documents
  that one of them was itself, and pointed at neither the duplicate nor `pnk doctor`, which finds it.
- **`os.replace` onto a symlinked sidecar** destroyed the link and left a regular file, with the real
  file elsewhere still holding the old text. `create()` guards this explicitly; `write()` did not, and
  `pnk link` is the first command a person points at a file of their own choosing. It now writes
  *through* the link.
- **The error fallback named the local KB root** while the comment beside it claimed it named the
  declared path — reporting an unrelated readable directory for a failure that had nothing to do
  with it. Neither of the two tests written for that fix caught it: both asserted only the message
  prefix.
- **`why_not_a_kb` reproduced, one level down, the defect its own docstring exists to record.** The
  three-way split was added because an `is_dir()` split called an existing regular file "no such
  directory" — *"the one answer a person would check and find false"*. But the caller's probe is
  `is_file()`, so a `pinakes.toml` that exists and is a **directory**, or a symlink to nothing, fell
  through to "no pinakes.toml there" with the file plainly visible in `ls`. Found in review 9 by
  reading the docstring's justification against the code beneath it, which is a cheap check worth
  running on any function whose comment argues for its shape.
- **`pnk link` takes no lock**, so a concurrent write to the same sidecar can lose one side's change.
  Rename-atomicity prevents a torn file, not a lost update, and DESIGN §2.2 now says which.
- **STATUS's *surface you can use today* table had no `pnk links` row at all**, an hour and a
  quarter after it shipped in 0.5.0 (`20260731 11:27`; the row landed in `b96d247`, 12:44) — found while writing the increment by reading the neighbourhood rather than the
  diff.

## L7 — `pnk doctor`'s link checks (20260801 05:40)

### The check read a partner's index, and DESIGN §6.2 forbids exactly that

**HIGH.** The cross-KB check opened `<partner>/.pinakes/index.db` read-only to ask whether the
target document exists. §6.2 rules that out in the sentence that defines reverse links: they come
from the other KB's committed sidecars, *"**not** its index, which is gitignored and simply absent
in a fresh clone, and which could not be read without holding a second KB's lock"* — repeated
verbatim in `linkscan`'s module docstring, which is the module the check imports from.

`mode=ro` is not enough, and this is the part worth keeping. Measured: a read-only connection still
materialises `index.db-shm` and `index.db-wal` inside the partner's `.pinakes/`, and cannot
checkpoint them away on close. A *diagnostic* command wrote into a KB it was only asked to look at.
Two more consequences fell out of the same choice: a partner cloned but never synced answered
"missing" for every target, and a partner whose `.pinakes/` is mode 0500 degraded silently with an
internal `StoreError` message that misdiagnosed the cause.

The fix is the machinery L2 already had — `partner_sources` + `sidecars_under` + `read_sidecar` —
which is design-conformant, works on a fresh clone with no index at all, and is now tested that way.

**The rule was in the imported module's own docstring.** Not a subtle design point: a paragraph in
the file the new code imports three names from.

### The metric's numerator and denominator came from different populations

**HIGH.** Coverage is `COUNT(DISTINCT src_doc_id) / active`. `sync`'s `SoftDelete` sets
`state = 'deleted'` and drops the chunks — it never deletes that document's `origin = 'sidecar'`
rows. So a deleted document still counted toward the numerator while leaving the denominator,
and the headline number of this increment reported **`2 of 1 documents linked (200%)`**.

A ratio built from two queries is two populations until something makes them one. The join is one
line; noticing it needed one was the work.

### The declared `[[links.kb]] id` is not evidence of which KB is at that path

**MEDIUM.** The check keyed partner document sets on `linked.id` — the *local declaration*.
`linkscan.scan_one` refuses that substitution with `LinkedKbIdMismatchError`, and DESIGN §6.2 rule 1
states it as a rule, because trusting the manifest files another KB's links under this alias.
Measured both ways with a manifest declaring `X` over a partner whose real id is `Y`: a target that
existed in `Y` was reported unresolved, and one that did not was silently resolved.

Two directions need two tests, and only one of them is obvious. Filtering on the declared id also
*skips* a partner whose real id is the one wanted — a dangling target that goes unreported rather
than misreported — and that mutant survived until a test was written for it specifically.

### Four remedies could be blanked with the suite green

**MEDIUM.** The plan required "every new WARN carries a remedy" precisely because the meta-guard
(`test_every_problem_carries_a_remedy`) runs on a fixture where these checks are `OK` and carry no
problem. The helper written to stand in for it asserted `is not None` — which `""` satisfies, while
the guard it substitutes for asserts truthiness. Four of five remedies were emptiable.

**A stand-in for a guard has to assert what the guard asserts.** It now returns the string and each
caller asserts a phrase from it.

### A test named for a guard, authoring nothing that reaches it

**MEDIUM.** `test_an_unreadable_linked_kb_path_is_a_warning_not_a_traceback` was written for the
sentence *"a diagnostic command reporting a traceback is the one outcome `pnk doctor` may not
have"*, and named `why_not_a_kb`'s "third caller needing the same `try`". It authored no cross-KB
link -- so `wanted` was empty, `_unresolved_cross_kb` returned before touching the partner, and the
test pinned the guard in `_linked_kbs` and *neither* of the two in the function the review had just
added. Both are load-bearing: a partner directory behind a mode-0000 parent raises `PermissionError`
out of `partner_sources`, and a `roots` entry carrying an escaped NUL -- which `tomllib` accepts and
`Path.resolve` does not -- raises `ValueError` out of `sidecars_under`.

Third time in two increments that a fixture stopped one step short of its guard, and the shape is
always the same: **the test sets up the failure but not the demand for it.** An unreadable partner
is only reached by code that has a reason to read it.

The dangling-link side of the soft-delete interaction had the same gap in miniature -- the fixture
that proves the *numerator* excludes a deleted document already produced `1 dangling inside this
KB` in the detail it held, and asserted nothing about it. The fix was one line in a test that
already existed.

### Mutants that were not the logic they claimed

**Methodological.** Four "blank the remedy" mutants replaced `"A cross-KB target…"` with
`"" or "A cross-KB target…"`, which evaluates to the original string. All four reported SURVIVED,
which read as four coverage gaps and was really one broken harness. Rebuilt to replace the whole
`remedies.append(...)` call, all four die.

This is the second increment where a mutant that did not reproduce the real prior logic was briefly
taken for a result. The check is cheap: a mutant that survives should be *run* against the case it
claims to break before it is believed.

## G2 — The headroom measurement, and what it found (20260801 12:14)

G2 was built to answer one question: is the graph release's gate reachable at all? **It is not, on
this corpus.** The precondition needed at least 7 of the ~18 single-KB multi-hop questions to fail
today. **One fails.** G3 does not start, and the answer arrived before anything bumped
`schema_version` and forced every KB in existence to rebuild — which is the whole reason the
measurement was sequenced first.

**HIGH — the demo corpus has no tags, and one directory. The plan assumed otherwise.**
`tests/demo-kb` is thirty documents in a flat `docs/`, and not one sidecar carries a `tags` key.
With `mentions` cut (decision 6), that leaves exactly **one** structural edge kind that crosses a
document boundary: `co-located`, through a single thirty-way directory hub. `shared-tag` derives
zero edges. `sibling`, `parent`/`child` and `in-section` are all intra-document and cannot bridge
two evidence documents by construction. So the "derived structure" the graph release exists to
evaluate is, on the committed corpus, one hub — and G5's own text reasons about "the directory
layout and **tag vocabulary** of `tests/demo-kb`" as though a vocabulary existed. It does not.
Whatever G3 would derive here, a result carried by it is a claim about one directory.

**HIGH — a reachability probe on a thirty-document corpus is close to vacuous, and the reason is
not the probe.** `candidates_per_source` is 30 and the corpus has ~30 chunks, so the vector channel
already returns essentially every document with a positive cosine: the funnel *sees* the whole
corpus on every query and then cuts to `final_k = 5`. A failing question is therefore almost never
a recall failure the channel could fix by reaching further — it is a ranking failure. That is why
the probe reports `at-seed` separately from `liftable`: two of the three questions the fake backend
called liftable were already among the fused candidates and merely ranked below the cut, having
traversed no edge at all. A ceiling built from those would have read as headroom and been none.

**The numbers, real `[light]` models, `tests/demo-kb` at 20260801 12:14.** 18 multi-hop questions,
**1 failing** (`mh-withdrawn-collection-register`), liftable 1 without authored edges and 1 with,
`beyond-2-hops` 0, `membership-only` 0. Required: 7 failing **and** 7 liftable without authored
edges. It fails on the first clause by six.

**The questions were frozen before the probe ran, and were not re-authored afterwards.** Thirteen
new multi-hop chains, authored from pairs of documents that between them answer one question and
share no vocabulary on the thing that joins them, with the second hop phrased in the first
document's words. Seventeen of eighteen are answered correctly. Re-authoring them until seven fail
is fitting the question set to the gate — the circularity decision 14 removed by cutting cross-KB
questions, and undetectable once done. The honest reading is that a corpus of thirty short,
topically disjoint documents cannot produce a hard multi-hop set: picking 5 of 30 is not a
discriminating retrieval task, and the pipeline scores 0.94 on it.

**MEDIUM — the fake backend and the real models disagree about the shape of the answer, and only
one of them is the measurement.** Under the deliberately tie-heavy hashing fake the same set shows
9 failing and 3 liftable without authored edges (6 with) — the exact with/without gap the plan
predicted L1's hand-authored links would produce. Under the real models both collapse to 1. A
measurement taken on the fake would have reported a *different failure* of the precondition and
invited the wrong remedy.

**MEDIUM — `_score` read `Outcome` objects, so the artifact could not have been re-scored.** Every
metric is a function of five fields per question, but the scorer was written against the in-memory
type. Splitting `score_rows(rows)` out is what makes the committed artifact checkable offline, and
it is what `test_the_committed_41_score_exactly_their_pre_growth_values` runs on: no weights, no
network, and the 41 pre-growth questions reproduce their baseline **byte-identically** — measured
on macOS against a baseline written by CI's ubuntu runner, which is the same cross-machine
agreement G1's new CI job independently confirmed the same morning.

**LOW — the first `--fake` run silently asked for real weights.** `_fake_kb` asserted each manifest
substitution appeared exactly once; `provider = "fastembed"` appears twice (embedding and rerank),
so the assertion fired and the run aborted — correctly. Loosening it to "replace whatever is there"
would have left the rerank provider real and made an "offline" gate download a model. The expected
occurrence count is asserted per line, not assumed.

**Review pass — MEDIUM, the empty-set skip could swallow a typo.** `load_questions` read
`raw.get("questions") or []`, so a file whose key was misspelled produced an empty list — which the
new skip then reported as "a template deliberately ships none" and exited 0. Under the old
behaviour that file failed. An *absent* key is now an error and only an explicit `questions: []`
skips; the two cases are genuinely different and the skip is only safe because it can tell them
apart.

**Review pass — MEDIUM, `read_outcomes` promised more than it delivered.** Its docstring said it
"refuses a file whose rows are not rows — never a partial read", and a row missing `confidence`
raised a bare `KeyError` from the middle of the loop. Every one of the five fields reaches a metric
in `score_rows`, so a row missing one cannot be scored; they are now checked by name.

**Review pass — LOW, `fused_candidates` is a stage, not an entry point.** It does not run
`check_coherence`, because `search` does that before calling it. Anything reaching for the new
public function directly is querying an index that may have been built by a different embedding
model, which returns confident nonsense rather than an error (§4.4). Stated in the docstring rather
than duplicated in the function, since `search` would then run it twice on every query.

## Source-walk containment — one rule, three sites, enforced at one (20260801 13:28)

**The durable lesson: a containment rule argued in prose beside one of its two inputs is a rule for
one input.** `manifest._sources` states that a source root must stay inside the KB and enforces it
for `roots`. `include` sat two lines away, validated nowhere. The same lexical
`candidate.relative_to(root)` non-guard then appeared at three sites — `linkscan.sidecars_under`
(fixed in L6 review 10), `sync.walk_sources`, and the sidecar sweep beside it — and the one whose
docstring carried the argument was the one that did not implement it.

**All three defects were re-measured on 0.7.0 before anything was changed**, against a plan that had
measured them on 0.5.0 at `900aae7`. All three still reproduced, unchanged:

| | Before | After |
|---|---|---|
| `include = ["../../outside/*.md"]` | `2 indexed`, **a sidecar minted outside the KB**, document keyed `docs/../../outside/secret.md` | `ManifestError` at load, naming the pattern and the root |
| `include = ["/abs/path/*.md"]` | bare `NotImplementedError` traceback out of `cli.main` | `ManifestError`: *"is an absolute path"*, with its own remedy |
| `docs/escape -> /outside`, `include = ["*/*.md"]` | `1 indexed`, **a sidecar minted outside the KB** | `0 indexed`, the pattern reported, nothing written outside |

**HIGH — a fourth defect, found by a test that was meant to pin correct behaviour.** Layer 1
deliberately *accepts* a `..` pattern that lands inside the KB (`include = ["../notes/*.md"]` from
`docs/`), because what matters is where a path lands rather than whether `..` occurs in it. The test
asserting that then failed on the document's key: `relative_to` is lexical, so it returned
`docs/../notes/n.md`. Measured with `roots = ["docs/", "notes/"]` and
`include = ["../notes/*.md", "*.md"]`, one file on disk produced **one indexed document and two
failures** — *"appeared after the walk had already read this directory"* — because the sidecar found
under one key was invisible under the other, and the unmatched sweep reported an indexed document as
unmatched. Nothing in the plan predicted this; it exists only because the legal `..` case had never
been exercised.

The fix is **lexical** collapse (`posixpath.normpath`), not `resolve()`. Resolving would follow a
symlinked *directory* and re-key every document under it — `docs/alias/x.md` becoming
`docs/real/x.md` — which on an existing KB is a path change against a permanent identity. Lexical
collapse touches only paths containing `..`, and every one of those is already broken today.
Containment does not rely on it: the per-candidate check resolves.

**The predicate was copied from `linkscan.sidecars_under`, not re-derived, and that was the whole
point.** Reviews 11, 12, 13 and 14 each found a different defect in a different spelling of this one
rule: refusing any `..` (rejects a valid manifest); resolving only the prefix before the first glob
component (defeated by a leading `*`); resolving the whole path (refuses a symlinked *document*
while accepting the same file via `*.md`); and keeping `**` in the probe (it matches *zero*
components while `Path.parts` counts it as one, so a following `..` cancels it). Re-deriving would
have cost that sequence again for nothing.

**MEDIUM — the static layer is the bound, and the dynamic layer is the guard; neither covers the
other.** Checking candidates after globbing refuses the results while still paying for the
enumeration, which is what the `roots` rule exists to prevent —
`test_an_escaping_pattern_is_refused_without_enumerating_the_tree` counts entries pulled from the
generator, not `resolve()` calls, because the cost being avoided is the walk itself. And a symlinked
directory has no `..` and no absolute path, so it is invisible to any load-time check. The
per-candidate test `break`s rather than `continue`s, and runs **before** the `is_file()`/sidecar
skip: a pattern reaching outside that matched only directories or only sidecars hit one of those
`continue`s first, so the walk left the KB and reported nothing.

**LOW — the default `include` is safe by luck, not by design.** `["**/*.md", "**/*.txt"]` does not
escape through a symlinked directory, because `pathlib`'s recursive `**` skips them. Any user who
writes a non-recursive pattern loses that, which is exactly the shape of a guarantee nobody knows
they are relying on. Stated in `walk_sources`' docstring rather than left as folklore.

### Mutation round — three survivors, two of them defects (20260801 13:38)

Eleven guards broken on purpose. Eight were caught immediately. The three that survived were worth
more than the eight:

**HIGH — the per-root skip copied from `linkscan` was data loss here.** `sidecars_under` does
`if pattern in escaping: continue`, so a pattern known to escape contributes nothing under any later
root — correct there, where a dropped candidate costs one inbound link and a partner's `[sources]`
is one statement about one KB. Copied into `walk_sources` it means something else entirely: the
escapes *this* loop can see are **symlinks**, which are a property of one directory rather than of
the pattern, and a dropped candidate here is a **deleted index row and an orphaned sidecar**. So
`docs/escape -> /outside` silently stopped `*/*.md` collecting anything under an unrelated second
root. Removed, with a test. "Copy the predicate, do not re-derive it" was the right instruction and
this was still the wrong thing to copy — the predicate and the policy around it are different
decisions.

**MEDIUM — the containment check ran before `is_file()`, and no test could tell.** Every symlink
test matched a *file*, so moving the check after the skip changed nothing observable. The case the
ordering exists for is a pattern that matches only a **directory** (or only sidecars): it hits that
`continue` first, and the walk leaves the KB reporting nothing. `*/*` against a symlinked directory
containing a subdirectory is that case, and it now has a test.

**MEDIUM — the `break` bounded nothing, because `sorted()` had already drained the generator.** The
plan carried `break`, not `continue`, on a 360× measurement from `linkscan` review 12 — where the
loop is lazy. Written here as `for candidate in sorted(root.glob(pattern))` the enumeration a
symlinked escape triggers has *already happened* by the time the first candidate is inspected, so
the `break` saved only the loop body, and the `resolved` cache made even that one dict lookup. This
is the shape of a guard inherited with its justification and without the property the justification
rested on. The loop is now lazy; output order does not depend on it, because `walk_sources` sorts
what it returns and the per-root sort only decided which of two candidates sharing one key won —
and they describe the same file with the same hash. Measured: **301 entries enumerated before, 1
after**, and both the `break` and a reversion to `sorted()` are caught by that number.

### Two tooling corrections swept in the same PATCH (20260801 13:52)

**`tools/link_density_gate.py`** resolved one of its two bases and not the other, so any
non-canonical root — every `/tmp` path on macOS — exited with a traceback. One `root.resolve()` at
the top of `census`, and a test driving the tool through a symlinked parent.

**`tools/fragments.py`'s duplicate-heading defect was already closed**, and the open-corrections
entry saying "the tool is unchanged" is stale. Measured rather than assumed: three fragments
(two `fixed-*`, one `added-*` whose body begins `- **Fixed: …**`) spliced into a section that
already had a `### Fixed` produce exactly one `### Fixed`, one `### Added`, and the
category-prefixed entry filed by its **filename**, which is where the category belongs. Both halves
have regression tests already —
`test_fragments_merge_into_a_category_heading_that_already_exists` asserts `count("### Added") == 1`.
Closed by the 0.6.0 release-prep commit, not by this one.

**LOW, and the reason to write this down: `fragments.py --apply` is anchored to the repo it lives
in, not the working directory.** Testing it by `cd`-ing to a temp tree spliced *this* worktree's
`CHANGELOG.md` and deleted its `changelog.d/` fragment, reporting success. `--repo` exists exactly
for that and the tool's own test suite uses it. The damage was recoverable only because the
fragment had already been committed — which is the same rule the G1 mutation harness earned:
**commit before running anything that rewrites the tree.** A `git checkout --` to undo a mutation
in the same session then reverted an *uncommitted* fix in `tools/`, for the second time in this
project, and was caught only by re-reading `git diff --stat` afterwards.

## The reachable-ceiling probe, against a corpus it did not ship with (20260804 04:21)

**HIGH — a measurement tool that absorbs malformed input reports a number that looks valid.** The
finding class, stated once because it generalises past this tool: every defect below is an input
the probe accepted, turned into a plausible verdict, and reported with no mark on the output. That
is strictly worse than a crash. A crash costs an hour; a number that is quietly wrong is read into
`docs/STATUS.md`, decides whether a `schema_version` bump is licensed, and is not falsifiable after
the fact — nobody re-derives a measurement that already looks fine. **Anything that converts input
into a number owes its caller a refusal for input it cannot measure, and the refusal must be a
named failure, never a diagnostic line a reader has to notice.**

The two found by the rehearsal that ran the probe against an external KB — both measured on
demo-kb *under the offline fake backend*, where the corpus reads 18 multi-hop / 9 failing / 3
liftable (the real `[light]` reading of the same corpus is 18 / 1 / 1, so the real-model impact of
each is several times larger):

* **A hop `expect` naming a path not in the index** resolved through a lookup that answered `""`
  for an unknown path, so the hop was recorded `lands=False, reachable=False` — failing and
  unreachable, identical in the output to a genuine one. One typo took `failing` from 9 to 10
  while `liftable` stayed 3. On a 200-document corpus converted by hand from a frozen question
  set, this is not hypothetical.
* **A `multi-hop` question with no `hops`** incremented the denominator and produced no verdict,
  so it could never be counted `failing` and appeared in no other figure: 18 became 19, invisibly.
  The scaffolded template documented `id`, `question`, `expect` and `kind` and **never mentioned
  `hops`** — the trap was armed by our own template, which is why the fix edits both the tool and
  `src/pinakes/templates/notes/eval/questions.yaml`.

**MEDIUM — the first fix was narrower than its own commit message claimed, and an adversarial pass
found three more of the same class.** Worth recording because the pattern is the lesson, not the
individual bugs: a guard written against the two known instances validated *the thing the bug
report named* rather than *the property the measurement needs*.

* **A document with no chunks.** The guard asked whether the path was in `documents`. Every node
  the channel walks is built from the `chunks` table, so a document with zero chunks — a blank
  file, a note that is only front matter, a PDF whose free extraction yielded nothing — passes a
  path check and is still incapable of landing or being reached. It reproduced defect 1 digit for
  digit (`failing` 9 → 10, `liftable` 3), from a path spelled correctly. **"The name resolves" is
  not "the measurement can use it".**
* **A `multi-hop` question with exactly one hop**, which the guard's own wording called "multi-hop
  in name only" and let through. This one is worse than the defect it was written for, because it
  moves `liftable` **upward** (3 → 4). Under-counting fails safe against a floor; over-counting
  licenses the schema bump. A guard on a threshold must be written in the direction that can do
  harm, and the harmful direction here was the one nobody had an example of.
* **An empty hop `query`**, absorbed the same way, and **a golden set with no `multi-hop` question
  at all**, whose entirely-zero report is indistinguishable from a measured one.

**MEDIUM — the second review pass found the same hole again, in the key nobody had looked at.**
`question.filters` is applied to the last hop and was never validated. A `tags`, `path_prefix` or
`source_type` the index does not hold makes that hop unable to land whatever the corpus contains.
Measured on demo-kb under the fake backend, against its 9 failing / 3 liftable: one such filter
took `failing` to 10; the same filter across every multi-hop question took the run to **18 failing
/ 0 liftable**, exit 0, unremarked. (The review pass that found it quoted only the second figure
for a single question — checking it is what caught the difference, which is the M5 lesson applied
to the fix's own write-up.) It is the empty-`query` defect wearing a different key, it moves *both*
binding clauses, and `failing` moves upward. Two review passes each found one more instance of a
class the first fix was supposed to have closed, which is the actual lesson: **the guard has to be
written from the list of everything the measurement consumes, not from the list of bugs already
reported.** What `probe()` consumes is now the checklist — `hops`, each hop's `query` and `expect`,
the document behind that path, and `filters`. It is validated through `search`'s own `_filter_sql`
rather than a hand-written copy, so the check cannot drift from the semantics it is checking.

**MEDIUM — a third pass, and the same lesson a third time: the artifact recorded every setting
except the one that moves the number most.** `retrieval.rerank` records the *mode* (`local`), never
the reranker's provider and model — and `lands` is `expect in` the top `final_k` **after**
reranking. Demonstrated by the reviewer on one corpus, one path, one manifest, with only
`[rerank] model` changed: 9 failing / 3 liftable became 18 / 12, and every identifying field in the
two artifacts compared equal. Worse, the commit that added the block claimed it mirrored
`eval.py::_header` — which carries *three* blocks, `embedding`, `rerank` and `retrieval`, its
docstring saying it holds "every setting that can move a row". The copy took two of the three and
dropped precisely the one not derivable from the others. **When you cite a prior art as the
standard you met, diff against it.** `index_built_at` joined the payload at the same time: a corpus
edited since its last `pnk sync` is measured as it stood then, and nothing else would say so.

**LOW, and the most human of the findings: one defect, two accusations.** The filters check ran
before the hop-path check, and filters cannot admit a path the index does not hold — so a mistyped
`expect` under a healthy `filters:` block produced two problems, the first of them pointing at the
wrong line, and a `{len(problems)}` count that overstated. Ordering between checks is part of a
refusal's correctness, not a detail: the message that names the wrong cause costs the same debugging
hour the guard was written to save.

**LOW — a sentence assembled from parts is a sentence nobody read.** The per-kind wording was
spliced mid-clause into three messages, and on the branch no test covered — a non-`multi-hop`
question carrying hops, which `load_questions` allows — it rendered "so this probe never measures
this question — only `multi-hop` — so no figure moves for the query rather than for the corpus —
the same silent deflation as a mistyped path": two `so`s, and a closing clause asserting the
deflation the same sentence had just denied. The commit message claimed that wording was fixed; no
test exercised it. Each message now ends with a whole sentence, and a test covers the branch.

**MEDIUM — a test can pin a claim it cannot falsify.** `test_the_probe_names_the_kb_it_measured`
ran only `--fake`, and `--fake` measures a copy of the demo KB: every assertion in it was satisfied
by a probe that ignored `--kb` and hardcoded the demo path, which is the very defect the test
names. It now runs a real `--kb` against a KB deliberately not called `demo-kb` (a small runner
script registers the fake backend in the subprocess). **A test whose fixture is the default cannot
detect "always reports the default".**

The same mistake then repeated one layer down, and is worth recording because it is so easy to
miss twice: the replacement asserted that `kb_root` is *resolved*, using `tmp_path` — which is
already absolute and already resolved, so dropping the `.resolve()` left the entire suite green.
An assertion whose fixture already satisfies the property tests nothing. It now also runs with a
**relative** `--kb` from the corpus's own parent directory, which is the only shape that can fail.

**MEDIUM — naming the corpus is not naming the measurement.** The artifact recorded which KB was
measured and not what produced the numbers. `failing` is `hop.expect in` the top `final_k`
passages, downstream of `candidates_per_source`, `fusion`, `fusion_top_k`, `rerank` and
`vector_tier` — all per-KB manifest keys. Two artifacts from two configurations of the *same*
corpus were indistinguishable, the exact defect the KB-naming fix was written to close, one level
in. `eval.py`'s artifact header already recorded the same set for the same reason; this one now
does too.

**MEDIUM — quoting a number without its backend.** The first commit message and changelog fragment
said "measured on demo-kb: `failing` 9 → 10" without saying the numbers were the hashing fake's;
this repository's own retrospective already records that the fake and the real models disagree
about the shape of that answer, and the real reading is 18 / 1 / 1. A user-facing fragment reads as
the real measurement. **Every measured number carries the configuration that produced it, or it is
a different claim than the one intended.**

**MEDIUM — four passes, and the identity question kept moving outward one input at a time.** Pass
one: the artifact did not name the corpus. Pass three: it named the corpus but not the pipeline.
Pass four: it named corpus and pipeline but not the **golden set** — the input every printed figure
is computed *from*, and the one this branch's own refuse-edit-re-run loop changes most often.
Demonstrated on one corpus, one index, one manifest, rewriting only the hop queries into a generic
word: 9 failing / 3 liftable became 18 / 9, and every recorded field except `reports` compared
equal. The payload now carries the golden set's resolved path, a sha256 of its bytes and its
counts, plus `revision` on both model blocks — a revision selects weights as surely as a model name
does. One correction the sixth pass earned: that "needs no re-sync, so nothing else would move with
it" is true of `[rerank] revision`, which nothing compares against the index, and **false** of
`[embedding] revision`, which `search.check_coherence` guards — change it without a re-sync and the
run stops rather than drifting. Both are recorded; only one of them could ever have moved a figure
in silence. **The general form: an artifact
must identify every input its numbers are a function of, and the way to find them is to enumerate
the function's arguments, not to wait for a reviewer to name one.**

**LOW — the contradiction moved instead of leaving.** The per-kind wording was fixed once by
appending the conditional sentence to the end, which left "the hop is recorded
failing-and-unreachable. No figure this probe prints moves" — an assertion and its denial, one
sentence apart, in a message the previous commit claimed to have fixed. The consequence is now
*entirely* inside the conditional (`_consequence`), so a non-`multi-hop` question is told nothing
was recorded at all, and the test asserts the class ("no line may claim a hop was recorded")
instead of one superseded string.

**LOW — one more absorption, found by asking what `check_measurable` does not compare.** Every hop
was validated on its own and never against its siblings, so two byte-identical hops passed:
`MIN_HOPS` satisfied, one retrieval written twice, and `liftable` moved from 3 to 4 on demo-kb —
upward again. A YAML copy-paste is the realistic route.

**MEDIUM — five passes, and the fixture-satisfied assertion came back twice in one commit.** The
pass-four commit added the golden set to the artifact and asserted it only under `--fake` — where
the measured golden set *is* demo-kb's, so hardcoding the demo path and digest passed every
assertion and the full suite. That is the identical defect pass two found for `kb_root`, recorded
in this very fragment as "a test whose fixture is the default cannot detect 'always reports the
default'", reintroduced by the same author two commits later for the input he had just added. The
same commit pinned `revision` on both model blocks against `manifest.<section>.revision` — and
demo-kb declares neither, so both assertions were `None == None`. **Writing the lesson down does
not apply it: the check is mechanical — for every assertion, ask what value the fixture already
has, and whether a hardcoded constant would pass.** `_fake_kb` now writes distinctive revisions
into its copy, and the golden-set identity is pinned on the real-`--kb` run.

**LOW — one more absorption, one normalisation short.** The identical-hops check compared
`(query, expect)` byte-exactly, so upper-casing or padding the duplicated query defeated it while
the retrieval stayed identical — FTS5 folds case, every backend here splits on whitespace. Measured
on demo-kb: `liftable` 3 → 4, exit 0, the same upward move the check was written to stop. The
fingerprint is now case-folded and whitespace-collapsed. **A guard on "the same input" must
normalise the way the consumer normalises**, which is the `_filter_sql` lesson again in a smaller
key.

**The fix removes the place the defect could live, not just the symptom.** `_doc_id` is gone;
`check_measurable` validates the golden set against the active `documents` rows *and* the chunked
subset up front, and `probe` is handed the resulting map, so an unknown path has exactly one place
it can be handled and that place refuses. Validation runs *before* the backend loads — on a real
run that is a model download, and a run that is going to refuse should refuse in a second.

**Two smaller defects of the same family.** `--fake` silently discarded `--kb`, so
`--kb <corpus> --fake` measured demo-kb and reported its numbers as the corpus's; and neither
output format named the KB, so two runs against two corpora produced artifacts indistinguishable on
inspection — which is exactly what made the discarded `--kb` survivable. The pair belongs together:
a silent substitution is only dangerous because the output is anonymous, and **naming the input in
the artifact is the cheapest defence a measurement tool has.** The closing prose's hardcoded
`>= 7` was the same error in prose form, a claim about one corpus printed under the numbers of
another; the threshold now stays with the corpus's own measurement plan.

**On testing a refusal in a subprocess.** These tests run the probe against a KB whose manifest
names a backend the test subprocess never registered, so a run that got *past* the refusal fails
too — a bare non-zero exit proves nothing. Every refusal test asserts the named message and the
offending id/path, and `test_a_well_formed_golden_set_is_not_refused` is the control that keeps the
message attributable to the question rather than the environment. Two assertions were weak for the
same reason and were tightened: `"hops" in stderr` is contained in *every* refusal's closing
remedy, and `"--fake" in stderr` is satisfied by any argparse error, since the usage line names
both flags.

**One deliberate over-reach, recorded so it can be overruled.** A question-level `expect` naming a
missing document refuses the run although `probe()` never reads `expect` — it measures hops. It
cannot move any figure the probe prints, and refusing hard-stops a corpus whose frozen question set
may not be edited. Kept because a golden set naming a document the index does not hold is broken
for `make eval`, which does read it, and measuring a release precondition against an unchecked
question set is not worth the saved minute — but the refusal now says which of its lines move the
count and which do not, rather than claiming they all do.

## Design review passes 1–7 (pre-implementation)

Seven adversarial passes over [`DESIGN.md`](DESIGN.md) **before any code was written** — 58 findings
resolved (11 HIGH, 32 MEDIUM, 15 LOW). Moved here 20260728 16:40 from DESIGN.md §10, so that all
project history lives in one file and the design document is specification only.

The headline lesson, visible only across the whole sequence: **passes 2 and 4 fixed defects that
passes 1 and 3 had themselves introduced.** That is the argument for looping a review rather than
running it once — and the same argument the per-increment retrospectives above rest on.

**Pass 1** — 6 HIGH, 15 MEDIUM, 5 LOW resolved.
*HIGH:* `sqlite-vec` wrongly described as an ANN index (verified false upstream — §3.1 rewritten and
the tiering rationale corrected to bounded memory); reverse cross-KB links specified against the
other KB's gitignored index, impossible after clone (now scans committed sidecars, §6.2);
`pnk://` URIs used local aliases, breaking on share (now KB ULIDs, §2.2); rename/orphan/duplicate-ID
sync semantics unspecified (§6.4 added); per-operation budget cap claimed a guarantee it could not
deliver post-hoc (now pre-call reservation, §5); v0.1 omitted `pnk sync`, `pnk doctor` and hooks
though every other section depended on them (§8).
*MEDIUM:* MCP tools renamed `kb_*` → `pinakes_*` for namespace safety; multi-hop scope stated as
single-KB in v0.1; "no network" qualified against first-use model download and weights moved to the
shared HF cache; embedding storage described two ways, unified on a float32 BLOB; confidence signal
recast as calibrated with term-coverage demoted to a tiebreak; token limits validated against the
model's own tokenizer; template versioning decoupled from package version; install line corrected to
`uvx --from "pinakes[st]" pnk` with core-only behaviour defined; sync partial-failure semantics and
`failures` table added; WAL/read-only/lock concurrency policy added (§6.5); orphaned-sidecar deletion
made opt-in; paths fixed as KB-root-relative; index migration policy stated as rebuild-only; ledger
privacy and append atomicity specified; `pnk build` unified into `pnk sync --rebuild`.
*LOW:* budget window timezone; FTS5 external-content triggers; RRF k=60; latency claim replaced with
a measured 2.25 ms at 50k×384; golden-set size and coverage targets.

**Pass 2** — 1 HIGH, 7 MEDIUM, 5 LOW resolved. Several were introduced *by* pass 1's fixes, which is
the argument for looping rather than reviewing once.
*HIGH:* the `--rebuild` swap added in pass 1 renamed a WAL-mode database without checkpointing,
leaving a stale `-wal` beside a new `index.db` — a corrupt read. Now checkpoint-truncate, clean
close, then rename (§6.5).
*MEDIUM:* "operation" undefined for the per-op cap, letting an N-step `--deep` loop spend N× the
limit (§5); §4.2 referenced calibration thresholds the manifest had no field for (§2.1); the `links`
schema could not represent a reverse link, whose source doc lives in another KB (`src_kb_id` +
`origin` enum added); §3.1 presented three tiers as if all shipped, with v0.1 behaviour above 50k
chunks undefined; duplicate-content files made hash-based rename detection ambiguous with no
tie-break (§6.4); MCP server boundary and prompt-injection posture unstated (§4.7); FTS5 /
`enable_load_extension` treated as universally available — verified present on uv-managed CPython
3.13, now probed by `pnk doctor`.
*LOW:* a single `top_k` covered three different cut-offs (split into `candidates_per_source` /
`fusion_top_k` / `final_k`); `max_tokens` sat under `[embedding]` though §4.6 treats it as chunking;
`[[links.kb]]` present from v0.1 but unused until v0.3, now labelled; what publishing a KB repo
exposes; reverse-link origin provenance.

**Pass 3** — 1 HIGH, 3 MEDIUM, 4 LOW resolved.
*HIGH:* §6.3 said `--rebuild` "discards `.pinakes/`", which would delete `ledger.jsonl` — the spend
history §5's rolling budget is computed from. A routine maintenance command would have silently reset
the budget. Rebuild now replaces `index.db` only; `cache/` clearing is opt-in.
*MEDIUM:* the server's staleness check read `meta.build_id` through its own open connection, which
after a rename still points at the old inode and would report the old id forever — replaced with a
per-request `stat()` on the path (§6.5); `per_operation_eur` served as both the confirm threshold and
the hard ceiling, making the confirmation prompt unreachable (split into `confirm_above_eur` +
`per_operation_eur`, §2.1/§5); §6.4 framed pairing as ordered per-file rules, but rename and
duplicate detection require the whole before/after set — restated as an explicit two-phase algorithm.
*LOW:* v0.1's `pnk doctor` list omitted the environment probe §3.1 depends on, and `pnk serve` was
referenced in §4.5 but absent from the release list; "aliases … never stored" contradicted the
manifest that stores them (clarified: never inside a URI); the reservation formula reused the name
`max_tokens`, which `[chunking]` already claims; "not in v0.1 but present from day one" reworded.

**Pass 4** — 2 MEDIUM resolved, both self-inflicted by pass 3.
The rebuild bullet still ended "readers detect the new `build_id` and reopen" — directly contradicting
the `stat()`-based detection added three lines above it in the same pass (§6.5, now reconciled;
`build_id` is retained for provenance only). And `pnk://self/…` was left unexpanded, so a sidecar
copied into another KB would silently retarget its link at the *new* KB — `self` is now expanded to
the owning KB's ULID on write, like every other alias (§2.2). A grep sweep confirmed no stale
`kb_*` tool names, `pnk build`, or bare `top_k` references survive outside the log.

**Pass 5** — 0 findings. Verified by re-reading §§1–10 in full and grepping for every identifier
renamed across passes 1–4. No section contradicts another; every external claim (`sqlite-vec` is
exhaustive not ANN, FTS5 + extension loading on uv-managed CPython 3.13, `pinakes` free on PyPI,
2.25 ms at 50k×384) was measured or fetched in-session rather than recalled; every locked constraint
is honoured; every capability in §1 maps to a release in §8. Review complete.

**Pass 6** (20260725 09:28, implementation-readiness review) — 2 HIGH, 2 MEDIUM, 1 LOW resolved; the two
product calls were decided by the user, not the review.
*HIGH:* the reranker was simultaneously a v0.1 default (`rerank = "local"` in §2.1, "on by default"
in §4.1, its scores the substrate of §4.2's confidence signal, "rerank precision" in §7's v0.1 CI)
and a v0.5 deliverable in §8 — a freshly-inited KB would have defaulted to a stage that didn't
exist, and v0.1 would have shipped with no defined confidence signal. Resolved: the reranker ships
in v0.1; default `BAAI/bge-reranker-base` (user decision — same id on both backends beats the
smaller ms-marco model's provider-specific ids), a `[rerank]` manifest block mirroring
`[embedding]`, `fitted_for` added to `[retrieval.confidence]`, and a CI `HF_HOME` cache so ~1.4GB
of weights download per cache key, not per job (§2.1, §4.5, §8). And §8's v0.1 had no CLI query
surface at all — `pnk search` existed in §4.2's escalation story, the CLI stub and the README, but
not in the release that claims "end to end". Added explicitly (§8).
*MEDIUM:* the `post-commit` hook wrote sidecars, dirtying the tree it had just committed — every
document commit would trail an untracked `.pnk.yaml` forever. Resolved with a three-hook split:
`pre-commit` mints and stages sidecars for staged documents only, `post-commit`/`post-merge` touch
the index only (§6.3). And a stale `sync.lock` from a killed sync silently disabled hook-driven
freshness forever ("a second sync exits immediately" had no liveness story). Resolved: the lock
records pid/host/start-time; dead-pid locks are reclaimed with a warning, cross-host locks refuse
with `--force-unlock` as the human path, `pnk doctor` reports held locks (§6.5).
*LOW:* the sidecar's `content_hash` duplicated `documents.content_hash`, was read by nothing, and
guaranteed a two-file diff on every document edit while going stale whenever sync hadn't run —
dropped from the sidecar (user decision); change detection is index-only, stated in §2.2.

**Pass 7** (20260725 09:52, surfaced while adversarially reviewing `plans/20260725_1317-v0.1.md` — the implementation
plan's review loop reads the design fresh each pass, which is how these escaped passes 1–6).
*HIGH:* §4.5 claimed model weights go to the shared HF cache on both backends — false for fastembed,
which defaults to `$TMPDIR/fastembed_cache` (verified upstream): CI's `HF_HOME` cache would never
hit and `pnk doctor`'s weights check would probe the wrong directory. The fastembed backend now
passes an explicit cache dir under `HF_HOME`, making the claim true by construction.
*MEDIUM:* a sidecar-only edit (tags/title/links changed, document untouched) fell through §6.4's
"path and hash unchanged → Skip" and was never re-indexed — `documents.sidecar_hash` added (§3) and
the sidecar-only change class stated (§6.4); soft delete left chunks and embeddings searchable —
removal on soft delete stated, identity row retained (§6.4); rename+edit in one sync had both the
adoption and deletion rows firing for the same ID with no stated winner — sidecar adoption now wins,
no soft delete emitted, and the sidecar-didn't-travel case is reported at sync time (§6.4).
