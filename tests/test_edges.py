"""G3 — the node model and the derived edge set, against real KBs synced on disk.

Every fixture here is a KB `pnk sync` actually built, never a hand-written `edges` table: the
properties under test are *derivation* properties, and a fixture that inserts the rows it then
asserts on tests nothing but the test (v0.1 rule 5).

The recurring defect this file is written against is an assertion satisfied by something other
than the property it names. So the negative half is written first wherever there is one — a heading
hub that must *not* span two documents, a `parent-child` edge that must *not* fire on
`Costs`/`Costsheet`, a hub spoke that must *not* also exist reversed, a kind name that must *not*
be silently ignored.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_sync_links import DIM, MANIFEST, fake_factory

from pinakes import store
from pinakes.errors import IndexSchemaError, TraversalError
from pinakes.graph import edges
from pinakes.ids import DocId, KbId, mint_doc_id, mint_kb_id
from pinakes.manifest import load
from pinakes.sidecar import SIDECAR_SUFFIX
from pinakes.sync import SyncOptions, SyncReport, sync

REPO = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------------------------
# A KB builder with the three knobs this increment needs: headings, tags and directories.


@dataclass
class Doc:
    path: str
    """KB-root-relative, POSIX. `docs/a.md`, `docs/deep/b.md` — the directory hub reads this."""
    body: str
    tags: tuple[str, ...] = ()
    doc_id: DocId | None = None
    """Forced only where the test needs two KBs to share a document ULID — which is what a forked
    KB produces, and the one shape that tells `authored_pairs`' two kb-id filters apart."""


@dataclass
class Corpus:
    root: Path
    kb_id: KbId
    ids: dict[str, DocId] = field(default_factory=dict[str, DocId])

    def write(self, doc: Doc) -> DocId:
        target = self.root / doc.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc.body, encoding="utf-8")
        doc_id = doc.doc_id or self.ids.get(doc.path) or mint_doc_id()
        self.ids[doc.path] = doc_id
        sidecar: dict[str, Any] = {"id": str(doc_id), "title": Path(doc.path).stem}
        if doc.tags:
            sidecar["tags"] = list(doc.tags)
        (self.root / (doc.path + SIDECAR_SUFFIX)).write_text(
            yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8"
        )
        return doc_id

    def remove(self, path: str) -> None:
        (self.root / path).unlink()
        (self.root / (path + SIDECAR_SUFFIX)).unlink()

    def sync(self, **options: Any) -> SyncReport:
        return sync(
            load(self.root),
            options=SyncOptions(**options),
            backend_factory=fake_factory,
            now="20260804 16:00",
        )

    def open(self) -> sqlite3.Connection:
        return store.connect_ro(load(self.root).index_path)


def build(root: Path, docs: Sequence[Doc], *, roots: str = "") -> Corpus:
    """A KB on disk with `docs`, synced. `roots = ""` indexes from the KB root itself."""
    root.mkdir(parents=True, exist_ok=True)
    kb_id = mint_kb_id()
    manifest = MANIFEST.format(name="edges", kb_id=kb_id, dim=DIM, docs=roots)
    if not roots:
        # `roots = ["/"]` is not a thing; the root itself is `["."]`.
        manifest = manifest.replace('roots   = ["/"]', 'roots   = ["."]')
    (root / "pinakes.toml").write_text(manifest, encoding="utf-8")
    corpus = Corpus(root=root, kb_id=kb_id)
    for doc in docs:
        corpus.write(doc)
    corpus.sync()
    return corpus


def sectioned(title: str, sections: Sequence[tuple[str, str]]) -> str:
    body = f"# {title}\n\nIntroducing {title}.\n"
    for heading, text in sections:
        body += f"\n## {heading}\n\n{text}\n"
    return body


# --------------------------------------------------------------------------------------------
# Reading helpers — deliberately raw SQL, so a test never asserts through the code under test.


def rows(connection: sqlite3.Connection) -> list[tuple[str, str, str, str, str]]:
    """Every edge as `(src kind, src key, kind, dst kind, dst key)`. Surrogate ids never leak
    into an assertion: they are minted per derivation and mean nothing across one."""
    return sorted(
        (str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]))
        for r in connection.execute(
            "SELECT s.kind, s.key, e.kind, d.kind, d.key FROM edges e "
            "JOIN nodes s ON s.id = e.src JOIN nodes d ON d.id = e.dst"
        )
    )


def nodes_of(connection: sqlite3.Connection, kind: str) -> list[str]:
    return sorted(
        str(r[0]) for r in connection.execute("SELECT key FROM nodes WHERE kind = ?", (kind,))
    )


def identifier(connection: sqlite3.Connection, kind: str, key: str) -> int:
    found = edges.node_id(connection, kind, key)
    assert found is not None, f"no {kind} node keyed {key!r}; nodes: {nodes_of(connection, kind)}"
    return found


def chunks_of(connection: sqlite3.Connection, doc_id: str) -> list[tuple[int, str | None]]:
    return [
        (int(r[0]), None if r[1] is None else str(r[1]))
        for r in connection.execute(
            "SELECT ordinal, heading_path FROM chunks WHERE doc_id = ? ORDER BY ordinal", (doc_id,)
        )
    ]


# --------------------------------------------------------------------------------------------
# Node identity


def test_a_chunk_node_is_keyed_on_the_document_ulid_and_ordinal(tmp_path: Path) -> None:
    corpus = build(tmp_path / "kb", [Doc("docs/a.md", sectioned("A", [("One", "x " * 40)]))])
    connection = corpus.open()
    try:
        doc_id = str(corpus.ids["docs/a.md"])
        expected = {
            edges.chunk_key(doc_id, ordinal) for ordinal, _ in chunks_of(connection, doc_id)
        }
        assert expected
        assert set(nodes_of(connection, "chunk")) == expected
    finally:
        connection.close()


