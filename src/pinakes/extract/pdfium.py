"""The pypdfium2 adapter: I/O only. Everything that decides *what the text is* lives in
`layout.py` — this module opens a file, guards its size, refuses anything pdfium itself cannot
load with a named error, turns its character-level text API into I3a's `CharSpan`s, and hands the
whole document to `layout.assemble()`. Rule 11's corollary (`layout.py`'s own docstring): review
effort here is budgeted for I/O, not structure — v0.1's pure half drew one finding under review,
its I/O half four, all environmental (docs/RETROSPECTIVES.md).

Also exposes `slice_pages(path, first, last) -> bytes`: a K-page sub-document, I7b's request unit
(decision 8, `plans/v0.2.md`). It lives here, not in I7b, because this module already owns pdfium,
and I7b must never become a second PDF I/O boundary.

**Verified against pypdfium2 5.12.1, not assumed** (`stubs/pypdfium2.pyi` carries the same rule):
`get_charbox(i)` returns `(left, bottom, right, top)` in PDF's own bottom-up coordinate space,
which maps directly onto `CharSpan(x0, y0, x1, y1)` with no flip — a page's top line naturally
sorts first under `layout.py`'s own `-c.y0` ordering. Font size has no wrapped method on
`PdfTextPage`; it comes from the raw binding, `pypdfium2.raw.FPDFText_GetFontSize(text_page,
index)`, called once per character. `import_pages` raises outright on an out-of-range page list
rather than clamping it, so `slice_pages` clamps its own range first. `PdfiumError.err_code`
distinguishes `FPDF_ERR_FORMAT` (corrupt/malformed) from `FPDF_ERR_PASSWORD` (needs a password)
for the two cases this project can act on differently; everything else — including
`FPDF_ERR_SUCCESS`, which pdfium raises on at least one genuinely-empty document's load *failure*
— folds into one generic refusal.

**The fingerprint omits `pypdfium2`'s bundled PDFium *build* number, despite `plans/v0.2.md` I3b
naming it as an input.** `fingerprint_inputs` must never import the backend it describes (I1's own
`test_fingerprint_inputs_never_import_the_backend` blocks the import and asserts the function still
answers, since §4.4 calls this on every query, never only at sync) — but the build number
(`pypdfium2.version.PDFIUM_INFO`) only exists as an attribute of the imported module; no installed
distribution's metadata carries it (checked via `importlib.metadata.metadata("pypdfium2")` against
5.12.1 — no such field). Recording it would mean importing pypdfium2 on every query, which the
existing test exists specifically to prevent. `pypdfium2_version` (from package metadata, no
import needed) is what actually changes fingerprint on an upgrade in practice, so the coherence
check §4.4 exists for still functions; only a PDFium rebuild under an unchanged pypdfium2 version
would go undetected, and that combination has never shipped (docs/RETROSPECTIVES.md, I3b).
"""

from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium

from pinakes.errors import ExtractionError
from pinakes.extract import ExtractedText, ExtractionContext
from pinakes.extract.floors import load_floors
from pinakes.extract.layout import CharSpan, Page, assemble, blocks_from_chars

_MAX_PDF_BYTES = 256 * 1024 * 1024


