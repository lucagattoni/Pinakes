#!/usr/bin/env python3
"""Regenerate every `tests/pdf-corpus/` fixture, deterministically.

    python tests/pdf-corpus/generate.py [--out-dir DIR]

With no `--out-dir`, writes over the committed fixtures in place (what `make corpus` does).
`tests/test_pdf_corpus.py` instead points `--out-dir` at a scratch directory and diffs the result
against the committed copies, so a byte-for-byte drift is caught rather than silently re-committed.

Ground truth is authored here, from each fixture's *spec* (what was placed and where) — never by
running an extractor over the generated PDF and copying its output. That would only prove an
extractor agrees with itself (ground rules, rule 5; `docs/RETROSPECTIVES.md`, I2).
"""

from __future__ import annotations

import argparse
import os
import textwrap
from pathlib import Path

from pdfwriter import Font, Page, Rect, TextRun, write_image_pdf, write_text_pdf
from spec import FIXTURES

DEFAULT_EPOCH = 1785181219
FONT_NAME = "F1"
PAGE_W = 612.0
PAGE_H = 792.0
MARGIN = 72.0
BODY_SIZE = 11.0
LINE_HEIGHT = 15.0
COLUMN_W = 204.0
COLUMN_GAP = 36.0
LEFT_X = MARGIN
RIGHT_X = MARGIN + COLUMN_W + COLUMN_GAP


def epoch() -> int:
    return int(os.environ.get("SOURCE_DATE_EPOCH", str(DEFAULT_EPOCH)))


def wrap(text: str, width_chars: int) -> list[str]:
    """Word-wrap only — `textwrap` knows nothing about PDF or fonts, so it decides nothing about
    the variable under test (reading order, table geometry, hyphenation placement); it just turns
    one long string into lines whose *content* this module still fully authors and knows.

    `break_on_hyphens=False` is load-bearing, not tidiness. Left at its default, `textwrap` splits
    an existing compound word across lines ("spine-" / "out"), and the ground truth — which joins
    lines with a single space — then reads "spine- out": a phantom space no correct extractor could
    ever produce, in a corpus whose only job is trustworthy ground truth. Hyphenation is exercised
    deliberately, by fixtures that place the hyphen themselves; it must never arrive by accident.
    """
    return textwrap.wrap(text, width=width_chars, break_long_words=False, break_on_hyphens=False)


def column_of_lines(lines: list[str], *, x: float, top: float, size: float = BODY_SIZE) -> Page:
    runs = tuple(
        TextRun(font=FONT_NAME, size=size, x=x, y=top - i * LINE_HEIGHT, text=line.encode("ascii"))
        for i, line in enumerate(lines)
    )
    return Page(runs=runs)


# --------------------------------------------------------------------------------------------
# Content bank — generic, invented, "library/archive" themed prose. Never harvested (CLAUDE.md).
# --------------------------------------------------------------------------------------------

SENTENCES = [
    "The archive catalogue records every acquisition by year, subject and provenance.",
    "A reading room clerk cross-references each request against the shelf index before release.",
    "Bound volumes are stored spine-out, sorted first by collection and then by accession number.",
    "Restoration work proceeds slowly, one folio at a time, under controlled humidity.",
    "The survey found that most requests concern maps rather than correspondence.",
    "Digitisation teams photograph each page twice, once in colour and once under raking light.",
    "A duplicate catalogue is kept off-site in case the reading room copy is ever damaged.",
    "Visiting scholars must register with the desk before any box leaves the stacks.",
    "The oldest ledger in the collection predates the building that now houses it.",
    "Conservation staff replace acidic folders with archival board on a rolling schedule.",
    "Every transfer between departments is logged, however small the parcel.",
    "The index cards were retired only after the electronic catalogue proved reliable.",
    "Loan requests from other institutions are reviewed by a standing committee each quarter.",
    "A single misfiled ledger can take a researcher an entire afternoon to locate again.",
    "The reading room closes an hour before the rest of the building, for a final sweep.",
]


def prose(n_sentences: int, *, start: int = 0) -> str:
    picked = [SENTENCES[(start + i) % len(SENTENCES)] for i in range(n_sentences)]
    return " ".join(picked)


# --------------------------------------------------------------------------------------------
# baseline
# --------------------------------------------------------------------------------------------


