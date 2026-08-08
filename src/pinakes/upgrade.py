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

**This module writes nothing.** Not to the manifest, not under `.pinakes/`. `pnk upgrade --apply`
is a later increment; until then a user adopts a change by reading the diff and editing their own
file, which is the same thing this command would have told them to do.
"""

import difflib
import re
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from pinakes import template
from pinakes.errors import PinakesError
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
        return tuple(line[1:] for line in self.lines if line[:1] == "-")

    @property
    def added(self) -> tuple[str, ...]:
        return tuple(line[1:] for line in self.lines if line[:1] == "+")

    @property
    def before(self) -> tuple[str, ...]:
        """The *before* image — context and removed lines. What the hunk expects to find."""
        return tuple(line[1:] for line in self.lines if line[:1] in (" ", "-"))

    @property
    def after(self) -> tuple[str, ...]:
        """The hunk's *after* image — context and added lines. What is there once it is applied."""
        return tuple(line[1:] for line in self.lines if line[:1] in (" ", "+"))


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

    def counted(self, placement: Placement) -> int:
        return sum(1 for hunk in self.hunks if hunk.placement is placement)


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
    removed = tuple(line[1:] for line in hunk_lines if line[:1] == "-")
    after = tuple(line[1:] for line in hunk_lines if line[:1] in (" ", "+"))
    before = tuple(line[1:] for line in hunk_lines if line[:1] in (" ", "-"))
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
    )


def as_json(report: Report) -> dict[str, object]:
    """The same three parts the human output carries, and the same hunks in the same order."""
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


def lines(report: Report) -> list[str]:
    """The human report, in the order the plan fixes: what the template changed, then how it fits.

    Nothing else. A line the user changed and the template did not is not drift and is not this
    command's business, so it appears nowhere — which is a property of `base → ours` being the only
    diff computed, not a filter applied afterwards.
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
    out += ["", f"Nothing was written: `pnk upgrade` reads your {MANIFEST_NAME} and reports."]
    return out
