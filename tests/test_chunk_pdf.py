"""`chunk_document(kind="pdf")` against the real corpus: the span invariant, the never-drop
guarantee, and page provenance — re-asserting I1/v0.1's guarantees hold for the new path, not
assuming they carry over just because `_fit`/`_atomise` are unchanged (I5).

Scanned fixtures are excluded (no text layer at all — nothing to chunk); the corrupt-header
fixture is excluded (cannot be opened, by design). That is the plan's own "15 extractable
fixtures... with the four exclusions declared" — 19 total minus 3 scanned minus 1 corrupt.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from conftest import pdf_extraction_runnable

from pinakes.chunk import Chunk, TokenCounter, chunk_document
from pinakes.extract import ExtractedText

pytestmark = [
    pytest.mark.pdf,
    pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed"),
]

CORPUS_DIR = Path(__file__).parent / "pdf-corpus"
MAX_TOKENS = 40
OVERLAP = 5


class WordCounter:
    def count_tokens(self, text: str) -> int:
        return len(text.split())


_WORD_COUNTER = WordCounter()


def _load_module(path: Path, name: str) -> ModuleType:
    """`tests/pdf-corpus/` has a hyphen, so it cannot be a dotted-import package — load by path
    (matching `test_pdf_corpus.py`'s own helper, not a `sys.path` mutation shared across tests)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extractable_fixtures() -> list[str]:
    fixtures = _load_module(CORPUS_DIR / "spec.py", "pdf_corpus_spec_for_chunking").FIXTURES
    return [f.name for f in fixtures if not f.scanned and not f.corrupt]


def _extract(name: str) -> ExtractedText:
    from pinakes.extract import ExtractionContext
    from pinakes.extract.pdfium import Pypdfium2Extractor

    return Pypdfium2Extractor().extract(CORPUS_DIR / f"{name}.pdf", ExtractionContext())


def _chunk_pdf(
    name: str, *, counter: TokenCounter = _WORD_COUNTER
) -> tuple[list[Chunk], ExtractedText]:
    extracted = _extract(name)
    chunks = chunk_document(
        extracted.text,
        counter=counter,
        max_tokens=MAX_TOKENS,
        overlap=OVERLAP,
        kind="pdf",
        page_spans=extracted.page_spans,
    )
    return chunks, extracted


@pytest.mark.parametrize("name", _extractable_fixtures())
def test_the_span_invariant_holds_for_every_chunk(name: str) -> None:
    """`chunk.text == extracted.text[char_start:char_end]` — a citation is only honest if the
    span it names really is the text it claims to be."""
    chunks, extracted = _chunk_pdf(name)
    for chunk in chunks:
        assert chunk.text == extracted.text[chunk.char_start : chunk.char_end]


@pytest.mark.parametrize("name", _extractable_fixtures())
def test_every_character_lands_in_at_least_one_chunk(name: str) -> None:
    """v0.1's never-drop guarantee, re-proved for the PDF path: overlap may repeat text, nothing
    may skip it."""
    chunks, extracted = _chunk_pdf(name)
    covered = bytearray(len(extracted.text))
    for chunk in chunks:
        for offset in range(chunk.char_start, chunk.char_end):
            covered[offset] = 1
    uncovered = [i for i, hit in enumerate(covered) if not hit and not extracted.text[i].isspace()]
    assert not uncovered, f"{name}: {len(uncovered)} non-whitespace characters in no chunk at all"


@pytest.mark.parametrize("name", _extractable_fixtures())
def test_page_numbers_are_monotonic_and_within_range(name: str) -> None:
    chunks, extracted = _chunk_pdf(name)
    page_count = len(extracted.page_spans)
    for chunk in chunks:
        assert chunk.page_start is not None
        assert chunk.page_end is not None
        assert 1 <= chunk.page_start <= chunk.page_end <= page_count


@pytest.mark.parametrize("name", _extractable_fixtures())
def test_heading_path_is_always_none_for_pdf_chunks(name: str) -> None:
    """A PDF has pages, not headings — stuffing "p. 7" into a free-text filter/citation column
    is v0.1's I6 defect rewritten (plan text, I5)."""
    chunks, _ = _chunk_pdf(name)
    assert all(chunk.heading_path is None for chunk in chunks)


def test_a_hyphenation_join_across_a_page_break_produces_a_genuine_two_page_chunk() -> None:
    """The corpus's own `hyphenation-page-break` fixture exists to exercise exactly this: a word
    split across two pages, joined with no separator (`join_hyphenation`, extract/layout.py), so
    the same blank-line block detection this module already does straddles the boundary — no
    special-cased splitting-at-page-boundaries logic needed, just a correct page lookup."""
    chunks, extracted = _chunk_pdf("hyphenation-page-break")
    assert len(extracted.page_spans) >= 2
    two_page = [c for c in chunks if c.page_start != c.page_end]
    assert two_page, "expected at least one chunk spanning two pages in hyphenation-page-break"
    for chunk in two_page:
        assert chunk.page_start is not None and chunk.page_end is not None
        assert chunk.page_end == chunk.page_start + 1


def test_markdown_and_text_chunks_never_carry_page_numbers() -> None:
    chunks = chunk_document(
        "# Title\n\nSome body text.\n", counter=_WORD_COUNTER, max_tokens=100, overlap=0
    )
    assert all(c.page_start is None and c.page_end is None for c in chunks)
