"""Manifest parsing: strict in both directions, and cross-key invariants checked at read time."""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from pinakes._toml import Table
from pinakes.errors import ManifestError, NoKbFoundError
from pinakes.ids import mint_kb_id
from pinakes.manifest import discover, find_kb_root, load

WriteManifest = Callable[[str], Path]

MINIMAL = """\
[kb]
name = "k"
id   = "{kb_id}"

[sources]
roots = ["docs/"]

[embedding]
provider = "sentence-transformers"
model    = "BAAI/bge-small-en-v1.5"
dim      = 384
"""


def minimal(**extra: str) -> str:
    body = MINIMAL.format(kb_id=mint_kb_id())
    return body + "".join(extra.values())


def test_the_design_example_parses(kb_root: Path) -> None:
    manifest = load(kb_root)
    assert manifest.kb.name == "research"
    assert manifest.kb.template == "notes@1.0"
    assert manifest.sources.exclude == ("**/drafts/**",)
    assert manifest.embedding.dim == 384
    assert manifest.extraction.backend == "pypdfium2"
    assert manifest.extraction.model == "claude-opus-5"
    assert manifest.retrieval.final_k == 8
    assert manifest.retrieval.confidence is not None
    assert manifest.retrieval.confidence.fitted_for == "BAAI/bge-reranker-base@abc123"
    assert manifest.rerank.model == "BAAI/bge-reranker-base"
    assert manifest.budget.timezone == "UTC"
    assert manifest.links == ()


def test_paths_derive_from_the_root(kb_root: Path) -> None:
    manifest = load(kb_root)
    assert manifest.path == kb_root / "pinakes.toml"
    assert manifest.state_dir == kb_root / ".pinakes"
    assert manifest.index_path == kb_root / ".pinakes" / "index.db"


def test_omitted_sections_take_the_documented_defaults(write_manifest: WriteManifest) -> None:
    manifest = load(write_manifest(minimal()))
    assert manifest.chunking == manifest.chunking.__class__("structural", 510, 64)
    assert manifest.extraction == manifest.extraction.__class__("pypdfium2", "claude-opus-5")
    assert manifest.retrieval.candidates_per_source == 50
    assert manifest.retrieval.rerank == "local"
    assert manifest.retrieval.confidence is None
    assert manifest.rerank.model == "BAAI/bge-reranker-base"
    assert manifest.budget.on_exceed == "abort"
    assert manifest.budget.confirm_above_eur == Decimal("0.01")
    assert manifest.budget.per_operation_eur == Decimal("0.30")
    assert manifest.budget.daily_eur == Decimal("1.00")
    assert manifest.budget.monthly_eur == Decimal("5.00")
    assert manifest.budget.max_price_age_days == 30


def test_extraction_backend_must_be_registered(write_manifest: WriteManifest) -> None:
    """Rejected without importing anything: manifest validation checks the registry's key set."""
    body = minimal(extraction='\n[extraction]\nbackend = "telepathy"\n')
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "telepathy" in exc_info.value.message


def test_extraction_model_defaults_and_can_be_overridden(write_manifest: WriteManifest) -> None:
    body = minimal(
        extraction='\n[extraction]\nbackend = "claude-vision"\nmodel = "claude-opus-4-8"\n'
    )
    manifest = load(write_manifest(body))
    assert manifest.extraction.backend == "claude-vision"
    assert manifest.extraction.model == "claude-opus-4-8"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("[kb]\nname = 'k'\n", "missing required key `id`"),
        ("[sources]\nroots = ['docs/']\n", "[kb]"),
        ("[kb]\nname = 'k'\nid = 'not-a-ulid'\n", "not a ULID"),
    ],
)
def test_missing_or_broken_kb_section(
    write_manifest: WriteManifest, body: str, expected: str
) -> None:
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert expected in exc_info.value.message


def test_unknown_keys_are_rejected_not_ignored(write_manifest: WriteManifest) -> None:
    """A typo must not leave the user with defaults while believing they configured something."""
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(minimal(extra="\n[retrieval]\nfinall_k = 20\n")))
    assert "unknown key(s): `finall_k`" in exc_info.value.message
    assert "[retrieval]" in exc_info.value.message


def test_the_old_top_k_name_is_rejected_by_name(write_manifest: WriteManifest) -> None:
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(minimal(extra="\n[retrieval]\ntop_k = 8\n")))
    assert "three separate widths" in exc_info.value.message


def test_widths_must_narrow(write_manifest: WriteManifest) -> None:
    body = minimal(
        extra="\n[retrieval]\ncandidates_per_source = 10\nfusion_top_k = 20\nfinal_k = 8\n"
    )
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "widths must narrow" in exc_info.value.message