def test_a_chunk_node_key_survives_a_rebuild(tmp_path: Path) -> None:
    """`chunks.id` is a rowid and `store.py` says it has no identity across rebuilds. The node key
    is `<doc-ulid>:<ordinal>` for exactly that reason — this asserts the difference is real, by
    checking the rowids genuinely moved. Without that half, a run where they happened not to move
    would pass while saying nothing.
    """
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "alpha " * 30)])),
            Doc("docs/b.md", sectioned("B", [("One", "beta " * 30)])),
            Doc("docs/c.md", sectioned("C", [("One", "gamma " * 30)])),
        ],
    )

    def snapshot() -> tuple[set[str], dict[str, int]]:
        connection = corpus.open()
        try:
            keys = set(nodes_of(connection, "chunk"))
            rowids = {
                edges.chunk_key(str(r[0]), int(r[1])): int(r[2])
                for r in connection.execute("SELECT doc_id, ordinal, id FROM chunks")
            }
            return keys, rowids
        finally:
            connection.close()

    # Re-chunk the *first* document, incrementally: its new rows are appended after c's, so the
    # rowid a chunk carries stops matching its position (G1's own measurement).
    corpus.write(Doc("docs/a.md", sectioned("A", [("One", "alpha " * 30), ("Two", "delta " * 30)])))
    corpus.sync()
    keys_incremental, rowids_incremental = snapshot()

    corpus.sync(rebuild=True)
    keys_rebuilt, rowids_rebuilt = snapshot()

    assert keys_incremental == keys_rebuilt
    shared = keys_incremental & keys_rebuilt
    assert any(rowids_incremental[key] != rowids_rebuilt[key] for key in shared), (
        "no chunk changed rowid across the rebuild, so this run cannot show that the node key "
        "survives something `chunks.id` does not"
    )


def test_a_heading_node_is_scoped_to_its_document(tmp_path: Path) -> None:
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("Shared", [("Intro", "a " * 200), ("Later", "a " * 200)])),
            Doc("docs/b.md", sectioned("Shared", [("Intro", "b " * 200), ("Later", "b " * 200)])),
        ],
    )
    connection = corpus.open()
    try:
        a, b = str(corpus.ids["docs/a.md"]), str(corpus.ids["docs/b.md"])
        headings = nodes_of(connection, "heading")
        assert headings, "the fixture produced no heading_path at all"
        assert all(key.startswith((a + ":", b + ":")) for key in headings)
        # The same heading text in two documents is two nodes, never one.
        assert edges.heading_key(a, "Shared > Intro") in headings
        assert edges.heading_key(b, "Shared > Intro") in headings
    finally:
        connection.close()


def test_a_document_at_the_kb_root_still_has_a_directory_hub(tmp_path: Path) -> None:
    """`posixpath.dirname` returns `""` at the root, which reads as "no directory" rather than
    "the root one" — so two documents beside `pinakes.toml` would silently stop being co-located."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc("a.md", sectioned("A", [("One", "x " * 40)])),
            Doc("b.md", sectioned("B", [("One", "y " * 40)])),
        ],
        roots="",
    )
    connection = corpus.open()
    try:
        assert nodes_of(connection, "dir") == [edges.ROOT_DIRECTORY]
        hub = identifier(connection, "dir", edges.ROOT_DIRECTORY)
        assert edges.hub_degree(connection, hub, "co-located") == 2
    finally:
        connection.close()


# --------------------------------------------------------------------------------------------
# Hubs: linear, single-row, damped


def test_a_shared_tag_produces_linear_not_quadratic_edges(tmp_path: Path) -> None:
    """Eight documents on one tag are eight spokes, not twenty-eight pairwise edges. The hub model
    exists for this; materialising the pairs is what makes a popular tag a noise clique."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc(f"docs/{name}.md", sectioned(name, [("One", "x " * 40)]), tags=("shared",))
            for name in "abcdefgh"
        ],
    )
    connection = corpus.open()
    try:
        spokes = [row for row in rows(connection) if row[2] == "shared-tag"]
        assert len(spokes) == 8, f"{len(spokes)} shared-tag rows; 8 spokes expected, 28 is the trap"
        assert {row[0] for row in spokes} == {"tag"}
        assert {row[3] for row in spokes} == {"doc"}
    finally:
        connection.close()


def test_a_hub_spoke_is_stored_once_not_twice(tmp_path: Path) -> None:
    """One row per spoke, hub always as `src`. Stored both ways round the damping divisor would
    count some hubs' spokes and some members' memberships and call both "degree"."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 40)]), tags=("t",)),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 40)]), tags=("t",)),
        ],
    )
    connection = corpus.open()
    try:
        hub = identifier(connection, "tag", "t")
        doc = identifier(connection, "doc", str(corpus.ids["docs/a.md"]))
        forward = connection.execute(
            "SELECT count(*) FROM edges WHERE src = ? AND dst = ? AND kind = 'shared-tag'",
            (hub, doc),
        ).fetchone()[0]
        reverse = connection.execute(
            "SELECT count(*) FROM edges WHERE src = ? AND dst = ? AND kind = 'shared-tag'",
            (doc, hub),
        ).fetchone()[0]
        assert (forward, reverse) == (1, 0)
    finally:
        connection.close()


def test_a_duplicate_tag_in_one_sidecar_is_one_spoke(tmp_path: Path) -> None:
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 40)]), tags=("t", "t")),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 40)]), tags=("t",)),
        ],
    )
    connection = corpus.open()
    try:
        hub = identifier(connection, "tag", "t")
        assert edges.hub_degree(connection, hub, "shared-tag") == 2
    finally:
        connection.close()


def test_a_hub_with_a_single_member_is_not_minted(tmp_path: Path) -> None:
    """A hub whose only member is the node that reached it connects nothing: expanding it returns
    that node and stops. Minting it would add a node, a spoke and a degree-1 entry in `pnk doctor`'s
    hub report for no reachable neighbour — and would make this census disagree with the probe the
    go decision was measured on."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 40)]), tags=("only-here", "both")),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 40)]), tags=("both",)),
        ],
    )
    connection = corpus.open()
    try:
        assert nodes_of(connection, "tag") == ["both"]
    finally:
        connection.close()


