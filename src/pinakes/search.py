"""The free pipeline: filter, BM25, vectors, fusion, rerank, confidence (docs/DESIGN.md §4.1).

Every stage narrows, and each width is its own manifest field, because `candidates_per_source`,
`fusion_top_k` and `final_k` are three different cut-offs that a single `top_k` would conflate.

Three things here are load-bearing beyond "it returns results":

* **The coherence gate runs before any query.** If the index was built by a different embedding
  model than the manifest now names, the stored vectors mean something else and the results would be
  confident nonsense. Queries refuse to run and instruct a rebuild (§4.4).
* **Confidence is a calibrated heuristic or it is `unknown`.** Reranker scores are not comparable
  across queries, so thresholds are only meaningful for the reranker they were fitted against.
  Absent block, or `fitted_for` naming a different model, means `unknown` — never a guess (§4.2).
* **Query-term coverage is a tiebreak, never a gate.** As a filter it would penalise exactly the
  paraphrase queries vector search exists to serve.
"""

import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from pinakes import store
from pinakes.embed import EmbeddingBackend, Reranker
from pinakes.errors import CoherenceError, ExtractionCoherenceError
from pinakes.extract import fingerprint as extraction_fingerprint
from pinakes.extract import is_paid_backend, registered_extractors
from pinakes.ids import DocId
from pinakes.manifest import Manifest

RRF_K = 60
UNKNOWN = "unknown"
LOW = "low"
MEDIUM = "medium"
HIGH = "high"

_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class Filters:
    tags: tuple[str, ...] = ()
    path_prefix: str | None = None
    source_type: str | None = None
    modified_after: float | None = None
    modified_before: float | None = None


@dataclass(frozen=True, slots=True)
class Passage:
    doc_id: DocId
    path: str
    title: str | None
    heading_path: str | None
    text: str
    char_start: int
    char_end: int
    lexical_rank: int | None
    vector_rank: int | None
    fused_score: float
    rerank_score: float | None
    stale_extraction: str | None = None
    """The recorded fingerprint, when this document's *paid* extraction backend has since moved
    on (§4.4, decision 13) — the text is still correct, merely older, so the result stands and is
    only marked, never withheld the way a free-backend mismatch (`ExtractionCoherenceError`) is."""
    page_start: int | None = None
    page_end: int | None = None
    """1-indexed, `None` for a non-paged source. `page_end > page_start` when a chunk straddles a
    page break, which I5 explicitly allows — so the citation has to be able to say so (I8)."""

    def citation(self) -> str:
        where = f"{self.path}:{self.locator()}"
        return f"{where} ({self.heading_path})" if self.heading_path else where

    def locator(self) -> str:
        """What follows the path in a citation: pages when the source has them, else characters.

        **The `p` is not decoration.** `report.pdf:12-480` already means *character offsets*, so a
        bare `report.pdf:12-13` would be a page range and a character range in the same syntax,
        distinguishable only by knowing the file. Paged sources therefore render `p12-13`, and
        every non-paged source keeps the offsets it rendered before (I8).
        """
        if self.page_start is None:
            return f"{self.char_start}-{self.char_end}"
        if self.page_end is None or self.page_end <= self.page_start:
            return f"p{self.page_start}"
        return f"p{self.page_start}-{self.page_end}"


@dataclass(frozen=True, slots=True)
class SearchResult:
    query: str
    passages: tuple[Passage, ...]
    confidence: str
    confidence_reason: str
    considered: int = 0
    filters: Filters = field(default_factory=Filters)