def build_baseline_1p() -> tuple[list[Page], str]:
    text = prose(6)
    lines = wrap(text, 68)
    page = column_of_lines(lines, x=MARGIN, top=PAGE_H - MARGIN)
    expected = " ".join(lines) + "\n"
    return [page], expected


def build_baseline_12p() -> tuple[list[Page], str]:
    pages: list[Page] = []
    expected_pages: list[str] = []
    for i in range(12):
        text = prose(5, start=i * 3)
        lines = wrap(text, 68)
        pages.append(column_of_lines(lines, x=MARGIN, top=PAGE_H - MARGIN))
        expected_pages.append(" ".join(lines))
    return pages, "\n".join(expected_pages) + "\n"


# --------------------------------------------------------------------------------------------
# two-column
# --------------------------------------------------------------------------------------------


def _two_column_page(left_text: str, right_text: str, *, width_chars: int = 34) -> Page:
    left_lines = wrap(left_text, width_chars)
    right_lines = wrap(right_text, width_chars)
    left = column_of_lines(left_lines, x=LEFT_X, top=PAGE_H - MARGIN)
    right = column_of_lines(right_lines, x=RIGHT_X, top=PAGE_H - MARGIN)
    return Page(runs=left.runs + right.runs)


def build_two_column_a() -> tuple[list[Page], str]:
    """The gutter reading-order case: left column read in full, then right, on each page."""
    p1_left, p1_right = prose(4, start=0), prose(4, start=4)
    p2_left, p2_right = prose(4, start=8), prose(4, start=12)
    pages = [_two_column_page(p1_left, p1_right), _two_column_page(p2_left, p2_right)]
    expected = f"{p1_left}\n{p1_right}\n{p2_left}\n{p2_right}\n"
    return pages, expected


def build_two_column_b() -> tuple[list[Page], str]:
    """A caption line spanning both columns, sitting between the column text in reading order."""
    left, right = prose(3, start=1), prose(3, start=5)
    caption = "Figure 1. Accession trends across the last decade of the catalogue."
    left_lines = wrap(left, 34)
    right_lines = wrap(right, 34)
    left_page = column_of_lines(left_lines, x=LEFT_X, top=PAGE_H - MARGIN)
    right_page = column_of_lines(right_lines, x=RIGHT_X, top=PAGE_H - MARGIN)
    caption_y = PAGE_H - MARGIN - (max(len(left_lines), len(right_lines)) + 2) * LINE_HEIGHT
    caption_run = TextRun(
        font=FONT_NAME, size=BODY_SIZE, x=LEFT_X, y=caption_y, text=caption.encode("ascii")
    )
    page1 = Page(runs=left_page.runs + right_page.runs + (caption_run,))
    left2, right2 = prose(3, start=9), prose(3, start=12)
    page2 = _two_column_page(left2, right2)
    expected = f"{left}\n{right}\n{caption}\n{left2}\n{right2}\n"
    return [page1, page2], expected


def build_two_column_c() -> tuple[list[Page], str]:
    """The left column's last sentence continues, uninterrupted, at the top of the right column."""
    lead = "The clerk opened the final ledger of the survey and began the last entry of the day"
    tail = "noting the shelf mark before closing the drawer for the evening."
    left_lines = wrap(lead, 34)
    # `tail` is wrapped like every other multi-word line, not placed whole: at 66 characters it
    # overran the right column and spilled ~7pt past the page's own MediaBox — the one line in the
    # corpus that was not validly laid out on its own page.
    right_lines = [*wrap(tail, 34), *wrap(prose(3, start=2), 34)]
    left_page = column_of_lines(left_lines, x=LEFT_X, top=PAGE_H - MARGIN)
    right_page = column_of_lines(right_lines, x=RIGHT_X, top=PAGE_H - MARGIN)
    page1 = Page(runs=left_page.runs + right_page.runs)
    left2, right2 = prose(3, start=6), prose(3, start=9)
    page2 = _two_column_page(left2, right2)
    joined_first_page = f"{lead} {tail}\n{' '.join(wrap(prose(3, start=2), 34))}"
    expected = f"{joined_first_page}\n{left2}\n{right2}\n"
    return [page1, page2], expected


# --------------------------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------------------------

