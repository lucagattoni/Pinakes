"""`pnk search` end to end through the real CLI, with a registered fake backend."""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from pinakes.cli import main
from pinakes.embed import (
    ModelInfo,
    Vectors,
    register_embedding_backend,
    register_reranker,
)
from pinakes.init import init
from pinakes.manifest import load
from pinakes.sync import SyncOptions, sync

VOCABULARY = ("retrieval", "ranking", "sourdough")


class FakeBackend:
    def embed(self, texts: Sequence[str]) -> Vectors:
        rows = [
            np.array([1.0 if w in t.lower() else 0.0 for w in VOCABULARY], dtype=np.float32)
            for t in texts
        ]
        if not rows:
            return np.zeros((0, len(VOCABULARY)), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", None, len(VOCABULARY), 512)


class FakeReranker:
    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        return [float(len(set(query.lower().split()) & set(p.lower().split()))) for p in passages]

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-reranker", None, 0, 512)


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    """A KB built through the real `init` + `sync`, then pointed at the fake backend."""
    register_embedding_backend("fake", lambda section, offline: FakeBackend())
    register_reranker("fake", lambda section, offline: FakeReranker())

    result = init(tmp_path / "kb", now="20260725 17:40")
    manifest_path = result.root / "pinakes.toml"
    text = manifest_path.read_text(encoding="utf-8")
    text = text.replace('provider = "sentence-transformers"', 'provider = "fake"')
    text = text.replace('model    = "BAAI/bge-small-en-v1.5"', 'model    = "fake-model"')
    text = text.replace("dim      = 384", f"dim      = {len(VOCABULARY)}")
    text = text.replace('model    = "BAAI/bge-reranker-base"', 'model    = "fake-reranker"')
    text = text.replace("max_tokens = 510", "max_tokens = 60")
    text = text.replace("overlap    = 64", "overlap    = 8")
    manifest_path.write_text(text, encoding="utf-8")

    (result.root / "docs" / "a.md").write_text(
        "# Retrieval\n\nHybrid retrieval fuses lexical and dense candidates.\n", encoding="utf-8"
    )
    (result.root / "docs" / "b.md").write_text(
        "# Baking\n\nSourdough needs a patient starter.\n", encoding="utf-8"
    )
    sync(load(result.root), options=SyncOptions(), now="20260725 17:41")
    return result.root


def test_search_prints_cited_passages_and_a_confidence_line(
    kb: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["search", "sourdough", "--kb", str(kb)]) == 0
    out = capsys.readouterr().out
    assert "docs/b.md" in out
    assert "Sourdough needs a patient starter" in out
    assert "confidence: unknown" in out


def test_an_uncalibrated_kb_says_so_without_naming_a_command_that_does_not_exist(
    kb: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["search", "sourdough", "--kb", str(kb)])
    out = capsys.readouterr().out
    assert "planned for v0.4" in out


def test_json_output_has_a_stable_shape(kb: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["search", "retrieval", "--kb", str(kb), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert set(payload) == {"query", "confidence", "confidence_reason", "considered", "passages"}
    assert payload["passages"]
    assert set(payload["passages"][0]) == {
        "doc_id",
        "path",
        "title",
        "heading_path",
        "char_start",
        "char_end",
        "text",
        "rerank_score",
        "fused_score",
    }


def test_filters_reach_the_pipeline(kb: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["search", "sourdough", "--kb", str(kb), "--path-prefix", "docs/a", "--json"])
    assert json.loads(capsys.readouterr().out)["passages"] == []


def test_a_bad_date_is_a_usage_level_error(kb: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["search", "x", "--kb", str(kb), "--modified-after", "yesterday"]) == 1
    assert "YYYYMMDD" in capsys.readouterr().err


def test_searching_outside_a_kb_says_how_to_fix_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["search", "x", "--kb", str(tmp_path)]) == 1
    assert "pnk init" in capsys.readouterr().err


def test_the_readme_quickstart_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The three commands the README promises, run through the real CLI in order."""
    register_embedding_backend("fake", lambda section, offline: FakeBackend())
    register_reranker("fake", lambda section, offline: FakeReranker())

    root = tmp_path / "my-kb"
    assert main(["init", str(root)]) == 0

    manifest_path = root / "pinakes.toml"
    text = manifest_path.read_text(encoding="utf-8")
    text = text.replace('provider = "sentence-transformers"', 'provider = "fake"')
    text = text.replace('model    = "BAAI/bge-small-en-v1.5"', 'model    = "fake-model"')
    text = text.replace("dim      = 384", f"dim      = {len(VOCABULARY)}")
    text = text.replace('model    = "BAAI/bge-reranker-base"', 'model    = "fake-reranker"')
    manifest_path.write_text(text, encoding="utf-8")

    (root / "docs" / "note.md").write_text("# Note\n\nAbout retrieval.\n", encoding="utf-8")

    assert main(["sync", "--kb", str(root)]) == 0
    capsys.readouterr()
    assert main(["search", "retrieval", "--kb", str(root)]) == 0
    assert "docs/note.md" in capsys.readouterr().out
