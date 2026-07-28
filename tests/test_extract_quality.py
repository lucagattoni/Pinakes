"""`extract/quality.py`'s five metrics on hand-built strings, then the corpus-level gate.

Every metric is checked against a hand-computed answer first (rule 3's own point: a metric that
cannot be wrong on a known input is not fit to gate anything) — only `TestCorpusGate` below touches
`tests/pdf-corpus/` or pdfium at all.
"""

import importlib.resources
import tomllib
from pathlib import Path

import pytest
from conftest import pdf_extraction_runnable

from pinakes.extract.quality import (
    EXEMPTIONS,
    Rate,
    char_recall,
    check_floor_drift,
    compare_to_baseline,
    fit_running_head_threshold,
    fit_text_yield_floor,
    junk_rate,
    order_fidelity,
    pair_adjacency,
    score_corpus,
    word_coverage,
    write_baseline,
)

CORPUS_DIR = Path(__file__).parent / "pdf-corpus"


def test_rate_value_is_none_not_zero_when_denominator_is_zero() -> None:
    """Rule 3: v0.1's `false_abstain: 0.0` was vacuous. A `Rate` with nothing to measure must be
    told apart from a `Rate` that measured a real zero."""
    assert Rate(numerator=0, denominator=0).value is None
    assert Rate(numerator=0, denominator=5).value == 0.0


def test_char_recall_all_characters_found_in_order() -> None:
    rate = char_recall("axbxc", "abc")
    assert (rate.numerator, rate.denominator) == (3, 3)
    assert rate.value == 1.0


def test_char_recall_out_of_order_characters_do_not_all_count() -> None:
    """LCS("abc", "cab") = "ab" (length 2): 'c' precedes 'a' in the extraction, so no subsequence
    using both 'c' and something after it in the expected order exists."""
    rate = char_recall("cab", "abc")
    assert (rate.numerator, rate.denominator) == (2, 3)


def test_char_recall_ignores_whitespace() -> None:
    rate = char_recall("a b c", "abc")
    assert (rate.numerator, rate.denominator) == (3, 3)


def test_order_fidelity_words_in_order_with_junk_between() -> None:
    rate = order_fidelity("the quick XYZ brown fox", "the quick brown fox")
    assert (rate.numerator, rate.denominator) == (4, 4)


def test_order_fidelity_reordered_words_do_not_all_count() -> None:
    rate = order_fidelity("brown quick the fox", "the quick brown fox")
    # LCS over words: "the quick brown fox" vs "brown quick the fox" -- longest common subsequence
    # is "quick fox" (length 2): quick(idx1) before fox(idx3) in both orderings.
    assert rate.numerator == 2
    assert rate.denominator == 4


def test_junk_rate_counts_extracted_words_absent_from_expected() -> None:
    rate = junk_rate("the cat sat on xyz", "the cat sat on the mat")
    assert (rate.numerator, rate.denominator) == (1, 5)


def test_junk_rate_zero_when_every_extracted_word_is_expected() -> None:
    rate = junk_rate("the cat sat", "the cat sat on the mat")
    assert rate.numerator == 0


def test_pair_adjacency_within_window_counts_as_matched() -> None:
    rate = pair_adjacency("Year 2019 Acquisitions 142", [("2019", "142")], window=80)
    assert (rate.numerator, rate.denominator) == (1, 1)


def test_pair_adjacency_beyond_window_does_not_count() -> None:
    text = "2019" + (" filler" * 20) + " 142"
    rate = pair_adjacency(text, [("2019", "142")], window=80)
    assert rate.numerator == 0
    assert rate.denominator == 1


def test_pair_adjacency_missing_label_or_value_does_not_count() -> None:
    rate = pair_adjacency("nothing relevant here", [("2019", "142")])
    assert rate.numerator == 0


def test_word_coverage_significant_words_present() -> None:
    rate = word_coverage("archive catalogue records acquisitions", "archive catalogue records")
    assert (rate.numerator, rate.denominator) == (3, 3)


def test_word_coverage_missing_significant_word_is_not_covered() -> None:
    rate = word_coverage("archive records", "archive catalogue records")
    assert rate.numerator == 2
    assert rate.denominator == 3


def test_word_coverage_short_and_stopword_tokens_are_not_significant() -> None:
    """ "the" and "a" (stopwords) and "in"/"of" (under 4 characters) never enter the denominator —
    only "catalogue" does."""
    rate = word_coverage("something else entirely", "the a in of catalogue")
    assert rate.denominator == 1


def test_compare_to_baseline_flags_a_regression_beyond_tolerance() -> None:
    from pinakes.extract.quality import CorpusReport, StratumReport

    report = CorpusReport(
        documents=(),
        strata={"two-column": StratumReport(1, 1, 2, 2, {"char_recall": Rate(50, 100)})},
    )
    baseline = {"strata": {"two-column": {"char_recall": 0.9}}}
    regressions = compare_to_baseline(report, baseline, tolerance=0.02)
    assert len(regressions) == 1
    assert "char_recall" in regressions[0]


