"""Estimate a PDF document's worst-case cost under a paid extraction backend (I6a, decision 8).

**A request is a K-page slice, never a whole document and never a single page.** Getting the unit
wrong is the difference between a reservation that bounds a run and one that is wrong by an order
of magnitude in either direction: a whole-document request makes input quadratic and stops fitting
the context window past a few hundred pages; a per-page request loses the neighbouring context a
table or sentence continuing across a page break needs. `K = 5` is a semantic constant, not a
tuning knob — it is hashed into the paid extractor's own request-shape version (I7b), because the
context a page is transcribed with is part of what produced its text.

**Worst case per request** = `(K * page_tokens + prompt_tokens) * input_price + max_tokens *
output_price`, and a document is `ceil(pages / K)` requests. `prompt_tokens` (the instructions plus
the JSON schema) is a measured module constant, not an afterthought a real "worst case" could
silently omit. There is deliberately no cache-write multiplier: the shared prefix (system prompt
plus instructions) is a few hundred tokens against the model's own cache minimum, so it very likely
cannot be cached at all, and even cached it is roughly 1% of a request dominated by page tokens.

**The whole request must also fit the model's documented context window before the first call** —
a check that costs nothing to run and, under the shipped constants, never fires (30,300 tokens
against 1,000,000), but names the exact limit that bounds it rather than letting a real 400 from a
call already in flight be how the limit is discovered.

Money is `Decimal` end to end and never quantised here — quantisation to the cent happens at
exactly one point, when a reservation or reconciliation is written to the ledger (I6b).
"""

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from pinakes.budget.prices import Prices
from pinakes.errors import ContextWindowExceededError, StalePricesError

#: Pages per request. A semantic constant (I7b hashes it into the request-shape version) — never
#: read from configuration, because changing it changes what every cached response actually means.
K: Final = 5

#: Ceiling on one page's input tokens. Derived from the vendor's documented high-resolution page
#: budget (~4,784 visual tokens per rendered page) plus that page's text.
#:
#: **Measured 20260729 03:17 at ~1,574 tokens/page — 3.8x below this ceiling — and deliberately
#: NOT lowered.** The measurement is over the *synthetic* corpus, whose rasters are generated at
#: modest resolution; a real 300-DPI scan of a dense page is exactly the case this ceiling exists
#: to survive, and it is the one case the corpus cannot supply. Lowering a ceiling on
#: unrepresentative data would trade a 3.8x over-reservation — which costs nothing but headroom —
#: for the chance of a reservation that does not cover the call it precedes.
#:
#: The over-reservation is real and worth knowing: on the first live extraction the reservation
#: was 11.5x the reconciled cost ($0.3515 against $0.0306). That is why reconciliation exists.
PAGE_TOKEN_CEILING: Final = 6_000

#: The fixed cost of a request: the instructions, the JSON schema, and the document block's own
#: envelope — everything that does not scale with the page count.
#:
#: **Measured, 20260729 03:17, claude-opus-5.** Fitted as the intercept of
#: `tokens ~ intercept + pages * per_page` over seven `messages.count_tokens` calls across the
#: synthetic corpus (1, 2 and 5-page slices): **571 tokens**. The previous value of 300 was an
#: estimate and understated it by 1.9x — the *unsafe* direction, being the one term of a "worst
#: case" that no page count compensates for. Rounded up to 700: a ceiling below a measurement is
#: not a ceiling.
PROMPT_TOKENS: Final = 700

#: Output ceiling per request. Caps thinking and response text *together* on `claude-opus-5`, so it
#: is the correct and only safe per-request output bound. ~4,000 tokens actually produced per
#: 5-page slice against this leaves 2x headroom, so a truncation retry is rare.
MAX_TOKENS: Final = 8_000

#: The one spelling of a price-table date. `pnk doctor`'s staleness WARN parses `as_of` with it too
#: (I6b), so the warning and the refusal can never disagree about what "30 days old" means.
TIMESTAMP_FORMAT: Final = "%Y%m%d %H:%M"

#: Documented maximum input tokens, by model name. Not a price, so it does not live in
#: `prices.toml` — a model absent here cannot be context-window-checked, which `estimate_document`
#: treats as "nothing to check" rather than a reason to refuse an otherwise-fine estimate.
MAX_INPUT_TOKENS: Final[dict[str, int]] = {
    "claude-opus-5": 1_000_000,
}


@dataclass(frozen=True, slots=True)
class Estimate:
    """A worst-case cost estimate for one document, at the request granularity decision 8 fixes."""

    model: str
    pages_total: int
    pages_estimated: int
    requests: int
    input_tokens_per_request: int
    output_tokens_per_request: int
    input_eur: Decimal
    output_eur: Decimal

    @property
    def total_eur(self) -> Decimal:
        return self.input_eur + self.output_eur

    @property
    def per_request_eur(self) -> Decimal:
        """Every request costs the same under this model (same `K`, same prompt, same
        `max_tokens`) — what `reserve()` checks before each individual call."""
        return self.total_eur / self.requests


def estimate_document(
    *,
    pages: int,
    model: str,
    prices: Prices,
    now: str,
    max_price_age_days: int,
    pages_estimated: int | None = None,
) -> Estimate:
    """Estimate the worst-case cost of extracting `pages` pages of a document with `model`.

    `now` is an explicit `YYYYMMDD HH:MM` string, never read from the wall clock internally —
    staleness is checked against whatever the caller supplies, which is what keeps this function
    pure and deterministic under test. `pages_estimated` defaults to the whole document (`pages`);
    a caller estimating only a remaining slice of a larger document may pass a smaller value, with
    `pages` still naming the document's true total.
    """
    if pages < 1:
        raise ValueError(f"estimate_document: pages={pages} must be >= 1")
    estimated = pages if pages_estimated is None else pages_estimated
    if not 1 <= estimated <= pages:
        raise ValueError(
            f"estimate_document: pages_estimated={estimated} must be between 1 and pages={pages}"
        )

    as_of = datetime.strptime(prices.as_of, TIMESTAMP_FORMAT)
    current = datetime.strptime(now, TIMESTAMP_FORMAT)
    if (current - as_of).days > max_price_age_days:
        raise StalePricesError(as_of=prices.as_of, max_age_days=max_price_age_days)

    model_price = prices.for_model(model)

    request_input_tokens = K * PAGE_TOKEN_CEILING + PROMPT_TOKENS
    max_input = MAX_INPUT_TOKENS.get(model)
    if max_input is not None and request_input_tokens > max_input:
        raise ContextWindowExceededError(
            request_tokens=request_input_tokens, max_input_tokens=max_input, model=model
        )

    requests = math.ceil(estimated / K)
    input_tokens_total = requests * request_input_tokens
    output_tokens_total = requests * MAX_TOKENS

    million = Decimal(1_000_000)
    input_usd = (Decimal(input_tokens_total) / million) * model_price.input_per_mtok_usd
    output_usd = (Decimal(output_tokens_total) / million) * model_price.output_per_mtok_usd

    return Estimate(
        model=model,
        pages_total=pages,
        pages_estimated=estimated,
        requests=requests,
        input_tokens_per_request=request_input_tokens,
        output_tokens_per_request=MAX_TOKENS,
        input_eur=input_usd / prices.usd_per_eur,
        output_eur=output_usd / prices.usd_per_eur,
    )
