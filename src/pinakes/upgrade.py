"""`pnk upgrade` — what the template changed since your KB was stamped, and whether it still fits.

**Three inputs, and which three is the whole design (docs/DESIGN.md §6.1, F4 in the template
release's plan).**

| Name | What it is |
|---|---|
| `base` | the **recorded** version's archived `pinakes.toml.j2`, rendered |
| `ours` | the **installed** version's, rendered through the *same* context |
| `theirs` | the KB's own `pinakes.toml`, as it is on disk |

The diff printed is `base → ours` — **template against template**, so nothing the user wrote is in
either side of it. `theirs` is never diffed against anything; it is only asked whether each hunk
still *fits*. A report built from the user's manifest could not tell a template change from their
own tuning, and presenting the second as the first is the defect this command exists not to commit.

**`plan` and everything it calls write nothing.** Not to the manifest, not under `.pinakes/`.
`apply` is the one function here that writes, it is reached only from `pnk upgrade --apply`, and it
is the **only** place in Pinakes that rewrites a KB's `pinakes.toml` after `pnk init`
(docs/DESIGN.md §2.1). Its rule, from which everything else follows: **it decides everything before
it writes anything.** Classification, the conflict check, the newline check, the `[kb] template`
rewrite and every refusal run over in-memory text; the first byte reaches the filesystem only once
the command has committed to writing. So a refusal provably leaves no `pinakes.toml.orig` behind —
a testable consequence, not an implementation detail, because a `.orig` left by a refused run makes
the *next* run refuse on the `.orig` rule instead of on its real reason.
"""

import difflib
import itertools
import os
import re
import stat
import tempfile
import textwrap
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from pinakes import template
from pinakes.errors import ManifestError, PinakesError, UpgradeError
from pinakes.lock import LOCK_NAME, read_holder
from pinakes.manifest import MANIFEST_NAME, Manifest

CONTEXT_LINES = 3
"""Unchanged lines each hunk carries — `diff -U3`, and the reason uniqueness is checkable at all.

A hunk with no context is a bare instruction to insert text at a line number, and a line number
means nothing in a file the user has been editing. Three lines is what makes "does this hunk occur
in `theirs`, exactly once" a question worth asking.
"""

WRAP = 92
"""Where a remedy paragraph wraps. Never the diff — a wrapped diff line is a wrong diff line."""

# A TOML table header and nothing else. `\s*\[` alone also matched a multi-line array's
# continuation line, so a hunk inside `include = [` reported its section as `["p", "q"],`.
# **Both bracket forms, and a trailing comment.** `[[links.kb]]` is a table a real KB has and
# `[budget]  # caps` is legal TOML; a pattern tight enough to reject an array element but not
# these two labels the hunk with the *preceding* table instead — silently wrong, which is worse
# than the array element it was tightened to reject.
#
# **No comma inside the brackets**, which is what separates a table header from the last element
# of a wrapped array: `["r", "s"]` closing an array carries no trailing comma, so the shape
# alone cannot tell it from `[a.b]`. A dotted key may legally contain a comma inside quotes
# (`[a."b,c"]`) and would be missed; that is a label on a table nobody has written, against a
# mislabel on an array anyone may wrap.
_TABLE = re.compile(r"\s*\[\[?[^]\[,]+\]\]?\s*(#.*)?\Z")
_CODE_SPAN = re.compile(r"`[^`]+`")
_GLUE = "\ue000"
"""A private-use codepoint standing in for a space inside a `code span` while the text is wrapped.

Not a decoration: the first wrapped remedy printed ``run `pnk`` at the end of one line and
``init` on a throwaway directory`` at the start of the next, which is a command a reader cannot
copy. `textwrap` breaks on whitespace, so the only way to keep a span whole is for it to contain
none while the wrapping happens.

Written as the escape `\\ue000` rather than pasted: an invisible character in source is exactly
what a reviewer cannot see, and this file's whole job is being read.
"""


def fill(text: str) -> str:
    """Wrap a paragraph for a terminal without splitting a `code span` across two lines.

    Public because it is the unit its own tests have to reach: whether a span straddles the
    wrap column depends on every word before it, so a test driving a real report is green
    under a broken wrapper whenever the current wording happens to be kind.
    """
    glued = _CODE_SPAN.sub(lambda span: span.group(0).replace(" ", _GLUE), text)
    # `break_long_words=False`: a span longer than the width overflows its line rather than being
    # cut in half, which is the lesser of two wrongs for something meant to be copied.
    return textwrap.fill(glued, width=WRAP, break_long_words=False).replace(_GLUE, " ")


class Placement(Enum):
    """Where a hunk stands against the user's manifest. Three outcomes, and the third is not an
    error — `pnk upgrade` reports, so a conflict is information rather than a failure."""

    CLEAN = "clean"
    ALREADY_APPLIED = "already-applied"
    CONFLICT = "conflict"

    @property
    def label(self) -> str:
        return _PLACEMENT_LABELS[self]


_PLACEMENT_LABELS = {
    Placement.CLEAN: "applies cleanly",
    Placement.ALREADY_APPLIED: "already applied",
    Placement.CONFLICT: "conflicts",
}

_PLACEMENT_COUNTED = {
    Placement.CLEAN: "clean",
    Placement.ALREADY_APPLIED: "already applied",
    Placement.CONFLICT: "conflicting",
}
"""The same three outcomes as nouns, for a line that puts a number in front of them."""


class Outcome(Enum):
    """What the command could say about this KB. `NO_BASELINE` is the one that is not a comparison.

    It is also the only one every KB in existence reaches today: `notes@1.0` is deliberately not
    archived, because it denotes eleven different template contents and a diff computed from the
    wrong base is worse than no diff (D-2b).
    """

    UP_TO_DATE = "up-to-date"
    SAME_MANIFEST = "same-manifest"
    DRIFTED = "drifted"
    NO_BASELINE = "no-baseline"


