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
MAX_ROWS = 200
DEFAULT_TOKEN_BUDGET = 4000
MAX_TOKEN_BUDGET = 20_000
_FRONTIER_HEADROOM = 4
"""How many `max_rows` of frontier entries to hold before the response is assembled.

More than one, so the ordering at the end has something to choose between; bounded, so a wide graph
cannot make the walk hold tens of thousands of entries it will discard.
"""
"""Ceilings on the response's own two caps.

They exist for the same reason the depth and fan-out ceilings do, and were missing while three
documents claimed "every bound is clamped server-side": once this is reachable over MCP, the caller
supplying `max_rows` is the untrusted party, and `max_rows=10**9` is one token away from a caller
who mistyped.
"""


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
    scored_by_query: bool
    """Whether `score` is a similarity or the edge's own weight.

    Without this a payload's `score` was one or the other with nothing on the wire to say which,
    and a caller comparing two responses would be comparing different quantities.
    """

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


def _rank(candidates: Sequence[Candidate], *, query: str | None) -> list[Candidate]:
    """Highest first. **With** a query, by provider similarity; without, by edge weight.

    The final tie-break is the opaque `node_key`, which is total — so the order is fully
    determined, and the *contents* of a capped answer cannot differ between identical calls.

    There is deliberately no `distance` term. An earlier version had one and a docstring claiming a
    nearer neighbour of equal weight ranked higher; `_rank` is called with the candidates of a
    single hop, so `distance` was constant inside every sort and the term was dead. Removing it and
    running the suite changed nothing, which is how it was found.
    """
    if query is not None:
        return sorted(candidates, key=lambda c: (-(c.score or 0.0), c.node_key))
    return sorted(candidates, key=lambda c: (-c.weight, c.node_key))


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
    """Walk outward from `start`, bounded four ways. **Every** bound is clamped server-side.

    All four, not two: an earlier version clamped only `depth` and `adjacent_k` while three
    documents claimed otherwise, and a caller passing `max_rows=10**9` got 3,660 rows and an empty
    `truncated`. The caller supplying these is the untrusted party once this is exposed over MCP.
    """
    depth = max(0, min(depth, MAX_DEPTH))
    adjacent_k = max(0, min(adjacent_k, MAX_ADJACENT_K))
    max_rows = max(0, min(max_rows, MAX_ROWS))
    token_budget = max(0, min(token_budget, MAX_TOKEN_BUDGET))

    neighbours: list[Neighbour] = []
    unresolved: list[Unresolved] = []
    truncated: set[str] = set()

    # Expanded or accepted. Seeded with the start, so a cycle back to it terminates. A hub reached
    # by three documents is expanded once *globally* — on a shared-tag graph that is the difference
    # between a bounded walk and a combinatorial one.
    visited: set[NodeKey] = {start}
    emitted: set[tuple[NodeKey, str]] = set()
    """Rows already returned, keyed by **(node, relation)**.

    Node-level row dedup silently dropped a second, distinct relation to the same target — an
    `a --supersedes--> t` and an `a --cites--> t` collapsed to one, with the second vanishing with
    no trace, in a module whose contract is that a fact about the graph is returned rather than
    dropped. Expansion still dedups per *node*; only the rows are per edge.
    """

    spent = 0
    frontier: dict[tuple[NodeKey, str], FrontierEntry] = {}

    def note(candidate: Candidate, reason: str, distance: int) -> None:
        key = (candidate.node_key, candidate.rel)
        if key in frontier:
            return
        if len(frontier) >= _FRONTIER_HEADROOM * max_rows:
            # Bounded in memory too, not only in the response: a 500-wide graph at depth 3 drops
            # tens of thousands of candidates, and holding one entry each to then discard almost
            # all of them is work nobody asked for. The headroom is what lets the ordering below
            # choose *which* entries survive rather than keeping whichever arrived first.
            truncated.add(ROWS)
            return
        frontier[key] = FrontierEntry(
            node_key=candidate.node_key, rel=candidate.rel, reason=reason, distance=distance
        )

    current: list[NodeKey] = [start]
    for distance in range(1, depth + 1):
        # Per parent: rank, then apply the *per-expansion* fan-out cap.
        pooled: list[Candidate] = []
        for node in current:
            unresolved.extend(provider.unresolved(node))
            ranked = _rank(list(provider.neighbours(node, query=query)), query=query)
            kept, dropped = ranked[:adjacent_k], ranked[adjacent_k:]
            for candidate in dropped:
                # `terminal` outranks every other reason: no larger cap and no greater depth can
                # reach past it, so any other answer invites a retry that cannot succeed.
                note(candidate, TERMINAL if candidate.terminal else FANOUT, distance)
            pooled.extend(kept)

        # Then rank the whole hop **together**, before the response caps bite. Ranking only per
        # parent let the row cap truncate by parent order, so a high-ranked neighbour behind a
        # low-ranked parent was dropped for a worthless one in front of it — the same mistake as
        # truncate-then-rank, one level up.
        following: list[NodeKey] = []
        for candidate in _rank(pooled, query=query):
            if candidate.node_key == start:
                # Explicit, now that row dedup is per *edge* rather than per node: a cycle back to
                # the start would otherwise be emitted as a neighbour of itself, because its
                # `(node, rel)` pair had never been seen before.
                continue
            row_key = (candidate.node_key, candidate.rel)
            if row_key in emitted:
                continue
            if len(neighbours) >= max_rows:
                truncated.add(ROWS)
                note(candidate, TERMINAL if candidate.terminal else ROWS, distance)
                continue
            if spent + candidate.tokens > token_budget:
                truncated.add(TOKENS)
                note(candidate, TERMINAL if candidate.terminal else TOKENS, distance)
                continue

            emitted.add(row_key)
            spent += candidate.tokens
            neighbours.append(
                Neighbour(
                    node_key=candidate.node_key,
                    rel=candidate.rel,
                    distance=distance,
                    score=(
                        candidate.score
                        if query is not None and candidate.score is not None
                        else candidate.weight
                    ),
                    # `query is not None`, not merely "the provider supplied a score": a
                    # provider is free to attach one always, and the question a caller is asking is
                    # whether *this call* ranked by similarity.
                    scored_by_query=query is not None and candidate.score is not None,
                    terminal=candidate.terminal,
                    weight=candidate.weight,
                )
            )
            if candidate.terminal:
                note(candidate, TERMINAL, distance)
            elif distance == depth:
                note(candidate, DEPTH, distance)
            elif candidate.node_key not in visited:
                visited.add(candidate.node_key)
                following.append(candidate.node_key)
        current = following
        if not current:
            break

    # Retract stale drops. A node dropped by fan-out at one hop and reached at another was left
    # claiming `fanout` while sitting in `neighbours` and having been expanded — so a caller
    # reading the frontier for "retry with a bigger adjacent_k" got a false positive on a node
    # already in its answer. `terminal` and `depth` are kept: those describe *accepted* nodes that
    # were deliberately not expanded, which is the contract.
    reached = {neighbour.node_key for neighbour in neighbours}
    kept_entries = [
        entry
        for entry in frontier.values()
        if entry.reason in (TERMINAL, DEPTH) or entry.node_key not in reached
    ]

    # **Entries about nodes you did *not* get come first.** The frontier's job is to say what is
    # missing and why; an entry about a node already in `neighbours` says only "this is the edge of
    # what you asked for". Capping without this ordering let the `depth` notes of *accepted* nodes
    # fill the whole budget and crowd out every `rows` note — so a caller asking for 2 of 5
    # neighbours was told nothing at all about the 3 it did not get.
    kept_entries.sort(key=lambda entry: (entry.node_key in reached, entry.distance))
    if len(kept_entries) > max_rows:
        truncated.add(ROWS)
    final = tuple(kept_entries[:max_rows])

    return Result(
        neighbours=tuple(neighbours),
        frontier=final,
        unresolved=tuple(unresolved),
        truncated=frozenset(truncated),
    )
