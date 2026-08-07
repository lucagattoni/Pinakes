"""Two eval legs differing in exactly one setting — paired on question id, counted by rank.

Written for the metadata-injection experiment
(`plans/20260805_1721-metadata-as-retrieval-context.md` §3) and deliberately not specific to it:
what it knows is that **two legs may differ in one named header key and must be identical in every
other**, which is the shape of any before/after run this project is allowed to draw a conclusion
from.

## Why not `graph_gate.judge`

That one is written around hit-flips within a single `kind`, for a three-leg channel comparison
whose legs are identified by `graph_channel` and an edge-set variant. This experiment has two legs,
identified by `chunking.metadata`, and its criterion is a **rank** comparison over all answerable
questions. `sign_test` and `read_leg` are reused from there unchanged — the statistic and the
artifact reader are the parts that must not be written twice — and `--sign-test` layers the same
p < 0.05 test on top for the gate phase.

## The rank rule, and the one judgement call in it

A question that was found at rank 3 and is now found at rank 1 **improved**. A question that was
found and is now missed is the worst regression available, so a miss sorts after every hit —
`math.inf`. Ranking a miss as "no rank, therefore unchanged" would let a change that loses answers
outright look neutral, which is the failure this ordering exists to prevent.

`no-answer` questions are excluded: they have no rank to move, and their correct outcome is an
abstention, which `eval.score_rows` already scores as `false_confidence`.

## What it refuses, and why refusing is the point

Two legs whose headers disagree on anything but the excepted key are **not** a before and an after
— they are two different experiments, and comparing them attributes the difference to whatever the
caller believed they were testing. `chunking` is the block this matters most for and the one
nothing compared until now: `5993521` added it to the artifact header, and
`graph_gate.check_identity` checks `k`, `embedding`, `rerank`, `ranking` and `retrieval` but not
it, so two legs chunked differently still compared clean. Measured on one RFC, `max_tokens` 510
versus 480 moves 63 of 1 858 chunk texts — a rechunk that a rank comparison would report as the
effect under test.

**What it cannot check, stated so nobody reads it as more than it is.** `eval.header` records
*settings*, not the corpus: no KB path, no document count, no chunk count, no index
`schema_version`. Two legs run against genuinely different corpora — a rebuild that dropped a
document, a re-fetch that picked up an errata-corrected source — therefore still compare clean
here. That has to be established outside this tool, and for the 2d screen it was: both indexes were
compared directly, giving 195 documents, 43 353 chunks and one equal sha256 over every chunk text.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from graph_gate import Leg, read_leg, sign_test

from pinakes.errors import PinakesError
from pinakes.eval import NO_ANSWER, OutcomeRow

#: The one header key the injection experiment's two legs are *meant* to differ on. Expressed as a
#: path into the header so the block it sits in is still compared key by key: excepting the whole
#: `chunking` block would hide a rechunk, which is the very thing this tool checks for.
INJECTION_KEY = ("chunking", "metadata")

MISS = math.inf
"""Where a question the run did not answer sorts: after every rank a run did answer at.

