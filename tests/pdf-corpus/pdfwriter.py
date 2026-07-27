"""A minimal, dependency-free PDF writer.

Rule 11/decision from `plans/v0.2.md` I2: the sixteen text-layer fixtures are raw content streams,
no layout engine, so nothing here hides the coordinates under a library's own line-breaking or
kerning decisions. This module is the whole PDF object model the generator needs and nothing more:
objects, an xref table, a trailer, page trees, base-14 font resources (optionally with a custom
`/Encoding /Differences` array and a `/ToUnicode` CMap, for ligatures and the soft hyphen), simple
line/rectangle drawing for table borders, and Flate-compressed grayscale image XObjects for the
scanned stratum.

**Verified, not assumed (this increment):** Pillow's own `Image.save(path, "PDF", ...)` always
writes grayscale/RGB images through `/DCTDecode` (JPEG) — there is no parameter to force a lossless
filter. The plan's own text says Pillow "writes the image-only PDF... Flate-compressed", which is
not achievable through Pillow's PDF plugin as shipped (checked against its `PdfImagePlugin.py`
source, Pillow 12.3.0). So Pillow supplies pixel manipulation only (rendering via pypdfium2, then
`Image.rotate`/`ImageEnhance.Contrast`); this module writes the final PDF, compressing the raw
pixel bytes with `zlib` directly — which is exactly what PDF's `/FlateDecode` filter is.

Every date embedded in a fixture comes from `SOURCE_DATE_EPOCH`, formatted in UTC, so regeneration
on any machine in any timezone produces byte-identical output for the sixteen text-layer fixtures.
"""

from __future__ import annotations

import datetime
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field

PRODUCER = "pinakes-pdf-corpus-generator"


def pdf_date(epoch: int) -> str:
    """`D:YYYYMMDDHHMMSSZ` in UTC — never local time, so the byte-identity claim holds anywhere."""
    stamp = datetime.datetime.fromtimestamp(epoch, tz=datetime.UTC)
    return stamp.strftime("D:%Y%m%d%H%M%SZ")


def escape_pdf_string(raw: bytes) -> bytes:
    """Escape `(`, `)` and `\\` inside a PDF literal string."""
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


@dataclass(frozen=True, slots=True)
class Font:
    """One `/Font` resource: a base-14 name, optionally a custom encoding and ToUnicode map.

    `differences`: {byte_code: glyph_name} for codes that need a non-standard glyph (ligatures).
    `to_unicode`: {byte_code: codepoint} for codes whose Unicode value the default encoding gets
    wrong for this fixture's purpose (WinAnsiEncoding maps 0xAD to U+002D, not the U+00AD a
    genuine soft hyphen needs — verified empirically against pypdfium2's text extraction).
    """

    name: str
    base_font: str = "Helvetica"
    differences: dict[int, str] = field(default_factory=dict[int, str])
    to_unicode: dict[int, int] = field(default_factory=dict[int, int])


@dataclass(frozen=True, slots=True)
class TextRun:
    """One `Tj` placement: base-14 font, size, baseline origin, and the literal bytes to show."""

    font: str
    size: float
    x: float
    y: float
    text: bytes
    char_space: float = 0.0
    render_mode: int | None = None  # `Tr N` before the run; 3 = invisible


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    w: float
    h: float
    stroke: bool = True
    fill: bool = False


@dataclass(frozen=True, slots=True)
class Page:
    runs: tuple[TextRun, ...] = ()
    rects: tuple[Rect, ...] = ()
    width: float = 612.0
    height: float = 792.0


