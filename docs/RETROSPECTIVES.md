# Retrospectives

One section per increment of [`plans/v0.1.md`](../plans/v0.1.md), written during that increment's
retrospective review (the workflow is in [`CLAUDE.md`](../CLAUDE.md)). Only findings worth keeping
land here: a real defect the review caught, or a fact that would be expensive to rediscover. Fixes
themselves live in the commits; this file records *what was learned*.

Every heading and claim here carries `YYYYMMDD HH:MM` (local, 24h) — several increments can
land in one day, and a bare date loses their order.

Severity follows the design review's scale: **HIGH** — wrong behaviour or false confidence;
**MEDIUM** — would block or mislead; **LOW** — worth remembering, not urgent.

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
