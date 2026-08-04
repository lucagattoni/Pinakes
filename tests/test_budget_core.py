"""The pure half of the money machinery (I6a): estimation, reservation, ledger-window aggregation.

No test here touches a file or imports `anthropic` — `budget/` itself never does, and the import
graph test at the bottom of this file asserts it stays that way.
"""

import ast
import importlib.resources
import tomllib
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import pinakes.budget.prices as prices_module
from pinakes.budget.estimate import (
    MAX_TOKENS,
    PAGE_TOKEN_CEILING,
    PROMPT_TOKENS,
    K,
    estimate_document,
)
from pinakes.budget.prices import ModelPrice, Prices, load_prices
from pinakes.budget.reserve import Caps, reserve, reserve_document
from pinakes.budget.window import CallRecord, WindowTotals, aggregate
from pinakes.errors import (
    ContextWindowExceededError,
    PricesMissingError,
    StalePricesError,
    UnknownModelPriceError,
)

BUDGET_DIR = Path(__file__).parent.parent / "src" / "pinakes" / "budget"
MODEL = "claude-opus-5"
NOW = "20260728 16:31"


def prices(*, as_of: str = NOW, usd_per_eur: str = "1.08") -> Prices:
    return Prices(
        as_of=as_of,
        usd_per_eur=Decimal(usd_per_eur),
        models={MODEL: ModelPrice(Decimal("5.00"), Decimal("25.00"))},
    )


# --- prices.py -------------------------------------------------------------------------------


def test_prices_are_installed_package_data() -> None:
    """Read through `importlib.resources`, the way an installed copy — not this repo checkout —
    would: a file only present in the source tree is invisible to every installed wheel."""
    text = (
        importlib.resources.files("pinakes.budget")
        .joinpath("prices.toml")
        .read_text(encoding="utf-8")
    )
    data = tomllib.loads(text)
    assert isinstance(data["as_of"], str)
    assert isinstance(data["usd_per_eur"], str)
    Decimal(data["usd_per_eur"])  # must parse as an exact decimal, not raise
    assert "claude-opus-5" in data["models"]


def test_the_committed_prices_toml_loads_and_is_not_stale_against_its_own_as_of() -> None:
    committed = load_prices()
    assert committed.for_model("claude-opus-5").input_per_mtok_usd == Decimal("5.00")
    assert committed.for_model("claude-opus-5").output_per_mtok_usd == Decimal("25.00")


def test_an_unknown_model_names_the_known_ones() -> None:
    with pytest.raises(UnknownModelPriceError) as exc_info:
        prices().for_model("gpt-5")
    assert "claude-opus-5" in exc_info.value.remedy


class _FakeTraversable:
    """The minimum `importlib.resources` `Traversable` surface `load_prices` actually calls."""

    def __init__(self, text: str | None) -> None:
        self._text = text

    def joinpath(self, _name: str) -> "_FakeTraversable":
        return self

    def read_text(self, encoding: str) -> str:
        if self._text is None:
            raise FileNotFoundError("prices.toml")
        return self._text


def _fake_files(text: str | None) -> Callable[[str], _FakeTraversable]:
    def files(_package: str) -> _FakeTraversable:
        return _FakeTraversable(text)

    return files


def test_a_missing_prices_toml_is_a_startup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prices_module.resources, "files", _fake_files(None))
    with pytest.raises(PricesMissingError) as exc_info:
        load_prices()
    assert "missing or unreadable" in exc_info.value.message


def test_a_malformed_prices_toml_is_a_startup_error_not_a_silent_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parse failure must be a named, loud error — never a `Prices` object with a zeroed or
    absent field a caller could silently compute a wrong estimate from."""
    monkeypatch.setattr(prices_module.resources, "files", _fake_files("not valid toml {{{"))
    with pytest.raises(PricesMissingError) as exc_info:
        load_prices()
    assert "malformed" in exc_info.value.message


def test_a_prices_toml_missing_a_required_field_is_a_startup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = 'as_of = "20260728 16:31"\n[models.claude-opus-5]\ninput_per_mtok_usd = "5.00"\n'
    monkeypatch.setattr(prices_module.resources, "files", _fake_files(broken))
    with pytest.raises(PricesMissingError):
        load_prices()  # no usd_per_eur at all


def test_a_prices_toml_with_an_unparsable_decimal_value_is_a_startup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Decimal(str(x))` raises `decimal.InvalidOperation` on a bad value — not the `ValueError`
    `floors.py`'s `float(x)` would raise for the same mistake, since this file parses via `Decimal`
    from the start (module docstring). A one-typo value like a European "5,00" or an unfilled "TBD"
    must still be a named `PricesMissingError`, never a bare `InvalidOperation`."""
    broken = (
        'as_of = "20260728 16:31"\nusd_per_eur = "1.08"\n'
        '[models.claude-opus-5]\ninput_per_mtok_usd = "5,00"\noutput_per_mtok_usd = "25.00"\n'
    )
    monkeypatch.setattr(prices_module.resources, "files", _fake_files(broken))
    with pytest.raises(PricesMissingError) as exc_info:
        load_prices()
    assert "malformed" in exc_info.value.message


