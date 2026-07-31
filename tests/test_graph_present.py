"""The traversal payload's shape, and the fields both surfaces had left unasserted.

Written after a review mutated eight fields of the `pinakes_links` payload — `direction`,
`scored_by_query`, the `round()`, the whole `title` block, `unresolved`, `truncated`,
`suggested_next`, the frontier's `distance` — and watched all eight survive the full 887-test suite.
Every field here is one of those: a constant a defect could freeze without anything noticing.

The key sets are written as **literals**, never imported from `present`. A test that reads the same
source it checks passes when that source drops a key, which is the whole failure it exists to catch.
"""

import sqlite3
from pathlib import Path
from typing import Any, cast

import pytest
from test_serve import author_link, doc_id_of, make_kb

from pinakes import store
from pinakes.errors import TraversalError
from pinakes.graph import present
from pinakes.graph.provider import DocumentProvider, document_key
from pinakes.graph.traverse import (
    FrontierEntry,
    Neighbour,
    NodeKey,
    Result,
    Unresolved,
    traverse,
)
from pinakes.ids import parse_doc_id, parse_kb_id
from pinakes.manifest import load

NEIGHBOUR_KEYS = {
    "kb_id",
    "doc_id",
    "rel",
    "direction",
    "distance",
    "score",
    "scored_by_query",
    "terminal",
}
FRONTIER_KEYS = {"kb_id", "doc_id", "rel", "reason", "distance"}
UNRESOLVED_KEYS = {"kb_id", "doc_id", "rel", "reason"}

# Parsed at import, so a mistyped one is a collection error rather than a test that quietly asserts
# nothing. Hand-writing a ULID has now produced a wrong one four times in this work — `O` and `I`
# are not in Crockford's alphabet, and 25 characters looks exactly like 26. A malformed target is
# rejected at sync, so the link simply never reaches the index and the assertion runs against [].
ABSENT_KB = str(parse_kb_id("01KYD0000000000000ABSENTKB"))
ABSENT_DOC = str(parse_doc_id("01KYD000000000000000ABSENT"))


@pytest.fixture
def reciprocal(tmp_path: Path) -> Path:
    """`a --related--> b`, and `b --cites--> a` written from the other end.

    The second link is what made the direction defect visible: asking about `a`, the `cites` row is
    an **inbound** edge — someone else wrote it — and keying directions by node alone reported it as
    outbound, i.e. as `a` citing `b` when the citation runs the other way.
    """
    root = make_kb(
        tmp_path / "reciprocal",
        name="reciprocal",
        documents={
            "a.md": "# Retrieval\n\nHybrid retrieval fuses lexical and dense candidates.\n",
            "b.md": "# Ranking\n\nRanking is what a reranker does.\n",
            "c.md": "# Sourdough\n\nSourdough needs a patient starter.\n",
        },
    )
    kb_id = load(root).kb.id
    author_link(root, "a.md", f"pnk://{kb_id}/{doc_id_of(root, 'b.md')}", "related")
    author_link(root, "b.md", f"pnk://{kb_id}/{doc_id_of(root, 'a.md')}", "cites")
    return root


