"""One projection of a traversal result into rows, shared by every surface that returns them.

`pnk links --json` and `pinakes_links` answer the same question and had, until this module, two
hand-written copies of the same dict literals. They had already diverged: the MCP `frontier` carried
a `distance` the CLI's did not, `scored_by_query` reached only one of them, and `unresolved` dropped
the `kb_id` that `neighbours` and `frontier` both carried. Nothing failed, because nothing compared
them — two independently plausible shapes for one documented payload.

So the shape lives here once, and `tests/test_graph_present.py` pins the key sets. A surface may add
a key of its own on top (the CLI adds none; MCP adds `reachable`, which is a fact about the *server*
and means nothing on a command line) — it may not quietly drop one.
"""

from typing import Any

from pinakes.graph.provider import DocumentProvider
from pinakes.graph.traverse import FrontierEntry, Neighbour, Result, Unresolved

NEIGHBOUR_KEYS = frozenset(
    {"kb_id", "doc_id", "rel", "direction", "distance", "score", "scored_by_query", "terminal"}
)
"""Every key on a neighbour row, `title` excepted — it is present only for a local document, and
absent rather than null, because a cross-KB title is not something this index could ever know."""

FRONTIER_KEYS = frozenset({"kb_id", "doc_id", "rel", "reason", "distance"})
UNRESOLVED_KEYS = frozenset({"kb_id", "doc_id", "rel", "reason"})

ARROWS = {"out": "->", "in": "<-", "both": "<->"}
UNKNOWN_ARROW = "?"
"""How a direction renders for a person.

Every value the provider can emit is named, and the fallback is deliberately *not* `<->`: an
`unknown` direction rendered as "written from both ends" would be the strongest claim the output can
make, produced by the one value that means nothing was established. Lives here rather than inline in
`run_links` so the mapping — including the fallback, which no fixture can reach through a real
provider — can be asserted directly.
"""


def arrow(direction: str) -> str:
    return ARROWS.get(direction, UNKNOWN_ARROW)


def neighbour_row(neighbour: Neighbour, *, provider: DocumentProvider) -> dict[str, Any]:
    """One neighbour, as both surfaces return it.

    `direction` is looked up by `(node, rel)` — the same granularity as the row itself — so a node
    reached by two relations reports each one's own direction rather than the first one's.
    """
    kb_id, doc_id = neighbour.node_key
    row: dict[str, Any] = {
        "kb_id": kb_id,
        "doc_id": doc_id,
        "rel": neighbour.rel,
        # `unknown` rather than `both` on the fallback: every emitted neighbour came from a
        # candidate this provider already recorded, so the default is unreachable — and an
        # unreachable branch should not default to the strongest claim the payload can make.
        "direction": provider.directions.get((neighbour.node_key, neighbour.rel), "unknown"),
        "distance": neighbour.distance,
        "score": round(neighbour.score, 4),
        # Which scale `score` is on. With a query, a neighbour with no local chunks to embed falls
        # back to its edge weight, which is on a different scale entirely from a cosine — so the
        # number alone cannot be compared across rows, and this flag is how a caller knows that
        # before sorting by it. The list is already returned in rank order; re-sorting by `score`
        # is the mistake this field exists to make visible.
        "scored_by_query": neighbour.scored_by_query,
        "terminal": neighbour.terminal,
    }
    title = provider.title(kb_id, doc_id)
    if title is not None:
        row["title"] = title
    return row


def frontier_row(entry: FrontierEntry) -> dict[str, Any]:
    return {
        "kb_id": entry.node_key[0],
        "doc_id": entry.node_key[1],
        "rel": entry.rel,
        "reason": entry.reason,
        "distance": entry.distance,
    }


def unresolved_row(entry: Unresolved) -> dict[str, Any]:
    """`kb_id` is always the local KB — `provider.unresolved` will not claim anything about
    another KB's documents — and it is written out anyway, so three lists read as one shape."""
    return {
        "kb_id": entry.node_key[0],
        "doc_id": entry.node_key[1],
        "rel": entry.rel,
        "reason": entry.reason,
    }


def payload(result: Result, *, provider: DocumentProvider, document: str) -> dict[str, Any]:
    """The whole traversal answer, minus whatever a surface adds of its own."""
    return {
        "document": document,
        "neighbours": [neighbour_row(n, provider=provider) for n in result.neighbours],
        "frontier": [frontier_row(entry) for entry in result.frontier],
        "unresolved": [unresolved_row(entry) for entry in result.unresolved],
        "truncated": sorted(result.truncated),
    }


def is_filtered(*, rel: str | None, direction: str, depth: int) -> bool:
    """Whether the caller narrowed the walk — a `rel`, one direction, or no hops at all.

    An empty result means two different things, and the difference is the whole hint: a document
    with no links at all, or a document whose links this call excluded. `pinakes_links` said
    *"No links from here — search instead"* for both, so asking `direction="out"` on a document
    whose only link is inbound told an agent to stop traversing a graph it was standing in.
    """
    return rel is not None or direction != "both" or depth < 1
