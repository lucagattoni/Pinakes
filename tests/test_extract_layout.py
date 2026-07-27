"""Table-driven tests for `extract/layout.py` and `extract/textpolicy.py` — pure, no PDF library.

Every `assemble()` case is checked against three properties, not two: join-identity and contiguous
coverage are one property and its own corollary (contiguous non-overlapping spans entail the join
identity), so a table asserting only those two would be the tautological shape this repo already
killed once (`docs/RETROSPECTIVES.md`, I2). Neither says *which page* a span belongs to —
`page_spans = [(0, L), (L, L), (L, L), ...]` satisfies both, and every `page_start` downstream
silently becomes 1. The third, content-anchored property is the one a wrong page number cannot
survive: a sentinel the fixture places on one page, and no other, must fall inside that page's span.
"""

import ast
import inspect
from pathlib import Path

from pinakes.extract import ExtractedText
from pinakes.extract import layout as layout_module
from pinakes.extract import textpolicy as textpolicy_module
from pinakes.extract.layout import (
    LAYOUT_VERSION,
    Block,
    CharSpan,
    Page,
    assemble,
    blocks_from_chars,
    join_hyphenation,
    reading_order,
    strip_running_heads,
)
from pinakes.extract.textpolicy import TEXT_POLICY_VERSION, normalise

LAYOUT_PATH = Path(inspect.getsourcefile(layout_module) or "")
TEXTPOLICY_PATH = Path(inspect.getsourcefile(textpolicy_module) or "")


def mkchar(char: str, x: float, y: float, size: float = 10.0) -> CharSpan:
    return CharSpan(char=char, x0=x, y0=y, x1=x + size * 0.6, y1=y + size, font_size=size)


def word(text: str, *, x: float, y: float, size: float = 10.0, gap: float = 0.0) -> list[CharSpan]:
    """One `CharSpan` per character of `text`, laid out left to right with no inter-char gap."""
    chars: list[CharSpan] = []
    cursor = x
    for ch in text:
        chars.append(mkchar(ch, cursor, y, size))
        cursor += size * 0.6 + gap
    return chars


def assert_extraction_properties(result: ExtractedText, sentinels: dict[int, str]) -> None:
    """The three properties every `assemble()` case must hold, content-anchoring included.

    Every *non-empty* page span must carry a sentinel: a page a fixture forgets to anchor is a page
    whose span could be silently wrong (even off by a whole page) with every property here still
    passing, since join-identity and contiguous coverage don't know or care which page is which. A
    zero-width span — a page with no characters at all
    (`test_assemble_page_with_no_characters_at_all`) — is the one legitimate exception: there is no
    content on such a page for a sentinel to anchor to.
    """
    assert "".join(result.text[s:e] for s, e in result.page_spans) == result.text

    covered = 0
    for start, end in result.page_spans:
        assert start == covered, "page_spans must be contiguous, in page order, with no gaps"
        covered = end
    assert covered == len(result.text)

    non_empty_pages = {i for i, (start, end) in enumerate(result.page_spans) if end > start}
    missing = non_empty_pages - sentinels.keys()
    assert not missing, f"page(s) {missing} have content but no sentinel to anchor them"

    for page_index, sentinel in sentinels.items():
        start, end = result.page_spans[page_index]
        position = result.text.find(sentinel)
        assert position != -1, f"sentinel {sentinel!r} missing from the assembled text"
        assert start <= position < end, (
            f"sentinel {sentinel!r} for page {page_index} fell in span {(start, end)}, "
            f"not where page {page_index} claims to start and end"
        )
        # and it must not appear inside any *other* page's span, or content-anchoring is vacuous
        for other_index, (other_start, other_end) in enumerate(result.page_spans):
            if other_index == page_index:
                continue
            assert not (other_start <= position < other_end), (
                f"sentinel {sentinel!r} also falls inside page {other_index}'s span"
            )


# --------------------------------------------------------------------------------------------
# blocks_from_chars — its own dense table
# --------------------------------------------------------------------------------------------


def test_blocks_from_chars_empty_page() -> None:
    assert blocks_from_chars([]) == []


