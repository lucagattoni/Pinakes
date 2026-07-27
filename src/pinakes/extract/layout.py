"""The free extraction pipeline's structural half: characters to ordered, de-furnished text.

Operates only on the types defined here and in `pinakes.extract` — no PDF library, no filesystem
(`test_layout_is_pure` asserts the import graph). `pdfium.pdf`'s adapter (I3b) is what turns a real
page into `CharSpan`s; everything downstream of that is pure and table-driven, because the densest,
most failure-prone logic in the extraction path — turning a character stream into ordered, readable
text — should be reachable through hand-built fixtures, not only through an end-to-end corpus score.

The pipeline, in order: `blocks_from_chars` (chars -> line-level `Block`s) -> `reading_order`
(column-aware ordering, per page) -> `strip_running_heads` (whole document, needs a fitted
threshold) -> `join_hyphenation` (whole document, can join across a page boundary) -> `assemble`
(offset-exact text with page spans). `textpolicy.normalise()` runs *inside* `assemble`, per block,
before any offset is computed — never the other way around, because it changes length.

`LAYOUT_VERSION` is hashed into the fingerprint of every backend that runs this module: a reading-
order or hyphenation change alters the extracted text as surely as a library upgrade does, and would
otherwise be an invisible cache hit. Bump it by hand whenever the *behaviour* of any function here
changes, not only when their signatures do.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from pinakes.extract import ExtractedText
from pinakes.extract.textpolicy import normalise

LAYOUT_VERSION = 1

_HYPHENS = ("-", "­")
_DIGITS = re.compile(r"\d+")

# Lines on the same line of text land within this many points of each other's baseline — a
# tolerance, not an equality, because two characters on one visual line rarely share one exact y.
_LINE_TOLERANCE = 2.0
# Two characters separated by less than this, on the same line, are the same word-space; more, and
# a space is inserted even if the font's own space glyph did not produce one (rule: geometry
# decides, never which content-stream operator a character happened to arrive in).
_WORD_GAP = 0.4
# A gap at least this wide, between two characters that landed in the same y-band, is two columns
# printed at the same height, not one wide word-space — split into separate Blocks, never joined
# with a single space, or a two-column page reads as one line spanning the full page width.
_BLOCK_SPLIT_GAP = 20.0
# A gap this wide between two clusters of block x0s is a column boundary, not a ragged margin.
_COLUMN_GAP = 20.0


@dataclass(frozen=True, slots=True)
class CharSpan:
    """One character, exactly as `pdfium`'s character-level text API reports it (I3b's job to
    produce; this module never asks pdfium for one — it only ever sees this type)."""

    char: str
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float


@dataclass(frozen=True, slots=True)
class Block:
    """One line-level unit: contiguous text with a bounding box.

    `heading`/`suppressed`/`joins_previous` start `False` and are set by later stages
    (`blocks_from_chars` sets `heading`; `strip_running_heads` sets `suppressed`;
    `join_hyphenation` sets `joins_previous`) — never all at construction, because each is the
    stated output of exactly one function, not a property `blocks_from_chars` could guess at.
    """

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page_index: int
    heading: bool = False
    suppressed: bool = False
    joins_previous: bool = False


@dataclass(frozen=True, slots=True)
class Page:
    blocks: tuple[Block, ...] = ()


type RawPages = tuple[Page, ...]


@dataclass(frozen=True, slots=True)
class RunningHeadResult:
    """`pages` with recurring lines marked `suppressed`, and the denominator behind that mark.

    A threshold ships with its own numerator and denominator so a wrong *T* is visible in the
    result rather than silently eating a real heading or waving through page furniture.
    """

    pages: RawPages
    suppressed: int
    total_pages: int


def blocks_from_chars(chars: Sequence[CharSpan], *, page_index: int = 0) -> list[Block]:
    """Group one page's characters into line-level `Block`s from geometry alone.

    Three passes: cluster characters into lines by baseline proximity (`_LINE_TOLERANCE`); within
    each line, split into runs wherever the gap between consecutive characters reaches
    `_BLOCK_SPLIT_GAP` — two columns printed at the same height are two runs, never one line
    spanning the page; then, within a run, concatenate left to right, inserting a space wherever the
    (smaller) gap exceeds `_WORD_GAP` and the source did not already supply one. Never asks which
    content-stream operator produced a character — a word arriving as two text runs looks identical,
    geometrically, to one arriving as a single run, which is what makes that case free to handle
    correctly rather than a special case to detect.
    """
    if not chars:
        return []

    ordered = sorted(chars, key=lambda c: (-c.y0, c.x0))
    lines: list[list[CharSpan]] = []
    for char in ordered:
        placed = False
        for line in lines:
            if abs(line[0].y0 - char.y0) <= _LINE_TOLERANCE:
                line.append(char)
                placed = True
                break
        if not placed:
            lines.append([char])
    lines.sort(key=lambda line: -max(c.y0 for c in line))

    body_size = _mode_font_size(ordered)
    blocks: list[Block] = []
    for line in lines:
        line_sorted = sorted(line, key=lambda c: c.x0)
        runs: list[list[CharSpan]] = [[line_sorted[0]]]
        for char in line_sorted[1:]:
            if char.x0 - runs[-1][-1].x1 >= _BLOCK_SPLIT_GAP:
                runs.append([char])
            else:
                runs[-1].append(char)
        for run in runs:
            block = _block_from_run(run, page_index=page_index, body_size=body_size)
            if block is not None:
                blocks.append(block)
    return blocks


def _block_from_run(run: Sequence[CharSpan], *, page_index: int, body_size: float) -> Block | None:
    text_parts: list[str] = []
    prev: CharSpan | None = None
    for char in run:
        if prev is not None:
            gap = char.x0 - prev.x1
            if gap > _WORD_GAP and not text_parts[-1].endswith(" ") and char.char != " ":
                text_parts.append(" ")
        text_parts.append(char.char)
        prev = char
    text = "".join(text_parts)
    if not text.strip():
        return None
    line_size = max(c.font_size for c in run)
    return Block(
        text=text,
        x0=min(c.x0 for c in run),
        x1=max(c.x1 for c in run),
        y0=min(c.y0 for c in run),
        y1=max(c.y1 for c in run),
        page_index=page_index,
        heading=line_size > body_size,
    )


def _mode_font_size(chars: Sequence[CharSpan]) -> float:
    counts: dict[float, int] = {}
    for char in chars:
        counts[char.font_size] = counts.get(char.font_size, 0) + 1
    return max(counts, key=lambda size: (counts[size], -size)) if counts else 0.0


def reading_order(page: Page) -> Page:
    """Column-aware ordering: cluster blocks by `x0` gap, then top-to-bottom within each column,
    columns left to right. A single-column page is one cluster and this is a no-op beyond sorting.
    """
    if not page.blocks:
        return page

    by_x = sorted(page.blocks, key=lambda b: b.x0)
    columns: list[list[Block]] = [[by_x[0]]]
    for block in by_x[1:]:
        if block.x0 - columns[-1][-1].x0 > _COLUMN_GAP:
            columns.append([block])
        else:
            columns[-1].append(block)

    ordered: list[Block] = []
    for column in columns:
        ordered.extend(sorted(column, key=lambda b: -b.y0))
    return Page(blocks=tuple(ordered))


def strip_running_heads(pages: RawPages, *, threshold: float) -> RunningHeadResult:
    """Suppress a line recurring, digits normalised, in the same y-band on `>= threshold` of pages.

    *T* arrives as a parameter and is never read from a file here — fitting it against real
    documents is I3b's job, over a corpus with enough pages to give the fit resolution finer than
    "every T in one wide range reproduces the same answer" (docs/RETROSPECTIVES.md, planning v0.2).

    A line must recur on **at least two** pages to count at all, whatever *T* says: on a one-page
    document every line trivially "recurs" on 1 of 1 pages (a fraction of 1.0, above any sane
    threshold), which would suppress the entire page — running is a property of more than one page,
    not an artefact of the fraction's denominator being small.
    """
    total = len(pages)
    if total == 0:
        return RunningHeadResult(pages=pages, suppressed=0, total_pages=0)

    signatures: dict[tuple[int, str], set[int]] = {}
    for page_num, page in enumerate(pages):
        seen_this_page: set[tuple[int, str]] = set()
        for block in page.blocks:
            key = (round(block.y0), _DIGITS.sub("#", block.text.strip()))
            seen_this_page.add(key)
        for key in seen_this_page:
            signatures.setdefault(key, set()).add(page_num)

    running: set[tuple[int, str]] = {
        key
        for key, pages_seen in signatures.items()
        if len(pages_seen) >= 2 and len(pages_seen) / total >= threshold
    }

    suppressed_count = 0
    new_pages: list[Page] = []
    for page in pages:
        new_blocks: list[Block] = []
        for block in page.blocks:
            key = (round(block.y0), _DIGITS.sub("#", block.text.strip()))
            if key in running:
                suppressed_count += 1
                new_blocks.append(
                    Block(
                        text=block.text,
                        x0=block.x0,
                        y0=block.y0,
                        x1=block.x1,
                        y1=block.y1,
                        page_index=block.page_index,
                        heading=block.heading,
                        suppressed=True,
                    )
                )
            else:
                new_blocks.append(block)
        new_pages.append(Page(blocks=tuple(new_blocks)))

    return RunningHeadResult(pages=tuple(new_pages), suppressed=suppressed_count, total_pages=total)


def _trailing_hyphen_stripped(text: str) -> str | None:
    if text and text[-1] in _HYPHENS:
        return text[:-1]
    return None


def join_hyphenation(lines: Sequence[Block]) -> list[Block]:
    """Join a trailing hyphen or U+00AD when the next real content starts lowercase.

    "Next real content" skips transparently over any number of `suppressed` blocks in between — a
    running head is page furniture, invisible to the document's own prose — but stops dead at a
    `heading`: a heading is real content, and a hyphen immediately before one almost certainly ends
    a compound word or a sentence, not a wrapped one. The join can span a page boundary (the two
    `Block`s keep their own `page_index`; `assemble` is what turns `joins_previous` into "no
    separator here" when it builds the final text and its per-page spans).
    """
    result = [
        Block(
            text=b.text,
            x0=b.x0,
            y0=b.y0,
            x1=b.x1,
            y1=b.y1,
            page_index=b.page_index,
            heading=b.heading,
            suppressed=b.suppressed,
            joins_previous=b.joins_previous,
        )
        for b in lines
    ]

    for i, block in enumerate(result):
        if block.suppressed:
            continue
        stripped = _trailing_hyphen_stripped(block.text)
        if stripped is None:
            continue

        j = i + 1
        while j < len(result) and result[j].suppressed:
            j += 1
        if j >= len(result) or result[j].heading:
            continue
        continuation = result[j].text
        if not continuation or not continuation[0].islower():
            continue

        result[i] = Block(
            text=stripped,
            x0=block.x0,
            y0=block.y0,
            x1=block.x1,
            y1=block.y1,
            page_index=block.page_index,
            heading=block.heading,
            suppressed=block.suppressed,
            joins_previous=block.joins_previous,
        )
        result[j] = Block(
            text=result[j].text,
            x0=result[j].x0,
            y0=result[j].y0,
            x1=result[j].x1,
            y1=result[j].y1,
            page_index=result[j].page_index,
            heading=result[j].heading,
            suppressed=result[j].suppressed,
            joins_previous=True,
        )

    return result


def assemble(pages: RawPages, *, running_head_threshold: float) -> ExtractedText:
    """Run the whole free-path pipeline and emit the seam type: reading order, per page, then
    running-head suppression and hyphenation joining over the whole document, then an
    offset-exact concatenation. `normalise()` runs per block, before that block's contribution to
    the final text is ever measured — never on the whole string after positions are already fixed,
    which is exactly backwards given `normalise` changes length (module docstring, `textpolicy.py`).
    """
    ordered_pages = tuple(reading_order(page) for page in pages)
    head_result = strip_running_heads(ordered_pages, threshold=running_head_threshold)
    flat = [block for page in head_result.pages for block in page.blocks]
    joined = join_hyphenation(flat)
    visible = (block for block in joined if not block.suppressed)

    text_parts: list[str] = []
    position = 0
    page_spans: list[tuple[int, int]] = []
    pending = next(visible, None)

    # Walked one page index at a time — never just "the next block's page" — so a page with no
    # blocks at all still gets a real, zero-width span at the point it actually falls in the
    # document, rather than defaulting to whatever `position` happens to be after the loop ends
    # (which, for a page with nothing on it, would wrongly be the very end of the whole document).
    for page_index in range(len(ordered_pages)):
        start = position
        while pending is not None and pending.page_index == page_index:
            piece = normalise(pending.text)
            if not pending.joins_previous and text_parts:
                text_parts.append("\n")
                position += 1
            text_parts.append(piece)
            position += len(piece)
            pending = next(visible, None)
        page_spans.append((start, position))

    text = "".join(text_parts)
    return ExtractedText(text=text, page_spans=tuple(page_spans), per_page_provenance=())