def test_a_prices_toml_with_a_wrong_shaped_models_table_is_a_startup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`models` present but not a table (a plausible authoring slip) must not crash with a bare
    `AttributeError` from `.items()` — still a named `PricesMissingError`."""
    broken = 'as_of = "20260728 16:31"\nusd_per_eur = "1.08"\nmodels = "oops"\n'
    monkeypatch.setattr(prices_module.resources, "files", _fake_files(broken))
    with pytest.raises(PricesMissingError) as exc_info:
        load_prices()
    assert "malformed" in exc_info.value.message


# --- estimate.py -------------------------------------------------------------------------------


def test_the_200_page_worked_example_still_reserves_the_right_shape() -> None:
    """`plans/20260727_1543-v0.2.md` worked this at 40 requests and $14.06, with `PROMPT_TOKENS = "
    "300`.

    The plan is a historical record and keeps its number; the constant does not. `PROMPT_TOKENS`
    was **measured** at 571 on 20260729 and raised to 700, so the reservation is now $14.14 — the
    slice count, which is what the example is really about, is unchanged.
    """
    est = estimate_document(pages=200, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    assert est.requests == 40
    assert (est.total_eur * Decimal("1.08")).quantize(Decimal("0.01")) == Decimal("14.14")


def test_a_single_slice_reserves_the_measured_worst_case() -> None:
    """$0.3515 in the plan, $0.3535 since `PROMPT_TOKENS` was measured rather than estimated.

    Worth pinning even though it moved: the first *live* extraction reconciled at $0.0306 against
    this reservation, an 11.5x over-reservation — safe, and the reason reconciliation exists.
    """
    est = estimate_document(pages=5, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    assert est.requests == 1
    assert (est.total_eur * Decimal("1.08")).quantize(Decimal("0.0001")) == Decimal("0.3535")


def test_requests_round_up_for_a_partial_last_slice() -> None:
    """201 pages at K=5 is 41 requests, not 40 — the last one partial, still billed as a full K
    under the worst-case model."""
    est = estimate_document(pages=201, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    assert est.requests == 41


def test_pages_estimated_defaults_to_the_whole_document() -> None:
    est = estimate_document(pages=10, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    assert est.pages_estimated == est.pages_total == 10


def test_a_stale_as_of_refuses_to_estimate_and_names_the_remedy() -> None:
    stale = prices(as_of="20260101 00:00")
    with pytest.raises(StalePricesError) as exc_info:
        estimate_document(pages=5, model=MODEL, prices=stale, now=NOW, max_price_age_days=30)
    assert "Upgrade pinakes" in exc_info.value.remedy


def test_exactly_at_the_max_price_age_boundary_still_estimates() -> None:
    """`max_price_age_days` days old exactly must not refuse — only *older* than that does."""
    as_of = "20260101 00:00"
    now_at_boundary = "20260131 00:00"  # exactly 30 days later
    est = estimate_document(
        pages=5, model=MODEL, prices=prices(as_of=as_of), now=now_at_boundary, max_price_age_days=30
    )
    assert est.requests == 1


@pytest.mark.parametrize("pages", [0, -1])
def test_zero_or_negative_pages_is_rejected(pages: int) -> None:
    """`pages=0` would otherwise divide by zero computing `per_request_eur` (`requests=0`); a
    negative `pages` would silently propagate. Neither is a real document."""
    with pytest.raises(ValueError, match="pages"):
        estimate_document(pages=pages, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)


@pytest.mark.parametrize("pages_estimated", [0, -5, 11])
def test_pages_estimated_outside_one_to_pages_is_rejected(pages_estimated: int) -> None:
    """A negative or zero slice makes no sense, and a slice bigger than the document's own total
    is impossible. Left unchecked, a negative `pages_estimated` produces a *negative* `total_eur`
    — the one direction a budget guard must never move, since it would understate real spend."""
    with pytest.raises(ValueError, match="pages_estimated"):
        estimate_document(
            pages=10,
            model=MODEL,
            prices=prices(),
            now=NOW,
            max_price_age_days=30,
            pages_estimated=pages_estimated,
        )


def test_the_context_window_precheck_names_its_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import pinakes.budget.estimate as estimate_module

    monkeypatch.setitem(estimate_module.MAX_INPUT_TOKENS, MODEL, 100)
    with pytest.raises(ContextWindowExceededError) as exc_info:
        estimate_document(pages=5, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    assert f"{K * PAGE_TOKEN_CEILING + PROMPT_TOKENS:,}" in exc_info.value.message
    assert "100" in exc_info.value.message


def test_an_unrecognised_model_skips_the_context_window_check() -> None:
    """A model with no documented context window entry cannot be checked — silently skipped,
    never a reason to refuse an otherwise-fine estimate (mirrors decision 13's "unrecognised
    backend" tolerance in the extraction-coherence check, I5)."""
    unlisted_prices = Prices(
        as_of=NOW,
        usd_per_eur=Decimal("1.08"),
        models={"some-future-model": ModelPrice(Decimal("1.00"), Decimal("1.00"))},
    )
    est = estimate_document(
        pages=5, model="some-future-model", prices=unlisted_prices, now=NOW, max_price_age_days=30
    )
    assert est.requests == 1


def test_reservation_bounds_every_usage_table() -> None:
    """Hand-written hypothetical *actual* usages for one 5-page request: the worst-case
    reservation must never be below what any of them would really have cost, since a reservation
    that could be exceeded by real usage is not a bound at all."""
    est = estimate_document(pages=5, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    model_price = prices().for_model(MODEL)
    million = Decimal(1_000_000)
    usages = [
        (0, 0),  # a call that produced nothing
        (1_000, 500),  # far below the ceiling
        (25_000, 4_000),  # a typical 5-page slice
        (K * PAGE_TOKEN_CEILING + PROMPT_TOKENS, MAX_TOKENS),  # exactly at the ceiling
    ]
    for input_tokens, output_tokens in usages:
        actual_eur = (
            (Decimal(input_tokens) / million) * model_price.input_per_mtok_usd
            + (Decimal(output_tokens) / million) * model_price.output_per_mtok_usd
        ) / Decimal("1.08")
        assert est.per_request_eur >= actual_eur, (input_tokens, output_tokens)


# --- window.py: aggregation and attribution -----------------------------------------------------

BERLIN = ZoneInfo("Europe/Berlin")


def test_a_pair_straddling_midnight_is_attributed_to_the_start() -> None:
    record = CallRecord(
        reserved_at=datetime(2026, 3, 15, 23, 59, 58, tzinfo=BERLIN), reserved_eur=Decimal("1.00")
    )
    now_next_day = datetime(2026, 3, 16, 0, 0, 3, tzinfo=BERLIN)
    totals = aggregate([record], now=now_next_day, timezone=BERLIN)
    assert totals.day == Decimal("0")  # not counted in the *new* day
    assert totals.month == Decimal("1.00")  # still the same month


def test_a_pair_straddling_a_month_end_is_attributed_to_the_start() -> None:
    record = CallRecord(
        reserved_at=datetime(2026, 3, 31, 22, 0, 0, tzinfo=BERLIN), reserved_eur=Decimal("2.00")
    )
    now_next_month = datetime(2026, 4, 1, 1, 0, 0, tzinfo=BERLIN)
    totals = aggregate([record], now=now_next_month, timezone=BERLIN)
    assert totals.day == Decimal("0")
    assert totals.month == Decimal("0")  # attributed to March, not counted in April's total


def test_a_pair_straddling_a_dst_transition_is_attributed_correctly() -> None:
    """Europe/Berlin springs forward on 2026-03-29 at 02:00 -> 03:00 local. A reservation just
    before the jump and "now" just after must still land in the same calendar day."""
    record = CallRecord(
        reserved_at=datetime(2026, 3, 29, 1, 30, 0, tzinfo=BERLIN), reserved_eur=Decimal("3.00")
    )
    now_after_dst = datetime(2026, 3, 29, 3, 30, 0, tzinfo=BERLIN)
    totals = aggregate([record], now=now_after_dst, timezone=BERLIN)
    assert totals.day == Decimal("3.00")
    assert totals.month == Decimal("3.00")


def test_aggregation_converts_a_differently_zoned_input_before_comparing() -> None:
    """Every test above constructs `reserved_at` and `now` already in the target `timezone`, where
    `astimezone()` is a no-op — mutating either conversion away entirely (`local_now = now`, or
    `local = record.reserved_at`) still passes every one of them. A ledger storing UTC timestamps
    (plausible for I6b) aggregated under `[budget] timezone = "Europe/Berlin"` is the real case this
    guards: 2026-03-15 23:30 UTC is 2026-03-16 00:30 in Berlin — the *next* calendar day locally,
    even though the UTC date is still the 15th."""
    record = CallRecord(
        reserved_at=datetime(2026, 3, 15, 23, 30, 0, tzinfo=UTC), reserved_eur=Decimal("4.00")
    )
    now_utc = datetime(2026, 3, 16, 0, 0, 0, tzinfo=UTC)  # 01:00 in Berlin
    totals = aggregate([record], now=now_utc, timezone=BERLIN)
    assert totals.day == Decimal("4.00")  # same Berlin calendar day (the 16th), not the UTC one
    assert totals.month == Decimal("4.00")


def test_an_unreconciled_reservation_counts_at_its_reserved_amount() -> None:
    record = CallRecord(
        reserved_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=BERLIN), reserved_eur=Decimal("0.50")
    )
    assert record.effective_eur == Decimal("0.50")


def test_a_reconciliation_supersedes_rather_than_adds() -> None:
    record = CallRecord(
        reserved_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=BERLIN),
        reserved_eur=Decimal("0.50"),
        outcome_eur=Decimal("0.30"),
    )
    assert record.effective_eur == Decimal("0.30")  # not 0.80


