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

from pinakes.eval import NO_ANSWER, OutcomeRow

#: The one header key the injection experiment's two legs are *meant* to differ on. Expressed as a
#: path into the header so the block it sits in is still compared key by key: excepting the whole
#: `chunking` block would hide a rechunk, which is the very thing this tool checks for.
INJECTION_KEY = ("chunking", "metadata")

MISS = math.inf
"""Where a question the run did not answer sorts: after every rank a run did answer at."""


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


def report(comparison: Comparison, *, sign: bool) -> str:
    lines = [
        f"answerable questions   {comparison.answerable}",
        f"improved               {len(comparison.improved)}",
        f"regressed              {len(comparison.regressed)}",
        f"unchanged              {comparison.unchanged}",
    ]
    if sign:
        p = sign_test(len(comparison.improved), len(comparison.regressed))
        lines.append(f"sign test p            {p:.4f}   {'PASS' if p < 0.05 else 'FAIL'} at 0.05")
    lines.append("")
    for label, moves in (("improved", comparison.improved), ("regressed", comparison.regressed)):
        if moves:
            lines.append(f"{label}:")
            lines.extend(f"  {move.render()}" for move in moves)
    if not comparison.moved:
        lines.append("nothing moved.")
    return "\n".join(lines)


def as_dict(comparison: Comparison) -> dict[str, Any]:
    return {
        "answerable": comparison.answerable,
        "improved": len(comparison.improved),
        "regressed": len(comparison.regressed),
        "unchanged": comparison.unchanged,
        "sign_test_p": sign_test(len(comparison.improved), len(comparison.regressed)),
        "screen_passes": comparison.screen_passes,
        "moved": [
            {"id": move.id, "kind": move.kind, "before": move.before, "after": move.after}
            for move in comparison.moved
        ],
    }


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

    before, after = read_leg(args.before), read_leg(args.after)
    excepting = tuple(str(args.excepting).split("."))
    problems = check_identity(before, after, excepting=excepting)
    if problems:
        print("refusing to compare:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    comparison = compare(before, after)
    print(report(comparison, sign=args.sign_test))
    if args.json is not None:
        args.json.write_text(json.dumps(as_dict(comparison), indent=2) + "\n", encoding="utf-8")
    return 0 if comparison.screen_passes else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