class _Writer:
    """Accumulates indirect objects and renders the final xref/trailer at the end."""

    def __init__(self) -> None:
        self._objects: list[bytes] = []

    def reserve(self) -> int:
        self._objects.append(b"")
        return len(self._objects)

    def set_object(self, number: int, header: bytes, stream: bytes | None = None) -> None:
        body = header
        if stream is not None:
            body = header + b"\nstream\n" + stream + b"\nendstream"
        self._objects[number - 1] = body

    def add_object(self, header: bytes, stream: bytes | None = None) -> int:
        number = self.reserve()
        self.set_object(number, header, stream)
        return number

    def render(self, root: int, info: int | None) -> bytes:
        parts: list[bytes] = [b"%PDF-1.4\n"]
        offsets: list[int] = [0]
        cursor = len(parts[0])
        for index, body in enumerate(self._objects, start=1):
            offsets.append(cursor)
            chunk = f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
            parts.append(chunk)
            cursor += len(chunk)
        xref_offset = cursor
        total = len(self._objects) + 1
        xref = [f"xref\n0 {total}\n".encode(), b"0000000000 65535 f \n"]
        for offset in offsets[1:]:
            xref.append(f"{offset:010d} 00000 n \n".encode())
        trailer_dict = f"<< /Size {total} /Root {root} 0 R"
        if info is not None:
            trailer_dict += f" /Info {info} 0 R"
        trailer_dict += " >>"
        parts.extend(xref)
        parts.append(b"trailer\n" + trailer_dict.encode() + b"\n")
        parts.append(b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF")
        return b"".join(parts)


def _font_object(writer: _Writer, font: Font) -> int:
    if not font.differences and not font.to_unicode:
        header = (
            f"<< /Type /Font /Subtype /Type1 /BaseFont /{font.base_font} "
            f"/Encoding /WinAnsiEncoding >>"
        ).encode()
        return writer.add_object(header)

    encoding_ref = None
    if font.differences:
        diffs = " ".join(f"{code} /{name}" for code, name in sorted(font.differences.items()))
        encoding_header = (
            f"<< /Type /Encoding /BaseEncoding /WinAnsiEncoding /Differences [{diffs}] >>"
        ).encode()
        encoding_ref = writer.add_object(encoding_header)

    tounicode_ref = None
    if font.to_unicode:
        tounicode_ref = writer.add_object(*_to_unicode_stream(font.to_unicode))

    parts = [f"/Type /Font /Subtype /Type1 /BaseFont /{font.base_font}"]
    parts.append(f"/Encoding {encoding_ref} 0 R" if encoding_ref else "/Encoding /WinAnsiEncoding")
    if tounicode_ref:
        parts.append(f"/ToUnicode {tounicode_ref} 0 R")
    header = ("<< " + " ".join(parts) + " >>").encode()
    return writer.add_object(header)


def _to_unicode_stream(mapping: dict[int, int]) -> tuple[bytes, bytes]:
    entries = "\n".join(
        f"<{code:02X}> <{codepoint:04X}>" for code, codepoint in sorted(mapping.items())
    )
    cmap = (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
        f"{len(mapping)} beginbfchar\n{entries}\nendbfchar\nendcmap\nend\nend"
    ).encode()
    return (f"<< /Length {len(cmap)} >>").encode(), cmap


def _content_stream(page: Page) -> bytes:
    ops: list[bytes] = []
    for rect in page.rects:
        ops.append(f"{rect.x:.2f} {rect.y:.2f} {rect.w:.2f} {rect.h:.2f} re".encode())
        if rect.fill and rect.stroke:
            ops.append(b"B")
        elif rect.fill:
            ops.append(b"f")
        else:
            ops.append(b"S")
    for run in page.runs:
        block = [f"BT /{run.font} {run.size:g} Tf {run.x:.2f} {run.y:.2f} Td".encode()]
        if run.render_mode is not None:
            block.append(f"{run.render_mode} Tr".encode())
        if run.char_space:
            block.append(f"{run.char_space:g} Tc".encode())
        block.append(b"(" + escape_pdf_string(run.text) + b") Tj")
        block.append(b"ET")
        ops.append(b" ".join(block))
    return b"\n".join(ops)


def write_text_pdf(
    pages: Sequence[Page], fonts: dict[str, Font], epoch: int, *, corrupt: bool = False
) -> bytes:
    """Render a multi-page, base-14-font, no-dependency PDF from `Page`/`TextRun` descriptions."""
    writer = _Writer()
    date = pdf_date(epoch)
    info = writer.add_object(
        (f"<< /Producer ({PRODUCER}) /CreationDate ({date}) /ModDate ({date}) >>").encode()
    )
    font_refs = {name: _font_object(writer, font) for name, font in fonts.items()}

    catalog = writer.reserve()
    pages_root = writer.reserve()
    page_refs: list[int] = []
    for page in pages:
        content = _content_stream(page)
        content_ref = writer.add_object((f"<< /Length {len(content)} >>").encode(), content)
        font_dict = " ".join(f"/{name} {ref} 0 R" for name, ref in font_refs.items())
        page_ref = writer.add_object(
            (
                f"<< /Type /Page /Parent {pages_root} 0 R "
                f"/MediaBox [0 0 {page.width:g} {page.height:g}] "
                f"/Resources << /Font << {font_dict} >> >> "
                f"/Contents {content_ref} 0 R >>"
            ).encode()
        )
        page_refs.append(page_ref)

    kids = " ".join(f"{ref} 0 R" for ref in page_refs)
    writer.set_object(
        pages_root, (f"<< /Type /Pages /Kids [{kids}] /Count {len(page_refs)} >>").encode()
    )
    writer.set_object(catalog, f"<< /Type /Catalog /Pages {pages_root} 0 R >>".encode())

    rendered = writer.render(root=catalog, info=info)
    if corrupt:
        rendered = b"%CORRUPT-1.4\n" + rendered[len(b"%PDF-1.4\n") :]
    return rendered


def write_image_pdf(
    images: Sequence[tuple[bytes, int, int]], epoch: int, *, dpi: int = 150
) -> bytes:
    """One page per `(grayscale_bytes, width, height)` tuple, Flate-compressed, no text layer."""
    writer = _Writer()
    date = pdf_date(epoch)
    info = writer.add_object(
        (f"<< /Producer ({PRODUCER}) /CreationDate ({date}) /ModDate ({date}) >>").encode()
    )
    catalog = writer.reserve()
    pages_root = writer.reserve()
    page_refs: list[int] = []
    for raw, width, height in images:
        page_w = width * 72.0 / dpi
        page_h = height * 72.0 / dpi
        compressed = zlib.compress(raw, level=9)
        image_ref = writer.add_object(
            (
                f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode "
                f"/Length {len(compressed)} >>"
            ).encode(),
            compressed,
        )
        content = f"q {page_w:.4f} 0 0 {page_h:.4f} 0 0 cm /Im0 Do Q".encode()
        content_ref = writer.add_object((f"<< /Length {len(content)} >>").encode(), content)
        page_ref = writer.add_object(
            (
                f"<< /Type /Page /Parent {pages_root} 0 R "
                f"/MediaBox [0 0 {page_w:.4f} {page_h:.4f}] "
                f"/Resources << /XObject << /Im0 {image_ref} 0 R >> >> "
                f"/Contents {content_ref} 0 R >>"
            ).encode()
        )
        page_refs.append(page_ref)

    kids = " ".join(f"{ref} 0 R" for ref in page_refs)
    writer.set_object(
        pages_root, (f"<< /Type /Pages /Kids [{kids}] /Count {len(page_refs)} >>").encode()
    )
    writer.set_object(catalog, f"<< /Type /Catalog /Pages {pages_root} 0 R >>".encode())
    return writer.render(root=catalog, info=info)