JSON has no infinity, so the artifact writes a miss as `null` — `json.dumps` would otherwise emit a
bare `Infinity` token, which is invalid RFC 8259: `JSON.parse` rejects it and `jq` silently coerces
it to 1.8e308, turning the very outcome this ordering exists to make visible into a finite rank."""

ALPHA = 0.05
"""`graph_gate.ALPHA`, restated because this module's exit code depends on it when
`--sign-test` is asked for."""


def rank_of(row: OutcomeRow) -> float:
    """The rank to compare, with a miss as the worst value rather than as no value."""
    if not row.hit or row.hit_rank is None:
        return MISS
    return float(row.hit_rank)


@dataclass(frozen=True, slots=True)
class Movement:
    """One question whose rank moved, in the form a report has to print."""

    id: str
    kind: str
    before: float
    after: float

    @property
    def improved(self) -> bool:
        return self.after < self.before

    def render(self) -> str:
        def rank(value: float) -> str:
            return "miss" if value == MISS else str(int(value))

        arrow = "->"
        return f"{self.id} [{self.kind}] {rank(self.before)} {arrow} {rank(self.after)}"


@dataclass(frozen=True, slots=True)
class Comparison:
    moved: tuple[Movement, ...]
    unchanged: int

    @property
    def improved(self) -> tuple[Movement, ...]:
        return tuple(move for move in self.moved if move.improved)

    @property
    def regressed(self) -> tuple[Movement, ...]:
        return tuple(move for move in self.moved if not move.improved)

    @property
    def answerable(self) -> int:
        return len(self.moved) + self.unchanged

    def sign_test_p(self) -> float:
        return sign_test(len(self.improved), len(self.regressed))

    def gate_passes(self) -> bool:
        """The 2f criterion: the exact one-sided sign test below `ALPHA`."""
        return self.sign_test_p() < ALPHA

    @property
    def screen_passes(self) -> bool:
        """2d's pre-registered criterion: strictly more improvements than regressions.

        Deliberately loose and deliberately not a p-value — its job is to stop a schema bump that
        would buy nothing, not to decide the hypothesis. The gate at 2f is `--sign-test`.
        """
        return len(self.improved) > len(self.regressed)


def _flatten(header: dict[str, Any], prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    """Header as `path -> value`, so one key inside a block can be excepted without hiding the
    rest of that block. A whole-block exception is how a rechunk would travel unnoticed."""
    flat: dict[tuple[str, ...], Any] = {}
    for key, value in header.items():
        path = (*prefix, str(key))
        if isinstance(value, dict):
            flat |= _flatten({str(k): v for k, v in value.items()}, path)  # pyright: ignore
        else:
            flat[path] = value
    return flat


def _excepted(leg: Leg, excepting: tuple[str, ...]) -> Any:
    """The value of the one key the legs may differ on; `None` if the leg does not carry it."""
    return _flatten(leg.header).get(excepting)


def check_identity(
    before: Leg, after: Leg, *, excepting: tuple[str, ...] = INJECTION_KEY
) -> list[str]:
    """Refuse two legs that are not a before and an after of the same experiment.

    Every complaint is otherwise a *silent* wrong answer: a rank comparison always produces
    numbers, and nothing in a pair of artifacts says they were produced by the same pipeline
    except the headers this reads.
    """
    problems: list[str] = []
    flat_before, flat_after = _flatten(before.header), _flatten(after.header)

    for path in sorted(set(flat_before) | set(flat_after), key=lambda item: ".".join(item)):
        if path == excepting:
            continue
        was, now = flat_before.get(path), flat_after.get(path)
        if was != now:
            problems.append(
                f"the legs disagree on `{'.'.join(path)}` ({was!r} vs {now!r}) — a leg is "
                "compared against one produced by the same pipeline, or it is not compared at all"
            )

    excepted_before = flat_before.get(excepting)
    excepted_after = flat_after.get(excepting)
    if excepted_before is None or excepted_after is None:
        problems.append(
            f"`{'.'.join(excepting)}` is absent from a leg "
            f"({excepted_before!r} vs {excepted_after!r}) — an artifact that cannot say which "
            "side of the change it is cannot be either side of it"
        )
    elif excepted_before == excepted_after:
        problems.append(
            f"both legs have `{'.'.join(excepting)}` = {excepted_before!r} — this compares a "
            "configuration against itself and would report no movement with no error"
        )

    unpaired = set(before.by_id) ^ set(after.by_id)
    if unpaired:
        problems.append(
            f"the legs do not cover the same questions ({len(unpaired)} unpaired: "
            f"{sorted(unpaired)[:5]}) — rows pair on `id`, which is why a frozen set may never be "
            "reworded or renumbered"
        )
    return problems


def compare(before: Leg, after: Leg) -> Comparison:
    """Paired rank movement over the answerable questions, in id order."""
    after_by_id = after.by_id
    moved: list[Movement] = []
    unchanged = 0
    for row in sorted(before.rows, key=lambda item: item.id):
        if row.kind == NO_ANSWER:
            continue
        was, now = rank_of(row), rank_of(after_by_id[row.id])
        if was == now:
            unchanged += 1
        else:
            moved.append(Movement(id=row.id, kind=row.kind, before=was, after=now))
    return Comparison(moved=tuple(moved), unchanged=unchanged)


def report(
    comparison: Comparison, *, sign: bool, before: Leg, after: Leg, excepting: tuple[str, ...]
) -> str:
    """Which leg was which, then the counts.

    The legs are named because **nothing else in the output or the artifact records them**, and
    transposing `--before` and `--after` inverts the verdict without changing anything else: the
    identity check can only require that the excepted key *differs*, never which value is the
    baseline, since the tool is not told what the change under test is. `eval.header`'s own
    docstring gives the reason this matters — "a before file and an after file are otherwise
    indistinguishable on inspection".
    """
    key = ".".join(excepting)
    lines = [
        f"before                 {before.path}   ({key} = {_excepted(before, excepting)!r})",
        f"after                  {after.path}   ({key} = {_excepted(after, excepting)!r})",
        "",
        f"answerable questions   {comparison.answerable}",
        f"improved               {len(comparison.improved)}",
        f"regressed              {len(comparison.regressed)}",
        f"unchanged              {comparison.unchanged}",
    ]
    if sign:
        verdict = "PASS" if comparison.gate_passes() else "FAIL"
        lines.append(
            f"sign test p            {comparison.sign_test_p():.4f}   {verdict} at {ALPHA}"
        )
    lines.append("")
    for label, moves in (("improved", comparison.improved), ("regressed", comparison.regressed)):
        if moves:
            lines.append(f"{label}:")
            lines.extend(f"  {move.render()}" for move in moves)
    if not comparison.moved:
        lines.append("nothing moved.")
    return "\n".join(lines)


def _json_rank(value: float) -> int | None:
    """A miss as `null`: JSON has no infinity, and a reader must not see it as a finite rank."""
    return None if value == MISS else int(value)


def as_dict(
    comparison: Comparison, *, sign: bool, before: Leg, after: Leg, excepting: tuple[str, ...]
) -> dict[str, Any]:
    """The artifact records what was asked for, and `sign_test_p` only when it was.

    Not cosmetic. 2d's screen is pre-registered as having **no p-value** — its criterion is
    deliberately looser than the gate's and its numbers may not be cited as evidence in either
    direction. A p-value sitting in the screen's own artifact is how it gets quoted anyway, by
    someone reading the file a week later with none of that context.
    """
    written: dict[str, Any] = {
        "excepting": ".".join(excepting),
        "before": {"path": str(before.path), "value": _excepted(before, excepting)},
        "after": {"path": str(after.path), "value": _excepted(after, excepting)},
        "answerable": comparison.answerable,
        "improved": len(comparison.improved),
        "regressed": len(comparison.regressed),
        "unchanged": comparison.unchanged,
        "screen_passes": comparison.screen_passes,
        "moved": [
            {
                "id": move.id,
                "kind": move.kind,
                "before": _json_rank(move.before),
                "after": _json_rank(move.after),
            }
            for move in comparison.moved
        ],
    }
    if sign:
        written["sign_test_p"] = comparison.sign_test_p()
        written["gate_passes"] = comparison.gate_passes()
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="two_leg_gate", description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument(
        "--excepting",
        default=".".join(INJECTION_KEY),
        help="dotted header path the two legs may differ on (default: %(default)s)",
    )
    parser.add_argument(
        "--sign-test",
        action="store_true",
        help="also report the exact one-sided sign test — the gate at 2f, never the screen",
    )
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    excepting = tuple(str(args.excepting).split("."))
    try:
        before, after = read_leg(args.before), read_leg(args.after)
    except (OSError, ValueError, PinakesError) as exc:
        # `ValueError` covers `json.JSONDecodeError`, which is what a leg truncated by an
        # interrupted eval run raises — `read_outcomes` only refuses a file that parses.
        # Exit 3, never 1. A 2f driver branching on the exit code would otherwise read a mistyped
        # path or an eval run truncated mid-write as "the screen returned no-go" and discard a
        # 46-minute rebuild pair on the strength of it.
        print(f"could not read a leg: {exc}", file=sys.stderr)
        return 3
    problems = check_identity(before, after, excepting=excepting)
    if problems:
        print("refusing to compare:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    comparison = compare(before, after)
    print(report(comparison, sign=args.sign_test, before=before, after=after, excepting=excepting))
    if args.json is not None:
        written = as_dict(
            comparison, sign=args.sign_test, before=before, after=after, excepting=excepting
        )
        args.json.write_text(json.dumps(written, indent=2) + "\n", encoding="utf-8")
    # **Which criterion the exit code answers is chosen by `--sign-test`.** Without it, the
    # screen's (more improvements than regressions); with it, the gate's (p < ALPHA). One exit code
    # that always answered the screen's would print `FAIL at 0.05` and exit 0 on the very run that
    # licenses the irreversible schema bump.
    passed = comparison.gate_passes() if args.sign_test else comparison.screen_passes
    return 0 if passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
