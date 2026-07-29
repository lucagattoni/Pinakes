"""The free per-page yield measurement, and the two consumers that must agree about it.

These cases lived in `test_extract_claude.py` while the code lived in `extract/claude.py`. Moving
them here is not tidying: `pnk doctor` now consumes the same measurement, and a free command may
not import the one module in `src/` allowed to import `anthropic` merely to ask how much text
pypdfium2 got out of a page. Nothing in this file touches the paid path.
"""

from pathlib import Path
from typing import Any

import pytest
from conftest import pdf_extraction_runnable

from pinakes.errors import ExtractionError, FloorsMissingError
from pinakes.extract import ExtractedText
from pinakes.extract import pageyield as pageyield_module
from pinakes.extract.pageyield import (
    SCANNED_PAGE_FRACTION,
    check_worth_paying_for,
    measure,
    survey_free_yield,
)

CORPUS = Path(__file__).parent / "pdf-corpus"


def _text(pages: list[str]) -> ExtractedText:
    """An `ExtractedText` whose page spans really do partition its text, so a measurement taken
    from it is a measurement of the pages it claims to have."""
    body = ""
    spans: list[tuple[int, int]] = []
    for page in pages:
        start = len(body)
        body += page
        spans.append((start, len(body)))
    return ExtractedText(text=body, page_spans=tuple(spans))


# --- the measurement itself, over text the caller already has ---------------------------------


def test_measure_flags_the_empty_pages_and_names_them() -> None:
    extracted = _text(["plenty of text here", "   \n  ", "more text", ""])
    survey = measure(extracted, floor=5.0)

    assert survey.pages_total == 4
    assert survey.below == (2, 4), "1-indexed, matching how a page is cited"
    assert survey.pages_below_floor == 2


def test_the_yield_counts_non_whitespace_characters_per_page() -> None:
    survey = measure(_text(["ab cd", "  \n\t "]), floor=1.0)
    assert survey.chars_per_page == (4, 0)


def test_a_page_exactly_on_the_floor_is_not_below_it() -> None:
    """`< floor`, never `<=`: the fitted value is the midpoint between the highest scanned yield
    and the lowest real one, so a page sitting exactly on it is on the healthy side by
    construction. A flipped comparison would flag a healthy page and invite a paid re-extraction
    of it."""
    survey = measure(_text(["abcde"]), floor=5.0)
    assert survey.below == ()


def test_the_decision_is_per_document_even_though_the_floor_is_per_page() -> None:
    """A 200-page report with eight scanned inserts: a healthy median, and it still needs the paid
    path. That is the whole reason the fraction exists rather than a median."""
    survey = measure(_text(["text"] * 192 + [""] * 8), floor=1.0)

    assert survey.pages_below_floor == 8
    assert survey.scanned_fraction == pytest.approx(0.04)
    assert not survey.needs_the_paid_path, "4% is below the 10% fraction"

    worse = measure(_text(["text"] * 180 + [""] * 20), floor=1.0)
    assert worse.scanned_fraction == pytest.approx(0.10)
    assert worse.needs_the_paid_path, f"exactly {SCANNED_PAGE_FRACTION:.0%} must qualify"


def test_a_document_with_no_pages_has_no_scanned_fraction_rather_than_a_zero_division() -> None:
    survey = measure(_text([]), floor=1.0)
    assert survey.pages_total == 0
    assert survey.scanned_fraction == 0.0


# --- the paid path's pre-check, which spends nothing ------------------------------------------


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_the_free_path_refuses_to_pay_for_a_healthy_pdf() -> None:
    """Paying to re-extract a PDF that already has a good text layer is the most likely way a user
    loses money by accident."""
    with pytest.raises(ExtractionError) as exc_info:
        check_worth_paying_for(CORPUS / "baseline-12p.pdf", force=False)
    assert "already reads" in exc_info.value.message
    assert "--force" in exc_info.value.remedy


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_force_is_what_overrides_the_healthy_pdf_refusal() -> None:
    survey = check_worth_paying_for(CORPUS / "baseline-12p.pdf", force=True)
    assert survey.pages_total == 12
    assert not survey.needs_the_paid_path


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_scanned_pdf_is_what_the_pre_check_lets_through() -> None:
    """The negative control's positive twin: if no real document ever qualified, the refusal above
    would pass on a check that refuses everything."""
    survey = check_worth_paying_for(CORPUS / "scanned-clean.pdf", force=False)
    assert survey.needs_the_paid_path
    assert survey.pages_below_floor == survey.pages_total


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_with_no_fitted_floor_the_paid_path_refuses_to_spend_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A paid path running with its own cost-control check disabled is worse than one that does
    not run: the check exists to stop the most likely accidental spend, so its absence is a
    refusal, never a shrug."""

    def no_floors() -> Any:
        raise FloorsMissingError(reason="floors.toml is missing")

    monkeypatch.setattr(pageyield_module, "load_floors", no_floors)
    with pytest.raises(FloorsMissingError):
        check_worth_paying_for(CORPUS / "baseline-12p.pdf", force=False)
    # `--force` must not buy a way past a *missing guard*, only past a healthy-PDF refusal.
    with pytest.raises(FloorsMissingError):
        check_worth_paying_for(CORPUS / "baseline-12p.pdf", force=True)


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_the_survey_keeps_the_extraction_it_measured() -> None:
    """The completeness audit's ground truth is this same extraction; running the free backend a
    second time to recover it would double the cost of the step that is supposed to be free."""
    survey = survey_free_yield(CORPUS / "baseline-12p.pdf")
    assert survey.native is not None
    assert len(survey.native.page_spans) == survey.pages_total
