"""A traversal asked for more than it may have gets less, and is told so — a gate, not a comment.

**Why this is a gate and not only a test.** The caps in `graph/traverse.py` are the only thing
standing between an agent's `depth=99, adjacent_k=10000` and a walk that returns most of a KB. A
unit test proves the clamp works today; a gate that runs the *shipped* artifact at absurd values on
every commit proves nobody has quietly turned a `min()` into a pass-through since. The distinction
matters here because the caps are cheap to weaken by accident and expensive to notice: the failure
is a slow query and an enormous answer, not an exception.

The predicate, stated rather than left as a name — it drives the core with a caller asking for
`depth=99` and `adjacent_k=10_000` against a fixture graph wide and deep enough that an uncapped
walk would visibly exceed both, then fails if:

* any neighbour's `distance` exceeds `MAX_DEPTH`;
* more than `MAX_ADJACENT_K` neighbours came back from one expansion;
* a cap bit and `truncated` did not say so — a silent truncation being the one outcome worse than a
  loud one, since the caller then believes it has the whole answer.

The fixture is built here rather than imported from the tests: this must keep working if the test
suite is refactored, and a gate that shares a fixture with the thing it is gating is one edit away
from vacuity.
"""

import sys
from collections.abc import Sequence

from pinakes.graph.traverse import (
    MAX_ADJACENT_K,
    MAX_DEPTH,
    ROWS,
    TOKENS,
    Candidate,
    NodeKey,
    Unresolved,
    traverse,
)

WIDTH = 500
"""Spokes per node — comfortably above `MAX_ADJACENT_K`, so the fan-out cap has to bite."""

CHAIN = 12
"""Levels — comfortably above `MAX_DEPTH`, so the depth cap has to bite."""

DOCUMENTED_MAX_DEPTH = 3
DOCUMENTED_MAX_ADJACENT_K = 64
"""What `docs/MANIFEST.md` and `docs/DESIGN.md` promise, written here as literals on purpose.

Raising a cap is allowed; raising it *silently* is not. These are the second copy that makes the
change show up.
"""

ROW_CAP = 100
"""Below what a depth- and fan-out-capped walk still yields (3 hops x 64), so the *row* cap bites
too — otherwise the `truncated` check never runs and the gate silently tests two things, not
three. Measured: an unbounded-row walk here returns 192."""


class WideDeepGraph:
    """Every node has `width` neighbours, and the chain runs `CHAIN` deep.

    `width` is a parameter so each probe can put the caps it is *not* testing out of reach —
    otherwise the first cap to bite hides every other.
    """

    def __init__(self, *, width: int, tokens: int = 0) -> None:
        self.width = width
        self.tokens = tokens

    def neighbours(self, node_key: NodeKey, *, query: str | None) -> Sequence[Candidate]:
        level = int(node_key[1].split("-")[0])
        if level >= CHAIN:
            return ()
        return [
            Candidate(
                node_key=("kb", f"{level + 1}-{level}_{index}"),
                rel="related",
                weight=float(index),
                tokens=self.tokens,
            )
            for index in range(self.width)
        ]

    def unresolved(self, node_key: NodeKey) -> Sequence[Unresolved]:
        return ()


