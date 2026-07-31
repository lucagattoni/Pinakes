"""The document edge provider — L3's core over the `links` table (docs/DESIGN.md §6.2).

**One query per hop, in a Python loop, never a recursive CTE.** The CTE is shorter and is the wrong
tool: the caps live in the core, and a recursive query would have to re-implement depth, fan-out and
dedup in SQL to honour them — three rules in two places, which is how they drift apart. Per-hop also
keeps the cost legible: `depth` queries, each bounded by the fan-out already applied to the frontier
of the previous hop.

**Every neighbour is a document.** Tag, directory and heading nodes have no `doc_id` and never reach
this surface — not in this release and not after it. That is precisely what lets a later release add
a whole structural graph without touching this contract, and why there is no filter here to flip.

**`kb_id` is the KB ULID, never a name.** Three namespaces exist — `[kb] name`, which the docs
promise is free to rename, `[[links.kb]] name`, which is machine-local, and the ULID, which is
canonical. Only the ULID is dereferenceable and portable, for the same reason a `pnk://` URI carries
no alias.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from pinakes.errors import TraversalError
from pinakes.graph.traverse import Candidate, NodeKey, Unresolved
from pinakes.ids import DocId, KbId

if TYPE_CHECKING:  # pragma: no cover
    from pinakes.embed import EmbeddingBackend

AUTHORED_WEIGHT = 2.0
"""Every edge this provider serves was written by a person.

A `reverse-scan` row is as hand-authored as a `sidecar` one — the human who wrote it just happened
to be on the other side. So both carry the same weight, and ranking without a query falls through to
the deterministic `node_key` tie-break rather than to an invented distinction.
"""

DIRECTIONS = ("out", "in", "both")
"""The only three a caller may ask for — **enforced**, not merely documented.

`edges_of` tests `direction in ("out", "both")` and `("in", "both")`, so an unrecognised string ran
neither query and returned a confident empty answer. The CLI's `argparse` `choices` caught it there;
the MCP surface, which is the one an untrusted model types into, had nothing.
"""


@dataclass(frozen=True, slots=True)
class Edge:
    """One row of `links`, oriented from the node that was asked about."""

    kb_id: str
    doc_id: str
    rel: str
    direction: str


def document_key(kb_id: str, doc_id: str) -> NodeKey:
    """`(kb_id, doc_id)` — the provider's half of L3's opaque key contract."""
    return (kb_id, doc_id)


def edges_of(
    connection: sqlite3.Connection,
    key: NodeKey,
    *,
    direction: str = "both",
    rel: str | None = None,
) -> list[Edge]:
    """Every link touching `key`, one query per direction asked for.

    Outbound and inbound are separate statements rather than a `UNION`, because the two need
    different columns projected and the union would have to invent a direction column anyway — and
    then a reader could no longer see which half produced a row.
    """
    kb_id, doc_id = key
    found: list[Edge] = []
    clause = " AND rel = ?" if rel is not None else ""
    arguments: tuple[str, ...] = (kb_id, doc_id) + ((rel,) if rel is not None else ())

    if direction in ("out", "both"):
        found.extend(
            Edge(str(row[0]), str(row[1]), str(row[2]), "out")
            for row in connection.execute(
                "SELECT dst_kb_id, dst_doc_id, rel FROM links "
                f"WHERE src_kb_id = ? AND src_doc_id = ?{clause}",
                arguments,
            )
        )
    if direction in ("in", "both"):
        found.extend(
            Edge(str(row[0]), str(row[1]), str(row[2]), "in")
            for row in connection.execute(
                "SELECT src_kb_id, src_doc_id, rel FROM links "
                f"WHERE dst_kb_id = ? AND dst_doc_id = ?{clause}",
                arguments,
            )
        )
    return found


class DocumentProvider:
    """`EdgeProvider` over `links`, for document nodes."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        local_kb: KbId,
        direction: str = "both",
        rel: str | None = None,
        scores: dict[str, float] | None = None,
    ) -> None:
        if direction not in DIRECTIONS:
            raise TraversalError(
                f"{direction!r} is not a direction.",
                remedy=f"Use one of: {', '.join(DIRECTIONS)}.",
            )
        self.connection = connection
        self.local_kb = str(local_kb)
        self.direction = direction
        self.rel = rel
        self.scores = scores or {}
        self.queries = 0
        """How many statements this provider has issued — read by the test that pins one per hop."""

        self._titles: dict[str, str] = {
            str(row[0]): str(row[1] or "")
            for row in connection.execute("SELECT id, title FROM documents WHERE state = 'active'")
        }
        self.directions: dict[tuple[NodeKey, str], str] = {}
        """Which way each neighbour was reached — the core does not carry it, and the surface
        needs it.

        **Keyed by `(node, rel)`**, not by node alone: keyed by node, the first edge seen won and
        every later row for that node inherited its direction, so given `a --related--> b` and
        `b --cites--> a`, asking about `a` reported the citation as running *from* `a`.

        **First expansion wins, and `both` is decided inside one expansion only.** Direction is
        relative to the node being expanded, so merging across expansions asserts something nobody
        wrote: with `t --cites--> a`, `a --related--> m` and `m --cites--> t`, expanding `m` at
        depth 2 would flip the already-emitted `(t, cites)` row from `in` to `both` — claiming `a`
        cites `t`. A row's direction would then change with `--depth`. Within a single expansion a
        `both` is real: two people wrote the same relation from either end of the same pair.

        The residual imprecision is inherited from L4 and left deliberately: a row at distance ≥ 2
        reports its direction relative to the **first** parent that reached it, because `Neighbour`
        does not carry which parent that was. Every distance-1 row — the only one most callers
        read, and the only one `depth=1` can produce — is exact, since the start is the sole parent.
        """

    def title(self, kb_id: str, doc_id: str) -> str | None:
        """A title for a **local** document only.

        Absent for a cross-KB neighbour, and deliberately not guessed at: this index holds the
        partner's *links*, never its documents, so the only title it could offer would be one
        invented from an id. A caller that needs it can dereference the `pnk://` URI in the KB that
        owns the document.
        """
        return self._titles.get(doc_id) if kb_id == self.local_kb else None

    def neighbours(self, node_key: NodeKey, *, query: str | None) -> Sequence[Candidate]:
        self.queries += 1
        candidates: list[Candidate] = []
        # Scoped to this one expansion. Merged into `self.directions` below with `setdefault`, so a
        # later hop can never rewrite the direction of a row an earlier hop already emitted.
        here: dict[tuple[NodeKey, str], str] = {}
        for edge in edges_of(self.connection, node_key, direction=self.direction, rel=self.rel):
            if edge.kb_id == self.local_kb and edge.doc_id not in self._titles:
                # A local target this KB does not have is **not** a neighbour — there is no
                # document there to be one. It comes back through `unresolved` instead, and the two
                # lists stay disjoint: a caller seeing the same id in both would have to guess
                # which one was lying.
                continue
            target = document_key(edge.kb_id, edge.doc_id)
            row_key = (target, edge.rel)
            seen = here.get(row_key)
            here[row_key] = edge.direction if seen is None or seen == edge.direction else "both"
            candidates.append(
                Candidate(
                    node_key=target,
                    rel=edge.rel,
                    weight=AUTHORED_WEIGHT,
                    score=self.scores.get(edge.doc_id) if query is not None else None,
                    # Terminal iff it lives in another KB. The reason is partiality, not
                    # emptiness: this index holds a partner's links *that target us*, never the
                    # partner's internal ones, so a second hop would return a slice of that KB's
                    # graph no caller could tell apart from the whole.
                    terminal=edge.kb_id != self.local_kb,
                    tokens=_tokens(edge, self.title(edge.kb_id, edge.doc_id)),
                )
            )
        for row_key, resolved in here.items():
            self.directions.setdefault(row_key, resolved)
        return candidates

    def unresolved(self, node_key: NodeKey) -> Sequence[Unresolved]:
        """Local links whose target document this KB does not have.

        Only ever local: a *cross-KB* target cannot be checked from here without the other KB, and
        reporting one as unresolved on that basis would be asserting something this index has no
        standing to know.
        """
        missing: list[Unresolved] = []
        for edge in edges_of(self.connection, node_key, direction=self.direction, rel=self.rel):
            if edge.kb_id == self.local_kb and edge.doc_id not in self._titles:
                missing.append(
                    Unresolved(
                        node_key=document_key(edge.kb_id, edge.doc_id),
                        rel=edge.rel,
                        reason="no active document with that id in this KB",
                    )
                )
        return missing


