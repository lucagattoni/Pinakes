"""The channel-reachable ceiling, measured in memory before any schema bumps (G2).

**What this answers, and why the answer is not "how many questions fail".** G5's gate needs
improvements, and an improvement can only come from a question that fails *today*. But failing is
necessary and nowhere near sufficient: a question is only *liftable* if the evidence its failing
hop needs lies within 2 logical hops of that hop's fused seeds, in the edge set G3 would derive.
With `mentions` cut (decision 6) every surviving structural edge connects things already near each
other, and the golden set's own authoring rule — evidence split across two documents with no shared
vocabulary — actively selects for pairs those edges cannot bridge. A failure count alone can pass
with zero reachable questions, bump `schema_version`, force every KB in existence to rebuild, and
only then reveal that the gate was unreachable.

**Two numbers, and only one of them binds.** Reachability is computed **with** and **without**
authored edges. A corpus reachable only through links its own author wrote cannot tell you whether
*derived* structure helps — the "1.00 by construction" shape decision 14 cut cross-KB questions
over. The without-authored figure is the precondition; the with-authored figure is recorded and
licenses nothing.

**In memory, at `schema_version` 2.** Nothing here writes a table, and the point is the ordering:
if the ceiling is not there, G3 must not have bumped the schema to find out.

**This is throwaway measurement code, not the G3 deriver.** It is the probe's reading of
APPROACH §3 and §4A, and G5's implementation is the authority if the two ever disagree:

* A **logical hop** is a chunk-or-doc → chunk-or-doc transition. Hub nodes (directory, tag,
  heading) and membership edges are transit, not distance, so `doc → dir-hub → doc` is one hop.
* `parent`/`child` are read as *intra-document* hierarchy. `heading_path` prefixes compared across
  documents would make every document sharing a heading title adjacent, which is exactly the
  global-hub failure APPROACH scopes heading nodes per document to avoid.
* A hub expands **once globally** (visited-edge dedup) and yields at most `adjacent_k` chunks,
  ranked by cosine against the hop's own query — because a hub node carries no content embedding
  and contributes its member chunks, query-ranked, like any others.
* Same-document chunks reachable **only** through their own document's membership edge are dropped
  before the `adjacent_k` cut, so they consume no fan-out budget either.

The generosity is deliberate and stated: this is a *ceiling*. A document that survives the fan-out
cut is counted reachable even though the channel would still have to out-rank everything else to
change the answer. A ceiling that is already too low is decisive; a ceiling that is high proves
only that the gate is not impossible.

**The probe must be shown to fail.** `--drop co-located` (or any edge kind) re-runs with that kind
removed; if the reachable count does not move, the probe is measuring something other than the edge
set and its output means nothing. `tests/test_eval.py` pins that.

Usage:
    python3 tools/reachable_ceiling_probe.py                    # real models, the measurement
    python3 tools/reachable_ceiling_probe.py --fake             # offline, for tests
    python3 tools/reachable_ceiling_probe.py --drop co-located  # prove the number moves
    python3 tools/reachable_ceiling_probe.py --json
"""

import argparse
import json
import posixpath
import shutil
import sqlite3
import sys
import tempfile
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pinakes import store
from pinakes.embed import (
    EmbeddingBackend,
    ModelInfo,
    Reranker,
    Vectors,
    load_backend,
    load_reranker,
    register_embedding_backend,
    register_reranker,
)
from pinakes.eval import Question, load_questions
from pinakes.manifest import Manifest, load
from pinakes.search import Filters, fused_candidates, search, unit_vectors
from pinakes.sync import SyncOptions, sync

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "tests" / "demo-kb"

STRUCTURAL_KINDS = ("sibling", "parent-child", "in-section", "co-located", "shared-tag")
AUTHORED = "authored"
ALL_KINDS = (*STRUCTURAL_KINDS, AUTHORED)

DEPTH = 2
"""APPROACH §4A's expansion depth, in logical hops. Not a knob: the gate is defined here."""

FAR_DEPTH = 6
"""Used only to separate "unreachable" from "reachable, but further than the channel looks"."""

FAKE_DIM = 64


# --------------------------------------------------------------------------------------------
# The in-memory edge set


@dataclass(frozen=True, slots=True)
class Chunk:
    id: int
    doc: str
    ordinal: int
    heading_path: str | None


