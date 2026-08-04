"""The structural edge set — APPROACH §3's node model, derived at sync and read at query time.

**Nothing here is on any released surface.** Decision 16 keeps `pnk links` and `pinakes_links`
document-only: every neighbour they return is a document read from `links`, and a tag, directory,
heading or chunk node has no `doc_id` to be expressed in that shape. This graph exists for the
expansion channel and nothing else, which is what makes G3 inert rather than merely small.

## The node model

A node is `(kind, key)`; `nodes.id` is a surrogate minted per index. Five kinds span incompatible
id spaces, so the key is what carries identity across a rebuild:

| kind | key |
|---|---|
| `doc` | the document ULID |
| `chunk` | `<doc-ulid>:<ordinal>` — **not** `chunks.id`, which has no identity across rebuilds |
| `tag` | the tag string |
| `heading` | `<doc-ulid>:<heading_path>` — scoped per document |
| `dir` | the KB-root-relative directory path, `.` at the root |

**Heading nodes are scoped per document on purpose.** A global "Introduction" hub would weld every
document that has one into a single noise clique — worse than any tag, and the exact failure the
hub model exists to prevent. So a cross-document heading comparison is impossible here by
construction, not by convention.

## Every shared-value relation goes through its hub

`doc ↔ tag`, `doc ↔ directory`, `chunk ↔ heading` are spokes to a hub node, never materialised
pairwise edges. A tag on 30 documents is 30 spokes, not 435 edges — linear, not quadratic — and it
gives the channel's visited-edge dedup a single node to expand once globally.

**A spoke is one row, with the hub always as `src`.** That is what makes the damping divisor
`count(*) FROM edges WHERE src = ? AND kind = ?` well defined: it counts the hub's spokes and
nothing else. There is no stored `degree` — derived state inside derived state, and the count is an
index lookup.

**Damping applies to every shared-value hub**: `1/section-size`, `1/dir-size`, `1/tag-degree`.
Adjacency (`sibling`), hierarchy (`parent-child`) and `membership` are not shared-value relations
and stay at 1.0. Flow between two members of a hub is the **product of both spokes**, so a big hub
damps superlinearly — deliberate.

## Orientation is part of the edge-kind table, not the reader's choice

| kind | stored as | read with |
|---|---|---|
| `membership` | doc → chunk | `src = ? OR dst = ?` |
| `sibling` | lower → higher ordinal | `src = ? OR dst = ?` |
| `parent-child` | parent → child | `src = ? OR dst = ?` |
| `in-section` | heading hub → chunk | `src = ?` from the hub, `dst = ?` from a member |
| `co-located` | directory hub → doc | `src = ?` from the hub, `dst = ?` from a member |
| `shared-tag` | tag hub → doc | `src = ?` from the hub, `dst = ?` from a member |
| `authored` | as `links` stores it | `src = ? OR dst = ?` |

A `src`-only query over a symmetric kind silently drops half of every relation it names — a wrong
answer that looks like a small one. `peers()` is the only way to read those kinds here.

The hub kinds' two directions are **not** unioned, because they are not the same question: a hub
asked for its `src` rows answers "who is in me", a member asked for its `dst` rows answers "what am
I in". `members()` and `hubs()` are separate functions for that reason, and both weight the spoke
by the hub's degree, never the member's.

## `authored` has one home, and it is `links`

Authored edges are in the channel — APPROACH §4A counts depth in *logical* hops precisely so the
highest-trust edges are not stranded past depth 2 — but they are **not copied into `edges`**. They
are resolved from `links` at read time by looking both ends up as `doc` nodes. A `doc` node is keyed
on the document ULID alone, so **only a local document has one**: a row with a foreign `src_kb_id`
(every reverse-scanned row) or a foreign `dst_kb_id` (an outbound cross-KB link) resolves to nothing
and never enters the channel, in either direction.

Its weight is frozen at 2.0 (decision 13) and **carries a measured-at-G5 marker**: real IETF data
shows a worst out-degree of 86 against the "authored links are sparse" premise the weight rests on.
Keeping it, damping it or capping out-degree all decide a frozen weight on an argument rather than a
measurement, so it is deferred to a G5 leg (resolved 20260804 10:16). Do not change it here.

## Kind selection is a read-time argument, never a rebuild

G5's gate runs a `--drop sibling` arm and computes itself twice, with and without authored edges.
Both are `kinds=` on the reads below — every kind is derived and stored, and a caller subtracts.
`select_kinds()` refuses an unknown name rather than dropping nothing, because a `--drop sibbling`
that silently changes nothing is a green run that measured the wrong thing.
"""

