"""Structural chunking: headings and paragraphs, not blind character windows.

A chunk is the unit that gets embedded, retrieved and quoted back at the user, so its boundaries
decide answer quality more than almost anything else in the pipeline. Two rules from the design
shape this module (docs/DESIGN.md §4.6):

* **Tokens are counted with the embedding model's own tokenizer**, never a word-count guess. The
  counter arrives as a protocol so chunking is testable without downloading weights.
* **Oversize text is split, never trimmed.** A truncated chunk has an unsearchable tail, and nothing
  in the output would reveal it. `assert_chunkable` refuses a `max_tokens` the model cannot honour,
  rather than silently truncating later.

Every chunk records the character span it came from, so a passage can be shown in its source
context, and the heading path it sat under, which is both a filter and a citation.

The invariant the tests hold this module to: **every character of the source lands in at least one
chunk.** Overlap may repeat text; nothing may drop it.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol

from pinakes.errors import ChunkingError

MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
CODE_SUFFIXES = frozenset({".py", ".js", ".ts", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".sh"})
PDF_SUFFIXES = frozenset({".pdf"})

_ATX_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_NUMBERED_HEADING = re.compile(r"^(?P<num>\d+(?:\.\d+)*)\.?[ \t]+(?P<title>\S.*)$")
"""Clause 2 of the numbered-heading predicate. Anchored at column 0 by construction — the pattern
opens on a digit, so any leading whitespace fails it, which *is* clause 1."""

_DOT_LEADER = re.compile(r"\.{3,}")
"""Clause 3. Three or more consecutive dots is a table-of-contents leader. Without this, a ToC's
entries duplicate every real section number and clause 6's no-repeats rule rejects the document."""

_MAX_HEADING_CHARS = 100
"""Clause 4. A heading is a label; a sentence is not. A *shape* bound, not a fitted threshold —
named here rather than inlined because this project has been bitten by an uncalibrated constant."""

_MIN_HEADINGS = 2
"""Clause 7. One candidate is likelier a stray list item than an outline."""


class TokenCounter(Protocol):
    """Counts tokens the way the embedding model does. Implemented by the backends in I7."""

    def count_tokens(self, text: str) -> int: ...


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    char_start: int
    char_end: int
    token_count: int
    heading_path: str | None
    page_start: int | None = None
    page_end: int | None = None
    """1-indexed, `None` for a non-paged source. A chunk may legitimately span two pages — e.g. a
    hyphenated word `join_hyphenation` (extract/layout.py) joined across a page break leaves no
    separator there, so the same blank-line-delimited block this module already finds can straddle
    the boundary with no special-casing; `page_start`/`page_end` just have to say so (I5)."""

    def as_row(self) -> tuple[str, int, int, int, str | None, int | None, int | None]:
        """The tuple `store.replace_chunks` expects."""
        return (
            self.text,
            self.char_start,
            self.char_end,
            self.token_count,
            self.heading_path,
            self.page_start,
            self.page_end,
        )


@dataclass(frozen=True, slots=True)
class Block:
    """A structural unit before token limits are applied: one paragraph under one heading path."""

    text: str
    start: int
    end: int
    heading_path: str | None


def source_type(filename: str) -> str:
    lowered = filename.lower()
    suffix = lowered[lowered.rfind(".") :] if "." in lowered else ""
    if suffix in MARKDOWN_SUFFIXES:
        return "markdown"
    if suffix in CODE_SUFFIXES:
        return "code"
    if suffix in PDF_SUFFIXES:
        return "pdf"
    return "text"


def assert_chunkable(max_tokens: int, *, model_max_tokens: int, special_tokens: int = 2) -> None:
    """Refuse a `max_tokens` the model would have to truncate (§4.6).

    A chunk longer than the model's window is not "mostly indexed": its tail is invisible to search
    and nothing in any output would say so.
    """
    budget = model_max_tokens - special_tokens
    if max_tokens > budget:
        raise ChunkingError(
            f"[chunking] max_tokens = {max_tokens}, but the model can encode {budget} "
            f"({model_max_tokens} minus {special_tokens} special tokens).",
            remedy=(
                f"Lower max_tokens to {budget} or less, or configure a model with a longer window."
            ),
        )


