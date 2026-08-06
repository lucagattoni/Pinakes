"""Embedding and reranking backends — the only part of the free path that needs model weights.

Two protocols, two open registries, and lazy imports. The shape follows three constraints:

* **Core install must stay light.** Neither backend is imported until a manifest asks for it, so
  `uv add pinakes` never pulls torch. A missing backend fails with the exact extra to install
  (docs/DESIGN.md §4.5), which is a supported state, not a broken one.
* **The registry is open.** Providers are looked up in a dict, not matched against an enum, so tests
  can register a deterministic fake and drive the real CLI end to end without downloading anything.
* **Weights live in one shared cache.** `HF_HOME` by default, so N KBs on a machine share one copy.
  fastembed left alone caches to `$TMPDIR/fastembed_cache` (verified in its `define_cache_dir`,
  20260725 15:15), so this module passes it an explicit directory under the HF cache instead.

Both protocols expose `info()`, because §4.4's coherence check compares what built the index against
what is loaded now, and §4.2's confidence thresholds are only valid for the reranker they were
fitted against.
"""

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from pinakes.errors import BackendMissingError, BackendUnknownError, EmbeddingError
from pinakes.manifest import EmbeddingSection, RerankSection

SENTENCE_TRANSFORMERS = "sentence-transformers"
FASTEMBED = "fastembed"

type Vectors = np.ndarray[Any, np.dtype[np.float32]]


@dataclass(frozen=True, slots=True)
class ModelInfo:
    provider: str
    model: str
    revision: str | None
    dim: int
    max_seq_length: int

    def fingerprint(self) -> str:
        """`model@revision` — what `[retrieval.confidence] fitted_for` records (§4.2)."""
        return f"{self.model}@{self.revision}" if self.revision else self.model


class EmbeddingBackend(Protocol):
    def embed(self, texts: Sequence[str]) -> Vectors: ...
    def count_tokens(self, text: str) -> int: ...
    def info(self) -> ModelInfo: ...


class Reranker(Protocol):
    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...
    def info(self) -> ModelInfo: ...


type EmbeddingFactory = Callable[[EmbeddingSection, bool], EmbeddingBackend]
type RerankerFactory = Callable[[RerankSection, bool], Reranker]

_EMBEDDING_BACKENDS: dict[str, EmbeddingFactory] = {}
_RERANKERS: dict[str, RerankerFactory] = {}


def register_embedding_backend(provider: str, factory: EmbeddingFactory) -> None:
    _EMBEDDING_BACKENDS[provider] = factory


def register_reranker(provider: str, factory: RerankerFactory) -> None:
    _RERANKERS[provider] = factory


def registered_embedding_providers() -> list[str]:
    return sorted(_EMBEDDING_BACKENDS)


def load_backend(section: EmbeddingSection, *, offline: bool = False) -> EmbeddingBackend:
    """Build the embedding backend a manifest asks for, and check it agrees about `dim`."""
    factory = _EMBEDDING_BACKENDS.get(section.provider)
    if factory is None:
        raise BackendUnknownError(section.provider, known=registered_embedding_providers())

    backend = factory(section, offline)
    info = backend.info()
    if info.dim != section.dim:
        raise EmbeddingError(
            f"[embedding] dim = {section.dim}, but {info.model} produces {info.dim} dimensions.",
            remedy=(
                f"Set dim = {info.dim} and run `pnk sync --rebuild`. A mismatch here would store "
                "vectors that cannot be compared."
            ),
        )
    return backend


def load_reranker(section: RerankSection, *, offline: bool = False) -> Reranker:
    factory = _RERANKERS.get(section.provider)
    if factory is None:
        raise BackendUnknownError(section.provider, known=sorted(_RERANKERS))
    return factory(section, offline)


