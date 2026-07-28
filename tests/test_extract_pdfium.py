"""`extract/pdfium.py`'s own contract — the reader's I/O refusals, and `slice_pages`'s range clamp.

Not tested here, by design: extraction *quality* against real content (`test_extract_quality.py`)
and `layout.py`'s own structural logic (`test_extract_layout.py`, pure, no pdfium at all). This file
is only about what happens when a file cannot, or should not, be opened at all.
"""

import hashlib
import io
import struct
from pathlib import Path

import pytest
from conftest import pdf_extraction_runnable

from pinakes.errors import ExtractionError
from pinakes.extract import ExtractionContext

pytestmark = [
    pytest.mark.pdf,
    pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed"),
]

CORPUS_DIR = Path(__file__).parent / "pdf-corpus"

# --------------------------------------------------------------------------------------------
# A minimal PDF Standard Security Handler (RC4-40, Revision 2), built once here for exactly one
# purpose: prove the reader refuses a password-protected file *before* any content parse. No
# dependency added for this — RC4 and the padding string are ~20 lines each, both public, and
# `hashlib.md5` is already stdlib. The content stream is left in plaintext; only the trailer's own
# /O, /U and /P need to be internally consistent for pdfium's own password check to run and fail,
# which is the only thing under test (verified: pdfium checks the password before ever touching a
# page's content, so an unencrypted body under a genuine /Encrypt dict still exercises the refusal).
# --------------------------------------------------------------------------------------------

_PADDING = bytes(
    [
        0x28, 0xBF, 0x4E, 0x5E, 0x4E, 0x75, 0x8A, 0x41,
        0x64, 0x00, 0x4E, 0x56, 0xFF, 0xFA, 0x01, 0x08,
        0x2E, 0x2E, 0x00, 0xB6, 0xD0, 0x68, 0x3E, 0x80,
        0x2F, 0x0C, 0xA9, 0xFE, 0x64, 0x53, 0x69, 0x7A,
    ]
)  # fmt: skip


def _rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(byte ^ s[(s[i] + s[j]) % 256])
    return bytes(out)


def _pad(password: bytes) -> bytes:
    return (password + _PADDING)[:32]


