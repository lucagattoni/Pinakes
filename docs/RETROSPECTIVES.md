# Retrospectives

One section per increment of the project's build plans (`plans/`), written during that increment's
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
