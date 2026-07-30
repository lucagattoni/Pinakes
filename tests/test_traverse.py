"""The traversal core, against fixture graphs.

Fixtures rather than a database, because the shapes that matter here are laborious to build in
SQLite and trivial to state directly: a hub with more spokes than the cap, a cycle, a neighbour
whose target resolves to nothing, a provider that returns its candidates in the *worst* order.

The last one is the point of several tests. A fixture that happens to return candidates
best-first cannot tell rank-then-truncate from truncate-then-rank, so every fan-out fixture here
returns them deliberately reversed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pinakes.graph.traverse import (
    DEPTH,
    FANOUT,
    MAX_ADJACENT_K,
    MAX_DEPTH,
    MAX_ROWS,
    REASONS,
    ROWS,
    TERMINAL,
    TOKENS,
    Candidate,
    NodeKey,
    Result,
    Unresolved,
    traverse,
)


class Graph:
    """An edge provider over a literal adjacency map."""

    def __init__(
        self,
        edges: Mapping[NodeKey, Sequence[Candidate]],
        *,
        dangling: Mapping[NodeKey, Sequence[Unresolved]] | None = None,
    ) -> None:
        self.edges: Mapping[NodeKey, Sequence[Candidate]] = edges
        self.dangling: Mapping[NodeKey, Sequence[Unresolved]] = dangling or {}
        self.asked: list[NodeKey] = []

    def neighbours(self, node_key: NodeKey, *, query: str | None) -> Sequence[Candidate]:
        self.asked.append(node_key)
        return self.edges.get(node_key, ())

    def unresolved(self, node_key: NodeKey) -> Sequence[Unresolved]:
        return self.dangling.get(node_key, ())


def node(name: str) -> NodeKey:
    return ("kb", name)


def candidate(
    name: str,
    *,
    rel: str = "related",
    weight: float = 1.0,
    score: float | None = None,
    terminal: bool = False,
    tokens: int = 0,
) -> Candidate:
    """Explicit keywords, not a `**kwargs` bag — the bag needed a type-ignore, and a helper that
    has to silence the checker about what it is building is one typo from building the wrong thing.
    """
    return Candidate(
        node_key=node(name),
        rel=rel,
        weight=weight,
        score=score,
        terminal=terminal,
        tokens=tokens,
    )


def names(result: Result) -> list[str]:
    return [neighbour.node_key[1] for neighbour in result.neighbours]


def reasons(result: Result) -> dict[str, str]:
    return {entry.node_key[1]: entry.reason for entry in result.frontier}


# --- Depth -----------------------------------------------------------------------------------


def test_depth_counts_one_hop_per_candidate() -> None:
    """Renamed from `..._counts_logical_hops_not_physical_edges`, which it could not hold.

    "Logical hops" is a property of what a *provider* offers: it composes `document → tag →
    document` into one candidate, and the core never sees the hub. This fixture has no hub in it,
    so no mutation could fail this and pass `test_depth_is_clamped_to_the_server_maximum` — it was
    a second copy of that test wearing a larger claim. What the core actually owes is counted here:
    one hop per candidate it is handed.
    """
    graph = Graph(
        {
            node("a"): [candidate("b")],  # one logical hop, however many edges it composed
            node("b"): [candidate("c")],
        }
    )

    assert names(traverse(graph, node("a"), depth=1)) == ["b"]
    assert names(traverse(graph, node("a"), depth=2)) == ["b", "c"]


def test_depth_is_clamped_to_the_server_maximum() -> None:
    chain = {node(str(index)): [candidate(str(index + 1))] for index in range(20)}
    result = traverse(Graph(chain), node("0"), depth=99)

    assert max(neighbour.distance for neighbour in result.neighbours) == MAX_DEPTH


def test_depth_zero_returns_nothing_rather_than_everything() -> None:
    """A clamp that read `0` as "unset" would turn the tightest request into the widest."""
    graph = Graph({node("a"): [candidate("b")]})
    assert traverse(graph, node("a"), depth=0).neighbours == ()


# --- Fan-out ---------------------------------------------------------------------------------


def test_fanout_keeps_the_highest_ranked_neighbours_not_the_first_k() -> None:
    """The fixture returns candidates worst-first on purpose. Truncate-then-rank keeps `low`;
    rank-then-truncate keeps `high`, and only a reversed fixture can tell them apart."""
    graph = Graph(
        {
            node("a"): [
                candidate("low", weight=0.1),
                candidate("mid", weight=0.5),
                candidate("high", weight=0.9),
            ]
        }
    )

    result = traverse(graph, node("a"), depth=1, adjacent_k=1)

    assert names(result) == ["high"]
    # `high` is on the frontier too, for `depth` — it was kept and then not expanded, which is a
    # different fact about a different node. Asserting only the dropped pair would have passed
    # against an implementation that never recorded the depth stop at all.
    assert reasons(result) == {"mid": FANOUT, "low": FANOUT, "high": DEPTH}


def test_fanout_is_clamped_to_the_server_maximum() -> None:
    wide = [candidate(f"n{index:03}", weight=index) for index in range(200)]
    # `max_rows` raised deliberately: at its default of 50 the row cap bites before the fan-out cap
    # and the assertion would be measuring the wrong bound — which is exactly the confusion having
    # two independent caps invites.
    result = traverse(
        Graph({node("a"): wide}), node("a"), depth=1, adjacent_k=10_000, max_rows=1000
    )

    assert len(result.neighbours) == MAX_ADJACENT_K


def test_ranking_without_a_query_uses_edge_weight_then_distance() -> None:
    graph = Graph(
        {
            node("a"): [candidate("weak", weight=0.2), candidate("strong", weight=2.0)],
        }
    )
    assert names(traverse(graph, node("a"), depth=1)) == ["strong", "weak"]


def test_ranking_with_a_query_uses_provider_supplied_similarity() -> None:
    """The core does not embed. Similarity arrives per candidate, and with a query it *overrides*
    edge weight — a fixture where the two disagree is the only way to see which one won."""
    graph = Graph(
        {
            node("a"): [
                candidate("heavy-but-irrelevant", weight=9.0, score=0.1),
                candidate("light-but-relevant", weight=0.1, score=0.9),
            ]
        }
    )

    assert names(traverse(graph, node("a"), depth=1, query="q")) == [
        "light-but-relevant",
        "heavy-but-irrelevant",
    ]
    # ...and without the query, the other order. Same fixture, both rankings.
    assert names(traverse(graph, node("a"), depth=1)) == [
        "heavy-but-irrelevant",
        "light-but-relevant",
    ]


def test_ranking_is_totally_ordered_so_a_capped_answer_is_reproducible() -> None:
    """Ties broken on the opaque `node_key`, which is total. Without it the *contents* of a capped
    answer could differ between identical calls — worse than a merely surprising order."""
    tied = [candidate(f"n{index}", weight=1.0) for index in range(10)]
    first = traverse(Graph({node("a"): tied}), node("a"), depth=1, adjacent_k=3)
    second = traverse(Graph({node("a"): list(reversed(tied))}), node("a"), depth=1, adjacent_k=3)

    assert names(first) == names(second)


# --- The frontier ------------------------------------------------------------------------------


def test_a_frontier_entry_carries_the_reason_it_was_not_expanded() -> None:
    """All five reasons, each from its own deterministic scenario.

    One fixture producing all five at once would need `rows` and `tokens` to bite in a fixed order
    within a single expansion, which is a property of the loop rather than of either cap — so the
    assertion would have had to hedge, and an assertion with an `or` in it is not asserting.
    """
    # terminal — the provider says so
    terminal = Graph({node("a"): [candidate("t", terminal=True)]})
    assert reasons(traverse(terminal, node("a"), depth=1)) == {"t": TERMINAL}

    # depth — kept, then the hop limit
    depth = Graph({node("a"): [candidate("b")], node("b"): [candidate("c")]})
    assert reasons(traverse(depth, node("a"), depth=1)) == {"b": DEPTH}

    # fanout — ranked out
    fanout = Graph({node("a"): [candidate("keep", weight=9.0), candidate("drop", weight=0.1)]})
    assert reasons(traverse(fanout, node("a"), depth=1, adjacent_k=1)) == {
        "keep": DEPTH,
        "drop": FANOUT,
    }

    # rows — free to carry, but too many of them. The frontier shares the same `max_rows` budget,
    # so a request for 2 rows gets 2 explanations, not one per dropped candidate.
    rows = Graph({node("a"): [candidate(f"n{index}", weight=1.0) for index in range(5)]})
    got = reasons(traverse(rows, node("a"), depth=1, max_rows=2, token_budget=10_000))
    assert sum(1 for reason in got.values() if reason == ROWS) == 2

    # tokens — few of them, but each expensive
    tokens = Graph(
        {node("a"): [candidate(f"n{index}", weight=1.0, tokens=100) for index in range(5)]}
    )
    got = reasons(traverse(tokens, node("a"), depth=1, max_rows=100, token_budget=150))
    assert sum(1 for reason in got.values() if reason == TOKENS) == 4


def test_the_five_reasons_are_exactly_what_the_vocabulary_declares() -> None:
    """A vocabulary with an unreachable member is wrong about something, and one with a member the
    code never emits is worse — a caller writes a branch that can never run."""
    assert set(REASONS) == {TERMINAL, DEPTH, FANOUT, ROWS, TOKENS}
    assert REASONS.index(TERMINAL) < REASONS.index(FANOUT), "precedence is the order"


def test_terminal_outranks_fanout_when_both_apply() -> None:
    """A cross-KB neighbour dropped by the fan-out cap reports `terminal`, because retrying with a
    larger cap cannot reach past it. A caller told `fanout` retries a hop that can never succeed."""
    graph = Graph(
        {
            node("a"): [
                candidate("kept", weight=9.0),
                candidate("dropped-and-terminal", weight=0.1, terminal=True),
            ]
        }
    )

    result = traverse(graph, node("a"), depth=1, adjacent_k=1)

    assert reasons(result)["dropped-and-terminal"] == TERMINAL


def test_a_cross_kb_neighbour_is_frontier_terminal_at_every_depth() -> None:
    """**The fixture contains the back-links that make the hop walkable**, in both directions.

    Without them this test passes against an implementation with no suppression at all — the walk
    would stop because there was nothing to walk to, and the assertion could not tell that apart
    from a policy. The reason to stop is not emptiness but partiality: an index holds a partner's
    links that target *us*, never the partner's internal ones, so a second hop returns a slice of
    someone else's graph that no caller could distinguish from the whole.
    """
    foreign = ("partner", "doc")
    graph = Graph(
        {
            node("a"): [Candidate(node_key=foreign, rel="counterpart", terminal=True, weight=1.0)],
            # Walkable in both directions, and richly so — if the suppression were removed these
            # would appear as neighbours at distance 2.
            foreign: [candidate("back-one"), candidate("back-two")],
        }
    )

    for depth in (1, 2, 3):
        result = traverse(graph, node("a"), depth=depth)
        assert [n.node_key for n in result.neighbours] == [foreign], f"depth={depth}"
        assert reasons(result) == {"doc": TERMINAL}
        assert "back-one" not in names(result), "the walk expanded past a terminal neighbour"


def test_a_terminal_neighbour_is_never_asked_for_its_own_neighbours() -> None:
    """Stronger than "it did not appear in the answer": the provider is never even consulted, so
    the suppression cannot be an accident of ranking."""
    foreign = ("partner", "doc")
    graph = Graph(
        {
            node("a"): [Candidate(node_key=foreign, rel="counterpart", terminal=True)],
            foreign: [candidate("back")],
        }
    )

    traverse(graph, node("a"), depth=3)

    assert foreign not in graph.asked


# --- Dedup and cycles ---------------------------------------------------------------------------


def test_a_hub_is_expanded_once_globally() -> None:
    """Once globally, not once per path. On a shared-tag graph that is the difference between a
    bounded walk and a combinatorial one."""
    graph = Graph(
        {
            node("a"): [candidate("b"), candidate("c")],
            node("b"): [candidate("hub")],
            node("c"): [candidate("hub")],
            node("hub"): [candidate("d")],
        }
    )

    traverse(graph, node("a"), depth=3)

    assert graph.asked.count(node("hub")) == 1


def test_a_cycle_terminates() -> None:
    graph = Graph(
        {
            node("a"): [candidate("b")],
            node("b"): [candidate("c")],
            node("c"): [candidate("a"), candidate("b")],
        }
    )

    result = traverse(graph, node("a"), depth=MAX_DEPTH)

    assert "a" not in names(result), "the walk returned to its own start"
    assert len(names(result)) == len(set(names(result)))


def test_the_start_node_is_never_returned_as_its_own_neighbour() -> None:
    graph = Graph({node("a"): [candidate("a"), candidate("b")]})
    assert names(traverse(graph, node("a"), depth=1)) == ["b"]


# --- The two response caps -----------------------------------------------------------------------


def test_the_token_budget_sets_truncated_independently_of_the_row_cap() -> None:
    """Independently, because they are different problems with different fixes — ask for fewer
    neighbours, or ask for less text. A single boolean would leave a caller guessing which."""
    expensive = [candidate(f"n{index}", weight=1.0, tokens=100) for index in range(10)]
    graph = Graph({node("a"): expensive})

    tokens_only = traverse(
        graph, node("a"), depth=1, adjacent_k=MAX_ADJACENT_K, max_rows=100, token_budget=250
    )
    assert tokens_only.truncated == {TOKENS}
    assert len(tokens_only.neighbours) == 2

    cheap = [candidate(f"n{index}", weight=1.0, tokens=0) for index in range(10)]
    rows_only = traverse(
        Graph({node("a"): cheap}),
        node("a"),
        depth=1,
        adjacent_k=MAX_ADJACENT_K,
        max_rows=3,
        token_budget=10_000,
    )
    assert rows_only.truncated == {ROWS}
    assert len(rows_only.neighbours) == 3


def test_an_answer_within_both_caps_reports_neither() -> None:
    """A `truncated` that is always set says nothing at all."""
    graph = Graph({node("a"): [candidate("b", tokens=1)]})
    assert traverse(graph, node("a"), depth=1).truncated == frozenset()


# --- Unresolved -----------------------------------------------------------------------------------


def test_unresolved_targets_survive_to_the_caller() -> None:
    """A link whose target no longer exists is a fact about the graph. Dropping it silently is the
    incomplete answer this project refuses — and the caller cannot ask about what it never saw."""
    missing = Unresolved(node_key=("kb", "ghost"), rel="related", reason="no such document")
    graph = Graph({node("a"): [candidate("b")]}, dangling={node("a"): [missing]})

    result = traverse(graph, node("a"), depth=1)

    assert result.unresolved == (missing,)
    assert names(result) == ["b"], "an unresolved target must not become a neighbour"


def test_unresolved_accumulates_across_hops() -> None:
    graph = Graph(
        {node("a"): [candidate("b")], node("b"): [candidate("c")]},
        dangling={
            node("a"): [Unresolved(("kb", "g1"), "related", "gone")],
            node("b"): [Unresolved(("kb", "g2"), "related", "gone")],
        },
    )

    result = traverse(graph, node("a"), depth=2)

    assert {entry.node_key[1] for entry in result.unresolved} == {"g1", "g2"}


def test_a_walk_that_finds_nothing_is_empty_rather_than_an_error() -> None:
    assert traverse(Graph({}), node("lonely"), depth=3) == traverse(Graph({}), node("lonely"))
    assert traverse(Graph({}), node("lonely")).neighbours == ()


# --- What the review found -----------------------------------------------------------------


def test_the_frontier_is_capped_like_the_rest_of_the_response() -> None:
    """It is the response's largest component and was bounded by nothing.

    Measured before the fix: a caller asking for **one** row received a thousand frontier entries —
    and this is the payload an agent parses. The module docstring claimed the response was
    "double-capped"; only half of it was.
    """
    wide = Graph(
        {node("a"): [candidate(f"n{index:04}", weight=float(index)) for index in range(1000)]}
    )

    result = traverse(wide, node("a"), depth=1, adjacent_k=10_000, max_rows=1, token_budget=1)

    assert len(result.neighbours) <= 1
    assert len(result.frontier) <= 1
    assert ROWS in result.truncated


def test_a_frontier_entry_is_retracted_when_the_node_is_reached_later() -> None:
    """A node dropped by fan-out at one hop and reached at another kept claiming `fanout` — while
    sitting in `neighbours` and having been expanded. A caller reading the frontier for "retry with
    a bigger adjacent_k" got a false positive on a node already in its answer."""
    graph = Graph(
        {
            node("a"): [candidate("b", weight=9.0), candidate("x", weight=0.1)],
            node("b"): [candidate("x", weight=5.0)],
            node("x"): [candidate("z")],
        }
    )

    result = traverse(graph, node("a"), depth=3, adjacent_k=1)

    assert "x" in names(result)
    assert reasons(result).get("x") != FANOUT, "a reached node still claims it was dropped"


