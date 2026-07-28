"""Hand-authored stub for the pypdfium2 surface this project actually calls.

pypdfium2 ships no `py.typed` marker and no `.pyi` files (checked against 5.12.1's installed
package — no inline suppression could fix that, since `reportMissingTypeStubs` flags the import
itself). This describes only what the project uses.

**Signatures transcribed from the installed library via `inspect.signature`, not from its docs.**
Two consequences worth stating, because a stub that quietly disagrees with reality is worse than
no stub: `render` really does absorb `grayscale` through `**kwargs` rather than declaring it, and
it is declared here explicitly so a typo in that keyword is still caught; and `PdfDocument` takes
`(input, password=None, autoclose=False)` positionally-or-by-keyword, so none of it is keyword-only.

**I3b additions, same rule.** `PdfDocument.new` is a `classmethod` (checked via
`inspect.getattr_static`, not guessed from call syntax); `import_pages` raises `PdfiumError` (no
`err_code`) when any requested index is out of range — it does not clamp or ignore silently, which
is why `extract/pdfium.py`'s `slice_pages` clamps its own range before calling it.
`PdfiumError.err_code` is a real, documented attribute (`Attributes:` in the library's own
docstring), not an inference: `FPDF_ERR_FORMAT` (3) for the corrupt-header fixture,
`FPDF_ERR_PASSWORD` (4) for a genuinely password-protected file, but *also* (4) for at least one
structurally-degenerate zero-page construction, and, oddest of all, `FPDF_ERR_SUCCESS` (0) for a
hand-built, spec-valid zero-page PDF (`PdfDocument.new()` raises with a "Success" message on a load
*failure* — verified against 5.12.1, `docs/RETROSPECTIVES.md`, I3b). `err_code` is therefore read
for the two cases the reader states distinctly (`FORMAT`, `PASSWORD`) and everything else — this
file's own `_Raw` block exists so pyright sees `pypdfium2.raw` as an attribute of the
already-imported top-level module (verified true via `hasattr`), never a package-style stub split,
since nothing else here needs one.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO

from PIL.Image import Image

class PdfiumError(RuntimeError):
    err_code: int | None

class PdfBitmap:
    def to_pil(self) -> Image: ...

class PdfTextPage:
    def get_text_range(self, index: int = ..., count: int = ..., errors: str = ...) -> str: ...
    def count_chars(self) -> int: ...
    def get_charbox(self, index: int, loose: bool = ...) -> tuple[float, float, float, float]: ...

class PdfPage:
    def render(
        self,
        scale: float = ...,
        rotation: int = ...,
        crop: tuple[float, float, float, float] = ...,
        may_draw_forms: bool = ...,
        color_scheme: Any | None = ...,
        fill_to_stroke: bool = ...,
        *,
        grayscale: bool = ...,
        **kwargs: Any,
    ) -> PdfBitmap: ...
    def get_textpage(self) -> PdfTextPage: ...
    def get_size(self) -> tuple[float, float]: ...

class PdfDocument:
    def __init__(
        self,
        input: bytes | str | Path,
        password: str | None = ...,
        autoclose: bool = ...,
    ) -> None: ...
    def __len__(self) -> int: ...
    def __getitem__(self, index: int) -> PdfPage: ...
    def __iter__(self) -> Iterator[PdfPage]: ...
    def close(self) -> None: ...
    @classmethod
    def new(cls) -> PdfDocument: ...
    def import_pages(
        self, pdf: PdfDocument, pages: list[int] | None = ..., index: int | None = ...
    ) -> None: ...
    def save(self, dest: BinaryIO, version: int | None = ..., flags: int = ...) -> None: ...

class _Raw:
    FPDF_ERR_SUCCESS: int
    FPDF_ERR_UNKNOWN: int
    FPDF_ERR_FILE: int
    FPDF_ERR_FORMAT: int
    FPDF_ERR_PASSWORD: int
    FPDF_ERR_SECURITY: int
    FPDF_ERR_PAGE: int
    @staticmethod
    def FPDFText_GetFontSize(text_page: PdfTextPage, index: int) -> float: ...

raw: _Raw

class _Version:
    # `str()`-only: the real type is a private `pypdfium2_raw.version._version_pdfium`, and every
    # call site here only ever wants its string form for a fingerprint, never the object itself.
    PDFIUM_INFO: object
    PYPDFIUM_INFO: object

version: _Version