def test_a_dropped_tag_lowers_the_divisor(tmp_path: Path) -> None:
    """Damping is read-time and unstored, so the divisor has to follow the corpus with no
    bookkeeping. Three documents on a tag weight each spoke 1/3; take one away and it is 1/2."""
    docs = [
        Doc(f"docs/{name}.md", sectioned(name, [("One", "x " * 40)]), tags=("t",)) for name in "abc"
    ]
    corpus = build(tmp_path / "kb", docs)

    connection = corpus.open()
    try:
        hub = identifier(connection, "tag", "t")
        assert edges.hub_degree(connection, hub, "shared-tag") == 3
        assert edges.spoke_weight(connection, hub, "shared-tag") == pytest.approx(1 / 3)
    finally:
        connection.close()

    corpus.write(Doc("docs/c.md", sectioned("c", [("One", "x " * 40)])))
    corpus.sync()

    connection = corpus.open()
    try:
        hub = identifier(connection, "tag", "t")
        assert edges.hub_degree(connection, hub, "shared-tag") == 2
        assert edges.spoke_weight(connection, hub, "shared-tag") == pytest.approx(1 / 2)
    finally:
        connection.close()


def test_weight_across_a_hub_is_the_product_of_both_spokes(tmp_path: Path) -> None:
    """Flow between two members of a hub is the product, never the smaller or the sum — which is
    what makes 1/degree damping superlinear on a big hub."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc(f"docs/{name}.md", sectioned(name, [("One", "x " * 40)]), tags=("t",))
            for name in "abcd"
        ],
    )
    connection = corpus.open()
    try:
        hub = identifier(connection, "tag", "t")
        a = identifier(connection, "doc", str(corpus.ids["docs/a.md"]))
        b = identifier(connection, "doc", str(corpus.ids["docs/b.md"]))

        into = next(s for s in edges.hubs(connection, a, kinds=edges.ALL_KINDS) if s.node == hub)
        out = next(s for s in edges.members(connection, hub, kinds=edges.ALL_KINDS) if s.node == b)
        assert into.weight == pytest.approx(0.25)
        assert out.weight == pytest.approx(0.25)
        assert edges.compose(into.weight, out.weight) == pytest.approx(0.0625)
    finally:
        connection.close()


def test_a_hub_is_entered_from_a_member_and_expanded_from_the_hub(tmp_path: Path) -> None:
    """The two halves of a hub kind are different questions and are read with different queries —
    `dst = ?` to ask "what am I in", `src = ?` to ask "who is in me". Reading a hub kind with
    `src = ?` alone would make every hub unreachable, and `shared-tag`/`co-located` are the two
    kinds the go decision measured carrying all nine liftable questions.

    Both spokes are weighted by the **hub's** degree, never the member's.
    """
    corpus = build(
        tmp_path / "kb",
        [
            Doc(f"docs/{name}.md", sectioned(name, [("One", "x " * 40)]), tags=("t",))
            for name in "abc"
        ],
    )
    connection = corpus.open()
    try:
        hub = identifier(connection, "tag", "t")
        a = identifier(connection, "doc", str(corpus.ids["docs/a.md"]))

        entered = edges.hubs(connection, a, kinds=edges.ALL_KINDS)
        assert hub in [s.node for s in entered]
        assert all(s.role == "hub" for s in entered)
        assert all(s.weight == pytest.approx(1 / 3) for s in entered if s.kind == "shared-tag")

        expanded = edges.members(connection, hub, kinds=edges.ALL_KINDS)
        assert sorted(s.node for s in expanded) == sorted(
            identifier(connection, "doc", str(corpus.ids[f"docs/{n}.md"])) for n in "abc"
        )
        assert all(s.role == "member" for s in expanded)
    finally:
        connection.close()


def test_a_heading_hub_never_connects_two_documents(tmp_path: Path) -> None:
    """The global-hub failure APPROACH scopes heading nodes to avoid: a shared "Introduction"
    would weld every document that has one into a single clique."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("Shared", [("Intro", "a " * 60), ("Intro", "a " * 60)])),
            Doc("docs/b.md", sectioned("Shared", [("Intro", "b " * 60), ("Intro", "b " * 60)])),
        ],
    )
    connection = corpus.open()
    try:
        spokes = [row for row in rows(connection) if row[2] == "in-section"]
        assert spokes, "the fixture derived no in-section spokes, so this asserts nothing"
        for hub_kind, hub_key, _, member_kind, member_key in spokes:
            assert hub_kind == "heading" and member_kind == "chunk"
            hub_doc, _, _ = hub_key.partition(":")
            member_doc, _ = edges.parse_chunk_key(member_key)
            assert hub_doc == member_doc, f"heading hub {hub_key} reaches into {member_doc}"
    finally:
        connection.close()


# --------------------------------------------------------------------------------------------
# Chunk-level structure