def test_an_accepted_node_may_still_be_on_the_frontier_for_terminal_or_depth() -> None:
    """The other half of the contract, so the retraction above cannot be over-applied: `terminal`
    and `depth` describe *accepted* nodes deliberately not expanded, which is exactly what a
    caller needs to know about a node it does have."""
    graph = Graph({node("a"): [candidate("t", terminal=True)]})
    result = traverse(graph, node("a"), depth=3)

    assert "t" in names(result)
    assert reasons(result)["t"] == TERMINAL


def test_the_response_caps_are_clamped_server_side_too() -> None:
    """ "Every bound is clamped" was true of two of the four. A caller passing `max_rows=10**9` got
    3,660 rows and an empty `truncated` — and once this is reachable over MCP, the caller supplying
    it is the untrusted party."""
    wide = {
        node(f"{level}-{index}"): [
            candidate(f"{level + 1}-{index}_{spoke}", weight=float(spoke)) for spoke in range(60)
        ]
        for level in range(3)
        for index in range(60)
    }
    wide[node("0-0")] = [candidate(f"1-{spoke}", weight=float(spoke)) for spoke in range(60)]

    result = traverse(
        Graph(wide),
        node("0-0"),
        depth=99,
        adjacent_k=10_000,
        max_rows=10**9,
        token_budget=10**9,
    )

    assert len(result.neighbours) <= MAX_ROWS
    assert ROWS in result.truncated


