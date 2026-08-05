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
    assert source_type("scan.pdf") == "pdf"
    assert source_type("SCAN.PDF") == "pdf"


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


@pytest.mark.parametrize("max_tokens", [4, 10, 25])
@pytest.mark.parametrize("overlap", [0, 1, 3, 9])
def test_no_chunk_ever_exceeds_the_limit(max_tokens: int, overlap: int) -> None:
    """Across the whole (max_tokens, overlap) matrix, including overlap close to the limit.

    An earlier version kept the carried-over context unconditionally, so `overlap = 9` with
    `max_tokens = 10` produced 12-token chunks — silently truncated at encode time.
    """
    if overlap >= max_tokens:
        pytest.skip("rejected by configuration")
    counter = WordCounter()
    text = " ".join(f"clause {n} of the paragraph." for n in range(40))
    chunks = chunk_document(
        text, counter=counter, max_tokens=max_tokens, overlap=overlap, kind="text"
    )
    assert chunks
    assert all(chunk.token_count <= max_tokens for chunk in chunks)
    assert_nothing_dropped(text, chunks)


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
    assert row == (chunk.text, chunk.char_start, chunk.char_end, chunk.token_count, "H", None, None)


def test_token_counts_come_from_the_counter(counter: TokenCounter) -> None:
    chunk = chunked("# H\n\none two three four\n", counter)[0]
    assert chunk.token_count == 6  # "# H" plus the four words


# --- The numbered-heading grammar (`[chunking] headings = "numbered"`) ---------------------------
#
# Every test below names the clause of the predicate it pins
# (`plans/20260805_1721-metadata-as-retrieval-context.md` § 5.3). The predicate was written in full
# *before* any corpus was consulted, and these tests are written against the clauses rather than
# against a corpus, for the same reason: a rule fitted to its own answer proves nothing.

_OUTLINE = """1. Introduction

This document describes a thing.

1.1. Scope

It applies broadly.

2. Terminology

Words mean things.
"""


def _paths(text: str, counter: TokenCounter, *, kind: str = "text", headings: str = "numbered"):
    chunks = chunk_document(
        text, counter=counter, max_tokens=100, overlap=10, kind=kind, headings=headings
    )
    return [chunk.heading_path for chunk in chunks]


def test_a_numbered_outline_becomes_a_heading_path(counter: TokenCounter) -> None:
    assert _paths(_OUTLINE, counter) == [
        "1. Introduction",
        "1. Introduction > 1.1. Scope",
        "2. Terminology",
    ]


def test_the_grammar_is_opt_in_and_off_by_default(counter: TokenCounter) -> None:
    """`headings="none"` is the default. The same document that labels cleanly above must come back
    with nothing when the key is absent — otherwise the key is decorative and every existing KB
    silently changed behaviour on upgrade."""
    assert set(_paths(_OUTLINE, counter, headings="none")) == {None}


def test_an_ordered_list_that_restarts_yields_no_headings_at_all(counter: TokenCounter) -> None:
    """Clause 8, the whole design. `1.` at line start is also an ordered list, and a list that
    restarts breaks the outline walk. The document must fall back to *exactly* pre-grammar
    behaviour — not to a partial labelling, which would be the confident-nonsense outcome."""
    listy = "Steps:\n\n1. First do this.\n\n2. Then do that.\n\n1. Restarting the count.\n"
    assert set(_paths(listy, counter)) == {None}


def test_a_repeated_number_rejects_the_document(counter: TokenCounter) -> None:
    """Clause 6's no-repeats rule, reached without a restart-to-1."""
    doubled = "1. Alpha\n\nBody.\n\n2. Beta\n\nBody.\n\n2. Beta again\n\nBody.\n"
    assert set(_paths(doubled, counter)) == {None}


def test_a_table_of_contents_does_not_disqualify_the_document(counter: TokenCounter) -> None:
    """Clause 3. Without the dot-leader rule a ToC's entries duplicate every real section number,
    clause 6 sees repeats, and the whole document is rejected — so this asserts the *sections*
    still label, which is what the clause exists to protect."""
    with_toc = (
        "Table of Contents\n\n"
        "1. Introduction .......................... 3\n\n"
        "2. Terminology ........................... 7\n\n"
        "1. Introduction\n\nBody of the introduction.\n\n"
        "2. Terminology\n\nBody of the terminology.\n"
    )
    # The ToC lines stay ordinary unlabelled blocks — they are content, not structure.
    assert _paths(with_toc, counter) == [
        None,
        None,
        None,
        "1. Introduction",
        "2. Terminology",
    ]


