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
`plans/v0.1.md` lists it among `pair()`'s return values. Raising is better: the condition is fatal
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

**Design note — the template ships `[retrieval.confidence]` commented out.** `plans/v0.1.md` had
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

**A promise in a section with no increment number belongs to nobody.** `plans/v0.1.md` asked for a
CI grep gate keeping paid-API clients out of `src/` under "Verification of the whole". No increment
owned it, so it never shipped — while the invariant it guards is the one `CLAUDE.md` calls
non-negotiable. Now enforced, and verified in both directions: it passes on the current source and
catches a planted `import openai`. *Lesson: every promised check carries an increment number and a
path, or it is a wish.*

## Planning v0.2 (20260727 17:00)

**A review pass is a change, and a change needs its own review.** Adversarial pass 2 over
`plans/v0.2.md` returned 5 HIGH — and **four of the five were created by pass 1's own fixes**, not
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

**HIGH — the table that verifies everything verified nothing.** `plans/v0.2.md` ends with 98 rows,
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

**Pass 7** (20260725 09:52, surfaced while adversarially reviewing `plans/v0.1.md` — the implementation
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