def test_sibling_edges_join_adjacent_ordinals(tmp_path: Path) -> None:
    corpus = build(
        tmp_path / "kb",
        [
            Doc(
                "docs/a.md",
                sectioned("A", [("One", "x " * 60), ("Two", "y " * 60), ("Three", "z " * 60)]),
            )
        ],
    )
    connection = corpus.open()
    try:
        doc_id = str(corpus.ids["docs/a.md"])
        ordinals = [ordinal for ordinal, _ in chunks_of(connection, doc_id)]
        assert len(ordinals) >= 3, "the fixture produced too few chunks to have a sibling chain"

        found = {
            (edges.parse_chunk_key(src)[1], edges.parse_chunk_key(dst)[1])
            for _, src, kind, _, dst in rows(connection)
            if kind == "sibling"
        }
        assert found == {(n, n + 1) for n in ordinals[:-1]}
        assert all(lower < higher for lower, higher in found), "stored higher→lower somewhere"
    finally:
        connection.close()


def test_a_sibling_edge_never_crosses_a_document(tmp_path: Path) -> None:
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60), ("Two", "x " * 60)])),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60), ("Two", "y " * 60)])),
        ],
    )
    connection = corpus.open()
    try:
        for _, src, kind, _, dst in rows(connection):
            if kind == "sibling":
                assert edges.parse_chunk_key(src)[0] == edges.parse_chunk_key(dst)[0]
    finally:
        connection.close()


def test_parent_and_child_follow_heading_path_prefixes(tmp_path: Path) -> None:
    """Stored parent → child, and on *path segments*: `Costs` is a string prefix of `Costsheet`
    and is not its parent."""
    corpus = build(
        tmp_path / "kb",
        [Doc("docs/a.md", sectioned("Costs", [("Detail", "x " * 60)]))],
    )
    connection = corpus.open()
    try:
        doc_id = str(corpus.ids["docs/a.md"])
        by_heading = {heading: ordinal for ordinal, heading in chunks_of(connection, doc_id)}
        assert "Costs" in by_heading and "Costs > Detail" in by_heading, by_heading

        found = {
            (edges.parse_chunk_key(src)[1], edges.parse_chunk_key(dst)[1])
            for _, src, kind, _, dst in rows(connection)
            if kind == "parent-child"
        }
        assert (by_heading["Costs"], by_heading["Costs > Detail"]) in found
        assert (by_heading["Costs > Detail"], by_heading["Costs"]) not in found
    finally:
        connection.close()


def test_a_sibling_heading_that_is_a_string_prefix_is_not_a_parent(tmp_path: Path) -> None:
    """`Costs` and `Costsheet` are two level-1 headings. A bare `startswith` makes the first the
    parent of the second, and nothing else in the suite would notice."""
    body = "# Costs\n\n" + ("x " * 60) + "\n\n# Costsheet\n\n" + ("y " * 60) + "\n"
    corpus = build(tmp_path / "kb", [Doc("docs/a.md", body)])
    connection = corpus.open()
    try:
        headings = {heading for _, heading in chunks_of(connection, str(corpus.ids["docs/a.md"]))}
        assert {"Costs", "Costsheet"} <= headings, headings
        assert not [row for row in rows(connection) if row[2] == "parent-child"]
    finally:
        connection.close()


def test_membership_runs_document_to_chunk(tmp_path: Path) -> None:
    corpus = build(tmp_path / "kb", [Doc("docs/a.md", sectioned("A", [("One", "x " * 60)]))])
    connection = corpus.open()
    try:
        membership = [row for row in rows(connection) if row[2] == "membership"]
        assert membership
        for src_kind, src_key, _, dst_kind, dst_key in membership:
            assert (src_kind, dst_kind) == ("doc", "chunk")
            assert edges.parse_chunk_key(dst_key)[0] == src_key
    finally:
        connection.close()


def test_a_symmetric_edge_is_reachable_from_both_ends(tmp_path: Path) -> None:
    """A symmetric kind is stored once under an orientation rule, so half of every relation lives
    on the far side of the row. A `src = ?` read returns a confident, smaller, wrong answer."""
    corpus = build(
        tmp_path / "kb",
        [Doc("docs/a.md", sectioned("A", [("One", "x " * 60), ("Two", "y " * 60)]))],
    )
    connection = corpus.open()
    try:
        doc_id = str(corpus.ids["docs/a.md"])
        ordinals = [ordinal for ordinal, _ in chunks_of(connection, doc_id)]
        assert len(ordinals) >= 2
        lower = identifier(connection, "chunk", edges.chunk_key(doc_id, ordinals[0]))
        higher = identifier(connection, "chunk", edges.chunk_key(doc_id, ordinals[1]))

        from_lower = [s.node for s in edges.peers(connection, lower, kinds=("sibling",))]
        from_higher = [s.node for s in edges.peers(connection, higher, kinds=("sibling",))]
        assert higher in from_lower, "the stored `src` end found its neighbour"
        assert lower in from_higher, "the stored `dst` end did not — a src-only read"
    finally:
        connection.close()


# --------------------------------------------------------------------------------------------
# Removal