def test_a_void_closes_a_reservation_at_zero() -> None:
    record = CallRecord(
        reserved_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=BERLIN),
        reserved_eur=Decimal("0.50"),
        outcome_eur=Decimal("0"),
    )
    assert record.effective_eur == Decimal("0")
    totals = aggregate(
        [record], now=datetime(2026, 3, 15, 13, 0, 0, tzinfo=BERLIN), timezone=BERLIN
    )
    assert totals.day == Decimal("0")


def test_the_operation_total_is_supplied_by_the_caller_not_aggregated() -> None:
    """`operation` bounds a single invocation, never the historical ledger — a record from an
    *earlier* operation today must not bleed into a fresh operation's own running total."""
    earlier_today = CallRecord(
        reserved_at=datetime(2026, 3, 15, 9, 0, 0, tzinfo=BERLIN), reserved_eur=Decimal("1.00")
    )
    totals = aggregate(
        [earlier_today],
        now=datetime(2026, 3, 15, 13, 0, 0, tzinfo=BERLIN),
        timezone=BERLIN,
        operation=Decimal("0"),
    )
    assert totals.operation == Decimal("0")
    assert totals.day == Decimal("1.00")


# --- reserve.py: boundary tests for all three windows -------------------------------------------


@pytest.mark.parametrize(
    ("cap_field", "spent_field"),
    [("per_operation_eur", "operation"), ("daily_eur", "day"), ("monthly_eur", "month")],
)
def test_exactly_at_the_cap_proceeds_one_cent_more_does_not(
    cap_field: str, spent_field: str
) -> None:
    cap = Decimal("1.00")
    caps = Caps(
        **{
            "per_operation_eur": Decimal("100"),
            "daily_eur": Decimal("100"),
            "monthly_eur": Decimal("100"),
            cap_field: cap,
        }
    )
    already_spent = Decimal("0.60")
    reserving_to_exactly_the_cap = cap - already_spent  # spent + reserved == cap, exactly
    spent = WindowTotals(
        **{
            "operation": Decimal("0"),
            "day": Decimal("0"),
            "month": Decimal("0"),
            spent_field: already_spent,
        }
    )

    at_boundary = reserve(reserving_to_exactly_the_cap, caps, spent)
    assert at_boundary.allowed, "spent + reserved == cap must proceed"

    one_cent_more = reserve(reserving_to_exactly_the_cap + Decimal("0.01"), caps, spent)
    assert not one_cent_more.allowed, "one cent more than the cap must refuse"
    assert one_cent_more.blocked_by == cap_field


