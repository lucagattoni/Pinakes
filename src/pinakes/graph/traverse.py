"""Bounded graph traversal — the pure half (APPROACH §4A, §5).

No SQLite, no manifest, no I/O. Everything the walk needs arrives through an `EdgeProvider`, which
is what lets this be tested against fixture graphs whose shape would be laborious to build in a
database — a hub with a thousand spokes, a cycle, a neighbour that resolves to nothing.

**Generic over node identity, deliberately.** A candidate carries an opaque `node_key` the provider
defines and totally orders. For documents that is `(kb_id, doc_id)`; for the structural nodes of a
later release it is `(kind, key)`. The core's dedup and tie-breaking use *only* that key, so one
implementation serves both — and the caps below therefore apply to both, rather than a second
expander growing up outside this module's gate.

Two consequences follow from an opaque key, and both have to be said because the key cannot carry
them implicitly:

* **Terminality is a flag the provider sets on a candidate**, never a KB-id comparison in here. The
  core cannot know what a "different KB" is when the key might be `(kind, key)`.
* **A frontier entry carries the `node_key`**, and each surface projects it into its own shape.

**Four things bound a walk, and they are not interchangeable.**

* `depth` — **logical hops**, not physical edges. Composition through a hub node (document → tag →
  document) is one hop, because the hub is transit rather than a destination. Counting physically
  would strand the highest-trust authored edges beyond any usable depth.
* `adjacent_k` — fan-out per expansion, applied **after ranking**. Truncating first and ranking
  after would make the cap select by whatever order the provider happened to return, which is the
  bug this ordering exists to prevent.
* `max_rows` and `token_budget` — the response's own two caps, reported **independently** on
  `truncated`, because "too many neighbours" and "too much text" are different problems with
  different fixes.

**`unresolved` is returned, never dropped.** A link whose target no longer exists is a fact about
the graph, and silently omitting it is the incomplete-answer failure this project refuses.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

NodeKey = tuple[str, ...]
"""An opaque, totally-ordered node identity. The provider defines it; the core only compares."""

TERMINAL = "terminal"
DEPTH = "depth"
FANOUT = "fanout"
ROWS = "rows"
TOKENS = "tokens"

REASONS: tuple[str, ...] = (TERMINAL, DEPTH, FANOUT, ROWS, TOKENS)
"""Why a discovered neighbour was not expanded — and the **precedence order** when several apply.

Five, because five distinct mechanisms stop an expansion and they mean different things to whoever
asked. The precedence is the point of the ordering: a cross-KB neighbour dropped by the fan-out cap
reports `terminal`, not `fanout`, because retrying with a larger cap can never help. A caller that
cannot tell those two apart retries a hop that will never succeed.
"""

DEFAULT_ADJACENT_K = 8
MAX_ADJACENT_K = 64
"""A server-side ceiling on fan-out, whatever a manifest or a caller asks for.

Not a preference — a bound. The traversal-cap gate drives this core with `adjacent_k=10_000` and
needs a number to assert against; without one, "capped" is a claim rather than a check.
"""

DEFAULT_DEPTH = 1
MAX_DEPTH = 3
DEFAULT_MAX_ROWS = 50
DEFAULT_TOKEN_BUDGET = 4000


@dataclass(frozen=True, slots=True)
class Candidate:
    """One neighbour, as the provider describes it."""

    node_key: NodeKey
    rel: str
    weight: float = 1.0
    """The edge's own trust. Ranks neighbours when no query was given."""

    score: float | None = None
    """Similarity to the caller's query, computed **by the provider**.

    The core does not embed and does not know what a query is; it ranks, caps and dedups. That is
    the whole reason this module has no dependencies.
    """

    terminal: bool = False
    """Expanding past this node would show a systematically partial view, so the walk stops here.

    Set by the provider, because only the provider knows why. For a cross-KB neighbour the reason
    is partiality, not emptiness: this index holds a partner's links *that point back at us* and
    never the partner's internal ones, so a second hop would return a slice of that KB's graph no
    caller could distinguish from the whole.
    """

    tokens: int = 0
    """What this row will cost the response, as the provider counts it."""


@dataclass(frozen=True, slots=True)
class Neighbour:
    """A candidate that made it into the answer."""

    node_key: NodeKey
    rel: str
    distance: int
    score: float
    terminal: bool
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class FrontierEntry:
    """A neighbour that was discovered and **not** expanded, and why."""

    node_key: NodeKey
    rel: str
    reason: str
    distance: int


@dataclass(frozen=True, slots=True)
class Unresolved:
    """A link whose target the provider could not resolve — returned, never dropped."""

    node_key: NodeKey
    rel: str
    reason: str


@dataclass(frozen=True, slots=True)
class Result:
    neighbours: tuple[Neighbour, ...] = ()
    frontier: tuple[FrontierEntry, ...] = ()
    unresolved: tuple[Unresolved, ...] = ()
    truncated: frozenset[str] = field(default_factory=frozenset[str])
    """Which caps actually bit — `{"rows"}`, `{"tokens"}`, or both.

    A set rather than a bool, because the two have different remedies: ask for fewer neighbours, or
    ask for less text. Collapsing them would leave a caller guessing which knob to turn.
    """


