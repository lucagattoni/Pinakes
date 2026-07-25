"""`pnk://` URIs — how one document addresses another, across KBs.

The form is `pnk://<kb-ulid>/<doc-ulid>` and it carries **ULIDs only**. An alias would break the
moment the KB is used on a machine where that alias is absent or renamed, and links that survive
being shared are the entire point of the scheme (docs/DESIGN.md §2.2). Aliases live in the
manifest's `[[links.kb]]` and are resolved *before* a URI is written.

`pnk://self/<doc-ulid>` is accepted on input as a convenience, and is expanded to the owning KB's
ULID before anything reaches disk — a sidecar copied into another KB must keep pointing at the
document it always meant, not silently retarget itself.

That expansion is enforced by the type system rather than by discipline: parsing yields a
`ParsedUri`, which cannot be formatted; only `resolve()` — which demands the owning KB's id — turns
it into a writable `PnkUri`.
"""

from dataclasses import dataclass

from pinakes.errors import InvalidUriError
from pinakes.ids import DocId, KbId, parse_doc_id, parse_kb_id

SCHEME = "pnk://"
SELF = "self"


@dataclass(frozen=True, slots=True)
class PnkUri:
    """A fully resolved URI: both ends are ULIDs, so it is safe to write to disk."""

    kb: KbId
    doc: DocId

    def __str__(self) -> str:
        return f"{SCHEME}{self.kb}/{self.doc}"


@dataclass(frozen=True, slots=True)
class ParsedUri:
    """A parsed URI whose KB may still be `self`, and which therefore cannot be written yet."""

    kb: KbId | None
    doc: DocId

    @property
    def is_self(self) -> bool:
        return self.kb is None

    def resolve(self, *, owner: KbId) -> PnkUri:
        """Expand `self` to `owner`. An explicit KB always wins — `self` never overrides it."""
        return PnkUri(kb=self.kb if self.kb is not None else owner, doc=self.doc)


def format_uri(kb: KbId, doc: DocId) -> str:
    return str(PnkUri(kb=kb, doc=doc))


def parse(raw: str) -> ParsedUri:
    """Parse a `pnk://` URI. Rejects aliases, malformed shapes, and anything but two segments."""
    if not raw.startswith(SCHEME):
        raise InvalidUriError(raw, reason=f"a link must start with `{SCHEME}`")

    body = raw[len(SCHEME) :]
    segments = body.split("/")
    if len(segments) != 2:
        raise InvalidUriError(
            raw, reason=f"expected exactly two segments after `{SCHEME}`, found {len(segments)}"
        )

    kb_part, doc_part = segments
    if not kb_part or not doc_part:
        raise InvalidUriError(raw, reason="both the KB and the document segment must be present")

    kb = None if kb_part.lower() == SELF else parse_kb_id_for_uri(raw, kb_part)
    return ParsedUri(kb=kb, doc=parse_doc_id_for_uri(raw, doc_part))


def parse_kb_id_for_uri(raw: str, segment: str) -> KbId:
    try:
        return parse_kb_id(segment)
    except Exception as exc:
        raise InvalidUriError(
            raw,
            reason=(
                f"`{segment}` is not a KB ULID. A `pnk://` URI never carries an alias: aliases are "
                f"machine-local, live in the manifest's [[links.kb]], and are resolved to a ULID "
                f"before the link is written"
            ),
        ) from exc


def parse_doc_id_for_uri(raw: str, segment: str) -> DocId:
    try:
        return parse_doc_id(segment)
    except Exception as exc:
        raise InvalidUriError(raw, reason=f"`{segment}` is not a document ULID") from exc
