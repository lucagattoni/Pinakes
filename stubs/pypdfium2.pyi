"""Hand-authored stub for the pypdfium2 surface this project actually calls.

pypdfium2 ships no `py.typed` marker and no `.pyi` files (checked against 5.12.1's installed
package — no inline suppression could fix that, since `reportMissingTypeStubs` flags the import
itself). This describes only what the project uses.

**Signatures transcribed from the installed library via `inspect.signature`, not from its docs.**
Two consequences worth stating, because a stub that quietly disagrees with reality is worse than
no stub: `render` really does absorb `grayscale` through `**kwargs` rather than declaring it, and
it is declared here explicitly so a typo in that keyword is still caught; and `PdfDocument` takes
`(input, password=None, autoclose=False)` positionally-or-by-keyword, so none of it is keyword-only.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from PIL.Image import Image

class PdfiumError(Exception): ...

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
