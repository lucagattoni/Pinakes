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