def test_the_operation_cap_passes_but_the_month_cap_does_not() -> None:
    caps = Caps(
        per_operation_eur=Decimal("1.00"), daily_eur=Decimal("10.00"), monthly_eur=Decimal("5.00")
    )
    spent = WindowTotals(operation=Decimal("0"), day=Decimal("0"), month=Decimal("4.90"))
    decision = reserve(Decimal("0.50"), caps, spent)  # fine for operation/day, breaches month
    assert not decision.allowed
    assert decision.blocked_by == "monthly_eur"


def test_when_two_windows_breach_together_the_earlier_one_in_order_is_named() -> None:
    """`reserve()`'s docstring promises checking `per_operation_eur`, then `daily_eur`, then
    `monthly_eur`, and naming "the first window it would breach". Every boundary test above sets
    two of the three caps to a generous 100, so only one window can ever be the true breach —
    this one breaches `daily_eur` *and* `monthly_eur` together and pins down which one wins."""
    caps = Caps(
        per_operation_eur=Decimal("100"), daily_eur=Decimal("1.00"), monthly_eur=Decimal("1.00")
    )
    spent = WindowTotals(operation=Decimal("0"), day=Decimal("0.60"), month=Decimal("0.60"))
    decision = reserve(Decimal("0.50"), caps, spent)  # 1.10 > 1.00 for both day and month
    assert not decision.allowed
    assert decision.blocked_by == "daily_eur"


