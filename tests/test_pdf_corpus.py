"""`tests/pdf-corpus/`: the corpus regenerates byte-identically (text-layer) or within tolerance
(scanned), cannot silently shrink or balloon, and every fixture is paired with its ground truth.

Not tested here, by design: any claim about extraction quality — nothing extracts a PDF yet
(I3a/I3b). This file only proves the corpus itself is what the plan says it is.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from conftest import pdf_runnable

CORPUS_DIR = Path(__file__).parent / "pdf-corpus"
GENERATOR = CORPUS_DIR / "generate.py"

# The plan's own stratum table (plans/v0.2.md, I2) — hardcoded independently of `spec.py`, so a
# drift between the two is caught rather than both silently agreeing on a wrong number.
PLAN_STRATA: dict[str, tuple[int, int]] = {  # stratum -> (fixture_count, total_pages)
    "two-column": (3, 6),
    "tables": (3, 6),
    "headers-footers": (3, 16),
    "ligatures-hyphenation": (3, 6),
    "scanned": (3, 10),
    "pathological": (2, 2),
    "baseline": (2, 13),
}
TOTAL_FIXTURES = 19
TOTAL_PAGES = 59
NAMED_PAID_TWINS = {
    "two-column-a",
    "tables-bordered",
    "headers-repeating",
    "ligatures-a",
    "baseline-12p",
}
TOTAL_BUDGET_BYTES = 2 * 1024 * 1024
SCANNED_BUDGET_BYTES = int(1.5 * 1024 * 1024)

# The scanned stratum's own raster resolution (`generate.py` renders at 150 dpi). The tolerance
# comparison must render at the same scale — see `test_scanned_regeneration_within_tolerance`.
RENDER_SCALE = 150 / 72
MAX_CHANGED_PIXELS = 300


def _load_module(path: Path, name: str) -> ModuleType:
    """`tests/pdf-corpus/` has a hyphen, so it cannot be a dotted-import package — load by path."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spec_module() -> ModuleType:
    return _load_module(CORPUS_DIR / "spec.py", "pdf_corpus_spec")


def _regenerate(out_dir: Path, *, skip_scanned: bool = False) -> None:
    """Explicitly pinned, on top of the inherited environment — never rely on the generator's own
    fallback alone (ground rules): a future edit to that fallback should not silently make this
    test's own determinism claim depend on it."""
    command = [sys.executable, str(GENERATOR), "--out-dir", str(out_dir)]
    if skip_scanned:
        command.append("--skip-scanned")
    subprocess.run(command, check=True, env={**os.environ, "SOURCE_DATE_EPOCH": "1785181219"})


def test_stratum_counts_and_page_counts_match_the_plan() -> None:
    """The corpus cannot silently shrink or balloon — every number here traces to the plan."""
    fixtures = _spec_module().FIXTURES
    assert len(fixtures) == TOTAL_FIXTURES
    assert sum(f.pages for f in fixtures) == TOTAL_PAGES

    by_stratum: dict[str, list[int]] = {}
    for fixture in fixtures:
        by_stratum.setdefault(fixture.stratum, []).append(fixture.pages)

    assert set(by_stratum) == set(PLAN_STRATA)
    for stratum, (expected_count, expected_pages) in PLAN_STRATA.items():
        pages = by_stratum[stratum]
        assert len(pages) == expected_count, (
            f"{stratum}: {len(pages)} fixtures, want {expected_count}"
        )
        assert sum(pages) == expected_pages, f"{stratum}: {sum(pages)} pages, want {expected_pages}"


def test_named_paid_twins_exist() -> None:
    """I7b's human-gated measurement cannot reference a fixture nobody committed."""
    fixtures = _spec_module().FIXTURES
    twins = {f.name for f in fixtures if f.paid_twin}
    assert twins == NAMED_PAID_TWINS
    assert len(twins) == 5
    for name in twins:
        assert (CORPUS_DIR / f"{name}.pdf").is_file()


def test_every_fixture_has_ground_truth_and_every_ground_truth_a_fixture() -> None:
    fixtures = _spec_module().FIXTURES
    pdf_names = {p.stem for p in CORPUS_DIR.glob("*.pdf")}
    expected_names = {p.name[: -len(".expected.txt")] for p in CORPUS_DIR.glob("*.expected.txt")}
    spec_names = {f.name for f in fixtures}

    assert pdf_names == spec_names, pdf_names.symmetric_difference(spec_names)
    assert expected_names == spec_names, expected_names.symmetric_difference(spec_names)


def test_byte_budget() -> None:
    fixtures = _spec_module().FIXTURES
    total = sum((CORPUS_DIR / f"{f.name}.pdf").stat().st_size for f in fixtures)
    scanned_total = sum(
        (CORPUS_DIR / f"{f.name}.pdf").stat().st_size for f in fixtures if f.scanned
    )
    assert total <= TOTAL_BUDGET_BYTES, f"{total} bytes committed, budget {TOTAL_BUDGET_BYTES}"
    assert scanned_total <= SCANNED_BUDGET_BYTES, (
        f"{scanned_total} scanned bytes, budget {SCANNED_BUDGET_BYTES}"
    )