@dataclass
class Graph:
    """Every node the channel could walk, derived from a `schema_version` 2 index and nothing else.

    Hubs are `dict[hub key, member list]` rather than materialised pairwise edges, which is the
    whole point of APPROACH §3's hub model: a tag on 30 documents is 30 spokes, not 435 edges.
    """

    chunks: dict[int, Chunk]
    chunk_kinds: set[str] = field(default_factory=set[str])
    """Which chunk ↔ chunk kinds this graph was derived with — `sibling`, `parent-child`, or
    neither. They materialise no hub, so unlike every other kind they cannot be read off the
    structures below, and `--drop sibling` would otherwise silently do nothing."""

    by_doc: dict[str, list[int]] = field(default_factory=dict[str, list[int]])
    doc_path: dict[str, str] = field(default_factory=dict[str, str])
    dir_hub: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    tag_hub: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    heading_hub: dict[tuple[str, str], list[int]] = field(
        default_factory=dict[tuple[str, str], list[int]]
    )
    authored: dict[str, set[str]] = field(default_factory=dict[str, set[str]])

    def hubs_of_doc(self, doc: str) -> list[tuple[str, str]]:
        hubs: list[tuple[str, str]] = []
        directory = posixpath.dirname(self.doc_path[doc])
        if directory in self.dir_hub:
            hubs.append(("co-located", directory))
        for tag, members in self.tag_hub.items():
            if doc in members:
                hubs.append(("shared-tag", tag))
        return hubs


def derive(connection: sqlite3.Connection, kb_id: str, *, kinds: Sequence[str]) -> Graph:
    """G3's edge set, in memory, from the tables that already exist.

    `kinds` is what makes the with/without-authored split and `--drop` possible at all: an edge
    kind absent from it is never derived, so nothing downstream can reach through it.
    """
    documents = {
        str(row["id"]): str(row["path"])
        for row in connection.execute(
            "SELECT id, path FROM documents WHERE state = 'active' ORDER BY path"
        )
    }
    chunks: dict[int, Chunk] = {}
    graph = Graph(
        chunks=chunks,
        chunk_kinds={k for k in kinds if k in {"sibling", "parent-child"}},
        doc_path=documents,
    )

    rows = connection.execute(
        "SELECT c.id, c.doc_id, c.ordinal, c.heading_path FROM chunks c "
        "JOIN documents d ON d.id = c.doc_id WHERE d.state = 'active' "
        "ORDER BY d.path, c.ordinal"
    )
    for row in rows:
        chunk = Chunk(
            id=int(row["id"]),
            doc=str(row["doc_id"]),
            ordinal=int(row["ordinal"]),
            heading_path=None if row["heading_path"] is None else str(row["heading_path"]),
        )
        chunks[chunk.id] = chunk
        graph.by_doc.setdefault(chunk.doc, []).append(chunk.id)
        if "in-section" in kinds and chunk.heading_path is not None:
            graph.heading_hub.setdefault((chunk.doc, chunk.heading_path), []).append(chunk.id)

    if "co-located" in kinds:
        for doc, path in documents.items():
            graph.dir_hub.setdefault(posixpath.dirname(path), []).append(doc)

    if "shared-tag" in kinds:
        for row in connection.execute(
            "SELECT d.id, j.value AS tag FROM documents d, json_each(d.metadata, '$.tags') j "
            "WHERE d.state = 'active' ORDER BY d.path"
        ):
            graph.tag_hub.setdefault(str(row["tag"]), []).append(str(row["id"]))

    if AUTHORED in kinds:
        # Only a *local* document has a `doc` node (G3), so an edge with either end in another KB
        # resolves to nothing and never enters the channel — in both directions.
        for row in connection.execute("SELECT * FROM links"):
            src_kb, dst_kb = str(row["src_kb_id"]), str(row["dst_kb_id"])
            src, dst = str(row["src_doc_id"]), str(row["dst_doc_id"])
            if src_kb != kb_id or dst_kb != kb_id or src not in documents or dst not in documents:
                continue
            graph.authored.setdefault(src, set()).add(dst)
            graph.authored.setdefault(dst, set()).add(src)

    return graph


# --------------------------------------------------------------------------------------------
# Expansion


