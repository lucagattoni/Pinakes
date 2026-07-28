"""The paid Claude-vision extractor — the only module in `src/` permitted to import `anthropic`.

Reached only when the manifest says `backend = "claude-vision"`, or when
`pnk sync --extract=claude-vision` does. Every free step runs before any paid one, and every paid
call is reserved before it is made.

**A request is a K-page slice** (`budget.estimate.K`), never a whole document and never a single
page. The unit is a semantic constant hashed into `REQUEST_SHAPE_VERSION`, because the neighbouring
context a page was transcribed with is part of what produced its text.

**Two retry budgets, because there are two kinds of retry, and one constant conflates them.** A
*semantic* budget of `SEMANTIC_CALL_BUDGET` token-billed calls per slice — the first attempt, up to
`SCHEMA_RETRIES` schema retries, one refusal retry, one truncation retry — and, inside each of
those, a *transport* budget of `TRANSPORT_ATTEMPTS` backoff attempts for 429/5xx. One shared counter
would let two early 429s silently consume the schema-retry budget and refuse a legitimate retry, an
outcome no test could tell from a genuine exhaustion.

**Failure classification is about billing, not about HTTP.** Every transport failure declares
whether the call was billed, and that — never a bare `finally` — is what decides void vs.
`unknown outcome` (CLAUDE.md, `budget/ledger.py`):

* **Never billed** (429, 5xx, a 4xx, a connection error *before* any response byte) → **void**,
  releasing the reservation at zero. Without it a handful of transient failures would permanently
  consume a monthly budget in an append-only file.
* **Billable-unknown** (a timeout, a connection error *mid-response*) → the reservation is left
  **unresolved**: the server may have generated and billed. `pnk budget --resolve` is the
  documented way out, and it is deliberately not automatic.

**Nothing here is imported eagerly that a *free* command would pay for.** `anthropic` is imported
inside `AnthropicTransport`, and `pypdfium2` inside the two functions that slice or count pages —
because §4.4 reaches this module on every query, through `fingerprint_inputs`, on installs with no
extras at all.

**The transport is a seam.** `Transport` returns plain mappings, so the recorded-fixture suite
the whole extractor with `anthropic` absent — which is what proves the registry seam rather than
asserting it. `anthropic` is imported lazily, inside `AnthropicTransport`, for the same reason.

**Thinking is explicitly disabled and the response's *string* content is still checked.**
`output_config.format` constrains the response's structure, not what a string contains, so a
`<thinking>` fragment can land inside a page's text and be cached, chunked and cited as extracted
text. A page matching `LEAKED_TAG_PATTERN` is a **schema failure, retried** — never silently
stripped, because stripping would change the extracted text and would then have to enter the
fingerprint.

**Assembly runs the string policy and nothing else** (decision 10). The response is per-page text
with no coordinates, so `layout.py`'s reading-order and running-head stages have nothing to operate
on; fabricating geometry to feed them would be invented data driving a stage that reasons about
position. `normalise()` runs **before** offsets are taken, exactly as `layout.assemble` does it:
ligature expansion turns one codepoint into two or three, and offsets taken first would be out from
the first ligature onward while the spans still tiled perfectly.
"""

import base64
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Final, Protocol, cast

from pinakes.budget.accountant import Accountant
from pinakes.budget.estimate import MAX_TOKENS, TIMESTAMP_FORMAT, K, estimate_document
from pinakes.budget.prices import ModelPrice
from pinakes.errors import ExtractionError, ExtractorMissingError
from pinakes.extract import CLAUDE_VISION, ExtractedText, ExtractionContext
from pinakes.extract.floors import load_floors
from pinakes.extract.quality import text_yield
from pinakes.extract.textpolicy import TEXT_POLICY_VERSION, normalise

#: Bumped whenever the prompt text changes — it is part of what produced a given extraction.
PROMPT_VERSION: Final = 1

#: Bumped whenever the response schema changes shape.
SCHEMA_VERSION: Final = 1

#: Bumped whenever anything about the request's *shape* changes: the slice size, the content-block
#: order, the thinking setting. Never `max_tokens` — see `fingerprint_inputs` below.
REQUEST_SHAPE_VERSION: Final = 1