def test_a_soft_deleted_document_leaves_no_edges(tmp_path: Path) -> None:
    """`state = 'deleted'` is a soft delete, so the row survives. If its edges did, the channel
    could surface deleted content — and the hub it was the second member of would keep a spoke
    pointing at a document nothing can fetch."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60)]), tags=("t",)),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)]), tags=("t",)),
        ],
    )
    gone = str(corpus.ids["docs/b.md"])

    connection = corpus.open()
    try:
        assert edges.node_id(connection, "doc", gone) is not None
        assert nodes_of(connection, "tag") == ["t"]
    finally:
        connection.close()

    corpus.remove("docs/b.md")
    report = corpus.sync()
    assert report.deleted == 1

    connection = corpus.open()
    try:
        state = connection.execute("SELECT state FROM documents WHERE id = ?", (gone,)).fetchone()
        assert str(state[0]) == "deleted", "the fixture hard-deleted instead of soft-deleting"

        assert edges.node_id(connection, "doc", gone) is None
        assert not [key for key in nodes_of(connection, "chunk") if key.startswith(gone + ":")]
        assert not [row for row in rows(connection) if gone in (row[1], row[4])]
        assert not [key for key in nodes_of(connection, "chunk") if key.startswith(gone)]
        # The tag hub is down to one member, so it connects nothing and is not minted at all.
        assert nodes_of(connection, "tag") == []
    finally:
        connection.close()


# --------------------------------------------------------------------------------------------
# Authored edges — one home, and it is `links`


def _link(corpus: Corpus, source: str, target_uri: str, rel: str) -> None:
    path = corpus.root / (source + SIDECAR_SUFFIX)
    body: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    body.setdefault("links", []).append({"to": target_uri, "rel": rel})
    path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")


def test_an_authored_edge_is_read_from_links_and_never_stored_in_edges(tmp_path: Path) -> None:
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60)])),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)])),
        ],
    )
    _link(corpus, "docs/a.md", f"pnk://{corpus.kb_id}/{corpus.ids['docs/b.md']}", "cites")
    corpus.sync()

    connection = corpus.open()
    try:
        assert not [
            row for row in connection.execute("SELECT kind FROM edges WHERE kind = 'authored'")
        ]
        a = identifier(connection, "doc", str(corpus.ids["docs/a.md"]))
        b = identifier(connection, "doc", str(corpus.ids["docs/b.md"]))
        assert edges.authored_pairs(connection, local_kb=str(corpus.kb_id)) == [(a, b)]
        assert edges.census(connection, local_kb=str(corpus.kb_id))["authored"] == 1

        both = [
            s
            for s in edges.peers(connection, a, kinds=edges.ALL_KINDS, local_kb=str(corpus.kb_id))
            if s.kind == "authored"
        ]
        assert [s.node for s in both] == [b]
        assert both[0].weight == 2.0

        # Symmetric: readable from the end the sidecar did *not* write.
        back = [
            s.node
            for s in edges.peers(connection, b, kinds=edges.ALL_KINDS, local_kb=str(corpus.kb_id))
            if s.kind == "authored"
        ]
        assert back == [a]
    finally:
        connection.close()


def test_an_authored_row_keeps_the_direction_the_sidecar_wrote_it(tmp_path: Path) -> None:
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60)])),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)])),
        ],
    )
    _link(corpus, "docs/b.md", f"pnk://{corpus.kb_id}/{corpus.ids['docs/a.md']}", "cites")
    corpus.sync()

    connection = corpus.open()
    try:
        a = identifier(connection, "doc", str(corpus.ids["docs/a.md"]))
        b = identifier(connection, "doc", str(corpus.ids["docs/b.md"]))
        assert edges.authored_pairs(connection, local_kb=str(corpus.kb_id)) == [(b, a)]
    finally:
        connection.close()


def test_a_cross_kb_authored_row_never_enters_the_channel(tmp_path: Path) -> None:
    """A `doc` node is keyed on the document ULID alone, so only a *local* document has one. An
    outbound link to another KB has a foreign `dst_kb_id` and resolves to nothing — the same
    reason, and in the same direction, as the reverse-scanned rows that carry a foreign `src`."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60)])),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)])),
        ],
    )
    foreign_kb, foreign_doc = mint_kb_id(), mint_doc_id()
    (corpus.root / "pinakes.toml").write_text(
        (corpus.root / "pinakes.toml").read_text(encoding="utf-8")
        + f'\n[[links.kb]]\nname = "far"\nid   = "{foreign_kb}"\npath = "../far"\n',
        encoding="utf-8",
    )
    _link(corpus, "docs/a.md", f"pnk://{foreign_kb}/{foreign_doc}", "cites")
    _link(corpus, "docs/a.md", f"pnk://{corpus.kb_id}/{corpus.ids['docs/b.md']}", "related")
    corpus.sync()

    connection = corpus.open()
    try:
        stored = connection.execute("SELECT count(*) FROM links").fetchone()[0]
        assert stored == 2, "the fixture did not record both authored rows"
        assert len(edges.authored_pairs(connection, local_kb=str(corpus.kb_id))) == 1
    finally:
        connection.close()


# --------------------------------------------------------------------------------------------
# Kind selection — G5's arms are a flag, not a rebuild


def test_dropping_a_kind_removes_it_from_every_read(tmp_path: Path) -> None:
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60), ("Two", "x " * 60)]), tags=("t",)),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)]), tags=("t",)),
        ],
    )
    connection = corpus.open()
    try:
        doc_id = str(corpus.ids["docs/a.md"])
        chunk = identifier(connection, "chunk", edges.chunk_key(doc_id, 0))

        everything = edges.select_kinds()
        without = edges.select_kinds(drop=["sibling"])
        assert "sibling" in everything and "sibling" not in without

        local = str(corpus.kb_id)
        with_sibling = edges.neighbours(connection, chunk, kinds=everything, local_kb=local)
        without_sibling = edges.neighbours(connection, chunk, kinds=without, local_kb=local)
        assert any(s.kind == "sibling" for s in with_sibling)
        assert not any(s.kind == "sibling" for s in without_sibling)
        assert len(without_sibling) < len(with_sibling)
    finally:
        connection.close()


def test_dropping_authored_removes_it_without_a_rederivation(tmp_path: Path) -> None:
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60)])),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)])),
        ],
    )
    _link(corpus, "docs/a.md", f"pnk://{corpus.kb_id}/{corpus.ids['docs/b.md']}", "cites")
    corpus.sync()

    connection = corpus.open()
    try:
        local = str(corpus.kb_id)
        a = identifier(connection, "doc", str(corpus.ids["docs/a.md"]))
        with_authored = edges.peers(connection, a, kinds=edges.select_kinds(), local_kb=local)
        without = edges.peers(
            connection, a, kinds=edges.select_kinds(drop=["authored"]), local_kb=local
        )
        assert [s.kind for s in with_authored].count("authored") == 1
        assert "authored" not in [s.kind for s in without]
    finally:
        connection.close()


