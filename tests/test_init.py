"""`pnk init`: a directory that is already correct, and an id that is never minted twice."""

from pathlib import Path

import pytest

from pinakes import template
from pinakes.errors import InitError, TemplateError
from pinakes.ids import parse_kb_id
from pinakes.init import init
from pinakes.manifest import load


def test_init_produces_a_kb_that_parses(tmp_path: Path) -> None:
    result = init(tmp_path / "research", now="20260725 17:30")
    manifest = load(result.root)

    assert manifest.kb.name == "research"
    assert manifest.kb.id == result.kb_id
    assert manifest.kb.template == "notes@1.0"
    assert manifest.kb.created == "20260725 17:30"
    assert manifest.embedding.model == "BAAI/bge-small-en-v1.5"
    assert manifest.rerank.model == "BAAI/bge-reranker-base"
    assert parse_kb_id(manifest.kb.id) == manifest.kb.id


def test_init_creates_docs_and_ignores_generated_state(tmp_path: Path) -> None:
    """Publishing a KB must never publish its index or its ledger (§4.7)."""
    result = init(tmp_path / "kb")
    assert (result.root / "docs").is_dir()
    assert ".pinakes/" in (result.root / ".gitignore").read_text(encoding="utf-8")


def test_the_template_ships_its_readme_and_a_golden_set_stub(tmp_path: Path) -> None:
    result = init(tmp_path / "kb")
    assert (result.root / "README.md").is_file()
    assert (result.root / "eval" / "questions.yaml").is_file()


def test_confidence_thresholds_are_commented_out(tmp_path: Path) -> None:
    """Thresholds fitted on someone else's corpus are not a calibration (§4.2)."""
    result = init(tmp_path / "kb")
    manifest_text = (result.root / "pinakes.toml").read_text(encoding="utf-8")
    assert "# [retrieval.confidence]" in manifest_text
    assert load(result.root).retrieval.confidence is None


def test_two_kbs_never_share_an_id(tmp_path: Path) -> None:
    first = init(tmp_path / "a")
    second = init(tmp_path / "b")
    assert first.kb_id != second.kb_id


def test_a_custom_name_is_kept(tmp_path: Path) -> None:
    result = init(tmp_path / "kb-directory", name="My Research")
    assert load(result.root).kb.name == "My Research"


def test_refusing_to_re_initialise_explains_why(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    init(root)
    with pytest.raises(InitError) as exc_info:
        init(root)
    assert "orphan every inbound link" in exc_info.value.remedy


def test_a_non_empty_directory_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "occupied"
    root.mkdir()
    (root / "something.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(InitError) as exc_info:
        init(root)
    assert "not empty" in exc_info.value.message


def test_an_unknown_template_lists_the_known_ones(tmp_path: Path) -> None:
    with pytest.raises(TemplateError) as exc_info:
        init(tmp_path / "kb", template_name="nonexistent")
    assert "notes" in exc_info.value.remedy


def test_templates_are_readable_from_the_installed_package() -> None:
    assert "notes" in template.available()
    info = template.describe("notes")
    assert info.reference == "notes@1.0"


def test_a_template_variable_that_is_never_supplied_fails_loudly() -> None:
    """StrictUndefined: a typo in a template must not render as an empty manifest key."""
    from jinja2 import UndefinedError

    with pytest.raises(UndefinedError):
        template.render_manifest("notes", {"name": "x"})
