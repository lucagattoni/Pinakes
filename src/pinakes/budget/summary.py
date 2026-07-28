"""What `pnk budget` prints: totals, outcome counts, and the conversion provenance behind them.

Kept out of `cli.py` for the reason `doctor.Check.line()` is: the numbers and the sentences about
them are worth testing without driving a command and capturing stdout.

**Every window shows the rate and `as_of` its total was computed with, and says so when it spans
more than one.** A euro figure derived from two different USD/EUR rates is still correct, but it is
not reproducible from a single number, and the rate is exactly the input that drifts between one
release's price table and the next.

**Unknown outcomes are shown, not hidden.** A reservation with no reconciliation and no void counts
at its reserved amount forever (I6a's rule), so three timeouts can quietly consume a €1.00 day.
Their total, their call ids and the exact `pnk budget --resolve` line that closes one are all
printed, because the alternative is a KB that becomes unusable with no visible way back.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from pinakes.budget.ledger import Call, CallState, LedgerRead, read, resolve
from pinakes.budget.reserve import Caps
from pinakes.budget.window import in_window

#: How many recent operations `pnk budget` lists. The day and month windows are the enforced ones;
#: the per-operation breakdown is context, and an unbounded list would bury it.
RECENT_OPERATIONS = 5

_CENT = Decimal("0.01")
_SUB_CENT = Decimal("0.0001")


def euros(amount: Decimal) -> str:
    """Spend, to four places. A paid call can cost well under a cent, and a total printed to the
    cent would show €0.00 beside a ledger that says otherwise."""
    return str(amount.quantize(_SUB_CENT, rounding=ROUND_HALF_UP))


def cap_euros(amount: Decimal) -> str:
    """A configured ceiling, to the cent — it is a number a human wrote."""
    return str(amount.quantize(_CENT, rounding=ROUND_HALF_UP))


@dataclass(frozen=True, slots=True)
class Window:
    name: str
    spent_eur: Decimal
    cap_eur: Decimal
    rates: tuple[Decimal, ...]
    as_of: tuple[str, ...]

    @property
    def spans_several_rates(self) -> bool:
        return len(self.rates) > 1

    def line(self) -> str:
        head = f"  {self.name:<11} €{euros(self.spent_eur)} of €{cap_euros(self.cap_eur)}"
        if not self.rates:
            return head
        rates = ", ".join(str(rate) for rate in self.rates)
        as_of = ", ".join(self.as_of)
        provenance = f"rate {rates} USD/EUR, prices as of {as_of}"
        if self.spans_several_rates:
            provenance += " — this window spans more than one rate"
        return f"{head}   ({provenance})"


@dataclass(frozen=True, slots=True)
class Operation:
    operation_id: str
    operation: str
    started: datetime
    spent_eur: Decimal
    calls: int


@dataclass(frozen=True, slots=True)
class Summary:
    kb_name: str
    kb_id: str
    timezone: str
    caps: Caps
    windows: tuple[Window, ...]
    operations: tuple[Operation, ...]
    operations_total: int = 0
    """How many operations the ledger holds, against the at-most-`RECENT_OPERATIONS` shown."""
    reservations: int = 0
    reconciled: int = 0
    voided: int = 0
    unknown: int = 0
    unknown_eur: Decimal = Decimal("0")
    unknown_ids: tuple[str, ...] = ()
    malformed: tuple[int, ...] = ()
    orphaned: int = 0
    superseded: int = 0


def _rates(calls: list[Call]) -> tuple[tuple[Decimal, ...], tuple[str, ...]]:
    """The distinct rates and price dates behind a window's total, in first-seen order.

    Taken from each call's *effective* record — the one whose amount is in the total — so the
    provenance shown is the provenance of the number beside it, not of a superseded reservation.
    """
    rates: list[Decimal] = []
    as_of: list[str] = []
    for call in calls:
        effective = call.outcome or call.reservation
        if effective.usd_per_eur not in rates:
            rates.append(effective.usd_per_eur)
        if effective.prices_as_of not in as_of:
            as_of.append(effective.prices_as_of)
    return tuple(rates), tuple(as_of)


def _window(name: str, calls: list[Call], cap: Decimal) -> Window:
    rates, as_of = _rates(calls)
    total = sum((call.effective_eur for call in calls), start=Decimal("0"))
    return Window(name=name, spent_eur=total, cap_eur=cap, rates=rates, as_of=as_of)


def _operations(calls: tuple[Call, ...]) -> tuple[tuple[Operation, ...], int]:
    """The most recent operations, and how many there are in total. Both, because a list capped at
    `RECENT_OPERATIONS` and rendered without saying so reads as "this is all of them"."""
    grouped: dict[str, list[Call]] = {}
    for call in calls:
        grouped.setdefault(call.reservation.operation_id, []).append(call)
    operations = [
        Operation(
            operation_id=operation_id,
            operation=members[0].reservation.operation,
            started=min(call.reservation.at for call in members),
            spent_eur=sum((call.effective_eur for call in members), start=Decimal("0")),
            calls=len(members),
        )
        for operation_id, members in grouped.items()
    ]
    operations.sort(key=lambda operation: operation.started, reverse=True)
    return tuple(operations[:RECENT_OPERATIONS]), len(operations)


def summarise(
    path: Path,
    *,
    kb_name: str,
    kb_id: str,
    caps: Caps,
    timezone: ZoneInfo,
    now: datetime,
) -> Summary:
    """Read the whole ledger and describe it. An absent ledger summarises to zeros — a KB that has
    never spent is the normal case, and it must not print a traceback."""
    contents: LedgerRead = read(path)
    resolved = resolve(contents.records)

    today: list[Call] = []
    month: list[Call] = []
    for call in resolved.calls:
        in_day, in_month = in_window(call.reservation.at, now=now, timezone=timezone)
        if in_day:
            today.append(call)
        if in_month:
            month.append(call)

    unknown = [call for call in resolved.calls if call.state is CallState.UNKNOWN]
    operations, operations_total = _operations(resolved.calls)
    return Summary(
        kb_name=kb_name,
        kb_id=kb_id,
        timezone=str(timezone),
        caps=caps,
        windows=(
            _window("today", today, caps.daily_eur),
            _window("this month", month, caps.monthly_eur),
        ),
        operations=operations,
        operations_total=operations_total,
        reservations=len(resolved.calls),
        reconciled=sum(1 for call in resolved.calls if call.state is CallState.RECONCILED),
        voided=sum(1 for call in resolved.calls if call.state is CallState.VOIDED),
        unknown=len(unknown),
        unknown_eur=sum((call.effective_eur for call in unknown), start=Decimal("0")),
        unknown_ids=tuple(call.call_id for call in unknown),
        malformed=contents.malformed,
        orphaned=len(resolved.orphaned),
        superseded=sum(call.superseded for call in resolved.calls),
    )


def render(summary: Summary) -> list[str]:
    lines = [
        f"budget — {summary.kb_name} ({summary.kb_id})",
        f"  windows computed in {summary.timezone}; "
        f"per-operation cap €{cap_euros(summary.caps.per_operation_eur)}",
        "",
    ]
    lines.extend(window.line() for window in summary.windows)

    lines.append("")
    lines.append(
        f"  {summary.reservations} reservation(s): {summary.reconciled} reconciled, "
        f"{summary.voided} voided, {summary.unknown} unknown outcome"
    )
    if summary.unknown:
        lines.append(
            f"  unknown outcomes hold €{euros(summary.unknown_eur)} — they may or may not have "
            "billed, so they count at their reserved amount until resolved:"
        )
        lines.extend(
            f"      pnk budget --resolve {call_id} --actual <eur>"
            for call_id in summary.unknown_ids
        )
    if summary.superseded:
        lines.append(
            f"  {summary.superseded} superseded outcome record(s) — a later record replaced an "
            "earlier one for the same call (an append-only correction)."
        )
    if summary.orphaned:
        lines.append(
            f"  {summary.orphaned} outcome record(s) with no reservation — not counted in any "
            "window. This should not happen; keep the file and report it."
        )
    if summary.malformed:
        numbers = ", ".join(str(number) for number in summary.malformed)
        lines.append(
            f"  {len(summary.malformed)} unreadable line(s) at {numbers} — skipped, and possibly "
            "spend. The ledger is append-only: do not edit it to make this go away."
        )

    if summary.operations:
        lines.append("")
        hidden = summary.operations_total - len(summary.operations)
        lines.append(
            f"  recent operations ({len(summary.operations)} of {summary.operations_total}, "
            f"{hidden} older not shown):"
            if hidden
            else "  recent operations:"
        )
        # Shown in `[budget] timezone`, the same zone the windows above are computed in. The
        # machine's own local zone would be a second, unlabelled clock in one report — and on a KB
        # synced from two machines it would make the same operation appear at two different times.
        zone = ZoneInfo(summary.timezone)
        lines.extend(
            f"    {operation.started.astimezone(zone).strftime('%Y%m%d %H:%M')}  "
            f"{operation.operation:<7} {operation.calls:>3} call(s)  "
            f"€{euros(operation.spent_eur)}"
            for operation in summary.operations
        )
    return lines
