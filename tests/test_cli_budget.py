"""`pnk budget`, and the seam where I6a's arithmetic meets I6b's ledger."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pinakes.budget.accountant import Accountant, caps_of, resolve_confirmation
from pinakes.budget.estimate import Estimate
from pinakes.budget.ledger import Record, RecordKind, append, ledger_path
from pinakes.budget.prices import Prices, load_prices
from pinakes.budget.reserve import DocumentDecision
from pinakes.budget.summary import summarise
from pinakes.cli import EXIT_FAILURE, EXIT_OK, main
from pinakes.errors import BudgetConfirmationError
from pinakes.manifest import load

MODEL = "claude-opus-5"
AS_OF = "20260728 12:00"


def entry(
    kind: RecordKind,
    *,
    call_id: str,
    kb_id: str,
    at: datetime,
    cost_usd: str,
    rate: str = "1.08",
    operation_id: str = "OP1",
    as_of: str = AS_OF,
) -> Record:
    return Record(
        kind=kind,
        at=at,
        operation_id=operation_id,
        call_id=call_id,
        operation="sync",
        kb_id=kb_id,
        model=MODEL,
        cost_usd=Decimal(cost_usd),
        usd_per_eur=Decimal(rate),
        prices_as_of=as_of,
    )


def ledger_of(root: Path) -> Path:
    return ledger_path(root / ".pinakes")


# --- the command ---------------------------------------------------------------------------


def test_an_empty_ledger_prints_zeros_rather_than_a_traceback(
    fake_kb: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A KB that has never spent is the normal case, not an error — and `pnk budget` is on the
    free path, so it must work before any paid backend exists at all."""
    assert not ledger_of(fake_kb).exists()
    assert main(["budget", "--kb", str(fake_kb)]) == EXIT_OK

    out = capsys.readouterr().out
    assert "€0.0000 of €" in out
    assert "0 reservation(s)" in out
    assert "per KB" in out  # `monthly_eur` is per KB; v0.2 adds no global cap and says so


