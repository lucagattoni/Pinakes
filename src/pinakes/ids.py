"""Document and KB identity.

Every document and every KB carries a ULID, minted once and **never regenerated** — every inbound
`pnk://` link depends on it and this design has no migration machinery by choice
(docs/INVARIANTS.md).

IDs are canonical uppercase Crockford base32, 26 characters. Lowercase is **rejected, not
normalised**: two spellings of one identity would slip straight past the duplicate-ID check that
protects §6.4's pairing, and an ID is machine-minted, so a lowercase one means something already
went wrong. `python-ulid` is strict about the rest for us — it rejects the ambiguous Crockford
letters (`I`, `L`, `O`, `U` — all four probed), wrong lengths, and timestamps past the 48-bit
ceiling (verified 20260725 14:05, python-ulid 4.0.1).
"""

from typing import NewType

from ulid import ULID

from pinakes.errors import InvalidIdError

KbId = NewType("KbId", str)
"""A KB's permanent identity — the authority in a `pnk://` URI (docs/DESIGN.md §2.2)."""

DocId = NewType("DocId", str)
"""A document's permanent identity, living in its sidecar."""

OperationId = NewType("OperationId", str)
"""One user-facing invocation — a whole `pnk sync`, a whole `pnk ask --deep`. The unit
`[budget] per_operation_eur` bounds (I6b). Not permanent: it identifies a run, not a thing."""

CallId = NewType("CallId", str)
"""One API call. The unit a ledger reservation/outcome pair keys on, and what an extraction cache
entry joins against (I6b). Distinct from `OperationId` because one operation makes many calls, and
one word for both made `per_operation_eur` ambiguous by a factor of forty."""

ID_LENGTH = 26


def mint_kb_id() -> KbId:
    return KbId(str(ULID()))


def mint_doc_id() -> DocId:
    return DocId(str(ULID()))


def mint_operation_id() -> OperationId:
    return OperationId(str(ULID()))


def mint_call_id() -> CallId:
    return CallId(str(ULID()))


def _parse(raw: str, *, kind: str) -> str:
    try:
        return str(ULID.from_str(raw))
    except (ValueError, TypeError) as exc:
        raise InvalidIdError(raw, kind=kind) from exc


def parse_kb_id(raw: str) -> KbId:
    return KbId(_parse(raw, kind="KB"))


def parse_doc_id(raw: str) -> DocId:
    return DocId(_parse(raw, kind="document"))


def is_id(raw: str) -> bool:
    """Whether `raw` is a well-formed ULID — for telling an ID from an alias, not for validation."""
    try:
        ULID.from_str(raw)
    except (ValueError, TypeError):
        return False
    return True