def check_coherence(connection: sqlite3.Connection, manifest: Manifest) -> dict[DocId, str]:
    """Refuse to query an index built by a different model (unchanged, §4.4) or extracted by a
    free backend whose fingerprint has since moved on. Returns the doc_ids whose *paid* extraction
    is stale instead of refusing for them — the caller marks affected passages, never withholds
    them (decision 13)."""
    meta = store.get_meta(connection)
    expected = {
        "embedding_provider": manifest.embedding.provider,
        "embedding_model": manifest.embedding.model,
        "embedding_dim": str(manifest.embedding.dim),
    }
    if manifest.embedding.revision:
        expected["embedding_revision"] = manifest.embedding.revision

    differences = {
        key: (meta.get(key, "(absent)"), value)
        for key, value in expected.items()
        if meta.get(key, "") != value
    }
    if differences:
        raise CoherenceError(differences)

    return _check_extraction_coherence(connection, manifest.extraction.model)


def _check_extraction_coherence(connection: sqlite3.Connection, model: str) -> dict[DocId, str]:
    stale_paid: dict[DocId, str] = {}
    known = set(registered_extractors())
    rows = connection.execute(
        "SELECT DISTINCT extraction_backend, extraction_fingerprint FROM documents "
        "WHERE state = 'active' AND extraction_backend IS NOT NULL"
    )
    for row in rows:
        backend = str(row["extraction_backend"])
        stored = str(row["extraction_fingerprint"])
        if backend not in known:
            # A future version's KB, or an extra no longer installed — cannot compare what cannot
            # be computed. `pnk doctor` WARNs about this separately; a query must still proceed,
            # because refusing every query on an otherwise-healthy KB over one unrecognised name
            # is a worse failure than the one this check exists to prevent.
            continue
        current = extraction_fingerprint(backend, model)
        if current == stored:
            continue
        affected = connection.execute(
            "SELECT id, path FROM documents "
            "WHERE state = 'active' AND extraction_backend = ? AND extraction_fingerprint = ?",
            (backend, stored),
        ).fetchall()
        if is_paid_backend(backend):
            stale_paid.update((DocId(str(r["id"])), stored) for r in affected)
        else:
            raise ExtractionCoherenceError(
                backend,
                stored_fingerprint=stored,
                current_fingerprint=current,
                paths=[str(r["path"]) for r in affected],
            )
    return stale_paid


def escape_fts(query: str) -> str:
    """Turn free text into an FTS5 expression.

    User text is not FTS5 syntax: `AND`, `*`, `"` and `NEAR` all mean something to the parser, and a
    bare apostrophe is a syntax error. Every word is quoted as a literal and joined with `OR`, which
    keeps recall — an implicit `AND` would drop a passage for one missing word.
    """
    words = _WORD.findall(query)
    if not words:
        return ""
    return " OR ".join('"' + word.replace('"', '""') + '"' for word in words)


def _filter_sql(filters: Filters) -> tuple[str, list[Any]]:
    clauses = ["d.state = 'active'"]
    parameters: list[Any] = []

    if filters.path_prefix:
        clauses.append("d.path LIKE ?")
        parameters.append(f"{filters.path_prefix}%")
    if filters.source_type:
        clauses.append("d.source_type = ?")
        parameters.append(filters.source_type)
    if filters.modified_after is not None:
        clauses.append("d.mtime >= ?")
        parameters.append(filters.modified_after)
    if filters.modified_before is not None:
        clauses.append("d.mtime <= ?")
        parameters.append(filters.modified_before)
    for tag in filters.tags:
        # Tags live in the metadata JSON, which sqlite can query directly — no second table, and
        # the sidecar stays the only place a user edits them.
        clauses.append(
            "EXISTS (SELECT 1 FROM json_each(d.metadata, '$.tags') WHERE json_each.value = ?)"
        )
        parameters.append(tag)

    return " AND ".join(clauses), parameters


def _allowed_chunks(connection: sqlite3.Connection, filters: Filters) -> set[int]:
    where, parameters = _filter_sql(filters)
    rows = connection.execute(
        f"SELECT c.id FROM chunks c JOIN documents d ON d.id = c.doc_id WHERE {where}", parameters
    )
    return {int(row["id"]) for row in rows}