def hf_cache_dir() -> Path:
    """The shared Hugging Face cache — one copy of the weights per machine, not per KB (§4.5)."""
    home = os.environ.get("HF_HOME")
    if home:
        return Path(home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


# The package each provider's factories import — used only to check, via `find_spec`, whether a
# *sibling* provider is already installed when the configured one is missing (never to import it:
# probing availability by loading a backend is exactly what the paid-path invariant forbids for
# the paid extractor, and the same reasoning applies here — a check must not have the side effects
# of the thing it is checking).
_PROVIDER_PACKAGE: dict[str, str] = {
    SENTENCE_TRANSFORMERS: "sentence_transformers",
    FASTEMBED: "fastembed",
}


def _installed_alternative(missing: str, siblings: Sequence[str]) -> str | None:
    """The first *other* registered provider whose package is importable on this machine, if any.

    `siblings` is every provider registered for the same kind (embedding or rerank) — including
    test fakes, which `_PROVIDER_PACKAGE` has no entry for and so are silently skipped rather than
    misreported as installed.
    """
    from importlib.util import find_spec

    for provider in siblings:
        if provider == missing:
            continue
        package = _PROVIDER_PACKAGE.get(provider)
        if package is not None and find_spec(package) is not None:
            return provider
    return None


def _import(module: str, extra: str, what: str, *, siblings: Sequence[str]) -> Any:
    try:
        return __import__(module, fromlist=["_"])
    except ImportError as exc:
        alternative = _installed_alternative(what, siblings)
        raise BackendMissingError(what, extra=extra, alternative=alternative) from exc


def _sentence_transformers_backend(section: EmbeddingSection, offline: bool) -> EmbeddingBackend:
    module = _import(
        "sentence_transformers", "st", section.provider, siblings=registered_embedding_providers()
    )
    model = module.SentenceTransformer(
        section.model,
        revision=section.revision,
        local_files_only=offline,
        cache_folder=str(hf_cache_dir()),
    )
    return _SentenceTransformersBackend(section, model)


def _sentence_transformers_reranker(section: RerankSection, offline: bool) -> Reranker:
    module = _import("sentence_transformers", "st", section.provider, siblings=sorted(_RERANKERS))
    model = module.CrossEncoder(
        section.model,
        revision=section.revision,
        local_files_only=offline,
        cache_folder=str(hf_cache_dir()),
    )
    return _SentenceTransformersReranker(section, model)


def _fastembed_backend(section: EmbeddingSection, offline: bool) -> EmbeddingBackend:
    module = _import(
        "fastembed", "light", section.provider, siblings=registered_embedding_providers()
    )
    _require_online_or_cached(offline)
    model = module.TextEmbedding(model_name=section.model, cache_dir=str(hf_cache_dir()))
    return _FastembedBackend(section, model)


def _fastembed_reranker(section: RerankSection, offline: bool) -> Reranker:
    module = _import(
        "fastembed.rerank.cross_encoder", "light", section.provider, siblings=sorted(_RERANKERS)
    )
    _require_online_or_cached(offline)
    model = module.TextCrossEncoder(model_name=section.model, cache_dir=str(hf_cache_dir()))
    return _FastembedReranker(section, model)


def _require_online_or_cached(offline: bool) -> None:
    """fastembed has no `local_files_only`; `--offline` is honoured by refusing to reach out."""
    if offline and not hf_cache_dir().exists():
        raise EmbeddingError(
            f"--offline was requested but no model cache exists at {hf_cache_dir()}.",
            remedy="Run once without --offline to populate the cache.",
        )


class _SentenceTransformersBackend:
    def __init__(self, section: EmbeddingSection, model: Any) -> None:
        self._section = section
        self._model = model

    def embed(self, texts: Sequence[str]) -> Vectors:
        vectors: Any = self._model.encode(
            list(texts), convert_to_numpy=True, normalize_embeddings=True
        )
        return np.ascontiguousarray(vectors, dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(self._model.tokenizer.encode(text, add_special_tokens=False))

    def info(self) -> ModelInfo:
        return ModelInfo(
            provider=self._section.provider,
            model=self._section.model,
            revision=self._section.revision,
            dim=int(self._model.get_sentence_embedding_dimension()),
            max_seq_length=int(self._model.max_seq_length),
        )


class _SentenceTransformersReranker:
    def __init__(self, section: RerankSection, model: Any) -> None:
        self._section = section
        self._model = model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        scores: Any = self._model.predict([(query, passage) for passage in passages])
        return [float(score) for score in scores]

    def info(self) -> ModelInfo:
        config: Any = getattr(self._model, "config", None)
        window = int(getattr(config, "max_position_embeddings", 512)) if config else 512
        return ModelInfo(
            provider=self._section.provider,
            model=self._section.model,
            revision=self._section.revision,
            dim=0,  # a cross-encoder emits a score, not a vector
            max_seq_length=window,
        )


class _FastembedBackend:
    def __init__(self, section: EmbeddingSection, model: Any) -> None:
        self._section = section
        self._model = model

    def embed(self, texts: Sequence[str]) -> Vectors:
        listed = list(texts)
        if not listed:
            return np.zeros((0, self.info().dim), dtype=np.float32)
        vectors = np.vstack([np.asarray(v, dtype=np.float32) for v in self._model.embed(listed)])
        return np.ascontiguousarray(vectors, dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        """fastembed exposes the HF tokenizer it loaded; `max_seq_length` is not public API."""
        tokenizer = self._tokenizer()
        return len(tokenizer.encode(text, add_special_tokens=False).ids)

    def _tokenizer(self) -> Any:
        model: Any = getattr(self._model, "model", self._model)
        tokenizer: Any = getattr(model, "tokenizer", None)
        if tokenizer is None:  # pragma: no cover — only if fastembed changes shape
            raise EmbeddingError(
                "this fastembed version does not expose a tokenizer.",
                remedy="Pin fastembed, or use the [st] backend, which does.",
            )
        return tokenizer

    def info(self) -> ModelInfo:
        described = [
            entry
            for entry in self._model.list_supported_models()
            if entry["model"] == self._section.model
        ]
        dim = int(described[0]["dim"]) if described else self._section.dim
        truncation: Any = getattr(self._tokenizer(), "truncation", None)
        window = int(truncation["max_length"]) if truncation else 512
        return ModelInfo(
            provider=self._section.provider,
            model=self._section.model,
            revision=self._section.revision,
            dim=dim,
            max_seq_length=window,
        )


class _FastembedReranker:
    def __init__(self, section: RerankSection, model: Any) -> None:
        self._section = section
        self._model = model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        return [float(score) for score in self._model.rerank(query, list(passages))]

    def info(self) -> ModelInfo:
        return ModelInfo(
            provider=self._section.provider,
            model=self._section.model,
            revision=self._section.revision,
            dim=0,
            max_seq_length=512,
        )


register_embedding_backend(SENTENCE_TRANSFORMERS, _sentence_transformers_backend)
register_embedding_backend(FASTEMBED, _fastembed_backend)
register_reranker(SENTENCE_TRANSFORMERS, _sentence_transformers_reranker)
register_reranker(FASTEMBED, _fastembed_reranker)