class EdgeProvider(Protocol):
    """What the core needs from the world. L4 implements this over SQLite."""

    def neighbours(self, node_key: NodeKey, *, query: str | None) -> Sequence[Candidate]:
        """Every candidate one logical hop from `node_key`, in any order.

        Ordering here is deliberately not the provider's business: the core ranks. A provider that
        pre-sorted would make the fan-out cap depend on two ranking rules that could disagree.
        """
        ...

    def unresolved(self, node_key: NodeKey) -> Sequence[Unresolved]:
        """Links from `node_key` whose target does not resolve. Empty for most providers."""
        return ()


def _rank(candidates: Sequence[Candidate], *, distance: int, query: str | None) -> list[Candidate]:
    """Highest first. **With** a query, by provider similarity; without, by edge weight.

    Distance participates in the no-query ordering because a nearer neighbour of equal weight is
    the better answer, and the final tie-break is the opaque `node_key` — which is total, so the
    order is fully determined. An unstable ranking under a cap means the *contents* of an answer
    change between identical calls, which is worse than a merely surprising order.
    """
    if query is not None:
        return sorted(
            candidates,
            key=lambda candidate: (-(candidate.score or 0.0), distance, candidate.node_key),
        )
    return sorted(
        candidates, key=lambda candidate: (-candidate.weight, distance, candidate.node_key)
    )


def traverse(
    provider: EdgeProvider,
    start: NodeKey,
    *,
    depth: int = DEFAULT_DEPTH,
    adjacent_k: int = DEFAULT_ADJACENT_K,
    max_rows: int = DEFAULT_MAX_ROWS,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    query: str | None = None,
) -> Result:
    """Walk outward from `start`, bounded four ways. Every bound is clamped server-side."""
    depth = max(0, min(depth, MAX_DEPTH))
    adjacent_k = max(1, min(adjacent_k, MAX_ADJACENT_K))

    neighbours: list[Neighbour] = []
    frontier: list[FrontierEntry] = []
    unresolved: list[Unresolved] = []
    truncated: set[str] = set()

    # Visited *nodes*, seeded with the start so a cycle back to it terminates. A hub reached by
    # three different documents is expanded once, globally — not once per path, which on a
    # shared-tag graph is the difference between a bounded walk and a combinatorial one.
    visited: set[NodeKey] = {start}
    spent = 0

    frontier_seen: set[tuple[NodeKey, str]] = set()

    def note(candidate: Candidate, reason: str, distance: int) -> None:
        key = (candidate.node_key, candidate.rel)
        if key in frontier_seen:
            return
        frontier_seen.add(key)
        frontier.append(
            FrontierEntry(
                node_key=candidate.node_key, rel=candidate.rel, reason=reason, distance=distance
            )
        )

    current: list[NodeKey] = [start]
    for distance in range(1, depth + 1):
        following: list[NodeKey] = []
        for node in current:
            unresolved.extend(provider.unresolved(node))
            found = list(provider.neighbours(node, query=query))
            ranked = _rank(found, distance=distance, query=query)

            # Rank, *then* truncate. The other order makes the cap select by whatever sequence the
            # provider happened to return — which is exactly the defect the ordering prevents, and
            # the one a test with a deliberately reversed fixture catches.
            kept, dropped = ranked[:adjacent_k], ranked[adjacent_k:]
            for candidate in dropped:
                # `terminal` outranks `fanout`: retrying with a larger cap cannot reach past a
                # terminal node, so telling the caller `fanout` would invite a doomed retry.
                note(candidate, TERMINAL if candidate.terminal else FANOUT, distance)

            for candidate in kept:
                if candidate.node_key in visited:
                    continue
                if len(neighbours) >= max_rows:
                    truncated.add(ROWS)
                    note(candidate, ROWS, distance)
                    continue
                if spent + candidate.tokens > token_budget:
                    # Independently observable from the row cap, and checked independently: a
                    # response can hit one without the other, and a caller needs to know which.
                    truncated.add(TOKENS)
                    note(candidate, TOKENS, distance)
                    continue

                visited.add(candidate.node_key)
                spent += candidate.tokens
                neighbours.append(
                    Neighbour(
                        node_key=candidate.node_key,
                        rel=candidate.rel,
                        distance=distance,
                        score=candidate.score if candidate.score is not None else candidate.weight,
                        terminal=candidate.terminal,
                        weight=candidate.weight,
                    )
                )
                if candidate.terminal:
                    # Terminal at *every* depth, by policy — not because the query comes back
                    # empty. It does not: this index holds a partner's links that target us, so a
                    # second hop from one would return our own documents through a partial view of
                    # someone else's graph.
                    note(candidate, TERMINAL, distance)
                elif distance == depth:
                    note(candidate, DEPTH, distance)
                else:
                    following.append(candidate.node_key)
        current = following
        if not current:
            break

    return Result(
        neighbours=tuple(neighbours),
        frontier=tuple(frontier),
        unresolved=tuple(unresolved),
        truncated=frozenset(truncated),
    )