from __future__ import annotations

import itertools
import json
import posixpath
import sqlite3
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from typing import Final, cast

from pinakes.errors import TraversalError
from pinakes.store import STRUCTURAL_EDGE_KINDS

AUTHORED: Final = "authored"
"""Read from `links`, never stored in `edges`. Named here because it is selectable like any other
kind — the with/without-authored split G5's gate needs is `kinds=`, not a second derivation."""

ALL_KINDS: Final = (*STRUCTURAL_EDGE_KINDS, AUTHORED)

HUB_KINDS: Final = frozenset({"in-section", "co-located", "shared-tag"})
"""Stored hub-first, damped by the hub's degree, and read directionally."""

SYMMETRIC_KINDS: Final = frozenset({"membership", "sibling", "parent-child", AUTHORED})
"""Stored once under an orientation rule, read from either end."""

WEIGHT: Final[dict[str, float]] = {
    "membership": 1.0,  # transit plumbing, not signal
    "sibling": 1.0,  # adjacency is not a shared value
    "parent-child": 1.0,  # nor is hierarchy
    "in-section": 1.0,  # ÷ section size
    "co-located": 1.0,  # ÷ directory size
    "shared-tag": 1.0,  # ÷ tag degree
    AUTHORED: 2.0,  # frozen by decision 13; measured at G5
}
"""The numerator. A hub kind's stored weight is this divided by the hub's degree; everything else
carries it as written. Frozen — a weight changed on an argument rather than a measurement is what
decision 13 froze the table to prevent."""

HEADING_SEPARATOR: Final = " > "
"""How `pinakes.chunk` joins a heading path. `parent-child` is a prefix comparison on it, and it
has to be the *path* separator rather than a bare `startswith`: "Costs" is not the parent of
"Costsheet"."""

ROOT_DIRECTORY: Final = "."
"""A document at the KB root still has a directory hub, and it needs a key. `posixpath.dirname`
returns `""` there, which would read as "no directory" rather than "the root one"."""


@dataclass(frozen=True, slots=True)
class Node:
    id: int
    kind: str
    key: str


@dataclass(frozen=True, slots=True)
class Spoke:
    """One edge, oriented from the node that was asked about."""

    node: int
    kind: str
    weight: float
    role: str
    """`peer` for a symmetric kind, `member` for a hub's member, `hub` for a member's hub. The
    channel needs it: a hub carries no content embedding and passes through by weight, while a peer
    is a chunk or a document that can be ranked."""


def chunk_key(doc_id: str, ordinal: int) -> str:
    """`<doc-ulid>:<ordinal>`. A ULID carries no `:`, so the split back is unambiguous."""
    return f"{doc_id}:{ordinal}"


def parse_chunk_key(key: str) -> tuple[str, int]:
    doc_id, _, ordinal = key.partition(":")
    return doc_id, int(ordinal)


def heading_key(doc_id: str, heading_path: str) -> str:
    """`<doc-ulid>:<heading_path>` — the per-document scoping, in one place so it cannot be
    forgotten at one call site and honoured at another."""
    return f"{doc_id}:{heading_path}"


def directory_of(path: str) -> str:
    return posixpath.dirname(path) or ROOT_DIRECTORY


def select_kinds(*, drop: Collection[str] = ()) -> frozenset[str]:
    """The kind set to read with, minus `drop`. **An unknown name is refused.**

    G5's arms are `--drop sibling` and `--drop authored`. A misspelling that quietly dropped nothing
    would produce a green run of the arm that was not measured — this project's recurring defect,
    an assertion satisfied by something other than the property it names.
    """
    unknown = sorted(set(drop) - set(ALL_KINDS))
    if unknown:
        raise TraversalError(
            f"unknown edge kind(s): {', '.join(unknown)}.",
            remedy=f"Use one of: {', '.join(ALL_KINDS)}.",
        )
    return frozenset(ALL_KINDS) - set(drop)


# --------------------------------------------------------------------------------------------
# Derivation


