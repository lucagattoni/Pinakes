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
from typing import Protocol

from pinakes.errors import ChunkingError

MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
CODE_SUFFIXES = frozenset({".py", ".js", ".ts", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".sh"})

_ATX_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


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

    def as_row(self) -> tuple[str, int, int, int, str | None]:
        """The tuple `store.replace_chunks` expects."""
        return (self.text, self.char_start, self.char_end, self.token_count, self.heading_path)


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
) -> list[Chunk]:
    """Split one document into chunks, preserving every character in at least one of them."""
    if overlap >= max_tokens:
        raise ChunkingError(
            f"overlap ({overlap}) must be smaller than max_tokens ({max_tokens}).",
            remedy="Otherwise each chunk would contain the whole of the one before it.",
        )
    if not text.strip():
        return []

    blocks = _markdown_blocks(text) if kind == "markdown" else _plain_blocks(text)

    chunks: list[Chunk] = []
    for block in blocks:
        chunks.extend(_fit(block, counter=counter, max_tokens=max_tokens, overlap=overlap))
    return chunks


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
