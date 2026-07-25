"""Retrieval: the pipeline narrows correctly, refuses incoherent indexes, and never guesses."""

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from pinakes import store
from pinakes.embed import EmbeddingBackend, ModelInfo, Vectors
from pinakes.errors import CoherenceError
from pinakes.manifest import Manifest, load
from pinakes.search import (
    HIGH,
    LOW,
    MEDIUM,
    UNKNOWN,
    Filters,
    SearchResult,
    escape_fts,
    search,
)
from pinakes.sync import SyncOptions, sync

DIM = 4


class KeywordBackend:
    """Embeds on a fixed vocabulary, so cosine similarity is exactly predictable."""

    VOCABULARY = ("retrieval", "ranking", "sourdough", "physics")

    def embed(self, texts: Sequence[str]) -> Vectors:
        rows = [
            np.array(
                [1.0 if word in text.lower() else 0.0 for word in self.VOCABULARY],
                dtype=np.float32,
            )
            for text in texts
        ]
        if not rows:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", None, DIM, 512)


class ScriptedReranker:
    """Returns whatever the test asked for, keyed by a substring of the passage."""

    def __init__(self, scores: dict[str, float], *, model: str = "fake-reranker@v1") -> None:
        self._scores = scores
        self._model = model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        return [
            next((value for key, value in self._scores.items() if key in passage), 0.0)
            for passage in passages
        ]

    def info(self) -> ModelInfo:
        model, _, revision = self._model.partition("@")
        return ModelInfo("fake", model, revision or None, 0, 512)


def backend_factory(manifest: Manifest, offline: bool) -> EmbeddingBackend:
    return KeywordBackend()


MANIFEST = """\
[kb]
name = "t"
id = "01KYCJ8ZVMBJDB4FKRJRNYS5DT"

[sources]
roots = ["docs/"]
include = ["**/*.md"]

[embedding]
provider = "fake"
model = "fake-model"
dim = 4

[chunking]
max_tokens = 60
overlap = 0

[retrieval]
candidates_per_source = 10
fusion_top_k = 6
final_k = 3
rerank = "none"
"""


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "docs").mkdir(parents=True)
    (root / "pinakes.toml").write_text(MANIFEST, encoding="utf-8")
    (root / "docs" / "retrieval.md").write_text(
        "# Retrieval\n\nHybrid retrieval fuses lexical and dense candidates.\n", encoding="utf-8"
    )
    (root / "docs" / "ranking.md").write_text(
        "# Ranking\n\nRanking decides which passages a reader sees first.\n", encoding="utf-8"
    )
    (root / "docs" / "baking.md").write_text(
        "# Baking\n\nSourdough needs a patient starter.\n", encoding="utf-8"
    )
    sync(load(root), options=SyncOptions(), backend_factory=backend_factory, now="20260725 17:00")
    return root


def connect(kb: Path) -> sqlite3.Connection:
    return store.connect_ro(kb / ".pinakes" / "index.db")


def find(
    kb: Path,
    query: str,
    *,
    filters: Filters | None = None,
    reranker: ScriptedReranker | None = None,
) -> SearchResult:
    connection = connect(kb)
    try:
        return search(
            connection,
            load(kb),
            query,
            backend=KeywordBackend(),
            reranker=reranker,
            filters=filters,
        )
    finally:
        connection.close()


def test_a_lexical_hit_is_found(kb: Path) -> None:
    result = find(kb, "sourdough")
    assert [p.path for p in result.passages][:1] == ["docs/baking.md"]


def test_a_paraphrase_is_found_by_the_vector_half(kb: Path) -> None:
    """No lexical overlap at all: only the dense side can retrieve this."""
    connection = connect(kb)
    try:
        result = search(
            connection, load(kb), "retrieval", backend=KeywordBackend(), filters=Filters()
        )
        assert result.passages
        assert result.passages[0].path == "docs/retrieval.md"
        assert result.passages[0].vector_rank is not None
    finally:
        connection.close()


def test_results_carry_a_citable_span(kb: Path) -> None:
    result = find(kb, "sourdough")
    passage = result.passages[0]
    source = (kb / passage.path).read_text(encoding="utf-8")
    assert source[passage.char_start : passage.char_end] == passage.text
    assert passage.citation().startswith("docs/baking.md:")


def test_final_k_is_respected_and_narrows_from_fusion(kb: Path) -> None:
    result = find(kb, "retrieval ranking sourdough")
    assert len(result.passages) <= 3
    assert result.considered >= len(result.passages)


def test_tag_filter_uses_the_sidecar_metadata(kb: Path) -> None:
    import yaml

    sidecar = kb / "docs" / "baking.md.pnk.yaml"
    data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    data["tags"] = ["cooking"]
    sidecar.write_text(yaml.safe_dump(data), encoding="utf-8")
    sync(load(kb), options=SyncOptions(), backend_factory=backend_factory, now="20260725 17:05")

    result = find(kb, "sourdough", filters=Filters(tags=("cooking",)))
    assert [p.path for p in result.passages] == ["docs/baking.md"]

    assert find(kb, "sourdough", filters=Filters(tags=("physics",))).passages == ()


def test_path_prefix_filter(kb: Path) -> None:
    assert find(kb, "sourdough", filters=Filters(path_prefix="docs/bak")).passages
    assert not find(kb, "sourdough", filters=Filters(path_prefix="docs/zzz")).passages