@dataclass(frozen=True, slots=True)
class Census:
    """What derivation produced, per kind — **every kind is a key, even at zero**.

    A kind missing from a dict is indistinguishable from a kind that derived nothing, and this
    corpus has already been measured once with three kinds silently at zero because the chunker
    degraded (`plans/20260804_1442-decision-g3-go.md`). A count that is absent cannot say so.
    """

    nodes: dict[str, int]
    edges: dict[str, int]

    @property
    def total_edges(self) -> int:
        return sum(self.edges.values())

    @property
    def total_nodes(self) -> int:
        return sum(self.nodes.values())


def derive(connection: sqlite3.Connection, *, local_kb: str) -> Census:
    """Rebuild `nodes` and `edges` from the active documents and chunks. Full, never incremental.

    **Full re-derivation, decided here.** An incremental deriver would have to reproduce, per
    changed document, every relation that document participates in — including the hub degrees of
    every tag and directory it shares — and get the *removals* right too. That is the same class of
    bug as a migration, in derived state a rebuild regenerates for free. The cost is measured rather
    than assumed: see the increment's `changelog.d/` fragment for wall-clock on both corpora.

    **Only active documents.** `state = 'deleted'` is a soft delete, so its chunks are gone but
    its row is not; deriving from it would let the channel surface deleted content. Because this
    rebuilds from scratch every time, a hub left with no members is never minted rather than needing
    reaping — degree zero cannot survive a derivation it was not part of.

    `local_kb` is taken rather than read from the index because the index does not hold it: the KB's
    own ULID lives in `pinakes.toml`. It is only used for the `authored` census, which counts the
    same population the channel can actually walk.
    """
    connection.execute("DELETE FROM edges")
    connection.execute("DELETE FROM nodes")

    documents = _active_documents(connection)
    chunks = _active_chunks(connection)

    keys: dict[tuple[str, str], int] = {}

    def mint(kind: str, key: str) -> int:
        found = keys.get((kind, key))
        if found is None:
            cursor = connection.execute("INSERT INTO nodes (kind, key) VALUES (?, ?)", (kind, key))
            found = int(cursor.lastrowid or 0)
            keys[(kind, key)] = found
        return found

    doc_node = {doc_id: mint("doc", doc_id) for doc_id in documents}
    chunk_node = {
        (row.doc_id, row.ordinal): mint("chunk", chunk_key(row.doc_id, row.ordinal))
        for row in chunks
    }

    # A set, so a duplicate triple is impossible by construction and a *reversed* one is still a
    # second element — which is exactly what `test_a_hub_spoke_is_stored_once_not_twice` looks for.
    edges: set[tuple[int, int, str]] = set()

    for row in chunks:
        edges.add((doc_node[row.doc_id], chunk_node[(row.doc_id, row.ordinal)], "membership"))

    edges |= _sibling_edges(chunks, chunk_node)
    edges |= _hierarchy_edges(chunks, chunk_node)

    hubs: dict[str, dict[str, list[int]]] = {
        "in-section": _section_buckets(chunks, chunk_node),
        "co-located": _directory_buckets(documents, doc_node),
        "shared-tag": _tag_buckets(documents, doc_node),
    }
    node_kind_of_hub = {"in-section": "heading", "co-located": "dir", "shared-tag": "tag"}
    for kind, buckets in hubs.items():
        for key, members in buckets.items():
            if len(members) < 2:
                # A hub with one member connects nothing: expanding it returns only the node that
                # reached it. Minting it would add a node and a spoke to every derivation, put a
                # degree-1 entry in `pnk doctor`'s hub report (G6), and make this census disagree
                # with the probe the go decision was taken on — for no reachable neighbour.
                continue
            hub = mint(node_kind_of_hub[kind], key)
            edges.update((hub, member, kind) for member in members)

    connection.executemany("INSERT INTO edges (src, dst, kind) VALUES (?, ?, ?)", sorted(edges))
    return Census(nodes=_node_census(connection), edges=census(connection, local_kb=local_kb))


@dataclass(frozen=True, slots=True)
class _ChunkRow:
    doc_id: str
    ordinal: int
    heading_path: str | None


@dataclass(frozen=True, slots=True)
class _DocumentRow:
    id: str
    path: str
    tags: tuple[str, ...]


def _active_documents(connection: sqlite3.Connection) -> dict[str, _DocumentRow]:
    return {
        str(row["id"]): _DocumentRow(
            id=str(row["id"]), path=str(row["path"]), tags=_tags(str(row["metadata"]))
        )
        for row in connection.execute(
            "SELECT id, path, metadata FROM documents WHERE state = 'active' ORDER BY path"
        )
    }