def test_final_k_may_not_exceed_fusion_top_k(write_manifest: WriteManifest) -> None:
    body = minimal(extra="\n[retrieval]\nfusion_top_k = 5\nfinal_k = 8\n")
    with pytest.raises(ManifestError):
        load(write_manifest(body))


def test_confidence_thresholds_require_the_reranker_they_were_fitted_for(
    write_manifest: WriteManifest,
) -> None:
    body = minimal(extra="\n[retrieval.confidence]\nlow_below = 0.3\nhigh_above = 0.6\n")
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "`fitted_for` is required" in exc_info.value.message
    assert "reports `unknown` rather than guessing" in exc_info.value.remedy


def test_confidence_thresholds_must_be_ordered(write_manifest: WriteManifest) -> None:
    body = minimal(
        extra="\n[retrieval.confidence]\nfitted_for = 'm@1'\nlow_below = 0.9\nhigh_above = 0.2\n"
    )
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "must not exceed" in exc_info.value.message


def test_confirm_threshold_above_the_hard_cap_is_rejected(write_manifest: WriteManifest) -> None:
    """Design pass 3 split these fields precisely so the prompt stays reachable (§5)."""
    body = minimal(extra="\n[budget]\nconfirm_above_eur = 0.10\nper_operation_eur = 0.05\n")
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "unreachable" in exc_info.value.remedy


def test_budget_timezone_must_resolve(write_manifest: WriteManifest) -> None:
    body = minimal(extra="\n[budget]\ntimezone = 'Mars/Olympus'\n")
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "not a known IANA zone" in exc_info.value.message


def test_budget_values_parse_as_exact_decimal_not_float(write_manifest: WriteManifest) -> None:
    """I6a: a `Decimal` constructed from a TOML float via `Decimal(the_float)` directly (rather
    than `Decimal(str(the_float))`) reproduces the binary value the literal only approximates —
    verified directly against every value here to fail this exact assertion if that regressed."""
    body = minimal(
        extra=(
            "\n[budget]\nconfirm_above_eur = 0.01\nper_operation_eur = 0.05\n"
            "daily_eur = 1.08\nmonthly_eur = 5.00\nmax_price_age_days = 45\n"
        )
    )
    manifest = load(write_manifest(body))
    assert manifest.budget.confirm_above_eur == Decimal("0.01")
    assert manifest.budget.per_operation_eur == Decimal("0.05")
    assert manifest.budget.daily_eur == Decimal("1.08")
    assert manifest.budget.monthly_eur == Decimal("5.00")
    assert manifest.budget.max_price_age_days == 45


def test_a_negative_budget_value_is_rejected(write_manifest: WriteManifest) -> None:
    body = minimal(extra="\n[budget]\ndaily_eur = -1.0\n")
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "must be >=" in exc_info.value.message


def test_table_decimal_validates_a_below_minimum_default_too(tmp_path: Path) -> None:
    """Every shipped `[budget]` default is in range, so `load()` alone cannot exercise this: a
    below-`minimum` *default* must still be rejected when the key is absent, not only a below-
    minimum value actually written in the TOML (`test_a_negative_budget_value_is_rejected` above).
    `integer()`/`number()` get this for free since their default and parsed-value are the same
    type and share one code path; `decimal()`'s default is pre-typed `Decimal` and used to return
    early, skipping `minimum` entirely."""
    table = Table({}, name="budget", source=tmp_path / "pinakes.toml")
    with pytest.raises(ManifestError) as exc_info:
        table.decimal("daily_eur", default=Decimal("-5"), minimum=Decimal("0"))
    assert "must be >=" in exc_info.value.message


def test_table_decimal_accepts_a_valid_default_unchanged(tmp_path: Path) -> None:
    table = Table({}, name="budget", source=tmp_path / "pinakes.toml")
    assert table.decimal("daily_eur", default=Decimal("1.00"), minimum=Decimal("0")) == Decimal(
        "1.00"
    )


def test_overlap_must_be_smaller_than_max_tokens(write_manifest: WriteManifest) -> None:
    body = minimal(extra="\n[chunking]\nmax_tokens = 64\noverlap = 64\n")
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "smaller than `max_tokens`" in exc_info.value.message


def test_booleans_are_not_integers(write_manifest: WriteManifest) -> None:
    """`max_tokens = true` must not quietly read as 1."""
    body = minimal(extra="\n[chunking]\nmax_tokens = true\n")
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "must be an integer" in exc_info.value.message


def test_enumerated_values_are_checked(write_manifest: WriteManifest) -> None:
    body = minimal(extra="\n[retrieval]\nrerank = 'sometimes'\n")
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "must be one of" in exc_info.value.message


