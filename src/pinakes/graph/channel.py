"""The expansion channel — RRF's third input, default off (APPROACH §4A, plan G5).

**Default `"off"`, and this module runs only when a manifest says otherwise.** `search` calls it
for `[retrieval] graph_channel = "expand"` and not at all for `"off"`, which is what
`test_off_issues_no_traversal_query` asserts by counting the statements that reach `nodes` and
`edges`. What licenses a different default is `tools/graph_gate.py`, never an argument.

## What it does

Take the fused top-*k* chunks as roots, walk the G3 edge set outward to depth ≤ 2 **logical hops**,
rank what it finds, and hand `search` a third ranking for RRF to fuse. An empty edge set yields an
empty third list, and RRF over `(lexical, vector, [])` is arithmetically identical to RRF over
`(lexical, vector)` — the degradation is exact rather than approximate, which is what
`test_an_empty_edge_set_reproduces_two_list_fusion_exactly` pins.

## Logical hops, and what is free

A hop is a **chunk-or-doc → chunk-or-doc transition**. Membership edges and hub pass-throughs cost
nothing (APPROACH §4A): counted physically, the model's own plumbing — chunk → doc → doc → chunk —
would strand the highest-trust authored edges beyond depth 2, which cannot be the intent. So one
hop from a root chunk `c` in document `D` reaches:

| through | to | costing |
|---|---|---|
| `sibling`, `parent-child` | another chunk | 1 hop |
| a heading hub (`in-section`) | another chunk of `D` | 1 hop |
| `D` (membership, free) then `authored` | another document's chunks (membership, free) | 1 hop |
| `D` (membership, free) then a directory or tag hub | another document's chunks | 1 hop |

The frontier is therefore a set of **chunk** nodes, and every doc, tag, heading and directory node
is transit. That is not a simplification: APPROACH §4A says non-chunk nodes *"carry no content
embedding, pass through by edge weight, and contribute their member chunks … which are then
query-ranked like any others"*, and `doc` is on its list.

## Two ranking rules, because two populations are being ranked

* **Chunk candidates rank by cosine** against the query embedding — the same similarity the vector
  half of the pipeline already computed, handed in rather than recomputed.
* **Non-chunk candidates rank by edge weight**, because they have no embedding to compare. This is
  where `authored`'s frozen 2.0 (decision 13) actually bites: against a `shared-tag` spoke damped
  to 1/degree, a document passes through to its authored neighbours first, every time.

`adjacent_k` caps **every** node's expansion — the chunk's own peers, a heading hub's members, a
document's onward documents, a document's member chunks — applied *after* ranking. Truncating
first would make the cap select by whatever order SQLite happened to return.

## The membership exclusion, at both points

APPROACH §3: *"same-doc chunks reached only through their own document's membership edges are
excluded from the expansion channel's output and never consume its fan-out budget"*, and §4A's
gloss on the same rule: *"contribute their member chunks (minus the root's own document)"*. Two
filters implement it, and both drop candidates **before** the `adjacent_k` cut, which is the half
an implementation forgets:

1. A document never passes through to itself (`D → tag-hub → D`).
2. **A root's own document never contributes member chunks, at any depth.**

Rule 2 reads §4A's *"the root's own document"* over the union of the roots, which is also what
`tools/reachable_ceiling_probe.py` measured — the ceiling that licensed this increment. It costs
nothing a caller wanted: intra-document structure is `sibling`/`parent-child`/`in-section`'s job,
those three kinds are untouched by both filters, and a same-document chunk that is *also* a
sibling, a child or a section-mate is therefore returned. The "only" in APPROACH's sentence is
load-bearing, and `test_a_same_document_chunk_reachable_by_sibling_is_not_excluded` is what keeps
it that way.

## The ranking handed to RRF

`(-cosine, distance, -weight, node_key)` — **cosine first, distance as a tiebreak.**

G5's spec says *"chunk neighbours rank by cosine"* and APPROACH §4A says *"score expanded chunks by
edge weight and link distance"*, so both terms are here and the order between them is a choice.
Distance-first was written first and is **wrong**, for a reason worth recording: the list is cut at
`candidates_per_source`, so with distance as the primary key every one-hop chunk precedes every
two-hop one — and on any corpus where one hop already finds that many chunks, **depth 2 contributes
nothing to the output at all**. The channel would be depth-1 wearing a depth-2 budget, and the
reachability ceiling that licensed this increment was measured at two logical hops
(`plans/20260804_1442-decision-g3-go.md`). Cosine first lets a two-hop chunk compete on merit;
distance still decides where cosine cannot, which is where the graph's own proximity is the only
evidence available.

The final tiebreak is the **node key** (`<doc-ulid>:<ordinal>`), never `chunks.id` — the rowid G1
measured moving between an incremental sync and a `--rebuild`, which is exactly how a channel could
change one golden-set answer without any edge changing.

## Why not `graph.traverse`

That core walks from **one** start and bounds a *response* (rows, tokens); this walks from *k*
roots with one global visited set, and its output is a ranking rather than a payload. Running the
core once per root would give each root its own visited set, and a popular tag would then expand
once per root instead of once globally — the bound that makes traversal survive a real graph. The
two share their bounding *rules*, not their loop.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pinakes.graph import edges as edge_set

DEPTH: Final = 2
"""Logical hops. APPROACH §4A's stage A expands *"breadth-first to depth ≤ 2"*, and G2's
reachability precondition was measured at exactly this budget — a channel walking further than the
ceiling that licensed it would be measuring something the precondition never covered."""

_CHUNK_PEER_KINDS: Final = frozenset({"sibling", "parent-child"})
"""What may reach a chunk directly. `membership` is transit and `authored` is document-level;
reading either here would put a same-document chunk into the chunk-peer population the membership
exclusion exists to keep out — with no filter downstream, because those two filters are about the
*document* path."""

_DOC_HUB_KINDS: Final = frozenset({"co-located", "shared-tag"})


@dataclass(frozen=True, slots=True)
class Reached:
    """One chunk the channel surfaced, and how."""

    chunk_id: int
    """`chunks.id` — the identity `search` fuses on."""

    node_key: str
    """`<doc-ulid>:<ordinal>`, the identity that survives a rebuild."""

    doc_id: str
    distance: int
    weight: float
    """The composed weight of the path that first reached it — the product of both spokes across a
    hub (`edges.compose`), the kind's own weight otherwise."""

    via: tuple[str, ...]
    """The edge kinds along that path, nearest first. Read by `tools/graph_matrix.py` to report
    which kind carried a lifting path: a result carried entirely by `shared-tag` over an
    author-chosen vocabulary is a weaker claim than one carried by `sibling`, and nothing else in
    the output can tell the two apart."""


