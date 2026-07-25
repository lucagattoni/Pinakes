"""Identity: ULIDs are permanent, canonical, and strictly parsed."""

import pytest

from pinakes.errors import InvalidIdError
from pinakes.ids import ID_LENGTH, is_id, mint_doc_id, mint_kb_id, parse_doc_id, parse_kb_id


def test_minted_ids_are_canonical() -> None:
    for minted in (mint_kb_id(), mint_doc_id()):
        assert len(minted) == ID_LENGTH
        assert minted == minted.upper()
        assert parse_kb_id(minted) == minted


def test_minted_ids_are_distinct() -> None:
    assert len({mint_doc_id() for _ in range(1000)}) == 1000


def test_round_trip_preserves_the_exact_string() -> None:
    minted = mint_doc_id()
    assert parse_doc_id(minted) == minted


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        ("", "empty"),
        ("01KYCJ8ZVMBJDB4FKRJRNYS5D", "too short"),
        ("01KYCJ8ZVMBJDB4FKRJRNYS5DTX", "too long"),
        ("01KYCI8ZVMBJDB4FKRJRNYS5DT", "contains ambiguous I"),
        ("01KYCU8ZVMBJDB4FKRJRNYS5DT", "contains ambiguous U"),
        ("81KYCJ8ZVMBJDB4FKRJRNYS5DT", "timestamp past the 48-bit ceiling"),
        ("01kycj8zvmbjdb4fkrjrnys5dt", "lowercase"),
        ("research-archive", "an alias, not an ID"),
        (" 01KYCJ8ZVMBJDB4FKRJRNYS5DT", "leading whitespace"),
    ],
)
def test_malformed_ids_are_rejected(raw: str, why: str) -> None:
    with pytest.raises(InvalidIdError) as exc_info:
        parse_doc_id(raw)
    assert exc_info.value.raw == raw
    assert "document" in exc_info.value.message
    assert not is_id(raw), why


def test_lowercase_is_rejected_rather_than_normalised() -> None:
    """Two spellings of one identity would defeat the duplicate-ID check that protects §6.4."""
    minted = mint_doc_id()
    with pytest.raises(InvalidIdError):
        parse_doc_id(minted.lower())


def test_kb_and_document_errors_name_which_kind_failed() -> None:
    with pytest.raises(InvalidIdError) as kb_error:
        parse_kb_id("nope")
    with pytest.raises(InvalidIdError) as doc_error:
        parse_doc_id("nope")
    assert "KB" in kb_error.value.message
    assert "document" in doc_error.value.message


def test_errors_carry_a_remedy_that_forbids_renumbering() -> None:
    with pytest.raises(InvalidIdError) as exc_info:
        parse_doc_id("nope")
    assert "renumbering breaks every inbound link" in exc_info.value.remedy