def _payload(
    root: Path,
    source: str,
    *,
    depth: int = 1,
    direction: str = "both",
    rel: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """The CLI's own path: build a provider, traverse, project — without going through argparse."""
    manifest = load(root)
    connection: sqlite3.Connection = store.connect_ro(manifest.index_path)
    try:
        scores: dict[str, float] = {}
        if query is not None:
            from pinakes.embed import load_backend
            from pinakes.graph.provider import score_documents

            scores = score_documents(
                connection,
                load_backend(manifest.embedding, offline=True),
                query,
                dim=manifest.embedding.dim,
            )
        provider = DocumentProvider(
            connection, local_kb=manifest.kb.id, direction=direction, rel=rel, scores=scores
        )
        result = traverse(
            provider,
            document_key(str(manifest.kb.id), doc_id_of(root, source)),
            depth=depth,
            adjacent_k=manifest.retrieval.adjacent_k,
            query=query,
        )
        return present.payload(result, provider=provider, document=doc_id_of(root, source))
    finally:
        connection.close()


def test_direction_is_per_relation_not_per_node(reciprocal: Path) -> None:
    """Both rows point at the same document; only one of them is outbound.

    Keyed by node, the first edge seen won and `cites` inherited `out` — the payload then asserted
    that this document cites the other, which is backwards. Nothing failed, on either surface.
    """
    rows = {row["rel"]: row for row in _payload(reciprocal, "a.md")["neighbours"]}

    assert rows["related"]["direction"] == "out", "a.md wrote this one"
    assert rows["cites"]["direction"] == "in", "b.md wrote this one — it points back"
    assert rows["related"]["doc_id"] == rows["cites"]["doc_id"], "same node, two relations"


def test_one_relation_written_from_both_ends_is_both(tmp_path: Path) -> None:
    """Not "whichever query ran first" — two people wrote the same relation from either side."""
    root = make_kb(
        tmp_path / "mutual",
        name="mutual",
        documents={"a.md": "# One\n\nRetrieval.\n", "b.md": "# Two\n\nRanking.\n"},
    )
    kb_id = load(root).kb.id
    author_link(root, "a.md", f"pnk://{kb_id}/{doc_id_of(root, 'b.md')}", "related")
    author_link(root, "b.md", f"pnk://{kb_id}/{doc_id_of(root, 'a.md')}", "related")

    rows = _payload(root, "a.md")["neighbours"]
    assert [row["direction"] for row in rows] == ["both"]


def test_a_direction_does_not_change_with_depth(tmp_path: Path) -> None:
    """A row's direction must not depend on how far the walk was allowed to go.

    `directions` accumulates across the whole walk, so merging `both` across *expansions* let an
    edge found while expanding an unrelated parent rewrite a row already emitted from the start.
    With `t --cites--> a`, `a --related--> m` and `m --cites--> t`, expanding `m` at depth 2 flipped
    the `(t, cites)` row from `in` to `both` — asserting that `a` cites `t`, which nobody wrote.
    Both other direction tests run at depth 1, where the start is the only parent, so neither can
    see this.
    """
    root = make_kb(
        tmp_path / "depths",
        name="depths",
        documents={
            "a.md": "# A\n\nRetrieval.\n",
            "m.md": "# M\n\nRanking.\n",
            "t.md": "# T\n\nSourdough.\n",
        },
    )
    kb_id = load(root).kb.id
    author_link(root, "t.md", f"pnk://{kb_id}/{doc_id_of(root, 'a.md')}", "cites")
    author_link(root, "a.md", f"pnk://{kb_id}/{doc_id_of(root, 'm.md')}", "related")
    author_link(root, "m.md", f"pnk://{kb_id}/{doc_id_of(root, 't.md')}", "cites")

    target = doc_id_of(root, "t.md")
    seen = {
        depth: next(
            row
            for row in _payload(root, "a.md", depth=depth)["neighbours"]
            if row["doc_id"] == target and row["rel"] == "cites"
        )["direction"]
        for depth in (1, 2, 3)
    }
    assert seen == {1: "in", 2: "in", 3: "in"}, f"direction moved with depth: {seen}"


def test_the_projections_key_sets_match_what_the_rows_carry() -> None:
    """`present`'s three constants are documentation until something compares them to a real row.

    All three could be replaced with nonsense and nothing failed — the same "a field with no
    assertion can be a constant" lesson this increment was written about, one level up.
    """
    row = present.neighbour_row(_neighbour(1.0), provider=cast(Any, _StubProvider()))
    assert present.NEIGHBOUR_KEYS == NEIGHBOUR_KEYS == set(row)
    assert present.FRONTIER_KEYS == FRONTIER_KEYS
    assert present.UNRESOLVED_KEYS == UNRESOLVED_KEYS
    assert (
        set(
            present.frontier_row(
                FrontierEntry(node_key=("K", "D"), rel="r", reason="depth", distance=1)
            )
        )
        == present.FRONTIER_KEYS
    )
    assert (
        set(present.unresolved_row(Unresolved(node_key=("K", "D"), rel="r", reason="gone")))
        == present.UNRESOLVED_KEYS
    )


def test_an_unknown_direction_is_refused_rather_than_answered_emptily(reciprocal: Path) -> None:
    """`edges_of` tests `in ("out", "both")` and `in ("in", "both")`, so an unrecognised string ran
    neither query and produced a confident empty answer with a "no links from here" hint."""
    manifest = load(reciprocal)
    connection = store.connect_ro(manifest.index_path)
    try:
        for asked in ("outbound", "OUT", "", "inbound"):
            with pytest.raises(TraversalError) as caught:
                DocumentProvider(connection, local_kb=manifest.kb.id, direction=asked)
            assert caught.value.remedy and "out" in caught.value.remedy
    finally:
        connection.close()


def test_scored_by_query_says_which_scale_the_score_is_on(reciprocal: Path) -> None:
    """False without a query, true with one. The field is what stops a caller comparing a cosine
    against an edge weight, and it could be frozen to either constant undetected."""
    without = _payload(reciprocal, "a.md")["neighbours"]
    assert without and not any(row["scored_by_query"] for row in without)

    with_query = _payload(reciprocal, "a.md", query="ranking")["neighbours"]
    assert with_query and all(row["scored_by_query"] for row in with_query)


def test_a_score_is_rounded_to_four_places(reciprocal: Path) -> None:
    """An unrounded float32 cosine renders as 0.7071067690849304 in JSON — sixteen digits of noise
    on a number whose own measurement error is far larger."""
    rows = _payload(reciprocal, "a.md", query="ranking")["neighbours"]
    for row in rows:
        assert row["score"] == round(row["score"], 4)


def test_a_local_neighbour_carries_a_title_and_a_cross_kb_one_does_not(tmp_path: Path) -> None:
    """Absent rather than null: this index holds a partner's *links*, never its documents, so the
    only title it could offer for one would be invented from an id."""
    root = make_kb(
        tmp_path / "titled",
        name="titled",
        documents={"a.md": "# One\n\nRetrieval.\n", "b.md": "# Two\n\nRanking.\n"},
    )
    kb_id = load(root).kb.id
    author_link(root, "a.md", f"pnk://{kb_id}/{doc_id_of(root, 'b.md')}", "related")
    author_link(root, "a.md", f"pnk://{ABSENT_KB}/{ABSENT_DOC}", "counterpart")

    rows = {row["rel"]: row for row in _payload(root, "a.md")["neighbours"]}
    local = rows["related"]
    assert local["title"] and local["title"] != local["doc_id"], "a title, not an id wearing one"
    assert "title" not in rows["counterpart"], "absent, never null and never guessed"


def test_an_unresolved_row_survives_and_carries_the_local_kb_id(tmp_path: Path) -> None:
    """Returned, never dropped, is the contract — and `unresolved` could be frozen to `[]`."""
    root = make_kb(
        tmp_path / "dangling",
        name="dangling",
        documents={"a.md": "# One\n\nRetrieval.\n"},
    )
    kb_id = str(load(root).kb.id)
    author_link(root, "a.md", f"pnk://{kb_id}/{ABSENT_DOC}", "related")

    payload = _payload(root, "a.md")
    assert payload["neighbours"] == [], "a missing local target is not a neighbour"
    assert len(payload["unresolved"]) == 1
    entry = payload["unresolved"][0]
    assert set(entry) == UNRESOLVED_KEYS
    assert entry["kb_id"] == kb_id and entry["rel"] == "related" and entry["reason"]


def test_every_row_shape_is_pinned_by_literal(reciprocal: Path) -> None:
    """The three shapes, written out. `present` exists so both surfaces share them; this is what
    stops the shared copy drifting from what the docs promise."""
    payload = _payload(reciprocal, "a.md", depth=3)

    assert set(payload) == {"document", "neighbours", "frontier", "unresolved", "truncated"}
    assert payload["neighbours"], "an empty list would satisfy the loop below without checking it"
    for row in payload["neighbours"]:
        assert NEIGHBOUR_KEYS <= set(row) <= NEIGHBOUR_KEYS | {"title"}
    # The frontier and unresolved shapes are pinned directly in
    # `test_the_projections_key_sets_match_what_the_rows_carry` — this fixture produces neither,
    # and a `for` over an empty list asserts nothing at all.


def test_the_two_surfaces_project_the_same_keys(reciprocal: Path) -> None:
    """`pnk links --json` and `pinakes_links` answered the same question through two hand-written
    copies of the same dict literals, and had already drifted: the MCP frontier carried a
    `distance` the CLI's did not, and `scored_by_query` reached only one of them."""
    from pinakes.serve import Server

    cli_payload = _payload(reciprocal, "a.md")
    made = Server([reciprocal])
    try:
        mcp_payload = made.links(doc_id_of(reciprocal, "a.md"))
    finally:
        made.close()

    # MCP adds four keys of its own, every one a fact about *this server*, not about the KB.
    assert set(mcp_payload) - set(cli_payload) == {
        "kb",
        "kb_id",
        "confidence",
        "suggested_next",
    }
    cli_rows = {row["rel"]: row for row in cli_payload["neighbours"]}
    for row in mcp_payload["neighbours"]:
        assert set(row) - set(cli_rows[row["rel"]]) <= {"reachable", "reason", "fetch_with"}
        assert set(cli_rows[row["rel"]]) <= set(row), "the CLI must not carry a key MCP dropped"


def test_is_filtered_names_every_argument_that_can_empty_an_answer() -> None:
    """Each of the three narrows the walk, and an empty answer caused by one of them must not be
    reported as "this document has no links"."""
    assert not present.is_filtered(rel=None, direction="both", depth=1)
    assert present.is_filtered(rel="cites", direction="both", depth=1)
    assert present.is_filtered(rel=None, direction="out", depth=1)
    assert present.is_filtered(rel=None, direction="in", depth=1)
    assert present.is_filtered(rel=None, direction="both", depth=0)


# --- The projection itself, over hand-built results -------------------------------------------
#
# Three fields survived a mutation pass against the KB-backed tests above, for the same reason each
# time: a fixture too tidy to distinguish. The fake embedding backend produces exact 1.0 cosines, so
# dropping `round()` changed nothing; no fixture hit a response cap, so `truncated` could be frozen
# empty; and no frontier entry sat past distance 1. Building the dataclasses directly removes the
# fixture from the question entirely.


class _StubProvider:
    """Enough of `DocumentProvider` for the projection: a title lookup and a direction map."""

    def __init__(self) -> None:
        self.directions: dict[tuple[NodeKey, str], str] = {}

    def title(self, kb_id: str, doc_id: str) -> str | None:
        return None


def _neighbour(score: float) -> Neighbour:
    return Neighbour(
        node_key=("KB", "DOC"),
        rel="related",
        distance=1,
        score=score,
        scored_by_query=True,
        terminal=False,
    )


def test_a_score_is_rounded_even_when_the_raw_value_is_long() -> None:
    """A float32 cosine renders as 0.7071067690849304 in JSON. The KB-backed test above cannot
    catch a dropped `round()` — the fake backend's vectors are orthonormal, so every cosine is
    already exactly 1.0 and rounding is a no-op on it."""
    row = present.neighbour_row(_neighbour(0.7071067690849304), provider=cast(Any, _StubProvider()))
    assert row["score"] == 0.7071


def test_truncated_reports_the_caps_that_bit() -> None:
    """Frozen to `[]`, a caller reading a cut-short answer would believe it was the whole graph."""
    result = Result(neighbours=(_neighbour(1.0),), truncated=frozenset({"rows", "tokens"}))
    payload = present.payload(result, provider=cast(Any, _StubProvider()), document="DOC")
    assert payload["truncated"] == ["rows", "tokens"], "sorted, so the output is reproducible"


def test_a_frontier_entry_carries_the_distance_it_was_found_at() -> None:
    """`distance` is how a caller knows whether a `depth`-stopped entry is one hop away or three —
    i.e. whether raising `depth` is worth the tokens. Frozen to 0, every entry looks adjacent."""
    result = Result(
        frontier=(FrontierEntry(node_key=("KB", "FAR"), rel="next", reason="depth", distance=3),)
    )
    payload = present.payload(result, provider=cast(Any, _StubProvider()), document="DOC")
    assert payload["frontier"][0]["distance"] == 3