def test_filters_that_match_nothing_return_nothing_and_say_so(kb: Path) -> None:
    result = find(kb, "sourdough", filters=Filters(source_type="pdf"))
    assert result.passages == ()
    assert result.confidence == UNKNOWN


def test_a_deleted_document_is_never_returned(kb: Path) -> None:
    (kb / "docs" / "baking.md").unlink()
    sync(load(kb), options=SyncOptions(), backend_factory=backend_factory, now="20260725 17:10")
    assert all(p.path != "docs/baking.md" for p in find(kb, "sourdough").passages)


@pytest.mark.parametrize(
    "query",
    ["retrieval AND ranking", 'a "quoted" phrase', "NEAR(a b)", "wild*", "it's", "OR", "()"],
)
def test_user_text_is_never_fts_syntax(kb: Path, query: str) -> None:
    """Every one of these means something to the FTS5 parser; none may reach it unescaped."""
    find(kb, query)  # must not raise


def test_a_passage_with_no_similarity_at_all_is_not_a_candidate(kb: Path) -> None:
    """Zero cosine is not weak evidence, it is none; padding the list only gives fusion noise."""
    (kb / "docs" / "baking.md").unlink()
    sync(load(kb), options=SyncOptions(), backend_factory=backend_factory, now="20260725 17:10")
    assert find(kb, "sourdough").passages == ()


def test_escape_fts_shapes() -> None:
    assert escape_fts("hybrid retrieval") == '"hybrid" OR "retrieval"'
    assert escape_fts("   ") == ""
    assert escape_fts('say "hi"') == '"say" OR "hi"'


def test_an_incoherent_index_refuses_to_answer(kb: Path) -> None:
    """A KB that silently returns garbage after a model change is worse than one that stops."""
    connection = store.connect_rw(kb / ".pinakes" / "index.db")
    store.set_meta(connection, {"embedding_model": "some-other-model"})
    connection.commit()
    connection.close()

    connection = connect(kb)
    try:
        with pytest.raises(CoherenceError) as exc_info:
            search(connection, load(kb), "anything", backend=KeywordBackend())
        assert "--rebuild" in exc_info.value.remedy
        assert "embedding_model" in exc_info.value.message
    finally:
        connection.close()


def _with_confidence(kb: Path, block: str) -> Manifest:
    path = kb / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace('rerank = "none"', 'rerank = "local"') + block,
        encoding="utf-8",
    )
    return load(kb)


def test_confidence_is_unknown_without_calibration(kb: Path) -> None:
    connection = connect(kb)
    try:
        result = search(
            connection,
            load(kb),
            "retrieval",
            backend=KeywordBackend(),
            reranker=ScriptedReranker({"Hybrid": 0.9}),
        )
        assert result.confidence == UNKNOWN
        assert "no calibrated thresholds" in result.confidence_reason
    finally:
        connection.close()


def test_confidence_is_unknown_when_fitted_for_a_different_reranker(kb: Path) -> None:
    """Thresholds are only meaningful for the model they were fitted against (§4.2)."""
    manifest = _with_confidence(
        kb,
        '\n[retrieval.confidence]\nfitted_for = "some-other@v9"\n'
        "low_below = 0.3\nhigh_above = 0.7\n",
    )
    connection = connect(kb)
    try:
        result = search(
            connection,
            manifest,
            "retrieval",
            backend=KeywordBackend(),
            reranker=ScriptedReranker({"Hybrid": 0.9}),
        )
        assert result.confidence == UNKNOWN
        assert "fitted for some-other@v9" in result.confidence_reason
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.1, LOW), (0.5, MEDIUM), (0.95, HIGH)],
)
def test_calibrated_thresholds_produce_a_signal(kb: Path, score: float, expected: str) -> None:
    manifest = _with_confidence(
        kb,
        '\n[retrieval.confidence]\nfitted_for = "fake-reranker@v1"\nlow_below = 0.3\n'
        "high_above = 0.7\n",
    )
    connection = connect(kb)
    try:
        result = search(
            connection,
            manifest,
            "retrieval",
            backend=KeywordBackend(),
            reranker=ScriptedReranker({"Hybrid": score, "Ranking": score - 0.05}),
        )
        assert result.confidence == expected
    finally:
        connection.close()


def test_reranking_reorders_the_survivors(kb: Path) -> None:
    manifest = _with_confidence(kb, "")
    connection = connect(kb)
    try:
        result = search(
            connection,
            manifest,
            "retrieval ranking",
            backend=KeywordBackend(),
            reranker=ScriptedReranker({"Ranking": 9.0, "Hybrid": 1.0}),
        )
        assert result.passages[0].path == "docs/ranking.md"
        assert result.passages[0].rerank_score == 9.0
    finally:
        connection.close()


def test_an_empty_index_answers_without_crashing(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    (root / "docs").mkdir(parents=True)
    (root / "pinakes.toml").write_text(MANIFEST, encoding="utf-8")
    sync(load(root), options=SyncOptions(), backend_factory=backend_factory, now="20260725 17:00")

    connection = store.connect_ro(root / ".pinakes" / "index.db")
    try:
        result = search(connection, load(root), "anything", backend=KeywordBackend())
        assert result.passages == ()
        assert result.confidence == UNKNOWN
    finally:
        connection.close()