def test_blocks_from_chars_characters_out_of_reading_order() -> None:
    """The input list is scrambled; the output must still read left to right."""
    in_order = word("Hello", x=0, y=700)
    scrambled = [in_order[2], in_order[0], in_order[4], in_order[1], in_order[3]]
    blocks = blocks_from_chars(scrambled)
    assert [b.text for b in blocks] == ["Hello"]


def test_blocks_from_chars_word_split_across_two_text_runs() -> None:
    """Two adjacent character groups, geometrically contiguous, read as one word — the function
    never asks which content-stream operator produced a character, only where it sits."""
    first_run = word("waf", x=0, y=700)
    second_run = word("fle", x=first_run[-1].x1, y=700)
    blocks = blocks_from_chars([*first_run, *second_run])
    assert [b.text for b in blocks] == ["waffle"]


def test_blocks_from_chars_two_columns_at_the_same_height_stay_separate() -> None:
    """Characters at the same y but far apart in x are two blocks, never one line-spanning block —
    the gap that matters for splitting is the same order of magnitude as a column gap."""
    left = word("AB", x=0, y=700)
    right = word("CD", x=200, y=700)
    blocks = blocks_from_chars([*left, *right])
    assert [b.text for b in blocks] == ["AB", "CD"]


def test_blocks_from_chars_overlapping_bounding_boxes() -> None:
    """Kerning/italic overhang can make adjacent glyphs' boxes overlap; order still follows `x0`."""
    a = CharSpan(char="A", x0=0, y0=700, x1=8, y1=710, font_size=10.0)
    b = CharSpan(char="B", x0=6, y0=700, x1=14, y1=710, font_size=10.0)  # overlaps `a`'s box
    blocks = blocks_from_chars([b, a])
    assert [blk.text for blk in blocks] == ["AB"]


def test_blocks_from_chars_zero_width_character() -> None:
    """A combining mark or a degenerate glyph (`x0 == x1`) must not break position bookkeeping."""
    a = mkchar("a", 0, 700)
    zero_width = CharSpan(char="́", x0=a.x1, y0=700, x1=a.x1, y1=710, font_size=10.0)
    b = mkchar("b", a.x1 + 0.1, 700)
    blocks = blocks_from_chars([a, zero_width, b])
    assert blocks[0].text == "áb"


def test_blocks_from_chars_flags_a_larger_line_as_a_heading() -> None:
    body = word("normal body text", x=0, y=700, size=10.0)
    heading = word("Big Title", x=0, y=740, size=18.0)
    blocks = blocks_from_chars([*body, *heading])
    by_text = {b.text: b.heading for b in blocks}
    assert by_text["normal body text"] is False
    assert by_text["Big Title"] is True


# --------------------------------------------------------------------------------------------
# reading_order
# --------------------------------------------------------------------------------------------


def test_reading_order_single_column_is_top_to_bottom() -> None:
    top = Block(text="first", x0=0, y0=700, x1=40, y1=710, page_index=0)
    bottom = Block(text="second", x0=0, y0=680, x1=40, y1=690, page_index=0)
    ordered = reading_order(Page(blocks=(bottom, top)))
    assert [b.text for b in ordered.blocks] == ["first", "second"]


def test_reading_order_two_columns_left_column_fully_before_right() -> None:
    left_top = Block(text="L1", x0=0, y0=700, x1=40, y1=710, page_index=0)
    left_bottom = Block(text="L2", x0=0, y0=680, x1=40, y1=690, page_index=0)
    right_top = Block(text="R1", x0=300, y0=700, x1=340, y1=710, page_index=0)
    right_bottom = Block(text="R2", x0=300, y0=680, x1=340, y1=690, page_index=0)
    page = Page(blocks=(right_bottom, left_top, right_top, left_bottom))
    ordered = reading_order(page)
    assert [b.text for b in ordered.blocks] == ["L1", "L2", "R1", "R2"]


def test_reading_order_empty_page() -> None:
    assert reading_order(Page(blocks=())).blocks == ()


# --------------------------------------------------------------------------------------------
# strip_running_heads — T is a parameter, never a constant read from a file
# --------------------------------------------------------------------------------------------


_BODY_WORDS = ("archive", "catalogue", "ledger", "folio", "manuscript", "index", "shelf", "volume")