def test_terminal_outranks_the_response_caps_as_well_as_fanout() -> None:
    """The stated precedence is `terminal, depth, fanout, rows, tokens`. Before this, the row and
    token checks ran before terminality was ever consulted, so a terminal neighbour dropped by the
    row cap reported `rows` — inviting a retry with a smaller request that cannot help."""
    graph = Graph(
        {
            node("a"): [
                candidate("keep", weight=9.0),
                candidate("term", weight=0.5, terminal=True),
            ]
        }
    )

    result = traverse(graph, node("a"), depth=1, max_rows=1, token_budget=10_000)

    assert names(result) == ["keep"]
    assert reasons(result)["term"] == TERMINAL


def test_two_relations_to_one_target_are_two_rows() -> None:
    """Row dedup is per **edge**, not per node — the plan and APPROACH both say visited-*edge*.
    Node-level dedup silently dropped the second relation, in a module whose contract is that a
    fact about the graph is returned rather than dropped."""
    graph = Graph(
        {
            node("a"): [
                candidate("t", rel="supersedes", weight=9.0),
                candidate("t", rel="cites", weight=8.0),
            ]
        }
    )

    result = traverse(graph, node("a"), depth=1)

    assert {(row.node_key[1], row.rel) for row in result.neighbours} == {
        ("t", "supersedes"),
        ("t", "cites"),
    }


