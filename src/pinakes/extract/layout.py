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

# Lines on the same line of text land within this many points of each other's *bounding-box*
# bottom — not the baseline itself, and the gap between those two is the reason this is 3.5, not a
# tighter number a hand-built fixture would have suggested. A descender (g, y, q, j, p) genuinely
# extends below the baseline its neighbours sit on: measured against real pdfium extraction across
# every non-scanned fixture in this project's own corpus (not just one), the deepest descender's
# box-bottom sits 2.299 pt below the same line's non-descender characters — a maximum, not a typical
# case. I3a's original 2.0 was tuned only against `test_extract_layout.py`'s hand-built fixtures
# (zero measured descender depth, since `mkchar`/`word` place every character at one shared `y`), so
# it silently split every descender onto its own one-character "line" the first time real font
# geometry reached this function — verified by reproducing it against
# `tests/pdf-corpus/baseline-1p.pdf` before this fix (docs/RETROSPECTIVES.md, I3b). 3.5 clears the
# measured 2.299 pt worst case with margin and stays far under any real line spacing (typically
# >=1.2x font size, i.e. several times this tolerance even for a small font) — a `_LINE_TOLERANCE`
# this size cannot merge two genuinely different lines.
_LINE_TOLERANCE = 3.5
# One shared constant for "this gap is column-sized", used both to split same-line characters into
# separate Blocks (two columns printed at the same height must never read as one line spanning the
# page) and to cluster already-formed Blocks into columns in `reading_order`. Two separately-tuned
# constants that happened to share a value would drift the moment either was fitted against real
# documents without the other noticing — one name, one fit, everywhere it is used.
_COLUMN_GAP = 20.0
# How far apart two running-head candidates' y0 may land and still count as "the same" band. Not
# `round()`: rounding to the nearest point puts a hard wall at every half-integer, so two instances
# of one genuine running head at 750.4 and 750.6 — sub-point rendering jitter, smaller than any real
# layout difference — round to *different* integers and are silently treated as two distinct lines,
# each below the recurrence threshold on its own even though the line is really recurring on every
# page. Tolerance-based clustering (matching `_LINE_TOLERANCE`'s own approach) has no such wall.
_RUNNING_HEAD_Y_TOLERANCE = 3.0


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

    Two passes: cluster characters into lines by baseline proximity (`_LINE_TOLERANCE`); within each
    line, split into runs wherever the gap between consecutive characters reaches `_COLUMN_GAP` —
    two columns printed at the same height are two runs, never one line spanning the page — then
    concatenate each run's characters exactly as the source gives them (`_block_from_run`). Never
    asks which content-stream operator produced a character — a word arriving as two text runs looks
    identical, geometrically, to one arriving as a single run, which is what makes that case free to
    handle correctly rather than a special case to detect.
    """
    if not chars:
        return []

    ordered = sorted(chars, key=lambda c: (-c.y0, c.x0))
    lines: list[list[CharSpan]] = []
    for char in ordered:
        placed = False
        for line in lines:
            # Against *any* existing member, not only the first: a hyphen sits up to 2.365 pt
            # *above* its own line's baseline (vertically centred near x-height, never touching the
            # baseline it separates two words on) while a descender sits up to 2.299 pt *below* it
            # — both maxima measured across every non-scanned fixture in this project's own corpus,
            # a combined ~4.66 pt spread neither `_LINE_TOLERANCE` alone nor a single fixed anchor
            # can bridge if that anchor happens to be whichever of the two outliers the
            # descending-y0 sort visits first. Matching any member works because most characters
            # on a real line of prose sit
            # exactly on the baseline (the majority, by character count) — once one has joined a
            # line, every outlier on either side matches *that* member independently, never needing
            # to match the outlier on the opposite side directly (verified by reproducing this
            # exact failure — a hyphen anchoring line 2 of `baseline-1p.pdf`, its own descenders
            # then falling 4.5pt away from that anchor — before this fix; docs/RETROSPECTIVES.md,
            # I3b).
            if any(abs(existing.y0 - char.y0) <= _LINE_TOLERANCE for existing in line):
                line.append(char)
                placed = True
                break
        if not placed:
            lines.append([char])
    lines.sort(key=lambda line: -max(c.y0 for c in line))

    # One vote per *line*, not per character: a verbose heading's own character count must never
    # be able to out-vote a short body line and become the "body" size itself, which would invert
    # `line_size > body_size` for the heading it describes.
    body_size = _mode_font_size([max(c.font_size for c in line) for line in lines])
    blocks: list[Block] = []
    for line in lines:
        line_sorted = sorted(line, key=lambda c: c.x0)
        runs: list[list[CharSpan]] = [[line_sorted[0]]]
        for char in line_sorted[1:]:
            if char.x0 - runs[-1][-1].x1 >= _COLUMN_GAP:
                runs.append([char])
            else:
                runs[-1].append(char)
        for run in runs:
            block = _block_from_run(run, page_index=page_index, body_size=body_size)
            if block is not None:
                blocks.append(block)
    return blocks


def _block_from_run(run: Sequence[CharSpan], *, page_index: int, body_size: float) -> Block | None:
    """Concatenate a run's characters exactly as the source stream gives them — no gap-inferred
    space insertion.

    I3a's original design inserted a synthetic space wherever the x-gap between two characters
    exceeded a small threshold, reasoning that geometry should decide word breaks rather than
    which content-stream operator a character arrived in. Measured against real pdfium extraction
    (`tests/pdf-corpus`, I3b), that reasoning didn't survive contact with real font metrics:
    ordinary kerned *intra-word* gaps (e.g. between 'g' and 'u' in "catalogue") ran as high as
    1.44 pt at an 11 pt body size, comfortably past any threshold small enough to avoid firing on
    nearly every letter pair, while genuine inter-word gaps measured no larger — the two
    distributions overlap, so no geometric threshold separates them. pdfium's own text extraction
    already emits an explicit `' '` `CharSpan` for every real word-space in this corpus (and in any
    PDF whose content stream places a literal space glyph, which is how most generators — including
    this project's own `pdfwriter.py` — produce text), so word boundaries come from the source
    stream's own characters, never a re-derived gap. A PDF that encodes spacing purely through `TJ`
    positioning with no space glyph at all would run words together under this simpler rule; no
    fixture in this corpus does that, and recovering it reliably needs calibration against real
    documents outside I3b's own corpus, which is exactly the class of fix
    `docs/RETROSPECTIVES.md` flags rather than guesses at.

    `\r`/`\n` characters are dropped, never concatenated: a `Tj` string authored with an embedded
    line break (this corpus's own multi-line fixtures do this) reports that break as a real,
    zero-width `CharSpan` sharing the *first* line's own y0 — geometrically part of the line above,
    not a separator `assemble` should see twice. `assemble` already inserts exactly one `\n` between
    blocks that don't join; keeping a source-embedded one too produced a `"\n\n"` where every other
    block boundary produced one `"\n"`, verified by reproducing it against real pdfium output before
    this fix (docs/RETROSPECTIVES.md, I3b).
    """
    text = "".join(char.char for char in run if char.char not in ("\r", "\n"))
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


def _mode_font_size(sizes: Sequence[float]) -> float:
    """The most common size in `sizes` — one entry per line, so a page's dominant body size is
    decided by how many *lines* are that size, never by how many *characters* are."""
    counts: dict[float, int] = {}
    for size in sizes:
        counts[size] = counts.get(size, 0) + 1
    return max(counts, key=lambda size: (counts[size], -size)) if counts else 0.0


def reading_order(page: Page) -> Page:
    """Column-aware ordering: cluster blocks by `x0` gap, then top-to-bottom within each column,
    columns left to right. A single-column page is one cluster and this is a no-op beyond sorting.

    A block that bridges from its own column's cluster into the *next* column's own territory
    (`_spanning_blocks`) is never a column member, however its `x0` happens to line up: a caption
    spanning two columns shares its `x0` with whichever column starts at the same margin, and
    clustering it by that alone would read it as that column's own last line, immediately after
    the line above it, rather than at its own correct position — after every column above it,
    before every column below. Spanning blocks split the page into Y-ordered sections; each
    section's non-spanning blocks are column-clustered exactly as a page with no spanning blocks
    would be (`_columns_in_order`), and a spanning block is emitted between sections at its own
    position.

    **Not "wide relative to the page," which is not the same thing.** An earlier version of this
    function flagged a block as spanning whenever its own width reached a fixed fraction
    (`_SPANNING_WIDTH_FRACTION`) of the page's total content span — measured against
    `tests/pdf-corpus/two-column-b.pdf`'s own caption (79% of the span) against that page's widest
    genuine column line (42%). That measurement was real, but the fraction it produced was never
    safe in general: a narrow sidebar beside a much wider main column (reproduced independently,
    not hypothetical) put the main column's own lines at 77% of the page's content span with
    nothing actually overlapping the sidebar at all, and the width-fraction check misread every one
    of them as spanning, interleaving the two columns line by line. Bridging into the *next*
    column's own `x0` is the geometric fact the caption case and the sidebar case actually differ
    on — a caption's `x1` reaches past where the right column starts; a wide-but-legitimate
    column's does not, because there is nothing to its own right to reach into
    (docs/RETROSPECTIVES.md, I3b retrospective).
    """
    if len(page.blocks) < 2:
        return page

    spanning = _spanning_blocks(page.blocks)
    if not spanning:
        return Page(blocks=tuple(_columns_in_order(page.blocks)))

    ordered: list[Block] = []
    section: list[Block] = []
    for block in sorted(page.blocks, key=lambda b: -b.y0):
        if block in spanning:
            ordered.extend(_columns_in_order(section))
            section = []
            ordered.append(block)
        else:
            section.append(block)
    ordered.extend(_columns_in_order(section))
    return Page(blocks=tuple(ordered))


def _cluster_by_x0(blocks: Sequence[Block]) -> list[list[Block]]:
    """Group `blocks` into columns by `x0` gap — the clustering step both `_columns_in_order`'s
    final ordering and `_spanning_blocks`' bridging check build on, so the two never disagree
    about where one column ends and the next begins.

    Each candidate is compared against the column's own *start* (`columns[-1][0]`), never its most
    recently added member: comparing to the last-placed block lets a column's accepted range chain
    forward one small step at a time — each step individually under `_COLUMN_GAP`, the total drift
    from the column's start well past it — and, sorted by `x0`, can merge a genuine third column
    into what should be its neighbour's cluster. Sorting by `x0` alone, never `x1`: a block's own
    width has no bearing on which bucket *it* joins or which bucket any *other* block joins, which
    is what makes clustering safe to run before spanning blocks have even been identified.
    """
    by_x = sorted(blocks, key=lambda b: b.x0)
    columns: list[list[Block]] = [[by_x[0]]]
    for block in by_x[1:]:
        if block.x0 - columns[-1][0].x0 >= _COLUMN_GAP:
            columns.append([block])
        else:
            columns[-1].append(block)
    return columns


def _spanning_blocks(blocks: Sequence[Block]) -> set[Block]:
    """Which blocks bridge from their own column's cluster into the very next column's territory.

    A block is spanning if its `x1` reaches at or past the next column's own `x0` — genuinely
    overlapping that column's space, not merely being wide. The last column has no "next" column to
    bridge into, so nothing in it is ever spanning by this test alone (a page whose one real column
    happens to be wide is not, on its own, evidence of anything spanning).
    """
    if len(blocks) < 2:
        return set()
    columns = _cluster_by_x0(blocks)
    if len(columns) < 2:
        return set()
    column_starts = [column[0].x0 for column in columns]
    spanning: set[Block] = set()
    for index, column in enumerate(columns[:-1]):
        next_start = column_starts[index + 1]
        for block in column:
            if block.x1 >= next_start:
                spanning.add(block)
    return spanning


def _columns_in_order(blocks: Sequence[Block]) -> list[Block]:
    """Cluster `blocks` into columns by `x0` gap, then read each column top to bottom, columns left
    to right."""
    if not blocks:
        return []
    ordered: list[Block] = []
    for column in _cluster_by_x0(blocks):
        ordered.extend(sorted(column, key=lambda b: -b.y0))
    return ordered


def block_signatures(
    pages: RawPages,
) -> tuple[dict[tuple[int, str], set[int]], dict[Block, tuple[int, str]]]:
    """Every block's `(y_band, digit-normalised text)` key: which page indices each key appears
    on, and which key each individual block itself resolves to. Exposed on its own so fitting *T*
    (`quality.py`, I3b) uses the exact same notion of "signature" production does, never a second,
    hand-rewritten copy of this logic that could quietly drift from it — and so
    `strip_running_heads` itself only ever computes a block's key once, from the one shared set of
    y-band anchors below, rather than re-deriving it from scratch in a second pass that could
    resolve a different band for the same y0 (`_RUNNING_HEAD_Y_TOLERANCE`'s clustering depends on
    anchor *order*, so re-running it from an empty anchor list a second time is not guaranteed to
    reproduce the first pass's answer).

    One shared set of y-band anchors for the whole document: a given y0 always resolves to the same
    band regardless of which page contributed the anchor, so two pages' otherwise-identical running
    heads compare equal even if the very first instance of that band came from a different page.
    """
    band_anchors: list[float] = []

    def y_band(y0: float) -> int:
        for index, anchor in enumerate(band_anchors):
            if abs(y0 - anchor) <= _RUNNING_HEAD_Y_TOLERANCE:
                return index
        band_anchors.append(y0)
        return len(band_anchors) - 1

    def block_key(block: Block) -> tuple[int, str]:
        return (y_band(block.y0), _DIGITS.sub("#", block.text.strip()))

    signatures: dict[tuple[int, str], set[int]] = {}
    keys_by_block: dict[Block, tuple[int, str]] = {}
    for page_num, page in enumerate(pages):
        seen_this_page: set[tuple[int, str]] = set()
        for block in page.blocks:
            key = block_key(block)
            keys_by_block[block] = key
            seen_this_page.add(key)
        for key in seen_this_page:
            signatures.setdefault(key, set()).add(page_num)
    return signatures, keys_by_block


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

    signatures, keys_by_block = block_signatures(pages)
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
            if keys_by_block[block] in running:
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
    a compound word or a sentence, not a wrapped one. The check runs both ways: a hyphen belonging
    to a heading itself is never a join candidate either, for the same reason a heading is never a
    valid *continuation* — "never join across a heading" means on either side of it. The join can
    span a page boundary (the two `Block`s keep their own `page_index`; `assemble` is what turns
    `joins_previous` into "no separator here" when it builds the final text and its per-page spans).
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
        if block.suppressed or block.heading:
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

    if pending is not None:
        # A block whose `page_index` never matched any page in `range(len(ordered_pages))` — out
        # of range, or the sequence isn't grouped by page — would otherwise be silently dropped
        # from the text with no error at all, not merely mis-spanned: the loop above only ever
        # advances past a page once, so a block for a page number already walked (or never
        # reached) simply falls off the end. That is a caller bug (I3b's future adapter builds
        # `page_index`; this module only consumes it), and it must be loud, never quiet.
        raise RuntimeError(
            f"block for page {pending.page_index} was never placed — pages must be numbered "
            f"0..{len(ordered_pages) - 1} and grouped by page in `pages`"
        )

    text = "".join(text_parts)
    return ExtractedText(text=text, page_spans=tuple(page_spans), per_page_provenance=())