def _active_chunks(connection: sqlite3.Connection) -> list[_ChunkRow]:
    return [
        _ChunkRow(
            doc_id=str(row["doc_id"]),
            ordinal=int(row["ordinal"]),
            heading_path=None if row["heading_path"] is None else str(row["heading_path"]),
        )
        for row in connection.execute(
            "SELECT c.doc_id, c.ordinal, c.heading_path FROM chunks c "
            "JOIN documents d ON d.id = c.doc_id WHERE d.state = 'active' "
            "ORDER BY d.path, c.ordinal"
        )
    ]


def _tags(metadata: str) -> tuple[str, ...]:
    """A document's tags, deduplicated and order-preserving.

    Read defensively: `metadata` is JSON assembled from a user-authored sidecar, and while
    `pinakes.sidecar` validates `tags` as a list of strings, this module is downstream of a column
    a future key could reshape. A non-list, or a non-string entry, contributes no hub rather than
    raising in the middle of a sync.
    """
    try:
        parsed = json.loads(metadata)
    except ValueError:  # pragma: no cover — `store.dumps_metadata` wrote it
        return ()
    if not isinstance(parsed, dict):  # pragma: no cover — same
        return ()
    raw: object = cast(dict[str, object], parsed).get("tags")
    if not isinstance(raw, list):
        return ()
    seen: dict[str, None] = {}
    for entry in cast(list[object], raw):
        if isinstance(entry, str):
            seen.setdefault(entry, None)
    return tuple(seen)


def _sibling_edges(
    chunks: Sequence[_ChunkRow], chunk_node: dict[tuple[str, int], int]
) -> set[tuple[int, int, str]]:
    """Adjacent ordinals within one document, stored **lower → higher**.

    Ordinals are the contiguous `0..n-1` `store.replace_chunks` assigns, so "adjacent" is a
    difference of exactly one and nothing else can satisfy it.
    """
    by_doc: dict[str, list[int]] = {}
    for row in chunks:
        by_doc.setdefault(row.doc_id, []).append(row.ordinal)
    edges: set[tuple[int, int, str]] = set()
    for doc_id, ordinals in by_doc.items():
        ordered = sorted(ordinals)
        for lower, higher in itertools.pairwise(ordered):
            if higher - lower == 1:
                edges.add((chunk_node[(doc_id, lower)], chunk_node[(doc_id, higher)], "sibling"))
    return edges


def _hierarchy_edges(
    chunks: Sequence[_ChunkRow], chunk_node: dict[tuple[str, int], int]
) -> set[tuple[int, int, str]]:
    """`parent-child`, by `heading_path` prefix, stored **parent → child**.

    The comparison is on path segments, never raw characters: `"Costs"` is a prefix string of
    `"Costsheet"` and is not its parent. Only `"Costs" + " > "` is.

    Within one document only. A cross-document comparison would be the global-hub failure that
    heading nodes are scoped per document to avoid, arriving through the back door.
    """
    by_doc: dict[str, list[_ChunkRow]] = {}
    for row in chunks:
        if row.heading_path:
            by_doc.setdefault(row.doc_id, []).append(row)

    edges: set[tuple[int, int, str]] = set()
    for doc_id, rows in by_doc.items():
        for parent in rows:
            for child in rows:
                assert parent.heading_path is not None and child.heading_path is not None
                if child.heading_path.startswith(parent.heading_path + HEADING_SEPARATOR):
                    edges.add(
                        (
                            chunk_node[(doc_id, parent.ordinal)],
                            chunk_node[(doc_id, child.ordinal)],
                            "parent-child",
                        )
                    )
    return edges


def _section_buckets(
    chunks: Sequence[_ChunkRow], chunk_node: dict[tuple[str, int], int]
) -> dict[str, list[int]]:
    buckets: dict[str, list[int]] = {}
    for row in chunks:
        if row.heading_path:
            key = heading_key(row.doc_id, row.heading_path)
            buckets.setdefault(key, []).append(chunk_node[(row.doc_id, row.ordinal)])
    return buckets


def _directory_buckets(
    documents: dict[str, _DocumentRow], doc_node: dict[str, int]
) -> dict[str, list[int]]:
    buckets: dict[str, list[int]] = {}
    for row in documents.values():
        buckets.setdefault(directory_of(row.path), []).append(doc_node[row.id])
    return buckets