def test_a_node_reachable_two_ways_is_still_expanded_once() -> None:
    """...and edge-level row dedup must not undo the node-level expansion dedup that bounds the
    walk."""
    graph = Graph(
        {
            node("a"): [candidate("t", rel="one"), candidate("t", rel="two")],
            node("t"): [candidate("z")],
        }
    )

    traverse(graph, node("a"), depth=3)

    assert graph.asked.count(node("t")) == 1


def test_the_row_cap_keeps_the_highest_ranked_across_the_whole_hop() -> None:
    """Ranking was per parent while the row cap was global, so a high-ranked neighbour behind a
    low-ranked parent was dropped for a worthless one in front of it — the same mistake as
    truncate-then-rank, one level up."""
    graph = Graph(
        {
            node("a"): [candidate("p1", weight=1.0), candidate("p2", weight=0.9)],
            node("p1"): [candidate("junk", weight=0.01)],
            node("p2"): [candidate("gold", weight=99.0)],
        }
    )

    result = traverse(graph, node("a"), depth=2, max_rows=3)

    assert "gold" in names(result), "a top-ranked neighbour lost to a worthless one"


def test_a_score_says_whether_it_came_from_the_query() -> None:
    """Without this the payload's `score` was a similarity or an edge weight with nothing on the
    wire to say which, so two responses could not be compared."""
    graph = Graph({node("a"): [candidate("b", weight=2.0, score=0.5)]})

    assert traverse(graph, node("a"), depth=1).neighbours[0].scored_by_query is False
    assert traverse(graph, node("a"), depth=1, query="q").neighbours[0].scored_by_query is True


def test_adjacent_k_zero_means_no_fanout_rather_than_one() -> None:
    """`max(1, ...)` made "no fan-out" unaskable — the inverse of the reasoning `depth=0` gets one
    screen away."""
    graph = Graph({node("a"): [candidate("b")]})
    assert traverse(graph, node("a"), depth=1, adjacent_k=0).neighbours == ()
