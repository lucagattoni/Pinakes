"""`.pinakes/ledger.jsonl` — the append-only spend record, and the call protocol that writes it.

**Three record kinds, keyed by `call_id`.** A **reservation** is written *before* the call, then
exactly one of a **reconciliation** (the call returned; true usage supersedes the reserved amount)
or a **void** (the call never billed; the reservation closes at zero). A crash between the call and
the ledger write would otherwise lose spend history permanently — the one thing in `.pinakes/` that
cannot be recomputed — and a reservation with neither successor is reported as `unknown outcome`,
never dropped and never counted as zero.

**A void is written only when no response was received, never from a bare `finally`.**
`PaidCall.response_received()` is called the instant the client returns, and only the
not-received path voids. A bare `finally` cannot tell "the call never happened" from "the call
returned and then schema branching or the staging write raised" — and in the second case it would
record €0 for money that left the account, permanently, in an append-only file. Under-counting is
the direction a budget system must never be wrong in, so the flag is the discriminator and
`paid_call` is the only supported way to write a pair.

**Cost is recorded in USD with its conversion provenance, never as a bare number.** Every line
carries `cost_usd`, the `usd_per_eur` rate used, and the price table's `as_of`; EUR is computed at
read time. A line saying only `cost: 0.043` is unreadable a month later — nobody can tell which
currency it is or which rate produced it — and the rate is exactly the number that drifts.

**Two identifiers.** `operation_id` is one `pnk sync` (or one `pnk ask --deep`) — the unit
`per_operation_eur` bounds. `call_id` is one API call — the unit a reservation/outcome pair keys
on, and what the extraction cache's entries join against.

**Quantisation happens here and nowhere else** (CLAUDE.md): amounts are `Decimal` end to end and
are quantised exactly once, when a record is written, to `QUANTUM` — six decimal places of USD,
not cents. Cents would be the wrong quantum in the unsafe direction: a €0.0043 call rounds to
€0.00, and a ledger that stores zero for a call that billed under-counts every window it belongs
to. Six places sit below any per-call amount these models can produce, so the rounding is
arithmetically inert and the invariant still holds — one quantisation, at write time.

Each line is a single `O_APPEND` write of under `MAX_RECORD_BYTES`, so two processes appending
concurrently cannot interleave a record (docs/DESIGN.md §5), and each write is `fsync`ed: the
whole point of writing the reservation *before* the call is that it survives a crash during it.

**The ledger stores no query text and no document content** — timestamps, ids, a record kind, an
operation kind, a model name, token counts and cost. It is diagnostics, not a transcript. `source`
distinguishes a reconciliation the client wrote from one an operator supplied via
`pnk budget --resolve`; it is an enum, never free text, for the same reason.
"""

import json
import os
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Self, cast

from pinakes.budget.window import CallRecord
from pinakes.errors import LedgerError, UnknownCallError

LEDGER_NAME: Final = "ledger.jsonl"

#: Bumped only if a *reader* would misread an older line. New optional keys do not bump it.
LEDGER_SCHEMA_VERSION: Final = 1

#: One record must fit a single atomic append. Well above any line this module writes (~350 bytes);
#: the check exists so a future field cannot silently cross the boundary the atomicity claim rests
#: on.
MAX_RECORD_BYTES: Final = 4096

#: The one place money is quantised — see the module docstring for why this is not the cent.
QUANTUM: Final = Decimal("0.000001")

ZERO: Final = Decimal("0")


class RecordKind(StrEnum):
    RESERVATION = "reservation"
    RECONCILIATION = "reconciliation"
    VOID = "void"


class Source(StrEnum):
    CALL = "call"
    """Written by the code that made the call."""
    OPERATOR = "operator"
    """Written by `pnk budget --resolve`, from a human reading the vendor's usage dashboard."""


class CallState(StrEnum):
    RECONCILED = "reconciled"
    VOIDED = "voided"
    UNKNOWN = "unknown outcome"