def _open(path: Path) -> pdfium.PdfDocument:
    """Open `path`, guarding its size and translating pdfium's own refusals into `ExtractionError`.

    The size guard reads `path.stat()` before pdfium ever sees the file — large enough that no
    legitimate corpus document trips it, small enough that a runaway file fails fast instead of
    exhausting memory (`plans/v0.2.md` I3b).
    """
    size = path.stat().st_size
    if size > _MAX_PDF_BYTES:
        raise ExtractionError(
            f"{path} is {size:,} bytes, over the {_MAX_PDF_BYTES:,}-byte (256 MB) size guard.",
            remedy="This guard exists so a runaway file fails fast instead of exhausting memory; "
            "split the document or extract it another way if it is genuinely this large.",
        )

    try:
        doc = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        if exc.err_code == pdfium.raw.FPDF_ERR_FORMAT:
            raise ExtractionError(
                f"{path} is not a valid PDF (corrupt or malformed header/structure).",
                remedy="Re-export or repair the source document.",
            ) from exc
        if exc.err_code == pdfium.raw.FPDF_ERR_PASSWORD:
            raise ExtractionError(
                f"{path} could not be opened without a password.",
                remedy="pinakes has no password-entry path; decrypt the file yourself before "
                "adding it to a KB.",
            ) from exc
        raise ExtractionError(
            f"{path} could not be opened by pdfium ({exc}).",
            remedy="Re-export the source document; if it opens in other PDF viewers, file a bug.",
        ) from exc

    # Both constructions tried (pypdfium2's own `PdfDocument.new()` round trip, and a hand-built
    # spec-valid `/Kids [] /Count 0` tree) raise `PdfiumError` at the line above already, on
    # every version checked — pdfium refuses to consider zero pages a loaded document at all,
    # never returning a handle with `len(doc) == 0`. This check is asserted directly regardless:
    # the plan's contract ("a zero-page file is an error, not an empty success") should not rest
    # on an upstream behaviour this project only sampled twice, not proved for every PDF a wider
    # world could produce.
    if len(doc) == 0:
        doc.close()
        raise ExtractionError(f"{path} has no pages.", remedy="Re-export the source document.")
    return doc


def chars_from_page(page: pdfium.PdfPage) -> list[CharSpan]:
    """Public, not module-private: `quality.py`'s own floor-fitting needs the same per-page
    character extraction `Pypdfium2Extractor.extract` uses, and re-deriving it a second way would
    risk drifting from what the real extractor actually does (I3b)."""
    textpage = page.get_textpage()
    chars: list[CharSpan] = []
    for index in range(textpage.count_chars()):
        left, bottom, right, top = textpage.get_charbox(index)
        chars.append(
            CharSpan(
                char=textpage.get_text_range(index, 1),
                x0=left,
                y0=bottom,
                x1=right,
                y1=top,
                font_size=pdfium.raw.FPDFText_GetFontSize(textpage, index),
            )
        )
    return chars


class Pypdfium2Extractor:
    """The free backend: `Extractor.extract`, all I/O — no reading-order or furniture decision
    lives here (that is `layout.assemble`'s job, over the `CharSpan`s this class hands it)."""

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractedText:
        floors = load_floors()
        doc = _open(path)
        try:
            pages: list[Page] = []
            for index, page in enumerate(doc):
                chars = chars_from_page(page)
                blocks = blocks_from_chars(chars, page_index=index)
                pages.append(Page(blocks=tuple(blocks)))
        finally:
            doc.close()
        return assemble(tuple(pages), running_head_threshold=floors.running_head_threshold)


def slice_pages(path: Path, first: int, last: int) -> bytes:
    """A `[first, last]` (inclusive, 0-indexed) sub-document as bytes — I7b's request unit.

    `last` is clamped to the source document's own last page: pdfium's `import_pages` raises
    outright on any out-of-range index rather than tolerating or clamping one itself (verified
    against 5.12.1), so a range that runs past the end must be narrowed before it ever reaches
    that call, not after.

    `first > last` (after clamping) raises `ValueError` rather than passing an empty page list
    through — verified against 5.12.1 that pypdfium2's own `import_pages` treats an empty list as
    falsy and silently imports *every* page, identically to passing `pages=None` ("all pages"),
    which is the opposite of what an empty requested range should mean. Caught here, before that
    call, since a future off-by-one computing a page window (e.g. the last window of a document
    whose length isn't a multiple of the window size) would otherwise silently send the *whole*
    document to a paid API instead of a small slice — a cost-control failure, not merely a wrong
    answer (docs/RETROSPECTIVES.md, I3b retrospective).
    """
    src = _open(path)
    try:
        if first < 0:
            raise ValueError(f"slice_pages: first={first} must be >= 0")
        last_clamped = min(last, len(src) - 1)
        if first > last_clamped:
            raise ValueError(
                f"slice_pages: first={first} is past last={last_clamped} "
                f"(document has {len(src)} pages, requested last was {last})"
            )
        dest = pdfium.PdfDocument.new()
        try:
            dest.import_pages(src, pages=list(range(first, last_clamped + 1)))
            buffer = io.BytesIO()
            dest.save(buffer)
            return buffer.getvalue()
        finally:
            dest.close()
    finally:
        src.close()