TABLE_HEADERS = ["Year", "Acquisitions", "Department"]
TABLE_ROWS = [
    ["2019", "142", "Manuscripts"],
    ["2020", "88", "Maps"],
    ["2021", "165", "Correspondence"],
    ["2022", "121", "Manuscripts"],
]
TABLE_COL_X = [MARGIN, MARGIN + 100, MARGIN + 220]


def _table_row_runs(row: list[str], y: float) -> tuple[TextRun, ...]:
    return tuple(
        TextRun(font=FONT_NAME, size=BODY_SIZE, x=x, y=y, text=cell.encode("ascii"))
        for x, cell in zip(TABLE_COL_X, row, strict=True)
    )


def _table_page(bordered: bool) -> tuple[Page, str]:
    top = PAGE_H - MARGIN
    row_h = 24.0
    runs: list[TextRun] = list(_table_row_runs(TABLE_HEADERS, top))
    rects: list[Rect] = []
    all_rows = [TABLE_HEADERS, *TABLE_ROWS]
    table_w = 100 + 120 + 120
    table_top = top + 6
    table_bottom = top - row_h * len(TABLE_ROWS) - 6
    if bordered:
        rects.append(Rect(x=MARGIN, y=table_bottom, w=table_w, h=table_top - table_bottom))
        for i in range(1, len(all_rows)):
            y = top - row_h * i + 6
            rects.append(Rect(x=MARGIN, y=y, w=table_w, h=0.01))
        for x in (*TABLE_COL_X[1:], MARGIN + table_w):
            rects.append(Rect(x=x, y=table_bottom, w=0.01, h=table_top - table_bottom))
    for i, row in enumerate(TABLE_ROWS, start=1):
        runs.extend(_table_row_runs(row, top - row_h * i))
    expected = "\n".join(" ".join(row) for row in all_rows)
    return Page(runs=tuple(runs), rects=tuple(rects)), expected


def build_tables_bordered() -> tuple[list[Page], str]:
    p1, e1 = _table_page(bordered=True)
    lines = wrap(prose(4, start=3), 68)
    p2 = column_of_lines(lines, x=MARGIN, top=PAGE_H - MARGIN)
    e2 = " ".join(lines)
    return [p1, p2], f"{e1}\n{e2}\n"


def build_tables_borderless() -> tuple[list[Page], str]:
    p1, e1 = _table_page(bordered=False)
    lines = wrap(prose(4, start=7), 68)
    p2 = column_of_lines(lines, x=MARGIN, top=PAGE_H - MARGIN)
    e2 = " ".join(lines)
    return [p1, p2], f"{e1}\n{e2}\n"


def build_tables_spanning() -> tuple[list[Page], str]:
    top = PAGE_H - MARGIN
    header = "Acquisitions by Department, 2019-2022"
    header_run = TextRun(
        font=FONT_NAME, size=BODY_SIZE, x=MARGIN, y=top, text=header.encode("ascii")
    )
    body_runs = list(_table_row_runs(TABLE_HEADERS, top - 24))
    for i, row in enumerate(TABLE_ROWS, start=1):
        body_runs.extend(_table_row_runs(row, top - 24 - 24 * i))
    p1 = Page(runs=(header_run, *body_runs))
    all_rows = [TABLE_HEADERS, *TABLE_ROWS]
    e1 = header + "\n" + "\n".join(" ".join(row) for row in all_rows)
    lines = wrap(prose(4, start=11), 68)
    p2 = column_of_lines(lines, x=MARGIN, top=PAGE_H - MARGIN)
    e2 = " ".join(lines)
    return [p1, p2], f"{e1}\n{e2}\n"


# --------------------------------------------------------------------------------------------
# headers / footers
# --------------------------------------------------------------------------------------------

RUNNING_HEAD = "PINAKES ARCHIVE REVIEW"


def build_headers_repeating() -> tuple[list[Page], str]:
    pages: list[Page] = []
    expected_pages: list[str] = []
    for i in range(10):
        head_run = TextRun(
            font=FONT_NAME, size=9.0, x=MARGIN, y=PAGE_H - MARGIN + 24, text=RUNNING_HEAD.encode()
        )
        lines = wrap(prose(3, start=i * 2), 68)
        body = column_of_lines(lines, x=MARGIN, top=PAGE_H - MARGIN)
        pages.append(Page(runs=(head_run, *body.runs)))
        expected_pages.append(f"{RUNNING_HEAD}\n{' '.join(lines)}")
    return pages, "\n".join(expected_pages) + "\n"