#: Output ceiling per request, and the raised ceiling one truncated slice is re-asked at. Both are
#: budget knobs, deliberately outside the fingerprint: a slice re-asked at a higher cap yields
#: *more complete* text of the same kind.
MAX_TOKENS_RETRY: Final = 16_000

#: Structured-output effort, pinned together with `THINKING` because the model accepts disabled
#: thinking only at effort `high` or below — changing one without the other 400s.
EFFORT: Final = "low"
THINKING: Final[Mapping[str, str]] = {"type": "disabled"}

#: The limit that can actually bind, checked on the **base64-encoded** slice: base64 inflates by
#: 4/3, so the effective raw ceiling is ~24 MB. The documented 600-page and 100-page per-request
#: limits are deliberately not checked — a request carries at most K = 5 pages, so they sit 120x
#: and 20x above anything a request can contain, and testing an unreachable limit is theatre.
MAX_REQUEST_BYTES: Final = 32 * 1024 * 1024

#: Token-billed calls per slice: one first attempt, up to three schema retries, one refusal retry,
#: one truncation retry.
SEMANTIC_CALL_BUDGET: Final = 6
SCHEMA_RETRIES: Final = 3

#: Backoff attempts for 429/5xx *within* one semantic attempt. Separate counter, on purpose.
TRANSPORT_ATTEMPTS: Final = 2
BACKOFF_SECONDS: Final = (1.0, 4.0)

#: The paid path refuses to spend when fewer than this fraction of pages fall below I3b's fitted
#: text-yield floor. Per page for the measurement, per document for the decision: a 200-page report
#: with eight scanned inserts has a healthy median and still needs the paid path, so a median would
#: be the wrong statistic.
SCANNED_PAGE_FRACTION: Final = 0.10

#: A page whose text carries one of these is a schema failure. Generic on purpose — the vendor's own
#: guidance is that naming thinking tags specifically is measurably less effective.
LEAKED_TAG_PATTERN: Final = re.compile(
    r"<\s*/?\s*(thinking|antml|system|internal)\b", re.IGNORECASE
)

PROMPT: Final = (
    "Transcribe every page of the attached PDF slice, in order, exactly as it appears. "
    "Return one entry per page, with the page's 1-based number within this slice. "
    "Preserve the reading order a human would follow. Do not summarise, do not translate, and do "
    "not add commentary. Do not include internal or system XML tags in the response. "
    "If a page is blank, return an empty string for it."
)