def _lexical(
    connection: sqlite3.Connection, query: str, allowed: set[int], limit: int
) -> list[int]:
    expression = escape_fts(query)
    if not expression:
        return []
    rows = connection.execute(
        "SELECT rowid AS chunk_id, bm25(chunks_fts) AS score FROM chunks_fts "
        "WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?",
        (expression, limit * 4),
    )
    ranked = [int(row["chunk_id"]) for row in rows]
    return [chunk_id for chunk_id in ranked if chunk_id in allowed][:limit]


def _vector(
    connection: sqlite3.Connection,
    backend: EmbeddingBackend,
    query: str,
    allowed: set[int],
    *,
    dim: int,
    limit: int,
) -> list[int]:
    chunk_ids, matrix = store.load_vectors(connection, dim=dim)
    if not chunk_ids:
        return []

    embedded = backend.embed([query])
    if embedded.shape[0] == 0:  # pragma: no cover — a backend returning nothing for one query
        return []

    similarities = _normalise(matrix) @ _normalise(embedded)[0]
    order = np.argsort(-similarities)

    ranked: list[int] = []
    for position in order:
        # A non-positive cosine means the passage shares no direction at all with the query. Real
        # models rarely produce one, but when they do it is not weak evidence — it is none, and
        # padding the candidate list with it only gives fusion noise to rank.
        if similarities[int(position)] <= 0:
            break
        chunk_id = chunk_ids[int(position)]
        if chunk_id in allowed:
            ranked.append(chunk_id)
            if len(ranked) == limit:
                break
    return ranked


def _normalise(
    matrix: "np.ndarray[Any, np.dtype[np.float32]]",
) -> "np.ndarray[Any, np.dtype[np.float32]]":
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return np.divide(matrix, np.where(norms == 0, 1, norms))


def _fuse(lexical: Sequence[int], vector: Sequence[int]) -> dict[int, float]:
    """Reciprocal Rank Fusion. Rank-based, so BM25 and cosine never need a common scale."""
    scores: dict[int, float] = {}
    for ranking in (lexical, vector):
        for position, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + position + 1)
    return scores


def _coverage(text: str, query: str) -> float:
    terms = {word.lower() for word in _WORD.findall(query)}
    if not terms:
        return 0.0
    present = {word.lower() for word in _WORD.findall(text)}
    return len(terms & present) / len(terms)


def search(
    connection: sqlite3.Connection,
    manifest: Manifest,
    query: str,
    *,
    backend: EmbeddingBackend,
    reranker: Reranker | None = None,
    filters: Filters | None = None,
    limit: int | None = None,
) -> SearchResult:
    stale_paid = check_coherence(connection, manifest)
    filters = filters or Filters()
    settings = manifest.retrieval
    final_k = limit or settings.final_k

    allowed = _allowed_chunks(connection, filters)
    if not allowed:
        return SearchResult(query, (), UNKNOWN, "nothing matched the filters", 0, filters)

    lexical = _lexical(connection, query, allowed, settings.candidates_per_source)
    vector = _vector(
        connection,
        backend,
        query,
        allowed,
        dim=manifest.embedding.dim,
        limit=settings.candidates_per_source,
    )

    fused = _fuse(lexical, vector)
    if not fused:
        return SearchResult(query, (), UNKNOWN, "no candidates", 0, filters)

    lexical_positions = {chunk_id: rank for rank, chunk_id in enumerate(lexical)}
    vector_positions = {chunk_id: rank for rank, chunk_id in enumerate(vector)}
    rows = _hydrate(connection, sorted(fused, key=lambda cid: -fused[cid])[: settings.fusion_top_k])

    passages = [
        Passage(
            doc_id=row.doc_id,
            path=row.path,
            title=row.title,
            heading_path=row.heading_path,
            text=row.text,
            char_start=row.char_start,
            char_end=row.char_end,
            lexical_rank=lexical_positions.get(row.id),
            vector_rank=vector_positions.get(row.id),
            fused_score=fused[row.id],
            rerank_score=None,
            stale_extraction=stale_paid.get(row.doc_id),
            page_start=row.page_start,
            page_end=row.page_end,
        )
        for row in rows
    ]

    # Coverage is a tiebreak only: as a gate it would penalise exactly the paraphrase queries the
    # vector half exists to serve (§4.2).
    passages.sort(key=lambda p: (-p.fused_score, -_coverage(p.text, query), p.path))
    considered = len(passages)

    if settings.rerank == "local" and reranker is not None and passages:
        scores = reranker.score(query, [passage.text for passage in passages])
        passages = [
            replace(passage, rerank_score=score)
            for passage, score in zip(passages, scores, strict=True)
        ]
        passages.sort(key=lambda p: (-(p.rerank_score or 0.0), -_coverage(p.text, query), p.path))

    top = tuple(passages[:final_k])
    confidence, reason = _confidence(manifest, reranker, top)
    return SearchResult(query, top, confidence, reason, considered, filters)