def test_compare_to_baseline_within_tolerance_is_not_a_regression() -> None:
    from pinakes.extract.quality import CorpusReport, StratumReport

    report = CorpusReport(
        documents=(),
        strata={"two-column": StratumReport(1, 1, 2, 2, {"char_recall": Rate(989, 1000)})},
    )
    baseline = {"strata": {"two-column": {"char_recall": 0.99}}}
    assert compare_to_baseline(report, baseline, tolerance=0.02) == []


def test_compare_to_baseline_flags_a_changed_exemption_as_a_structural_regression() -> None:
    from pinakes.extract.quality import CorpusReport, StratumReport

    report = CorpusReport(
        documents=(),
        strata={"scanned": StratumReport(1, 1, 1, 1, {"junk_rate": Rate(3, 10)})},
    )
    baseline = {"strata": {"scanned": {"junk_rate": None}}}
    regressions = compare_to_baseline(report, baseline)
    assert len(regressions) == 1
    assert "exemption changed" in regressions[0]


class TestCorpusGate:
    """Everything below actually extracts `tests/pdf-corpus/` — skipped without `pinakes[pdf]`."""

    pytestmark = pytest.mark.skipif(
        not pdf_extraction_runnable(), reason="pinakes[pdf] not installed"
    )

    def test_documents_scored_equals_total_for_every_non_exempt_stratum(self) -> None:
        report = score_corpus(CORPUS_DIR)
        for name, stratum in report.strata.items():
            if name == "pathological":  # the corrupt-header fixture can never be opened, by design
                assert stratum.documents_scored == stratum.documents_total - 1
                continue
            assert stratum.documents_scored == stratum.documents_total, name

    def test_write_baseline_declares_every_actual_exemption_with_a_reason(
        self, tmp_path: Path
    ) -> None:
        report = score_corpus(CORPUS_DIR)
        out = tmp_path / "baseline.json"
        write_baseline(out, report)  # raises ValueError itself if EXEMPTIONS drifted from reality
        for by_stratum in EXEMPTIONS.values():
            for reason in by_stratum.values():
                assert reason  # every declared exemption carries a non-empty reason string

    def test_a_planted_truncation_regression_fails_the_baseline_comparison(
        self, tmp_path: Path
    ) -> None:
        """One fixture's extraction truncated to its first page must move its stratum's
        `char_recall` (and likely `order_fidelity`) down enough to fail the comparison — proving
        the gate actually catches a regression, not only that it passes when nothing changed."""
        from pinakes.extract.quality import score_document

        report = score_corpus(CORPUS_DIR)
        baseline_path = tmp_path / "baseline.json"
        write_baseline(baseline_path, report)

        target = next(d for d in report.documents if d.name == "baseline-12p")
        expected_text = (CORPUS_DIR / "baseline-12p.expected.txt").read_text()
        truncated_extraction = expected_text[: len(expected_text) // 12]  # roughly one of 12 pages
        truncated = score_document(
            name=target.name,
            stratum=target.stratum,
            pages=target.pages,
            extracted=truncated_extraction,
            expected=expected_text,
        )
        documents = tuple(truncated if d.name == target.name else d for d in report.documents)
        from pinakes.extract.quality import aggregate

        regressed_report = report.__class__(documents=documents, strata=aggregate(documents))

        import json

        regressions = compare_to_baseline(regressed_report, json.loads(baseline_path.read_text()))
        assert regressions, "a fixture truncated to ~1/12 of its text must fail the comparison"

    def test_fit_running_head_threshold_matches_the_committed_floor(self) -> None:
        from pinakes.extract.floors import load_floors

        committed = load_floors()
        threshold, reason = fit_running_head_threshold(CORPUS_DIR)
        assert abs(threshold - committed.running_head_threshold) < 1e-6
        assert reason  # the fit states its own justification, not only its number

    def test_fit_text_yield_floor_matches_the_committed_floor(self) -> None:
        from pinakes.extract.floors import load_floors

        committed = load_floors()
        report = score_corpus(CORPUS_DIR)
        floor, reason = fit_text_yield_floor(report)
        assert abs(floor - committed.text_yield_floor) < 1e-6
        assert reason

    def test_a_drifted_floor_fails_the_gate(self, tmp_path: Path) -> None:
        report = score_corpus(CORPUS_DIR)
        drifted = tmp_path / "floors.toml"
        drifted.write_text(
            'running_head_threshold = 0.0\ntext_yield_floor = 100000.0\nfitted_on = "test"\n',
            encoding="utf-8",
        )
        drift = check_floor_drift(CORPUS_DIR, drifted, report)
        assert len(drift) == 2  # both floors were deliberately moved far outside tolerance


def test_floors_toml_is_installed_package_data() -> None:
    """Read through `importlib.resources`, the way an installed copy — not this repo checkout —
    would: a file only present in the source tree is invisible to every installed wheel."""
    text = (
        importlib.resources.files("pinakes.extract")
        .joinpath("floors.toml")
        .read_text(encoding="utf-8")
    )
    data = tomllib.loads(text)
    assert isinstance(data["running_head_threshold"], float)
    assert 0.0 < data["running_head_threshold"] < 1.0
    assert isinstance(data["text_yield_floor"], float)
    assert data["text_yield_floor"] > 0.0
    assert isinstance(data["fitted_on"], str) and data["fitted_on"]