def build_footers_pagenum() -> tuple[list[Page], str]:
    pages: list[Page] = []
    expected_pages: list[str] = []
    for i in range(3):
        lines = wrap(prose(4, start=i * 2), 68)
        body = column_of_lines(lines, x=MARGIN, top=PAGE_H - MARGIN)
        footer = f"Page {i + 1}"
        footer_run = TextRun(
            font=FONT_NAME, size=9.0, x=PAGE_W / 2 - 12, y=MARGIN - 30, text=footer.encode()
        )
        pages.append(Page(runs=(*body.runs, footer_run)))
        expected_pages.append(f"{' '.join(lines)}\n{footer}")
    return pages, "\n".join(expected_pages) + "\n"


def build_footer_first_page_only() -> tuple[list[Page], str]:
    pages: list[Page] = []
    expected_pages: list[str] = []
    footer = "Confidential draft - internal circulation only"
    for i in range(3):
        lines = wrap(prose(4, start=i * 2 + 1), 68)
        body = column_of_lines(lines, x=MARGIN, top=PAGE_H - MARGIN)
        if i == 0:
            footer_run = TextRun(
                font=FONT_NAME, size=9.0, x=MARGIN, y=MARGIN - 30, text=footer.encode()
            )
            pages.append(Page(runs=(*body.runs, footer_run)))
            expected_pages.append(f"{' '.join(lines)}\n{footer}")
        else:
            pages.append(body)
            expected_pages.append(" ".join(lines))
    return pages, "\n".join(expected_pages) + "\n"


# --------------------------------------------------------------------------------------------
# ligatures & hyphenation
# --------------------------------------------------------------------------------------------

LIGATURE_FONT = Font(name=FONT_NAME, differences={129: "fi", 130: "fl"})
SOFT_HYPHEN_FONT = Font(name=FONT_NAME, to_unicode={0xAD: 0x00AD})


def _ligature_bytes(word_with_marker: str) -> bytes:
    """`^` -> the "fi" glyph (byte 129), `~` -> the "fl" glyph (byte 130)."""
    out = bytearray()
    for ch in word_with_marker:
        if ch == "^":
            out.append(129)
        elif ch == "~":
            out.append(130)
        else:
            out.extend(ch.encode("ascii"))
    return bytes(out)


def build_ligatures_a() -> tuple[list[Page], str]:
    words = ["The archive of^ce", "ordered a waf~e", "for the dif^cult", "shelf-move on Friday."]
    plain = ["office", "waffle", "difficult"]
    y = PAGE_H - MARGIN
    runs: list[TextRun] = []
    for i, marked in enumerate(words):
        runs.append(
            TextRun(
                font=FONT_NAME,
                size=BODY_SIZE,
                x=MARGIN,
                y=y - i * LINE_HEIGHT,
                text=_ligature_bytes(marked),
            )
        )
    page1 = Page(runs=tuple(runs))
    lines2 = wrap(prose(3, start=4), 68)
    page2 = column_of_lines(lines2, x=MARGIN, top=PAGE_H - MARGIN)
    expected1 = "The archive office ordered a waffle for the difficult shelf-move on Friday."
    expected = f"{expected1}\n{' '.join(lines2)}\n"
    assert all(word in expected1 for word in plain)
    return [page1, page2], expected