PAGE_SCHEMA: Final[Mapping[str, Any]] = {
    "type": "object",
    "properties": {
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"page": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["page", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["pages"],
    "additionalProperties": False,
}


class Billability(Enum):
    """Whether a failed call cost money — the only question that decides void vs. unknown."""

    NOT_BILLED = "not billed"
    UNKNOWN = "unknown"


class TransportError(ExtractionError):
    """A call that did not return a usable response, classified by what it cost.

    `retryable` is about whether *re-sending* could succeed; `billability` is about what already
    happened. They are independent: a timeout is billable-unknown and not automatically retried,
    while a 429 is not billed and is.

    An `ExtractionError`, and therefore a `PinakesError`, on purpose: `sync` isolates each document
    behind `except (PinakesError, OSError, ValueError)`, so a bare `Exception` here would take the
    whole run down over one PDF — the opposite of the per-document isolation §6.4 promises.
    """

    def __init__(
        self, message: str, *, billability: Billability, retryable: bool, status: int | None = None
    ) -> None:
        super().__init__(
            message,
            remedy=(
                "The document is recorded as a failure; the rest of the corpus is unaffected. "
                "`pnk budget` shows what the attempts cost, and whether any is still unresolved."
            ),
        )
        self.billability = billability
        self.retryable = retryable
        self.status = status


class Transport(Protocol):
    """The seam. Returns plain mappings so recorded fixtures can drive the whole extractor."""

    def create(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def count_tokens(self, request: Mapping[str, Any]) -> int: ...


def build_client_kwargs() -> dict[str, Any]:
    """The client's construction arguments, as a pure function of nothing.

    `max_retries=0` because the SDK's default of 2 silently turns one `messages.create` into up to
    three billed HTTP requests — and a request retried after a timeout can be billed twice for
    generation the server already completed. The accountant owns retry, not the SDK.

    A function rather than a literal at the construction site so an unmarked test can assert it
    with `anthropic` absent: a test that could only inspect a stand-in would be asserting a
    property of itself.
    """
    return {"max_retries": 0}


def build_request(
    *,
    model: str,
    pdf_bytes: bytes,
    pages_in_slice: int,
    max_tokens: int = MAX_TOKENS,
) -> dict[str, Any]:
    """One slice's request.

    The `document` block comes **before** the text block; base64 is newline-free and no beta header
    is sent. `temperature`, `top_p` and `top_k` are never sent — they 400 on this model.
    """
    encoded = base64.standard_b64encode(pdf_bytes).decode("ascii")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise RequestTooLargeError(encoded_bytes=len(encoded), pages=pages_in_slice)
    return {
        "model": model,
        "max_tokens": max_tokens,
        "thinking": dict(THINKING),
        "output_config": {
            "format": {"type": "json_schema", "schema": dict(PAGE_SCHEMA)},
            "effort": EFFORT,
        },
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": encoded,
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    }


class RequestTooLargeError(ExtractionError):
    """A slice whose base64 payload exceeds the per-request limit. Caught by the slicing loop,
    which halves the slice and retries — down to a single page, which is a page failure by name."""

    def __init__(self, *, encoded_bytes: int, pages: int) -> None:
        super().__init__(
            f"a {pages}-page slice encodes to {encoded_bytes:,} bytes, over the "
            f"{MAX_REQUEST_BYTES:,}-byte per-request limit.",
            remedy="Re-save or downsample the pages in that slice; nothing was sent or spent.",
        )
        self.encoded_bytes = encoded_bytes
        self.pages = pages


class SchemaFailureError(Exception):
    """A response that returned but cannot be used: invalid JSON, the wrong number of pages, or a
    leaked internal tag. Retryable within the semantic budget; each retry is billed and reserved."""


@dataclass(frozen=True, slots=True)
class SliceResult:
    pages: tuple[str, ...]
    model: str
    input_tokens: int
    output_tokens: int


@dataclass(slots=True)
class CallTally:
    """What one document's extraction actually cost, for the caller and for the cache's join key."""

    calls: int = 0
    call_ids: list[str] = field(default_factory=list[str])


def _text_blocks(response: Mapping[str, Any]) -> str:
    """The response's text, selected by an explicit `block["type"] == "text"` check.

    The block union is narrowed by *reading the discriminator*, never by asserting a block is the
    variant we hoped for — that check is the whole of rule 7's requirement here. A response
    carrying no text block at all is a schema failure, not a crash.
    """
    content: object = response.get("content")
    if not isinstance(content, list):
        raise SchemaFailureError("response carried no content list")
    parts: list[str] = []
    for block in cast(list[object], content):
        if not isinstance(block, dict):
            continue
        typed = cast(dict[str, object], block)
        if typed.get("type") != "text":
            continue
        text = typed.get("text")
        if isinstance(text, str):
            parts.append(text)
    if not parts:
        raise SchemaFailureError("response carried no text block")
    return "".join(parts)


def parse_pages(response: Mapping[str, Any], *, expected: int) -> tuple[str, ...]:
    """Validate one slice's response into `expected` page strings.

    **The length assertion runs before the positional mapping**, and it is the most important line
    in this module. The response maps to pages positionally, so a 4-element response to a 5-page
    slice would store pages 2-5 under numbers 1-4: spans still tile, the cache entry is still
    written, and the order-free completeness audit cannot see a page shift — every citation for
    that document silently off by one, for good. An array-length constraint in the schema is not
    something to rely on for that.
    """
    raw = _text_blocks(response)
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SchemaFailureError(f"response was not JSON ({exc})") from exc
    if not isinstance(parsed, dict):
        raise SchemaFailureError("response JSON was not an object")
    pages_value = cast(dict[str, object], parsed).get("pages")
    if not isinstance(pages_value, list):
        raise SchemaFailureError("response JSON carried no `pages` array")

    texts: list[str] = []
    for entry in cast(list[object], pages_value):
        if not isinstance(entry, dict):
            raise SchemaFailureError("a `pages` entry was not an object")
        typed = cast(dict[str, object], entry)
        text = typed.get("text")
        if not isinstance(text, str):
            raise SchemaFailureError("a `pages` entry carried no string `text`")
        texts.append(text)

    if len(texts) != expected:
        raise SchemaFailureError(
            f"response carried {len(texts)} page(s) for a {expected}-page slice — refusing to map "
            "positionally, which would shift every page's text and every citation with it"
        )
    for index, text in enumerate(texts):
        if LEAKED_TAG_PATTERN.search(text):
            raise SchemaFailureError(
                f"page {index + 1} of the slice carried an internal tag; retrying rather than "
                "stripping, which would change the extracted text"
            )
    return tuple(texts)


def assemble_pages(page_texts: Sequence[str]) -> ExtractedText:
    """Per-page strings into offset-exact text, `normalise()` first.

    Mirrors `layout.assemble`'s joining exactly — a newline before each non-empty page after the
    first, counted inside *that* page's span — so both backends' spans tile the same way and I3a's
    page-attribution properties hold against either.
    """
    parts: list[str] = []
    position = 0
    spans: list[tuple[int, int]] = []
    for raw in page_texts:
        start = position
        piece = normalise(raw)
        if piece:
            if parts:
                parts.append("\n")
                position += 1
            parts.append(piece)
            position += len(piece)
        spans.append((start, position))
    return ExtractedText(text="".join(parts), page_spans=tuple(spans))


# --- the free pre-checks, which all run before any paid call --------------------------------


@dataclass(frozen=True, slots=True)
class FreeYield:
    """What the *free* backend already got out of this document, per page."""

    pages_total: int
    pages_below_floor: int
    floor: float

    @property
    def scanned_fraction(self) -> float:
        return self.pages_below_floor / self.pages_total if self.pages_total else 0.0

    @property
    def needs_the_paid_path(self) -> bool:
        """At least `SCANNED_PAGE_FRACTION` of pages yielded nothing.

        The floor is per page and the decision is per document, and the aggregation is stated
        rather than left to the reader: a median would be the wrong statistic, because a 200-page
        report with eight scanned inserts has a healthy median and still needs the paid path.
        """
        return self.scanned_fraction >= SCANNED_PAGE_FRACTION


def survey_free_yield(path: Path) -> FreeYield:
    """Run the free extractor and measure each page against I3b's fitted floor.

    Free, and it is the check that stops the most likely way a user loses money by accident:
    paying to re-extract a PDF that already has a perfectly good text layer.
    """
    from pinakes.extract.pdfium import Pypdfium2Extractor

    floors = load_floors()
    extracted = Pypdfium2Extractor().extract(path, ExtractionContext())
    below = 0
    for start, end in extracted.page_spans:
        page_text = extracted.text[start:end]
        if text_yield(page_text, pages=1).numerator < floors.text_yield_floor:
            below += 1
    return FreeYield(
        pages_total=len(extracted.page_spans),
        pages_below_floor=below,
        floor=floors.text_yield_floor,
    )


def check_worth_paying_for(path: Path, *, force: bool) -> FreeYield:
    """Refuse to spend on a document the free path already handles, unless `--force`.

    With **no fitted floor installed this refuses to spend at all** rather than proceeding without
    its guard: a paid path running with its own cost-control check disabled is worse than one that
    does not run.
    """
    survey = survey_free_yield(path)
    if survey.needs_the_paid_path or force:
        return survey
    raise ExtractionError(
        f"{path.name}: the free extractor already reads "
        f"{survey.pages_total - survey.pages_below_floor} of {survey.pages_total} page(s) "
        f"({survey.scanned_fraction:.0%} below the fitted floor of {survey.floor:g} "
        f"non-whitespace characters per page), so a paid extraction would spend money to "
        f"re-read text you already have.",
        remedy=(
            "Run `pnk sync` with the free backend, or pass `--force` if you have a reason to pay "
            "for a re-extraction anyway."
        ),
    )


# --- one billed call, reserved before it is made --------------------------------------------


def _usage(response: Mapping[str, Any]) -> tuple[int, int]:
    raw: object = response.get("usage")
    if not isinstance(raw, dict):
        return 0, 0
    usage = cast(dict[str, object], raw)
    inputs = usage.get("input_tokens")
    outputs = usage.get("output_tokens")
    return (
        inputs if isinstance(inputs, int) else 0,
        outputs if isinstance(outputs, int) else 0,
    )


def actual_cost_usd(response: Mapping[str, Any], *, price: ModelPrice) -> Decimal:
    """What the call really cost, from the response's own usage.

    The reservation is a worst case; **the reconciliation must supersede it with this**, or the
    protocol is a no-op that records the estimate twice and charges every window worst-case
    forever — the reservation stands, nothing corrects it, and `pnk budget` reports an estimate as
    if it were spend.
    """
    input_tokens, output_tokens = _usage(response)
    million = Decimal(1_000_000)
    return (Decimal(input_tokens) / million) * price.input_per_mtok_usd + (
        Decimal(output_tokens) / million
    ) * price.output_per_mtok_usd


def _responded_model(response: Mapping[str, Any]) -> str:
    """The model that actually answered.

    Recorded per slice in `per_page_provenance`, because a future fingerprint naming the model that
    answered — rather than the alias that was asked for — is the stated precondition for ever
    revisiting server-side fallbacks.
    """
    model = response.get("model")
    return model if isinstance(model, str) else ""


def _billed_call(
    *,
    transport: Transport,
    accountant: Accountant,
    request: Mapping[str, Any],
    model: str,
    reserved_eur: Decimal,
    price: ModelPrice,
    tally: CallTally,
    sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any]:
    """One semantic attempt, including its transport backoffs. Every attempt is its own call, its
    own reservation and its own ledger pair — §5 requires reserving before *each* call, and a
    single reservation covering a retry loop is not a cap.

    The transport budget lives here rather than in the caller so a 429 can never consume a schema
    retry: exhausting these attempts raises, and the caller's semantic counter is untouched by the
    attempts that happened inside.
    """
    for attempt in range(TRANSPORT_ATTEMPTS + 1):
        decision = accountant.check_call(reserved_eur)
        if not decision.allowed:
            raise BudgetRefusedError(decision.message or "refused by the budget")
        with accountant.paid_call(model=model, reserved_eur=reserved_eur) as call:
            tally.calls += 1
            tally.call_ids.append(call.call_id)
            try:
                response = transport.create(request)
            except TransportError as exc:
                if exc.billability is Billability.UNKNOWN:
                    # A timeout, or a connection error mid-response. The reservation stays open on
                    # purpose: the server may have generated, and voiding would under-count.
                    call.may_have_billed()
                    raise
                # Not billed: leaving the block without `response_received` voids it, releasing
                # the reservation at zero — which is what stops a run of transient failures from
                # permanently consuming a monthly budget.
                if not exc.retryable or attempt == TRANSPORT_ATTEMPTS:
                    raise
            else:
                call.response_received()
                input_tokens, output_tokens = _usage(response)
                call.reconcile(
                    cost_usd=actual_cost_usd(response, price=price),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                return response
        # Slept outside the block, so the reservation is already closed while waiting rather than
        # holding headroom open for the whole backoff.
        sleep(BACKOFF_SECONDS[attempt])
    raise TransportError(
        "transport attempts exhausted", billability=Billability.NOT_BILLED, retryable=False
    )


class BudgetRefusedError(ExtractionError):
    """The accountant refused the next call, so it was never made."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            remedy=(
                "Raise the named cap in `[budget]`, or wait for the window to roll over. "
                "`pnk budget` shows what has been spent and against which ceiling."
            ),
        )


# --- one slice, with the semantic retry budget -----------------------------------------------


def extract_slice(
    *,
    transport: Transport,
    accountant: Accountant,
    pdf_bytes: bytes,
    pages_in_slice: int,
    model: str,
    reserved_eur: Decimal,
    price: ModelPrice,
    tally: CallTally,
    sleep: Callable[[float], None] = time.sleep,
) -> SliceResult:
    """One K-page slice into per-page strings, retrying within the semantic budget.

    The branch order is load-bearing and is checked in exactly this sequence:

    1. **`refusal` before `content` is read at all** — a pre-output refusal is not billed for
       output, the cheap failure. Retried once, then recorded.
    2. **`model_context_window_exceeded` is hard, with no retry** — at K = 5 it should be
       unreachable, so reaching it means a page constant is wrong, and re-sending an identical
       oversize request only spends again.
    3. **`max_tokens` before schema validation** — a truncated response *is* invalid JSON, and
       without this branch it would be retried identically three times, all paid, all truncating
       at the same place. Re-asked once at `MAX_TOKENS_RETRY` under a fresh reservation.
    4. Schema validation, including the page-count assertion.

    **A retry re-asks the whole slice, never a single page from it.** A page transcribed with
    different neighbours is a different extraction, and mixing the two inside one document is
    exactly the provenance mess the fingerprint exists to prevent.
    """
    max_tokens = MAX_TOKENS
    schema_failures = 0
    refusals = 0
    truncations = 0
    last_error = "no attempt was made"
    # Per *slice*, never document-wide: `tally` accumulates across the whole document, and
    # checking the budget against it would let slice 1's retries silently refuse slice 2 its
    # first attempt.
    calls_before = tally.calls

    while tally.calls - calls_before < SEMANTIC_CALL_BUDGET:
        request = build_request(
            model=model, pdf_bytes=pdf_bytes, pages_in_slice=pages_in_slice, max_tokens=max_tokens
        )
        response = _billed_call(
            transport=transport,
            accountant=accountant,
            request=request,
            model=model,
            reserved_eur=reserved_eur,
            price=price,
            tally=tally,
            sleep=sleep,
        )
        stop_reason = response.get("stop_reason")

        if stop_reason == "refusal":
            refusals += 1
            last_error = "the model refused the request"
            if refusals > 1:
                break
            continue

        if stop_reason == "model_context_window_exceeded":
            raise ExtractionError(
                f"a {pages_in_slice}-page slice exceeded {model}'s context window.",
                remedy=(
                    "This should be unreachable at the shipped slice size — it means the "
                    "per-page token constant is wrong. Retrying an identical oversize request "
                    "would only spend again. Report it as a pinakes defect."
                ),
            )

        if stop_reason == "max_tokens":
            truncations += 1
            last_error = "the response was truncated"
            if truncations > 1:
                break
            max_tokens = MAX_TOKENS_RETRY
            continue

        try:
            pages = parse_pages(response, expected=pages_in_slice)
        except SchemaFailureError as exc:
            schema_failures += 1
            last_error = str(exc)
            if schema_failures > SCHEMA_RETRIES:
                break
            continue

        input_tokens, output_tokens = _usage(response)
        return SliceResult(
            pages=pages,
            model=_responded_model(response),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    raise ExtractionError(
        f"a {pages_in_slice}-page slice could not be extracted after "
        f"{tally.calls - calls_before} call(s): {last_error}.",
        remedy=(
            "The slice is recorded as a page failure; the rest of the document is unaffected. "
            "`pnk budget` shows what the attempts cost."
        ),
    )


# --- the whole document ----------------------------------------------------------------------


def _slice_windows(pages_total: int) -> list[tuple[int, int]]:
    """`[first, last]` inclusive, 0-indexed, K pages each — the last one short if it must be."""
    return [(first, min(first + K - 1, pages_total - 1)) for first in range(0, pages_total, K)]


def _slice_bytes(
    path: Path, first: int, last: int, *, pages_in_slice: int
) -> list[tuple[bytes, int]]:
    """A slice's bytes, halved and retried if the encoded payload is too large.

    Down to a single page; a single page that still exceeds the limit is a page failure naming the
    path and the size. **Reducing K is deliberately not an option** — K is hashed into the
    fingerprint, so a smaller slice would silently be a different extraction.
    """
    from pinakes.extract.pdfium import slice_pages

    # Measured on the base64 payload, which is what the request actually carries: base64 inflates
    # by 4/3, so a raw-bytes check would pass a slice a third too big. `slice_pages` itself never
    # raises `RequestTooLargeError` — only `build_request` does, and by then the call is committed
    # — so the size question is settled here, before anything is built.
    raw = slice_pages(path, first, last)
    if len(base64.standard_b64encode(raw)) <= MAX_REQUEST_BYTES:
        return [(raw, pages_in_slice)]
    if pages_in_slice == 1:
        raise ExtractionError(
            f"{path.name}: page {first + 1} alone encodes to more than "
            f"{MAX_REQUEST_BYTES:,} bytes, so it cannot be sent in any request.",
            remedy="Re-save or downsample that page; it is a single oversized page, not a slice.",
        )
    midpoint = pages_in_slice // 2
    left = _slice_bytes(path, first, first + midpoint - 1, pages_in_slice=midpoint)
    right = _slice_bytes(path, first + midpoint, last, pages_in_slice=pages_in_slice - midpoint)
    return left + right


def extract_document(
    path: Path,
    *,
    transport: Transport,
    accountant: Accountant,
    model: str,
    pages_total: int,
    force: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[ExtractedText, CallTally]:
    """Every free step, then every paid one — in that order, which is the whole design.

    **The whole document is checked before the first call**, not only per call: per-call
    reservation alone bounds each call and nothing else, and a document that will certainly breach
    a window by call 15 should be refused at call 0.
    """
    check_worth_paying_for(path, force=force)

    prices = accountant.prices
    estimate = estimate_document(
        pages=pages_total,
        model=model,
        prices=prices,
        now=datetime.now().strftime(TIMESTAMP_FORMAT),
        max_price_age_days=accountant.manifest.budget.max_price_age_days,
    )
    upfront = accountant.check_document(estimate)
    if not upfront.allowed:
        raise BudgetRefusedError(upfront.message or "refused by the budget")
    # Evaluated **once, against the whole-document estimate** — never per call. A per-call reading
    # against a several-cent slice would prompt dozens of times for one multi-page document, which
    # is how a confirmation becomes something a user learns to hold `y` through.
    if not accountant.confirm_document(upfront, estimate.total_eur):
        raise ExtractionError(
            f"{path.name}: not confirmed, so nothing was spent.",
            remedy="Re-run and answer `y`, or pass `--yes` to authorise the estimate up front.",
        )

    tally = CallTally()
    page_texts: list[str] = []
    provenance: list[Mapping[str, str]] = []
    for first, last in _slice_windows(pages_total):
        pages_in_slice = last - first + 1
        for payload, payload_pages in _slice_bytes(
            path, first, last, pages_in_slice=pages_in_slice
        ):
            result = extract_slice(
                transport=transport,
                accountant=accountant,
                pdf_bytes=payload,
                pages_in_slice=payload_pages,
                model=model,
                reserved_eur=estimate.per_request_eur,
                price=prices.for_model(model),
                tally=tally,
                sleep=sleep,
            )
            page_texts.extend(result.pages)
            provenance.extend(
                {"backend": CLAUDE_VISION, "responded_model": result.model} for _ in result.pages
            )

    assembled = assemble_pages(page_texts)
    return (
        ExtractedText(
            text=assembled.text,
            page_spans=assembled.page_spans,
            per_page_provenance=tuple(provenance),
        ),
        tally,
    )


# --- the real transport, and the registry entry ------------------------------------------------


class AnthropicTransport:
    """The only place `anthropic` is constructed. Imported lazily so the recorded-fixture suite —
    which is unmarked, and must run with the package absent — can import this module at all."""

    def __init__(self, *, timeout: float = 600.0) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised by the `[light]` CI leg
            raise ExtractorMissingError("claude-vision", extra="claude") from exc
        self._anthropic = anthropic
        kwargs = build_client_kwargs()
        self._max_retries = kwargs["max_retries"]
        self._client = anthropic.Anthropic(timeout=timeout, **kwargs)

    @property
    def max_retries(self) -> int:
        """What the constructed client actually carries — the `paid`-marked half of the
        SDK-retry test reads this rather than reaching into a private attribute."""
        return self._max_retries

    def create(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            response = self._client.messages.create(**dict(request))
        except Exception as exc:
            raise self._classify(exc) from exc
        return response.model_dump()

    def count_tokens(self, request: Mapping[str, Any]) -> int:
        payload = {
            key: value for key, value in request.items() if key not in ("max_tokens", "thinking")
        }
        return self._client.messages.count_tokens(**payload).input_tokens

    def _classify(self, exc: Exception) -> TransportError:
        """Map an SDK exception onto the only distinction that matters: did it bill?

        `APIConnectionError` is a *sibling* of `APIStatusError`, not a subclass, and it splits by
        phase: a failure before any response byte never billed and may be retried, while a
        timeout — which the SDK models as its own subclass — is billable-unknown, because the
        server may have generated the response we never saw.
        """
        module = self._anthropic
        if isinstance(exc, module.APITimeoutError):
            return TransportError(
                f"the request timed out: {exc}", billability=Billability.UNKNOWN, retryable=False
            )
        if isinstance(exc, module.APIConnectionError):
            return TransportError(
                f"the connection failed before any response: {exc}",
                billability=Billability.NOT_BILLED,
                retryable=True,
            )
        if isinstance(exc, module.APIStatusError):
            # Read through `getattr` and checked, rather than trusted: the SDK's own type stubs
            # are not resolvable on a `[light]` install, and a status silently arriving as
            # something other than an int would make `>= 500` a comparison against a string.
            raw: object = getattr(exc, "status_code", None)
            status = raw if isinstance(raw, int) else None
            retryable = status is not None and (status == 429 or status >= 500)
            return TransportError(
                f"the API returned {status}: {exc}",
                billability=Billability.NOT_BILLED,
                retryable=retryable,
                status=status,
            )
        return TransportError(
            f"the client failed: {exc}", billability=Billability.UNKNOWN, retryable=False
        )


def fingerprint_inputs() -> Mapping[str, str]:
    """What this backend's extraction depends on — client-free, so §4.4 can hash it on every query.

    Includes the pdfium versions because this backend **does** load pypdfium2, to slice and to
    pre-check the free text yield. Includes `TEXT_POLICY_VERSION` because it runs `normalise()`,
    which changes the text. **Excludes `LAYOUT_VERSION`**, which it genuinely never runs (decision
    15 is what makes that true rather than merely asserted), and **excludes `max_tokens`**, a
    budget knob rather than a semantic one: a slice re-asked at a higher cap yields more complete
    text of the same kind, and hashing it would change the fingerprint mid-run at exactly the
    truncation retry.
    """
    from pinakes.extract import CLAUDE_VISION, installed_version

    return {
        "backend": CLAUDE_VISION,
        "prompt_version": str(PROMPT_VERSION),
        "schema_version": str(SCHEMA_VERSION),
        "request_shape_version": str(REQUEST_SHAPE_VERSION),
        "slice_pages": str(K),
        "text_policy_version": str(TEXT_POLICY_VERSION),
        "pypdfium2_version": installed_version("pypdfium2"),
    }


def default_transport() -> Transport:
    """The one place production builds a transport.

    A module-level factory rather than a constructor call at each site, so a test can replace the
    whole transport for `pnk sync --estimate-only` — which otherwise reaches `AnthropicTransport`
    through two layers of CLI and could only be tested with a real key.
    """
    return AnthropicTransport()


class ClaudeVisionExtractor:
    """The registered `claude-vision` backend.

    `transport` is injectable so the recorded-fixture suite drives the *whole* extractor — every
    branch, every retry, every ledger pair — with `anthropic` absent. That is what proves the
    registry seam rather than asserting it, and it is why nothing here constructs a client until
    a call is actually about to be made.
    """

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractedText:
        accountant = ctx.accountant
        if not isinstance(accountant, Accountant):
            # Not a defensive check — the accountant is what enforces §5's three ceilings, so a
            # paid extraction reaching this point without one would be an unbounded spender. It
            # refuses rather than defaulting to some cap of its own.
            raise ExtractionError(
                f"{path.name}: a paid extraction was requested with no accountant.",
                remedy=(
                    "This is a pinakes defect, not a configuration problem: the paid path may "
                    "only run through `pnk sync`, which builds one. Please report it."
                ),
            )
        if not ctx.model:
            raise ExtractionError(
                f"{path.name}: `[extraction] model` names no model.",
                remedy='Set `model` in the manifest\'s `[extraction]` table, e.g. "claude-opus-5".',
            )
        from pinakes.extract.pdfium import page_count

        extracted, _tally = extract_document(
            path,
            transport=self._transport or default_transport(),
            accountant=accountant,
            model=ctx.model,
            pages_total=page_count(path),
            force=ctx.force,
        )
        return extracted


def estimate_only(
    path: Path, *, transport: Transport, model: str, pages_total: int
) -> tuple[int, int]:
    """Measure the first slice's exact input tokens, and extrapolate the document's request count.

    **A network call, not an offline estimate** — it needs a key, and `--help` says so, because
    "estimate" reads as free. It generates nothing: `count_tokens` bills no output, which is what
    makes it the cheap way to tighten the reservation constant before a real run.
    """
    from pinakes.extract.pdfium import slice_pages

    first, last = _slice_windows(pages_total)[0]
    request = build_request(
        model=model,
        pdf_bytes=slice_pages(path, first, last),
        pages_in_slice=last - first + 1,
    )
    return transport.count_tokens(request), len(_slice_windows(pages_total))
