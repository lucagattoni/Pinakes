"""The §5 accountant, wired: the manifest's caps, the ledger's history, I6a's arithmetic (I6b).

I6a shipped `reserve()` and `aggregate()` as pure functions with nothing feeding them. This is what
feeds them — and it is a module rather than a few lines inside `sync.py` because the seam is where
a budget system actually fails: caps read from one place and spend from another, agreeing only by
coincidence. `Accountant` is the object `ExtractionContext.accountant` carries from I7b onward.

**The operation window is derived from the ledger, not tallied in memory.** `per_operation_eur`
bounds one `pnk sync`, and the obvious implementation — a running total the caller increments — is
lost the moment the process dies mid-operation and silently restarts at zero. Filtering the ledger
by `operation_id` gives the same number from the same source as the day and month windows, and it
survives a crash the way a reservation is supposed to.

**Every check re-reads the ledger.** A sync makes many calls; another process may be spending
against the same KB between two of them. Caching the totals for the duration of a run would turn
three enforced ceilings into three ceilings enforced against a stale snapshot.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from pinakes.budget import ledger
from pinakes.budget.estimate import Estimate
from pinakes.budget.prices import Prices
from pinakes.budget.reserve import Caps, Decision, DocumentDecision, reserve, reserve_document
from pinakes.budget.window import WindowTotals, aggregate
from pinakes.errors import BudgetConfirmationError
from pinakes.ids import CallId, OperationId, mint_call_id, mint_operation_id
from pinakes.manifest import BudgetSection, Manifest


def caps_of(budget: BudgetSection) -> Caps:
    """The three enforced ceilings. `confirm_above_eur` is deliberately not among them — it is a
    prompt threshold, evaluated independently, never a cap (docs/DESIGN.md §5)."""
    return Caps(
        per_operation_eur=budget.per_operation_eur,
        daily_eur=budget.daily_eur,
        monthly_eur=budget.monthly_eur,
    )


def _display(amount: Decimal) -> str:
    return str(amount.quantize(Decimal("0.01")))


class Accountant:
    """One KB's caps, ledger and clock, for the duration of one operation."""

    def __init__(
        self,
        manifest: Manifest,
        *,
        prices: Prices,
        operation: str = "sync",
        operation_id: OperationId | None = None,
        now: datetime | None = None,
    ) -> None:
        self.manifest = manifest
        self.prices = prices
        self.operation = operation
        self.operation_id: OperationId = operation_id or mint_operation_id()
        self.caps = caps_of(manifest.budget)
        self.timezone = ZoneInfo(manifest.budget.timezone)
        self._now = now

    @property
    def path(self) -> Path:
        return ledger.ledger_path(self.manifest.state_dir)

    def _stamp(self) -> datetime:
        return self._now or datetime.now(UTC)

    def spent(self) -> WindowTotals:
        """Today's, this month's and this operation's totals, all read from the ledger."""
        resolved = ledger.resolve(ledger.read(self.path).records)
        operation_total = sum(
            (
                call.effective_eur
                for call in resolved.calls
                if call.reservation.operation_id == self.operation_id
            ),
            start=Decimal("0"),
        )
        return aggregate(
            resolved.as_call_records(),
            now=self._stamp(),
            timezone=self.timezone,
            operation=operation_total,
        )

    def check_call(self, reserved_eur: Decimal) -> Decision:
        """All three windows, before one call (I6a `reserve`)."""
        return reserve(reserved_eur, self.caps, self.spent())

    def check_document(self, estimate: Estimate) -> DocumentDecision:
        """All three windows, before the *first* call of a document (I6a `reserve_document`)."""
        return reserve_document(
            estimate,
            self.caps,
            self.spent(),
            confirm_above_eur=self.manifest.budget.confirm_above_eur,
        )

    def open_call(
        self,
        *,
        model: str,
        reserved_eur: Decimal,
        call_id: CallId | None = None,
    ) -> ledger.PaidCall:
        """Mint a call and write its reservation. The caller drives it — `response_received()` the
        instant the client returns, then `reconcile()` — and `budget.ledger.paid_call` is the
        wrapper that guarantees an unclosed call is still resolved correctly."""
        call = ledger.PaidCall(
            self.path,
            operation_id=self.operation_id,
            call_id=call_id or mint_call_id(),
            operation=self.operation,
            kb_id=self.manifest.kb.id,
            model=model,
            reserved_usd=reserved_eur * self.prices.usd_per_eur,
            usd_per_eur=self.prices.usd_per_eur,
            prices_as_of=self.prices.as_of,
            now=self._now,
        )
        call.reserve()
        return call


@dataclass(frozen=True, slots=True)
class Confirmation:
    """What a `confirm_above_eur` prompt resolved to, and why."""

    proceed: bool
    asked: bool


def resolve_confirmation(
    decision: DocumentDecision,
    *,
    estimate_eur: Decimal,
    threshold_eur: Decimal,
    interactive: bool,
    yes: bool,
    ask: Callable[[str], str] | None = None,
) -> Confirmation:
    """Answer a `confirm_above_eur` prompt, or refuse to proceed without one.

    The scope is the whole point. Read broadly, "abort when there is no TTY" would abort every
    non-interactive sync — including the hook-driven ones this project's freshness model depends
    on. So the abort fires only when a confirmation is *actually* owed: nothing above the threshold
    means a non-interactive run proceeds normally, and `--yes` answers the prompt when one is owed.

    `--yes` raises no cap. A run that breaches a cap never reaches here — `reserve_document` has
    already refused it — which is what keeps the flag an answer to a question rather than a way
    around a ceiling.
    """
    if not decision.needs_confirmation:
        return Confirmation(proceed=True, asked=False)
    if yes:
        return Confirmation(proceed=True, asked=False)
    if not interactive or ask is None:
        raise BudgetConfirmationError(
            amount_eur=_display(estimate_eur), threshold_eur=_display(threshold_eur)
        )
    answer = ask(
        f"this run is estimated at €{_display(estimate_eur)}, above the "
        f"€{_display(threshold_eur)} `confirm_above_eur` threshold. proceed? [y/N] "
    )
    return Confirmation(proceed=answer.strip().lower() == "y", asked=True)