def chunk_document(
    text: str,
    *,
    counter: TokenCounter,
    max_tokens: int,
    overlap: int,
    kind: str = "markdown",
    headings: str = "none",
    page_spans: Sequence[tuple[int, int]] | None = None,
) -> list[Chunk]:
    """Split one document into chunks, preserving every character in at least one of them.

    `page_spans` (I1's `ExtractedText.page_spans`, the same object on a cache hit and a cache
    miss) is consumed only for PDFs: each resulting chunk's `page_start`/`page_end` is looked up
    from it, never used to force an extra split — the existing block/fit machinery already
    produces the right chunk boundaries; this only labels them.

    `headings` is `[chunking] headings` and is **read only when `kind == "text"`**. `markdown`
    already has a grammar; `code` and `pdf` are out of scope by decision, not by oversight — the PDF
    path is *disabled here, never dismantled*, and extending it waits on structure detection strong
    enough to be worth trusting.
    """
    if overlap >= max_tokens:
        raise ChunkingError(
            f"overlap ({overlap}) must be smaller than max_tokens ({max_tokens}).",
            remedy="Otherwise each chunk would contain the whole of the one before it.",
        )
    if not text.strip():
        return []

    if kind == "markdown":
        blocks = _markdown_blocks(text)
    elif kind == "text" and headings == "numbered":
        blocks = _numbered_blocks(text)
    else:
        blocks = _plain_blocks(text)

    chunks: list[Chunk] = []
    for block in blocks:
        chunks.extend(_fit(block, counter=counter, max_tokens=max_tokens, overlap=overlap))

    if page_spans is not None:
        chunks = [_with_pages(chunk, page_spans) for chunk in chunks]
    return chunks


def _with_pages(chunk: Chunk, page_spans: Sequence[tuple[int, int]]) -> Chunk:
    return Chunk(
        text=chunk.text,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        token_count=chunk.token_count,
        heading_path=chunk.heading_path,
        page_start=_page_for(chunk.char_start, page_spans),
        page_end=_page_for(max(chunk.char_start, chunk.char_end - 1), page_spans),
    )


def _page_for(position: int, page_spans: Sequence[tuple[int, int]]) -> int:
    """1-indexed page containing `position` (I8's `path:page` citations). `page_spans` partitions
    the text with no gaps (extract/layout.py's `assemble`), so any position a real chunk can carry
    falls in exactly one span — anything else means the caller passed spans for different text."""
    for index, (start, end) in enumerate(page_spans):
        if start <= position < end:
            return index + 1
    raise RuntimeError(
        f"position {position} falls outside every page span — page_spans does not match this text"
    )


def _markdown_blocks(text: str) -> list[Block]:
    """Paragraphs, carrying — and *including* — the headings they sit under.

    The heading line becomes part of the first block beneath it rather than being consumed as pure
    structure. Two reasons: the lexical index only sees chunk text, so a heading-only word would
    otherwise be unsearchable; and a passage quoted back to the user reads far better with the
    heading it belongs to attached. `heading_path` still carries the hierarchy for filtering.

    Blocks are recorded as offsets and sliced from the source at the end, so `text` is always
    exactly `source[char_start:char_end]` — spans that drift from the document would make every
    citation a guess.
    """
    blocks: list[Block] = []
    headings: list[str] = []
    in_fence = False

    block_start: int | None = None
    block_end = 0
    pending_start: int | None = None  # start of a run of headings not yet attached to a block
    offset = 0

    def flush() -> None:
        nonlocal block_start
        if block_start is None:
            return
        body = text[block_start:block_end].rstrip("\n")
        if body.strip():
            blocks.append(
                Block(
                    text=body,
                    start=block_start,
                    end=block_start + len(body),
                    heading_path=" > ".join(headings) if headings else None,
                )
            )
        block_start = None

    for line in text.splitlines(keepends=True):
        line_start = offset
        offset += len(line)
        stripped = line.rstrip("\n")

        if _FENCE.match(stripped):
            in_fence = not in_fence
            if block_start is None:
                block_start = pending_start if pending_start is not None else line_start
                pending_start = None
            block_end = offset
            continue

        if not in_fence:
            heading = _ATX_HEADING.match(stripped)
            if heading is not None:
                flush()
                level = len(heading.group("hashes"))
                del headings[level - 1 :]
                headings.append(heading.group("title"))
                if pending_start is None:
                    pending_start = line_start
                continue

            if not stripped.strip():
                flush()
                continue

        if block_start is None:
            block_start = pending_start if pending_start is not None else line_start
            pending_start = None
        block_end = offset

    flush()
    return blocks


