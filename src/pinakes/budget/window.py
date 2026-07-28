"""Aggregate ledger records into day/month spend totals, in `[budget] timezone` (I6a).

Reading `ledger.jsonl` itself is I6b's job — this module only ever takes an in-memory list, which
is what keeps it pure. `operation` (the running total for the *current* `pnk ask --deep` invocation)
is not aggregated here: it is the caller's own tally of calls it has itself made so far this run,
never a property of the historical ledger.

**How a reservation/reconciliation pair aggregates — the rule a draft of this design never
stated:**

* **A pair is one record, attributed to the *reservation's* timestamp.** A call reserved at
  23:59:58 and reconciled at 00:00:03 belongs entirely to the first day. Attribution never moves.
* **The reconciliation supersedes the reservation's amount in place** — it does not add to it.
* **An unreconciled reservation counts at its reserved amount**, so an in-flight or crashed call
  consumes headroom rather than vanishing.
* **A `void` record (I7b) closes a reservation at zero** — the one escape hatch for a call that
  never billed, without which a handful of transient failures would permanently consume budget.

`CallRecord` already models a pair post-resolution (`outcome=None` for unreconciled,
`outcome=Decimal("0")` for a void, `outcome=<amount>` for a reconciled call) — pairing raw
reservation/reconciliation/void lines by `call_id` is I6b's job, once those lines actually exist.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class CallRecord:
    """One call's outcome, already resolved from its reservation/reconciliation/void lines."""

    reserved_at: datetime
    """Tz-aware. The reservation's own moment — this, and never the outcome's, is what attributes
    the record to a day and a month."""
    reserved_eur: Decimal
    outcome_eur: Decimal | None = None
    """`None` (unreconciled, counts at `reserved_eur`) or the superseding amount (a reconciliation,
    or `Decimal("0")` for a void)."""

    @property
    def effective_eur(self) -> Decimal:
        return self.reserved_eur if self.outcome_eur is None else self.outcome_eur


@dataclass(frozen=True, slots=True)
class WindowTotals:
    """What `reserve()` compares each cap against. `operation` is supplied by the caller — its own
    running tally for the current invocation — never aggregated from the ledger."""

    operation: Decimal
    day: Decimal
    month: Decimal


def in_window(reserved_at: datetime, *, now: datetime, timezone: ZoneInfo) -> tuple[bool, bool]:
    """`(falls in today, falls in this month)` for one reservation moment.

    The attribution rule lives here alone. `aggregate` sums with it and `pnk budget` (I6b) reports
    per-window rates with it, so the totals and the provenance shown beside them can never be
    computed from two different readings of "today".
    """
    local = reserved_at.astimezone(timezone)
    local_now = now.astimezone(timezone)
    return (
        local.date() == local_now.date(),
        (local.year, local.month) == (local_now.year, local_now.month),
    )


def aggregate(
    records: Sequence[CallRecord],
    *,
    now: datetime,
    timezone: ZoneInfo,
    operation: Decimal = Decimal("0"),
) -> WindowTotals:
    """Sum `records`' effective amounts into today's and this month's totals, both computed in
    `timezone` — the same conversion applies to `now` and to every record, so a reservation just
    before midnight and one just after are correctly told apart regardless of what timezone the
    records themselves were constructed in (`reserved_at` need only be tz-aware; it is converted
    here, not assumed to already be in `timezone`).
    """
    day_total = Decimal("0")
    month_total = Decimal("0")
    for record in records:
        today, this_month = in_window(record.reserved_at, now=now, timezone=timezone)
        if today:
            day_total += record.effective_eur
        if this_month:
            month_total += record.effective_eur
    return WindowTotals(operation=operation, day=day_total, month=month_total)