@dataclass(frozen=True, slots=True)
class Ranking:
    """How the channel orders what it found — **one gated configuration, two reported knobs**.

    APPROACH §4A puts in-degree salience and a `center_node_uuid`-style link-distance rerank *"in
    the first eval matrix"*, and G5 gates exactly one configuration: three variables against one
    threshold is not a decision procedure. So neither of these is a manifest key. They exist for
    `tools/graph_matrix.py`, which reports them beside the headline, and a setting a user could
    turn on would be a setting nobody had measured.
    """

    link_distance: bool = True
    """Whether hop distance ranks two equally-similar chunks, nearer first. §4A scores expanded
    chunks by *"edge weight and link distance"*; the arm that drops the term is what says whether
    it earns its place. It is a **tiebreak**, never the primary key — see the module docstring for
    why the other order silently makes depth 2 unreachable."""

    in_degree_salience: bool = False
    """A static citation-count prior: a document's inbound `links` count, inherited by its chunks
    through the membership edge, folded into the similarity as a factor of `(1 + log1p(in-degree))`.
    Multiplicative rather than additive so a chunk at cosine 0 stays at 0 — popularity is not
    evidence on its own, and §4.1 already treats a non-positive cosine as no evidence at all."""


GATED_RANKING: Final = Ranking()
"""The one configuration G5 gates. Every other point in the matrix is reported, never shipped."""


