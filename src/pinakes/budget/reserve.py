"""The §5 accountant — pure: given an estimate, the configured caps, and what has already been
spent, decide whether a call (or a whole document) may proceed (I6a).

**Before every call, all three ceilings are checked** — `per_operation_eur`, `daily_eur`, and
`monthly_eur` — and if any of `spent.X + reserved` would exceed its cap, the call is never made.
One operation (one `pnk sync`, one `pnk ask --deep`) bounds a single invocation only; the day and
month windows are what stop a *sequence* of invocations, which is the failure mode a hook-driven KB
actually has.

**The whole document is checked before the first call**, not only per call: per-call reservation
alone bounds each call and nothing else, and a document that will certainly blow through a window
by call 15 should be refused at call 0, not discovered by watching it fail partway through.
`reserve_document` is that upfront check — it refuses with all three windows' current headroom,
the computed estimate, the complete manifest edit that would admit this run, and a line on the
ongoing exposure that edit creates (a raised cap is permanent; a one-run `--extract=` override for
a specific paid backend is not).

`confirm_above_eur` is evaluated **once, against the whole-document estimate** — never per call
(`reserve` itself does not touch it): a per-call reading against a several-cent slice would prompt
dozens of times for one multi-page document, which is how a confirmation becomes something a user
learns to hold down `y` through.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from pinakes.budget.estimate import Estimate
from pinakes.budget.window import WindowTotals

_CENT = Decimal("0.01")


def _display(amount: Decimal) -> str:
    """Round-half-up to the cent for a human-facing message only — the comparisons above run at
    full `Decimal` precision throughout; quantisation for *storage* happens once, at ledger-write
    time (I6b), and this is a separate, display-only rounding that never feeds back into a
    decision."""
    return str(amount.quantize(_CENT, rounding=ROUND_HALF_UP))


#: (attribute on `Caps`, attribute on `WindowTotals`, display name) — one row per window, checked
#: in this order everywhere the three are named together.
_WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("per_operation_eur", "operation", "per_operation_eur"),
    ("daily_eur", "day", "daily_eur"),
    ("monthly_eur", "month", "monthly_eur"),
)


@dataclass(frozen=True, slots=True)
class Caps:
    per_operation_eur: Decimal
    daily_eur: Decimal
    monthly_eur: Decimal


@dataclass(frozen=True, slots=True)
class Decision:
    """The outcome of one per-call `reserve()` check."""

    allowed: bool
    blocked_by: str | None = None
    """Which window refused it — `"per_operation_eur"`, `"daily_eur"` or `"monthly_eur"` — `None`
    when `allowed`."""
    message: str | None = None
    """A ready-to-print refusal, set only when `allowed` is `False`."""


@dataclass(frozen=True, slots=True)
class DocumentDecision:
    """The outcome of the whole-document `reserve_document()` precheck."""

    allowed: bool
    needs_confirmation: bool
    """`confirm_above_eur` reached — a soft prompt, meaningful only when `allowed`."""
    message: str | None = None
    """The complete, multi-line refusal — every window's headroom, the estimate, the manifest
    edit that would admit this run, and the ongoing-exposure line. Set only when not `allowed`."""


def reserve(reserved_eur: Decimal, caps: Caps, spent: WindowTotals) -> Decision:
    """Check one call's estimated cost against all three windows, in order. The first window it
    would breach is the one named — the call is refused before any of the others are even
    checked, since one honest reason is clearer than three, and the caller cannot make the call
    anyway."""
    for cap_attr, spent_attr, name in _WINDOWS:
        cap = getattr(caps, cap_attr)
        already = getattr(spent, spent_attr)
        would_be = already + reserved_eur
        if would_be > cap:
            message = (
                f"refused: the {name} cap of €{_display(cap)} would be exceeded "
                f"(already spent €{_display(already)} this window, this call would add "
                f"€{_display(reserved_eur)}, total €{_display(would_be)})."
            )
            return Decision(allowed=False, blocked_by=name, message=message)
    return Decision(allowed=True)


def reserve_document(
    estimate: Estimate, caps: Caps, spent: WindowTotals, *, confirm_above_eur: Decimal
) -> DocumentDecision:
    """Check a whole document's worst-case estimate against all three windows before the first
    call. Unlike `reserve`, a refusal here names *every* window at once — walking a user through
    one manifest edit, then a second, then a third, to discover the actual ceiling is precisely
    the defect this exists to avoid."""
    total = estimate.total_eur
    blocked = [
        (cap_attr, spent_attr, name, getattr(caps, cap_attr), getattr(spent, spent_attr))
        for cap_attr, spent_attr, name in _WINDOWS
        if getattr(spent, spent_attr) + total > getattr(caps, cap_attr)
    ]
    if blocked:
        return DocumentDecision(
            allowed=False, needs_confirmation=False, message=_refusal_message(estimate, blocked)
        )
    return DocumentDecision(allowed=True, needs_confirmation=total > confirm_above_eur)


def _refusal_message(
    estimate: Estimate, blocked: list[tuple[str, str, str, Decimal, Decimal]]
) -> str:
    lines = [
        f"refused: extracting {estimate.pages_estimated} page(s) of {estimate.pages_total} with "
        f"{estimate.model} is estimated at €{_display(estimate.total_eur)} "
        f"({estimate.requests} request(s), worst case), which exceeds "
        f"{len(blocked)} of the three budget windows:",
    ]
    edits: list[str] = []
    for cap_attr, _spent_attr, name, cap, already in blocked:
        headroom = cap - already
        minimum_cap = (already + estimate.total_eur).quantize(_CENT, rounding=ROUND_CEILING)
        lines.append(
            f"  - {name}: cap €{_display(cap)}, already spent €{_display(already)} this window, "
            f"headroom €{_display(headroom)} — this run needs €{_display(estimate.total_eur)}."
        )
        edits.append(f"{cap_attr} = {minimum_cap}")
    lines.append("The complete manifest edit that would admit this run:")
    lines.append("  [budget]")
    lines.extend(f"  {edit}" for edit in edits)
    lines.append(
        "Raising a cap is a permanent, ongoing exposure to every future run at that ceiling — a "
        "one-run `--extract=<backend>` override changes only this invocation, not the manifest."
    )
    return "\n".join(lines)