def main(argv: list[str] | None = None) -> int:
    """Three probes, not one run.

    A single run cannot test all three caps: whichever bites first hides the others. Measured
    directly — with a tight row cap in force, deleting the *depth* clamp entirely changed nothing
    observable, because the walk was stopped by rows long before depth mattered. A gate that cannot
    detect the removal of the guard it names is not gating it.
    """
    import argparse

    parser = argparse.ArgumentParser(description="the traversal-cap gate")
    parser.add_argument(
        "--expect-depth",
        type=int,
        default=DOCUMENTED_MAX_DEPTH,
        help="the depth cap the docs promise; exists so CI can drive this gate into failure",
    )
    parser.add_argument("--expect-fanout", type=int, default=DOCUMENTED_MAX_ADJACENT_K)
    args = parser.parse_args(argv)

    problems: list[str] = []
    lines: list[str] = []

    # **The documented numbers, as literals.** Importing `MAX_DEPTH` and comparing the walk against
    # it means the gate compares the code with itself: raising the cap to 10 moved the walk to 10
    # and the gate still passed, while `docs/MANIFEST.md` went on promising 64. A gate that reads
    # its threshold from the thing it is gating measures nothing.
    if (args.expect_depth, args.expect_fanout) != (MAX_DEPTH, MAX_ADJACENT_K):
        problems.append(
            f"the caps moved: depth {MAX_DEPTH} (docs say {args.expect_depth}), fan-out "
            f"{MAX_ADJACENT_K} (docs say {args.expect_fanout}) — update docs/MANIFEST.md "
            f"and docs/DESIGN.md in the same change, or this is a silent contract break"
        )

    # Probe 1 — depth, over a narrow graph so neither other cap can bite first.
    narrow = traverse(
        WideDeepGraph(width=2),
        ("kb", "0-0"),
        depth=99,
        adjacent_k=10_000,
        max_rows=10_000,
        token_budget=10_000_000,
    )
    deepest = max((n.distance for n in narrow.neighbours), default=0)
    lines.append(f"depth: asked 99 over a 2-wide {CHAIN}-deep graph, reached {deepest}")
    if deepest != MAX_DEPTH:
        # An equality, not an upper bound. Every check here was one-sided, so a `traverse()` that
        # returned an empty `Result` satisfied all three and the gate exited 0 — a gate whose
        # fixture yields nothing passes vacuously, which is the failure its own docstring is an
        # essay about.
        problems.append(f"depth reached {deepest}, and the cap is {MAX_DEPTH}")

    # Probe 2 — fan-out, one hop, rows and tokens deliberately out of the way.
    wide = traverse(
        WideDeepGraph(width=WIDTH),
        ("kb", "0-0"),
        depth=1,
        adjacent_k=10_000,
        max_rows=10_000,
        token_budget=10_000_000,
    )
    per_hop = len(wide.neighbours)
    lines.append(f"fan-out: asked 10000 over a {WIDTH}-wide graph, got {per_hop}")
    if per_hop != MAX_ADJACENT_K:
        problems.append(f"one expansion returned {per_hop}, and the cap is {MAX_ADJACENT_K}")

    # Probe 3 — the row cap, and that it says so. A silent truncation is the one outcome worse
    # than a loud one: the caller then believes it has the whole answer.
    capped = traverse(
        WideDeepGraph(width=WIDTH),
        ("kb", "0-0"),
        depth=99,
        adjacent_k=10_000,
        max_rows=ROW_CAP,
        token_budget=10_000_000,
    )
    lines.append(
        f"rows: capped at {ROW_CAP}, got {len(capped.neighbours)}, "
        f"truncated={sorted(capped.truncated) or 'none'}"
    )
    if len(capped.neighbours) != ROW_CAP:
        problems.append(f"{len(capped.neighbours)} rows came back, and the cap is {ROW_CAP}")
    if ROWS not in capped.truncated:
        problems.append("the row cap bit and `truncated` did not say so")

    # Probe 4 — the token budget. Every fixture above costs zero tokens, so removing the token cap
    # entirely passed this gate; only the unit tests caught it, and this gate exists precisely for
    # what the unit tests might one day stop covering.
    expensive = traverse(
        WideDeepGraph(width=WIDTH, tokens=100),
        ("kb", "0-0"),
        depth=1,
        adjacent_k=10_000,
        max_rows=10_000,
        token_budget=250,
    )
    lines.append(
        f"tokens: budget 250 at 100 each, got {len(expensive.neighbours)}, "
        f"truncated={sorted(expensive.truncated) or 'none'}"
    )
    if len(expensive.neighbours) != 2:
        problems.append(f"{len(expensive.neighbours)} rows fit a 250-token budget at 100 each")
    if TOKENS not in expensive.truncated:
        problems.append("the token budget bit and `truncated` did not say so")

    for line in lines:
        print(f"traversal-cap: {line}")
    for problem in problems:
        print(f"traversal-cap: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