@dataclass(frozen=True, slots=True)
class Hunk:
    """One region the template changed, and whether it still fits `theirs`.

    `lines` are unified-diff lines — each prefixed with a space, `-` or `+` — so the printed diff
    and the placement decision are read from one structure rather than derived twice.
    """

    header: str
    section: str | None
    lines: tuple[str, ...]
    placement: Placement

    @property
    def removed(self) -> tuple[str, ...]:
        return image(self.lines, "-")

    @property
    def added(self) -> tuple[str, ...]:
        return image(self.lines, "+")

    @property
    def where(self) -> str:
        """`[sources] @@ -8,7 +8,11 @@` — the region, named on **one line**.

        One string rather than a caller's f-string because a refusal message and the placement
        listing must name a conflict identically, and because the exit criterion greps for the
        table and the word *conflict* on the same line: two greps that each pass on a different
        line establish nothing.
        """
        return f"{self.section} {self.header}" if self.section else self.header


@dataclass(frozen=True, slots=True)
class Change:
    """One key whose value a hunk moves, with both sides as the file spells them.

    `before is None` means the hunk introduces the key; `after is None` means it removes one.
    Neither happens in any template drift that has ever shipped (F2), and both are represented
    anyway — the recommendation `--apply` prints is *about* introduced keys, so a shape that could
    not express one would make that feature untestable.
    """

    section: str | None
    key: str
    before: str | None
    after: str | None

    @property
    def path(self) -> str:
        return f"{self.section}.{self.key}" if self.section else self.key

    def describe(self) -> str:
        return f"{self.key}: {self.before or 'not set'} → {self.after or 'removed'}"


def _literal(line: str) -> str:
    """The value a `key = value` line assigns, as written, with any trailing comment dropped.

    Read out of the source text rather than round-tripped through `tomllib`, because the numbers
    this feeds are **spending caps a user is being asked to consent to**: `tomllib` parses
    `monthly_eur = 5.00` to the float `5.0`, and a consent line that silently reprints a cap in a
    spelling the file does not use is asking about a different number than the one on screen.

    The scan is quote-aware for the same reason it is not a `split("#")`: `on_exceed = "abort # no"`
    is legal TOML, and cutting at the first `#` would report a truncated value.
    """
    after = line.split("=", 1)[1]
    out: list[str] = []
    quote: str | None = None
    for character in after:
        if quote is not None:
            out.append(character)
            if character == quote:
                quote = None
        elif character in "\"'":
            quote = character
            out.append(character)
        elif character == "#":
            break
        else:
            out.append(character)
    return "".join(out).strip()