def test_totals_match_a_hand_computed_fixture_including_a_window_spanning_two_rates(
    fake_kb: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Three calls, one rate change. Every number here was computed by hand from the records
    below, never from the code under test."""
    loaded = load(fake_kb)
    path = ledger_of(fake_kb)
    now = datetime.now(UTC)

    # Reconciled at $0.0540, rate 1.08  ->  €0.05
    append(
        path,
        entry(RecordKind.RESERVATION, call_id="A", kb_id=loaded.kb.id, at=now, cost_usd="0.1080"),
    )
    append(
        path,
        entry(
            RecordKind.RECONCILIATION, call_id="A", kb_id=loaded.kb.id, at=now, cost_usd="0.0540"
        ),
    )
    # Voided  ->  €0
    append(
        path,
        entry(RecordKind.RESERVATION, call_id="B", kb_id=loaded.kb.id, at=now, cost_usd="0.1080"),
    )
    append(path, entry(RecordKind.VOID, call_id="B", kb_id=loaded.kb.id, at=now, cost_usd="0"))
    # Unreconciled at $0.0550, rate 1.10  ->  €0.05, and a second rate in the same window
    append(
        path,
        entry(
            RecordKind.RESERVATION,
            call_id="C",
            kb_id=loaded.kb.id,
            at=now,
            cost_usd="0.0550",
            rate="1.10",
            as_of="20260801 09:00",
        ),
    )

    summary = summarise(
        path,
        kb_name=loaded.kb.name,
        kb_id=loaded.kb.id,
        caps=caps_of(loaded.budget),
        timezone=ZoneInfo(loaded.budget.timezone),
        now=now,
    )
    day, month = summary.windows
    assert day.spent_eur == Decimal("0.10")
    assert month.spent_eur == Decimal("0.10")
    assert day.rates == (Decimal("1.08"), Decimal("1.10"))
    assert day.spans_several_rates
    assert day.as_of == (AS_OF, "20260801 09:00")
    assert (summary.reservations, summary.reconciled, summary.voided, summary.unknown) == (
        3,
        1,
        1,
        1,
    )
    assert summary.unknown_eur == Decimal("0.05")

    assert main(["budget", "--kb", str(fake_kb)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "spans more than one rate" in out
    assert "pnk budget --resolve C --actual <eur>" in out


def test_a_ledger_line_holding_no_rate_at_all_would_be_unreadable(fake_kb: Path) -> None:
    """The claim `pnk budget` rests on: every total is reproducible from the line that produced
    it. Drop the rate and the euro figure is unrecoverable, which is why the field is mandatory."""
    loaded = load(fake_kb)
    path = ledger_of(fake_kb)
    append(
        path,
        entry(
            RecordKind.RESERVATION,
            call_id="A",
            kb_id=loaded.kb.id,
            at=datetime.now(UTC),
            cost_usd="0.1080",
        ),
    )
    stored = path.read_text(encoding="utf-8")
    assert '"usd_per_eur":"1.08"' in stored
    assert f'"prices_as_of":"{AS_OF}"' in stored


def test_resolve_needs_actual_and_actual_needs_resolve(
    fake_kb: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["budget", "--kb", str(fake_kb), "--resolve", "C"]) == EXIT_FAILURE
    assert "--actual" in capsys.readouterr().err

    assert main(["budget", "--kb", str(fake_kb), "--actual", "0.02"]) == EXIT_FAILURE
    assert "--resolve" in capsys.readouterr().err


def test_resolve_closes_an_unknown_outcome_from_the_command_line(
    fake_kb: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    loaded = load(fake_kb)
    path = ledger_of(fake_kb)
    append(
        path,
        entry(
            RecordKind.RESERVATION,
            call_id="C",
            kb_id=loaded.kb.id,
            at=datetime.now(UTC),
            cost_usd="0.1080",
        ),
    )

    assert main(["budget", "--kb", str(fake_kb), "--resolve", "C", "--actual", "0.02"]) == EXIT_OK
    assert "appended, nothing edited" in capsys.readouterr().out

    summary = summarise(
        path,
        kb_name=loaded.kb.name,
        kb_id=loaded.kb.id,
        caps=caps_of(loaded.budget),
        timezone=ZoneInfo(loaded.budget.timezone),
        now=datetime.now(UTC),
    )
    assert summary.unknown == 0
    assert summary.reconciled == 1


def test_resolve_refuses_a_non_numeric_amount(
    fake_kb: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["budget", "--kb", str(fake_kb), "--resolve", "C", "--actual", "five cents"])
        == EXIT_FAILURE
    )
    assert "not a number" in capsys.readouterr().err


# --- the seam: I6a's arithmetic reading I6b's ledger -----------------------------------------


def prices() -> Prices:
    return Prices(as_of=AS_OF, usd_per_eur=Decimal("1.08"), models=load_prices().models)


def test_a_kb_at_499_of_a_500_month_refuses_the_next_call(
    make_fake_kb: Callable[..., Path],
) -> None:
    """The seam, proved rather than assumed: the operation cap is untouched (this is the run's
    first call) and the day cap is generous, but the *month* window — which exists only because
    something reads the ledger — is what refuses."""
    root = make_fake_kb(budget={"daily_eur": "100.00", "monthly_eur": "5.00"})
    loaded = load(root)
    path = ledger_of(root)
    now = datetime.now(UTC)
    append(
        path,
        entry(RecordKind.RESERVATION, call_id="OLD", kb_id=loaded.kb.id, at=now, cost_usd="5.3892"),
    )  # $5.3892 / 1.08 = €4.99

    accountant = Accountant(loaded, prices=prices(), operation_id=None, now=now)
    assert accountant.spent().month == Decimal("4.99")
    assert accountant.spent().operation == Decimal("0")

    decision = accountant.check_call(Decimal("0.02"))
    assert not decision.allowed
    assert decision.blocked_by == "monthly_eur"


def test_the_operation_window_is_read_back_from_the_ledger_not_tallied_in_memory(
    make_fake_kb: Callable[..., Path],
) -> None:
    """A running total held in a variable restarts at zero when the process dies mid-operation.
    Reading it back by `operation_id` gives the same number from the same source as the other two
    windows, and survives the crash a reservation exists to survive."""
    root = make_fake_kb(budget={"per_operation_eur": "0.10", "daily_eur": "100.00"})
    loaded = load(root)
    now = datetime.now(UTC)
    accountant = Accountant(loaded, prices=prices(), now=now)

    with accountant.paid_call(model=MODEL, reserved_eur=Decimal("0.06")) as call:
        assert call.call_id
        call.response_received()
        # Inside the call, before it is reconciled: the reservation already consumes headroom.
        assert accountant.spent().operation == Decimal("0.06")

        # A second accountant on the *same* operation id — what a resumed process would build.
        resumed = Accountant(loaded, prices=prices(), operation_id=accountant.operation_id, now=now)
        assert resumed.spent().operation == Decimal("0.06")
        assert not resumed.check_call(Decimal("0.06")).allowed
        call.reconcile(cost_usd=Decimal("0.0648"))

    assert accountant.spent().operation == Decimal("0.06")

    # A different operation starts with a clean per-operation allowance, and still sees the day.
    fresh = Accountant(loaded, prices=prices(), now=now)
    assert fresh.spent().operation == Decimal("0")
    assert fresh.spent().day == Decimal("0.06")


def test_spend_is_attributed_in_the_configured_timezone(
    make_fake_kb: Callable[..., Path],
) -> None:
    """The ledger stores UTC; `[budget] timezone` decides which day that is. 23:30 UTC is already
    tomorrow in Berlin (docs/RETROSPECTIVES.md, I6a)."""
    root = make_fake_kb(budget={"timezone": '"Europe/Berlin"', "daily_eur": "100.00"})
    loaded = load(root)
    reserved_at = datetime(2026, 7, 15, 23, 30, tzinfo=UTC)
    append(
        ledger_of(root),
        entry(
            RecordKind.RESERVATION, call_id="A", kb_id=loaded.kb.id, at=reserved_at, cost_usd="1.08"
        ),
    )

    berlin_morning = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    assert Accountant(loaded, prices=prices(), now=berlin_morning).spent().day == Decimal("1.00")

    utc_root = make_fake_kb(budget={"timezone": '"UTC"', "daily_eur": "100.00"})
    utc_loaded = load(utc_root)
    append(
        ledger_of(utc_root),
        entry(
            RecordKind.RESERVATION,
            call_id="A",
            kb_id=utc_loaded.kb.id,
            at=reserved_at,
            cost_usd="1.08",
        ),
    )
    assert Accountant(utc_loaded, prices=prices(), now=berlin_morning).spent().day == Decimal("0")


# --- the confirmation prompt -----------------------------------------------------------------


def estimate(total_eur: str) -> Estimate:
    half = Decimal(total_eur) / 2
    return Estimate(
        model=MODEL,
        pages_total=5,
        pages_estimated=5,
        requests=1,
        input_tokens_per_request=30_300,
        output_tokens_per_request=8_000,
        input_eur=half,
        output_eur=half,
    )


def test_a_non_interactive_run_with_nothing_to_confirm_proceeds() -> None:
    """The scope that matters. Read broadly, "abort with no TTY" would abort every hook-driven
    sync this project's freshness model depends on."""
    decision = DocumentDecision(allowed=True, needs_confirmation=False)
    outcome = resolve_confirmation(
        decision,
        estimate_eur=Decimal("0.001"),
        threshold_eur=Decimal("0.01"),
        interactive=False,
        yes=False,
    )
    assert outcome.proceed
    assert not outcome.asked


def test_a_confirmation_owed_with_no_tty_and_no_yes_aborts_with_a_remedy() -> None:
    decision = DocumentDecision(allowed=True, needs_confirmation=True)
    with pytest.raises(BudgetConfirmationError) as exc_info:
        resolve_confirmation(
            decision,
            estimate_eur=Decimal("0.04"),
            threshold_eur=Decimal("0.01"),
            interactive=False,
            yes=False,
        )
    assert "--yes" in exc_info.value.remedy
    assert "raises no cap" in exc_info.value.remedy
    assert "0.04" in exc_info.value.message


def test_yes_answers_the_prompt_and_nothing_else() -> None:
    decision = DocumentDecision(allowed=True, needs_confirmation=True)
    outcome = resolve_confirmation(
        decision,
        estimate_eur=Decimal("0.04"),
        threshold_eur=Decimal("0.01"),
        interactive=False,
        yes=True,
    )
    assert outcome.proceed
    assert not outcome.asked


def test_an_interactive_run_asks_and_honours_the_answer() -> None:
    decision = DocumentDecision(allowed=True, needs_confirmation=True)
    asked: list[str] = []

    def say(answer: str) -> Callable[[str], str]:
        def _ask(prompt: str) -> str:
            asked.append(prompt)
            return answer

        return _ask

    yes = resolve_confirmation(
        decision,
        estimate_eur=Decimal("0.04"),
        threshold_eur=Decimal("0.01"),
        interactive=True,
        yes=False,
        ask=say("y"),
    )
    no = resolve_confirmation(
        decision,
        estimate_eur=Decimal("0.04"),
        threshold_eur=Decimal("0.01"),
        interactive=True,
        yes=False,
        ask=say("n"),
    )
    assert yes.proceed and yes.asked
    assert not no.proceed and no.asked
    assert all("0.04" in prompt and "0.01" in prompt for prompt in asked)


def test_a_document_that_breaches_a_cap_never_reaches_the_prompt(
    make_fake_kb: Callable[..., Path],
) -> None:
    """`--yes` raises no cap, and this is why it cannot: a refusal happens in `reserve_document`,
    before any confirmation is even considered."""
    root = make_fake_kb(budget={"per_operation_eur": "0.05", "confirm_above_eur": "0.01"})
    accountant = Accountant(load(root), prices=prices(), now=datetime.now(UTC))

    decision = accountant.check_document(estimate("9.00"))
    assert not decision.allowed
    assert not decision.needs_confirmation

    outcome = resolve_confirmation(
        decision,
        estimate_eur=Decimal("9.00"),
        threshold_eur=Decimal("0.01"),
        interactive=False,
        yes=True,
    )
    assert outcome.proceed  # `--yes` says nothing about the cap — the refusal above already stands


# --- `--clear-cache` and what `--yes` does not authorise --------------------------------------


def paid_cache_entry(root: Path, name: str) -> Path:
    cache = root / ".pinakes" / "cache" / "extract"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{name}.json"
    path.write_text(
        '{"schema": 1, "content_hash": "sha256:deadbeef", "operation_id": "OP1", '
        '"text": "", "page_spans": []}',
        encoding="utf-8",
    )
    return path


def free_cache_entry(root: Path, name: str) -> Path:
    cache = root / ".pinakes" / "cache" / "extract"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{name}.json"
    path.write_text(
        '{"schema": 1, "content_hash": "sha256:deadbeef", "operation_id": null, '
        '"text": "", "page_spans": []}',
        encoding="utf-8",
    )
    return path


def test_yes_alone_cannot_destroy_paid_cache_entries_unattended(
    fake_kb: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The behaviour `--clear-cache` claimed to forbid while `--yes`'s stated scope permitted it:
    a cron line carrying `--yes` for freshness must not also throw away paid extractions."""
    import sys

    paid = paid_cache_entry(fake_kb, "paid-one")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    assert main(["sync", "--kb", str(fake_kb), "--clear-cache", "--yes"]) == EXIT_FAILURE
    captured = capsys.readouterr()
    assert paid.is_file()
    assert "written by a paid backend" in captured.out
    assert "--clear-cache=paid" in captured.err


def test_clear_cache_paid_is_the_explicit_way_through(fake_kb: Path) -> None:
    paid = paid_cache_entry(fake_kb, "paid-one")
    assert main(["sync", "--kb", str(fake_kb), "--clear-cache=paid", "--yes"]) == EXIT_OK
    assert not paid.exists()


def test_yes_still_clears_a_cache_holding_nothing_paid(fake_kb: Path) -> None:
    """The narrow scope again: the guard fires on paid entries, not on every unattended clear."""
    free = free_cache_entry(fake_kb, "free-one")
    assert main(["sync", "--kb", str(fake_kb), "--clear-cache", "--yes"]) == EXIT_OK
    assert not free.exists()


def test_no_hook_and_no_workflow_writes_the_paid_clearing_flag() -> None:
    """`--clear-cache=paid` is only a protection if nothing machine-driven ever writes it."""
    from pinakes.ci import WORKFLOW
    from pinakes.hooks import HOOKS

    assert all("--clear-cache" not in command for command in HOOKS.values())
    assert "--clear-cache" not in WORKFLOW


def test_a_call_opened_through_the_accountant_is_always_closed(
    make_fake_kb: Callable[..., Path],
) -> None:
    """`Accountant.paid_call` is a context manager, not a `PaidCall` handed back: a returned object
    leaves both the void/unknown decision and the closing write to whoever remembers, which is the
    one thing `budget.ledger` exists to take out of a caller's hands."""
    from pinakes.budget.ledger import CallState, read, resolve

    root = make_fake_kb(budget={"per_operation_eur": "1.00", "daily_eur": "100.00"})
    accountant = Accountant(load(root), prices=prices(), now=datetime.now(UTC))

    with (
        pytest.raises(RuntimeError),
        accountant.paid_call(model=MODEL, reserved_eur=Decimal("0.06")),
    ):
        raise RuntimeError("connection reset before any response byte")

    (call,) = resolve(read(ledger_of(root)).records).calls
    assert call.state is CallState.VOIDED
    assert accountant.spent().day == Decimal("0")


def test_recent_operations_are_shown_in_the_configured_timezone(
    make_fake_kb: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """One report, one clock. The machine's own local zone would be a second, unlabelled one — and
    on a KB synced from two machines the same operation would appear at two different times."""
    root = make_fake_kb(budget={"timezone": '"Asia/Tokyo"'})
    loaded = load(root)
    # 23:30 UTC on the 15th is 08:30 on the *16th* in Tokyo.
    append(
        ledger_of(root),
        entry(
            RecordKind.RESERVATION,
            call_id="A",
            kb_id=loaded.kb.id,
            at=datetime(2026, 7, 15, 23, 30, tzinfo=UTC),
            cost_usd="0.01",
        ),
    )

    assert main(["budget", "--kb", str(root)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "20260716 08:30" in out