def test_an_indented_number_is_not_a_heading(counter: TokenCounter) -> None:
    """Clause 1 — column 0. Indented enumerations are the commonest false positive, and with only
    one real heading left the document falls below clause 7's minimum."""
    indented = "1. Real Heading\n\nBody.\n\n    2. Indented item\n\nMore body.\n"
    assert set(_paths(indented, counter)) == {None}


def test_a_sentence_shaped_line_is_not_a_heading(counter: TokenCounter) -> None:
    """Clause 4 — a heading is a label, not a sentence. Both halves: over-long, and
    terminal punctuation."""
    long_title = "x" * (100 + 1)
    assert set(_paths(f"1. {long_title}\n\nBody.\n\n2. Beta\n\nBody.\n", counter)) == {None}
    assert set(_paths("1. Alpha:\n\nBody.\n\n2. Beta:\n\nBody.\n", counter)) == {None}


def test_a_line_not_preceded_by_a_blank_line_is_not_a_heading(counter: TokenCounter) -> None:
    """Clause 5. A numbered line continuing a paragraph is prose, not structure."""
    inline = "1. Alpha\n\nSome prose runs on and then\n2. Beta appears mid-paragraph\n\nMore.\n"
    assert set(_paths(inline, counter)) == {None}


def test_a_single_heading_is_not_an_outline(counter: TokenCounter) -> None:
    """Clause 7. One candidate is likelier a stray list item than a document structure."""
    assert set(_paths("1. Alpha\n\nBody with no second section.\n", counter)) == {None}


def test_a_heading_may_return_to_an_ancestors_next_sibling(counter: TokenCounter) -> None:
    """Clause 6's third permitted step — 1.1 -> 2 must be legal, or every real outline is
    rejected the moment it climbs back out of a subsection."""
    assert _paths("1. Alpha\n\nA.\n\n1.1. Sub\n\nB.\n\n2. Beta\n\nC.\n", counter) == [
        "1. Alpha",
        "1. Alpha > 1.1. Sub",
        "2. Beta",
    ]


def test_a_skipped_number_rejects_the_document(counter: TokenCounter) -> None:
    """Clause 6 admits +1 only. A jump from 1 to 3 is the signature of matched prose, not a
    document that merely omitted a section."""
    assert set(_paths("1. Alpha\n\nA.\n\n3. Gamma\n\nB.\n", counter)) == {None}


@pytest.mark.parametrize("kind", ["pdf", "code", "markdown"])
def test_the_grammar_runs_for_text_only(counter: TokenCounter, kind: str) -> None:
    """Scope, decided 20260805: `text` only. `markdown` already has a grammar; `pdf` is *disabled
    here, never dismantled*. A PDF whose extracted text happens to look like an outline must be
    chunked exactly as it is today, whatever the manifest says."""
    assert set(_paths(_OUTLINE, counter, kind=kind)) == {None}


def test_the_heading_line_stays_inside_its_own_chunk(counter: TokenCounter) -> None:
    """Same contract `_markdown_blocks` holds: the lexical index only sees chunk text, so a
    heading consumed as pure structure would make its own words unsearchable."""
    chunks = chunk_document(
        _OUTLINE, counter=counter, max_tokens=100, overlap=10, kind="text", headings="numbered"
    )
    assert "1.1. Scope" in chunks[1].text


def test_no_character_is_dropped_when_a_document_is_rejected(counter: TokenCounter) -> None:
    """The fallback must be `_plain_blocks`, not a degraded parse: rejecting an outline may never
    cost content."""
    listy = "Steps:\n\n1. First do this.\n\n2. Then do that.\n\n1. Restarting the count.\n"
    chunks = chunk_document(
        listy, counter=counter, max_tokens=100, overlap=10, kind="text", headings="numbered"
    )
    plain = chunk_document(listy, counter=counter, max_tokens=100, overlap=10, kind="text")
    assert [(c.text, c.char_start, c.char_end) for c in chunks] == [
        (c.text, c.char_start, c.char_end) for c in plain
    ]
