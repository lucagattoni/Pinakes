## L6 — `pnk link` (20260731 13:45)

Three adversarial rounds, and each one found defects in the round before it. What follows is the
state after all three, not a log of them: the rule is to rewrite to the current state rather than
layer corrections, and an earlier draft of this fragment broke it twice — it still described a
concurrency scenario that round 2 had disproved, and still called every self-link a typo after
round 2's own fix existed because it is not.

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

### A fixture that was representative rather than discriminating

**MEDIUM.** `test_no_line_outside_the_links_block_changes_when_a_link_is_added` used a sidecar with a
*populated* `tags:` list, which `write()` short-circuits as unchanged and therefore never touches. It
could not have failed. Meanwhile `tags:` and `provenance:` written with nothing under them were being
rewritten to `tags: []` and `provenance: {}` on every `pnk link` — two lines changed outside the
block, in the increment whose test says none are, against a promise stated as byte-identity.

Reachable before L6 only from a paid PDF extraction, which is why L5b's sweep missed it; `pnk link`
reaches it on a *first* link, the common case. The sibling
`test_a_known_key_with_a_null_value_does_not_crash_the_writer` parametrises exactly these three keys
and asserts only `"id:" in text`: it pins the absence of a crash and nothing about the value.

### A docstring claiming a safety property its function cannot have

**MEDIUM.** `_doc_id_of`'s `owner` argument was documented as preventing the `pnk://self/…`
retargeting defect. It cannot: only `.id` is returned, so `owner` never reaches an observable —
measured both ways, the mutation is caught by no test and the output against a partner sidecar
carrying the exact retargeting shape is byte-identical. The protection is real but lives in
`linkscan.scan_one`, which keeps the links it reads. A plausible rationale attached to the correct
line is harder to catch than a wrong line, because reviewing it means re-deriving the claim rather
than reading the code.

### `expanduser()`, and the errno class it named but did not close

**MEDIUM.** `Path("~nosuchuser/x.md").expanduser()` raises `RuntimeError`, which is not a
`PinakesError`, so it left `cli.main` as a traceback — on the only command that called it. It bought
nothing either: a `~` that does expand lands in `$HOME` and is refused by the containment check on
the next line. Copying a call across a boundary copies its justification too, and `linkscan`'s need
for it (a `[[links.kb]] path` may be `~/kbs/partner`) did not survive the trip.

Its docstring then named the escaping-non-`PinakesError` class as the reason — and two more instances
of that same class were left in the same function: `Path.is_file()` ignores `ENOENT`/`ENOTDIR`/
`EBADF`/`ELOOP` and nothing else, so an unreadable parent directory (`EACCES`) and an over-long name
(`ENAMETOOLONG`) both raised through `cli.main`. Naming a defect class is not fixing it; the fix is
to go looking for the rest of the class.

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

Thirty-four mutants across three rounds, all but one caught by the intended test. That one is
genuinely equivalent — substituting the locally declared `[[links.kb]] id` for the partner's own when
writing an alias target changes nothing, because the refusal above has established the two are equal.
Saying so is part of the result: the rule is enforced by that refusal, which *is* caught, and the
docstring records it so nobody simplifies the variable away on the grounds that they are the same.

### Green expires at the next keystroke

**HIGH.** `./check.sh` ran green, then a docstring was reworded to 101 characters, then the increment
was committed. Under `set -e` a failing `ruff check` means the eleven gates after it never ran either:
the increment's own verification stopped at gate two, unnoticed, because the earlier green run was
still in mind. The rule already says green-before-review; what this adds is that the run has to be the
*last* thing before the commit, including after an edit to a comment.

### Assertions satisfied by the path rather than by the message

**LOW, twice.** `assert "outside" in message` against a fixture named `outside.md`, and
`assert "partner" in message` against a `tmp_path` ending in `/partner`. Both were satisfied by the
interpolated path, so the *reason* could have vanished from the wording with the test still green —
proven by rewording the error and watching all 29 pass. Fixture renamed, phrases asserted.

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
- **`pnk link` takes no lock**, so a concurrent write to the same sidecar can lose one side's change.
  Rename-atomicity prevents a torn file, not a lost update, and DESIGN §2.2 now says which.
- **STATUS's *surface you can use today* table had no `pnk links` row at all**, three weeks after it
  shipped in 0.5.0 — found while writing the increment by reading the neighbourhood rather than the
  diff.
