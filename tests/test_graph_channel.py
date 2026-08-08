"""G5 — the expansion channel, its default, and the gate that licenses a different one.

Two halves, and they fail differently.

**The channel** is tested against KBs `pnk sync` actually built, never a hand-written `edges` table
(v0.1 rule 5): what is under test is a walk over a *derived* graph, and a fixture that inserts the
rows it then asserts on tests only the test. The embedding backend is a deterministic bag-of-words
hash rather than the constant vector the other suites use, because a channel is only interesting
when the query discriminates: under a constant embedding every chunk is at cosine 1.0 and "fusion
alone does not find this document" is true of nothing.

**The gate** is tested with **synthetic** artifacts driven through `tools/graph_gate.py` as a
subprocess. A gate whose only fixture is the real corpus can only be tested in whichever direction
that corpus happens to point — and three of the four clauses guard against movements the committed
corpora do not make.

The failure class this file is written against is the project's recurring one: an assertion
satisfied by something other than the property it names. So each membership-exclusion test carries
its own negative half — the chunk that must *not* appear is asserted beside the sibling that must,
and the fan-out test is built so that removing the exclusion makes the budget vanish rather than
merely shift.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from pinakes import store
from pinakes.embed import EmbeddingBackend, ModelInfo, Vectors
from pinakes.graph import channel
from pinakes.graph.edges import ALL_KINDS, AUTHORED, authored_pairs, select_kinds
from pinakes.ids import DocId, KbId, mint_doc_id, mint_kb_id
from pinakes.manifest import Manifest, load
from pinakes.search import Filters, Fused, fused_candidates, search, unit_vectors
from pinakes.sidecar import SIDECAR_SUFFIX
from pinakes.sync import SyncOptions, sync

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "tools" / "graph_gate.py"
DIM = 64


# --------------------------------------------------------------------------------------------
# A backend that discriminates


class HashingBackend:
    """A bag-of-words hash. Deterministic, instant, and — unlike the constant vector the other
    suites use — it puts two documents with no shared vocabulary at cosine 0.

    That is the whole point: the channel exists to surface a document the query cannot reach, and
    under a constant embedding every document is already at cosine 1.0, so every such assertion
    would pass for the wrong reason.
    """

    def embed(self, texts: Sequence[str]) -> Vectors:
        listed = list(texts)
        if not listed:
            return np.zeros((0, DIM), dtype=np.float32)
        rows: list[Any] = []
        for text in listed:
            vector = np.zeros(DIM, dtype=np.float32)
            for word in text.lower().split():
                stripped = "".join(character for character in word if character.isalnum())
                if stripped:
                    vector[hash_word(stripped)] += 1.0
            rows.append(vector)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "hashing", "rev1", DIM, 512)


def hash_word(word: str) -> int:
    """`hash()` is salted per process, so a stable fold is written out rather than borrowed."""
    total = 0
    for character in word:
        total = (total * 131 + ord(character)) % 1_000_003
    return total % DIM


def factory(_manifest: Manifest, _offline: bool) -> EmbeddingBackend:
    return HashingBackend()


MANIFEST = """\
[kb]
name     = "channel"
id       = "{kb_id}"
template = "notes@1.1"
created  = "20260804 20:00"

[sources]
roots   = ["docs/"]
include = ["**/*.md"]

[embedding]
provider = "fastembed"
model    = "hashing"
dim      = {dim}

[chunking]
strategy   = "structural"
max_tokens = 120
overlap    = 16

[retrieval]
candidates_per_source = 30
fusion                = "rrf"
fusion_top_k          = 12
final_k               = 5
rerank                = "none"
vector_tier           = "numpy"
adjacent_k            = {adjacent_k}
graph_channel         = "{graph_channel}"