def reachable_docs(
    graph: Graph,
    seeds: Sequence[int],
    similarity: dict[int, float],
    *,
    adjacent_k: int,
    depth: int,
    exclude_membership: bool = True,
) -> set[str]:
    """Documents within `depth` logical hops of `seeds`, under the channel's two bounding rules."""
    root_docs = {graph.chunks[c].doc for c in seeds if c in graph.chunks}
    frontier_chunks = {c for c in seeds if c in graph.chunks}
    frontier_docs = set(root_docs)
    expanded_hubs: set[tuple[str, object]] = set()
    reached: set[str] = set()

    for _ in range(depth):
        found: set[int] = set()

        # Chunk-level structure: sibling and intra-document hierarchy, both direct chunk ↔ chunk.
        for chunk_id in frontier_chunks:
            chunk = graph.chunks[chunk_id]
            for sibling in graph.by_doc.get(chunk.doc, ()):
                other = graph.chunks[sibling]
                if "sibling" in graph.chunk_kinds and abs(other.ordinal - chunk.ordinal) == 1:
                    found.add(sibling)
                if (
                    "parent-child" in graph.chunk_kinds
                    and chunk.heading_path
                    and other.heading_path
                    and _is_prefix(chunk.heading_path, other.heading_path)
                ):
                    found.add(sibling)
            if chunk.heading_path is not None:
                key = (chunk.doc, chunk.heading_path)
                if key in graph.heading_hub and ("in-section", key) not in expanded_hubs:
                    expanded_hubs.add(("in-section", key))
                    found.update(graph.heading_hub[key])

        # Document-level structure: every shared-value relation goes through its hub, and each hub
        # expands once globally — a popular tag or a big directory is not re-walked per encounter.
        for doc in frontier_docs:
            for kind, key in graph.hubs_of_doc(doc):
                if (kind, key) in expanded_hubs:
                    continue
                expanded_hubs.add((kind, key))
                members = graph.dir_hub[key] if kind == "co-located" else graph.tag_hub[key]
                found.update(
                    _rank_hub_members(
                        graph,
                        members,
                        similarity,
                        adjacent_k=adjacent_k,
                        drop_docs=root_docs if exclude_membership else set(),
                        already=found,
                    )
                )
            for neighbour in graph.authored.get(doc, ()):
                found.update(graph.by_doc.get(neighbour, ()))

        frontier_chunks = found
        frontier_docs = {graph.chunks[c].doc for c in found}
        reached |= frontier_docs
        if not found:
            break
    return reached


def _is_prefix(a: str, b: str) -> bool:
    return a != b and (b.startswith(a + " > ") or a.startswith(b + " > "))


def _rank_hub_members(
    graph: Graph,
    members: Sequence[str],
    similarity: dict[int, float],
    *,
    adjacent_k: int,
    drop_docs: set[str],
    already: set[int],
) -> list[int]:
    """A hub carries no embedding: it contributes its member chunks, query-ranked and capped.

    `drop_docs` are the roots' own documents. Their chunks are reachable here only through their
    own document's membership edge, which APPROACH §3 excludes from the channel's output **and**
    from its fan-out budget — so they are dropped *before* the cut, never counted against it.
    """
    candidates = [
        chunk_id
        for doc in members
        if doc not in drop_docs
        for chunk_id in graph.by_doc.get(doc, ())
        if chunk_id not in already
    ]
    candidates.sort(key=lambda c: (-similarity.get(c, 0.0), graph.doc_path[graph.chunks[c].doc], c))
    return candidates[:adjacent_k]


# --------------------------------------------------------------------------------------------
# Running the golden set through it


@dataclass(frozen=True, slots=True)
class HopVerdict:
    question: str
    hop: int
    document: str
    lands_today: bool
    at_seed: bool
    reachable: bool
    reachable_far: bool
    reachable_via_membership: bool


@dataclass(frozen=True, slots=True)
class Report:
    variant: str
    kinds: tuple[str, ...]
    multi_hop: int
    failing: int
    liftable: int
    at_seed_only: int
    beyond_depth: int
    membership_only: int
    verdicts: tuple[HopVerdict, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "kinds": list(self.kinds),
            "multi_hop_questions": self.multi_hop,
            "failing": self.failing,
            "liftable": self.liftable,
            "at_seed_only": self.at_seed_only,
            "beyond_depth": self.beyond_depth,
            "membership_only": self.membership_only,
        }