def _paged(*, running_head_on: set[int], total: int) -> tuple[Page, ...]:
    """Body text differs by *word*, not by an embedded digit — text differing only by a digit is
    exactly a running head's own shape, so using it for "definitely not a running head" body
    content would test nothing (the digit-normalisation rule would unify it right back together)."""
    pages: list[Page] = []
    for i in range(total):
        blocks = [
            Block(
                text=f"the {_BODY_WORDS[i % len(_BODY_WORDS)]}",
                x0=0,
                y0=700,
                x1=100,
                y1=710,
                page_index=i,
            )
        ]
        if i in running_head_on:
            blocks.insert(
                0, Block(text=f"Report {i + 1}", x0=0, y0=750, x1=60, y1=760, page_index=i)
            )
        pages.append(Page(blocks=tuple(blocks)))
    return tuple(pages)


def test_strip_running_heads_suppresses_a_line_recurring_above_threshold() -> None:
    pages = _paged(running_head_on={0, 1, 2, 3}, total=5)  # recurs on 4/5 = 0.8
    result = strip_running_heads(pages, threshold=0.6)
    assert result.total_pages == 5
    assert result.suppressed == 4
    for i in range(4):
        head = next(b for b in result.pages[i].blocks if b.text.startswith("Report"))
        assert head.suppressed is True


def test_strip_running_heads_digits_are_normalised_before_comparing() -> None:
    """`Report 1`, `Report 2`, ... must be recognised as *one* recurring signature."""
    pages = _paged(running_head_on={0, 1, 2}, total=3)
    result = strip_running_heads(pages, threshold=0.6)
    assert result.suppressed == 3


def test_strip_running_heads_threshold_is_a_parameter_not_a_constant() -> None:
    """The same data, two different T values, two different answers — T must reach this function
    as an argument (`test_layout_is_pure` separately asserts it is never read from a file)."""
    pages = _paged(running_head_on={0, 1}, total=4)  # recurs on 2/4 = 0.5
    lenient = strip_running_heads(pages, threshold=0.4)
    strict = strip_running_heads(pages, threshold=0.6)
    assert lenient.suppressed == 2
    assert strict.suppressed == 0


def test_strip_running_heads_below_threshold_is_untouched() -> None:
    pages = _paged(running_head_on={0}, total=5)  # recurs on 1/5 = 0.2
    result = strip_running_heads(pages, threshold=0.6)
    assert result.suppressed == 0
    for page in result.pages:
        assert all(not b.suppressed for b in page.blocks)


def test_strip_running_heads_empty_document() -> None:
    result = strip_running_heads((), threshold=0.6)
    assert result.total_pages == 0
    assert result.suppressed == 0


# --------------------------------------------------------------------------------------------
# join_hyphenation
# --------------------------------------------------------------------------------------------


def _line(
    text: str, *, page_index: int = 0, heading: bool = False, suppressed: bool = False
) -> Block:
    return Block(
        text=text,
        x0=0,
        y0=700,
        x1=100,
        y1=710,
        page_index=page_index,
        heading=heading,
        suppressed=suppressed,
    )


def test_join_hyphenation_ordinary_hyphen_joins_a_lowercase_continuation() -> None:
    lines = [_line("cata-"), _line("logue entry.")]
    joined = join_hyphenation(lines)
    assert [b.text for b in joined] == ["cata", "logue entry."]
    assert joined[1].joins_previous is True


def test_join_hyphenation_soft_hyphen_joins_too() -> None:
    lines = [_line("archi­"), _line("val record.")]
    joined = join_hyphenation(lines)
    assert joined[0].text == "archi"
    assert joined[1].joins_previous is True


def test_join_hyphenation_uppercase_continuation_does_not_join() -> None:
    """A hyphen followed by a capitalised line is a new sentence or a dash, not a wrapped word."""
    lines = [_line("The archive closed early-"), _line("Visitors were asked to leave.")]
    joined = join_hyphenation(lines)
    assert joined[0].text == "The archive closed early-"
    assert joined[1].joins_previous is False


def test_join_hyphenation_never_joins_into_a_heading() -> None:
    lines = [_line("co-"), _line("Chapter Two", heading=True)]
    joined = join_hyphenation(lines)
    assert joined[0].text == "co-"
    assert joined[1].joins_previous is False


