"""Backends: the registry is open, missing extras fail helpfully, and dims must agree.

Unit tests use a deterministic fake. The `model`-marked tests below exercise real weights and skip
unless they are already cached — a clean checkout must never be blocked on a 1GB download, while CI
(which caches `HF_HOME`) runs them for real.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from pinakes.embed import (
    FASTEMBED,
    SENTENCE_TRANSFORMERS,
    ModelInfo,
    Vectors,
    hf_cache_dir,
    load_backend,
    load_reranker,
    register_embedding_backend,
    registered_embedding_providers,
)
from pinakes.errors import BackendMissingError, BackendUnknownError, EmbeddingError
from pinakes.manifest import EmbeddingSection, RerankSection

DIM = 8


class FakeBackend:
    """Deterministic embeddings: a hash of the text, so tests can assert exact rankings."""

    def __init__(self, dim: int = DIM) -> None:
        self._dim = dim

    def embed(self, texts: Sequence[str]) -> Vectors:
        rows = [
            np.array(
                [((hash(text) >> (bit * 3)) % 17) / 17 for bit in range(self._dim)],
                dtype=np.float32,
            )
            for text in texts
        ]
        if not rows:
            return np.zeros((0, self._dim), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", "rev1", self._dim, 512)


def _section(provider: str = "fake", dim: int = DIM) -> EmbeddingSection:
    return EmbeddingSection(provider=provider, model="fake-model", dim=dim, revision=None)


@pytest.fixture(autouse=True)
def fake_provider() -> None:
    # Fixed width, deliberately *not* `section.dim`: a fake that adopts whatever the manifest
    # claims can never disagree with it, so the dim-mismatch check would be untestable.
    register_embedding_backend("fake", lambda section, offline: FakeBackend())


def test_the_registry_is_open_so_tests_can_supply_a_backend() -> None:
    assert "fake" in registered_embedding_providers()
    assert SENTENCE_TRANSFORMERS in registered_embedding_providers()
    assert FASTEMBED in registered_embedding_providers()

    backend = load_backend(_section())
    assert backend.embed(["a", "b"]).shape == (2, DIM)
    assert backend.embed([]).shape == (0, DIM)


def test_a_dim_disagreement_is_a_hard_error() -> None:
    """Vectors of different widths cannot be compared; storing them would poison the index."""
    with pytest.raises(EmbeddingError) as exc_info:
        load_backend(_section(dim=DIM + 1))
    assert "--rebuild" in exc_info.value.remedy


def test_an_unknown_provider_lists_the_known_ones() -> None:
    with pytest.raises(BackendUnknownError) as exc_info:
        load_backend(_section(provider="telepathy"))
    assert SENTENCE_TRANSFORMERS in exc_info.value.remedy


def test_a_missing_extra_names_the_install_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """A core-only install is a supported state — it just has to say so precisely (§4.5)."""
    import builtins

    real_import = builtins.__import__

    def refuse(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("sentence_transformers"):
            raise ImportError("no module named sentence_transformers")
        return real_import(name, *args, **kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType]

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(BackendMissingError) as exc_info:
        load_backend(_section(provider=SENTENCE_TRANSFORMERS))
    assert exc_info.value.extra == "st"
    assert 'uv add "pinakes[st]"' in exc_info.value.remedy


def test_reranker_registry_rejects_unknown_providers() -> None:
    with pytest.raises(BackendUnknownError):
        load_reranker(RerankSection(provider="telepathy", model="m", revision=None))


def test_model_fingerprint_matches_what_fitted_for_records() -> None:
    assert ModelInfo("p", "m", "abc", 4, 512).fingerprint() == "m@abc"
    assert ModelInfo("p", "m", None, 4, 512).fingerprint() == "m"


def test_weights_resolve_under_the_shared_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One copy of the weights per machine, not per KB — and never fastembed's $TMPDIR default."""
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    assert hf_cache_dir() == tmp_path / "hf" / "hub"

    monkeypatch.delenv("HF_HOME", raising=False)
    assert hf_cache_dir() == Path.home() / ".cache" / "huggingface" / "hub"
    assert "fastembed_cache" not in str(hf_cache_dir())


def _runnable(fragment: str) -> bool:
    """Both halves must hold: the backend importable *and* its weights already cached.

    Checking only the cache was wrong — the weights live in a shared, machine-wide directory, so
    they can be present in an environment that has no fastembed installed at all. The test then ran
    and failed with `BackendMissingError` instead of skipping.
    """
    from importlib.util import find_spec

    if find_spec("fastembed") is None:
        return False
    cache = hf_cache_dir()
    return cache.exists() and any(fragment in entry.name for entry in cache.iterdir())


@pytest.mark.model
@pytest.mark.skipif(not _runnable("bge-small"), reason="fastembed or its weights absent")
def test_real_embedding_backend_agrees_with_the_manifest() -> None:
    section = EmbeddingSection(
        provider=FASTEMBED, model="BAAI/bge-small-en-v1.5", dim=384, revision=None
    )
    backend = load_backend(section)
    info = backend.info()

    assert info.dim == 384
    assert 0 < info.max_seq_length <= 512
    # Assert the relationship, not a magic number: the real BPE count for that phrase is 3, and
    # an earlier ">" here was a guess that the real model promptly falsified.
    short = backend.count_tokens("retrieval augmented generation")
    assert short >= 3
    assert backend.count_tokens("retrieval augmented generation " * 10) > short

    vectors = backend.embed(["a passage about retrieval", "an unrelated passage"])
    assert vectors.shape == (2, 384)
    assert vectors.dtype == np.float32


@pytest.mark.model
@pytest.mark.skipif(not _runnable("bge-reranker"), reason="fastembed or its weights absent")
def test_real_reranker_orders_by_relevance() -> None:
    reranker = load_reranker(
        RerankSection(provider=FASTEMBED, model="BAAI/bge-reranker-base", revision=None)
    )
    scores = reranker.score(
        "how does hybrid retrieval work?",
        ["Hybrid retrieval fuses BM25 and vector search.", "A recipe for sourdough bread."],
    )
    assert len(scores) == 2
    assert scores[0] > scores[1]
    assert reranker.score("q", []) == []
