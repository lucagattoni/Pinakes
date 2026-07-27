"""Hand-authored stub for the pypdfium2 surface this project actually calls.

pypdfium2 ships no `py.typed` marker and no `.pyi` files (checked against 5.12.1's installed
package — no inline suppression could fix that, since `reportMissingTypeStubs` flags the import
itself). This describes only what I2 uses, verified empirically against the real library rather
than assumed from its docs: `PdfDocument` accepts `bytes` directly (no temp file needed),
`render(scale=...)` takes a `float`, and `PdfBitmap.to_pil()` returns a real `PIL.Image.Image`.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from PIL.Image import Image

class PdfiumError(Exception): ...

class PdfBitmap:
    def to_pil(self) -> Image: ...

class PdfTextPage:
    def get_text_range(self, index: int = ..., count: int = ...) -> str: ...
    def count_chars(self) -> int: ...

class PdfPage:
    def render(
        self,
        scale: float = ...,
        rotation: int = ...,
        grayscale: bool = ...,
        **kwargs: Any,
    ) -> PdfBitmap: ...
    def get_textpage(self) -> PdfTextPage: ...
    def get_size(self) -> tuple[float, float]: ...

class PdfDocument:
    def __init__(self, input_data: bytes | str | Path, *, autoclose: bool = ...) -> None: ...
    def __len__(self) -> int: ...
    def __getitem__(self, index: int) -> PdfPage: ...
    def __iter__(self) -> Iterator[PdfPage]: ...
    def close(self) -> None: ...