def _numbered_candidates(text: str) -> list[tuple[int, tuple[int, ...], str]]:
    """Every line passing clauses 1-5, as `(line_start, number, full_heading_text)`.

    Clause 5 — preceded by a blank line, or the first line — is why this walks the document rather
    than filtering lines independently.
    """
    found: list[tuple[int, tuple[int, ...], str]] = []
    offset = 0
    previous_blank = True  # start of document satisfies clause 5

    for line in text.splitlines(keepends=True):
        line_start = offset
        offset += len(line)
        stripped = line.rstrip("\n")

        if not stripped.strip():
            previous_blank = True
            continue

        match = _NUMBERED_HEADING.match(stripped) if previous_blank else None
        previous_blank = False
        if match is None:
            continue

        title = match.group("title").rstrip()
        if _DOT_LEADER.search(title):  # clause 3
            continue
        if len(title) > _MAX_HEADING_CHARS or title[-1] in ".,;:":  # clause 4
            continue

        number = tuple(int(part) for part in match.group("num").split("."))
        found.append((line_start, number, stripped.strip()))

    return found


def _normalise(number: tuple[int, ...]) -> tuple[int, ...]:
    """`(1, 0)` is section 1. Trailing zero components are a numbering *style*, not a depth.

    **Clause 10, added after measuring — like clause 9 and unlike clauses 1-8.** A recurring
    convention numbers top-level sections `1.0`, `2.0`, and mixes the two freely: RFC 2006 runs
    `6` then `7.0`, RFC 2024 runs `1.1` then `2.0`. Without this they read as depth changes that no
    outline walk can accept, and the document is rejected whole.

    A genuine subsection never carries `.0` — subsections start at `.1` — so nothing real is
    conflated by folding it away.
    """
    while len(number) > 1 and number[-1] == 0:
        number = number[:-1]
    return number


def _is_valid_step(previous: tuple[int, ...], current: tuple[int, ...]) -> bool:
    """Clause 6, for one pair: a first child, a sibling increment, or an ancestor's next sibling."""
    if len(current) == len(previous) + 1 and current[:-1] == previous and current[-1] == 1:
        return True  # first child: X -> X.1
    depth = len(current)
    if depth <= len(previous) and current[: depth - 1] == previous[: depth - 1]:
        return current[depth - 1] == previous[depth - 1] + 1  # sibling, or ancestor's next sibling
    return False


def _outline_ok(numbers: Sequence[tuple[int, ...]]) -> bool:
    """Clauses 6 and 7 over the whole document. **A single failure rejects every heading in it.**

    That is the design, not a shortcut. The fallback is `_plain_blocks` — *exactly* the behaviour
    before this grammar existed — so a document this misreads loses nothing it had, and an ordered
    list restarting at `1.` disqualifies its document instead of minting confident nonsense. The
    same judgement the title decision made: a visibly absent value beats a plausible wrong one,
    because a wrong one is harder to notice.

    **§5.3 also states "no number repeats". That is not checked here, because it cannot happen.**
    Every step `_is_valid_step` admits raises the tuple lexicographically — a sibling raises its
    last component, a first child appends to it, and an ancestor's next sibling raises a shallower
    one — so an accepted sequence is strictly increasing and a repeat is unreachable. The first
    draft did check it; **mutation testing found the check could be deleted with no test failing**,
    which is the signature of dead code, not of a missing test. It is gone rather than kept as
    defence in depth: a guard that cannot fire still reads as one, and would invite someone to
    weaken the step rule believing this backs it up.

    **The start-at-1 rule is clause 9, and it was added *after* measuring — recorded as such.**
    §5.3's predicate was written before any corpus was consulted; this clause was not. Measuring 66
    real RFCs found one false positive: RFC 769's command-code list (`56 - SET-UP`, `57 - DATA`,
    `58 - END`) satisfied every clause — consecutive integers, short labels, column 0, blank lines
    around — and produced three headings that are not headings. What separates it from a real
    outline is not its *form*: RFC 2010 numbers real sections `1 - Rationale and Scope`, the
    identical shape. It is where it starts. An outline begins at section 1; a list of opcodes
    begins at 56.

    A different discriminator was tried first and **rejected on the evidence**: "the title must not
    begin with punctuation" also killed the false positive, but took three genuine documents with
    it — `5.1.  /get`, `2.7.3.  "iprev"` and RFC 2010's whole dash-separated outline are all real
    headings. Start-at-1 changes exactly one verdict across the corpus, and it is the wrong one.
    """
    if len(numbers) < _MIN_HEADINGS:
        return False
    walk = [_normalise(number) for number in numbers]
    if walk[0][0] != 1:
        return False
    return all(_is_valid_step(before, after) for before, after in pairwise(walk))