def probe(
    connection: sqlite3.Connection,
    manifest: Manifest,
    questions: Sequence[Question],
    *,
    backend: EmbeddingBackend,
    reranker: Reranker | None,
    kinds: Sequence[str],
    variant: str,
) -> Report:
    graph = derive(connection, manifest.kb.id, kinds=kinds)

    chunk_ids, matrix = store.load_vectors(connection, dim=manifest.embedding.dim)
    unit = unit_vectors(matrix)

    verdicts: list[HopVerdict] = []
    multi_hop = [q for q in questions if q.kind == "multi-hop"]
    for question in multi_hop:
        for index, hop in enumerate(question.hops):
            filters = question.filters if index == len(question.hops) - 1 else Filters()
            result = search(
                connection,
                manifest,
                hop.query,
                backend=backend,
                reranker=reranker,
                filters=filters,
                limit=manifest.retrieval.final_k,
            )
            lands = hop.expect in {passage.path for passage in result.passages}

            seeds = fused_candidates(
                connection, manifest, hop.query, backend=backend, filters=filters
            ).order
            similarity = _similarity(unit, chunk_ids, backend, hop.query)
            near = reachable_docs(
                graph,
                seeds,
                similarity,
                adjacent_k=manifest.retrieval.adjacent_k,
                depth=DEPTH,
            )
            far = reachable_docs(
                graph,
                seeds,
                similarity,
                adjacent_k=manifest.retrieval.adjacent_k,
                depth=FAR_DEPTH,
            )
            through_membership = reachable_docs(
                graph,
                seeds,
                similarity,
                adjacent_k=manifest.retrieval.adjacent_k,
                depth=DEPTH,
                exclude_membership=False,
            )
            wanted = _doc_id(connection, hop.expect)
            seed_docs = {graph.chunks[c].doc for c in seeds if c in graph.chunks}
            verdicts.append(
                HopVerdict(
                    question=question.id,
                    hop=index,
                    document=hop.expect,
                    lands_today=lands,
                    at_seed=wanted in seed_docs,
                    reachable=wanted in near or wanted in seed_docs,
                    reachable_far=wanted in far,
                    reachable_via_membership=wanted in through_membership,
                )
            )

    return _summarise(variant, tuple(kinds), multi_hop, verdicts)


def _summarise(
    variant: str,
    kinds: tuple[str, ...],
    multi_hop: Sequence[Question],
    verdicts: Sequence[HopVerdict],
) -> Report:
    by_question: dict[str, list[HopVerdict]] = {}
    for verdict in verdicts:
        by_question.setdefault(verdict.question, []).append(verdict)

    failing = 0
    liftable = 0
    at_seed_only = 0
    beyond = 0
    membership_only = 0
    for hops in by_question.values():
        missed = [hop for hop in hops if not hop.lands_today]
        if not missed:
            continue
        failing += 1
        # A question is liftable only when *every* hop it currently misses is reachable: a hit
        # requires each hop to land its own document by its own query.
        if all(hop.reachable for hop in missed):
            liftable += 1
            # Distance zero. The document is already among the fused candidates and merely ranked
            # below the cut, so the channel would have to *re-rank* it, not reach it — no edge is
            # traversed. Counted in `liftable`, because §9 says "within 2 logical hops" and zero is
            # within two, and reported separately, because a ceiling made of these says nothing
            # about whether derived structure bridges anything.
            if all(hop.at_seed for hop in missed):
                at_seed_only += 1
        elif all(hop.reachable_far for hop in missed):
            beyond += 1
        elif all(hop.reachable_via_membership for hop in missed):
            membership_only += 1
    return Report(
        variant=variant,
        kinds=kinds,
        multi_hop=len(multi_hop),
        failing=failing,
        liftable=liftable,
        at_seed_only=at_seed_only,
        beyond_depth=beyond,
        membership_only=membership_only,
        verdicts=tuple(verdicts),
    )


def _similarity(
    unit: "np.ndarray[Any, np.dtype[np.float32]]",
    chunk_ids: Sequence[int],
    backend: EmbeddingBackend,
    query: str,
) -> dict[int, float]:
    """Cosine of every stored chunk against one query — how a hub's members are ranked."""
    embedded = backend.embed([query])
    if embedded.shape[0] == 0:
        return {}
    scores = unit @ unit_vectors(embedded)[0]
    return {chunk_id: float(scores[index]) for index, chunk_id in enumerate(chunk_ids)}


def _doc_id(connection: sqlite3.Connection, path: str) -> str:
    row = connection.execute("SELECT id FROM documents WHERE path = ?", (path,)).fetchone()
    return "" if row is None else str(row["id"])


# --------------------------------------------------------------------------------------------
# Fake backends, so the mechanism is testable without weights or network


class HashingBackend:
    """The same deterministic bag-of-words hash `tests/test_eval.py` uses. crc32, never `hash()`."""

    def embed(self, texts: Sequence[str]) -> Vectors:
        rows: list[Vectors] = []
        for text in texts:
            vector_ = np.zeros(FAKE_DIM, dtype=np.float32)
            for word in text.lower().split():
                vector_[zlib.crc32(word.strip(".,:;()").encode("utf-8")) % FAKE_DIM] += 1.0
            rows.append(vector_)
        if not rows:
            return np.zeros((0, FAKE_DIM), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "hashing", "v1", FAKE_DIM, 512)