def test_an_unknown_kind_name_is_refused_rather_than_dropping_nothing() -> None:
    """`--drop sibbling` that quietly changes nothing is a green run of the arm nobody measured."""
    with pytest.raises(TraversalError) as info:
        edges.select_kinds(drop=["sibbling"])
    assert "sibbling" in str(info.value)
    assert "sibling" in info.value.remedy


def test_every_kind_is_a_census_key_even_at_zero(tmp_path: Path) -> None:
    """A kind missing from a dict is indistinguishable from a kind that derived nothing — and a
    decision has already been taken on a corpus where three of six were silently at zero."""
    corpus = build(tmp_path / "kb", [Doc("docs/a.md", "no headings here at all\n")])
    connection = corpus.open()
    try:
        counts = edges.census(connection, local_kb=str(corpus.kb_id))
        assert set(counts) == set(edges.ALL_KINDS)
        assert counts["in-section"] == 0
        assert counts["shared-tag"] == 0
    finally:
        connection.close()


def test_the_sync_report_prints_every_kind_with_its_wall_clock(tmp_path: Path) -> None:
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60)]), tags=("t",)),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)]), tags=("t",)),
        ],
    )
    report = corpus.sync(rebuild=True)
    assert set(report.edges) == set(edges.ALL_KINDS)
    line = report.edge_line()
    for kind in edges.ALL_KINDS:
        assert f"{kind}=" in line
    assert "edge(s) derived in" in line
    assert "authored read from links" in line
    assert line in report.lines()


# --------------------------------------------------------------------------------------------
# The released surface, and the schema


def test_the_traversal_surface_returns_no_structural_nodes(tmp_path: Path) -> None:
    """Decision 16: `pnk links` serves documents only. A tag, directory, heading or chunk node has
    no `doc_id` and cannot be expressed in the shape L4 pins — so there is no filter to flip."""
    import contextlib
    import io
    import json

    from pinakes.cli import main

    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60), ("Two", "x " * 60)]), tags=("t",)),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)]), tags=("t",)),
        ],
    )
    _link(corpus, "docs/a.md", f"pnk://{corpus.kb_id}/{corpus.ids['docs/b.md']}", "cites")
    corpus.sync()

    connection = corpus.open()
    try:
        edge_count = connection.execute("SELECT count(*) FROM edges").fetchone()[0]
        structural = {
            key for kind in ("tag", "dir", "heading", "chunk") for key in nodes_of(connection, kind)
        }
        documents = {
            str(r[0]) for r in connection.execute("SELECT id FROM documents WHERE state = 'active'")
        }
        authored = {
            str(r[0])
            for r in connection.execute(
                "SELECT dst_doc_id FROM links UNION SELECT src_doc_id FROM links"
            )
        }
    finally:
        connection.close()
    assert edge_count > 0, "no structural edges exist, so this test cannot detect one leaking"
    assert structural

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert main(["links", "docs/a.md", "--kb", str(corpus.root), "--json", "--depth", "3"]) == 0
    payload = json.loads(buffer.getvalue())

    neighbours = payload["neighbours"]
    assert neighbours, "the fixture returned no neighbours, so nothing was checked"
    # `doc_id in documents` is the load-bearing half. Asserting "not a structural node key" would
    # be true by key *format* alone — a tag is a word, a directory is a path, a chunk key carries
    # a `:` — and so could never fail. What can fail is a neighbour no `links` row put there.
    for row in neighbours:
        assert row["doc_id"] in documents
    assert {str(row["doc_id"]) for row in neighbours} <= authored, (
        "a neighbour arrived that no authored link accounts for"
    )


def test_a_schema_version_2_index_is_refused_with_its_remedy(tmp_path: Path) -> None:
    """G3 bumps to 3 and there is no migration machinery, by design. A 2 must refuse and say so."""
    index = tmp_path / ".pinakes" / "index.db"
    connection = store.create(index)
    store.set_meta(connection, {"schema_version": "2"})
    connection.commit()
    connection.close()

    for opener in (store.connect_rw, store.connect_ro):
        with pytest.raises(IndexSchemaError) as info:
            opener(index)
        assert info.value.found == "2"
        assert info.value.expected == 3
        assert "pnk sync --rebuild" in info.value.remedy
        assert "no migration machinery" in info.value.remedy


# --------------------------------------------------------------------------------------------
# The deriver against the instrument the go decision was taken on


def test_the_stored_edge_set_agrees_with_the_probe_the_decision_was_taken_on() -> None:
    """G3 must build the graph G2 measured, not a second graph that happens to be plausible.

    `tools/reachable_ceiling_probe.py` derives the same six relations in memory, written
    independently and against the same two sections of APPROACH. It is throwaway measurement code
    and explicitly *not* this deriver — which is exactly what makes it a useful second opinion:
    the counts agreeing is evidence neither implementation quietly reinterpreted the spec.

    `membership` is absent from the probe (it never needed transit plumbing) and is therefore not
    compared. `authored` is: the probe counts unordered local pairs, this counts resolved `links`
    rows, and on a corpus with no pair linked in both directions those are the same number.
    """
    import importlib.util
    import shutil
    import tempfile

    spec = importlib.util.spec_from_file_location(
        "reachable_ceiling_probe", REPO / "tools" / "reachable_ceiling_probe.py"
    )
    assert spec is not None and spec.loader is not None
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    with tempfile.TemporaryDirectory() as raw:
        workspace = Path(raw)
        shutil.copytree(REPO / "tests" / "demo-kb", workspace / "demo-kb")
        shutil.copytree(REPO / "tests" / "partner-kb", workspace / "partner-kb")
        loaded = load(workspace / "demo-kb")
        sync(loaded, options=SyncOptions(scan_links=True), backend_factory=fake_factory)

        connection = store.connect_ro(loaded.index_path)
        try:
            mine = edges.census(connection, local_kb=str(loaded.kb.id))
            graph = probe.derive(connection, str(loaded.kb.id), kinds=probe.ALL_KINDS)
            theirs = probe.edge_census(graph)
        finally:
            connection.close()

    shared = set(mine) & set(theirs)
    assert shared == set(edges.ALL_KINDS) - {"membership"}, sorted(shared)
    assert {kind: mine[kind] for kind in sorted(shared)} == {
        kind: theirs[kind] for kind in sorted(shared)
    }
    assert sum(theirs[kind] for kind in shared) > 0, "the probe derived nothing to agree about"