def _numbered_blocks(text: str) -> list[Block]:
    """`_plain_blocks`, but labelled by a numbered outline when the document has one.

    The heading line is *included* in the block beneath it, exactly as `_markdown_blocks` does and
    for the same two reasons: the lexical index only sees chunk text, and a quoted passage reads
    better carrying its own heading. The number stays in the label — unlike Markdown's `#`, which is
    syntax, `1.2` is content you would cite.
    """
    candidates = _numbered_candidates(text)
    if not _outline_ok([number for _, number, _ in candidates]):
        return _plain_blocks(text)

    at_line: dict[int, tuple[tuple[int, ...], str]] = {
        line_start: (number, label) for line_start, number, label in candidates
    }
    blocks: list[Block] = []
    headings: list[str] = []
    block_start: int | None = None
    block_end = 0
    pending_start: int | None = None
    offset = 0

    def flush() -> None:
        nonlocal block_start
        if block_start is None:
            return
        body = text[block_start:block_end].rstrip("\n")
        if body.strip():
            blocks.append(
                Block(
                    text=body,
                    start=block_start,
                    end=block_start + len(body),
                    heading_path=" > ".join(headings) if headings else None,
                )
            )
        block_start = None

    for line in text.splitlines(keepends=True):
        line_start = offset
        offset += len(line)

        heading = at_line.get(line_start)
        if heading is not None:
            flush()
            number, label = heading
            # The *normalised* depth, matching the walk. `2.0` is a top-level section, so reading
            # its raw length would nest it under `1.0` instead of making it a sibling — the walk
            # would accept the document and the hierarchy would still come out wrong.
            depth = len(_normalise(number))
            del headings[depth - 1 :]
            headings.append(label)
            if pending_start is None:
                pending_start = line_start
            continue

        if not line.strip():
            flush()
            continue

        if block_start is None:
            block_start = pending_start if pending_start is not None else line_start
            pending_start = None
        block_end = offset

    flush()
    return blocks


def _plain_blocks(text: str) -> list[Block]:
    """Blank-line separated blocks. No syntax parsing for code in v0.1 — a stated limitation."""
    blocks: list[Block] = []
    block_start: int | None = None
    block_end = 0
    offset = 0

    def flush() -> None:
        nonlocal block_start
        if block_start is None:
            return
        body = text[block_start:block_end].rstrip("\n")
        if body.strip():
            blocks.append(
                Block(text=body, start=block_start, end=block_start + len(body), heading_path=None)
            )
        block_start = None

    for line in text.splitlines(keepends=True):
        line_start = offset
        offset += len(line)
        if not line.strip():
            flush()
            continue
        if block_start is None:
            block_start = line_start
        block_end = offset

    flush()
    return blocks