def quantise(amount: Decimal) -> Decimal:
    """Round to the stored quantum. Half-up, and applied once — at write time."""
    return amount.quantize(QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Record:
    """One ledger line. `cost_usd` is the *reserved* amount on a reservation and the *actual*
    amount on a reconciliation; a void is always zero."""

    kind: RecordKind
    at: datetime
    """Tz-aware, written in UTC. Day and month attribution converts it to `[budget] timezone` at
    read time — the ledger never stores a local time, so a KB carried between zones stays
    readable."""
    operation_id: str
    call_id: str
    operation: str
    """The user-facing invocation kind — `sync`, `ask`. An operator's `--resolve` record copies the
    reservation's own value rather than inventing one: the pair describes one call, made by one
    operation, and `source` is what says who wrote the closing line."""
    kb_id: str
    model: str
    cost_usd: Decimal
    usd_per_eur: Decimal
    prices_as_of: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    source: Source = Source.CALL

    @property
    def cost_eur(self) -> Decimal:
        """Computed at read time, at full `Decimal` precision — never stored (module docstring)."""
        return self.cost_usd / self.usd_per_eur

    def as_json(self) -> dict[str, Any]:
        return {
            "schema": LEDGER_SCHEMA_VERSION,
            "kind": self.kind.value,
            "at": self.at.astimezone(UTC).isoformat(),
            "operation_id": self.operation_id,
            "call_id": self.call_id,
            "operation": self.operation,
            "kb_id": self.kb_id,
            "model": self.model,
            "cost_usd": str(quantise(self.cost_usd)),
            "usd_per_eur": str(self.usd_per_eur),
            "prices_as_of": self.prices_as_of,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "source": self.source.value,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Self:
        """Parse one line. Raises `ValueError` for anything unreadable — `read` turns that into a
        counted malformed line rather than a crash, because a ledger a reader refuses to open is a
        budget nobody can see."""
        schema = data.get("schema")
        if schema != LEDGER_SCHEMA_VERSION:
            raise ValueError(f"unsupported ledger schema {schema!r}")
        try:
            return cls(
                kind=RecordKind(data["kind"]),
                at=_utc(data["at"]),
                operation_id=_text(data, "operation_id"),
                call_id=_text(data, "call_id"),
                operation=_text(data, "operation"),
                kb_id=_text(data, "kb_id"),
                model=_text(data, "model"),
                cost_usd=_money(data, "cost_usd"),
                usd_per_eur=_rate(data, "usd_per_eur"),
                prices_as_of=_text(data, "prices_as_of"),
                input_tokens=_count(data, "input_tokens"),
                output_tokens=_count(data, "output_tokens"),
                source=Source(data.get("source", Source.CALL.value)),
            )
        except (KeyError, TypeError, InvalidOperation) as exc:
            # `InvalidOperation` is not a `ValueError` (it descends from `ArithmeticError`), so it
            # has to be named: `Decimal("5,00")` raises it, and an inherited except tuple that
            # omits it is a claim about `float`-parsing code, not this (docs/RETROSPECTIVES.md,
            # I6a).
            raise ValueError(str(exc)) from exc


def _utc(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise TypeError(f"timestamp must be a string, got {type(raw).__name__}")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp {raw!r} carries no timezone")
    return parsed.astimezone(UTC)


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string, got {type(value).__name__}")
    return value


def _money(data: Mapping[str, Any], key: str) -> Decimal:
    value = data[key]
    if not isinstance(value, str):
        # Stored as strings on purpose: a JSON number would come back as a `float` and reintroduce
        # exactly the binary imprecision `Decimal` is here to keep out.
        raise TypeError(f"{key} must be a decimal string, got {type(value).__name__}")
    return Decimal(value)


def _rate(data: Mapping[str, Any], key: str) -> Decimal:
    """A conversion rate, which every euro figure is *divided* by.

    Zero (or negative) is rejected here rather than at the division, because the division happens
    in `cost_eur` — a property, called long after parsing, from inside `pnk budget`'s own summing.
    A `DivisionByZero` escaping from there is a traceback out of a read-only reporting command,
    and the whole point of counting malformed lines is that no single bad line can do that.
    """
    rate = _money(data, key)
    if rate <= ZERO:
        raise ValueError(f"{key} must be positive, got {rate}")
    return rate


def _count(data: Mapping[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an integer or null, got {type(value).__name__}")
    return value


def ledger_path(state_dir: Path) -> Path:
    return state_dir / LEDGER_NAME


def append(path: Path, record: Record) -> None:
    """One record, one atomic append, fsynced.

    `O_APPEND` makes the seek-and-write a single kernel operation, so a second process appending at
    the same moment cannot land inside this line. The `fsync` is what makes the pre-call
    reservation worth writing at all: without it a crash during the call can lose the very record
    that exists to survive one.

    The *directory* is fsynced too, but only when this call created the file. Syncing a file's
    contents does not make its directory entry durable, so without it the very first reservation a
    KB ever writes — the one before the first paid call it ever makes — could vanish entirely on a
    crash while every later one survived.
    """
    payload = json.dumps(record.as_json(), separators=(",", ":"), sort_keys=True) + "\n"
    data = payload.encode("utf-8")
    if len(data) > MAX_RECORD_BYTES:
        raise LedgerError(
            f"a ledger record of {len(data)} bytes exceeds the {MAX_RECORD_BYTES}-byte limit.",
            remedy="Records must fit one atomic append (docs/DESIGN.md §5). Shorten the fields.",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    created = not path.exists()
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    except OSError as exc:
        raise LedgerError(
            f"cannot open {path}: {exc.strerror}.",
            remedy="The spend ledger must be writable before a paid call is made.",
        ) from exc
    try:
        written = os.write(handle, data)
        if written != len(data):
            raise LedgerError(
                f"short write to {path}: {written} of {len(data)} bytes.",
                remedy="A partial record breaks the append-only guarantee; check the filesystem.",
            )
        os.fsync(handle)
    except OSError as exc:
        raise LedgerError(
            f"cannot write to {path}: {exc.strerror}.",
            remedy="The spend ledger must be writable before a paid call is made.",
        ) from exc
    finally:
        os.close(handle)
    if created:
        _fsync_directory(path.parent)


def _fsync_directory(directory: Path) -> None:
    """Best effort — a platform that cannot open a directory read-only still gets a durable file,
    just not a guaranteed durable name for it, and refusing to record spend over that would be the
    worse trade."""
    try:
        handle = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


@dataclass(frozen=True, slots=True)
class LedgerRead:
    records: tuple[Record, ...]
    malformed: tuple[int, ...] = ()
    """1-based line numbers that could not be parsed. Surfaced by `pnk budget`, never silently
    dropped: an unreadable line may be spend, and a reader that hides it is worse than one that
    refuses to open."""


def read(path: Path) -> LedgerRead:
    """Read every record. A missing ledger is an empty one — a KB that has never spent is the
    normal case, not an error."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return LedgerRead(())
    except OSError as exc:
        raise LedgerError(
            f"cannot read {path}: {exc.strerror}.",
            remedy="Spend history is the one part of `.pinakes/` a rebuild cannot recreate.",
        ) from exc

    records: list[Record] = []
    malformed: list[int] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError("not a JSON object")
            records.append(Record.from_json(cast(dict[str, Any], parsed)))
        except (json.JSONDecodeError, ValueError):
            malformed.append(number)
    return LedgerRead(tuple(records), tuple(malformed))


@dataclass(frozen=True, slots=True)
class Call:
    """One `call_id`'s reservation and its closing record, if it has one."""

    reservation: Record
    outcome: Record | None = None
    superseded: int = 0
    """Outcomes for this call that are not the effective one — a corrected `--resolve`, or a void
    refused because a reconciliation already stood. Counted and shown by `pnk budget` rather than
    absorbed silently, since either means two records disagree about one call."""

    @property
    def call_id(self) -> str:
        return self.reservation.call_id

    @property
    def state(self) -> CallState:
        if self.outcome is None:
            return CallState.UNKNOWN
        if self.outcome.kind is RecordKind.VOID:
            return CallState.VOIDED
        return CallState.RECONCILED

    @property
    def effective_eur(self) -> Decimal:
        return self.reservation.cost_eur if self.outcome is None else self.outcome.cost_eur

    def as_call_record(self) -> CallRecord:
        """I6a's aggregation input. Attribution is the *reservation's* timestamp, always — a call
        reserved at 23:59:58 and reconciled at 00:00:03 belongs entirely to the first day."""
        return CallRecord(
            reserved_at=self.reservation.at,
            reserved_eur=self.reservation.cost_eur,
            outcome_eur=None if self.outcome is None else self.outcome.cost_eur,
        )


@dataclass(frozen=True, slots=True)
class Resolved:
    calls: tuple[Call, ...]
    orphaned: tuple[Record, ...] = ()
    """Outcomes whose reservation is absent — impossible under this protocol, so worth reporting
    rather than absorbing into a total."""

    def as_call_records(self) -> tuple[CallRecord, ...]:
        return tuple(call.as_call_record() for call in self.calls)


def resolve(records: Sequence[Record]) -> Resolved:
    """Pair reservations with their outcomes by `call_id`, in file order.

    **The last outcome wins, with one asymmetry: a void may never supersede a reconciliation.**
    An append-only file cannot edit, so correcting a mistaken `pnk budget --resolve` requires a
    later record to win — first-wins would make one typo permanent. But letting a void overwrite a
    reconciliation would zero out money that was actually billed, which is the under-counting
    direction this module exists to prevent, so that one transition is refused and counted instead.
    """
    reservations: dict[str, Record] = {}
    outcomes: dict[str, Record] = {}
    superseded: dict[str, int] = {}
    orphaned: list[Record] = []

    for record in records:
        if record.kind is RecordKind.RESERVATION:
            # A duplicate reservation for one `call_id` cannot happen under `paid_call`, which
            # mints the id. Keeping the first means a stray second one can never *raise* the
            # reserved amount, which is the direction that would silently consume headroom.
            reservations.setdefault(record.call_id, record)
            continue
        if record.call_id not in reservations:
            orphaned.append(record)
            continue
        previous = outcomes.get(record.call_id)
        if previous is not None:
            if record.kind is RecordKind.VOID and previous.kind is RecordKind.RECONCILIATION:
                superseded[record.call_id] = superseded.get(record.call_id, 0) + 1
                continue
            superseded[record.call_id] = superseded.get(record.call_id, 0) + 1
        outcomes[record.call_id] = record

    calls = tuple(
        Call(
            reservation=reservation,
            outcome=outcomes.get(call_id),
            superseded=superseded.get(call_id, 0),
        )
        for call_id, reservation in reservations.items()
    )
    return Resolved(calls, tuple(orphaned))


def call_records(path: Path) -> tuple[CallRecord, ...]:
    """The whole read-and-pair path in one call — what the accountant aggregates."""
    return resolve(read(path).records).as_call_records()


def resolve_unknown(
    path: Path, *, call_id: str, actual_eur: Decimal, now: datetime | None = None
) -> Record:
    """`pnk budget --resolve` — close an `unknown outcome` at an amount an operator has read from
    the vendor's usage dashboard.

    **An append, never an edit.** The ledger's whole guarantee is that nothing already written
    changes, so the correction is a new reconciliation that supersedes the reservation. It carries
    the *reservation's* own `usd_per_eur` and `prices_as_of`, not today's: the operator supplies a
    euro figure for a call priced under that rate, and stamping it with a newer one would make the
    pair internally inconsistent while looking tidier.
    """
    if actual_eur < ZERO:
        raise LedgerError(
            f"--actual {actual_eur} is negative.",
            remedy="A resolved call cost nothing or something; it cannot cost less than nothing.",
        )
    resolved = resolve(read(path).records)
    call = next((candidate for candidate in resolved.calls if candidate.call_id == call_id), None)
    if call is None:
        raise UnknownCallError(call_id, reason="no reservation with that id is in the ledger")
    if call.state is not CallState.UNKNOWN:
        raise UnknownCallError(
            call_id, reason=f"it is already {call.state.value} and needs no resolution"
        )

    reservation = call.reservation
    record = Record(
        kind=RecordKind.RECONCILIATION,
        at=now or datetime.now(UTC),
        operation_id=reservation.operation_id,
        call_id=call_id,
        operation=reservation.operation,
        kb_id=reservation.kb_id,
        model=reservation.model,
        cost_usd=actual_eur * reservation.usd_per_eur,
        usd_per_eur=reservation.usd_per_eur,
        prices_as_of=reservation.prices_as_of,
        source=Source.OPERATOR,
    )
    append(path, record)
    return record


class PaidCall:
    """One call's ledger pair. Built by `paid_call`, never constructed directly by a caller."""

    def __init__(
        self,
        path: Path,
        *,
        operation_id: str,
        call_id: str,
        operation: str,
        kb_id: str,
        model: str,
        reserved_usd: Decimal,
        usd_per_eur: Decimal,
        prices_as_of: str,
        now: datetime | None = None,
    ) -> None:
        self._path = path
        self._operation_id = operation_id
        self._call_id = call_id
        self._operation = operation
        self._kb_id = kb_id
        self._model = model
        self._reserved_usd = reserved_usd
        self._usd_per_eur = usd_per_eur
        self._prices_as_of = prices_as_of
        self._now = now
        self._response_received = False
        self._closed = False

    @property
    def call_id(self) -> str:
        return self._call_id

    def _stamp(self) -> datetime:
        return self._now or datetime.now(UTC)

    def _record(
        self,
        kind: RecordKind,
        cost_usd: Decimal,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> Record:
        return Record(
            kind=kind,
            at=self._stamp(),
            operation_id=self._operation_id,
            call_id=self._call_id,
            operation=self._operation,
            kb_id=self._kb_id,
            model=self._model,
            cost_usd=cost_usd,
            usd_per_eur=self._usd_per_eur,
            prices_as_of=self._prices_as_of,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def reserve(self) -> None:
        """Write the reservation. Called before the request leaves — a reservation written after
        the call is not a reservation."""
        append(self._path, self._record(RecordKind.RESERVATION, self._reserved_usd))

    def response_received(self) -> None:
        """Call this the instant the client returns, before any branching on the response. From
        here on the call is billable, so it can never be voided — only reconciled or left
        `unknown outcome`."""
        self._response_received = True

    def reconcile(
        self,
        *,
        cost_usd: Decimal,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        """True usage supersedes the reservation."""
        if self._closed:
            raise LedgerError(
                f"call {self._call_id} is already closed.",
                remedy="Each call writes exactly one reconciliation or one void.",
            )
        self._closed = True
        append(
            self._path,
            self._record(
                RecordKind.RECONCILIATION,
                cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        )

    def _void(self) -> None:
        self._closed = True
        append(self._path, self._record(RecordKind.VOID, ZERO))

    def close_unfinished(self) -> None:
        """Close a call the body did not close, using the only fact that can decide it safely.

        No response received → the call never billed → **void**. A response received → it billed,
        whatever happened next → left `unknown outcome` for `pnk budget --resolve`, never voided.
        """
        if self._closed:
            return
        if self._response_received:
            return
        self._void()


@contextmanager
def paid_call(
    path: Path,
    *,
    operation_id: str,
    call_id: str,
    operation: str,
    kb_id: str,
    model: str,
    reserved_usd: Decimal,
    usd_per_eur: Decimal,
    prices_as_of: str,
    now: datetime | None = None,
) -> Generator[PaidCall]:
    """The only supported way to write a reservation/outcome pair.

    The reservation is written on entry; on exit — normal *or* exceptional — an unclosed call is
    resolved by `close_unfinished`, which voids only when no response was received. That is why
    this is a context manager and not a documented convention: the rule that a void needs
    `response_received` is enforced by the code that writes the record, not by whoever remembers.
    """
    call = PaidCall(
        path,
        operation_id=operation_id,
        call_id=call_id,
        operation=operation,
        kb_id=kb_id,
        model=model,
        reserved_usd=reserved_usd,
        usd_per_eur=usd_per_eur,
        prices_as_of=prices_as_of,
        now=now,
    )
    call.reserve()
    try:
        yield call
    finally:
        call.close_unfinished()