def test_a_forked_kb_sharing_a_document_ulid_does_not_forge_a_local_authored_edge(
    tmp_path: Path,
) -> None:
    """`authored_pairs` filters on **both** `kb_id`s, and the `nodes` join is not enough on its own.

    The join looks sufficient — a foreign document ULID has no local `doc` node — right up until
    two KBs share one. Forking a KB does exactly that: copy the directory, mint a new `[kb] id`,
    and every document keeps its permanent ULID. A reverse scan of the fork then writes
    `(fork_kb, D, local_kb, E)` where `D` is *also* one of our documents, and a filter that
    accepted either end would read it as "our D cites E" — an edge nobody authored here, taken
    from precisely the partial view of a foreign graph decision 16 refuses to serve.

    Found by mutation: replacing the `AND` with an `OR` was caught by nothing.
    """
    local = build(
        tmp_path / "local",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60)])),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)])),
        ],
    )
    shared = local.ids["docs/a.md"]

    # The fork: its own KB id, its own copy of a document that kept the original's ULID, and a
    # link from that document into ours. Built with the same builder, so it is a real KB.
    fork = build(
        tmp_path / "fork",
        [Doc("docs/a.md", sectioned("A", [("One", "x " * 60)]), doc_id=shared)],
    )
    _link(fork, "docs/a.md", f"pnk://{local.kb_id}/{local.ids['docs/b.md']}", "cites")
    fork.sync()

    (local.root / "pinakes.toml").write_text(
        (local.root / "pinakes.toml").read_text(encoding="utf-8")
        + f'\n[[links.kb]]\nname = "fork"\nid   = "{fork.kb_id}"\npath = "../fork"\n',
        encoding="utf-8",
    )
    local.sync(scan_links=True)

    connection = local.open()
    try:
        reverse = connection.execute(
            "SELECT src_kb_id, src_doc_id FROM links WHERE origin = 'reverse-scan'"
        ).fetchall()
        assert [(str(r[0]), str(r[1])) for r in reverse] == [(str(fork.kb_id), str(shared))], (
            "the reverse scan did not record the fork's row, so this test asserts nothing"
        )
        assert identifier(connection, "doc", str(shared)), "the shared ULID is a local doc node too"
        assert edges.authored_pairs(connection, local_kb=str(local.kb_id)) == [], (
            "a row whose source lives in the fork was resolved into a local authored edge"
        )
    finally:
        connection.close()


def test_hierarchy_matches_the_naive_prefix_predicate(tmp_path: Path) -> None:
    """The ancestor lookup replaced an every-pair `startswith`, which was quadratic in a document's
    chunk count and took 3.3 s on one 8 000-chunk document. This recomputes the relation the naive
    way, from the same `chunks` rows, and asserts the stored edges are exactly it — so the
    optimisation cannot quietly drop or invent a hierarchy edge.
    """
    body = (
        "# Costs\n\n" + ("a " * 60) + "\n\n"
        "## Detail\n\n" + ("b " * 60) + "\n\n"
        "### Deeper\n\n" + ("c " * 60) + "\n\n"
        "## Other\n\n" + ("d " * 60) + "\n\n"
        "# Costsheet\n\n" + ("e " * 60) + "\n"
    )
    corpus = build(tmp_path / "kb", [Doc("docs/a.md", body)])
    connection = corpus.open()
    try:
        doc_id = str(corpus.ids["docs/a.md"])
        rows_ = chunks_of(connection, doc_id)
        assert len({heading for _, heading in rows_}) >= 4, rows_

        naive = {
            (parent, child)
            for parent, parent_path in rows_
            for child, child_path in rows_
            if parent_path
            and child_path
            and child_path.startswith(parent_path + edges.HEADING_SEPARATOR)
        }
        assert naive, "the fixture has no hierarchy, so the comparison is vacuous"

        stored = {
            (edges.parse_chunk_key(src)[1], edges.parse_chunk_key(dst)[1])
            for _, src, kind, _, dst in rows(connection)
            if kind == "parent-child"
        }
        assert stored == naive
    finally:
        connection.close()


def test_asking_for_authored_without_the_local_kb_is_refused(tmp_path: Path) -> None:
    """Silently skipping the kind is the same defect as a `src`-only read, from the other side.

    G5's gate runs with and without authored edges. A caller who forgets `local_kb=` would get the
    "without" arm while believing it ran the "with" one — and lose the highest-trust edge class
    with nothing said. `select_kinds(drop=["authored"])` is how you mean it.
    """
    corpus = build(tmp_path / "kb", [Doc("docs/a.md", sectioned("A", [("One", "x " * 60)]))])
    connection = corpus.open()
    try:
        node = identifier(connection, "doc", str(corpus.ids["docs/a.md"]))
        with pytest.raises(TraversalError) as info:
            edges.peers(connection, node, kinds=edges.ALL_KINDS)
        assert "local_kb" in info.value.remedy
        with pytest.raises(TraversalError):
            edges.neighbours(connection, node, kinds=edges.ALL_KINDS)
        # Dropping it explicitly is fine, and is the documented way to mean it.
        assert edges.neighbours(connection, node, kinds=edges.select_kinds(drop=["authored"]))
    finally:
        connection.close()