def build_hyphenation_soft() -> tuple[list[Page], str]:
    """Uses `SOFT_HYPHEN_FONT` (passed in by `build_all`'s `emit`) for the U+00AD ToUnicode map.

    Two pages, the ordinary line-break hyphen at the very end of page 1 and its continuation at the
    very start of page 2 — not two text-showing operations on one shared page, which is what the
    original, single-page version of this fixture did. Verified against pdfium 5.12.1: whenever a
    text-showing operation ending in an ordinary hyphen is *immediately* followed by another one
    starting lowercase on the *same page*, pdfium's own text-extraction reconstruction reports that
    hyphen as U+FFFE instead of U+002D — reproduced across every construction tried in between (one
    shared `BT`/`ET` block, separate blocks, a `Td` or `T*` between the two `Tj` calls) before
    finding the one pattern that never triggers it: the identical hyphen-then-lowercase shape split
    across a *page* boundary, exactly what `build_hyphenation_page_break` already does safely a few
    fixtures below (docs/RETROSPECTIVES.md, I3b). The soft hyphen inside "archive[U+00AD]al"
    was never affected — it sits mid-run, inside one continuous `Tj` string, never at a text-object
    boundary — so only where the *ordinary* hyphen falls needed to move.
    """
    page1 = Page(
        runs=(
            TextRun(
                font=FONT_NAME,
                size=BODY_SIZE,
                x=MARGIN,
                y=PAGE_H - MARGIN,
                text=b"The clerk filed the coopera-",
            ),
        )
    )
    # "archiv" + U+00AD + "al", not "archive" + U+00AD + "al" — dropping the soft hyphen must spell
    # "archival", and "archive" + "al" spells "archiveal" (I3b: this typo predates the fix that
    # finally made the soft hyphen's removal visible in the extracted text at all).
    continuation = b"tion agreement under the archiv" + bytes([0xAD]) + b"al index."
    lines2 = wrap(prose(3, start=7), 68)
    page2_runs = [
        TextRun(font=FONT_NAME, size=BODY_SIZE, x=MARGIN, y=PAGE_H - MARGIN, text=continuation),
        *(
            TextRun(
                font=FONT_NAME,
                size=BODY_SIZE,
                x=MARGIN,
                y=PAGE_H - MARGIN - (i + 1) * LINE_HEIGHT,
                text=line.encode("ascii"),
            )
            for i, line in enumerate(lines2)
        ),
    ]
    page2 = Page(runs=tuple(page2_runs))
    # The two hyphens differ deliberately: the line-break hyphen in "coopera-" is joined away across
    # the page boundary; the soft hyphen inside "archive[U+00AD]al" is dropped in place, mid-word,
    # never touching a block boundary at all.
    expected = (
        f"The clerk filed the cooperation agreement under the archival index.\n{' '.join(lines2)}\n"
    )
    return [page1, page2], expected


def build_hyphenation_page_break() -> tuple[list[Page], str]:
    lines1 = wrap(prose(4, start=2), 68)[:-1]
    last_word_split = "contin-"
    page1_lines = [*lines1, last_word_split]
    page1 = column_of_lines(page1_lines, x=MARGIN, top=PAGE_H - MARGIN)
    continuation = "uing the survey into its second volume."
    lines2 = [continuation, *wrap(prose(3, start=9), 68)]
    page2 = column_of_lines(lines2, x=MARGIN, top=PAGE_H - MARGIN)
    body1 = " ".join(lines1)
    expected = f"{body1} continuing the survey into its second volume.\n{' '.join(lines2[1:])}\n"
    return [page1, page2], expected


# --------------------------------------------------------------------------------------------
# pathological
# --------------------------------------------------------------------------------------------


def build_pathological_invisible_text() -> tuple[list[Page], str]:
    lines = wrap(prose(3, start=13), 68)
    runs = tuple(
        TextRun(
            font=FONT_NAME,
            size=BODY_SIZE,
            x=MARGIN,
            y=PAGE_H - MARGIN - i * LINE_HEIGHT,
            text=line.encode("ascii"),
            render_mode=3,
        )
        for i, line in enumerate(lines)
    )
    return [Page(runs=runs)], " ".join(lines) + "\n"


def build_pathological_corrupt_header_source() -> list[Page]:
    lines = wrap(prose(2, start=1), 68)
    return [column_of_lines(lines, x=MARGIN, top=PAGE_H - MARGIN)]


# --------------------------------------------------------------------------------------------
# fonts each fixture needs
# --------------------------------------------------------------------------------------------

PLAIN_FONTS = {FONT_NAME: Font(name=FONT_NAME)}