class OverlapReranker:
    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        terms = set(query.lower().split())
        return [float(len(terms & set(passage.lower().split()))) - 3.0 for passage in passages]

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "overlap-reranker", "v1", 0, 512)


def _fake_kb(destination: Path) -> Path:
    root = destination / "demo-kb"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns(".pinakes"))
    manifest_path = root / "pinakes.toml"
    text = manifest_path.read_text(encoding="utf-8")
    # The expected count is asserted, not assumed: `provider` legitimately appears twice (embedding
    # and rerank) and every other line once. A silent no-op here would leave the manifest naming
    # real weights, and the "offline" run would quietly download them.
    for old, new, occurrences in (
        ('provider = "fastembed"', 'provider = "fake"', 2),
        ('model    = "BAAI/bge-small-en-v1.5"', 'model    = "hashing"', 1),
        ("dim      = 384", f"dim      = {FAKE_DIM}", 1),
        ('model    = "BAAI/bge-reranker-base"', 'model    = "overlap-reranker"', 1),
        ('fitted_for = "BAAI/bge-reranker-base"', 'fitted_for = "overlap-reranker@v1"', 1),
    ):
        if text.count(old) != occurrences:
            raise SystemExit(f"manifest no longer contains {old!r} exactly {occurrences}x")
        text = text.replace(old, new)
    manifest_path.write_text(text, encoding="utf-8")
    sync(load(root), options=SyncOptions(), now="20260725 18:30")
    return root


# --------------------------------------------------------------------------------------------


def _tables(connection: sqlite3.Connection) -> list[str]:
    return sorted(
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    )


def _render(reports: Iterable[Report]) -> str:
    lines: list[str] = []
    for report in reports:
        lines.append(
            f"{report.variant:<18} multi-hop {report.multi_hop:>3}  failing {report.failing:>3}  "
            f"liftable {report.liftable:>3} (of which at-seed {report.at_seed_only:>3})  "
            f"beyond-{DEPTH}-hops {report.beyond_depth:>3}  "
            f"membership-only {report.membership_only:>3}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb", type=Path, default=DEMO)
    parser.add_argument("--fake", action="store_true", help="offline hashing backend, for tests")
    parser.add_argument(
        "--drop",
        action="append",
        default=[],
        choices=list(ALL_KINDS),
        help="derive without this edge kind — the number must move, or the probe measures nothing",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as workspace:
        if args.fake:
            register_embedding_backend("fake", lambda section, offline: HashingBackend())
            register_reranker("fake", lambda section, offline: OverlapReranker())
            root = _fake_kb(Path(workspace))
        else:
            root = args.kb

        manifest = load(root)
        questions = load_questions(root / "eval" / "questions.yaml")
        backend = load_backend(manifest.embedding)
        reranker = load_reranker(manifest.rerank) if manifest.retrieval.rerank == "local" else None
        connection = store.connect_ro(manifest.index_path)
        try:
            before = _tables(connection)
            kept = [kind for kind in ALL_KINDS if kind not in args.drop]
            reports = [
                probe(
                    connection,
                    manifest,
                    questions,
                    backend=backend,
                    reranker=reranker,
                    kinds=[k for k in kept if k != AUTHORED],
                    variant="without-authored",
                ),
                probe(
                    connection,
                    manifest,
                    questions,
                    backend=backend,
                    reranker=reranker,
                    kinds=kept,
                    variant="with-authored",
                ),
            ]
            after = _tables(connection)
            schema = store.get_meta(connection).get("schema_version", "?")
        finally:
            connection.close()

    payload = {
        "schema_version": schema,
        "tables_before": before,
        "tables_after": after,
        "adjacent_k": manifest.retrieval.adjacent_k,
        "depth": DEPTH,
        "dropped": sorted(set(args.drop)),
        "reports": [report.as_dict() for report in reports],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(_render(reports))
        print(
            f"\nschema_version {schema}, adjacent_k {manifest.retrieval.adjacent_k}, "
            f"depth {DEPTH} logical hops"
        )
        print(f"tables unchanged: {before == after}")
        if args.drop:
            print(f"derived without: {', '.join(sorted(set(args.drop)))}")
        print(
            "\nThe precondition is the *without-authored* liftable count (>= 7). The\n"
            "with-authored figure is recorded and licenses nothing: a corpus reachable only\n"
            "through links its own author wrote cannot say whether derived structure helps.\n"
            "`at-seed` is the part of `liftable` that traverses no edge at all."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
