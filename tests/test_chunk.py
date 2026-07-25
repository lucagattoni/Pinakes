"""Chunking: structure is respected, limits are honoured, and no character is ever dropped."""

import pytest

from pinakes.chunk import (
    Chunk,
    TokenCounter,
    assert_chunkable,
    chunk_document,
    source_type,
)
from pinakes.errors import ChunkingError


class WordCounter:
    """A deterministic stand-in for a model tokenizer: one token per whitespace-separated word.

    Chunking is tested against this rather than a real model so the assertions are exact and no
    test downloads weights. The real tokenizers arrive in I7 behind the same protocol.
    """

    def count_tokens(self, text: str) -> int:
        return len(text.split())


class DenseCounter:
    """Closer to a real BPE tokenizer: roughly one token per four characters.

    Needed because a `WordCounter` says a 400-character unbroken run is one token, which is true
    for it and false for every model — the character-cut path only exists for counters like this.
    """

    def count_tokens(self, text: str) -> int:
        return max(1, -(-len(text) // 4))


@pytest.fixture
def counter() -> TokenCounter:
    return WordCounter()


def chunked(
    text: str,
    counter: TokenCounter,
    *,
    max_tokens: int = 20,
    overlap: int = 0,
    kind: str = "markdown",
) -> list[Chunk]:
    return chunk_document(text, counter=counter, max_tokens=max_tokens, overlap=overlap, kind=kind)


def assert_nothing_dropped(text: str, chunks: list[Chunk]) -> None:
    """The module's central invariant: every non-space character lands in at least one chunk."""
    covered = bytearray(len(text))
    for chunk in chunks:
        for index in range(chunk.char_start, min(chunk.char_end, len(text))):
            covered[index] = 1
    missing = [
        index for index, flag in enumerate(covered) if not flag and not text[index].isspace()
    ]
    assert not missing, (
        f"characters dropped at {missing[:10]}: {text[missing[0] : missing[0] + 40]!r}"
    )


def test_source_type_from_filename() -> None:
    assert source_type("notes.md") == "markdown"
    assert source_type("NOTES.MARKDOWN") == "markdown"
    assert source_type("main.py") == "code"
    assert source_type("readme") == "text"
    assert source_type("data.csv") == "text"


def test_paragraphs_become_chunks_under_their_heading_path(counter: TokenCounter) -> None:
    text = (
        "# Retrieval\n\n"
        "Hybrid search fuses lexical and dense results.\n\n"
        "## Reranking\n\n"
        "A cross-encoder scores the survivors.\n\n"
        "Its scores are not comparable across queries.\n"
    )
    chunks = chunked(text, counter)

    assert [chunk.heading_path for chunk in chunks] == [
        "Retrieval",
        "Retrieval > Reranking",
        "Retrieval > Reranking",
    ]
    # The heading is part of its first chunk: the lexical index only sees chunk text, so a
    # heading-only word would otherwise be unsearchable.
    assert chunks[0].text.startswith("# Retrieval")
    assert "Hybrid search" in chunks[0].text
    assert_nothing_dropped(text, chunks)


def test_heading_paths_pop_back_to_the_right_level(counter: TokenCounter) -> None:
    text = "# A\n\nfirst\n\n## B\n\nsecond\n\n### C\n\nthird\n\n## D\n\nfourth\n\n# E\n\nfifth\n"
    assert [chunk.heading_path for chunk in chunked(text, counter)] == [
        "A",
        "A > B",
        "A > B > C",
        "A > D",
        "E",
    ]


def test_spans_point_at_the_original_text(counter: TokenCounter) -> None:
    text = "# Title\n\nFirst paragraph here.\n\nSecond paragraph here.\n"
    for chunk in chunked(text, counter):
        assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_a_fenced_code_block_is_not_split_by_its_blank_lines(counter: TokenCounter) -> None:
    text = "# Code\n\n```python\ndef f():\n\n    return 1\n```\n\nAfter.\n"
    chunks = chunked(text, counter)
    code = [chunk for chunk in chunks if "def f()" in chunk.text]
    assert len(code) == 1
    assert "return 1" in code[0].text
    assert_nothing_dropped(text, chunks)


def test_an_oversize_paragraph_is_split_never_trimmed(counter: TokenCounter) -> None:
    """A truncated chunk has an unsearchable tail and nothing in the output would reveal it."""
    sentences = " ".join(f"Sentence number {n} carries some words." for n in range(40))
    text = f"# Long\n\n{sentences}\n"
    chunks = chunked(text, counter, max_tokens=20)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 20 for chunk in chunks)
    assert_nothing_dropped(text, chunks)
    assert "Sentence number 39" in "".join(chunk.text for chunk in chunks)


def test_overlap_repeats_context_without_losing_position(counter: TokenCounter) -> None:
    sentences = " ".join(f"Part {n} of the paragraph." for n in range(30))
    chunks = chunked(sentences, counter, max_tokens=15, overlap=5, kind="text")

    assert len(chunks) > 1
    assert all(chunk.token_count <= 15 for chunk in chunks)
    assert_nothing_dropped(sentences, chunks)


def test_a_single_unbroken_run_is_still_divided(counter: TokenCounter) -> None:
    """One enormous piece with no punctuation must not defeat the limit."""
    text = "word " * 200
    chunks = chunked(text.strip(), counter, max_tokens=10, kind="text")
    assert len(chunks) > 1
    assert all(chunk.token_count <= 10 for chunk in chunks)


def test_empty_and_whitespace_documents_produce_nothing(counter: TokenCounter) -> None:
    assert chunked("", counter) == []
    assert chunked("   \n\n\t\n", counter) == []


def test_overlap_at_least_max_tokens_is_refused(counter: TokenCounter) -> None:
    with pytest.raises(ChunkingError) as exc_info:
        chunked("text", counter, max_tokens=10, overlap=10)
    assert "smaller than max_tokens" in exc_info.value.message


def test_max_tokens_beyond_the_model_window_is_refused() -> None:
    assert_chunkable(510, model_max_tokens=512)
    with pytest.raises(ChunkingError) as exc_info:
        assert_chunkable(512, model_max_tokens=512)
    assert "510" in exc_info.value.remedy


def test_plain_text_has_no_heading_paths(counter: TokenCounter) -> None:
    text = "First block.\n\nSecond block.\n"
    chunks = chunked(text, counter, kind="text")
    assert [chunk.heading_path for chunk in chunks] == [None, None]
    assert_nothing_dropped(text, chunks)


def test_headings_alone_produce_no_chunks(counter: TokenCounter) -> None:
    """A document with no body has nothing to retrieve; headings attach to content or not at all."""
    assert chunked("# Only\n\n## Headings\n", counter) == []


def test_an_unbroken_token_dense_run_is_cut_by_characters() -> None:
    """A base64 blob has no sentence or word boundaries, and must still not exceed the limit."""
    dense = DenseCounter()
    blob = "A" * 400
    chunks = chunked(blob, dense, max_tokens=8, kind="text")

    assert len(chunks) > 1
    assert all(chunk.token_count <= 8 for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks) == blob
    assert_nothing_dropped(blob, chunks)


def test_as_row_matches_the_store_signature(counter: TokenCounter) -> None:
    chunk = chunked("# H\n\nbody text\n", counter)[0]
    row = chunk.as_row()
    assert row == (chunk.text, chunk.char_start, chunk.char_end, chunk.token_count, "H")


def test_token_counts_come_from_the_counter(counter: TokenCounter) -> None:
    chunk = chunked("# H\n\none two three four\n", counter)[0]
    assert chunk.token_count == 6  # "# H" plus the four words