def _tag_buckets(
    documents: dict[str, _DocumentRow], doc_node: dict[str, int]
) -> dict[str, list[int]]:
    buckets: dict[str, list[int]] = {}
    for row in documents.values():
        for tag in row.tags:
            buckets.setdefault(tag, []).append(doc_node[row.id])
    return buckets


def _node_census(connection: sqlite3.Connection) -> dict[str, int]:
    from pinakes.store import NODE_KINDS

    counts: dict[str, int] = dict.fromkeys(NODE_KINDS, 0)
    for row in connection.execute("SELECT kind, count(*) FROM nodes GROUP BY kind"):
        counts[str(row[0])] = int(row[1])
    return counts


def census(connection: sqlite3.Connection, *, local_kb: str) -> dict[str, int]:
    """Edges per kind, `authored` included and counted the way the channel can walk it."""
    counts: dict[str, int] = dict.fromkeys(ALL_KINDS, 0)
    for row in connection.execute("SELECT kind, count(*) FROM edges GROUP BY kind"):
        counts[str(row[0])] = int(row[1])
    counts[AUTHORED] = len(authored_pairs(connection, local_kb=local_kb))
    return counts


# --------------------------------------------------------------------------------------------
# Reading


def node_id(connection: sqlite3.Connection, kind: str, key: str) -> int | None:
    row = connection.execute(
        "SELECT id FROM nodes WHERE kind = ? AND key = ?", (kind, key)
    ).fetchone()
    return int(row[0]) if row else None


def node(connection: sqlite3.Connection, identifier: int) -> Node | None:
    row = connection.execute(
        "SELECT id, kind, key FROM nodes WHERE id = ?", (identifier,)
    ).fetchone()
    return Node(int(row[0]), str(row[1]), str(row[2])) if row else None


def hub_degree(connection: sqlite3.Connection, hub: int, kind: str) -> int:
    """The damping divisor. One `count(*)` on `(src, kind)`, which is indexed.

    Well defined **because** a hub spoke always carries the hub as `src`: stored either way round,
    this would count some hubs' spokes and some members' memberships and call both "degree".
    """
    row = connection.execute(
        "SELECT count(*) FROM edges WHERE src = ? AND kind = ?", (hub, kind)
    ).fetchone()
    return int(row[0])


def spoke_weight(connection: sqlite3.Connection, hub: int, kind: str) -> float:
    """A hub spoke's weight: the kind's numerator over the hub's degree. 1.0 for the rest."""
    if kind not in HUB_KINDS:
        return WEIGHT[kind]
    degree = hub_degree(connection, hub, kind)
    return WEIGHT[kind] / degree if degree else 0.0


def compose(first: float, second: float) -> float:
    """Flow between two members of a hub is the **product** of both spokes.

    Named rather than inlined because it is the reason 1/degree damping is superlinear on a big
    hub, and a `min` or a sum would look just as reasonable at the call site.
    """
    return first * second


def peers(
    connection: sqlite3.Connection,
    identifier: int,
    *,
    kinds: Collection[str],
    local_kb: str | None = None,
) -> list[Spoke]:
    """Symmetric kinds, read from **both** ends.

    `src = ? OR dst = ?`, never `src = ?`: these kinds are stored once under an orientation rule,
    so half of every relation lives on the far side of the row. A `src`-only read returns a
    confident, wrong, smaller answer.

    `authored` is included when it is in `kinds` **and** `local_kb` is given — it lives in `links`,
    not in `edges`, and resolving it needs to know which KB is local.
    """
    wanted = [kind for kind in kinds if kind in SYMMETRIC_KINDS and kind != AUTHORED]
    found: list[Spoke] = []
    if wanted:
        placeholders = ",".join("?" for _ in wanted)
        rows = connection.execute(
            f"SELECT src, dst, kind FROM edges WHERE (src = ? OR dst = ?) AND kind IN "
            f"({placeholders}) ORDER BY kind, src, dst",
            (identifier, identifier, *wanted),
        )
        for src, dst, kind in rows:
            other = int(dst) if int(src) == identifier else int(src)
            found.append(Spoke(node=other, kind=str(kind), weight=WEIGHT[str(kind)], role="peer"))
    if AUTHORED in kinds and local_kb is not None:
        found.extend(_authored_peers(connection, identifier, local_kb=local_kb))
    return found