def _encrypted_pdf_bytes(
    *, user_password: bytes = b"secret", owner_password: bytes = b"owner"
) -> bytes:
    """A syntactically valid, genuinely password-required one-page PDF — the user password is
    deliberately non-empty, so pdfium's own default (empty-password) open attempt fails."""
    o_value = _rc4(hashlib.md5(_pad(owner_password)).digest()[:5], _pad(user_password))
    p_value = -4
    id0 = hashlib.md5(b"pinakes-test-fixture-id").digest()
    key = hashlib.md5(_pad(user_password) + o_value + struct.pack("<i", p_value) + id0).digest()[:5]
    u_value = _rc4(key, _PADDING)

    def hexs(data: bytes) -> str:
        return "<" + data.hex() + ">"

    content = b"BT /F1 12 Tf 72 700 Td (hello) Tj ET"
    objects = [
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        f"<< /Length {len(content)} >>".encode() + b"\nstream\n" + content + b"\nendstream",
        b"<< /Type /Catalog /Pages 4 0 R >>",
        b"<< /Type /Pages /Kids [5 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 4 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 1 0 R >> >> /Contents 2 0 R >>"
        ),
        (
            f"<< /Filter /Standard /V 1 /R 2 /O {hexs(o_value)} /U {hexs(u_value)} /P {p_value} >>"
        ).encode(),
    ]
    parts = [b"%PDF-1.4\n"]
    offsets = [0]
    cursor = len(parts[0])
    for index, body in enumerate(objects, start=1):
        offsets.append(cursor)
        chunk = f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
        parts.append(chunk)
        cursor += len(chunk)
    xref_offset = cursor
    total = len(objects) + 1
    xref = [f"xref\n0 {total}\n".encode(), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode())
    trailer = (
        f"<< /Size {total} /Root 3 0 R /Encrypt 6 0 R /ID [{hexs(id0)} {hexs(id0)}] >>"
    ).encode()
    parts.extend(xref)
    parts.append(b"trailer\n" + trailer + b"\n")
    parts.append(b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF")
    return b"".join(parts)


def _zero_page_pdf_bytes() -> bytes:
    """A spec-valid PDF whose page tree has zero pages (`/Kids [] /Count 0`) — not
    `pdfium.PdfDocument.new()`'s own round trip, which raises with a *different*, more confusing
    `err_code` (verified against 5.12.1; docs/RETROSPECTIVES.md, I3b): this is the more
    representative "a real tool wrote an empty document" shape."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [] /Count 0 >>",
    ]
    parts = [b"%PDF-1.4\n"]
    offsets = [0]
    cursor = len(parts[0])
    for index, body in enumerate(objects, start=1):
        offsets.append(cursor)
        chunk = f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
        parts.append(chunk)
        cursor += len(chunk)
    xref_offset = cursor
    total = len(objects) + 1
    xref = [f"xref\n0 {total}\n".encode(), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode())
    parts.extend(xref)
    parts.append(b"trailer\n" + f"<< /Size {total} /Root 1 0 R >>".encode() + b"\n")
    parts.append(b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF")
    return b"".join(parts)


def test_corrupt_header_fixture_raises_a_named_error_not_a_crash() -> None:
    from pinakes.extract.pdfium import Pypdfium2Extractor

    path = CORPUS_DIR / "pathological-corrupt-header.pdf"
    with pytest.raises(ExtractionError, match="corrupt or malformed"):
        Pypdfium2Extractor().extract(path, ExtractionContext())


def test_size_guard_fires_at_256mb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A real 256 MB file is never written for this test — `_MAX_PDF_BYTES` is a plain module
    constant read from `path.stat()`, so a small file plus a lowered constant proves the same
    branch a real oversize file would hit, without allocating one."""
    from pinakes.extract import pdfium as pdfium_module

    monkeypatch.setattr(pdfium_module, "_MAX_PDF_BYTES", 10)
    path = tmp_path / "small-but-over-the-lowered-limit.pdf"
    path.write_bytes(b"%PDF-1.4\nnot even a real PDF, just over 10 bytes\n")
    with pytest.raises(ExtractionError, match="256 MB"):
        pdfium_module.Pypdfium2Extractor().extract(path, ExtractionContext())


def test_encrypted_file_is_refused_before_any_parse(tmp_path: Path) -> None:
    from pinakes.extract.pdfium import Pypdfium2Extractor

    path = tmp_path / "encrypted.pdf"
    path.write_bytes(_encrypted_pdf_bytes())
    with pytest.raises(ExtractionError, match="password"):
        Pypdfium2Extractor().extract(path, ExtractionContext())


def test_zero_page_file_is_an_error_not_an_empty_success(tmp_path: Path) -> None:
    from pinakes.extract.pdfium import Pypdfium2Extractor

    path = tmp_path / "zero-pages.pdf"
    path.write_bytes(_zero_page_pdf_bytes())
    with pytest.raises(ExtractionError):
        Pypdfium2Extractor().extract(path, ExtractionContext())


def test_invisible_render_mode_fixture_yields_its_characters() -> None:
    """Text-rendering mode 3 (invisible) hides a glyph from *rendering*, not from *extraction* —
    pdfium's character-level API has no render-mode signal to filter on in the first place, so this
    fixture's whole point is proving nothing here accidentally reads or respects one."""
    from pinakes.extract.pdfium import Pypdfium2Extractor

    path = CORPUS_DIR / "pathological-invisible-text.pdf"
    expected = (CORPUS_DIR / "pathological-invisible-text.expected.txt").read_text()
    result = Pypdfium2Extractor().extract(path, ExtractionContext())
    assert " ".join(result.text.split()) == " ".join(expected.split())


def test_slice_pages_returns_a_valid_subdocument_matching_the_requested_range() -> None:
    import pypdfium2 as pdfium

    from pinakes.extract.pdfium import slice_pages

    path = CORPUS_DIR / "baseline-12p.pdf"
    sliced = slice_pages(path, 2, 4)  # pages 2,3,4 -- inclusive, 0-indexed
    doc = pdfium.PdfDocument(sliced)
    try:
        assert len(doc) == 3
        text = "".join(page.get_textpage().get_text_range() for page in doc)
        assert text.strip()
    finally:
        doc.close()


def test_slice_pages_clamps_a_range_that_runs_past_the_last_page() -> None:
    """pdfium's own `import_pages` raises outright on an out-of-range index rather than tolerating
    or clamping it (verified against 5.12.1) — `slice_pages` must narrow the range itself before
    that call, not after, or a caller asking for "the rest of the document" from an unknown page
    count would simply crash instead of getting what actually exists."""
    import pypdfium2 as pdfium

    from pinakes.extract.pdfium import slice_pages

    path = CORPUS_DIR / "baseline-12p.pdf"
    sliced = slice_pages(path, 10, 999)  # only pages 10, 11 actually exist (12-page document)
    doc = pdfium.PdfDocument(sliced)
    try:
        assert len(doc) == 2
    finally:
        doc.close()


def test_slice_pages_round_trip_preserves_bytes_that_reopen(tmp_path: Path) -> None:
    """`slice_pages` returns real, independently-openable PDF bytes -- not a reference into the
    source document, which `_open`'s own `finally: src.close()` would otherwise invalidate."""
    from pinakes.extract.pdfium import slice_pages

    path = CORPUS_DIR / "baseline-12p.pdf"
    sliced = slice_pages(path, 0, 0)
    out = tmp_path / "one-page.pdf"
    out.write_bytes(sliced)
    buffer = io.BytesIO(sliced)
    assert buffer.getvalue().startswith(b"%PDF")
