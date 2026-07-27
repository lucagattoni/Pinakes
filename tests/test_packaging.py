"""Packaging invariants: extras stay extras, and each library imports cleanly when installed."""

import tomllib
from collections.abc import Callable
from importlib import import_module
from importlib.machinery import ModuleSpec
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import conftest
import pytest

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _pyproject() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _spec_absent(name: str) -> ModuleSpec | None:
    return None


def _spec_present(name: str) -> ModuleSpec | None:
    return ModuleSpec(name, None)


def _spec_for(*present: str) -> Callable[[str], ModuleSpec | None]:
    """A `find_spec` stand-in reporting only the named modules as importable."""

    def find(name: str) -> ModuleSpec | None:
        return ModuleSpec(name, None) if name in present else None

    return find


def test_extractors_stay_extras() -> None:
    """`pypdfium2`/`anthropic` must never enter core — a light install stays torch-free (§4.5)."""
    dependencies = " ".join(_pyproject()["project"]["dependencies"]).lower()
    assert "pypdfium2" not in dependencies
    assert "anthropic" not in dependencies


def test_claude_extra_requires_pdf_extra() -> None:
    """The paid path slices, pre-checks and audits through pypdfium2 — it cannot run without it."""
    optional = _pyproject()["project"]["optional-dependencies"]
    assert "pinakes[pdf]" in optional["claude"]


@pytest.mark.skipif(find_spec("pypdfium2") is None, reason="pinakes[pdf] not installed")
def test_pypdfium2_imports_without_a_warning() -> None:
    """`filterwarnings = ["error"]` (pyproject) turns any import-time warning into this failing."""
    import_module("pypdfium2")


@pytest.mark.skipif(find_spec("anthropic") is None, reason="pinakes[claude] not installed")
def test_anthropic_imports_without_a_warning() -> None:
    import_module("anthropic")


def test_pdf_runnable_requires_all_three_conditions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pypdfium2, Pillow, and the corpus — checking fewer than all three passes on a KB missing one.

    Pillow joined this predicate in I2 (dev-group-only, never core, never an extra): a pypdfium2 +
    corpus check that forgot it would report runnable in an environment where `pdf`-marked tests
    would still crash constructing a `PIL.Image`, not skip.
    """
    corpus = tmp_path / "pdf-corpus"
    monkeypatch.setattr(conftest, "PDF_CORPUS", corpus)

    monkeypatch.setattr(conftest, "find_spec", _spec_absent)
    assert conftest.pdf_runnable() is False  # nothing holds

    corpus.mkdir()
    assert conftest.pdf_runnable() is False  # corpus present, neither library is

    monkeypatch.setattr(conftest, "find_spec", _spec_for("pypdfium2"))
    assert conftest.pdf_runnable() is False  # pypdfium2 only, Pillow still missing

    monkeypatch.setattr(conftest, "find_spec", _spec_for("PIL"))
    assert conftest.pdf_runnable() is False  # Pillow only, pypdfium2 still missing

    monkeypatch.setattr(conftest, "find_spec", _spec_present)
    assert conftest.pdf_runnable() is True  # all three hold


def test_paid_runnable_requires_all_three_conditions(monkeypatch: pytest.MonkeyPatch) -> None:
    """`anthropic` importable, a key present, and the pytest-only opt-in — all three, not two."""
    monkeypatch.setattr(conftest, "find_spec", _spec_present)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("PINAKES_ALLOW_SPEND", "1")
    assert conftest.paid_runnable() is True

    monkeypatch.setattr(conftest, "find_spec", _spec_absent)
    assert conftest.paid_runnable() is False  # anthropic not importable
    monkeypatch.setattr(conftest, "find_spec", _spec_present)

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert conftest.paid_runnable() is False  # no key present
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    monkeypatch.setenv("PINAKES_ALLOW_SPEND", "0")
    assert conftest.paid_runnable() is False  # opt-in set, but not to exactly "1"