def members(connection: sqlite3.Connection, hub: int, *, kinds: Collection[str]) -> list[Spoke]:
    """What a hub connects — `src = ?`, because the hub is always the `src` of its own spokes."""
    wanted = [kind for kind in kinds if kind in HUB_KINDS]
    if not wanted:
        return []
    placeholders = ",".join("?" for _ in wanted)
    rows = connection.execute(
        f"SELECT dst, kind FROM edges WHERE src = ? AND kind IN ({placeholders}) "
        "ORDER BY kind, dst",
        (hub, *wanted),
    ).fetchall()
    weights = {kind: spoke_weight(connection, hub, kind) for kind in wanted}
    return [
        Spoke(node=int(dst), kind=str(kind), weight=weights[str(kind)], role="member")
        for dst, kind in rows
    ]


def hubs(connection: sqlite3.Connection, member: int, *, kinds: Collection[str]) -> list[Spoke]:
    """What a member is in — `dst = ?`, the other half of a hub kind, and a different question.

    Weighted by the **hub's** degree, never the member's: `1/tag-degree` is a property of the tag.
    """
    wanted = [kind for kind in kinds if kind in HUB_KINDS]
    if not wanted:
        return []
    placeholders = ",".join("?" for _ in wanted)
    rows = connection.execute(
        f"SELECT src, kind FROM edges WHERE dst = ? AND kind IN ({placeholders}) "
        "ORDER BY kind, src",
        (member, *wanted),
    ).fetchall()
    return [
        Spoke(
            node=int(src),
            kind=str(kind),
            weight=spoke_weight(connection, int(src), str(kind)),
            role="hub",
        )
        for src, kind in rows
    ]


def neighbours(
    connection: sqlite3.Connection,
    identifier: int,
    *,
    kinds: Collection[str],
    local_kb: str | None = None,
) -> list[Spoke]:
    """Every edge touching a node, under one kind selection — the channel's single entry point.

    Three reads rather than one union, because the three answer different questions and carry
    different weights. Whichever of them a given node has rows for is decided by the data: a chunk
    has peers and hubs, a tag hub has members, a document has all three.
    """
    return [
        *peers(connection, identifier, kinds=kinds, local_kb=local_kb),
        *members(connection, identifier, kinds=kinds),
        *hubs(connection, identifier, kinds=kinds),
    ]


# --------------------------------------------------------------------------------------------
# Authored edges, resolved from `links`


def authored_pairs(connection: sqlite3.Connection, *, local_kb: str) -> list[tuple[int, int]]:
    """`(src doc node, dst doc node)` for every `links` row whose **both** ends are local documents.

    Orientation is the one `links` stores — the direction the sidecar wrote it — and is never
    flipped to put the local document first. A reverse-scanned row keeps the foreign document as
    `src`, which is also why it resolves to nothing: only a local document has a `doc` node.

    The join drops a deleted document too, since `derive` mints `doc` nodes for active documents
    only. That is the same guarantee the soft-delete rule gives the structural kinds, reached the
    only way an unstored kind can reach it.
    """
    rows = connection.execute(
        "SELECT s.id, d.id FROM links l "
        "JOIN nodes s ON s.kind = 'doc' AND s.key = l.src_doc_id "
        "JOIN nodes d ON d.kind = 'doc' AND d.key = l.dst_doc_id "
        "WHERE l.src_kb_id = ? AND l.dst_kb_id = ? ORDER BY s.id, d.id",
        (local_kb, local_kb),
    )
    return sorted({(int(src), int(dst)) for src, dst in rows})


def _authored_peers(
    connection: sqlite3.Connection, identifier: int, *, local_kb: str
) -> list[Spoke]:
    seen: dict[int, None] = {}
    for src, dst in authored_pairs(connection, local_kb=local_kb):
        if src == identifier:
            seen.setdefault(dst, None)
        elif dst == identifier:
            seen.setdefault(src, None)
    return [
        Spoke(node=other, kind=AUTHORED, weight=WEIGHT[AUTHORED], role="peer") for other in seen
    ]


def format_census(counts: Iterable[tuple[str, int]]) -> str:
    """`kind=count` pairs, in `ALL_KINDS` order, for a report line."""
    return " ".join(f"{kind}={count}" for kind, count in counts)