def test_an_empty_tag_is_not_a_shared_value(tmp_path: Path) -> None:
    """`tags: [""]` on two documents would otherwise hub them together at a divisor of two — the
    noise clique damping exists to prevent, built out of nothing at all."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60)]), tags=("", "  ")),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)]), tags=("",)),
        ],
    )
    connection = corpus.open()
    try:
        assert nodes_of(connection, "tag") == []
    finally:
        connection.close()


def test_one_document_repeating_a_tag_mints_no_hub(tmp_path: Path) -> None:
    """The `< 2` rule counts the bucket, and the edge `set` downstream hides a duplicated entry:
    a lone document listing `t` twice looked like a two-member hub, and got a node with one spoke
    and a divisor of 2."""
    corpus = build(
        tmp_path / "kb",
        [Doc("docs/a.md", sectioned("A", [("One", "x " * 60)]), tags=("t", "t"))],
    )
    connection = corpus.open()
    try:
        assert nodes_of(connection, "tag") == []
        assert not [row for row in rows(connection) if row[2] == "shared-tag"]
    finally:
        connection.close()


def test_a_nested_directory_is_its_own_hub(tmp_path: Path) -> None:
    """`co-located` is the immediate directory, never an ancestor: `docs/a.md` and
    `docs/deep/c.md` are not co-located. Pinned because it is a design choice with a plausible
    opposite, and because it is what `posixpath.dirname` happens to give."""
    corpus = build(
        tmp_path / "kb",
        [
            Doc("docs/a.md", sectioned("A", [("One", "x " * 60)])),
            Doc("docs/b.md", sectioned("B", [("One", "y " * 60)])),
            Doc("docs/deep/c.md", sectioned("C", [("One", "z " * 60)])),
            Doc("docs/deep/d.md", sectioned("D", [("One", "w " * 60)])),
        ],
    )
    connection = corpus.open()
    try:
        assert nodes_of(connection, "dir") == ["docs", "docs/deep"]
        docs_hub = identifier(connection, "dir", "docs")
        members = {
            spoke.node for spoke in edges.members(connection, docs_hub, kinds=("co-located",))
        }
        assert members == {
            identifier(connection, "doc", str(corpus.ids[f"docs/{n}.md"])) for n in "ab"
        }
    finally:
        connection.close()


def test_a_heading_containing_the_separator_is_a_known_bound(tmp_path: Path) -> None:
    """A heading titled `A > B` is indistinguishable from the path `A` / `B`, and the ambiguity is
    older than this module: `pinakes.chunk` joins a heading path with `" > "` and stores one string.

    Recorded as a **bound**, not fixed here. A heading containing `>` is ordinary in software
    documentation ("Settings > Advanced"), and the honest repair is storing segments rather than a
    joined string — a `chunks.heading_path` change, which is a schema decision this increment does
    not get to take alone. The test exists so the bound is measured rather than believed, and so it
    fails loudly if `chunk.py` ever starts escaping the separator.
    """
    body = (
        "# A > B\n\n" + ("p " * 60) + "\n\n"
        "## C\n\n" + ("q " * 60) + "\n\n"
        "# A\n\n" + ("r " * 60) + "\n\n"
        "## B\n\n" + ("s " * 60) + "\n"
    )
    corpus = build(tmp_path / "kb", [Doc("docs/a.md", body)])
    connection = corpus.open()
    try:
        doc_id = str(corpus.ids["docs/a.md"])
        headings = [heading for _, heading in chunks_of(connection, doc_id)]
        assert headings.count("A > B") == 2, (
            f"chunk.py no longer collides these two headings ({headings}) — the bound below is "
            "stale and this test should assert the separation instead"
        )
        # One heading node for two unrelated sections, and hierarchy edges between them.
        assert len(nodes_of(connection, "heading")) < len(set(headings))
        assert [row for row in rows(connection) if row[2] == "parent-child"]
    finally:
        connection.close()


def test_the_hierarchy_row_count_is_pinned_because_it_is_the_product_of_two_sections(
    tmp_path: Path,
) -> None:
    """`parent-child` is chunk ↔ chunk by APPROACH §3 — the one relation deliberately *not* hubbed
    — so a multi-chunk ancestor multiplies: ancestor chunks times descendant chunks, per pair of
    related headings. Six chunks under `Top` and four under `Top > Section` is 24 rows from ten
    chunks.

    Pinned rather than fixed: hubbing it would contradict APPROACH §3, and restricting it to the
    immediate parent would narrow the relation the go decision's probe measured. The number is
    here so a reader sees the shape rather than discovering it on a long document, and so an
    accidental change to the relation's arity fails a test.
    """
    lead = "\n\n".join("x " * 200 for _ in range(3))
    section = "\n\n".join("y " * 200 for _ in range(2))
    corpus = build(
        tmp_path / "kb", [Doc("docs/a.md", f"# Top\n\n{lead}\n\n## Section\n\n{section}\n")]
    )
    connection = corpus.open()
    try:
        doc_id = str(corpus.ids["docs/a.md"])
        by_heading: dict[str | None, int] = {}
        for _, heading in chunks_of(connection, doc_id):
            by_heading[heading] = by_heading.get(heading, 0) + 1
        ancestors = by_heading["Top"]
        descendants = by_heading["Top > Section"]
        assert ancestors >= 2 and descendants >= 2, by_heading

        found = len([row for row in rows(connection) if row[2] == "parent-child"])
        assert found == ancestors * descendants, (
            f"{found} parent-child rows for {ancestors} ancestor and {descendants} descendant "
            "chunks — the relation's arity moved"
        )
    finally:
        connection.close()