def test_join_hyphenation_skips_transparently_over_a_suppressed_running_head() -> None:
    """A running head is page furniture — invisible to the join, unlike a heading."""
    lines = [
        _line("conclu-", page_index=0),
        _line("Running Head", page_index=1, suppressed=True),
        _line("sion follows.", page_index=1),
    ]
    joined = join_hyphenation(lines)
    assert joined[0].text == "conclu"
    assert joined[1].joins_previous is False  # the suppressed line itself is not joined into
    assert joined[2].joins_previous is True


def test_join_hyphenation_no_continuation_at_all() -> None:
    lines = [_line("trailing-")]
    joined = join_hyphenation(lines)
    assert joined[0].text == "trailing-"


def test_join_hyphenation_empty_input() -> None:
    assert join_hyphenation([]) == []


# --------------------------------------------------------------------------------------------
# textpolicy.normalise
# --------------------------------------------------------------------------------------------


def test_normalise_expands_all_seven_ligatures() -> None:
    assert normalise("ﬀﬁﬂﬃﬄﬅﬆ") == "fffiflffifflstst"


def test_normalise_composes_nfc() -> None:
    decomposed = "é"  # 'e' + combining acute accent
    assert normalise(decomposed) == "é"  # 'é', precomposed


def test_normalise_collapses_horizontal_whitespace_but_keeps_newlines() -> None:
    assert normalise("a   b\t\tc") == "a b c"
    assert normalise("line one\nline two") == "line one\nline two"


def test_normalise_strips_trailing_line_whitespace() -> None:
    assert normalise("line one   \nline two") == "line one\nline two"


def test_normalise_is_idempotent() -> None:
    text = "The oﬃce sáw it."
    once = normalise(text)
    assert normalise(once) == once


# --------------------------------------------------------------------------------------------
# assemble — the whole pipeline, three properties over every case
# --------------------------------------------------------------------------------------------


def test_assemble_single_page() -> None:
    page = Page(blocks=(_line("Only one line of SENTINEL_A text."),))
    result = assemble((page,), running_head_threshold=0.6)
    assert result.text == "Only one line of SENTINEL_A text."
    assert result.per_page_provenance == ()
    assert_extraction_properties(result, {0: "SENTINEL_A"})


def test_assemble_multiple_pages_no_running_head() -> None:
    pages = (
        Page(blocks=(_line("Page zero SENTINEL_A content.", page_index=0),)),
        Page(blocks=(_line("Page one SENTINEL_B content.", page_index=1),)),
        Page(blocks=(_line("Page two SENTINEL_C content.", page_index=2),)),
    )
    result = assemble(pages, running_head_threshold=0.6)
    assert_extraction_properties(result, {0: "SENTINEL_A", 1: "SENTINEL_B", 2: "SENTINEL_C"})


def test_assemble_suppresses_running_heads_end_to_end() -> None:
    # Sentinels are distinct *words*, never a shared prefix plus a digit: after digit
    # normalisation "SENTINEL_0".."SENTINEL_3" are one recurring signature, exactly a running
    # head's own shape, which would suppress the sentinels along with the genuine running head.
    sentinels = ("SENTINEL_ALPHA", "SENTINEL_BETA", "SENTINEL_GAMMA", "SENTINEL_DELTA")
    pages = tuple(
        Page(
            blocks=(
                Block(text="ARCHIVE REVIEW", x0=0, y0=750, x1=80, y1=760, page_index=i),
                _line(f"This page holds {sentinels[i]}.", page_index=i),
            )
        )
        for i in range(4)
    )
    result = assemble(pages, running_head_threshold=0.6)
    assert "ARCHIVE REVIEW" not in result.text
    assert_extraction_properties(result, dict(enumerate(sentinels)))


def test_assemble_two_column_page_continues_mid_sentence_into_the_right_column() -> None:
    """Compound case: the left column's last line ends without terminal punctuation; the right
    column's first line is the literal continuation of that sentence."""
    left = [
        Block(
            text="The clerk opened the SENTINEL_LEFT ledger and began the",
            x0=0,
            y0=700,
            x1=200,
            y1=710,
            page_index=0,
        ),
        Block(
            text="final entry of the day, noting the shelf mark before",
            x0=0,
            y0=685,
            x1=200,
            y1=695,
            page_index=0,
        ),
    ]
    right = [
        Block(
            text="closing the drawer for the SENTINEL_RIGHT evening.",
            x0=300,
            y0=700,
            x1=500,
            y1=710,
            page_index=0,
        ),
    ]
    page = Page(blocks=tuple(right + left))  # deliberately out of order
    ordered = reading_order(page)
    result = assemble((Page(blocks=ordered.blocks),), running_head_threshold=0.6)
    assert result.text == (
        "The clerk opened the SENTINEL_LEFT ledger and began the\n"
        "final entry of the day, noting the shelf mark before\n"
        "closing the drawer for the SENTINEL_RIGHT evening."
    )
    assert_extraction_properties(result, {0: "SENTINEL_LEFT"})