def test_source_roots_stay_inside_the_kb(write_manifest: WriteManifest) -> None:
    for bad in ("/etc", "../elsewhere"):
        body = MINIMAL.format(kb_id=mint_kb_id()).replace('roots = ["docs/"]', f"roots = ['{bad}']")
        with pytest.raises(ManifestError) as exc_info:
            load(write_manifest(body))
        assert "must stay inside the KB" in exc_info.value.message


def test_linked_kbs_parse_and_reject_duplicates(write_manifest: WriteManifest) -> None:
    first, second = mint_kb_id(), mint_kb_id()
    body = minimal(
        extra=(
            f"\n[[links.kb]]\nname = 'archive'\nid = '{first}'\npath = '~/kb/archive'\n"
            f"\n[[links.kb]]\nname = 'other'\nid = '{second}'\npath = '~/kb/other'\n"
        )
    )
    manifest = load(write_manifest(body))
    assert [linked.name for linked in manifest.links] == ["archive", "other"]
    assert manifest.linked_kb("archive") is not None
    assert manifest.linked_kb("missing") is None

    duplicate = minimal(
        extra=(
            f"\n[[links.kb]]\nname = 'archive'\nid = '{first}'\npath = 'a'\n"
            f"\n[[links.kb]]\nname = 'archive'\nid = '{second}'\npath = 'b'\n"
        )
    )
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(duplicate))
    assert "duplicate name" in exc_info.value.message


def test_created_must_carry_a_time(write_manifest: WriteManifest) -> None:
    body = minimal(extra="").replace("id   =", "created = '20260725'\nid   =")
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body))
    assert "20260725 09:14" in exc_info.value.message


@pytest.mark.parametrize(
    "body",
    [
        "[kb]\nname = ''\nid = '{kb_id}'\n[sources]\nroots=['docs/']\n"
        "[embedding]\nprovider='p'\nmodel='m'\ndim=1\n",
        "[kb]\nname = 'k'\nid = '{kb_id}'\n[sources]\nroots=['docs/']\n"
        "[embedding]\nprovider='p'\nmodel=''\ndim=1\n",
    ],
)
def test_empty_strings_are_rejected(write_manifest: WriteManifest, body: str) -> None:
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(body.format(kb_id=mint_kb_id())))
    assert "must not be empty" in exc_info.value.message


def test_an_explicit_empty_value_never_becomes_the_default(write_manifest: WriteManifest) -> None:
    """`timezone = ""` is a mistake to report, not a request for UTC."""
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest(minimal(extra="\n[budget]\ntimezone = ''\n")))
    assert "`timezone` must not be empty" in exc_info.value.message


def test_malformed_toml_names_the_file(write_manifest: WriteManifest) -> None:
    with pytest.raises(ManifestError) as exc_info:
        load(write_manifest("[kb\nname = "))
    assert "is not valid TOML" in exc_info.value.message


def test_missing_manifest_reports_the_path(tmp_path: Path) -> None:
    with pytest.raises(ManifestError) as exc_info:
        load(tmp_path)
    assert "cannot be read" in exc_info.value.message


def test_find_kb_root_walks_up(kb_root: Path) -> None:
    nested = kb_root / "docs" / "deep" / "deeper"
    nested.mkdir(parents=True)
    assert find_kb_root(nested) == kb_root.resolve()
    assert find_kb_root(kb_root) == kb_root.resolve()
    assert discover(nested).kb.name == "research"


def test_find_kb_root_stops_with_a_remedy(tmp_path: Path) -> None:
    with pytest.raises(NoKbFoundError) as exc_info:
        find_kb_root(tmp_path)
    assert "pnk init" in exc_info.value.remedy


def test_adjacent_k_defaults_to_eight(write_manifest: Callable[[str], Path]) -> None:
    """New behaviour ships with its test. The default was asserted only in prose."""
    from pinakes.graph.traverse import DEFAULT_ADJACENT_K

    assert load(write_manifest(minimal())).retrieval.adjacent_k == DEFAULT_ADJACENT_K


def test_adjacent_k_above_the_server_cap_is_refused_not_clamped(
    write_manifest: Callable[[str], Path],
) -> None:
    """Answering 64 to a request for 10,000 while saying nothing leaves the author believing
    something untrue — which is the whole argument for refusing at parse time, and it was made in
    a commit message rather than in a test."""
    from pinakes.errors import ManifestError
    from pinakes.graph.traverse import MAX_ADJACENT_K

    body = minimal(retrieval="\n[retrieval]\nadjacent_k = 10000\n")
    with pytest.raises(ManifestError) as caught:
        load(write_manifest(body))
    assert str(MAX_ADJACENT_K) in caught.value.message