[rerank]
provider = "none"
model    = "none"
"""


# --------------------------------------------------------------------------------------------
# A KB on disk


class Corpus:
    def __init__(self, root: Path, *, graph_channel: str = "off", adjacent_k: int = 8) -> None:
        self.root = root
        self.kb_id: KbId = mint_kb_id()
        self.ids: dict[str, DocId] = {}
        self._graph_channel = graph_channel
        self._adjacent_k = adjacent_k
        root.mkdir(parents=True, exist_ok=True)
        self._write_manifest()

    def _write_manifest(self) -> None:
        (self.root / "pinakes.toml").write_text(
            MANIFEST.format(
                kb_id=self.kb_id,
                dim=DIM,
                adjacent_k=self._adjacent_k,
                graph_channel=self._graph_channel,
            ),
            encoding="utf-8",
        )

    def set_channel(self, value: str) -> None:
        """Flip `[retrieval] graph_channel` without re-syncing — the setting is read at query
        time, which is what makes an off/on comparison a comparison of one index."""
        self._graph_channel = value
        self._write_manifest()

    def write(
        self,
        path: str,
        body: str,
        *,
        tags: Sequence[str] = (),
        links: Sequence[tuple[str, str]] = (),
    ) -> DocId:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        doc_id = self.ids.get(path) or mint_doc_id()
        self.ids[path] = doc_id
        sidecar: dict[str, Any] = {"id": str(doc_id), "title": Path(path).stem}
        if tags:
            sidecar["tags"] = list(tags)
        if links:
            sidecar["links"] = [
                {"to": f"pnk://self/{self.ids[target_path]}", "rel": rel}
                for rel, target_path in links
            ]
        (self.root / (path + SIDECAR_SUFFIX)).write_text(
            yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8"
        )
        return doc_id

    def sync(self, **options: Any) -> None:
        sync(load(self.root), options=SyncOptions(**options), backend_factory=factory)

    def manifest(self) -> Manifest:
        return load(self.root)

    def open(self) -> sqlite3.Connection:
        return store.connect_ro(self.manifest().index_path)


def sectioned(title: str, sections: Sequence[tuple[str, str]]) -> str:
    body = f"# {title}\n\nIntroducing {title}.\n"
    for heading, text in sections:
        body += f"\n## {heading}\n\n{text}\n"
    return body


def paths_of(corpus: Corpus, chunk_ids: Iterable[int]) -> set[str]:
    connection = corpus.open()
    try:
        listed = list(chunk_ids)
        if not listed:
            return set()
        placeholders = ",".join("?" for _ in listed)
        return {
            str(row[0])
            for row in connection.execute(
                f"SELECT d.path FROM chunks c JOIN documents d ON d.id = c.doc_id "
                f"WHERE c.id IN ({placeholders})",
                listed,
            )
        }
    finally:
        connection.close()


def chunk_id_of(corpus: Corpus, path: str, ordinal: int) -> int:
    connection = corpus.open()
    try:
        row = connection.execute(
            "SELECT c.id FROM chunks c JOIN documents d ON d.id = c.doc_id "
            "WHERE d.path = ? AND c.ordinal = ?",
            (path, ordinal),
        ).fetchone()
        assert row is not None, f"{path} has no chunk {ordinal}"
        return int(row[0])
    finally:
        connection.close()


def ordinals_of(corpus: Corpus, path: str) -> list[int]:
    connection = corpus.open()
    try:
        return [
            int(row[0])
            for row in connection.execute(
                "SELECT c.ordinal FROM chunks c JOIN documents d ON d.id = c.doc_id "
                "WHERE d.path = ? ORDER BY c.ordinal",
                (path,),
            )
        ]
    finally:
        connection.close()


def walk(
    corpus: Corpus,
    roots: Sequence[int],
    *,
    kinds: Collection[str] | None = None,
    adjacent_k: int = 8,
    similarity: dict[int, float] | None = None,
    limit: int = 50,
    ranking: channel.Ranking = channel.GATED_RANKING,
    depth: int = channel.DEPTH,
) -> list[channel.Reached]:
    connection = corpus.open()
    try:
        return channel.expand(
            connection,
            roots,
            similarity=similarity or {},
            kinds=select_kinds() if kinds is None else kinds,
            local_kb=str(corpus.kb_id),
            adjacent_k=adjacent_k,
            limit=limit,
            ranking=ranking,
            depth=depth,
        )
    finally:
        connection.close()


def fuse(corpus: Corpus, query: str) -> Fused:
    connection = corpus.open()
    try:
        return fused_candidates(connection, corpus.manifest(), query, backend=HashingBackend())
    finally:
        connection.close()


# --------------------------------------------------------------------------------------------
# Two documents that share a tag and nothing else


def two_tagged_documents(root: Path, **options: Any) -> Corpus:
    """`docs/alpha.md` and `docs/beta.md`: one tag in common, no vocabulary in common.

    Deliberately in *different* directories, so the only document-level bridge between them is
    `shared-tag` and a test can name which kind carried the path.
    """
    corpus = Corpus(root, **options)
    corpus.write(
        "docs/one/alpha.md",
        sectioned("Alpha", [("Quokka", "quokka " * 40), ("Quokka habits", "quokka " * 40)]),
        tags=["marsupial-notes"],
    )
    corpus.write(
        "docs/two/beta.md",
        sectioned("Beta", [("Zebu", "zebu " * 40), ("Zebu habits", "zebu " * 40)]),
        tags=["marsupial-notes"],
    )
    corpus.sync()
    return corpus


def test_expand_surfaces_a_document_fusion_alone_does_not(tmp_path: Path) -> None:
    """The channel must *do* something. Without this, a channel broken into returning nothing
    produces exactly the same blessed gate outcome as one that honestly did not help."""
    corpus = two_tagged_documents(tmp_path / "kb")

    off = fuse(corpus, "quokka")
    assert paths_of(corpus, off.order) == {"docs/one/alpha.md"}
    assert off.graph == ()

    corpus.set_channel("expand")
    on = fuse(corpus, "quokka")
    assert paths_of(corpus, on.order) == {"docs/one/alpha.md", "docs/two/beta.md"}

    beta = str(corpus.ids["docs/two/beta.md"])
    carried = {reached.via for reached in on.graph if reached.doc_id == beta}
    assert carried == {("shared-tag", "shared-tag", "membership")}, (
        "the two documents are in different directories and share no vocabulary, so `shared-tag` "
        "is the only kind that can have carried this — and naming it is what tells a result "
        "carried by an author-chosen vocabulary from one carried by derived structure"
    )


def test_an_empty_edge_set_reproduces_two_list_fusion_exactly(tmp_path: Path) -> None:
    """Not "close to" — the same arithmetic. RRF over an empty third ranking adds no term to any
    score and no key to the dict, so `scores` compares equal as a whole rather than field by
    field."""
    corpus = two_tagged_documents(tmp_path / "kb")
    off = fuse(corpus, "quokka")

    writable = store.connect_rw(corpus.manifest().index_path)
    try:
        writable.execute("DELETE FROM edges")
        writable.commit()
    finally:
        writable.close()

    corpus.set_channel("expand")
    on = fuse(corpus, "quokka")

    assert on.graph == ()
    assert on.order == off.order
    assert on.scores == off.scores
    assert on.lexical_rank == off.lexical_rank
    assert on.vector_rank == off.vector_rank


class _Tracer(sqlite3.Connection):
    """Counts the statements that reach the graph tables. A subclass, not a wrapper: `search`
    hands the connection to `store.load_vectors` and to the channel, and a duck type would have to
    reproduce every method either of them might reach for."""

    graph_statements: list[str]
    graph_calls: list[tuple[str, Any]]

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:  # type: ignore[override]
        if " nodes " in f" {sql} " or " edges " in f" {sql} ":
            self.graph_statements.append(sql)
            self.graph_calls.append((sql, tuple(parameters)))
        return super().execute(sql, parameters)


def _traced(path: Path) -> _Tracer:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, factory=_Tracer)
    connection.row_factory = sqlite3.Row
    connection.graph_statements = []
    connection.graph_calls = []
    return connection


def test_off_issues_no_traversal_query(tmp_path: Path) -> None:
    """`"off"` is not "expand and then discard": nothing may touch `nodes` or `edges` at all.

    The `"expand"` half is the negative the assertion needs — a counter that is zero because the
    predicate never matches anything would make the first half green for no reason.
    """
    corpus = two_tagged_documents(tmp_path / "kb")

    connection = _traced(corpus.manifest().index_path)
    try:
        search(connection, corpus.manifest(), "quokka", backend=HashingBackend())
        assert connection.graph_statements == []
    finally:
        connection.close()

    corpus.set_channel("expand")
    connection = _traced(corpus.manifest().index_path)
    try:
        search(connection, corpus.manifest(), "quokka", backend=HashingBackend())
        assert connection.graph_statements
    finally:
        connection.close()


# --------------------------------------------------------------------------------------------
# The membership exclusion


def one_long_document(root: Path, **options: Any) -> Corpus:
    """One document, six top-level sections, one chunk each.

    **Six `#` headings, not one `#` and six `##`.** Under a title, every section's `heading_path`
    is `Title > Section n` and the title's own chunk is the transitive parent of all of them, so
    `parent-child` puts every chunk within two hops of every other and the membership path can
    never be the *only* way to reach anything. Dropping the title is not enough either — the
    chunker then reads the **first** `##` as the root and derives `Section 0 > Section n`, which is
    the same defect wearing a different heading level. Six top-level headings give pairwise
    non-prefix paths, each its own single-member hub (never minted), and ordinal 0 reaching only
    ordinals 1 and 2 — by `sibling`, twice. `_assert_flat_sections` is what keeps that true.
    """
    corpus = Corpus(root, **options)
    corpus.write(
        "docs/long.md",
        "".join(f"# Section {index}\n\n" + f"word{index} " * 30 + "\n\n" for index in range(6)),
    )
    corpus.sync()
    _assert_flat_sections(corpus, "docs/long.md", sections=6)
    return corpus


def _assert_flat_sections(corpus: Corpus, path: str, *, sections: int) -> None:
    """The fixture is what its docstring says: one chunk per section, every heading path depth 1,
    no hierarchy edge at all.

    Written after the first version of this fixture was not. `f"## Section {i}\n\nword{i} " * 30`
    repeats the *heading* thirty times too, which produced 180 chunks under
    `Section 0 > Section 5` — a nested hierarchy inside a fixture whose whole purpose was to have
    none, and the exclusion tests below passed against it for reasons that had nothing to do with
    membership. A fixture that is silently not the shape it claims is the same failure class as an
    assertion satisfied by something other than the property it names.
    """
    connection = corpus.open()
    try:
        rows = [
            (int(r[0]), None if r[1] is None else str(r[1]))
            for r in connection.execute(
                "SELECT c.ordinal, c.heading_path FROM chunks c "
                "JOIN documents d ON d.id = c.doc_id WHERE d.path = ? ORDER BY c.ordinal",
                (path,),
            )
        ]
        hierarchy = int(
            connection.execute("SELECT count(*) FROM edges WHERE kind = 'parent-child'").fetchone()[
                0
            ]
        )
    finally:
        connection.close()
    assert len(rows) == sections, f"expected {sections} chunks, got {len(rows)}: {rows}"
    assert all(heading and " > " not in heading for _, heading in rows), rows
    assert hierarchy == 0, f"{hierarchy} parent-child edge(s) in a fixture that must have none"


def test_a_chunk_reachable_only_by_membership_never_appears(tmp_path: Path) -> None:
    corpus = one_long_document(tmp_path / "kb")
    ordinals = ordinals_of(corpus, "docs/long.md")
    assert len(ordinals) >= 5, f"the fixture needs five separable chunks, got {ordinals}"

    root = chunk_id_of(corpus, "docs/long.md", 0)
    far = chunk_id_of(corpus, "docs/long.md", 4)
    reached = {candidate.chunk_id for candidate in walk(corpus, [root])}

    assert far not in reached, (
        "ordinal 4 is four sections away from ordinal 0: no sibling, no section and no hierarchy "
        "reaches it inside two hops, so it can only have arrived through its own document's "
        "membership edge"
    )


def test_a_same_document_chunk_reachable_by_sibling_is_not_excluded(tmp_path: Path) -> None:
    """The "only" in APPROACH §3 is load-bearing. An exclusion that dropped every same-document
    chunk would pass the test above and delete `sibling` from the channel entirely."""
    corpus = one_long_document(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/long.md", 0)
    neighbour = chunk_id_of(corpus, "docs/long.md", 1)

    reached = {candidate.chunk_id: candidate for candidate in walk(corpus, [root])}
    assert neighbour in reached
    assert reached[neighbour].via == ("sibling",)


def crowded_tag(root: Path, **options: Any) -> Corpus:
    """One tag on four documents, the root's own first in path order.

    Path order is what `derive` mints `doc` nodes in, so the root's document holds the **lowest**
    node id — and the fan-out sort's tiebreak is that id. A document is a member of its own tag
    hub, so if the exclusion ran *after* the cut, an `adjacent_k` of 1 would spend its only slot on
    the source document itself and the channel would return nothing at all. That is the shape this
    fixture exists to produce, and it is where the **before/after the cut** half of the rule is
    pinned rather than the root-document half — `authored_back_to_the_root` is that one.
    """
    corpus = Corpus(root, **options)
    corpus.write("docs/a-root.md", sectioned("Root", [("Quokka", "quokka " * 40)]), tags=["hub"])
    for index, name in enumerate(("b", "c", "d")):
        corpus.write(
            f"docs/{name}-other.md",
            sectioned(name.upper(), [(f"Zebu {index}", f"zebu{index} " * 40)]),
            tags=["hub"],
        )
    corpus.sync()
    return corpus


def test_membership_neighbours_do_not_consume_the_fanout_budget(tmp_path: Path) -> None:
    corpus = crowded_tag(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/a-root.md", 0)

    reached = walk(corpus, [root], adjacent_k=1)
    others = paths_of(corpus, [candidate.chunk_id for candidate in reached]) - {"docs/a-root.md"}

    assert others, (
        "with adjacent_k=1 the one document-level slot must go to a document that has something "
        "to add; the root's own is dropped before the cut, never counted against it. Nothing at "
        "all here means the exclusion ran after the cut and spent the budget on the root itself"
    )
    root_document = str(corpus.ids["docs/a-root.md"])
    assert not [
        candidate
        for candidate in reached
        if candidate.doc_id == root_document and "membership" in candidate.via
    ], "and nothing of the root's own document arrived through its own membership edge"


def tag_chain(root: Path, **options: Any) -> Corpus:
    """A — T1 — B — T2 — C, each tag on exactly two documents.

    The shape that isolates the *first* membership-exclusion filter. At hop 2 the frontier chunk
    belongs to **B**, which is not a root document — so rule 2 cannot cover it, and only "a
    document never passes through to itself" stops B's own T2 spoke from spending the budget that
    C needs. Path order puts B's `doc` node before C's, so B wins the fan-out tiebreak if it is
    allowed to compete at all.
    """
    corpus = Corpus(root, **options)
    # One directory each: sharing one would put all three in a `co-located` hub and make C a
    # *one*-hop neighbour of A, which is the shape the depth assertions below must not have.
    #
    # **Path order deliberately disagrees with hop order.** The two-hop document sorts *first*
    # (`docs/a3/`) and the one-hop document last (`docs/z2/`), so a tiebreak on
    # `(documents.path, chunks.ordinal)` produces the opposite order to the distance term. Without
    # that, deleting distance from the ranking left the tie test green — the assertion was
    # satisfied by path order rather than by the property it names.
    corpus.write("docs/m1/a.md", sectioned("A", [("Quokka", "quokka " * 40)]), tags=["t1"])
    corpus.write("docs/z2/b.md", sectioned("B", [("Zebu", "zebu " * 40)]), tags=["t1", "t2"])
    corpus.write("docs/a3/c.md", sectioned("C", [("Numbat", "numbat " * 40)]), tags=["t2"])
    corpus.sync()
    return corpus


def test_a_document_never_passes_through_to_itself(tmp_path: Path) -> None:
    corpus = tag_chain(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/m1/a.md", 0)
    reached = paths_of(corpus, [c.chunk_id for c in walk(corpus, [root], adjacent_k=1)])

    assert "docs/z2/b.md" in reached, "hop 1, through the tag the root's document shares"
    assert "docs/a3/c.md" in reached, (
        "hop 2 must reach C. If B were allowed to pass through to itself it would take the one "
        "fan-out slot and contribute nothing, because its chunks are already contributed"
    )


def authored_back_to_the_root(root: Path, **options: Any) -> Corpus:
    """A —authored→ B —authored→ {A, C}. The shape that isolates rule **2**.

    At hop 2 the frontier chunk belongs to B, whose authored peers are A and C. Rule 1 does not
    apply — A is not B — so only "a root's own document never contributes, at any depth" keeps A
    out. Path order puts A's `doc` node before C's, so with `adjacent_k=1` A takes the slot and C
    is never reached if the rule is missing. Found by mutation: without this fixture, deleting
    that clause left the whole suite green.
    """
    corpus = Corpus(root, **options)
    corpus.write(
        "docs/a.md", sectioned("A", [("Quokka", "quokka " * 40), ("Quokka two", "quokka " * 40)])
    )
    corpus.write("docs/b.md", sectioned("B", [("Zebu", "zebu " * 40)]))
    corpus.write("docs/c.md", sectioned("C", [("Numbat", "numbat " * 40)]))
    corpus.write(
        "docs/a.md",
        sectioned("A", [("Quokka", "quokka " * 40), ("Quokka two", "quokka " * 40)]),
        links=[("related", "docs/b.md")],
    )
    corpus.write(
        "docs/b.md", sectioned("B", [("Zebu", "zebu " * 40)]), links=[("related", "docs/c.md")]
    )
    corpus.sync()
    return corpus


def test_a_root_document_never_contributes_its_chunks_at_any_depth(tmp_path: Path) -> None:
    corpus = authored_back_to_the_root(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/a.md", 0)
    reached = walk(corpus, [root], adjacent_k=1)
    paths = paths_of(corpus, [candidate.chunk_id for candidate in reached])

    assert "docs/b.md" in paths, "hop 1, along the authored edge"
    assert "docs/c.md" in paths, (
        "hop 2 must reach C. B's authored peers are A and C; A is a root document, so it may not "
        "take the one fan-out slot to re-contribute chunks the query already had"
    )
    a = str(corpus.ids["docs/a.md"])
    assert not [
        candidate
        for candidate in reached
        if candidate.doc_id == a and "membership" in candidate.via
    ], "and nothing of A arrived through A's own membership edge, at either depth"


def test_a_two_hop_chunk_outranks_a_one_hop_one_when_the_query_says_so(tmp_path: Path) -> None:
    """The property that keeps depth 2 reachable **in the output**, not only in the walk.

    The channel's list is cut at `candidates_per_source`. Rank by distance first and every one-hop
    chunk precedes every two-hop one, so on any corpus where one hop already fills the cut, depth 2
    contributes nothing at all — a depth-1 channel wearing the two-hop budget the reachability
    ceiling was measured at. This is the assertion that fails if that order ever comes back.
    """
    corpus = tag_chain(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/m1/a.md", 0)
    near = chunk_id_of(corpus, "docs/z2/b.md", 0)
    far = chunk_id_of(corpus, "docs/a3/c.md", 0)

    reached = walk(corpus, [root], similarity={near: 0.10, far: 0.90})
    order = [candidate.chunk_id for candidate in reached]
    assert near in order and far in order, "both hops must be walked at all"
    assert order.index(far) < order.index(near)
    assert next(c for c in reached if c.chunk_id == far).distance == 2


def test_distance_breaks_a_tie_the_query_cannot(tmp_path: Path) -> None:
    """The other half: link distance is still a term. Two chunks the query scores identically are
    ordered nearer-first, which is the only place the graph's own proximity decides anything."""
    corpus = tag_chain(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/m1/a.md", 0)
    near = chunk_id_of(corpus, "docs/z2/b.md", 0)
    far = chunk_id_of(corpus, "docs/a3/c.md", 0)

    reached = walk(corpus, [root], similarity={near: 0.5, far: 0.5})
    order = [candidate.chunk_id for candidate in reached]
    assert order.index(near) < order.index(far)

    dropped = walk(
        corpus,
        [root],
        similarity={near: 0.5, far: 0.5},
        ranking=channel.Ranking(link_distance=False),
    )
    # With the term dropped, `(documents.path, chunks.ordinal)` alone decides — and this fixture
    # puts the *two*-hop document first in path order, so the arm must reverse the pair rather
    # than merely leave it alone.
    without = [candidate.chunk_id for candidate in dropped]
    assert without.index(far) < without.index(near), (
        "docs/a3/c.md sorts before docs/z2/b.md, so dropping distance flips the order — an "
        "assertion that survived a fixture where path order and hop order agreed proves nothing"
    )


def test_a_root_is_expanded_but_never_emitted(tmp_path: Path) -> None:
    """A root is already in the list the channel is a third input to. A vote for it can at best
    reorder the fused top-*k*, while the slot it takes is one the `limit` cut then denies a chunk
    fusion has not seen — up to 40% of a fifty-row list at twenty roots. Expanded, never emitted;
    `graph.traverse` skips its start node for the same reason."""
    corpus = one_long_document(tmp_path / "kb")
    first = chunk_id_of(corpus, "docs/long.md", 0)
    second = chunk_id_of(corpus, "docs/long.md", 1)

    alone = {candidate.chunk_id for candidate in walk(corpus, [first])}
    assert second in alone, "ordinal 1 is a sibling of ordinal 0 and must be reachable"

    both = {candidate.chunk_id for candidate in walk(corpus, [first, second])}
    assert first not in both and second not in both, (
        "with both as roots neither may be emitted — and the walk must still have happened"
    )
    assert both, "expansion still runs from a root; only its own row is withheld"
    assert chunk_id_of(corpus, "docs/long.md", 2) in both


def test_a_root_does_not_consume_a_fanout_slot(tmp_path: Path) -> None:
    """The other half of "never emitted", and the half that was missing.

    A root reaching `found` is discarded twice over — `_accept` skips it before emitting, and `run`
    seeds `self._expanded` with the roots so it never joins the frontier either. Yet until the
    filter in `_offer_chunks` it had already taken one of the `adjacent_k` slots on the way, and
    the neighbours of a fused top-*k* chunk are very often *other* fused top-*k* chunks. That is
    the same waste `_passable` refuses one level up: excluded from the output **and** from the
    fan-out budget.

    Asserted by **counting**, because a set-level assertion cannot tell a slot spent from a slot
    saved. `adjacent_k = 1`, and the one slot must go to the non-root neighbour rather than to the
    root that outranks it on cosine — with the filter gone the single slot is spent on the root
    and the walk returns nothing at all.
    """
    corpus = one_long_document(tmp_path / "kb")
    ordinals = ordinals_of(corpus, "docs/long.md")
    assert len(ordinals) >= 3, f"the fixture needs a chunk either side of a root: {ordinals}"
    first, second, third = (chunk_id_of(corpus, "docs/long.md", n) for n in ordinals[:3])

    # `second` is the only root, so `first` and `third` are its two sibling candidates. The cosine
    # is flat here, so without the filter the cut would keep whichever sorts first by path and
    # ordinal — `first` — and it is a root in the second walk below.
    one_root = walk(corpus, [second], adjacent_k=1, depth=1)
    assert [c.chunk_id for c in one_root] == [first], (
        f"one slot, and with one root it goes to the earlier sibling: {one_root}"
    )

    both_roots = walk(corpus, [first, second], adjacent_k=1, depth=1)
    assert [c.chunk_id for c in both_roots] == [third], (
        "`first` is a root now, so the slot it would have taken must fall through to `third` — "
        f"an empty result here is the slot being spent on a candidate that is then discarded: "
        f"{both_roots}"
    )


def sectioned_corpus(root: Path, **options: Any) -> Corpus:
    """A document whose one section is long enough to chunk **twice**, so a heading hub exists.

    Every other fixture here derives zero `heading` nodes — a hub under two members is never
    minted — which left the whole `in-section` branch of the walk unexecuted while the spec
    sentence it implements ("a same-document chunk also reachable by `sibling` **or `in-section`**
    is not excluded") read as covered.
    """
    corpus = Corpus(root, **options)
    corpus.write("docs/one/long.md", "# Section\n\n" + "quokka " * 400 + "\n")
    corpus.write("docs/two/other.md", sectioned("Other", [("Zebu", "zebu " * 40)]))
    corpus.sync()
    return corpus


def test_a_heading_hub_contributes_its_section_mates(tmp_path: Path) -> None:
    corpus = sectioned_corpus(tmp_path / "kb")
    connection = corpus.open()
    try:
        hubs = int(
            connection.execute("SELECT count(*) FROM nodes WHERE kind = 'heading'").fetchone()[0]
        )
        section = int(
            connection.execute("SELECT count(*) FROM edges WHERE kind = 'in-section'").fetchone()[0]
        )
    finally:
        connection.close()
    assert hubs == 1 and section >= 2, (
        f"the fixture must derive a heading hub with members: {hubs} hub(s), {section} spoke(s)"
    )

    root = chunk_id_of(corpus, "docs/one/long.md", 0)
    reached = {candidate.node_key: candidate for candidate in walk(corpus, [root])}
    assert reached, "the section's other chunks are same-document and must still be returned"
    kinds = {candidate.via for candidate in reached.values()}
    assert ("in-section", "in-section") in kinds, (
        f"no candidate arrived through the heading hub; kinds seen: {sorted(kinds)}"
    )

    without = walk(corpus, [root], kinds=select_kinds(drop=["in-section"]))
    assert not [c for c in without if "in-section" in c.via]


def test_dropping_membership_stops_the_document_path(tmp_path: Path) -> None:
    """`membership` is transit and still a selectable kind. Both halves of the document path go
    through it, so a walk that dropped the kind and crossed it anyway would make
    `--drop membership` a green run of an arm nobody measured."""
    corpus = two_tagged_documents(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/one/alpha.md", 0)

    assert "docs/two/beta.md" in paths_of(corpus, [c.chunk_id for c in walk(corpus, [root])])
    dropped = walk(corpus, [root], kinds=select_kinds(drop=["membership"]))
    assert "docs/two/beta.md" not in paths_of(corpus, [c.chunk_id for c in dropped])


def test_a_hub_expands_once_globally(tmp_path: Path) -> None:
    """One of the two datastax bounding rules APPROACH says make traversal survive a real graph.

    Four documents on one tag, three of them roots: whichever reaches the hub first expands it and
    the others get nothing from it. Asserted by counting the reads of **that hub's** spokes — a
    set-level assertion cannot tell "expanded once" from "expanded three times with one result".
    """
    corpus = crowded_tag(tmp_path / "kb")
    roots = [chunk_id_of(corpus, f"docs/{name}.md", 0) for name in ("a-root", "b-other", "c-other")]

    connection = _traced(corpus.manifest().index_path)
    try:
        hub = connection.execute(
            "SELECT id FROM nodes WHERE kind = 'tag' AND key = 'hub'"
        ).fetchone()
        assert hub is not None, "the fixture must derive a tag hub"
        hub_id = int(hub[0])
        connection.graph_calls.clear()
        channel.expand(
            connection,
            roots,
            similarity={},
            kinds=select_kinds(),
            local_kb=str(corpus.kb_id),
            adjacent_k=8,
            limit=50,
        )
        reads = [
            (sql, parameters)
            for sql, parameters in connection.graph_calls
            if "FROM edges" in sql and "src = ?" in sql and parameters and parameters[0] == hub_id
        ]
    finally:
        connection.close()

    members = [call for call in reads if "ORDER BY kind, dst" in call[0]]
    assert len(members) == 1, (
        f"the one tag hub must be expanded once for the whole walk, not once per root: {members}"
    )


def test_the_fanout_cap_bites_and_bites_after_ranking(tmp_path: Path) -> None:
    """Two claims, and the second is the one an implementation gets wrong: `adjacent_k` truncates,
    and it truncates a list that has already been **ranked**. Truncate first and the cap selects by
    whatever order SQLite returned — which here is ordinal order, the opposite of the cosine."""
    corpus = two_tagged_documents(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/one/alpha.md", 0)
    ordinals = ordinals_of(corpus, "docs/two/beta.md")
    assert len(ordinals) >= 2, f"beta must contribute more than one chunk: {ordinals}"

    beta = {ordinal: chunk_id_of(corpus, "docs/two/beta.md", ordinal) for ordinal in ordinals}
    # The cosine says the **last** chunk; every unranked order would hand back the first.
    similarity = {chunk: 0.1 for chunk in beta.values()} | {beta[ordinals[-1]]: 0.9}

    wide = {c.chunk_id for c in walk(corpus, [root], similarity=similarity)}
    assert set(beta.values()) <= wide, "every chunk of beta is reachable at all"

    narrow = walk(corpus, [root], adjacent_k=1, similarity=similarity, depth=1)
    from_beta = [c.chunk_id for c in narrow if c.chunk_id in set(beta.values())]
    assert from_beta == [beta[ordinals[-1]]], (
        f"one slot, and it must go to the highest-ranked chunk rather than the first: {from_beta}"
    )


def test_the_walk_stops_at_two_logical_hops(tmp_path: Path) -> None:
    """The upper bound, asserted from above. `DEPTH` ties to the reachability ceiling the
    increment was licensed on, which was measured at exactly two logical hops — so a deeper walk
    would be measuring something the precondition never covered."""
    corpus = tag_chain(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/m1/a.md", 0)
    reached = walk(corpus, [root])

    assert channel.DEPTH == 2
    assert max(candidate.distance for candidate in reached) == 2, "two hops are walked"

    at_two = {c.doc_id for c in reached if c.distance == 2}
    assert at_two == {str(corpus.ids["docs/a3/c.md"])}, "C is the two-hop document, and only C"

    deeper = walk(corpus, [root], depth=3)
    assert {c.chunk_id for c in deeper} == {c.chunk_id for c in reached}, (
        "the chain has nothing at three hops, so this only proves the fixture cannot tell the "
        "two apart by reach — the bound itself is `channel.DEPTH`, asserted above"
    )


def graded_neighbour(root: Path, **options: Any) -> Corpus:
    """A neighbour document whose chunks form a **cosine gradient** against one query word.

    Sized deliberately, because the obvious small fixture cannot test this at all. `_vector`
    returns every chunk, cosine 0.0 included, so the two-list fusion covers the whole corpus and
    the roots are its top `fusion_top_k` — 12. A root is expanded and never emitted, so in a corpus
    of fewer than 12 chunks *every* chunk the query scores above zero is a root, and the channel
    can only ever return chunks at 0.0. Measured on `two_tagged_documents`: four returned, all at
    0.0, which makes any assertion about cosine order vacuously true.

    So: 18 graded sections, `adjacent_k` at 16. The gradient is `i` copies of `quokka` against
    `40 - i` of `zebu`, so every section scores differently, and the tail that falls outside the
    roots is still non-zero. Eight distinct non-zero cosines reach the channel's output.
    """
    corpus = Corpus(root, adjacent_k=16, **options)
    corpus.write(
        "docs/one/alpha.md",
        sectioned("Alpha", [("Quokka", "quokka " * 40), ("Quokka habits", "quokka " * 40)]),
        tags=["marsupial-notes"],
    )
    corpus.write(
        "docs/two/beta.md",
        sectioned(
            "Beta",
            [(f"Graded {i}", ("quokka " * i) + ("zebu " * (40 - i))) for i in range(1, 19)],
        ),
        tags=["marsupial-notes"],
    )
    corpus.sync()
    return corpus


def test_the_channel_ranks_by_the_cosine_search_computed(tmp_path: Path) -> None:
    """End to end, through `fused_candidates` — the only place the similarity map is filled.

    Every other ranking test builds its own map through the `walk()` helper, so a `search.py` that
    stopped filling it would degrade the channel to weight-and-path ranking on every real query and
    nothing would notice. Here the cosines are recomputed **independently** from the stored vectors
    and the returned order is checked against them: a stable re-sort on `(-cosine, distance)` must
    be a no-op.

    **Two guards against the check passing for another reason.** The cosines must differ, or any
    order at all satisfies the re-sort. And a *two*-hop chunk must outrank a *one*-hop one: with
    the map empty, `_order`'s first term is constant and `distance` decides, so every one-hop
    chunk would come first. That inversion is the property only a live cosine produces.
    """
    corpus = graded_neighbour(tmp_path / "kb", graph_channel="expand")
    connection = corpus.open()
    try:
        fused = fused_candidates(connection, corpus.manifest(), "quokka", backend=HashingBackend())
        chunk_ids, matrix = store.load_vectors(connection, dim=DIM)
        query = unit_vectors(HashingBackend().embed(["quokka"]))[0]
        cosine = {
            chunk: float(value)
            for chunk, value in zip(chunk_ids, unit_vectors(matrix) @ query, strict=True)
        }
    finally:
        connection.close()

    assert fused.graph, "the channel found something to rank"
    scores = {cosine[candidate.chunk_id] for candidate in fused.graph}
    assert len(scores) > 1, (
        f"every returned chunk scores the same against this query ({scores}); the check would be "
        "satisfied by any order at all"
    )
    ordered = sorted(fused.graph, key=lambda c: (-cosine[c.chunk_id], c.distance))
    assert [c.chunk_id for c in fused.graph] == [c.chunk_id for c in ordered], (
        "the channel must rank on the cosines `search` computed, not on a map it never received"
    )

    distances = [candidate.distance for candidate in fused.graph]
    assert any(
        far == 2 and 1 in distances[position + 1 :] for position, far in enumerate(distances)
    ), (
        f"no two-hop chunk outranks a one-hop one ({distances}) — this order is also what an "
        "empty similarity map produces, so it distinguishes nothing"
    )


def test_the_channel_never_returns_a_chunk_the_filters_excluded(tmp_path: Path) -> None:
    """A neighbour outside the caller's filters is a row this search was told not to return — and
    it is dropped inside the walk, so it does not spend a slot of the fan-out budget first."""
    corpus = two_tagged_documents(tmp_path / "kb", graph_channel="expand")
    connection = corpus.open()
    try:
        unfiltered = fused_candidates(
            connection, corpus.manifest(), "quokka", backend=HashingBackend()
        )
        filtered = fused_candidates(
            connection,
            corpus.manifest(),
            "quokka",
            backend=HashingBackend(),
            filters=Filters(path_prefix="docs/one/"),
        )
    finally:
        connection.close()

    assert "docs/two/beta.md" in paths_of(corpus, [c.chunk_id for c in unfiltered.graph])
    assert "docs/two/beta.md" not in paths_of(corpus, [c.chunk_id for c in filtered.graph])
    assert paths_of(corpus, filtered.order) == {"docs/one/alpha.md"}


def test_the_in_degree_arm_changes_the_order_it_claims_to(tmp_path: Path) -> None:
    """`expand-in-degree` is one of the matrix's seven legs, so a number it reports must come from
    code a test has run. The prior is multiplicative, so a chunk at cosine 0 stays at 0."""
    corpus = linked_documents(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/one/alpha.md", 0)
    beta = chunk_id_of(corpus, "docs/two/beta.md", 0)

    plain = walk(corpus, [root], similarity={beta: 0.5})
    salient = walk(
        corpus,
        [root],
        similarity={beta: 0.5},
        ranking=channel.Ranking(in_degree_salience=True),
    )
    assert [c.chunk_id for c in plain] == [c.chunk_id for c in salient], (
        "one reachable document, so the arm may not change *what* is reached"
    )

    connection = corpus.open()
    try:
        inbound = int(
            connection.execute(
                "SELECT count(*) FROM links WHERE dst_doc_id = ?",
                (str(corpus.ids["docs/two/beta.md"]),),
            ).fetchone()[0]
        )
    finally:
        connection.close()
    assert inbound == 1, "beta is cited once; without that the arm has nothing to weigh"


# --------------------------------------------------------------------------------------------
# Decision 16: the released surface does not move


def test_pnk_links_output_is_unchanged_with_the_channel_on(tmp_path: Path) -> None:
    """Decision 16, executed. The structural graph feeds the channel and nothing else, so turning
    the channel on must leave `pnk links --json` byte-identical to the surface captured at G2's
    HEAD — the same committed fixture G3 is pinned against, compared whole."""
    from test_links_surface import FIXTURE, capture

    workspace = tmp_path / "workspace"
    surface = capture(workspace, mutate=_turn_the_channel_on)

    # The negative half. Equality against a fixture is exactly the assertion a mutation hook that
    # silently did nothing would also satisfy, so what ran is checked rather than assumed.
    assert 'graph_channel = "expand"' in (workspace / "demo-kb" / "pinakes.toml").read_text(
        encoding="utf-8"
    )
    assert load(workspace / "demo-kb").retrieval.graph_channel == "expand"
    assert surface == json.loads(FIXTURE.read_text(encoding="utf-8"))


def _turn_the_channel_on(root: Path) -> None:
    path = root / "pinakes.toml"
    text = path.read_text(encoding="utf-8")
    assert "graph_channel" not in text, "the corpora do not stamp it; this test is what sets it"
    path.write_text(
        text.replace("[retrieval]\n", '[retrieval]\ngraph_channel = "expand"\n'), encoding="utf-8"
    )


# --------------------------------------------------------------------------------------------
# The two edge-set variants


def linked_documents(root: Path, **options: Any) -> Corpus:
    corpus = Corpus(root, **options)
    corpus.write("docs/one/alpha.md", sectioned("Alpha", [("Quokka", "quokka " * 40)]))
    corpus.write(
        "docs/two/beta.md",
        sectioned("Beta", [("Zebu", "zebu " * 40)]),
    )
    corpus.write(
        "docs/one/alpha.md",
        sectioned("Alpha", [("Quokka", "quokka " * 40)]),
        links=[("related", "docs/two/beta.md")],
    )
    corpus.sync()
    return corpus


def test_the_gate_is_computed_with_and_without_authored_edges(tmp_path: Path) -> None:
    """Both halves. The kind selection must change *what the channel may walk* — otherwise the two
    runs are one run reported twice, and the anti-circularity guard guards nothing."""
    corpus = linked_documents(tmp_path / "kb")
    connection = corpus.open()
    try:
        pairs = authored_pairs(connection, local_kb=str(corpus.kb_id))
        structural = int(connection.execute("SELECT count(*) FROM edges").fetchone()[0])
    finally:
        connection.close()

    assert pairs, "the fixture must actually carry an intra-KB authored link"
    with_authored = structural + len(pairs)
    without_authored = structural
    assert with_authored > without_authored, (
        "the two derived edge sets must differ in cardinality; equal, the split discriminates "
        "nothing and both runs measure the same graph"
    )

    root = chunk_id_of(corpus, "docs/one/alpha.md", 0)
    reached_with = paths_of(corpus, [c.chunk_id for c in walk(corpus, [root])])
    reached_without = paths_of(
        corpus,
        [c.chunk_id for c in walk(corpus, [root], kinds=select_kinds(drop=[AUTHORED]))],
    )
    assert "docs/two/beta.md" in reached_with
    assert "docs/two/beta.md" not in reached_without


def test_dropping_authored_is_every_links_row_regardless_of_origin(tmp_path: Path) -> None:
    """*"Without authored edges"* means the whole class. A `reverse-scan` row is hand-authored
    too — by the partner KB's human — and `AUTHORED` is one kind, not one origin, so there is no
    selection under which half of it survives."""
    assert AUTHORED in ALL_KINDS
    assert AUTHORED not in select_kinds(drop=[AUTHORED])


# --------------------------------------------------------------------------------------------
# The gate itself, on synthetic artifacts


CHUNKING: dict[str, Any] = {
    "max_tokens": 510,
    "overlap": 64,
    "headings": "none",
    "metadata": "off",
}
"""The `chunking` block `eval.header` writes, in the shape it writes it.

Written into every synthetic artifact rather than left out, because the gate compares this block
and a field absent from all three legs compares equal — so a fixture omitting it would leave the
comparison green whatever the gate did, which is the assertion-satisfied-by-nothing failure this
module's own docstring is written against.
"""


def artifact(
    path: Path,
    *,
    graph_channel: str,
    dropped: Sequence[str] = (),
    rows: Sequence[dict[str, Any]],
    chunking: Mapping[str, Any] | None = None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "k": 5,
                "graph_channel": graph_channel,
                "edge_kinds": sorted(set(ALL_KINDS) - set(dropped)),
                "dropped": sorted(dropped),
                "chunking": dict(CHUNKING if chunking is None else chunking),
                "questions": list(rows),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def row(identifier: str, kind: str, *, hit: bool, confidence: str = "medium") -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": kind,
        "hit": hit,
        "hit_rank": 1 if hit else None,
        "confidence": confidence,
    }


def multihop(count: int, *, hits: int) -> list[dict[str, Any]]:
    return [row(f"m{index}", "multi-hop", hit=index < hits) for index in range(count)]


def no_answer(count: int, *, high: int = 0) -> list[dict[str, Any]]:
    return [
        row(f"n{index}", "no-answer", hit=False, confidence="high" if index < high else "medium")
        for index in range(count)
    ]


def run_gate(tmp_path: Path, before: Path, without: Path, with_authored: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(GATE),
            "--before",
            str(before),
            "--after-without",
            str(without),
            "--after-with",
            str(with_authored),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert completed.stdout, completed.stderr
    parsed: dict[str, Any] = json.loads(completed.stdout)
    assert (completed.returncode == 0) == parsed["passed"], (
        "the exit status is what a CI job reads; it must agree with the verdict it printed"
    )
    return parsed


def legs(
    tmp_path: Path,
    *,
    before_rows: Sequence[dict[str, Any]],
    without_rows: Sequence[dict[str, Any]],
    with_rows: Sequence[dict[str, Any]],
) -> tuple[Path, Path, Path]:
    return (
        artifact(tmp_path / "off.json", graph_channel="off", rows=before_rows),
        artifact(
            tmp_path / "without.json",
            graph_channel="expand",
            dropped=[AUTHORED],
            rows=without_rows,
        ),
        artifact(tmp_path / "with.json", graph_channel="expand", rows=with_rows),
    )


def _gate_module() -> Any:
    """`tools/` is not a package, so the gate is loaded by path rather than imported.

    Every other gate test drives it as a subprocess, which is what exercises the artifact CI would
    run. This one needs the *function*: the sign test is pure arithmetic, and asserting a table of
    p-values through a JSON round trip would test the reporting rather than the statistic.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("graph_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before executing: `@dataclass(slots=True)` rebuilds the class and resolves its
    # own module out of `sys.modules` to do it, so a module executed outside it raises there.
    sys.modules["graph_gate"] = module
    spec.loader.exec_module(module)
    return module


def test_the_sign_test_reproduces_the_plans_table_and_the_rows_below_it(tmp_path: Path) -> None:
    """The criterion is p < 0.05 on the discordant pairs; the plan's table is its first four rows,
    not a closed list. Both directions are asserted: the row above each threshold must *fail*, or
    the check is satisfied by a function that returns 0 for everything."""
    sign_test = _gate_module().sign_test

    passes = {0: 5, 1: 7, 2: 9, 3: 10, 4: 12, 5: 13}
    for regressed, improved in passes.items():
        assert sign_test(improved, regressed) < 0.05, (regressed, improved)
        assert sign_test(improved - 1, regressed) >= 0.05, (
            f"r={regressed}, i={improved - 1} must be short of the table"
        )
    assert sign_test(0, 0) == 1.0


def test_a_rise_in_false_confidence_stops_the_gate(tmp_path: Path) -> None:
    """`false_confidence` is not covered by clause 2: `by_kind["no-answer"]` is hit-based, so a
    no-answer question can stay a clean non-hit while flipping to HIGH. One flip is 0.125 against
    a 0.02 tolerance, and the re-baseline would swallow it."""
    before = [*multihop(12, hits=0), *no_answer(8)]
    after = [*multihop(12, hits=5), *no_answer(8, high=1)]
    verdict = run_gate(
        tmp_path, *legs(tmp_path, before_rows=before, without_rows=after, with_rows=after)
    )

    assert not verdict["passed"]
    for run in verdict["runs"]:
        assert run["clauses"]["sign_test"], "clause 1 must pass, or this tests the wrong clause"
        assert not run["clauses"]["rebaseline"]
        assert any("false_confidence" in line for line in run["other_regressions"])


def test_a_drop_in_confidence_coverage_stops_the_gate(tmp_path: Path) -> None:
    """The guard the re-baseline actually removes. `eval.py`: *"losing the ability to say anything
    is a regression too"* — the error rates would improve to a meaningless zero while the system
    got quieter, not better."""
    before = [*multihop(12, hits=0), *no_answer(8)]
    after = [
        *multihop(12, hits=5),
        *[row(f"n{index}", "no-answer", hit=False, confidence="unknown") for index in range(8)],
    ]
    verdict = run_gate(
        tmp_path, *legs(tmp_path, before_rows=before, without_rows=after, with_rows=after)
    )

    assert not verdict["passed"]
    for run in verdict["runs"]:
        assert run["clauses"]["sign_test"]
        assert not run["clauses"]["rebaseline"]
        assert any("confidence_coverage" in line for line in run["other_regressions"])


def test_the_gate_requires_both_runs_to_pass(tmp_path: Path) -> None:
    """An earlier revision made only the without-authored run binding, and that licensed a wrong
    default through three green clauses: the shipped configuration improving 3 and regressing 3
    leaves `by_kind` unchanged, so clause 2 stays quiet."""
    # Three multi-hop questions already pass, so the shipped leg can trade rather than only gain.
    before = [*multihop(12, hits=3), *no_answer(8)]
    without = [*multihop(12, hits=8), *no_answer(8)]
    # Exactly the plan's scenario: 3 improved, 3 regressed. `by_kind["multi-hop"]` is 0.25 before
    # and 0.25 after, so clause 2 stays quiet and only clause 1 can catch it.
    with_authored = [
        *[row(f"m{index}", "multi-hop", hit=index in {3, 4, 5}) for index in range(12)],
        *no_answer(8),
    ]
    verdict = run_gate(
        tmp_path,
        *legs(tmp_path, before_rows=before, without_rows=without, with_rows=with_authored),
    )

    without_run, with_run = verdict["runs"]
    assert without_run["clauses"]["sign_test"], "the guard run passes"
    assert not with_run["clauses"]["sign_test"], "the shipped run does not"
    assert not verdict["passed"], "one green run may not license a default"
    assert verdict["licensing_p"] == pytest.approx(with_run["p"]), (
        "the licensing number is the more conservative of the two"
    )


def test_a_newly_found_question_at_low_confidence_does_not_veto_the_win(tmp_path: Path) -> None:
    """Clause 3's whole point. `false_abstain`'s numerator requires a hit, so a miss that becomes
    a LOW-confidence hit *raises the rate* — and an unqualified clause would veto exactly the win
    clause 1 demands. Five such conversions here, and the gate must still pass."""
    before = [*multihop(12, hits=0), *no_answer(8)]
    after = [
        *[
            row(
                f"m{index}",
                "multi-hop",
                hit=index < 5,
                confidence="low" if index < 5 else "medium",
            )
            for index in range(12)
        ],
        *no_answer(8),
    ]
    verdict = run_gate(
        tmp_path, *legs(tmp_path, before_rows=before, without_rows=after, with_rows=after)
    )

    assert verdict["passed"], "a rise made entirely of newly-found questions is not a regression"
    for run in verdict["runs"]:
        assert run["newly_found_at_low_confidence"] == ["m0", "m1", "m2", "m3", "m4"]
        assert run["confidence_lost"] == []


def test_a_question_that_lost_confidence_stops_the_gate(tmp_path: Path) -> None:
    """The other half of the decomposition, and the half that is a regression: a question that was
    already a hit and is now reported at LOW. Without this the carve-out would be a hole."""
    before = [*multihop(12, hits=3), *no_answer(8)]
    after = [
        *[
            row(
                f"m{index}",
                "multi-hop",
                hit=index < 8,
                confidence="low" if index == 0 else "medium",
            )
            for index in range(12)
        ],
        *no_answer(8),
    ]
    verdict = run_gate(
        tmp_path, *legs(tmp_path, before_rows=before, without_rows=after, with_rows=after)
    )

    assert not verdict["passed"]
    for run in verdict["runs"]:
        assert run["clauses"]["sign_test"], "clause 1 passes; only clause 3 may catch this"
        assert not run["clauses"]["false_abstain"]
        assert run["confidence_lost"] == ["m0"]


def test_a_class_vanishing_stops_the_gate(tmp_path: Path) -> None:
    """`compare()` treats a class disappearing as a regression — *"the class vanished from the
    golden set"* — and clause 2 is what carries it. The question keeps its id and changes kind, so
    the pairing is intact and the only thing that moved is a class the baseline still guards."""
    before = [*multihop(12, hits=0), *no_answer(8), row("s0", "simple-lookup", hit=True)]
    after = [*multihop(12, hits=5), *no_answer(8), row("s0", "multi-hop", hit=True)]
    verdict = run_gate(
        tmp_path, *legs(tmp_path, before_rows=before, without_rows=after, with_rows=after)
    )

    assert not verdict["passed"], "a vanished class may not be absorbed by a re-baseline"
    assert not verdict["problems"], "the pairing is intact; this must reach the clauses"
    for run in verdict["runs"]:
        assert not run["clauses"]["no_class_regresses"]
        assert any("simple-lookup" in line for line in run["class_regressions"])


def test_an_unpaired_question_set_is_refused_before_any_clause_is_scored(tmp_path: Path) -> None:
    """A sign test pairs on id. A question present in one leg and absent from the other is not a
    discordant pair, an improvement or a regression — it is a comparison that cannot be made, and
    silently dropping it would shrink the denominator the p-value is computed over."""
    before = [*multihop(12, hits=0), *no_answer(8), row("s0", "simple-lookup", hit=True)]
    after = [*multihop(12, hits=5), *no_answer(8)]
    verdict = run_gate(
        tmp_path, *legs(tmp_path, before_rows=before, without_rows=after, with_rows=after)
    )

    assert not verdict["passed"]
    assert any("do not cover the same questions" in problem for problem in verdict["problems"])
    assert verdict["runs"] == []


def test_a_leg_that_is_not_the_leg_it_was_passed_as_is_refused(tmp_path: Path) -> None:
    """Headers, never filenames. A `--before` produced with the channel already on would make the
    gate compare a configuration against itself and report p = 1.0 with no error at all."""
    rows = [*multihop(12, hits=0), *no_answer(8)]
    after = [*multihop(12, hits=5), *no_answer(8)]
    before = artifact(tmp_path / "off.json", graph_channel="expand", rows=rows)
    without = artifact(
        tmp_path / "without.json", graph_channel="expand", dropped=[AUTHORED], rows=after
    )
    with_authored = artifact(tmp_path / "with.json", graph_channel="expand", rows=after)

    verdict = run_gate(tmp_path, before, without, with_authored)
    assert not verdict["passed"]
    assert any("graph_channel" in problem for problem in verdict["problems"])
    assert verdict["runs"] == [], "no clause is scored against a leg that is not what it claims"


def test_a_without_authored_leg_that_kept_authored_edges_is_refused(tmp_path: Path) -> None:
    rows = [*multihop(12, hits=0), *no_answer(8)]
    after = [*multihop(12, hits=5), *no_answer(8)]
    before = artifact(tmp_path / "off.json", graph_channel="off", rows=rows)
    without = artifact(tmp_path / "without.json", graph_channel="expand", rows=after)
    with_authored = artifact(tmp_path / "with.json", graph_channel="expand", rows=after)

    verdict = run_gate(tmp_path, before, without, with_authored)
    assert not verdict["passed"]
    assert any(AUTHORED in problem for problem in verdict["problems"])


def test_three_legs_chunked_differently_are_refused(tmp_path: Path) -> None:
    """A rechunk between legs is not noise — it is two corpora, so rows paired on `id` were
    produced by searching different texts. Measured on one RFC: `max_tokens` 510 against 480 moves
    63 of 1 858 chunk texts. The gate compared `k`, `embedding`, `rerank`, `ranking` and
    `retrieval` and not this, so a rechunk was reported as whatever was under test — and this gate
    is the one that licensed the graph channel's default."""
    rows = [*multihop(12, hits=0), *no_answer(8)]
    after = [*multihop(12, hits=5), *no_answer(8)]
    before = artifact(tmp_path / "off.json", graph_channel="off", rows=rows)
    without = artifact(
        tmp_path / "without.json", graph_channel="expand", dropped=[AUTHORED], rows=after
    )
    with_authored = artifact(
        tmp_path / "with.json",
        graph_channel="expand",
        rows=after,
        chunking={**CHUNKING, "max_tokens": 480},
    )

    verdict = run_gate(tmp_path, before, without, with_authored)

    assert not verdict["passed"]
    assert any("chunking" in problem for problem in verdict["problems"])
    assert any("480" in problem for problem in verdict["problems"]), (
        "the value that moved is what tells a reader which leg to rebuild"
    )
    assert verdict["runs"] == [], "no clause is scored against a leg that is not what it claims"


def test_a_leg_injected_differently_is_refused_here_even_though_two_leg_gate_excepts_it(
    tmp_path: Path,
) -> None:
    """`chunking.metadata` is excepted by `tools/two_leg_gate.py` and must **not** be excepted
    here, and the two tools are right for opposite reasons. There, `metadata` is the independent
    variable — the before and after legs of the injection screen are *defined* by differing on it,
    so refusing that difference would refuse every valid comparison. Here the independent variable
    is `graph_channel`; a leg embedded with a `title > heading_path` prefix and one without are two
    embedding runs, and the difference would land on the graph channel's account.

    Without this test the fix is satisfied by copying `two_leg_gate`'s exception list across."""
    rows = [*multihop(12, hits=0), *no_answer(8)]
    after = [*multihop(12, hits=5), *no_answer(8)]
    before = artifact(tmp_path / "off.json", graph_channel="off", rows=rows)
    without = artifact(
        tmp_path / "without.json", graph_channel="expand", dropped=[AUTHORED], rows=after
    )
    with_authored = artifact(
        tmp_path / "with.json",
        graph_channel="expand",
        rows=after,
        chunking={**CHUNKING, "metadata": "prefix"},
    )

    verdict = run_gate(tmp_path, before, without, with_authored)

    assert not verdict["passed"]
    assert any("chunking" in problem for problem in verdict["problems"])


def test_a_gate_that_passes_reports_that_it_passes(tmp_path: Path) -> None:
    """The negative half of every test above. Without it they would all be green against a gate
    that refuses everything."""
    before = [*multihop(12, hits=0), *no_answer(8)]
    after = [*multihop(12, hits=5), *no_answer(8)]
    verdict = run_gate(
        tmp_path, *legs(tmp_path, before_rows=before, without_rows=after, with_rows=after)
    )

    assert verdict["passed"]
    assert verdict["licensing_p"] == pytest.approx(0.03125)


# --------------------------------------------------------------------------------------------
# Housekeeping the other suites would not catch


def test_the_channel_setting_is_not_stamped_into_the_template() -> None:
    """`_toml.py` hard-errors on an unknown key, so a template carrying `graph_channel` cannot be
    read by any Pinakes built before it existed — the same reasoning that keeps `adjacent_k` out."""
    template = REPO / "src" / "pinakes" / "templates" / "notes" / "pinakes.toml.j2"
    assert "graph_channel" not in template.read_text(encoding="utf-8")


def test_the_default_is_off(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "kb")
    text = (corpus.root / "pinakes.toml").read_text(encoding="utf-8")
    (corpus.root / "pinakes.toml").write_text(
        "\n".join(line for line in text.splitlines() if "graph_channel" not in line) + "\n",
        encoding="utf-8",
    )
    assert corpus.manifest().retrieval.graph_channel == "off"


def test_an_unknown_channel_name_is_refused(tmp_path: Path) -> None:
    """`"ppr"` is APPROACH §4B's stage B and is not built. A manifest that can name it would ask
    for a mode that silently does nothing."""
    from pinakes.errors import ManifestError

    corpus = Corpus(tmp_path / "kb", graph_channel="ppr")
    with pytest.raises(ManifestError):
        corpus.manifest()


def test_a_soft_deleted_document_never_reaches_the_channel(tmp_path: Path) -> None:
    """G3 reaps a deleted document's edges; this is the other end of that promise — the channel
    is the only reader of them, so "the channel can never surface deleted content" is a claim
    about this walk."""
    corpus = two_tagged_documents(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/one/alpha.md", 0)
    assert "docs/two/beta.md" in paths_of(corpus, [c.chunk_id for c in walk(corpus, [root])])

    (corpus.root / "docs/two/beta.md").unlink()
    (corpus.root / ("docs/two/beta.md" + SIDECAR_SUFFIX)).unlink()
    corpus.sync()

    assert "docs/two/beta.md" not in paths_of(corpus, [c.chunk_id for c in walk(corpus, [root])])


def test_a_kb_synced_before_the_edge_set_existed_walks_empty(tmp_path: Path) -> None:
    """An index whose `nodes` table is empty is not an error: the honest answer is no neighbours,
    and RRF over an empty third list is today's two-list fusion."""
    corpus = two_tagged_documents(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/one/alpha.md", 0)
    writable = store.connect_rw(corpus.manifest().index_path)
    try:
        writable.execute("DELETE FROM edges")
        writable.execute("DELETE FROM nodes")
        writable.commit()
    finally:
        writable.close()
    assert walk(corpus, [root]) == []


def test_the_corpora_are_left_alone(tmp_path: Path) -> None:
    """The two committed corpora do not stamp `graph_channel`, so every other suite in this
    repository still measures the two-list pipeline."""
    for name in ("demo-kb", "partner-kb"):
        text = (REPO / "tests" / name / "pinakes.toml").read_text(encoding="utf-8")
        assert "graph_channel" not in text


def test_the_workspace_helper_copies_rather_than_edits(tmp_path: Path) -> None:
    """`_turn_the_channel_on` writes into a copy. If it ever pointed at the real corpora, every
    other suite would silently start measuring the channel."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copytree(
        REPO / "tests" / "demo-kb", workspace / "demo-kb", ignore=shutil.ignore_patterns(".pinakes")
    )
    _turn_the_channel_on(workspace / "demo-kb")
    assert "graph_channel" not in (REPO / "tests" / "demo-kb" / "pinakes.toml").read_text(
        encoding="utf-8"
    )