def _key_value(line: str) -> tuple[str, str] | None:
    """`(key, literal)` if *line* is a single `key = value` assignment, else `None`.

    `tomllib` decides whether it is one, so the answer matches what will read the file back.
    Hand-rolling the predicate is how a comment, a table header or one line of a wrapped array
    comes to be counted as a key.

    **The `"=" not in line` guard is load-bearing and not a fast path.** `tomllib.loads("[budget]")`
    succeeds and returns `{"budget": {}}` — one top-level key — so without it every table header in
    a hunk would be reported as a changed key named after its own table.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    try:
        parsed: Mapping[str, Any] = tomllib.loads(stripped)
    except tomllib.TOMLDecodeError:
        return None
    if len(parsed) != 1:
        return None
    # A **dotted** key parses to nested tables, so `next(iter(parsed))` alone would report
    # `budget.monthly_eur = 30.00` as a key called `budget` — and the spending-cap heading would
    # name a table instead of the cap. Walk down to the leaf and rejoin.
    key, value = next(iter(parsed.items()))
    while isinstance(value, dict) and len(cast(Mapping[str, Any], value)) == 1:
        inner, value = next(iter(cast(Mapping[str, Any], value).items()))
        key = f"{key}.{inner}"
    return key, _literal(stripped)


def _path_of(section: str | None) -> str | None:
    """`[retrieval.confidence]` → `retrieval.confidence`. `None` stays `None` (a hunk before any
    table, which a manifest's identity block cannot produce but a third-party template can)."""
    if section is None:
        return None
    return section.strip().strip("[]").strip() or None


def changes(hunk: Hunk) -> tuple[Change, ...]:
    """Every key whose value this hunk moves, in the order the hunk mentions them.

    **Keys are read out of the hunk's own lines, never matched against a list of names.** The
    consent path this feeds must announce a cap the author of this function never heard of:
    `confirm_above_eur` exists today beside the two the plan names, and a later template may add a
    fourth. A name list prints a heading for the keys someone remembered and stays silent on the
    rest — which is a consent path that fails exactly when it is carrying new information.

    A key present on both sides with the same literal is not a change. That happens when a hunk
    rewrites the comments around a value and difflib pairs the untouched line into the replacement.
    """
    section = _path_of(hunk.section)
    removed: dict[tuple[str | None, str], str] = {}
    added: dict[tuple[str | None, str], str] = {}
    order: list[tuple[str | None, str]] = []
    for line in hunk.lines:
        marker, text = line[:1], line[1:]
        # **A table header inside the hunk moves the section from there on.** `hunk.section` is read
        # out of `base` by scanning *backwards* from the first changed line, so it is the table the
        # hunk *starts* in — and a hunk that adds a whole new table carries keys belonging to a
        # table `base` does not have. Attributing those to the preceding table is not a cosmetic
        # mislabel: a new table stamped directly after `[budget]` would have every one of its keys
        # announced as a spending cap, which is precisely the false alarm D-10's requirement 2
        # exists to prevent. Context lines count too — that is how the header usually arrives.
        if _TABLE.match(text):
            section = _path_of(text.strip())
            continue
        if marker not in ("-", "+"):
            continue
        pair = _key_value(text)
        if pair is None:
            continue
        key, value = pair
        (removed if marker == "-" else added)[(section, key)] = value
        if (section, key) not in order:
            order.append((section, key))
    return tuple(
        Change(
            section=where, key=key, before=removed.get((where, key)), after=added.get((where, key))
        )
        for where, key in order
        if removed.get((where, key)) != added.get((where, key))
    )


@dataclass(frozen=True, slots=True)
class Report:
    """What `pnk upgrade` found. Nothing here is an instruction to write anything."""

    outcome: Outcome
    detail: str
    name: str | None = None
    recorded: str | None = None
    installed: str | None = None
    remedy: str | None = None
    diff: str = ""
    hunks: tuple[Hunk, ...] = ()
    base: str = ""
    """The recorded version's rendered manifest — the left side of the diff, kept because `apply`
    needs it to tell a key the hunks *introduce* from one the baseline already had. Not in
    `as_json`: it is an input to the comparison, not a finding, and a consumer that wants it can
    render it. Empty on every outcome that made no comparison."""

    def counted(self, placement: Placement) -> int:
        return sum(1 for hunk in self.hunks if hunk.placement is placement)

    def placed(self, placement: Placement) -> tuple[Hunk, ...]:
        return tuple(hunk for hunk in self.hunks if hunk.placement is placement)


BUDGET = "budget"
"""The TOML table whose keys are money. Named once; found by position, never by key name."""

SPEND_HEADING = "⚠️  a spending cap changes:"
"""The heading a money change is printed under, in **both** outputs.

**Its wording is an assertion target, so it may not contain the word `budget`.** The diff prints
`[budget]` as its own hunk header whatever else happens, so a negative control asserting the
heading is *absent* would fail for a reason that has nothing to do with the heading — and the
negative controls are the only thing that makes the three positive assertions mean anything. The
discriminating substring is `spending cap`, which occurs nowhere else in this command's output.
"""

INVALIDATES: Mapping[str, frozenset[str]] = {
    "embedding": frozenset({"model", "dim", "revision"}),
    "chunking": frozenset({"strategy", "max_tokens", "overlap"}),
}
"""Keys whose value the existing `.pinakes/index.db` was built under (drift axis 2,
docs/KB-UPDATES.md §2). Applying one of these leaves an index search refuses to open, so `--apply`
names them and names `pnk sync --rebuild`. Unlike the money keys these **are** a name list, and
deliberately: it is not "every key in this table" — `[chunking] headings` is here too in spirit but
`[embedding] provider` is not, since a provider swap that keeps the model is not a rebuild."""


def budget_changes(report: Report) -> tuple[Change, ...]:
    """Every money key an `--apply` of this report would actually move. Empty when it would not.

    **One predicate, called by `pnk upgrade` and by `pnk upgrade --apply`**, because a heading that
    the report and the writer disagree about is worse than no heading: the report is where the user
    decides, and it must not be the weaker of the two outputs.

    Three near-misses are excluded, and each of them would announce a change that is not happening:
    a conflicting run (nothing is written at all, `[budget]` included — the rule is all-or-nothing),
    an *already applied* budget hunk (the KB already carries the value), and a bump touching no
    `[budget]` line.

    **A fourth is excluded that the plan did not enumerate, and the deviation is deliberate.** The
    plan's predicate is positional — *a clean hunk falls inside `[budget]`* — and the shipped
    template's own `[budget]` drift (M3) rewrote three comment lines as well as two values. A hunk
    that moved *only* the comments is inside `[budget]`, applies cleanly, and moves no money; under
    the positional rule it would print a spending-cap heading with nothing under it. That is the
    fourth near-miss, it trains a user to skip the one heading that must be read, and requirement 2
    of D-10 is written against exactly that failure. So the predicate is *a clean hunk inside
    `[budget]` that changes at least one key* — still structural, still no key-name list.
    """
    if report.counted(Placement.CONFLICT):
        return ()
    return tuple(
        change
        for hunk in report.placed(Placement.CLEAN)
        for change in changes(hunk)
        if change.section == BUDGET
    )


def invalidating(report: Report) -> tuple[Change, ...]:
    """Applied keys that leave the existing index incoherent, so the output can name them.

    Refusing to sync without saying so leaves the user holding exactly the state they cannot
    search — and `::test_apply_does_not_run_a_sync` would otherwise pin that as correct.
    """
    if report.counted(Placement.CONFLICT):
        return ()
    return tuple(
        change
        for hunk in report.placed(Placement.CLEAN)
        for change in changes(hunk)
        if change.key in INVALIDATES.get(change.section or "", frozenset())
    )


def _flat_keys(table: Mapping[str, Any], prefix: str = "") -> set[str]:
    """Every leaf key of a parsed manifest as a dotted path — `budget.monthly_eur`."""
    found: set[str] = set()
    for key, value in table.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            found |= _flat_keys(cast(Mapping[str, Any], value), f"{path}.")
        else:
            found.add(path)
    return found


def introduced(report: Report, base: str) -> tuple[str, ...]:
    """Keys the applied hunks add that the manifest's baseline did not have.

    **The operands are the part that is easy to get wrong.** The set is
    "base plus the applied hunks", minus "base", **not** "ours" minus "base". The two differ
    on any hunk that is *already applied* and skipped: the natural wrong implementation credits
    this run with a key the user adopted by hand some time ago, and then recommends they think
    about `[kb] requires_pinakes` because of it.

    Computed as *a key an applied hunk adds which `base` does not already carry anywhere*, which is
    the same set and needs no second copy of the document to be reconstructed. **Today it is always
    empty** — no template change has ever added a key (F2) — which is exactly why the negative test
    is the load-bearing one.
    """
    if report.counted(Placement.CONFLICT):
        return ()
    try:
        existing = _flat_keys(tomllib.loads(base))
    except tomllib.TOMLDecodeError:  # pragma: no cover — `base` rendered from an archived template
        return ()
    found: list[str] = []
    for hunk in report.placed(Placement.CLEAN):
        for change in changes(hunk):
            if change.before is None and change.path not in existing and change.path not in found:
                found.append(change.path)
    return tuple(found)


def image(lines: Sequence[str], *markers: str) -> tuple[str, ...]:
    """The unified-diff lines carrying any of *markers*, with the marker stripped.

    One derivation, three uses. `_placement` needs the *before* and *after* images before a `Hunk`
    exists to hold them, so a second copy on the dataclass had gone unused while the two could
    silently disagree — the shape this project keeps finding (see `template.cannot_compare`).
    """
    return tuple(line[1:] for line in lines if line[:1] in markers)


def _occurrences(lines: Sequence[str], block: Sequence[str]) -> int:
    """How many positions of *lines* hold *block* contiguously, in order, byte for byte.

    An empty block occurs zero times. Nothing depends on that today — the pure-addition case is
    carried by `_placement`'s own `not removed` guard, where it is visible — but "everywhere" is
    the other defensible convention for the empty block and silently picking it would change an
    answer, so the choice is stated rather than left to whoever reads the loop.
    """
    if not block:
        return 0
    width = len(block)
    return sum(
        1 for start in range(len(lines) - width + 1) if lines[start : start + width] == list(block)
    )


def _placement(hunk_lines: Sequence[str], theirs: Sequence[str]) -> Placement:
    """The placement predicate, evaluated in an order that is part of the predicate.

    1. `ALREADY_APPLIED` — the *after* image occurs at exactly one position, and the hunk's
       *before* image occurs at none. A hunk that removes nothing satisfies the second half
       vacuously, and that is what makes this reachable at all for a pure addition.
    2. `CLEAN` — the *before* image occurs at exactly one position.
    3. `CONFLICT` — anything else: no match, several matches, a partial match, a different order.

    **Test 1 before test 2, or every pure-addition hunk is classified wrong.** A hunk that only
    adds lines has an empty removed set, so its *before* image is its context alone — which is
    still present after the change has been applied whenever the added lines sit at the context's
    edge. Both predicates then hold and whichever runs first wins. Every hunk the shipped template
    has ever produced under `[sources]` is a pure addition, so this is the ordinary case and not a
    corner.

    **The second half of test 1 asks about the *before image*, not about the removed lines on their
    own — and the difference is a misclassification, not a nicety.** "Do the removed lines appear
    anywhere in the file" is a whole-file question, so a hunk that removes a blank line or a bare
    `#` — a manifest is comment-dense and repeats both — could never be *already applied*: the
    user who adopted that change by hand was told `conflicts`, and under a later `--apply`'s
    all-or-nothing rule that refuses the whole run for them. Asking whether the *before image* is
    still there scopes the question to the hunk's own region, which is what was meant.

    **"Found, unmodified, somewhere in `theirs`" is not the predicate.** A comment-dense file's
    repeated blank lines and repeated comment shapes satisfy a loose rule twice over, and two
    places a hunk could belong is not one. Uniqueness and contiguity are part of the rule, not a
    refinement of it. (A user who moved a whole table *intact* is **not** an example of this:
    placement here is content-addressed rather than offset-addressed, so a moved-but-unbroken
    region still places, correctly. The plan's own text used it as one, and it does not hold.)
    """
    removed = image(hunk_lines, "-")
    after = image(hunk_lines, " ", "+")
    before = image(hunk_lines, " ", "-")
    if _occurrences(theirs, after) == 1 and (not removed or _occurrences(theirs, before) == 0):
        return Placement.ALREADY_APPLIED
    if _occurrences(theirs, before) == 1:
        return Placement.CLEAN
    return Placement.CONFLICT


def _range(start: int, stop: int) -> str:
    """A unified-diff range, `difflib`'s own rule: a one-line range prints as a bare line number,
    and an empty range points at the line *before* the gap."""
    beginning = start + 1
    length = stop - start
    if length == 1:
        return str(beginning)
    if not length:
        beginning -= 1
    return f"{beginning},{length}"


def _section(
    base_lines: Sequence[str], group: Sequence[tuple[str, int, int, int, int]]
) -> str | None:
    """The TOML table a hunk falls inside, read out of `base` — what a conflict message names.

    Scanned backwards from the hunk's first *changed* line, because a hunk carries three lines of
    context and the table header is usually in it. An insertion changes nothing in `base`, so the
    scan starts one line earlier: the text lands *before* `base_lines[i1]`, which may itself be the
    next table's header.
    """
    for tag, i1, _i2, _j1, _j2 in group:
        if tag == "equal":
            continue
        start = i1 - 1 if tag == "insert" else i1
        for index in range(min(start, len(base_lines) - 1), -1, -1):
            if _TABLE.match(base_lines[index]):
                return base_lines[index].strip()
        return None
    return None


def hunks(base: str, ours: str, theirs: str) -> tuple[Hunk, ...]:
    """Every region `base → ours` changes, each carrying where it stands against `theirs`.

    `autojunk=False` is a guard rather than a fix, and its limit is worth stating: difflib's
    heuristic only engages at 200 elements or more, and the shipped manifest is about fifty lines,
    so **on anything this project ships the flag changes nothing**. It is set for the manifest that
    is not ours — a third-party template, or one that grows — where a blank line appearing in more
    than 1% of the file would be treated as noise and could cost a hunk.
    """
    base_lines = base.splitlines()
    ours_lines = ours.splitlines()
    theirs_lines = theirs.splitlines()

    found: list[Hunk] = []
    matcher = difflib.SequenceMatcher(a=base_lines, b=ours_lines, autojunk=False)
    for group in matcher.get_grouped_opcodes(CONTEXT_LINES):
        lines: list[str] = []
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                lines.extend(f" {line}" for line in base_lines[i1:i2])
                continue
            if tag in ("replace", "delete"):
                lines.extend(f"-{line}" for line in base_lines[i1:i2])
            if tag in ("replace", "insert"):
                lines.extend(f"+{line}" for line in ours_lines[j1:j2])
        old = _range(group[0][1], group[-1][2])
        new = _range(group[0][3], group[-1][4])
        found.append(
            Hunk(
                header=f"@@ -{old} +{new} @@",
                section=_section(base_lines, group),
                lines=tuple(lines),
                placement=_placement(lines, theirs_lines),
            )
        )
    return tuple(found)


def _no_baseline(
    detail: str,
    remedy: str,
    *,
    name: str | None = None,
    recorded: str | None = None,
    installed: str | None = None,
) -> Report:
    """Every field this report can still honestly carry, named — never `**kwargs`.

    A spread would let a caller set `diff` or `hunks` on a report that made no comparison, which is
    the one thing a `NO_BASELINE` outcome asserts did not happen.
    """
    return Report(
        outcome=Outcome.NO_BASELINE,
        detail=detail,
        remedy=remedy,
        name=name,
        recorded=recorded,
        installed=installed,
    )


def plan(manifest: Manifest) -> Report:
    """Read three inputs, decide, and return. Nothing under the KB is opened for writing."""
    recorded = manifest.kb.template
    if recorded is None:
        return _no_baseline(
            "cannot compare: this KB records no template",
            "`[kb] template` is what says which blueprint the KB was stamped from, and this "
            "manifest has none — so there is nothing to compare it against. A KB written by hand "
            "is a legitimate KB; `pnk upgrade` is simply not a command it has a use for.",
        )

    name, _, version = recorded.partition("@")
    try:
        installed = template.describe(name)
    except PinakesError as exc:
        return _no_baseline(
            f"cannot compare: {recorded} is not installed here",
            f"{exc.remedy} Your KB is unaffected — a template is the blueprint it was stamped "
            "from, not something it needs at rest.",
            recorded=recorded,
            name=name,
        )

    if installed.version == version:
        return Report(
            outcome=Outcome.UP_TO_DATE,
            detail=f"up to date: {recorded}",
            name=name,
            recorded=recorded,
            installed=installed.reference,
        )

    archived = template.archived_versions(name)
    missing = [
        reference
        for reference, candidate in ((recorded, version), (installed.reference, installed.version))
        if candidate not in archived
    ]
    if missing:
        detail, remedy = template.cannot_compare(missing, name, archived)
        return _no_baseline(
            detail,
            remedy,
            name=name,
            recorded=recorded,
            installed=installed.reference,
        )

    context = template.render_context(manifest)
    try:
        base = template.render_archived(name, version, context)
        ours = template.render_archived(name, installed.version, context)
    except PinakesError as exc:
        # An archived version this build cannot render is the same fact `pnk doctor` reports as
        # `cannot compare`, and it is not the user's to fix. A traceback here would be the third
        # answer to a question two surfaces already agree on.
        return _no_baseline(
            f"cannot compare: {exc.message}",
            exc.remedy,
            name=name,
            recorded=recorded,
            installed=installed.reference,
        )

    theirs = manifest.path.read_text(encoding="utf-8")
    found = hunks(base, ours, theirs)
    if not found:
        # **A version can move without the manifest moving.** A template version denotes four
        # consumed files and this command reads one of them, so a bump that touched only the
        # starter golden set lands here. Printing an empty diff and calling it agreement is what
        # `pnk doctor`'s fourth outcome was added to stop.
        return Report(
            outcome=Outcome.SAME_MANIFEST,
            detail=f"{recorded} and {installed.reference} stamp an identical {MANIFEST_NAME}",
            name=name,
            recorded=recorded,
            installed=installed.reference,
            remedy="A template version covers more than the manifest — its README and its starter "
            "golden set — and those are yours to keep or refresh by hand. `pnk init` a throwaway "
            "directory to see the current ones.",
        )

    return Report(
        outcome=Outcome.DRIFTED,
        detail=f"{recorded} → {installed.reference}",
        name=name,
        recorded=recorded,
        installed=installed.reference,
        diff="\n".join(line for hunk in found for line in (hunk.header, *hunk.lines)),
        hunks=found,
        base=base,
    )


def as_json(
    report: Report, *, applied: "Applied | None" = None, refused: PinakesError | None = None
) -> dict[str, object]:
    """The same three parts the human output carries, and the same hunks in the same order.

    `applied` and `refused` are mutually exclusive and both absent unless `--apply` ran. `spend`
    is always present and always the same predicate the heading uses — a consumer must be able to
    ask *would this move money* without parsing a heading out of prose.
    """
    money_moved = budget_changes(report)
    return {
        "spend": [
            {"key": change.path, "before": change.before, "after": change.after}
            for change in money_moved
        ],
        "applied": None
        if applied is None
        else {
            "written": len(applied.written),
            "skipped": len(applied.skipped),
            "backup": str(applied.backup),
            "template": applied.reference,
            "invalidates": [change.path for change in applied.invalidating],
            "introduced": list(applied.introduced),
        },
        "refused": None
        if refused is None
        else {"message": refused.message, "remedy": refused.remedy},
        **_report_json(report),
    }


def _report_json(report: Report) -> dict[str, object]:
    return {
        "outcome": report.outcome.value,
        "detail": report.detail,
        "remedy": report.remedy,
        "template": report.name,
        "recorded": report.recorded,
        "installed": report.installed,
        "diff": report.diff,
        "hunks": [
            {
                "header": hunk.header,
                "section": hunk.section,
                "placement": hunk.placement.value,
                "removed": list(hunk.removed),
                "added": list(hunk.added),
            }
            for hunk in report.hunks
        ],
        "counts": {
            placement.value: report.counted(placement)
            for placement in (Placement.CLEAN, Placement.ALREADY_APPLIED, Placement.CONFLICT)
        },
    }


def lines(report: Report, *, applying: bool = False) -> list[str]:
    """The human report, in the order the plan fixes: what the template changed, then how it fits.

    Nothing else. A line the user changed and the template did not is not drift and is not this
    command's business, so it appears nowhere — which is a property of `base → ours` being the only
    diff computed, not a filter applied afterwards.

    *applying* drops only the closing *nothing was written* line, which `--apply` replaces with an
    account of what it did. **Everything else is byte-identical between the two commands**, the
    spending-cap heading included — that is what makes the report the thing a user decides on.
    """
    if report.outcome is not Outcome.DRIFTED:
        out = [report.detail]
        if report.remedy:
            # Wrapped here and nowhere else: `as_json` hands a consumer the string it was given.
            # On this path the remedy *is* the output — a KB recording an unarchived version has
            # nothing else to show — and a 600-character paragraph in one terminal line is a
            # remedy nobody reads.
            out += ["", fill(report.remedy)]
        return out

    out = [report.detail, "", "what the template changed:", ""]
    out += report.diff.splitlines()
    out += ["", f"how it fits your {MANIFEST_NAME}:", ""]
    for hunk in report.hunks:
        where = f"{hunk.section} " if hunk.section else ""
        out.append(f"  {hunk.placement.label:<15} {where}{hunk.header}")
    # `placement.label` is a verb phrase for the per-hunk listing ("applies cleanly"), which reads
    # as "2 applies cleanly" once a count is put in front of it. The summary needs a noun.
    counts = ", ".join(
        f"{report.counted(placement)} {_PLACEMENT_COUNTED[placement]}"
        for placement in (Placement.CLEAN, Placement.ALREADY_APPLIED, Placement.CONFLICT)
        if report.counted(placement)
    )
    out += ["", counts + "."]
    if report.counted(Placement.CONFLICT):
        out.append(
            fill(
                "A conflict is not a fault. It means the lines a change expects are not in your "
                "file the way it expects them — edited, reordered, or present in two places — so "
                "nothing can be placed there mechanically and the diff above is what to apply by "
                "hand."
            )
        )
    out += money(report)
    if not applying:
        out += ["", f"Nothing was written: `pnk upgrade` reads your {MANIFEST_NAME} and reports."]
    return out


BACKUP_SUFFIX = ".orig"
"""D-5 A: the pre-`--apply` manifest, beside the manifest, named and printed and never deleted.

D-10 raises the stakes on it specifically — with `[budget]` hunks applying, this file is the only
way a user who did not want a raised cap gets the old numbers back without an editor and a memory.
It therefore holds the bytes as they were **before** the write, which is why it is written from the
bytes that were read rather than copied from a file that is about to change under it.
"""

_KB_TABLE = re.compile(r"\s*\[kb\]\s*(#.*)?\Z")
_TEMPLATE_KEY = re.compile(r"\s*template\s*=")
_TEMPLATE_ASSIGNMENT = re.compile(
    r"(?P<prefix>\s*template\s*=\s*)(?P<value>\"[^\"]*\"|'[^']*')(?P<rest>.*)\Z"
)
"""`template = "notes@1.0"  # stamped at init` → prefix, value, rest.

Three groups rather than a whole-line rewrite, and each one is a thing that would otherwise be
destroyed: the prefix carries the column alignment the template renders, and `rest` carries a
trailing comment the user may have written. A rewrite that reformats the line it was asked to
restamp is a second edit nobody consented to.
"""


@dataclass(frozen=True, slots=True)
class Source:
    """The KB's manifest as text that can be written back byte-for-byte.

    **`Path.read_text` cannot do this job and the reason is not obvious.** It opens in universal-
    newline mode, so a CRLF manifest is already `\\n`-only by the time anything here sees it — which
    is *correct* for the report (the change genuinely belongs there) and silently wrong for a write,
    which would put LF lines into a CRLF file and leave the endings mixed. So the bytes are read
    raw, the convention is recorded, and every line is written back in it.
    """

    raw: bytes
    content: tuple[str, ...]
    trailing: bool
    newline: str

    def render(self, content: Sequence[str]) -> bytes:
        body = "\n".join(content) + ("\n" if self.trailing else "")
        return body.replace("\n", self.newline).encode("utf-8")


def read_source(path: Path) -> Source:
    """Read the manifest for writing, refusing a file whose line endings are not uniform.

    **Refuse rather than repair**, which is the choice this open correction left to T4. A mixed-
    ending manifest is already the product of two tools disagreeing, and picking one for the user
    silently rewrites lines they did not ask to be touched — in the one file Pinakes has spent every
    other rule not touching. Uniform CRLF is *preserved*, which is the common Windows case and the
    one worth carrying; a lone `\\r` and a CRLF/LF mixture are named and refused.
    """
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    crlf = text.count("\r\n")
    stray_cr = text.count("\r") - crlf
    stray_lf = text.count("\n") - crlf
    if stray_cr or (crlf and stray_lf):
        raise UpgradeError(
            f"{path.name} does not use one line ending throughout"
            f" ({crlf} CRLF, {stray_lf} LF, {stray_cr} bare CR).",
            remedy="`--apply` writes lines back, and writing into a file whose endings already "
            "disagree would leave a mixture nobody chose. Normalise the file to one convention "
            "and run it again; `pnk upgrade` without `--apply` reports either way.",
        )
    normalised = text.replace("\r\n", "\n")
    parts = normalised.split("\n")
    trailing = bool(parts) and parts[-1] == ""
    content = parts[:-1] if trailing else parts
    # **The report splits lines one way and this splits them another, so they are checked against
    # each other rather than assumed equal.** `hunks()` reaches `str.splitlines()`, which breaks on
    # `\u2028`, `\u2029` and `\x85`; `split("\n")` breaks on none of them. All three are `non-ascii`
    # under TOML's own comment grammar, so a manifest can legally carry one and still load — and it
    # would then be a different list of lines on each side, so a hunk the report called *unique*
    # could match somewhere else here, or nowhere. Rejoining on `\n` instead would silently turn
    # that character into a newline in a file the user owns, which is worse than refusing.
    # (A form feed cannot get here: TOML forbids control characters in a comment, so `manifest.load`
    # refuses it one guard earlier.)
    if normalised.splitlines() != content:
        raise UpgradeError(
            f"{path.name} contains a character Python breaks lines on that is not a newline "
            "(a Unicode line separator, or U+0085).",
            remedy="`--apply` writes lines back, and that character makes *which lines* an "
            "ambiguous question. Remove it and run this again; `pnk upgrade` without `--apply` "
            "reports either way.",
        )
    return Source(
        raw=raw,
        content=tuple(content),
        trailing=trailing,
        newline="\r\n" if crlf else "\n",
    )


@dataclass(frozen=True, slots=True)
class Splice:
    """One clean hunk, resolved to the exact region of `theirs` it replaces."""

    hunk: Hunk
    start: int
    stop: int
    replacement: tuple[str, ...]


def splices(report: Report, content: Sequence[str]) -> tuple[Splice, ...]:
    """Where every clean hunk lands, all of it decided before anything is written.

    Public for the same reason `fill` and `restamp` are: **both of its refusals are unreachable
    from any fixture that drives the command**, so a test has to reach the function itself or the
    two guards ship untested. One is unreachable by construction (`_placement` already established
    uniqueness over the same text) and the other needs a manifest repeating a region in a shape
    `difflib` will still call two hunks.

    Positions are resolved against the **unmodified** manifest and applied last-to-first, so no
    splice shifts the coordinates of another. Two guards, and both are refusals rather than
    corrections:

    * **a hunk that no longer places uniquely** — `_placement` said it did, over the same text, so
      this is unreachable and stays as an assertion because the alternative is writing at a guessed
      position;
    * **two hunks whose regions overlap.** `difflib` yields hunks that are disjoint in `base`;
      nothing makes their *placements in `theirs`* disjoint, and a user whose manifest repeats a
      region can produce it. Overlapping edits have no defined result, which is what a conflict is,
      so it is refused as one.
    """
    planned: list[Splice] = []
    for hunk in report.placed(Placement.CLEAN):
        before = image(hunk.lines, " ", "-")
        after = image(hunk.lines, " ", "+")
        width = len(before)
        starts = [
            index
            for index in range(len(content) - width + 1)
            if list(content[index : index + width]) == list(before)
        ]
        if len(starts) != 1 or not width:
            raise UpgradeError(
                f"cannot apply: {hunk.where} does not place in a single position any more.",
                remedy=f"Your {MANIFEST_NAME} changed between the report and the write. Run "
                "`pnk upgrade` again to see the current placement.",
            )
        planned.append(Splice(hunk, starts[0], starts[0] + width, after))
    planned.sort(key=lambda splice: splice.start)
    for earlier, later in itertools.pairwise(planned):
        if later.start < earlier.stop:
            raise UpgradeError(
                f"cannot apply: {earlier.hunk.where} and {later.hunk.where} land on top of each "
                f"other in your {MANIFEST_NAME} — that is a conflict.",
                remedy="Two changes cannot both be written into one region. Apply the diff above "
                "by hand.",
            )
    return tuple(planned)


def _spliced(content: Sequence[str], splices: Sequence[Splice]) -> list[str]:
    out = list(content)
    for splice in reversed(splices):
        out[splice.start : splice.stop] = list(splice.replacement)
    return out


def restamp(content: Sequence[str], reference: str) -> list[str]:
    """Rewrite `[kb] template`, **in place, inside `[kb]` only** — the one key `--apply` writes
    outside the applied hunks (D-11 leaves `requires_pinakes` to the user).

    Public because it is the unit its own tests have to reach, the same reason `fill` is: the case
    that would corrupt a file — a `template = …` line in a *later* table — is unreachable through
    the product, since an unknown manifest key is a hard error in `manifest.load`. A test driving
    it end to end would silently assert nothing.

    Bounded on purpose, and the bound is what pays for there being no `tomlkit` in the core
    dependencies: one line, one known shape, refusing rather than inventing. A whole-file
    `^template =` substitution corrupts a `template = …` line in any later table, and appending the
    key when it is absent guesses where it belongs in a file the user owns — which is the thing
    this command exists not to do.

    The region ends at the next **table header**, not at the next line starting with `[`: a wrapped
    array's continuation line starts with `[` too, and ending the region there would look past the
    key and refuse a manifest that is perfectly ordinary.
    """
    start = next((index for index, line in enumerate(content) if _KB_TABLE.match(line)), None)
    if start is None:
        raise UpgradeError(
            f"cannot apply: your {MANIFEST_NAME} has no `[kb]` table to record the new "
            "template version in.",
            remedy="`[kb]` is what says which blueprint the KB was stamped from. Add the table by "
            "hand, or leave it and adopt the diff above yourself.",
        )
    stop = next(
        (index for index in range(start + 1, len(content)) if _TABLE.match(content[index])),
        len(content),
    )
    found = [index for index in range(start + 1, stop) if _TEMPLATE_KEY.match(content[index])]
    if len(found) != 1:
        raise UpgradeError(
            f"cannot apply: `[kb] template` occurs {len(found)} times in your {MANIFEST_NAME}, "
            "and it must occur exactly once for the new version to be recorded.",
            remedy="Guessing where the key belongs in a file you own is the one thing this command "
            "will not do. Fix `[kb]` by hand and run it again.",
        )
    match = _TEMPLATE_ASSIGNMENT.match(content[found[0]])
    if match is None:
        raise UpgradeError(
            f"cannot apply: `[kb] template` is not a quoted value this command can rewrite: "
            f"{content[found[0]].strip()}",
            remedy='It rewrites `template = "name@version"` and nothing else, so that a line it '
            "does not understand is left alone rather than reformatted.",
        )
    out = list(content)
    out[found[0]] = f'{match["prefix"]}"{reference}"{match["rest"]}'
    return out


def through_symlink(path: Path) -> Path:
    """Where a write to *path* must actually land.

    **`os.replace` onto a symlink destroys the link** and leaves a regular file, with the real
    manifest untouched somewhere else still holding the old text — the user's own arrangement
    dismantled silently. `sidecar.write` learned this first and resolves the same way; a KB whose
    `pinakes.toml` is a link into a shared config directory is exactly the arrangement a portable
    tool should not break.
    """
    return path.resolve() if path.is_symlink() else path


def _write_atomic(path: Path, payload: bytes) -> None:
    """Rename-atomic, preserving the target's own permissions.

    `mkstemp` creates its file `0600`, so renaming it into place would silently narrow a manifest
    the user had made group- or world-readable. The mode is copied from the file being replaced,
    which is the only place the intended value exists.
    """
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pnk-upgrade-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    except BaseException:  # pragma: no cover — a failing write is not reproducible in-process
        Path(temporary).unlink(missing_ok=True)
        raise


@dataclass(frozen=True, slots=True)
class Applied:
    """What `--apply` wrote. Every field is something the output has to name."""

    written: tuple[Hunk, ...]
    skipped: tuple[Hunk, ...]
    backup: Path
    root: Path
    reference: str

    @property
    def backup_shown(self) -> str:
        """How to name the backup so a reader can find it.

        Its bare filename, when it sits in the KB — which is every ordinary KB, and the form the
        rest of this command's output uses. **Its full path when it does not**, which happens when
        `pinakes.toml` is a symlink: the backup is written beside the file it backs up, and telling
        someone their old manifest is in `pinakes.toml.orig` when that file is in another directory
        entirely is worse than saying nothing.
        """
        return self.backup.name if self.backup.parent == self.root else str(self.backup)

    invalidating: tuple[Change, ...]
    introduced: tuple[str, ...]


def apply(manifest: Manifest, report: Report) -> Applied:
    """Write the cleanly-applying hunks, or write nothing at all and say why.

    **The order of what follows is the specification, not an implementation choice.** Every refusal
    is raised before the first byte is written, so a refused run leaves the KB byte-identical and,
    in particular, leaves no `pinakes.toml.orig` — a backup written by a refusal would make the
    *next* run refuse on the `.orig` rule instead of on its real reason, which is a non-zero exit
    delivered by the wrong guard.

    **Content refusals come before environmental ones.** A conflict is a permanent fact about this
    KB and a stray `.orig` is transient, so checking the transient one first would tell a user to
    clear a file in order to be told, on the retry, that their manifest conflicts anyway.

    **All-or-nothing, `[budget]` included (D-10 B).** One conflicting hunk refuses the whole run;
    the applier has no `[budget]` predicate, no exclusion and no second flag. What makes that
    defensible is the consent path — `money()` in both outputs, printed before this function is
    called — and not a special case here. A later reader who adds one has reversed a decision.
    """
    reference = report.installed
    if report.outcome is not Outcome.DRIFTED or reference is None:  # pragma: no cover
        raise UpgradeError(  # the CLI never gets here: it prints and returns on every other outcome
            f"cannot apply: {report.detail}",
            remedy="`--apply` writes the hunks of a template diff, and this KB has no diff.",
        )

    conflicts = report.placed(Placement.CONFLICT)
    if conflicts:
        listed = "; ".join(hunk.where for hunk in conflicts)
        raise UpgradeError(
            f"cannot apply: {len(conflicts)} of {len(report.hunks)} hunks conflict — {listed}",
            remedy="Nothing was written, and that is all-or-nothing on purpose: applying the rest "
            "would leave your manifest half-upgraded with no record of which half. The diff above "
            "is what to apply by hand.",
        )

    target = through_symlink(manifest.path)
    source = read_source(target)

    backup = target.with_name(target.name + BACKUP_SUFFIX)
    if backup.exists():
        raise UpgradeError(
            f"cannot apply: {backup.name} is already there.",
            remedy=f"It is the manifest as it was before an earlier `--apply`. Overwriting it "
            f"would destroy the only copy of that state, so it is never written twice. Move or "
            f"delete {backup.name} once you are sure you no longer need it.",
        )

    holder = read_holder(manifest.state_dir / LOCK_NAME)
    if holder is not None:
        raise UpgradeError(
            f"cannot apply: a sync holds this KB — {holder.describe()}.",
            remedy="A sync indexes under the settings this file states, so rewriting it mid-run "
            "would leave that index built under settings the manifest no longer carries. Wait for "
            "it to finish. If nothing is running, the next `pnk sync` reclaims a stale lock on "
            "this host automatically.",
        )

    updated = restamp(_spliced(source.content, splices(report, source.content)), reference)
    payload = source.render(updated)

    # ---- everything above decided; the first byte lands here -------------------------------
    backup.write_bytes(source.raw)
    _write_atomic(target, payload)

    try:
        from pinakes import manifest as manifest_module

        manifest_module.load(manifest.root)
    except ManifestError as exc:
        # Atomically, and the backup is removed only afterwards: until the restore has landed, that
        # file is the only copy of the state being restored.
        _write_atomic(target, source.raw)
        backup.unlink(missing_ok=True)
        raise UpgradeError(
            f"cannot apply: the result would not load as a manifest — {exc.message}",
            remedy=f"Your {MANIFEST_NAME} has been restored exactly as it was and no backup was "
            f"left behind. This is a defect in Pinakes, not in your KB: please report it with the "
            f"diff `pnk upgrade` prints.",
        ) from exc

    return Applied(
        written=report.placed(Placement.CLEAN),
        skipped=report.placed(Placement.ALREADY_APPLIED),
        backup=backup,
        root=manifest.root,
        reference=reference,
        invalidating=invalidating(report),
        introduced=introduced(report, report.base),
    )


def applied_lines(result: Applied) -> list[str]:
    """What `--apply` did, after the report and after the spending-cap heading.

    The `.orig` line is the write anchor every ordering assertion uses, and it is printed only when
    a backup was written — which is the moment the write begins. Anchoring on a word like
    *applied* instead would fire against the *already applied* count printed further up.
    """
    counted = [f"{len(result.written)} applied"]
    if result.skipped:
        counted.append(f"{len(result.skipped)} already applied and skipped")
    out = ["", ", ".join(counted) + ".", ""]
    out.append(f"{result.backup_shown} holds your previous {MANIFEST_NAME}, byte for byte.")
    out.append(
        fill(
            "It is a new file in your KB and nothing ignores it — `pnk init` writes a "
            "`.gitignore` covering `.pinakes/` only — so in a git repository it shows up in "
            "`git status` and can be committed by accident."
        )
    )
    out += ["", f"`[kb] template` now records {result.reference}."]
    if result.invalidating:
        named = ", ".join(change.path for change in result.invalidating)
        out += [
            "",
            fill(
                f"These applied keys are what your index was built under: {named}. Search will "
                f"refuse to open it until it is rebuilt — run `pnk sync --rebuild`. Nothing was "
                f"re-chunked, re-embedded or re-extracted here; `--apply` writes the manifest and "
                f"stops."
            ),
        ]
    if result.introduced:
        named = ", ".join(result.introduced)
        out += [
            "",
            fill(
                f"These keys are new to your manifest: {named}. A Pinakes older than the release "
                f"that introduced them cannot read this KB, so you may want "
                f"`[kb] requires_pinakes` "
                f"set by hand. No number is suggested and none is written: nothing in Pinakes maps "
                f"a manifest key to the release it arrived in, so a printed floor would be a guess "
                f"wearing a decimal point."
            ),
        ]
    return out


def money(report: Report) -> list[str]:
    """The spending-cap heading and its lines, or nothing at all.

    Separate from `lines` so the predicate has one caller shape and one test target. A heading
    printed unconditionally satisfies every positive assertion anyone can write about it, so what
    this function must get right is the empty case.
    """
    found = budget_changes(report)
    if not found:
        return []
    return ["", SPEND_HEADING, ""] + [f"  {change.describe()}" for change in found]
