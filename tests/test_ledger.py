"""The spend ledger: what it stores, what it refuses to store, and what survives a crash."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pinakes.budget.ledger import (
    MAX_RECORD_BYTES,
    CallState,
    Record,
    RecordKind,
    Source,
    append,
    call_records,
    ledger_path,
    paid_call,
    quantise,
    read,
    resolve,
    resolve_unknown,
)
from pinakes.budget.window import aggregate
from pinakes.errors import LedgerError, UnknownCallError

MODEL = "claude-opus-5"
RATE = Decimal("1.08")
AS_OF = "20260728 12:00"
KB_ID = "01K1B0GJ0000000000000000AA"


def moment(text: str) -> datetime:
    """A UTC instant from `YYYYMMDD HH:MM`."""
    return datetime.strptime(text, "%Y%m%d %H:%M").replace(tzinfo=UTC)


def record(
    kind: RecordKind,
    *,
    call_id: str,
    at: str = "20260728 12:00",
    cost_usd: str = "0.10",
    operation_id: str = "OP1",
    rate: Decimal = RATE,
    as_of: str = AS_OF,
    source: Source = Source.CALL,
) -> Record:
    return Record(
        kind=kind,
        at=moment(at),
        operation_id=operation_id,
        call_id=call_id,
        operation="sync",
        kb_id=KB_ID,
        model=MODEL,
        cost_usd=Decimal(cost_usd),
        usd_per_eur=rate,
        prices_as_of=as_of,
        source=source,
    )


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return ledger_path(tmp_path / ".pinakes")


def lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- what a line carries -------------------------------------------------------------------


def test_every_line_carries_its_cost_and_the_conversion_that_produced_it(path: Path) -> None:
    """A bare `cost: 0.043` is unreadable a month later: neither the currency nor the rate that
    made it is recoverable, and the rate is exactly what drifts between releases."""
    with paid_call(
        path,
        operation_id="OP1",
        call_id="CALL1",
        operation="sync",
        kb_id=KB_ID,
        model=MODEL,
        reserved_usd=Decimal("0.0432"),
        usd_per_eur=RATE,
        prices_as_of=AS_OF,
    ) as call:
        call.response_received()
        call.reconcile(cost_usd=Decimal("0.0310"), input_tokens=30_300, output_tokens=4_000)

    for entry in lines(path):
        assert entry["cost_usd"] is not None
        assert entry["usd_per_eur"] == str(RATE)
        assert entry["prices_as_of"] == AS_OF
        assert entry["call_id"] == "CALL1"
        assert entry["operation_id"] == "OP1"


def test_the_ledger_stores_no_query_text_and_no_document_content(path: Path) -> None:
    """The sentinel test. A paid call's whole reason to exist is the text it returns; not one
    character of it may reach a file whose job is diagnostics, not a transcript.

    Driven through `paid_call` rather than a real extractor because the paid extractor lands in
    I7b — but through the *same* protocol I7b uses, and with the sentinel flowing through the
    call the way a page's text will: returned by the callee, held by the caller, never handed to
    the ledger. The assertion is a grep over the whole file, so a future field that quietly
    accepts a caller's string fails here rather than in production.
    """
    sentinel = "QUOKKA-VESTIBULE-71828"

    def make_the_call() -> str:
        return f"page 1 text containing {sentinel} and more prose"

    with paid_call(
        path,
        operation_id="OP1",
        call_id="CALL1",
        operation="sync",
        kb_id=KB_ID,
        model=MODEL,
        reserved_usd=Decimal("0.04"),
        usd_per_eur=RATE,
        prices_as_of=AS_OF,
    ) as call:
        extracted = make_the_call()
        call.response_received()
        call.reconcile(cost_usd=Decimal("0.03"), input_tokens=30_300, output_tokens=len(extracted))

    assert sentinel in extracted  # the text really did flow through the call
    assert sentinel not in path.read_text(encoding="utf-8")


def test_money_is_quantised_once_and_below_the_cent(path: Path) -> None:
    """Cent quantisation would store €0.00 for a call that billed — under-counting, the one
    direction a budget must never be wrong in."""
    append(path, record(RecordKind.RESERVATION, call_id="C", cost_usd="0.0043216"))
    assert lines(path)[0]["cost_usd"] == "0.004322"
    assert quantise(Decimal("0.0043216")) == Decimal("0.004322")

    read_back = read(path).records[0]
    assert read_back.cost_usd == Decimal("0.004322")
    # EUR is derived at read time, at full precision — never stored.
    assert read_back.cost_eur == Decimal("0.004322") / RATE


def test_a_record_too_large_for_one_atomic_append_is_refused(path: Path) -> None:
    oversize = record(RecordKind.RESERVATION, call_id="C" * MAX_RECORD_BYTES)
    with pytest.raises(LedgerError) as exc_info:
        append(path, oversize)
    assert "atomic append" in exc_info.value.remedy


def test_a_missing_ledger_reads_as_an_empty_one(tmp_path: Path) -> None:
    assert read(tmp_path / "nope" / "ledger.jsonl").records == ()


def test_an_unreadable_line_is_counted_rather_than_crashing_the_reader(path: Path) -> None:
    append(path, record(RecordKind.RESERVATION, call_id="C1"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json at all\n")
        handle.write('{"schema": 99, "kind": "reservation"}\n')
    append(path, record(RecordKind.RESERVATION, call_id="C2"))

    contents = read(path)
    assert [entry.call_id for entry in contents.records] == ["C1", "C2"]
    assert contents.malformed == (2, 3)


def test_a_json_number_for_money_is_rejected_rather_than_silently_floated(path: Path) -> None:
    """Prices are stored as strings so no `float` ever touches them. A line that used a JSON
    number would parse into a `float`, and `Decimal(0.05) != Decimal("0.05")`."""
    append(path, record(RecordKind.RESERVATION, call_id="C1"))
    entry = lines(path)[0]
    entry["cost_usd"] = 0.05
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    contents = read(path)
    assert contents.records == ()
    assert contents.malformed == (1,)


# --- the three record kinds ----------------------------------------------------------------


def test_a_reconciliation_supersedes_the_reservation_rather_than_adding_to_it(path: Path) -> None:
    append(path, record(RecordKind.RESERVATION, call_id="C1", cost_usd="0.10"))
    append(path, record(RecordKind.RECONCILIATION, call_id="C1", cost_usd="0.03"))

    (call,) = resolve(read(path).records).calls
    assert call.state is CallState.RECONCILED
    assert call.effective_eur == Decimal("0.03") / RATE


def test_an_unreconciled_reservation_counts_at_its_reserved_amount(path: Path) -> None:
    """An in-flight or crashed call consumes headroom rather than vanishing (I6a's rule)."""
    append(path, record(RecordKind.RESERVATION, call_id="C1", cost_usd="0.10"))

    (call,) = resolve(read(path).records).calls
    assert call.state is CallState.UNKNOWN
    assert call.effective_eur == Decimal("0.10") / RATE


def test_a_void_closes_a_reservation_at_zero(path: Path) -> None:
    append(path, record(RecordKind.RESERVATION, call_id="C1", cost_usd="0.10"))
    append(path, record(RecordKind.VOID, call_id="C1", cost_usd="0"))

    (call,) = resolve(read(path).records).calls
    assert call.state is CallState.VOIDED
    assert call.effective_eur == Decimal("0")


def test_a_call_that_raises_before_a_response_is_voided_and_consumes_no_headroom(
    path: Path,
) -> None:
    """Without this, every transient 429 leaves a reservation nothing closes — and since the
    ledger is append-only, a handful of them would lock a user out of the month permanently."""

    class TransientError(RuntimeError):
        pass

    with (
        pytest.raises(TransientError),
        paid_call(
            path,
            operation_id="OP1",
            call_id="CALL1",
            operation="sync",
            kb_id=KB_ID,
            model=MODEL,
            reserved_usd=Decimal("0.10"),
            usd_per_eur=RATE,
            prices_as_of=AS_OF,
        ) as call,
    ):
        assert call.call_id == "CALL1"
        raise TransientError("429 from the vendor")

    kinds = [entry["kind"] for entry in lines(path)]
    assert kinds == ["reservation", "void"]

    (resolved,) = resolve(read(path).records).calls
    assert resolved.state is CallState.VOIDED
    totals = aggregate(call_records(path), now=moment("20260728 13:00"), timezone=ZoneInfo("UTC"))
    assert totals.day == Decimal("0")
    assert totals.month == Decimal("0")


def test_a_call_that_raises_after_a_response_is_never_voided(path: Path) -> None:
    """The defect this whole flag exists to prevent. A bare `finally` cannot tell "the call never
    happened" from "the call returned and then the staging write raised" — and in the second case
    it records €0 for money that left the account, permanently, in a file nothing can edit."""

    with (
        pytest.raises(ValueError),
        paid_call(
            path,
            operation_id="OP1",
            call_id="CALL1",
            operation="sync",
            kb_id=KB_ID,
            model=MODEL,
            reserved_usd=Decimal("0.10"),
            usd_per_eur=RATE,
            prices_as_of=AS_OF,
        ) as call,
    ):
        call.response_received()  # billed from here on, whatever happens next
        raise ValueError("the response was a 4-page array for a 5-page slice")

    assert [entry["kind"] for entry in lines(path)] == ["reservation"]
    (resolved,) = resolve(read(path).records).calls
    assert resolved.state is CallState.UNKNOWN
    assert resolved.effective_eur == Decimal("0.10") / RATE


def test_a_second_reconciliation_supersedes_the_first(path: Path) -> None:
    """An append-only file cannot edit, so correcting a mistaken `--resolve` needs a later record
    to win. First-wins would make one typo permanent."""
    append(path, record(RecordKind.RESERVATION, call_id="C1", cost_usd="0.10"))
    append(path, record(RecordKind.RECONCILIATION, call_id="C1", cost_usd="0.09"))
    append(path, record(RecordKind.RECONCILIATION, call_id="C1", cost_usd="0.03"))

    (call,) = resolve(read(path).records).calls
    assert call.effective_eur == Decimal("0.03") / RATE
    assert call.superseded == 1


def test_a_void_can_never_supersede_a_reconciliation(path: Path) -> None:
    """The one asymmetry in last-wins: zeroing a call that demonstrably billed is the
    under-counting direction, so it is refused and counted instead."""
    append(path, record(RecordKind.RESERVATION, call_id="C1", cost_usd="0.10"))
    append(path, record(RecordKind.RECONCILIATION, call_id="C1", cost_usd="0.09"))
    append(path, record(RecordKind.VOID, call_id="C1", cost_usd="0"))

    (call,) = resolve(read(path).records).calls
    assert call.state is CallState.RECONCILED
    assert call.effective_eur == Decimal("0.09") / RATE
    assert call.superseded == 1


def test_an_outcome_with_no_reservation_is_reported_not_absorbed(path: Path) -> None:
    append(path, record(RecordKind.RECONCILIATION, call_id="GHOST", cost_usd="9.99"))
    resolved = resolve(read(path).records)
    assert resolved.calls == ()
    assert len(resolved.orphaned) == 1


def test_a_pair_is_attributed_to_the_reservations_timestamp(path: Path) -> None:
    """Reserved at 23:59:58 on the 27th, reconciled at 00:00:03 on the 28th: the whole record
    belongs to the 27th, and attribution never moves afterwards."""
    append(
        path,
        record(RecordKind.RESERVATION, call_id="C1", at="20260727 23:59", cost_usd="0.10"),
    )
    append(
        path,
        record(RecordKind.RECONCILIATION, call_id="C1", at="20260728 00:01", cost_usd="0.05"),
    )

    on_the_27th = aggregate(
        call_records(path), now=moment("20260727 23:59"), timezone=ZoneInfo("UTC")
    )
    on_the_28th = aggregate(
        call_records(path), now=moment("20260728 00:01"), timezone=ZoneInfo("UTC")
    )
    assert on_the_27th.day == Decimal("0.05") / RATE
    assert on_the_28th.day == Decimal("0")


def test_a_utc_ledger_is_attributed_in_the_configured_timezone(path: Path) -> None:
    """The ledger stores UTC and `[budget] timezone` may be anything: 23:30 UTC on the 15th is
    00:30 on the *16th* in Berlin. A conversion that was quietly dropped would file this spend
    under the wrong day (docs/RETROSPECTIVES.md, I6a)."""
    append(
        path,
        record(RecordKind.RESERVATION, call_id="C1", at="20260715 23:30", cost_usd="0.10"),
    )
    berlin = ZoneInfo("Europe/Berlin")
    now = moment("20260716 08:00")

    assert aggregate(call_records(path), now=now, timezone=berlin).day == Decimal("0.10") / RATE
    assert aggregate(call_records(path), now=now, timezone=ZoneInfo("UTC")).day == Decimal("0")


# --- durability ----------------------------------------------------------------------------


CRASH_SCRIPT = """\
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pinakes.budget.ledger import PaidCall

call = PaidCall(
    Path(sys.argv[1]),
    operation_id="OP1",
    call_id="CALL1",
    operation="sync",
    kb_id="{kb_id}",
    model="{model}",
    reserved_usd=Decimal("0.10"),
    usd_per_eur=Decimal("{rate}"),
    prices_as_of="{as_of}",
    now=datetime.now(UTC),
)
call.reserve()
import os
os._exit(9)  # killed between the reservation and any outcome
"""


def test_a_process_killed_after_reserving_leaves_a_readable_unknown_outcome(
    path: Path, tmp_path: Path
) -> None:
    """The reservation is written *before* the call and fsynced, so a crash during the call leaves
    spend visible rather than lost. `os._exit` skips every `finally` in the interpreter, which is
    the closest a test gets to a real kill."""
    script = tmp_path / "crash.py"
    script.write_text(
        CRASH_SCRIPT.format(kb_id=KB_ID, model=MODEL, rate=RATE, as_of=AS_OF), encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, str(script), str(path)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 9, result.stderr

    contents = read(path)
    assert contents.malformed == ()
    (call,) = resolve(contents.records).calls
    assert call.state is CallState.UNKNOWN
    assert call.effective_eur == Decimal("0.10") / RATE


APPENDER_SCRIPT = """\
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pinakes.budget.ledger import Record, RecordKind, append

path, tag, count = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
for index in range(count):
    append(
        path,
        Record(
            kind=RecordKind.RESERVATION,
            at=datetime.now(UTC),
            operation_id=tag,
            call_id=f"{tag}-{index}",
            operation="sync",
            kb_id="%(kb_id)s",
            model="%(model)s",
            cost_usd=Decimal("0.001"),
            usd_per_eur=Decimal("%(rate)s"),
            prices_as_of="%(as_of)s",
        ),
    )
"""


def test_two_processes_appending_at_once_interleave_no_record(path: Path, tmp_path: Path) -> None:
    """Each line is one `O_APPEND` write under 4 KB, so the kernel cannot split it (§5). A torn
    line would show up as a malformed line here, and a lost one as a short count."""
    per_process = 120
    script = tmp_path / "appender.py"
    script.write_text(
        APPENDER_SCRIPT % {"kb_id": KB_ID, "model": MODEL, "rate": RATE, "as_of": AS_OF},
        encoding="utf-8",
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    processes = [
        subprocess.Popen(
            [sys.executable, str(script), str(path), tag, str(per_process)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for tag in ("AAA", "BBB")
    ]
    for process in processes:
        _out, err = process.communicate()
        assert process.returncode == 0, err.decode()

    contents = read(path)
    assert contents.malformed == ()
    assert len(contents.records) == 2 * per_process
    assert len({entry.call_id for entry in contents.records}) == 2 * per_process


# --- `pnk budget --resolve` ----------------------------------------------------------------


def test_resolving_an_unknown_outcome_appends_and_never_edits(path: Path) -> None:
    append(path, record(RecordKind.RESERVATION, call_id="C1", cost_usd="0.10"))
    before = path.read_bytes()

    written = resolve_unknown(path, call_id="C1", actual_eur=Decimal("0.02"))

    after = path.read_bytes()
    assert after.startswith(before)  # nothing already written changed
    assert written.source is Source.OPERATOR
    # Priced at the *reservation's* rate, so the pair stays internally consistent.
    assert written.usd_per_eur == RATE
    assert written.prices_as_of == AS_OF
    assert written.cost_eur == Decimal("0.02")

    (call,) = resolve(read(path).records).calls
    assert call.state is CallState.RECONCILED


def test_resolving_refuses_an_unknown_call_id(path: Path) -> None:
    with pytest.raises(UnknownCallError):
        resolve_unknown(path, call_id="NOPE", actual_eur=Decimal("0.02"))


def test_resolving_refuses_a_call_that_is_already_closed(path: Path) -> None:
    append(path, record(RecordKind.RESERVATION, call_id="C1"))
    append(path, record(RecordKind.VOID, call_id="C1", cost_usd="0"))
    with pytest.raises(UnknownCallError) as exc_info:
        resolve_unknown(path, call_id="C1", actual_eur=Decimal("0.02"))
    assert "already voided" in exc_info.value.message


def test_resolving_refuses_a_negative_amount(path: Path) -> None:
    """The input validation that matters is whichever one lets the number move in the
    safe-looking direction: a negative `--actual` would *subtract* from a window's total."""
    append(path, record(RecordKind.RESERVATION, call_id="C1"))
    with pytest.raises(LedgerError):
        resolve_unknown(path, call_id="C1", actual_eur=Decimal("-1.00"))


# --- what must never touch it --------------------------------------------------------------


def test_the_ledger_survives_rebuild_and_clear_cache_byte_for_byte(fake_kb: Path) -> None:
    """`--rebuild` recreates `index.db` and `--clear-cache` empties `cache/extract/`; neither may
    touch the one file in `.pinakes/` that cannot be recomputed (§6.3)."""
    from pinakes.cli import main

    ledger = ledger_path(fake_kb / ".pinakes")
    append(ledger, record(RecordKind.RESERVATION, call_id="C1"))
    append(ledger, record(RecordKind.RECONCILIATION, call_id="C1", cost_usd="0.02"))
    before = ledger.read_bytes()

    assert main(["sync", "--kb", str(fake_kb)]) == 0
    assert ledger.read_bytes() == before
    assert main(["sync", "--kb", str(fake_kb), "--rebuild"]) == 0
    assert ledger.read_bytes() == before
    assert main(["sync", "--kb", str(fake_kb), "--clear-cache", "--yes"]) == 0
    assert ledger.read_bytes() == before


def test_an_old_reservation_falls_out_of_both_windows(path: Path) -> None:
    """Nothing prunes the ledger — the windows are what bound it, and a record from last month
    must stop counting on its own."""
    stale = (datetime.now(UTC) - timedelta(days=70)).strftime("%Y%m%d %H:%M")
    append(path, record(RecordKind.RESERVATION, call_id="OLD", at=stale, cost_usd="4.00"))

    totals = aggregate(call_records(path), now=datetime.now(UTC), timezone=ZoneInfo("UTC"))
    assert totals.day == Decimal("0")
    assert totals.month == Decimal("0")


def test_the_ledger_directory_is_created_on_first_write(tmp_path: Path) -> None:
    target = ledger_path(tmp_path / "brand-new" / ".pinakes")
    assert not target.parent.exists()
    append(target, record(RecordKind.RESERVATION, call_id="C1"))
    assert target.is_file()


def test_the_write_is_a_single_append_not_a_rewrite(path: Path) -> None:
    """`O_APPEND`, never `open(..., "w")`: a rewrite would lose every earlier line the moment two
    processes overlapped."""
    append(path, record(RecordKind.RESERVATION, call_id="C1"))
    inode_before = os.stat(path).st_ino
    append(path, record(RecordKind.RESERVATION, call_id="C2"))
    assert os.stat(path).st_ino == inode_before
    assert len(lines(path)) == 2


def test_the_module_reads_what_it_writes(path: Path) -> None:
    """A round trip through JSON, including the fields a `float` would corrupt."""
    original = Record(
        kind=RecordKind.RECONCILIATION,
        at=moment("20260728 12:34"),
        operation_id="OP1",
        call_id="C1",
        operation="sync",
        kb_id=KB_ID,
        model=MODEL,
        cost_usd=Decimal("0.043210"),
        usd_per_eur=Decimal("1.0812"),
        prices_as_of=AS_OF,
        input_tokens=30_300,
        output_tokens=4_000,
        source=Source.OPERATOR,
    )
    append(path, original)
    assert read(path).records[0] == original


def test_a_naive_timestamp_is_refused(path: Path) -> None:
    """Attribution converts `at` into `[budget] timezone`; a timestamp with no zone cannot be
    converted, only guessed at."""
    append(path, record(RecordKind.RESERVATION, call_id="C1"))
    entry = lines(path)[0]
    entry["at"] = "2026-07-28T12:00:00"
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    assert read(path).malformed == (1,)


def test_a_zero_conversion_rate_is_a_malformed_line_not_a_traceback(path: Path) -> None:
    """Every euro figure is `cost_usd / usd_per_eur`, and that division happens in a property —
    called long after parsing, from inside `pnk budget`'s own summing. A `DivisionByZero` escaping
    from there is a traceback out of a read-only reporting command."""
    append(path, record(RecordKind.RESERVATION, call_id="C1"))
    entry = lines(path)[0]
    entry["usd_per_eur"] = "0"
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    contents = read(path)
    assert contents.records == ()
    assert contents.malformed == (1,)


def test_a_negative_conversion_rate_is_refused_too(path: Path) -> None:
    append(path, record(RecordKind.RESERVATION, call_id="C1"))
    entry = lines(path)[0]
    entry["usd_per_eur"] = "-1.08"
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    assert read(path).malformed == (1,)


def test_the_first_write_syncs_the_directory_entry_too(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Syncing a file's contents does not make its *name* durable. Without this, the very first
    reservation a KB ever writes — the one before its first paid call — could vanish on a crash
    while every later one survived."""
    synced: list[int] = []
    real_fsync = os.fsync

    def spy(handle: int) -> None:
        synced.append(handle)
        real_fsync(handle)

    monkeypatch.setattr(os, "fsync", spy)

    append(path, record(RecordKind.RESERVATION, call_id="C1"))
    assert len(synced) == 2, "the file and its directory"

    synced.clear()
    append(path, record(RecordKind.RESERVATION, call_id="C2"))
    assert len(synced) == 1, "the file only — the directory entry already exists"