def test_assemble_running_head_that_is_a_genuine_heading_on_one_page() -> None:
    """Compound case: 'SURVEY REPORT' is an ordinary running head on 4 pages and, coincidentally,
    also this page's own (larger-font) heading on the 5th. Detection is purely positional/frequency
    based, so it is suppressed everywhere alike — a documented trade-off, not a special case."""
    sentinels = (
        "SENTINEL_ALPHA",
        "SENTINEL_BETA",
        "SENTINEL_GAMMA",
        "SENTINEL_DELTA",
        "SENTINEL_EPSILON",
    )
    pages: list[Page] = []
    for i in range(5):
        is_the_odd_page = i == 4
        head = Block(
            text="SURVEY REPORT",
            x0=0,
            y0=750,
            x1=80,
            y1=760 if not is_the_odd_page else 770,
            page_index=i,
        )
        body = _line(f"Body content {sentinels[i]} here.", page_index=i)
        pages.append(Page(blocks=(head, body)))
    result = assemble(tuple(pages), running_head_threshold=0.6)
    assert "SURVEY REPORT" not in result.text
    assert_extraction_properties(result, dict(enumerate(sentinels)))


def test_assemble_hyphenated_word_across_a_page_break_opening_with_a_running_head() -> None:
    """Compound case: page 0 ends mid-word; page 1 opens with a running head (suppressed) and then
    the real continuation. The join must skip the running head, not be blocked by it."""
    p0 = Page(
        blocks=(
            Block(text="Running Head", x0=0, y0=750, x1=60, y1=760, page_index=0),
            _line("This SENTINEL_A page ends with a con-", page_index=0),
        )
    )
    p1 = Page(
        blocks=(
            Block(text="Running Head", x0=0, y0=750, x1=60, y1=760, page_index=1),
            _line("clusion, SENTINEL_B, on the next page.", page_index=1),
        )
    )
    result = assemble((p0, p1), running_head_threshold=0.6)
    assert "Running Head" not in result.text
    assert "a conclusion, SENTINEL_B" in result.text
    assert_extraction_properties(result, {0: "SENTINEL_A", 1: "SENTINEL_B"})


def test_assemble_offsets_are_computed_after_normalise_not_before() -> None:
    """A ligature is one character pre-normalise and two after; the span must reflect the *after*
    length, or every offset past it is out by one — while tiling and join-identity stay unaware."""
    page = Page(blocks=(_line("The oﬃce SENTINEL_A is closed."),))
    result = assemble((page,), running_head_threshold=0.6)
    assert "ﬃ" not in result.text
    assert "office" in result.text
    assert_extraction_properties(result, {0: "SENTINEL_A"})


def test_assemble_empty_document() -> None:
    result = assemble((), running_head_threshold=0.6)
    assert result.text == ""
    assert result.page_spans == ()


def test_assemble_page_with_no_characters_at_all() -> None:
    pages = (
        Page(blocks=()),
        Page(blocks=(_line("SENTINEL_A only page with content", page_index=1),)),
    )
    result = assemble(pages, running_head_threshold=0.6)
    assert result.page_spans[0] == (0, 0)
    assert_extraction_properties(result, {1: "SENTINEL_A"})


# --------------------------------------------------------------------------------------------
# LAYOUT_VERSION / TEXT_POLICY_VERSION exist and are the right type
# --------------------------------------------------------------------------------------------


def test_layout_version_is_a_hand_bumped_int() -> None:
    assert isinstance(LAYOUT_VERSION, int)
    assert LAYOUT_VERSION >= 1


def test_text_policy_version_is_a_hand_bumped_int() -> None:
    assert isinstance(TEXT_POLICY_VERSION, int)
    assert TEXT_POLICY_VERSION >= 1


