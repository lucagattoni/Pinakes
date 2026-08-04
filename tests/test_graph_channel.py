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
from collections.abc import Collection, Iterable, Sequence
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
from pinakes.search import Fused, fused_candidates, search
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
template = "notes@1.0"
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

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:  # type: ignore[override]
        if " nodes " in f" {sql} " or " edges " in f" {sql} ":
            self.graph_statements.append(sql)
        return super().execute(sql, parameters)


def _traced(path: Path) -> _Tracer:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, factory=_Tracer)
    connection.row_factory = sqlite3.Row
    connection.graph_statements = []
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

    **No `# Title`, deliberately.** With one, every section's `heading_path` is
    `Title > Section n` and the title's own chunk is the transitive parent of all of them, so
    `parent-child` puts every chunk within two hops of every other and the membership path can
    never be the *only* way to reach anything. Without it the heading paths are pairwise
    non-prefix, each section is its own single-member hub (never minted), and ordinal 0 reaches
    only ordinals 1 and 2 — by `sibling`, twice.
    """
    corpus = Corpus(root, **options)
    corpus.write(
        "docs/long.md",
        "".join(f"## Section {index}\n\nword{index} " * 30 + "\n\n" for index in range(6)),
    )
    corpus.sync()
    return corpus


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
    corpus.write("docs/a.md", sectioned("A", [("Quokka", "quokka " * 40)]), tags=["t1"])
    corpus.write("docs/b.md", sectioned("B", [("Zebu", "zebu " * 40)]), tags=["t1", "t2"])
    corpus.write("docs/c.md", sectioned("C", [("Numbat", "numbat " * 40)]), tags=["t2"])
    corpus.sync()
    return corpus


def test_a_document_never_passes_through_to_itself(tmp_path: Path) -> None:
    corpus = tag_chain(tmp_path / "kb")
    root = chunk_id_of(corpus, "docs/a.md", 0)
    reached = paths_of(corpus, [c.chunk_id for c in walk(corpus, [root], adjacent_k=1)])

    assert "docs/b.md" in reached, "hop 1, through the tag the root's document shares"
    assert "docs/c.md" in reached, (
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


def artifact(
    path: Path,
    *,
    graph_channel: str,
    dropped: Sequence[str] = (),
    rows: Sequence[dict[str, Any]],
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "k": 5,
                "graph_channel": graph_channel,
                "edge_kinds": sorted(set(ALL_KINDS) - set(dropped)),
                "dropped": sorted(dropped),
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
                "m%d" % index,
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
                "m%d" % index,
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
    shutil.copytree(REPO / "tests" / "demo-kb", workspace / "demo-kb")
    _turn_the_channel_on(workspace / "demo-kb")
    assert "graph_channel" not in (REPO / "tests" / "demo-kb" / "pinakes.toml").read_text(
        encoding="utf-8"
    )