def _fit(block: Block, *, counter: TokenCounter, max_tokens: int, overlap: int) -> list[Chunk]:
    """Emit one chunk per block, or split an oversize block on sentence-ish boundaries."""
    tokens = counter.count_tokens(block.text)
    if tokens <= max_tokens:
        return [
            Chunk(
                text=block.text,
                char_start=block.start,
                char_end=block.end,
                token_count=tokens,
                heading_path=block.heading_path,
            )
        ]

    pieces = _atomise(_split_points(block.text), counter=counter, max_tokens=max_tokens)
    chunks: list[Chunk] = []
    window: list[tuple[str, int]] = []  # (piece text, offset within block)

    def emit() -> None:
        if not window:
            return
        body = "".join(piece for piece, _ in window)
        start = block.start + window[0][1]
        chunks.append(
            Chunk(
                text=body,
                char_start=start,
                char_end=start + len(body),
                token_count=counter.count_tokens(body),
                heading_path=block.heading_path,
            )
        )

    for piece, position in pieces:
        candidate = [*window, (piece, position)]
        body = "".join(text for text, _ in candidate)
        if window and counter.count_tokens(body) > max_tokens:
            emit()
            carried = _carry_over(window, counter=counter, overlap=overlap)
            # The carry is context, not content: if keeping it would push this chunk past the
            # model's window, drop it. `overlap` close to `max_tokens` otherwise produces chunks
            # larger than the limit — the tail would be truncated at encode time, silently, which
            # is the outcome §4.6 exists to prevent.
            with_carry = "".join(text for text, _ in [*carried, (piece, position)])
            window = (
                [*carried, (piece, position)]
                if (counter.count_tokens(with_carry) <= max_tokens)
                else [(piece, position)]
            )
        else:
            window = candidate
    emit()

    return chunks or [
        Chunk(
            text=block.text,
            char_start=block.start,
            char_end=block.end,
            token_count=tokens,
            heading_path=block.heading_path,
        )
    ]


def _carry_over(
    window: Sequence[tuple[str, int]], *, counter: TokenCounter, overlap: int
) -> list[tuple[str, int]]:
    """Keep the previous chunk's tail, up to `overlap` tokens, so context is not cut mid-idea."""
    if overlap <= 0:
        return []
    carried: list[tuple[str, int]] = []
    for piece, position in reversed(window):
        candidate = [(piece, position), *carried]
        if counter.count_tokens("".join(text for text, _ in candidate)) > overlap:
            break
        carried = candidate
    return carried


def _atomise(
    pieces: list[tuple[str, int]], *, counter: TokenCounter, max_tokens: int
) -> list[tuple[str, int]]:
    """Guarantee no single piece exceeds the limit on its own.

    Sentence splitting does nothing for a paragraph with no punctuation, and a lone oversize piece
    would be emitted whole — quietly producing a chunk the model must truncate, which is the exact
    outcome §4.6 forbids. Fall back to words, then to characters for a single token-dense run.
    """
    resolved: list[tuple[str, int]] = []
    for piece, position in pieces:
        if counter.count_tokens(piece) <= max_tokens:
            resolved.append((piece, position))
            continue

        words = [
            (match.group(0), position + match.start()) for match in re.finditer(r"\S+\s*", piece)
        ]
        if len(words) > 1:
            resolved.extend(_atomise(words, counter=counter, max_tokens=max_tokens))
            continue

        # One unbroken run (a hash, a base64 blob). Cut it by characters: splitting mid-token is
        # ugly, but it is still every character indexed, where truncation would silently lose them.
        span = max(1, len(piece) // max(1, -(-counter.count_tokens(piece) // max_tokens)))
        resolved.extend(
            (piece[offset : offset + span], position + offset)
            for offset in range(0, len(piece), span)
        )
    return resolved


def _split_points(text: str) -> list[tuple[str, int]]:
    """Break text into sentence-ish pieces, keeping their offsets so spans stay exact.

    Every character belongs to exactly one piece — including the separators — so reassembling the
    pieces reproduces the block. That is what makes the never-drop guarantee checkable.
    """
    pieces: list[tuple[str, int]] = []
    for match in re.finditer(r".*?(?:(?<=[.!?;:])\s+|\n|$)", text, flags=re.S):
        piece = match.group(0)
        if piece:
            # `match.start()`, never a running total: finditer can yield an empty match at the end
            # of the string, and skipping one would desynchronise an accumulator from the source.
            pieces.append((piece, match.start()))
    return pieces or [(text, 0)]
