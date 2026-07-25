"""`pnk://` URIs: ULIDs only, `self` expanded before anything is written."""

import pytest

from pinakes.errors import InvalidUriError
from pinakes.ids import mint_doc_id, mint_kb_id
from pinakes.uri import SCHEME, ParsedUri, PnkUri, format_uri, parse


def test_format_and_parse_round_trip() -> None:
    kb, doc = mint_kb_id(), mint_doc_id()
    formatted = format_uri(kb, doc)
    assert formatted == f"{SCHEME}{kb}/{doc}"

    parsed = parse(formatted)
    assert parsed.kb == kb
    assert parsed.doc == doc
    assert not parsed.is_self


def test_self_parses_unresolved_and_expands_to_the_owner() -> None:
    doc, owner = mint_doc_id(), mint_kb_id()
    parsed = parse(f"{SCHEME}self/{doc}")

    assert parsed.is_self
    assert parsed.kb is None

    resolved = parsed.resolve(owner=owner)
    assert resolved == PnkUri(kb=owner, doc=doc)
    assert str(resolved) == f"{SCHEME}{owner}/{doc}"


def test_self_is_case_insensitive() -> None:
    doc = mint_doc_id()
    assert parse(f"{SCHEME}SELF/{doc}").is_self


def test_resolving_never_overrides_an_explicit_kb() -> None:
    """A sidecar copied into another KB must keep pointing where it always pointed."""
    kb, doc, other = mint_kb_id(), mint_doc_id(), mint_kb_id()
    resolved = parse(format_uri(kb, doc)).resolve(owner=other)
    assert resolved.kb == kb


def test_an_alias_is_rejected_and_the_error_says_where_aliases_live() -> None:
    doc = mint_doc_id()
    with pytest.raises(InvalidUriError) as exc_info:
        parse(f"{SCHEME}research-archive/{doc}")
    assert "[[links.kb]]" in exc_info.value.reason
    assert "never carries an alias" in exc_info.value.reason


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "research-archive/doc",
        "pnk:/01KYCJ8ZVMBJDB4FKRJRNYS5DT/01KYCJ8ZVMBJDB4FKRJRNYS5DT",
        "http://01KYCJ8ZVMBJDB4FKRJRNYS5DT/01KYCJ8ZVMBJDB4FKRJRNYS5DT",
        "pnk://01KYCJ8ZVMBJDB4FKRJRNYS5DT",
        "pnk://01KYCJ8ZVMBJDB4FKRJRNYS5DT/",
        "pnk:///01KYCJ8ZVMBJDB4FKRJRNYS5DT",
        "pnk://01KYCJ8ZVMBJDB4FKRJRNYS5DT/01KYCJ8ZVMBJDB4FKRJRNYS5DT/extra",
        "pnk://01KYCJ8ZVMBJDB4FKRJRNYS5DT/self",
        "pnk://self/self",
        "pnk://01KYCJ8ZVMBJDB4FKRJRNYS5DT/01kycj8zvmbjdb4fkrjrnys5dt",
    ],
)
def test_malformed_uris_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidUriError) as exc_info:
        parse(raw)
    assert exc_info.value.raw == raw
    assert "pnk://<kb-ulid>/<doc-ulid>" in exc_info.value.remedy


def test_an_unresolved_uri_cannot_be_formatted() -> None:
    """The type system, not discipline, is what stops a `self` link reaching disk."""
    parsed = parse(f"{SCHEME}self/{mint_doc_id()}")
    assert isinstance(parsed, ParsedUri)
    assert not hasattr(parsed, "__str__") or "pnk://" not in str(parsed)


def test_resolved_uris_are_hashable_and_comparable() -> None:
    kb, doc = mint_kb_id(), mint_doc_id()
    assert PnkUri(kb=kb, doc=doc) == PnkUri(kb=kb, doc=doc)
    assert len({PnkUri(kb=kb, doc=doc), PnkUri(kb=kb, doc=doc)}) == 1
