"""The completeness audit: what it measures, what it refuses to measure, and what it never does."""

import pytest

from pinakes.extract import ExtractedText
from pinakes.extract.audit import audit_completeness

FLOOR = 65.75  # I3b's fitted text-yield floor, in non-whitespace characters per page


def document(*pages: str) -> ExtractedText:
    """Pages joined the way both backends join them: a newline before each non-empty page after
    the first, counted inside that page's own span."""
    parts: list[str] = []
    position = 0
    spans: list[tuple[int, int]] = []
    for page in pages:
        start = position
        if page:
            if parts:
                parts.append("\n")
                position += 1
            parts.append(page)
            position += len(page)
        spans.append((start, position))
    return ExtractedText(text="".join(parts), page_spans=tuple(spans))


def prose(seed: str, words: int = 40) -> str:
    """Enough *distinct* words to clear the yield floor and give `word_coverage` a denominator.

    Distinct alphabetically, not by digit: `word_coverage` tokenises on `[a-zA-Z]+`, so
    `f"{seed}{index}"` would collapse forty words into one and every page would score 1.00 —
    a fixture that cannot fail whatever the code does.
    """
    built = [f"{seed}{chr(97 + index // 26)}{chr(97 + index % 26)}" for index in range(words)]
    # `_significant_words` keeps only words of four characters or more, so a short seed produces
    # a page with a coverage *denominator of zero* — unmeasurable, not perfect. Asserted here
    # rather than left to the caller: a fixture that silently stops being measurable is the exact
    # failure this file already hit twice.
    assert all(len(word) >= 4 for word in built), f"seed {seed!r} is too short to be measurable"
    return " ".join(built)


def test_a_faithful_extraction_scores_full_coverage() -> None:
    native = document(prose("alpha"), prose("beta"))
    report = audit_completeness(native, native, text_yield_floor=FLOOR)
    assert len(report.audited) == 2
    assert report.exempt == ()
    assert all(page.coverage == 1.0 for page in report.audited)
    assert report.below_median == (), "a document that scores identically everywhere has no outlier"


def test_a_page_that_dropped_content_is_reported_below_median() -> None:
    """The only failure this audit exists to find: one page quietly missing what the free layer
    already had, in a document whose other pages are fine."""
    native = document(prose("alpha"), prose("beta"), prose("gamma"))
    paid = document(prose("alpha"), "beta0 beta1 beta2", prose("gamma"))

    report = audit_completeness(paid, native, text_yield_floor=FLOOR)
    assert len(report.audited) == 3
    (outlier,) = report.below_median
    assert outlier.page == 2
    assert outlier.coverage is not None and outlier.coverage < 0.2
    assert report.low_coverage_paths("docs/report.pdf") == ("docs/report.pdf:2",)


def test_a_page_with_no_native_layer_is_exempt_not_zero() -> None:
    """A scanned page has nothing to compare against. Scoring it 0 would make the exact case the
    paid path exists for look like its worst failure — and would drag the median down with it,
    flagging the *healthy* pages as outliers."""
    native = document(prose("alpha"), "", prose("gamma"))
    paid = document(prose("alpha"), prose("recovered"), prose("gamma"))

    report = audit_completeness(paid, native, text_yield_floor=FLOOR)
    assert [page.page for page in report.exempt] == [2]
    assert report.exempt[0].coverage is None
    assert len(report.audited) == 2
    assert report.below_median == ()


def test_the_summary_always_carries_its_denominators() -> None:
    """`audited N of M` is a fact; `N pages audited` is a number with nothing to judge it by."""
    native = document(prose("alpha"), "", prose("gamma"))
    report = audit_completeness(native, native, text_yield_floor=FLOOR)
    line = report.line()
    assert "audited 2 of 3" in line
    assert "exempt 1 of 3" in line
    assert "below-median 0" in line


def test_an_all_exempt_document_reports_no_median_rather_than_zero() -> None:
    """Every page scanned: there is no measurement at all, which is not the same as a median of 0
    — and a `0.00` printed here would read as "this extraction recovered nothing"."""
    native = document("", "")
    paid = document(prose("recovered"), prose("more"))

    report = audit_completeness(paid, native, text_yield_floor=FLOOR)
    assert report.median_coverage is None
    assert report.below_median == ()
    assert "audited 0 of 2" in report.line()
    assert "median coverage" not in report.line(), "no measurement is not a median of 0.00"


def test_a_page_count_mismatch_refuses_rather_than_zipping_to_the_shorter() -> None:
    """Comparing positionally after a mismatch scores each page against a *different* page, which
    is worse than not auditing: it manufactures outliers that are really an off-by-one."""
    with pytest.raises(ValueError) as exc_info:
        audit_completeness(
            document(prose("alpha"), prose("bravo")),
            document(prose("alpha"), prose("bravo"), prose("delta")),
            text_yield_floor=FLOOR,
        )
    assert "against a different page" in str(exc_info.value)


def test_below_median_is_strict_so_a_uniform_document_flags_nothing() -> None:
    """Non-strict, half of every document is 'below median' by construction — including a
    perfect one."""
    native = document(prose("alpha"), prose("bravo"), prose("delta"), prose("gamma"))
    report = audit_completeness(native, native, text_yield_floor=FLOOR)
    assert report.median_coverage == 1.0
    assert report.below_median == ()


def test_a_page_with_no_significant_words_is_exempt_not_perfect() -> None:
    """A page of figures clears the yield floor and still gives `word_coverage` nothing to look
    for. Scoring it 1.00 claims full preservation of something never checked — and drags the
    median *up*, making the genuine outliers look less unusual than they are."""
    figures = "1234 5678 90.12 3.14159 " * 12
    native = document(figures, prose("beta"), prose("gamma"))
    paid = document(figures, prose("beta"), prose("gamma"))

    report = audit_completeness(paid, native, text_yield_floor=FLOOR)
    assert [page.page for page in report.exempt] == [1]
    assert report.exempt[0].coverage is None
    assert len(report.audited) == 2