def expand(
    connection: sqlite3.Connection,
    roots: Sequence[int],
    *,
    similarity: Mapping[int, float],
    kinds: Collection[str],
    local_kb: str,
    adjacent_k: int,
    depth: int = DEPTH,
    limit: int,
    ranking: Ranking = GATED_RANKING,
) -> list[Reached]:
    """The channel's ranking, best first, at most `limit` long.

    `similarity` maps `chunks.id` to the query cosine the vector stage already computed. Handed in
    rather than recomputed: two similarity computations over one query are two things that can
    disagree, and the caller has the matrix in hand anyway. An absent chunk scores 0.0 — a chunk
    the vector stage never scored is not evidence, and inventing a score would rank it above a real
    low one.
    """
    return _Walk(
        connection,
        similarity=similarity,
        kinds=frozenset(kinds),
        local_kb=local_kb,
        adjacent_k=max(0, adjacent_k),
        ranking=ranking,
    ).run(roots, depth=depth, limit=limit)


@dataclass(frozen=True, slots=True)
class _Candidate:
    node: int
    key: str
    weight: float
    via: tuple[str, ...]


class _Walk:
    """One expansion. A class only because the visited sets are global to the walk, not per hop."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        similarity: Mapping[int, float],
        kinds: frozenset[str],
        local_kb: str,
        adjacent_k: int,
        ranking: Ranking = GATED_RANKING,
    ) -> None:
        self._connection = connection
        self._similarity = similarity
        self._kinds = kinds
        self._local_kb = local_kb
        self._adjacent_k = adjacent_k
        self._ranking = ranking
        self._in_degree: dict[str, int] = {}

        self._expanded: set[int] = set()
        """Every node already walked. A hub reached from three documents expands **once
        globally**, which is the difference between a bounded walk and a combinatorial one."""

        self._contributed: set[int] = set()
        """Document nodes whose member chunks have already been contributed."""

        self._root_documents: set[int] = set()
        self._emitted: dict[int, Reached] = {}
        self._nodes: dict[int, tuple[str, str]] = {}
        self._chunk_ids: dict[str, dict[int, int]] = {}

    # -- the loop ----------------------------------------------------------------------------

    def run(self, roots: Sequence[int], *, depth: int, limit: int) -> list[Reached]:
        frontier = self._root_nodes(roots)
        self._expanded |= set(frontier)
        for distance in range(1, max(0, depth) + 1):
            if not frontier:
                break
            found: dict[int, _Candidate] = {}
            for node in frontier:
                self._expand_chunk(node, found)
            frontier = self._accept(found, distance)

        ordered = sorted(self._emitted.values(), key=self._order)
        return ordered[:limit]

    def _order(self, reached: Reached) -> tuple[float, int, float, str]:
        """`(-cosine, distance, -weight, node_key)`, with distance held constant when the
        link-distance arm is off — so the term drops out of the comparison rather than the sort
        having two shapes."""
        return (
            -self._scored(reached.node_key),
            reached.distance if self._ranking.link_distance else 0,
            -reached.weight,
            reached.node_key,
        )

    def _root_nodes(self, roots: Sequence[int]) -> list[int]:
        """The `chunk` nodes for the fused top-*k*, and the documents they must not re-surface."""
        nodes: list[int] = []
        for chunk_id in roots:
            row = self._connection.execute(
                "SELECT doc_id, ordinal FROM chunks WHERE id = ?", (chunk_id,)
            ).fetchone()
            if row is None:  # pragma: no cover — a fused candidate is a live chunk by construction
                continue
            doc_id = str(row["doc_id"])
            node = edge_set.node_id(
                self._connection, "chunk", edge_set.chunk_key(doc_id, int(row["ordinal"]))
            )
            if node is None:
                # No edge set derived for this chunk — an index whose derivation found nothing, or
                # a soft-deleted document still holding rows. An empty walk is the honest answer.
                continue
            nodes.append(node)
            document = edge_set.node_id(self._connection, "doc", doc_id)
            if document is not None:
                self._root_documents.add(document)
        return nodes

    def _accept(self, found: Mapping[int, _Candidate], distance: int) -> list[int]:
        """Emit what this hop found, and return the chunk nodes the next hop expands from."""
        following: list[int] = []
        for node, candidate in found.items():
            chunk_id = self._chunk_id(candidate.key)
            if chunk_id is None:  # pragma: no cover — every chunk node names a live chunk
                continue
            self._emitted.setdefault(
                chunk_id,
                Reached(
                    chunk_id=chunk_id,
                    node_key=candidate.key,
                    doc_id=edge_set.parse_chunk_key(candidate.key)[0],
                    distance=distance,
                    weight=candidate.weight,
                    via=candidate.via,
                ),
            )
            if node not in self._expanded:
                self._expanded.add(node)
                following.append(node)
        return following

    # -- one chunk's expansion ---------------------------------------------------------------

    def _expand_chunk(self, node: int, found: dict[int, _Candidate]) -> None:
        peers = [
            _Candidate(spoke.node, key, spoke.weight, (spoke.kind,))
            for spoke, (kind, key) in self._described(
                edge_set.peers(self._connection, node, kinds=self._kinds & _CHUNK_PEER_KINDS)
            )
            if kind == "chunk"
        ]
        self._offer_chunks(peers, found)

        for hub in edge_set.hubs(self._connection, node, kinds=self._kinds):
            if hub.kind != "in-section" or hub.node in self._expanded:
                continue
            self._expanded.add(hub.node)
            members = [
                _Candidate(
                    spoke.node,
                    key,
                    edge_set.compose(hub.weight, spoke.weight),
                    (hub.kind, spoke.kind),
                )
                for spoke, (kind, key) in self._described(
                    edge_set.members(self._connection, hub.node, kinds=self._kinds)
                )
                if kind == "chunk" and spoke.node != node
            ]
            self._offer_chunks(members, found)

        self._expand_document(node, found)

    def _expand_document(self, chunk_node: int, found: dict[int, _Candidate]) -> None:
        """The document-level half: transit into the chunk's own document, once globally."""
        described = self._nodes.get(chunk_node) or self._describe_one(chunk_node)
        if described is None:  # pragma: no cover — the caller only passes live chunk nodes
            return
        document = edge_set.node_id(
            self._connection, "doc", edge_set.parse_chunk_key(described[1])[0]
        )
        if document is None or document in self._expanded:
            return
        self._expanded.add(document)

        # Non-chunk candidates rank by edge weight — they carry no embedding to compare against.
        onward: list[_Candidate] = []
        for spoke in edge_set.peers(
            self._connection,
            document,
            kinds=self._kinds & frozenset({edge_set.AUTHORED}),
            local_kb=self._local_kb,
        ):
            if not self._passable(spoke.node, document):
                continue
            onward.append(_Candidate(spoke.node, "", spoke.weight, (spoke.kind,)))
        for hub in edge_set.hubs(self._connection, document, kinds=self._kinds):
            if hub.kind not in _DOC_HUB_KINDS or hub.node in self._expanded:
                continue
            self._expanded.add(hub.node)
            for spoke in edge_set.members(self._connection, hub.node, kinds=self._kinds):
                if not self._passable(spoke.node, document):
                    continue
                onward.append(
                    _Candidate(
                        spoke.node,
                        "",
                        edge_set.compose(hub.weight, spoke.weight),
                        (hub.kind, spoke.kind),
                    )
                )

        onward.sort(key=lambda c: (-c.weight, c.node))
        for candidate in onward[: self._adjacent_k]:
            self._contribute(candidate, found)

    def _passable(self, candidate: int, source: int) -> bool:
        """Both membership-exclusion filters, applied **before** the fan-out cut.

        Rule 1 is `candidate != source`; rule 2 is the roots' own documents. Dropping them here
        rather than in `_contribute` is the whole of *"never consume its fan-out budget"* — after
        the cut they would each still have taken a slot from a document that had something to add.
        """
        return candidate != source and candidate not in self._root_documents

    def _contribute(self, document: _Candidate, found: dict[int, _Candidate]) -> None:
        """A document node's member chunks — the other half of "pass through and contribute"."""
        if document.node in self._contributed:
            return
        self._contributed.add(document.node)
        members = [
            _Candidate(node, key, document.weight, (*document.via, "membership"))
            for node, kind, key in self._members(document.node)
            if kind == "chunk"
        ]
        self._offer_chunks(members, found)

    def _offer_chunks(self, candidates: Sequence[_Candidate], found: dict[int, _Candidate]) -> None:
        """Rank by cosine, cap at `adjacent_k`, and record — keeping the **first** path to a node.

        First rather than best, deliberately: `via` and `weight` describe how the channel got
        there, and a later path overwriting them would make the provenance `tools/graph_matrix.py`
        reports disagree with the walk that produced the ranking it is explaining.
        """
        ranked = sorted(candidates, key=lambda c: (-self._scored(c.key), -c.weight, c.key))
        for candidate in ranked[: self._adjacent_k]:
            found.setdefault(candidate.node, candidate)

    # -- lookups -----------------------------------------------------------------------------

    def _scored(self, node_key: str) -> float:
        """A chunk's ranking score: its query cosine, times the in-degree prior when that arm is
        on. The same function ranks the fan-out and the final list, so an arm cannot select one
        set of neighbours and then order them by a different rule."""
        chunk_id = self._chunk_id(node_key)
        cosine = 0.0 if chunk_id is None else self._similarity.get(chunk_id, 0.0)
        if not self._ranking.in_degree_salience:
            return cosine
        return cosine * (1.0 + math.log1p(self._inbound(edge_set.parse_chunk_key(node_key)[0])))

    def _inbound(self, doc_id: str) -> int:
        """Every `links` row pointing at this document — the citation count §4A calls a zero-cost
        salience signal.

        The source may be **foreign**: a reverse-scanned row from a partner KB counts, even though
        such a row is inert in the walk itself (only a local document has a `doc` node). The two
        are different questions. Inertness is about *where a hop can go*; salience is about how
        often a document is cited, and a partner citing it is evidence either way.
        """
        known = self._in_degree.get(doc_id)
        if known is None:
            known = int(
                self._connection.execute(
                    "SELECT count(*) FROM links WHERE dst_kb_id = ? AND dst_doc_id = ?",
                    (self._local_kb, doc_id),
                ).fetchone()[0]
            )
            self._in_degree[doc_id] = known
        return known

    def _described(
        self, spokes: Sequence[edge_set.Spoke]
    ) -> list[tuple[edge_set.Spoke, tuple[str, str]]]:
        """Pair each spoke with its node's `(kind, key)`, resolving unknown ids in one query."""
        unknown = sorted({spoke.node for spoke in spokes} - self._nodes.keys())
        if unknown:
            placeholders = ",".join("?" for _ in unknown)
            for row in self._connection.execute(
                f"SELECT id, kind, key FROM nodes WHERE id IN ({placeholders})", unknown
            ):
                self._nodes[int(row[0])] = (str(row[1]), str(row[2]))
        return [(spoke, self._nodes[spoke.node]) for spoke in spokes if spoke.node in self._nodes]

    def _describe_one(self, node: int) -> tuple[str, str] | None:
        found = edge_set.node(self._connection, node)
        if found is None:  # pragma: no cover — every edge references a live node
            return None
        self._nodes[node] = (found.kind, found.key)
        return self._nodes[node]

    def _members(self, document: int) -> list[tuple[int, str, str]]:
        """A document's `membership` spokes, with each member's kind and key in the same query."""
        return [
            (int(row[0]), str(row[1]), str(row[2]))
            for row in self._connection.execute(
                "SELECT e.dst, n.kind, n.key FROM edges e JOIN nodes n ON n.id = e.dst "
                "WHERE e.src = ? AND e.kind = 'membership' ORDER BY e.dst",
                (document,),
            )
        ]

    def _chunk_id(self, node_key: str) -> int | None:
        """`<doc-ulid>:<ordinal>` back to `chunks.id`, one query per **document** rather than per
        chunk: a 2 969-chunk document is one round trip, not 2 969."""
        doc_id, ordinal = edge_set.parse_chunk_key(node_key)
        known = self._chunk_ids.get(doc_id)
        if known is None:
            known = {
                int(row[0]): int(row[1])
                for row in self._connection.execute(
                    "SELECT ordinal, id FROM chunks WHERE doc_id = ?", (doc_id,)
                )
            }
            self._chunk_ids[doc_id] = known
        return known.get(ordinal)