def test_regeneration_is_reproducible(tmp_path: Path) -> None:
    """The sixteen text-layer fixtures must regenerate byte-identically — the scanned three do
    not (rendering/rasterisation is not byte-stable across pdfium/Pillow versions by design) and
    are checked separately, with a tolerance, by `test_scanned_regeneration_within_tolerance`.

    Deliberately **not** `pdf`-marked: `--skip-scanned` drops the only fixtures needing pypdfium2
    and Pillow, so this gate runs on a `[light]`-only checkout too. The plan asks for the *scanned
    half* to skip with a printed reason, not the whole corpus check.
    """
    fixtures = _spec_module().FIXTURES
    _regenerate(tmp_path, skip_scanned=True)

    mismatches: list[str] = []
    for fixture in fixtures:
        if fixture.scanned:
            continue
        for suffix in (".pdf", ".expected.txt"):
            committed = (CORPUS_DIR / f"{fixture.name}{suffix}").read_bytes()
            regenerated = (tmp_path / f"{fixture.name}{suffix}").read_bytes()
            if committed != regenerated:
                mismatches.append(f"{fixture.name}{suffix}")
    assert not mismatches, f"regeneration drifted for: {', '.join(mismatches)}"


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_runnable(), reason="pinakes[pdf] and/or Pillow not installed")
def test_scanned_regeneration_within_tolerance(tmp_path: Path) -> None:
    """No text layer, matching page count and geometry, and at most 300 pixels differing by more
    than 32 levels — an absolute count, not a whole-page mean.

    **The comparison must run at the fixtures' own resolution or the threshold means nothing**, and
    the arithmetic below is measured rather than estimated, because an earlier version of it was
    wrong in both its page format and its dpi and nobody could tell from a green gate.

    The fixtures are US Letter (612 x 792 pt — `PAGE_W`/`PAGE_H` in `generate.py`, never A4)
    rastered at 150 dpi, so a page measures 1275 x 1651 = 2,105,025 px and 300 px is 0.014% of it.
    Measured on `baseline-12p`'s ninth page: shifting the whole page by 3 px changes **33,451**
    pixels by more than 32 levels, ~111x the threshold, so a single moved word — a small fraction
    of a page — still clears it comfortably. The gate is deliberately deaf below 32 levels: a
    contrast change from 0.35 to 0.45 moves *zero* pixels past that bar, which is the intended
    noise floor, while 0.35 to 0.5 trips it at 12,762 px.

    `scale=RENDER_SCALE`, never `scale=1.0`: pdfium's default renders 1 px per *point*, i.e. 72 dpi,
    downsampling the stored 150 dpi image ~2x before comparing. That shrinks the page to 485,316 px
    and a moved word's delta to well under 300 — so the gate would have passed exactly the change it
    exists to catch, while claiming a 2x margin. (A whole-page *mean* tolerance of 2/255 fails the
    same way for the same reason, which is why this is an absolute count.)
    """
    import numpy as np
    import pypdfium2 as pdfium

    fixtures = [f for f in _spec_module().FIXTURES if f.scanned]
    _regenerate(tmp_path)

    for fixture in fixtures:
        committed_doc = pdfium.PdfDocument(str(CORPUS_DIR / f"{fixture.name}.pdf"))
        fresh_doc = pdfium.PdfDocument(str(tmp_path / f"{fixture.name}.pdf"))
        try:
            assert len(committed_doc) == fixture.pages
            assert len(fresh_doc) == len(committed_doc)
            for committed_page, fresh_page in zip(committed_doc, fresh_doc, strict=True):
                assert committed_page.get_textpage().get_text_range() == ""
                committed_size = committed_page.get_size()
                assert fresh_page.get_size() == pytest.approx(committed_size, rel=0.01)

                committed_arr = np.asarray(
                    committed_page.render(scale=RENDER_SCALE).to_pil().convert("L")
                )
                fresh_arr = np.asarray(fresh_page.render(scale=RENDER_SCALE).to_pil().convert("L"))
                assert committed_arr.shape == fresh_arr.shape
                diff = np.abs(committed_arr.astype(int) - fresh_arr.astype(int))
                changed = int(np.count_nonzero(diff > 32))
                assert changed <= MAX_CHANGED_PIXELS, (
                    f"{fixture.name}: {changed} pixels differ by >32 levels"
                )
        finally:
            committed_doc.close()
            fresh_doc.close()


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_runnable(), reason="pinakes[pdf] and/or Pillow not installed")
def test_corrupt_header_fixture_fails_closed() -> None:
    """The pathological corrupt-header fixture must not be openable — that is its whole purpose."""
    import pypdfium2 as pdfium

    with pytest.raises(pdfium.PdfiumError):
        pdfium.PdfDocument(str(CORPUS_DIR / "pathological-corrupt-header.pdf"))
