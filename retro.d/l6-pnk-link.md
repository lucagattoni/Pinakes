## L6 — `pnk link` (20260731 13:07)

### The gate was red on the commit, because the last edit came after the last run

**HIGH.** `./check.sh` was green, then a docstring was reworded, then the increment was committed —
and that docstring line was 101 characters. `check.sh` runs under `set -e`, so `ruff check` failing
means the *eleven gates after it never ran either*: the increment's own verification stopped at
gate two and nobody noticed, because the earlier green run was still in mind. The rule already says
green-before-review; what this adds is that "green" expires at the next keystroke, including a
keystroke in a comment. The adversarial pass found it with `git diff --stat HEAD` (empty — the file
on disk *is* the commit) followed by one `ruff check`.

### Two documentation claims that the code contradicts, in a doc written from the design

**HIGH.** The new `pnk link` section told the user that a `pnk://` URI pointing at a KB not on this
machine is fine because *"`pnk doctor` reports a dangling target; `pnk links` lists it under
`unresolved`"*. Neither happens. `doctor.py` filters its dangling list to `kb_id == manifest.kb.id`
— intra-KB only, and the cross-KB check is **L7, the next increment**. `provider.py`'s `unresolved`
carries a docstring explicitly refusing to do it: *"a cross-KB target cannot be checked from here
without the other KB, and reporting one as unresolved on that basis would be asserting something
this index has no standing to know."*

So a reassurance was invented for the one case the section was telling the reader not to worry
about, and half of it described a thing the design had already declined to build. Both halves read
as obviously true while writing, because they are what the system *ought* to do. Running them takes
twenty seconds and is the only thing that separates the two.

### A symlinked document was in the KB for every command except this one

**HIGH.** `Path.resolve()` follows the final symlink *before* the containment check, so a document
that `pnk sync` indexes, `pnk doctor` calls a readable sidecar and `pnk links` traverses was refused
by `pnk link` as *"outside this KB"* — with a remedy repeating the path the user had just typed
correctly. Nothing could link it, in either direction, ever.

The fix is to normalise **lexically** (`os.path.normpath`) rather than through the filesystem: what
decides membership of a KB is the path under its `[sources]`, which is what every other command
uses; where the inode lives is not this command's business. `..` is still collapsed, so the escape
the check exists for is still refused — pinned by its own test, because a lexical check is exactly
the kind that quietly stops refusing anything.

### `expanduser()` on an argument documented as KB-root-relative

**MEDIUM.** `Path("~nosuchuser/x.md").expanduser()` raises `RuntimeError`, which is not a
`PinakesError`, so it went straight out through `cli.main` as a traceback — the only command on the
surface that does. And it bought nothing: a `~` that *does* expand lands in `$HOME` and is refused
by the containment check on the very next line. A pure crash surface, added by reflex because the
neighbouring `linkscan.resolve_path` legitimately needs it (a `[[links.kb]] path` may be
`~/kbs/partner`). Copying a call across a boundary copies its justification too, and that one did
not survive the trip.

### A fixture that was representative rather than discriminating — again

**MEDIUM.** `test_no_line_outside_the_links_block_changes_when_a_link_is_added` used a sidecar with
a *populated* `tags:` list, which `write()` short-circuits as unchanged and therefore never touches.
It could not have failed. Meanwhile `tags:` and `provenance:` written with nothing under them were
being rewritten to `tags: []` and `provenance: {}` on every `pnk link` — two lines changed outside
the block, in the increment whose test says none are, against a promise stated as byte-identity.

Reachable before L6 only from a paid PDF extraction, which is why L5b's own sweep missed it;
`pnk link` reaches it on a *first* link, which is the common case. Fixed in `write()` (an empty
known key whose node is `null` is left alone — both read back identically, so rewriting changes
bytes for no meaning), and pinned by a fixture built for this shape rather than borrowed from the
test next door. The sibling `test_a_known_key_with_a_null_value_does_not_crash_the_writer`
parametrises exactly these three keys and asserts only `"id:" in text`: it pins the absence of a
crash and nothing about the value.

### A docstring claiming a safety property the function cannot have

**MEDIUM.** `_doc_id_of`'s `owner` argument was documented as preventing the `pnk://self/…`
retargeting defect. It cannot: the function returns `.id` and discards everything else, so `owner`
never reaches an observable. Measured both ways — the mutation is caught by no test, and the output
against a partner sidecar carrying the exact retargeting shape is byte-identical. The protection is
real but lives in `linkscan.scan_one`, which actually keeps the links it reads. A plausible
rationale attached to the correct line is harder to catch than a wrong line, because reviewing it
means re-deriving the claim rather than reading the code.

### Mutation testing, and how a killed run poisons everything after it

**HIGH, methodological.** The first mutation run blew a two-minute timeout and was killed
mid-mutation, so its `finally` never restored the source. The next run's pattern then failed to
match the already-mutated file, reported "pattern not found", skipped — and that guard stayed
disabled for all ten mutants that followed. The signature is unmistakable once known: **one
unrelated test failing on every mutant**, including mutations that cannot reach it.

Two things made it recoverable. The disabled guard had its own test, so the failure was loud; and
`./check.sh` had been green minutes earlier, which dated the contamination precisely. The fix is a
**baseline snapshot taken before the first mutation and asserted after every restore** — not
`git diff --quiet`, which is useless in the increment's own worktree where the source is
legitimately dirty. Scope the run to the modules under test, too: the full-suite run is what blew
the timeout that caused this.

Twenty mutants in the end, all but one caught by the intended test. The exception is genuinely
equivalent: substituting the locally declared `[[links.kb]] id` for the partner's own when writing
an alias target changes nothing, because the refusal above has already established the two are
equal. Saying so is part of the result — the rule is enforced by that refusal, which *is* caught,
and the docstring now records it so nobody simplifies the variable away on the grounds that they
are the same.

### Assertions satisfied by the path rather than by the message

**LOW, twice.** `assert "outside" in message` against a fixture named `outside.md`, and
`assert "partner" in message` against a `tmp_path` ending in `/partner`. Both were satisfied by the
interpolated path, so the *reason* could have vanished from the wording with the test still green —
proven by rewording the error and watching all 29 pass. Renamed the fixture and asserted the phrase.

### Smaller things

- `pnk link A A` wrote a self-loop, which says nothing and would return the document as its own
  neighbour. Refused now; every way of reaching it is a typo.
- `os.replace` onto a **symlinked sidecar** destroyed the link and left a regular file, with the
  real file elsewhere still holding the old text. `create()` guards this explicitly; `write()` did
  not, and `pnk link` is the first command a person points at a file of their own choosing. It now
  writes *through* the link.
- `pnk link` takes no lock, so a concurrent sync can lose one side's change. Rename-atomicity was
  offered as the reassurance in DESIGN §2.2 — it prevents a torn file, not a lost update, and the
  text now says which. A lock held around a `docs/` write while a paid extraction runs would block
  the interactive command for as long as the money takes; the exposure is a person typing against a
  hook firing in the same second.
- STATUS's *surface you can use today* table had no `pnk links` row at all, three weeks after it
  shipped in 0.5.0. Found by reading the neighbourhood rather than the diff.
