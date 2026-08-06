"""Chunking: structure is respected, limits are honoured, and no character is ever dropped."""

import pytest

from pinakes.chunk import (
    Chunk,
    TokenCounter,
    assert_chunkable,
    assert_prefix_fits,
    chunk_document,
    embedding_text,
    metadata_prefix,
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


def test_an_outline_must_start_at_section_one(counter: TokenCounter) -> None:
    """Clause 9 — **added after measuring, unlike clauses 1-8**, and the docstring says so.

    RFC 769 lists facsimile command codes as `56 - SET-UP`, `57 - DATA`, `58 - END`: consecutive
    integers, short labels, column 0, blank lines around. Every other clause passes and it produced
    three headings that are not headings. Form cannot separate it from a real outline — RFC 2010
    numbers genuine sections `1 - Rationale and Scope`, the identical shape — but the starting
    number can.
    """
    codes = "Commands:\n\n56 - SET-UP\n\nA block.\n\n57 - DATA\n\nAnother.\n\n58 - END\n\nLast.\n"
    assert set(_paths(codes, counter)) == {None}

    # The same shape starting at 1 is a real outline and must still be read as one.
    sections = "1 - Rationale\n\nA block.\n\n2 - Requirements\n\nAnother.\n"
    assert _paths(sections, counter) == ["1 - Rationale", "2 - Requirements"]


def test_a_top_level_section_may_be_numbered_with_a_trailing_zero(counter: TokenCounter) -> None:
    """Clause 10 — **added after measuring**, like clause 9. A recurring convention numbers
    top-level sections `1.0`, `2.0`, and real documents mix the two freely: RFC 2006 runs `6` then
    `7.0`, RFC 2024 runs `1.1` then `2.0`. Read literally those are depth changes no outline walk
    can accept, and the whole document is rejected."""
    assert _paths("1.0  Overview\n\nA.\n\n2.0  Model\n\nB.\n", counter) == [
        "1.0  Overview",
        "2.0  Model",
    ]

    mixed = "1.  Intro\n\nA.\n\n1.1.  Sub\n\nB.\n\n2.0  Next\n\nC.\n"
    assert _paths(mixed, counter) == ["1.  Intro", "1.  Intro > 1.1.  Sub", "2.0  Next"]


def test_a_genuine_subsection_is_not_confused_with_a_trailing_zero(counter: TokenCounter) -> None:
    """The normalisation is safe only because a real subsection never carries `.0` — they start at
    `.1`. If it folded those away too, `1.1` and `1` would become the same node and the hierarchy
    would collapse."""
    assert _paths("1.  Intro\n\nA.\n\n1.1.  Sub\n\nB.\n", counter) == [
        "1.  Intro",
        "1.  Intro > 1.1.  Sub",
    ]


# --- The metadata prefix, and the refusal that keeps it out of the model's window ----------------
#
# `plans/20260805_1721-metadata-as-retrieval-context.md` § 3, the reserve bullet. Nothing calls
# `assert_prefix_fits` on the indexing path yet — the manifest option that turns injection on
# arrives in 2d — so these tests are the only thing exercising it, deliberately: a refusal shipped
# without a caller and without tests would be a refusal nobody had ever seen fire.


class NewlineCounter:
    """One token per whitespace-separated word, **plus one per newline**.

    `WordCounter` says `"a\n\nb".split()` is two tokens, so a separator costs nothing and a check
    that forgot to measure it would pass. Real tokenizers vary: BERT's WordPiece drops newlines
    entirely, byte-level BPEs give them tokens of their own. This is the one that would catch a
    separator measured with the text instead of with the prefix.
    """

    def count_tokens(self, text: str) -> int:
        return len(text.split()) + text.count("\n")


def _chunk(text: str, counter: TokenCounter, *, headings: str = "numbered") -> list[Chunk]:
    return chunk_document(
        text, counter=counter, max_tokens=100, overlap=10, kind="text", headings=headings
    )


def _fits(
    chunks: list[Chunk],
    counter: TokenCounter,
    *,
    max_tokens: int,
    title: str | None = "HTTP Semantics",
) -> None:
    """`assert_prefix_fits` against a 512-token window, so a test names only what it varies."""
    assert_prefix_fits(
        chunks,
        title=title,
        path="docs/rfc.txt",
        counter=counter,
        max_tokens=max_tokens,
        model_max_tokens=512,
    )


def test_the_prefix_strips_the_section_numbers_the_heading_path_keeps(
    counter: TokenCounter,
) -> None:
    """The decision of 20260806 05:05: `title > heading_path` with section numbers stripped.

    Both halves are asserted together because they are the point — `heading_path` keeps its numbers
    for citation, the prefix drops them for embedding, and a change that quietly unified the two
    forms would satisfy either assertion alone.
    """
    chunks = _chunk(_OUTLINE, counter)

    assert [chunk.heading_path for chunk in chunks] == [
        "1. Introduction",
        "1. Introduction > 1.1. Scope",
        "2. Terminology",
    ]
    assert [chunk.unnumbered_heading_path for chunk in chunks] == [
        "Introduction",
        "Introduction > Scope",
        "Terminology",
    ]
    assert [metadata_prefix(chunk, title="HTTP Semantics") for chunk in chunks] == [
        "HTTP Semantics > Introduction",
        "HTTP Semantics > Introduction > Scope",
        "HTTP Semantics > Terminology",
    ]


def test_the_unnumbered_stack_pops_with_the_numbered_one(counter: TokenCounter) -> None:
    """The two paths are built from one walk and must stay in step through a *shallower* heading.

    `1.1` pushes a second label; `2` must pop it from both stacks. If only the numbered stack were
    truncated, section 2's prefix would still read `Introduction > Scope > Terminology` — a
    hierarchy the document does not have, injected into the embedding as if it did.
    """
    deep = (
        "1. Alpha\n\nA.\n\n"
        "1.1. Beta\n\nB.\n\n"
        "1.1.1. Gamma\n\nC.\n\n"
        "2. Delta\n\nD.\n\n"
        "2.1. Epsilon\n\nE.\n"
    )
    assert [chunk.unnumbered_heading_path for chunk in _chunk(deep, counter)] == [
        "Alpha",
        "Alpha > Beta",
        "Alpha > Beta > Gamma",
        "Delta",
        "Delta > Epsilon",
    ]


def test_a_markdown_heading_keeps_whatever_number_its_author_wrote(
    counter: TokenCounter,
) -> None:
    """Numbers are stripped **by construction, never by re-parsing** — so only the grammar that
    parsed one may remove it. Markdown's `#` is syntax and is already gone; a `1.` an author typed
    into the heading text is content, and a second regex over the joined string would eat it. It
    would also mis-fire on a heading that legitimately begins with a digit, like this one's `404`.
    """
    text = "# 1. Introduction\n\nBody.\n\n# 404 Not Found\n\nMore body.\n"
    chunks = chunk_document(text, counter=counter, max_tokens=100, overlap=10, kind="markdown")

    assert [chunk.heading_path for chunk in chunks] == ["1. Introduction", "404 Not Found"]
    assert [chunk.unnumbered_heading_path for chunk in chunks] == [
        "1. Introduction",
        "404 Not Found",
    ]


def test_either_half_of_the_prefix_stands_alone(counter: TokenCounter) -> None:
    """A document may have a title and no headings, or headings and no title. Both are prefixes;
    only the absence of both is not."""
    unstructured = _chunk("Just a paragraph.\n", counter, headings="none")[0]
    titled = _chunk(_OUTLINE, counter)[0]

    assert metadata_prefix(unstructured, title="A Title") == "A Title"
    assert metadata_prefix(unstructured, title=None) is None
    assert metadata_prefix(titled, title=None) == "Introduction"


def test_a_chunk_with_no_prefix_is_embedded_exactly_as_it_is_today(
    counter: TokenCounter,
) -> None:
    """The two legs of the experiment must differ *only* where the mechanism applies. A document
    with neither a title nor a heading path has no metadata to inject, so its embedded text has to
    be byte-identical to the unprefixed leg's — not `"" + separator + text`, which would change
    every untitled document for nothing."""
    chunk = _chunk("Just a paragraph.\n", counter, headings="none")[0]

    assert embedding_text(chunk, title=None) == chunk.text
    assert embedding_text(chunk, title="A Title") == "A Title\n\nJust a paragraph."


def test_the_reserve_is_measured_against_the_longest_prefix_in_the_document(
    counter: TokenCounter,
) -> None:
    """The boundary from both sides, which is what pins the check to the reserve rather than to
    some smaller number that merely happens to fit.

    `HTTP Semantics > Introduction > Scope` is 6 tokens to `WordCounter` (the `>` are words too),
    and the separator costs it nothing. A `max_tokens` leaving exactly 6 must pass; one leaving 5
    must refuse.
    """
    chunks = _chunk(_OUTLINE, counter)

    _fits(chunks, counter, max_tokens=504)
    with pytest.raises(ChunkingError) as exc_info:
        _fits(chunks, counter, max_tokens=505)
    assert "HTTP Semantics > Introduction > Scope" in exc_info.value.message
    assert "docs/rfc.txt" in exc_info.value.message
    assert "504" in exc_info.value.remedy


def test_the_separator_is_counted_with_the_prefix_not_with_the_text() -> None:
    """Whatever the separator costs has to be inside the reserve. Measured on the text side it
    would be free here and charged at embedding time — the tail of every full chunk truncated by
    exactly the tokens nobody counted."""
    counter = NewlineCounter()
    chunks = _chunk(_OUTLINE, counter)

    # Two newlines on top of the 6-token prefix: the boundary moves by exactly what they cost.
    _fits(chunks, counter, max_tokens=502)
    with pytest.raises(ChunkingError):
        _fits(chunks, counter, max_tokens=503)


def test_a_document_with_nothing_to_inject_is_never_refused(counter: TokenCounter) -> None:
    """No title and no headings means no prefix, so no reserve is needed — the zero-headroom
    default that every existing KB uses must stay usable for such a document."""
    chunks = _chunk("Just a paragraph.\n", counter, headings="none")

    _fits(chunks, counter, max_tokens=510, title=None)


def test_a_prefix_larger_than_the_window_does_not_suggest_a_negative_limit(
    counter: TokenCounter,
) -> None:
    """`budget - longest` is the number to lower `max_tokens` to, and it is only advice while it is
    positive. A title longer than the model's whole window is a different problem and the remedy
    has to say so rather than print `max_tokens = -3`."""
    chunks = _chunk(_OUTLINE, counter)
    with pytest.raises(ChunkingError) as exc_info:
        _fits(
            chunks,
            counter,
            max_tokens=100,
            title=" ".join(f"word{n}" for n in range(600)),
        )
    assert "-" not in exc_info.value.remedy
    assert "shorten its title" in exc_info.value.remedy


def test_page_labelling_preserves_the_unnumbered_path(counter: TokenCounter) -> None:
    """The PDF path rebuilds every chunk to attach page numbers. A field-by-field rebuild there
    would drop whichever field was added last — silently, and only for PDFs, which is the kind of
    gap that survives a green suite."""
    chunks = chunk_document(
        _OUTLINE,
        counter=counter,
        max_tokens=100,
        overlap=10,
        kind="text",
        headings="numbered",
        page_spans=[(0, len(_OUTLINE))],
    )

    assert [chunk.page_start for chunk in chunks] == [1, 1, 1]
    assert [chunk.unnumbered_heading_path for chunk in chunks] == [
        "Introduction",
        "Introduction > Scope",
        "Terminology",
    ]