def _tokens(edge: Edge, title: str | None) -> int:
    """A neighbour row's cost, roughly. Two ULIDs, a relation and a title, at four chars a token."""
    return (len(edge.kb_id) + len(edge.doc_id) + len(edge.rel) + len(title or "")) // 4 + 1


def score_documents(
    connection: sqlite3.Connection,
    backend: "EmbeddingBackend",
    query: str,
    *,
    dim: int,
) -> dict[str, float]:
    """Each document's best chunk cosine against `query`.

    Document-level rather than chunk-level because that is the granularity this surface returns: a
    document is as relevant as its most relevant part, which is the rule `search` already applies
    when it ranks passages and reports the documents they came from.

    Scores *every* chunk in the KB, which is the honest cost of ranking neighbours by similarity
    when no document vector exists. At the scale this tool is built for that is one matrix multiply;
    if it ever stops being one, the fix is a document vector, not a smaller answer.
    """
    from pinakes import store

    chunk_ids, matrix = store.load_vectors(connection, dim=dim)
    if not chunk_ids:
        return {}
    embedded = backend.embed([query])
    if embedded.shape[0] == 0:  # pragma: no cover — a backend returning nothing for one query
        return {}

    similarities = _normalise(matrix) @ _normalise(embedded)[0]
    owner = {
        int(row[0]): str(row[1]) for row in connection.execute("SELECT id, doc_id FROM chunks")
    }
    best: dict[str, float] = {}
    for position, chunk_id in enumerate(chunk_ids):
        doc_id = owner.get(int(chunk_id))
        if doc_id is None:
            continue
        value = float(similarities[position])
        if value > best.get(doc_id, float("-inf")):
            best[doc_id] = value
    return best


def _normalise(
    matrix: "np.ndarray[Any, np.dtype[np.float32]]",
) -> "np.ndarray[Any, np.dtype[np.float32]]":
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return np.divide(matrix, np.where(norms == 0, 1, norms))


def resolve_document(connection: sqlite3.Connection, reference: str) -> DocId | None:
    """A document ULID from either a ULID or a path — what a person types on a command line.

    A path is accepted because `pnk search` prints paths, and requiring a ULID would mean copying
    one out of `--json` to ask about a result you can already see.
    """
    from pinakes.errors import InvalidIdError
    from pinakes.ids import parse_doc_id

    try:
        candidate = parse_doc_id(reference)
    except InvalidIdError:
        candidate = None
    if candidate is not None:
        row = connection.execute(
            "SELECT id FROM documents WHERE id = ? AND state = 'active'", (str(candidate),)
        ).fetchone()
        return DocId(str(row[0])) if row else None

    row = connection.execute(
        "SELECT id FROM documents WHERE path = ? AND state = 'active'", (reference,)
    ).fetchone()
    return DocId(str(row[0])) if row else None