def build_all(e: int, *, skip_scanned: bool = False) -> dict[str, tuple[bytes, str | None]]:
    """Returns {name: (pdf_bytes, expected_text_or_None)}. `None` means "no .expected.txt".

    `skip_scanned` omits the three rastered fixtures, which are the only ones needing pypdfium2 and
    Pillow. That is what lets the byte-identical text-layer gate still run on a `[light]`-only
    checkout, which the plan requires: the *scanned half* skips with a printed reason, not the
    whole corpus check.
    """
    results: dict[str, tuple[bytes, str | None]] = {}

    def emit(
        name: str, pages: list[Page], expected: str, fonts: dict[str, Font] | None = None
    ) -> None:
        pdf_bytes = write_text_pdf(pages, fonts or PLAIN_FONTS, e)
        results[name] = (pdf_bytes, expected)

    p, x = build_baseline_1p()
    emit("baseline-1p", p, x)
    p, x = build_baseline_12p()
    emit("baseline-12p", p, x)

    p, x = build_two_column_a()
    emit("two-column-a", p, x)
    p, x = build_two_column_b()
    emit("two-column-b", p, x)
    p, x = build_two_column_c()
    emit("two-column-c", p, x)

    p, x = build_tables_bordered()
    emit("tables-bordered", p, x)
    p, x = build_tables_borderless()
    emit("tables-borderless", p, x)
    p, x = build_tables_spanning()
    emit("tables-spanning", p, x)

    p, x = build_headers_repeating()
    emit("headers-repeating", p, x)
    p, x = build_footers_pagenum()
    emit("footers-pagenum", p, x)
    p, x = build_footer_first_page_only()
    emit("footer-first-page-only", p, x)

    p, x = build_ligatures_a()
    emit("ligatures-a", p, x, fonts={FONT_NAME: LIGATURE_FONT})
    p, x = build_hyphenation_soft()
    emit("hyphenation-soft", p, x, fonts={FONT_NAME: SOFT_HYPHEN_FONT})
    p, x = build_hyphenation_page_break()
    emit("hyphenation-page-break", p, x)

    p, x = build_pathological_invisible_text()
    emit("pathological-invisible-text", p, x)

    corrupt_pages = build_pathological_corrupt_header_source()
    corrupt_bytes = write_text_pdf(corrupt_pages, PLAIN_FONTS, e, corrupt=True)
    results["pathological-corrupt-header"] = (corrupt_bytes, "")

    if skip_scanned:
        print("scanned stratum: skipped — --skip-scanned requested (needs pypdfium2 and Pillow)")
    else:
        _build_scanned(results, e)
    return results


def _build_scanned(results: dict[str, tuple[bytes, str | None]], e: int) -> None:
    """Rasters slices of `baseline-12p`'s own pages — reusing its ground truth verbatim."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageEnhance

    baseline_bytes = results["baseline-12p"][0]
    baseline_expected = results["baseline-12p"][1] or ""
    baseline_lines = baseline_expected.rstrip("\n").split("\n")

    doc = pdfium.PdfDocument(baseline_bytes)
    try:
        rendered: list[Image.Image] = []
        for page in doc:
            bitmap = page.render(scale=150 / 72, grayscale=True)
            rendered.append(bitmap.to_pil().convert("L"))
    finally:
        doc.close()

    clean_pages = rendered[0:6]
    skewed_pages = [img.rotate(2, expand=True, fillcolor=255) for img in rendered[6:8]]
    low_contrast_pages = [ImageEnhance.Contrast(img).enhance(0.35) for img in rendered[8:10]]

    def to_images_pdf(pages: list[Image.Image]) -> bytes:
        tuples = [(img.convert("L").tobytes(), img.width, img.height) for img in pages]
        return write_image_pdf(tuples, e, dpi=150)

    results["scanned-clean"] = (to_images_pdf(clean_pages), "\n".join(baseline_lines[0:6]) + "\n")
    results["scanned-skewed"] = (to_images_pdf(skewed_pages), "\n".join(baseline_lines[6:8]) + "\n")
    results["scanned-low-contrast"] = (
        to_images_pdf(low_contrast_pages),
        "\n".join(baseline_lines[8:10]) + "\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument(
        "--skip-scanned",
        action="store_true",
        help="omit the three rastered fixtures (the only ones needing pypdfium2 and Pillow)",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    e = epoch()
    built = build_all(e, skip_scanned=args.skip_scanned)

    names = {f.name for f in FIXTURES if not (args.skip_scanned and f.scanned)}
    if set(built) != names:
        missing = names - set(built)
        extra = set(built) - names
        raise SystemExit(f"generator/spec drift: missing={missing} extra={extra}")

    for name, (pdf_bytes, expected) in built.items():
        (args.out_dir / f"{name}.pdf").write_bytes(pdf_bytes)
        if expected is not None:
            (args.out_dir / f"{name}.expected.txt").write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