@dataclass(frozen=True, slots=True)
class _ChunkRow:
    """One hydrated chunk. `sqlite3.Row` hands back `Any`; narrowing happens here, once."""

    id: int
    doc_id: DocId
    text: str
    char_start: int
    char_end: int
    heading_path: str | None
    path: str
    title: str | None
    page_start: int | None
    page_end: int | None


def _hydrate(connection: sqlite3.Connection, chunk_ids: Sequence[int]) -> list[_ChunkRow]:
    if not chunk_ids:
        return []
    placeholders = ", ".join("?" for _ in chunk_ids)
    rows = connection.execute(
        "SELECT c.id, c.doc_id, c.text, c.char_start, c.char_end, c.heading_path, "
        "c.page_start, c.page_end, d.path, d.title "
        "FROM chunks c JOIN documents d ON d.id = c.doc_id "
        f"WHERE c.id IN ({placeholders})",
        list(chunk_ids),
    )
    return [
        _ChunkRow(
            id=int(row["id"]),
            doc_id=DocId(str(row["doc_id"])),
            text=str(row["text"]),
            char_start=int(row["char_start"]),
            char_end=int(row["char_end"]),
            heading_path=None if row["heading_path"] is None else str(row["heading_path"]),
            path=str(row["path"]),
            title=None if row["title"] is None else str(row["title"]),
            page_start=None if row["page_start"] is None else int(row["page_start"]),
            page_end=None if row["page_end"] is None else int(row["page_end"]),
        )
        for row in rows
    ]


def _confidence(
    manifest: Manifest, reranker: Reranker | None, passages: Sequence[Passage]
) -> tuple[str, str]:
    """`unknown` unless thresholds exist *and* were fitted for the reranker actually in use."""
    if not passages:
        return UNKNOWN, "no passages"

    thresholds = manifest.retrieval.confidence
    if thresholds is None:
        return UNKNOWN, "no calibrated thresholds in the manifest ([retrieval.confidence])"
    if manifest.retrieval.rerank != "local" or reranker is None:
        return UNKNOWN, "thresholds are fitted on reranker scores, and reranking is off"

    active = reranker.info().fingerprint()
    if thresholds.fitted_for != active:
        return (
            UNKNOWN,
            f"thresholds were fitted for {thresholds.fitted_for}, but {active} is in use",
        )

    best = passages[0].rerank_score
    if best is None:  # pragma: no cover — reranking ran, so a score exists
        return UNKNOWN, "no reranker score"
    if best < thresholds.low_below:
        return LOW, f"top rerank score {best:.3f} is below {thresholds.low_below}"
    if best > thresholds.high_above:
        return HIGH, f"top rerank score {best:.3f} is above {thresholds.high_above}"
    return MEDIUM, f"top rerank score {best:.3f} sits between the fitted thresholds"