def test_confirm_threshold_and_hard_cap_are_independent_boundaries() -> None:
    """A request landing exactly at the hard cap must still be allowed (`<=`, not `<`), and must
    still be flagged for confirmation if it clears `confirm_above_eur` — the two thresholds are
    evaluated independently, so a request is never silently refused *instead of* being asked
    about (design pass 3's finding)."""
    est = estimate_document(pages=5, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    caps = Caps(
        per_operation_eur=est.total_eur,  # the cap is exactly the estimate's own total
        daily_eur=Decimal("100"),
        monthly_eur=Decimal("100"),
    )
    zero_spent = WindowTotals(operation=Decimal("0"), day=Decimal("0"), month=Decimal("0"))
    decision = reserve_document(
        est,
        caps,
        zero_spent,
        confirm_above_eur=Decimal("0.01"),  # far below the estimate
    )
    assert decision.allowed  # exactly at the cap, not over it
    assert decision.needs_confirmation


def test_confirm_above_eur_is_a_strict_boundary() -> None:
    """ "Confirm **above**" names a strict `>`: a document landing exactly at the threshold must
    not need confirmation, only one cent over should. Asserted only incidentally by the test
    above until now — this pins down the exact boundary the hard-cap test already gets for `<=`."""
    est = estimate_document(pages=5, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    generous_caps = Caps(
        per_operation_eur=Decimal("100"), daily_eur=Decimal("100"), monthly_eur=Decimal("100")
    )
    zero_spent = WindowTotals(operation=Decimal("0"), day=Decimal("0"), month=Decimal("0"))

    at_the_threshold = reserve_document(
        est, generous_caps, zero_spent, confirm_above_eur=est.total_eur
    )
    assert at_the_threshold.allowed
    assert not at_the_threshold.needs_confirmation, "exactly at the threshold must not confirm"

    one_cent_above = reserve_document(
        est, generous_caps, zero_spent, confirm_above_eur=est.total_eur - Decimal("0.01")
    )
    assert one_cent_above.needs_confirmation


def test_the_refusal_names_all_three_windows() -> None:
    est = estimate_document(pages=5, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    zero_caps = Caps(
        per_operation_eur=Decimal("0"), daily_eur=Decimal("0"), monthly_eur=Decimal("0")
    )
    zero_spent = WindowTotals(operation=Decimal("0"), day=Decimal("0"), month=Decimal("0"))
    decision = reserve_document(est, zero_caps, zero_spent, confirm_above_eur=Decimal("0.01"))
    assert not decision.allowed
    assert decision.message is not None
    assert "per_operation_eur" in decision.message
    assert "daily_eur" in decision.message
    assert "monthly_eur" in decision.message
    assert "[budget]" in decision.message  # the complete manifest edit is printed
    assert "--extract=" in decision.message  # the ongoing-exposure line


def test_a_partial_breach_names_only_the_windows_actually_blocked() -> None:
    """The test above breaches all three windows at once, so it cannot tell "every blocked window
    is named" apart from "every window is always named regardless of whether it's blocked". This
    breaches only `monthly_eur` and asserts the other two are absent from the message — a
    regression reintroducing over-reporting would mislead a user into raising caps they don't
    need to."""
    est = estimate_document(pages=5, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    caps = Caps(
        per_operation_eur=Decimal("100"),
        daily_eur=Decimal("100"),
        monthly_eur=est.total_eur - Decimal("0.01"),  # only this one is breached
    )
    zero_spent = WindowTotals(operation=Decimal("0"), day=Decimal("0"), month=Decimal("0"))
    decision = reserve_document(est, caps, zero_spent, confirm_above_eur=Decimal("0.01"))
    assert not decision.allowed
    assert decision.message is not None
    assert "monthly_eur" in decision.message
    assert "per_operation_eur" not in decision.message
    assert "daily_eur" not in decision.message


def test_a_cap_lowered_below_already_recorded_spend_reads_as_over_not_negative() -> None:
    """A cap can be lowered mid-window (a manifest edit) below what an earlier call in that same
    window already recorded — `headroom` then goes negative. "headroom €-1.00" reads as a typo;
    the message should say the window is already over instead."""
    est = estimate_document(pages=5, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    caps = Caps(
        per_operation_eur=Decimal("100"),
        daily_eur=Decimal("100"),
        monthly_eur=Decimal("1.00"),  # lowered below what's already spent this month
    )
    already_over_cap_spent = WindowTotals(
        operation=Decimal("0"), day=Decimal("0"), month=Decimal("2.00")
    )
    decision = reserve_document(
        est, caps, already_over_cap_spent, confirm_above_eur=Decimal("0.01")
    )
    assert not decision.allowed
    assert decision.message is not None
    assert "over cap" in decision.message
    assert "headroom €-" not in decision.message


def test_an_unaffordable_document_is_refused_before_the_first_call() -> None:
    est = estimate_document(pages=200, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    default_caps = Caps(
        per_operation_eur=Decimal("0.05"), daily_eur=Decimal("1.00"), monthly_eur=Decimal("5.00")
    )
    zero_spent = WindowTotals(operation=Decimal("0"), day=Decimal("0"), month=Decimal("0"))
    decision = reserve_document(est, default_caps, zero_spent, confirm_above_eur=Decimal("0.01"))

    calls_made = 0

    def spy_call() -> None:
        nonlocal calls_made
        calls_made += 1

    if decision.allowed:
        spy_call()  # would run once per request in the real caller; never reached here

    assert calls_made == 0
    assert not decision.allowed
    assert decision.message is not None
    for window in ("per_operation_eur", "daily_eur", "monthly_eur"):
        assert window in decision.message


def test_confirmation_is_once_per_document_not_per_slice() -> None:
    """A 20-page document (4 requests) whose *per-request* cost is well below
    `confirm_above_eur`, but whose *document total* is above it, must still be flagged — the
    check is against the whole-document estimate, never a per-slice reading."""
    est = estimate_document(pages=20, model=MODEL, prices=prices(), now=NOW, max_price_age_days=30)
    assert est.requests == 4
    per_request = est.per_request_eur
    confirm_above = per_request + Decimal("0.01")  # above one slice, below the whole document
    assert est.total_eur > confirm_above  # the whole document clears it...
    assert per_request < confirm_above  # ...even though a single slice would not

    generous_caps = Caps(
        per_operation_eur=Decimal("100"), daily_eur=Decimal("100"), monthly_eur=Decimal("100")
    )
    zero_spent = WindowTotals(operation=Decimal("0"), day=Decimal("0"), month=Decimal("0"))
    decision = reserve_document(est, generous_caps, zero_spent, confirm_above_eur=confirm_above)
    assert decision.allowed
    assert decision.needs_confirmation


# --- import graph: budget/ imports neither anthropic nor anything under extract/ ----------------


def _imported_names(path: Path) -> set[str]:
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
    return any(name == module or name.startswith(f"{module}.") for name in imports)


@pytest.mark.parametrize("path", sorted(BUDGET_DIR.glob("*.py")), ids=lambda p: p.name)
def test_budget_module_is_pure(path: Path) -> None:
    imports = _imported_names(path)
    assert not any("anthropic" in name for name in imports), f"{path.name} imports anthropic"
    assert not _imports_module(imports, "extract"), f"{path.name} imports pinakes.extract"
    assert not _imports_module(imports, "pinakes.extract"), f"{path.name} imports pinakes.extract"
