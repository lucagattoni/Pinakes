## L6 — `pnk link` (20260731 21:28)

**Every review commit on this increment found defects in the one before it, and five of them found
the previous commit's own fix or claim** rather than something it had missed: `3ce150e` (the
containment fix had traded one defect for two), `9c8f667` (the totality fix re-anchored the walk on
the working directory), `cdee8d8` (the test for an untested branch did not enter it), `dbebd8b` (a
severity asserted, not measured) and this one (the escape refusal did not bound the walk).

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
and there are five `Path.resolve()` sites across the two modules rather than two.

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
accepts in a manifest and `pathlib` will not open. Enumerated rather than excused, there are five
sites: `_document_in` (`link.py:298`) resolves a path built from user text and is now guarded and
tested; `resolve_path` (`linkscan.py:178`) is the fix above; and `sidecars_under` has three —
`anchor`, the `roots` entry, and the per-candidate containment check review 10 added — all inside
the caller's `except (OSError, ValueError, NotImplementedError, PinakesError)`.

The enumeration is the point: *"safe at both call sites"* named neither the number nor the reason,
so it could not be checked without redoing the work — whereas a count with line numbers is wrong
the moment it drifts, and says so. It has drifted twice already: round 8 corrected an earlier
version that called two of the `sidecars_under` sites partner-controlled when one is not, and round
10's own fix added the fifth site, making "four" stale in the same commit that relied on it.

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

Every fix in every round was mutation-tested against the test written for it, and all but one mutant
was caught. (An earlier draft gave a total here; it was stale within a round and unverifiable
afterwards, since the runs leave no artefact. The method is the durable part.) The one escape was
the NUL guard above — a test existed, and the mutation is what proved it never reached the line.

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

The fix resolves the parent and leaves the final component — `link._document_in`'s spelling, for
`_document_in`'s reason — so a symlinked *document* inside the partner KB is still read while a
symlinked *directory* cannot carry the walk out. Both directions are tested, because tightening this
into "resolve the whole path" would silently drop legitimate documents, and a dropped document is a
deleted inbound row.

**`sync.walk_sources` has the identical shape for the *local* manifest** and is not fixed here: it
is the user's own configuration rather than a partner's, and changing the engine's document walk is
not this increment's to do. Reported instead — it wants its own increment, since `pnk sync` mints
sidecars for what it ingests, so a stray `../` in a local `include` writes files outside the KB.

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