# --------------------------------------------------------------------------------------------
# Import graph: layout.py imports no PDF library; textpolicy.py imports neither that nor layout.py
# --------------------------------------------------------------------------------------------

_PDF_LIBRARY_MARKERS = ("pypdfium2", "fitz", "pymupdf", "pdfium")
_FILESYSTEM_MARKERS = ("os", "pathlib", "io")


def _imported_names(path: Path) -> set[str]:
    """Every module *and* fully-qualified name this file imports.

    `from X import Y` is recorded as `X.Y`, not only `X` — `from pinakes.extract import layout`
    imports the *name* `layout`, and checking only `node.module` (`"pinakes.extract"`) would let
    it slip straight past a search for `"extract.layout"`, despite being the exact import
    `layout.py` itself already uses for its own dependencies. Bare relative imports (`from . import
    layout`, where `node.module` is `None`) are folded in by name alone, since there is no absolute
    path to qualify them with, and would otherwise be dropped entirely.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}" if node.module else alias.name)
            if node.module:
                names.add(node.module)
    return names


def _imports_module(imports: set[str], module: str) -> bool:
    """True if `imports` names `module` itself or a dotted name/submodule under it.

    Deliberately not a bare substring test: `"io" in name` also matches `typing.Optional` and
    `collections.abc.Iterable` (`...t-i-o-n...`), neither of which touches the filesystem. `os` and
    `io` are common enough as substrings that a future, unrelated import would trip this the moment
    it added a word containing one — matching on the module boundary (`==` or a `"module."` prefix)
    is what `pypdfium2`/`fitz`/`pymupdf`/`pdfium` don't need, since none of them collides with an
    ordinary English word, but `os`/`io`/`pathlib` do.
    """
    return any(name == module or name.startswith(f"{module}.") for name in imports)


def test_layout_is_pure() -> None:
    imports = _imported_names(LAYOUT_PATH)
    for marker in _PDF_LIBRARY_MARKERS:
        assert not any(marker in name for name in imports), f"layout.py imports {marker}"
    for module in _FILESYSTEM_MARKERS:
        assert not _imports_module(imports, module), f"layout.py imports {module}"


def test_textpolicy_is_pure_and_does_not_import_layout() -> None:
    imports = _imported_names(TEXTPOLICY_PATH)
    for marker in _PDF_LIBRARY_MARKERS:
        assert not any(marker in name for name in imports), f"textpolicy.py imports {marker}"
    for module in _FILESYSTEM_MARKERS:
        assert not _imports_module(imports, module), f"textpolicy.py imports {module}"
    assert not any("extract.layout" in name or name == "layout" for name in imports)


def test_imported_names_catches_a_name_import_of_layout() -> None:
    """The exact violation `test_textpolicy_is_pure_and_does_not_import_layout` exists to catch —
    `from pinakes.extract import layout`, the same style `layout.py` itself uses for `ExtractedText`
    — must actually be visible to it, not silently reduced to the enclosing package's name."""
    tmp = LAYOUT_PATH.parent / "__scratch_import_check__.py"
    tmp.write_text("from pinakes.extract import layout\n", encoding="utf-8")
    try:
        imports = _imported_names(tmp)
        assert any("extract.layout" in name or name == "layout" for name in imports)
    finally:
        tmp.unlink()


def test_imports_module_catches_a_real_filesystem_import_but_not_a_lookalike_word() -> None:
    """Proves both directions of the fix at once: `import os` must be caught (the actual violation
    this check exists to find), while `from typing import Optional` — which contains the substring
    `"io"` but touches no filesystem — must not be, or the check would false-positive on ordinary,
    unrelated code the moment it used a word like "Optional" or "collections.abc.Iterable"."""
    assert _imports_module(_imported_names_from_source("import os\n"), "os")
    assert _imports_module(_imported_names_from_source("from os import path\n"), "os")
    assert not _imports_module(_imported_names_from_source("from typing import Optional\n"), "io")


def _imported_names_from_source(source: str) -> set[str]:
    tmp = LAYOUT_PATH.parent / "__scratch_import_check__.py"
    tmp.write_text(source, encoding="utf-8")
    try:
        return _imported_names(tmp)
    finally:
        tmp.unlink()
