"""`<file>.pnk.yaml` — the document's identity and metadata, next to the document itself.

A sidecar is **committed, user-editable, and owned by the user** (docs/DESIGN.md §2.2). Three
consequences shape this module:

* **Unknown keys are preserved.** A sidecar is a file a person may add their own fields to. Reading
  one and writing it back must never silently drop what Pinakes does not understand — that is data
  loss dressed up as normalisation.
* **`id` is permanent.** It is minted once, at first ingest, and never regenerated. Writing a
  sidecar that already has an id keeps that id.
* **Links are resolved before they are written.** Aliases and `self` are expanded to ULIDs on the
  way in (§2.2), so what lands on disk survives being shared.

There is deliberately no `content_hash` here: change detection is the index's job, and a hash in a
committed file would dirty two files per edit and go stale whenever sync had not run (§2.2).

**Written through `ruamel.yaml`, in round-trip mode, at YAML 1.2.** Two things follow, and both are
the point rather than a side effect (`plans/20260731_0602-decision-ruamel-yaml.md`):

* **A rewrite preserves comments, quoting, block scalars and blank lines**, because `write()`
  reconciles the known keys *into the document that was read* instead of rendering a fresh one.
* **`country: NO` stays `NO`.** Under YAML 1.1 it was read as `False` and written back as `false` —
  along with `0755` → `493` and `1:30` → `90` — silently, on keys this module documents as
  round-tripped untouched. 1.2 reads **three of the four** as the strings they visibly are; `0755`
  becomes int **755**, not the string and not PyYAML's octal 493, and survives on disk only because
  ruamel preserves the source form. The index still stores a number. Corruption reduced, not
  eliminated.
"""

import json
import os
import warnings
from copy import deepcopy
from dataclasses import dataclass, field, replace
from io import StringIO
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML, YAMLError
from ruamel.yaml.comments import CommentedMap, TaggedScalar
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import ReusedAnchorWarning
from ruamel.yaml.nodes import ScalarNode
from ruamel.yaml.resolver import VersionedResolver
from ruamel.yaml.scalarstring import SingleQuotedScalarString

from pinakes.errors import InvalidIdError, InvalidUriError, SidecarError
from pinakes.ids import DocId, KbId, mint_doc_id, parse_doc_id
from pinakes.uri import ParsedUri, PnkUri
from pinakes.uri import parse as parse_uri

SIDECAR_SUFFIX = ".pnk.yaml"

# Keys this module understands. Anything else is preserved verbatim under `extra`.
KNOWN_KEYS = frozenset({"id", "title", "tags", "created", "links", "provenance"})


def _yaml() -> YAML:
    """A **fresh** round-trip parser, per call. Never one shared instance.

    Sharing one was specified, and measured at 282 µs against 399 µs. It is a cross-document
    corruption bug: ruamel keeps the `%YAML` directive from the last `load()` on the instance and
    applies it to every later load *and* dump. Read a sidecar that carries `%YAML 1.1`, then write
    an unrelated one that never did, and it comes back with a `%YAML 1.1` header injected and
    `country: NO` rewritten to `false` — the exact corruption this module exists to prevent,
    reintroduced across documents in exchange for 117 microseconds. Freshly minted sidecars are
    contaminated the same way.

    Nothing softer works: resetting `version` after the load still emits the directive, pinning it
    up front is overwritten by the next load, and nulling `_yaml_version` between loads is not
    enough. A fresh instance is the fix.

    Both settings below are load-bearing. Without `preserve_quotes` a quoted scalar comes back bare
    on the next write; `width` at ruamel's default of 80 folds a long value with spaces across
    lines, changing a file nobody edited. 4096 exceeds what PyYAML did rather than matching it.
    """
    parser = YAML()  # round-trip, YAML 1.2
    parser.preserve_quotes = True
    parser.width = 4096
    return parser


_RESOLVERS = (VersionedResolver((1, 1)), VersionedResolver((1, 2)))
_STRING_TAG = "tag:yaml.org,2002:str"


def needs_quoting(value: str) -> bool:
    """Whether a scalar **Pinakes is writing** would be read back as something other than a string.

    Keyed on the value being assigned, never on whether the document is new: `skeleton()` derives a
    title from the filename stem, so `NO.md` would mint a bare `title: NO` that any 1.1 reader takes
    as `False` — and `pnk link --rel no` is the same hazard on a file that already exists.

    Both YAML versions, because the file may be read by something that is not Pinakes. 1.2 alone
    would leave `NO` bare, which is correct for 1.2 and wrong for every 1.1 reader in the world.
    Scalars Pinakes did *not* author are left exactly as the user wrote them.
    """
    return any(
        resolver.resolve(ScalarNode, value, (True, False)) != _STRING_TAG for resolver in _RESOLVERS
    )


def _authored(value: str) -> str | SingleQuotedScalarString:
    return SingleQuotedScalarString(value) if needs_quoting(value) else value


def _json_encodable(path: Path, mapping: dict[str, Any]) -> None:
    """Refuse a mapping the index could not store — **the assembled mapping, not each value**.

    `store.dumps_metadata` is `json.dumps(metadata, sort_keys=True, ensure_ascii=False)`, and
    `_metadata()` hands it `tags`, `provenance` and every `extra` key **at once** — so this is
    called with that same union, not with the parts. Two escapes come from getting the argument
    wrong: checking each *value* accepts `{123: v, abc: w}`, both of which encode fine on their own;
    and checking `extra` *alone* accepts a uniformly int-keyed `{1: a}`, which only becomes mixed
    once `tags` and `provenance` join it. The failure is a comparison between keys that meet
    nowhere else.

    **This keeps behaviour equivalent; it is not a new refusal.** PyYAML rejects an unknown tag
    today as a clean `SidecarError` (`ConstructorError` subclasses `YAMLError`); ruamel returns a
    `TaggedScalar` instead, so without this the swap alone would turn that clean error into a
    traceback out of `pnk sync`.

    Two residuals, both identical under PyYAML today and so neither a regression:
    `.nan`/`.inf` encode as `NaN`/`Infinity`, which no conforming JSON reader accepts; and a
    **uniformly** non-string-keyed mapping is accepted and silently coerced (`{1: a, 2: b}` becomes
    `{"1": "a", "2": "b"}`, at any depth). `sort_keys=True` catches **mixed**-type keys only.
    """
    try:
        json.dumps(dict(mapping), sort_keys=True, ensure_ascii=False)
    except TypeError as exc:
        # **A key failure and a value failure are different sentences.** Reported as one, a
        # non-string key surfaced as "has a value the index cannot store" followed by the raw
        # `'<' not supported between instances of 'int' and 'str'` — naming neither the key nor
        # anything the user can act on, which is what `_describe` exists to prevent one level up.
        bad_key = _first_non_string_key(mapping)
        if bad_key is not None:
            raise SidecarError(
                path,
                f"has a key that is not a string: {bad_key[0]!r} ({_describe(bad_key[0])})",
                remedy=(
                    "The index stores sidecar metadata as JSON, whose keys must be strings. "
                    "Quote "
                    f'it — `"{bad_key[0]}":` rather than `{bad_key[0]}:`' + bad_key[1] + "."
                ),
            ) from exc
        offending = next(
            (
                f"{key!r} ({_describe(value)})"
                for key, value in mapping.items()
                if not _encodes(value)
            ),
            str(exc),
        )
        raise SidecarError(
            path,
            f"has a value the index cannot store: {offending}",
            remedy=(
                "The index stores sidecar metadata as JSON, so every value in the sidecar "
                "must be JSON-encodable, and its keys must all be strings. A tag on a "
                "*scalar* (`!!binary`, `!!set`, "
                "`!!timestamp`, `!!str`, or one of your own), a bare date, or a mapping mixing "
                "string and non-string keys will not encode — a custom tag on a mapping or a "
                "sequence is fine, because it serialises. Quote it, or drop the tag."
            ),
        ) from exc


def _first_non_string_key(mapping: dict[Any, Any], trail: str = "") -> tuple[object, str] | None:
    """The first key that is not a string, and where it sits — searched at every depth.

    `json.dumps(sort_keys=True)` raises only when the keys of one mapping are of *mixed* types, so
    the exception says nothing about which key is at fault, and a uniformly non-string mapping does
    not raise at all — it is silently coerced. Finding the key ourselves reports the real problem in
    both cases.
    """
    for key, value in mapping.items():
        if not isinstance(key, str):
            return key, trail
        if isinstance(value, dict):
            found = _first_non_string_key(cast(dict[Any, Any], value), f"{trail}, under `{key}`")
            if found is not None:
                return found
    return None


def _encodes(value: Any) -> bool:
    try:
        json.dumps(value, sort_keys=True, ensure_ascii=False)
    except TypeError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class Link:
    to: PnkUri
    rel: str


@dataclass(frozen=True, slots=True)
class Sidecar:
    id: DocId
    title: str | None = None
    tags: tuple[str, ...] = ()
    created: str | None = None
    links: tuple[Link, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict[str, Any])
    extra: dict[str, Any] = field(default_factory=dict[str, Any])
    """Keys Pinakes does not know. Round-tripped untouched — the file belongs to the user."""

    present: frozenset[str] = frozenset()
    """Known keys the file actually carried.

    An explicit `tags: []` is not the same as no `tags` at all: the first is something the user
    wrote and expects to still be there. Without this, writing back would quietly delete it.
    """

    owner: KbId | None = field(default=None, compare=False, repr=False)
    """The KB this sidecar was read against — what `self` in a link means.

    `write()` needs it to recognise that a node still saying `pnk://self/X` is the same link
    `read()` handed back as `pnk://<owner>/X`. `None` on a freshly minted sidecar, which has no
    document to reconcile against.
    """

    original: CommentedMap | None = field(default=None, compare=False, repr=False)
    """The document this sidecar was read from, comments and all — `None` when freshly minted.

    `write()` reconciles the known keys *into* this rather than rendering a new document, which is
    the only way comments, quoting and blank lines survive a rewrite.

    `compare=False`: two sidecars with the same fields are the same sidecar whether or not one of
    them remembers a file. It is also excluded from `repr`, being a whole document.
    """


def sidecar_path(document: Path) -> Path:
    """`docs/notes.md` → `docs/notes.md.pnk.yaml`. The suffix is appended, never substituted."""
    return document.with_name(document.name + SIDECAR_SUFFIX)


def is_sidecar(path: Path) -> bool:
    return path.name.endswith(SIDECAR_SUFFIX)


def document_for(sidecar: Path) -> Path:
    if not is_sidecar(sidecar):
        raise SidecarError(sidecar, f"is not a {SIDECAR_SUFFIX} file")
    return sidecar.with_name(sidecar.name[: -len(SIDECAR_SUFFIX)])


def read(path: Path, *, owner: KbId) -> Sidecar:
    """Read and validate a sidecar. `owner` expands `self` links (§2.2)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SidecarError(path, f"cannot be read: {exc.strerror}") from exc
    except UnicodeDecodeError as exc:
        raise SidecarError(path, "is not valid UTF-8") from exc

    try:
        # **The warning is promoted to an error here, not left to the ambient filter.** A repeated
        # anchor name was a clean `SidecarError` before the swap (PyYAML raises `ComposerError`,
        # which is a `YAMLError`); ruamel accepts it, resolves every alias to the *last* anchor of
        # that name — so `a: &dup 1`, `b: &dup 2`, `c: *dup` silently makes `c` equal 2 — and says
        # so only through a `ReusedAnchorWarning` on stderr. That warning is not a `YAMLError`, so
        # the handlers below never see it; and under `filterwarnings = ["error"]`, which this
        # project's pytest config sets, it escapes as a bare `ReusedAnchorWarning` traceback
        # instead. Catching it explicitly makes the outcome the same everywhere, whatever the
        # caller's warning filters happen to be.
        with warnings.catch_warnings():
            warnings.simplefilter("error", ReusedAnchorWarning)
            loaded: object = _yaml().load(raw)
    except ReusedAnchorWarning as exc:
        raise SidecarError(
            path,
            f"reuses an anchor name: {exc}",
            remedy=(
                "Give each `&anchor` its own name. Every `*alias` to a repeated name resolves to "
                "the last one, so which value an alias meant is not recoverable."
            ),
        ) from exc
    except DuplicateKeyError as exc:
        # Caught ahead of `YAMLError`, which it subclasses. PyYAML took the last of a repeated key
        # silently; ruamel refuses, and its own message ends with a URL for suppressing the check —
        # advice Pinakes does not want followed, since which value was meant is exactly what nobody
        # can know.
        raise SidecarError(
            path,
            f"repeats a key: {exc.problem or exc}".split("\nTo suppress")[0],
            remedy="Delete the duplicate. Which of the two values was meant is not recoverable.",
        ) from exc
    except YAMLError as exc:
        raise SidecarError(path, f"is not valid YAML: {exc}") from exc

    if loaded is None:
        raise SidecarError(path, "is empty", remedy="Every sidecar must carry at least an `id`.")
    if not isinstance(loaded, dict):
        raise SidecarError(path, f"must be a mapping, found {type(loaded).__name__}")

    data = cast(CommentedMap, loaded)
    tags = _tags(path, data)
    provenance = deepcopy(_mapping(path, data, "provenance"))
    extra = deepcopy({key: value for key, value in data.items() if key not in KNOWN_KEYS})
    # **Checked over the shape `_metadata()` assembles**, not over `extra` and `provenance`
    # separately. A uniformly int-keyed `extra` passes on its own — `{1: "a"}` sorts fine — and
    # `_metadata()` then merges it with the string keys `tags` and `provenance`, making the union
    # mixed and `json.dumps(sort_keys=True)` raise out of `pnk sync`. Validating the parts is not
    # validating the whole; the failure is a comparison *between* keys that only meet here.
    _json_encodable(path, {"tags": list(tags), "provenance": dict(provenance), **extra})
    return Sidecar(
        id=_id(path, data),
        title=_optional_str(path, data, "title"),
        tags=tags,
        created=_optional_str(path, data, "created"),
        links=_links(path, data, owner=owner),
        # **Copies, not the live nodes.** `_mapping` would otherwise hand back the very node stored
        # in `original`, and `dataclasses.replace` shares it between the pre- and post-extraction
        # sidecar — so `write()` would merge a mapping into itself. That is a silent no-op, not a
        # crash, which is the worst way for it to be wrong.
        provenance=provenance,
        extra=extra,
        present=frozenset(key for key in KNOWN_KEYS if key in data),
        owner=owner,
        original=data,
    )


def _merge_mapping(existing: Any, incoming: dict[str, Any], *, delete_missing: bool = True) -> None:
    """Merge `incoming` into `existing` in place, key by key, **at every depth**.

    Never replaces a mapping node that already exists, because ruamel binds a comment to the
    **preceding** key — so a comment describing a *sibling* of `extraction` lives inside the
    `extraction` node and dies with it. One level of merging is not enough:
    `with_extraction_provenance` builds a plain `dict` for `extraction`, and assigning that whole
    dict over the loaded node takes the comment with it.

    A key absent from `incoming` **is deleted at the top level only** — `delete_missing` is not
    passed down. The deletion is required there: `without_extraction_provenance` returns a
    provenance with no `extraction`, and a merge that only assigns would leave the stale paid claim
    in place, silently failing the `--force` reversal DESIGN §2.2 treats as an invariant. Recursing
    with it would strip the user's own keys from *inside* `extraction`, because
    `with_extraction_provenance` builds a plain four-key replacement — and CLAUDE.md says a paid
    extraction rewrites that block additively, "never any other key". Measured: a `reviewed_by: me`
    written beside `content_hash` was destroyed by the unbounded version.
    """
    if delete_missing:
        for key in [key for key in existing if key not in incoming]:
            del existing[key]
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            _merge_mapping(existing[key], cast(dict[str, Any], value), delete_missing=False)
        else:
            existing[key] = value


def _merge_links(existing: Any, links: tuple[Link, ...], *, owner: KbId | None) -> None:
    """Reconcile the `links` block. Three rules, each of which a shipped version of this got wrong.

    **(a) Resolve before comparing.** `read()` expands `pnk://self/X` to `pnk://<kb-ulid>/X`, so a
    loaded entry's `to` never equals the raw text still in the node. Comparing raw text found no
    match, deleted the entry and appended a bare replacement — reproduced on a committed corpus
    sidecar, on a **no-op write**, taking the user's comment and their unknown per-link keys with it
    and moving the entry to the end.

    **(b) Multiplicity, never a set.** `{(to, rel), …}` collapses two identical entries and the
    second is then deleted — three links in, one out. `_links()` does not deduplicate; only the
    index's primary key does. So `wanted` is a **list**, consumed by `remove`.

    **(c) A `rel` edit is an in-place assignment, not delete-and-append.** Keying on the whole
    `(to, rel)` pair makes the pair the entire content of an entry, so no matched entry is ever
    updated and every edit becomes a delete plus an append — which by the pinned limitation below
    misattributes one comment and destroys another. Match on the resolved `to`, preferring an entry
    whose `rel` already agrees, and assign `rel` into the node otherwise.

    Nothing else inside a matched entry is touched: `_links()` surfaces `to` and `rel` alone, so a
    delete-what-is-missing merge would destroy the unknown per-link keys DESIGN §2.2 round-trips.
    """
    wanted = list(links)
    pending: list[tuple[int, dict[str, Any], str, str, str]] = []
    # **Deleted by index, highest first — never by slice assignment.** `existing[:] = keep` wipes
    # `CommentedSeq.ca.items` outright, taking every comment in the sequence with it; `del` shifts
    # the surviving indices and their comments along with them. Measured: after a slice assignment
    # `ca.items` is `{}`, after a `del` it is `{0: '# first', 1: '# third'}`.
    for index in range(len(cast(list[object], existing)) - 1, -1, -1):
        # One cast at the boundary, as `link_density_gate.py` does: a `CommentedMap` is a
        # `dict[Any, Any]`, and letting that `Any` leak makes every later subscript unknown to the
        # strict checker — which is how a module ends up carrying per-line suppressions.
        raw_entry: object = existing[index]
        if not isinstance(raw_entry, dict):
            del existing[index]
            continue
        entry = cast(dict[str, Any], raw_entry)
        written, rel = str(entry.get("to")), str(entry.get("rel"))
        resolved = _resolved_uri(written, owner)
        pending.append((index, entry, written, resolved, rel))

    # **Two passes, not one pass with two tiers.** Matching each entry to an exact `(to, rel)` and
    # otherwise falling back to `to` alone, in a single walk, lets a later entry's *fallback*
    # consume the exact match an earlier entry was owed: editing one relation where two links share
    # a `to` swapped both relations and left both comments on the wrong entries — the defect this
    # rule exists to prevent. Every exact match is claimed first; only then do the leftovers pair
    # up by `to` alone, which is what turns a `rel` edit into an in-place assignment.
    matched: dict[int, Link] = {}
    for index, _entry, _written, resolved, rel in pending:
        exact = next(
            (link for link in wanted if str(link.to) == resolved and link.rel == rel), None
        )
        if exact is not None:
            wanted.remove(exact)
            matched[index] = exact
    for index, _entry, _written, resolved, _rel in pending:
        if index in matched:
            continue
        loose = next((link for link in wanted if str(link.to) == resolved), None)
        if loose is not None:
            wanted.remove(loose)
            matched[index] = loose

    for index, entry, written, _resolved, rel in pending:
        match = matched.get(index)
        if match is None:
            del existing[index]
            continue
        if written != str(match.to):
            entry["to"] = _authored(str(match.to))  # expand `self`, keeping the entry itself
        if rel != match.rel:
            entry["rel"] = _authored(match.rel)  # an edit, in place — never delete-and-append
    for link in wanted:  # never seen in the document — appended, in the order they were given
        existing.append(CommentedMap(to=_authored(str(link.to)), rel=_authored(link.rel)))


def _resolved_uri(written: str, owner: KbId | None) -> str:
    """The URI a node's `to` text denotes, with `self` expanded — what `read()` already returned."""
    if owner is None:
        return written
    try:
        return str(resolve_link(written, "", owner=owner).to)
    except InvalidUriError:
        return written


def _unchanged(existing: object, incoming: object) -> bool:
    """Whether a key's reconciled value is already exactly what the document holds.

    **Assign a known key only when its value actually changed.** This is what makes byte-identity
    structural rather than incidental: nothing in Pinakes edits `tags`, so under this rule its node
    is never touched at all, and the same holds for every key a given write does not modify.

    Compared through `str` for scalars, because the document's entries may be `ScalarString`
    subclasses carrying their original quoting — equal to a plain `str`, but not interchangeable
    with one. Scalars are safe either way (reassigning the same string keeps its trailing comment,
    verified); sequences and mappings are not, which is what this is for.
    """
    if isinstance(existing, list) and isinstance(incoming, list):
        left = cast(list[object], existing)
        right = cast(list[object], incoming)
        return len(left) == len(right) and all(
            _unchanged(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(existing, dict) and isinstance(incoming, dict):
        left_map = cast(dict[object, object], existing)
        right_map = cast(dict[object, object], incoming)
        return set(left_map) == set(right_map) and all(
            _unchanged(left_map[key], right_map[key]) for key in left_map
        )
    if isinstance(existing, list | dict) or isinstance(incoming, list | dict):
        return False  # one is a container and the other is not, or they are of different kinds
    if isinstance(existing, str) and isinstance(incoming, str):
        return str(existing) == str(incoming)
    # Scalars, by type and representation. `existing == incoming` is `Any` here — one side comes
    # out of a `CommentedMap` — and comparing through `repr` keeps this typed without a
    # suppression, while distinguishing `1` from `True` and from `1.0`, which `==` does not.
    return type(existing) is type(incoming) and repr(existing) == repr(incoming)


def _describe(value: object) -> str:
    """What a wrong value *is*, in words a person can act on.

    `type(value).__name__` names a ruamel internal on exactly the inputs this increment made
    reachable — `TaggedScalar`, `ScalarFloat`, `OctalInt` — so three of its headline breaking
    changes would have surfaced as class names from a library the user never chose. The remedy
    matters more than the type: what they wrote needs quoting, or its tag dropped.
    """
    if isinstance(value, TaggedScalar):
        return "a tagged value"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int):
        return "a number"
    if isinstance(value, float):
        return "a number"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "a mapping"
    if value is None:
        return "nothing"
    return f"a {type(value).__name__}"


_QUOTE_IT = (
    "Quote it — YAML 1.2 reads an unquoted `1e3`, `0o17` or `NO` as a number or a boolean, and a "
    "tagged value (`!!str`, `!!binary`, or one of your own) is not a string either. Wrapping it in "
    "quotes makes it the string it looks like."
)


def _merge_tags(existing: Any, tags: tuple[str, ...]) -> None:
    """Reconcile `tags` **by value** — match, append, delete the removed — the same shape `links`
    uses for `to`.

    Not "a list of plain strings with no per-entry comments": ruamel stores a comment on a `tags`
    entry exactly as it does on a `links` entry, and replacing the sequence wholesale destroys it.
    A comment on a *deleted* entry is still lost, in either sequence.
    """
    wanted = list(tags)
    # Highest index first, and `del` rather than a slice assignment — see `_merge_links`.
    for index in range(len(cast(list[object], existing)) - 1, -1, -1):
        value = str(cast(list[object], existing)[index])
        if value in wanted:
            wanted.remove(value)
        else:
            del existing[index]
    for tag in wanted:
        existing.append(_authored(tag))


def _known(sidecar: Sidecar) -> dict[str, Any]:
    """The known keys this sidecar would write, in canonical order, omitting those it does not."""
    document: dict[str, Any] = {"id": _authored(str(sidecar.id))}
    if sidecar.title is not None or "title" in sidecar.present:
        document["title"] = _authored(sidecar.title) if sidecar.title is not None else None
    if sidecar.tags or "tags" in sidecar.present:
        document["tags"] = [_authored(tag) for tag in sidecar.tags]
    if sidecar.created is not None or "created" in sidecar.present:
        document["created"] = _authored(sidecar.created) if sidecar.created is not None else None
    if sidecar.links or "links" in sidecar.present:
        # `_authored` here too: this is the branch taken when `links` first appears and on a mint,
        # which is exactly the path `pnk link` follows on a sidecar that has none yet — so
        # `--rel no` would otherwise land bare and read as `False` to any YAML 1.1 reader. The
        # merge path quoted; this one did not, and it is the common case.
        document["links"] = [
            {"to": _authored(str(link.to)), "rel": _authored(link.rel)} for link in sidecar.links
        ]
    if sidecar.provenance or "provenance" in sidecar.present:
        document["provenance"] = dict(sidecar.provenance)
    return document


def write(path: Path, sidecar: Sidecar) -> None:
    """Write a sidecar, preserving everything about the file this one was read from.

    When `sidecar.original` is present the known keys are **reconciled into it** — comments,
    quoting, blank lines and the user's own key order all survive, because the document being
    dumped is the document that was parsed. A freshly minted sidecar has no original and is
    rendered in canonical order instead.
    """
    known = _known(sidecar)
    if sidecar.original is None:
        document = CommentedMap()
        for key, value in known.items():
            document[key] = value
        for key in sorted(sidecar.extra):  # canonical order, for minting only
            document[key] = sidecar.extra[key]
    else:
        document = sidecar.original
        for key, value in known.items():
            if key not in document:
                # **Appended at the end, never inserted at its canonical position.** `provenance`
                # first appears on a paid extraction; inserting it between the last known key and
                # the first unknown one would put it directly above a comment that introduces that
                # unknown key — and ruamel binds a comment to its preceding key, so the comment
                # would end up reading as though it described `provenance`. A larger diff beats a
                # misplaced comment, in the increment whose whole purpose is not to misplace them.
                document[key] = value
            elif _unchanged(document.get(key), value):
                continue  # the node already says this; touching it can only lose a comment
            elif document.get(key) is None and not value:
                # **An empty known key stays as the user wrote it.** `tags:` and `provenance:` with
                # nothing under them read back as `()` and `{}` — identical to `tags: []` and
                # `provenance: {}` in every way Pinakes can observe — so rewriting them changes
                # bytes for no meaning, against a promise stated as byte-identity. Reached on the
                # common path only from L6: before `pnk link`, `write()` over an existing file ran
                # on the paid-PDF path alone. Guarded on `not value` so a *first* link into a null
                # `links:` still writes; that case has something to say.
                #
                # `if key not in document` runs first, so this only ever sees a key that is
                # **present and null** — never an absent one. One latent case, reachable by no
                # caller today: a null `title:` on disk with `title=""` supplied would be skipped
                # rather than written. `read()` returns `""` only from a non-null node, which this
                # branch does not match, so it stays latent until something constructs a `Sidecar`
                # with an empty-string field by hand.
                continue
            elif key == "links" and isinstance(document.get(key), list):
                _merge_links(document[key], sidecar.links, owner=sidecar.owner)
            elif key == "tags" and isinstance(document.get(key), list):
                _merge_tags(document[key], sidecar.tags)
            elif isinstance(value, dict) and isinstance(document.get(key), dict):
                _merge_mapping(document[key], cast(dict[str, Any], value))
            else:
                document[key] = value
        # A known key that left `present` goes; `present` names top-level keys and nothing nested.
        for key in [key for key in document if key in KNOWN_KEYS and key not in known]:
            del document[key]

    stream = StringIO()
    _yaml().dump(document, stream)
    rendered = stream.getvalue()

    # **Written through a symlink, not over it.** `os.replace` onto a symlink destroys the link and
    # leaves a regular file, with the real sidecar untouched somewhere else still holding the old
    # text — the user's own arrangement dismantled silently. `create()` refuses this case outright
    # because minting over *anything* already there is unrecoverable; a rewrite has no such problem
    # and simply follows it. Reached routinely only from L6: `pnk link` is the first command a
    # person points at a file of their choosing.
    target = path.resolve() if path.is_symlink() else path

    # Atomically: write beside the target, then rename over it. A truncated sidecar would lose the
    # document's permanent ULID, and every inbound pnk:// link with it — the one failure in this
    # module that no later command could repair.
    temporary = target.with_name(f"{target.name}.new")
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def create(path: Path, sidecar: Sidecar) -> None:
    """Write a sidecar for a document that has none — and refuse if a file is already there.

    `write` overwrites by design: I5 merges `provenance.extraction` into an existing sidecar, which
    is a read-modify-write of that same file keeping that same id. Minting is the opposite case.
    The id it carries has just been minted, so writing it over an existing sidecar replaces a
    **permanent** ULID with a different one — and every inbound `pnk://` link points at the old one,
    with no migration machinery by design (§2.2). That is unrecoverable rather than merely wrong,
    which is why the refusal lives here, at the write, rather than only in the one caller that
    happens to reach it today.

    Reachable whenever a sidecar exists but will not parse: `sync.walk_sources` drops an unreadable
    sidecar from the walk, the document then looks like one that was never ingested, and the mint
    path writes over the file still holding its id. Found 20260729 while hand-authoring a corpus
    with one malformed link URI — `pnk sync` reported success with no failures, and `pnk doctor`
    afterwards reported every sidecar readable and no duplicate ids, because the evidence had been
    overwritten by the thing that destroyed it.
    """
    # `is_symlink` as well as `exists`, which follows symlinks and so reports False for a dangling
    # one — leaving `os.replace` free to quietly turn the link into a regular file. Nothing holding
    # a ULID is lost either way, but "refuse where something is already there" is the rule, and a
    # predicate that means something narrower than the rule it enforces drifts apart from it later.
    if path.exists() or path.is_symlink():
        raise SidecarError(
            path,
            "already exists, so a freshly minted sidecar cannot be written over it",
            remedy=(
                "It may hold the document's permanent ULID, which nothing can recompute. Repair "
                "the file rather than deleting it — `pnk doctor` names the parse error. Delete it "
                "only if the id itself is unrecoverable and no other document links to it."
            ),
        )
    write(path, sidecar)


def minted_title(document: Path) -> str:
    """The title `skeleton` mints from a filename when the document offers none.

    **A function rather than an inline expression because two callers need to agree exactly.**
    `pnk doctor` reports documents still carrying a minted title, and it can only do that by
    recomputing what minting *would* produce — so a second copy of this rule would make the check
    quietly wrong the day either copy changed, in the direction of reporting nothing.
    """
    return document.stem.replace("-", " ").replace("_", " ")


def skeleton(document: Path, *, title: str | None = None, created: str | None = None) -> Sidecar:
    """The sidecar minted for a newly ingested document: an id, and as little else as possible."""
    return Sidecar(
        id=mint_doc_id(),
        title=title if title is not None else minted_title(document),
        created=created,
    )


def with_extraction_provenance(
    sidecar: Sidecar, *, backend: str, fingerprint: str, extracted: str, content_hash: str
) -> Sidecar:
    """Merge `provenance.extraction` into an existing sidecar, preserving every other key (I5).

    `provenance` is already a free-form mapping (`Sidecar.provenance`), so this needs no new field
    — only an additive read-merge-write, which is the whole reason `--rebuild` can seed
    `documents.extraction_backend`/`extraction_fingerprint` from the sidecar rather than losing
    them the moment the index is discarded (docs/DESIGN.md §2.2, decision 11).

    `content_hash` is the file's hash *at the time of this paid extraction* — deliberately not the
    same thing DESIGN §2.2 refuses to store generally (a hash that dirties the sidecar on every
    edit): this one changes only when a paid extraction itself runs, and it is what lets a later
    sync answer "has this changed since" directly from the sidecar, without depending on whether
    `extract/cache.py`'s entry (or any prior local index row) still happens to exist.
    """
    merged_provenance = {
        **sidecar.provenance,
        "extraction": {
            "backend": backend,
            "fingerprint": fingerprint,
            "extracted": extracted,
            "content_hash": content_hash,
        },
    }
    # `replace`, never a hand-enumerated constructor: this dataclass has gained a field before
    # (`original`), and every field a rebuilder forgets is silently dropped rather than flagged.
    return replace(sidecar, provenance=merged_provenance, present=sidecar.present | {"provenance"})


def without_extraction_provenance(sidecar: Sidecar) -> Sidecar:
    """Clear a `provenance.extraction` claim that just became false.

    The one caller of this is `--force` plus an explicit free `--extract` overwriting what was a
    paid extraction (decision 9): the file is no longer paid-protected, and leaving the old claim
    in place would tell the next sync — or a different clone reading the same committed sidecar —
    that it still is.
    """
    remaining = {key: value for key, value in sidecar.provenance.items() if key != "extraction"}
    present = sidecar.present | {"provenance"} if remaining else sidecar.present - {"provenance"}
    return replace(sidecar, provenance=remaining, present=present)


def extraction_provenance(sidecar: Sidecar) -> tuple[str, str, str] | None:
    """`(backend, fingerprint, content_hash)` if this sidecar records a prior extraction, else
    `None`.

    Deliberately tolerant of a malformed or hand-edited `provenance.extraction` block: a sidecar
    is user-owned (module docstring), and a document whose provenance cannot be read back is
    treated as never-extracted rather than failing the whole sync over a decoration field.
    """
    raw_extraction: object = sidecar.provenance.get("extraction")
    if not isinstance(raw_extraction, dict):
        return None
    extraction = cast(dict[str, Any], raw_extraction)
    backend = extraction.get("backend")
    fingerprint = extraction.get("fingerprint")
    content_hash = extraction.get("content_hash")
    if (
        not isinstance(backend, str)
        or not isinstance(fingerprint, str)
        or not isinstance(content_hash, str)
    ):
        return None
    return backend, fingerprint, content_hash


def resolve_link(raw: str, rel: str, *, owner: KbId) -> Link:
    """Parse one link, expanding `self` against the owning KB before it can be stored."""
    parsed: ParsedUri = parse_uri(raw)
    return Link(to=parsed.resolve(owner=owner), rel=rel)


def find_duplicate_ids(sidecars: dict[Path, Sidecar]) -> dict[DocId, list[Path]]:
    """Group paths by id, keeping only ids claimed more than once.

    §6.4 makes this a hard error rather than a renumbering: two documents claiming one id means
    every inbound link to it is ambiguous, and renumbering would break links that were fine.
    """
    by_id: dict[DocId, list[Path]] = {}
    for path, sidecar in sidecars.items():
        by_id.setdefault(sidecar.id, []).append(path)
    return {doc_id: sorted(paths) for doc_id, paths in by_id.items() if len(paths) > 1}


def _id(path: Path, data: dict[str, Any]) -> DocId:
    raw: object = data.get("id")
    if raw is None:
        raise SidecarError(
            path,
            "has no `id`",
            remedy="Every sidecar carries the document's permanent ULID (docs/DESIGN.md §2.2).",
        )
    if not isinstance(raw, str):
        raise SidecarError(path, f"`id` must be a string, found {_describe(raw)}", remedy=_QUOTE_IT)
    try:
        return parse_doc_id(raw)
    except InvalidIdError as exc:
        raise SidecarError(
            path,
            f"`id` is not a ULID: {raw!r}",
            remedy=(
                "Restore the original id — it is permanent, and every inbound pnk:// link "
                "depends on it."
            ),
        ) from exc


def _optional_str(path: Path, data: dict[str, Any], key: str) -> str | None:
    raw: object = data.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise SidecarError(
            path, f"`{key}` must be a string, found {_describe(raw)}", remedy=_QUOTE_IT
        )
    return raw


def _tags(path: Path, data: dict[str, Any]) -> tuple[str, ...]:
    raw: object = data.get("tags")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise SidecarError(path, "`tags` must be a list of strings")
    tags: list[str] = []
    for item in cast(list[object], raw):
        if not isinstance(item, str):
            raise SidecarError(
                path, f"`tags` must be strings, found {_describe(item)}", remedy=_QUOTE_IT
            )
        tags.append(item)
    return tuple(tags)


def _mapping(path: Path, data: dict[str, Any], key: str) -> dict[str, Any]:
    raw: object = data.get(key)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SidecarError(path, f"`{key}` must be a mapping")
    return cast(dict[str, Any], raw)


def _links(path: Path, data: dict[str, Any], *, owner: KbId) -> tuple[Link, ...]:
    raw: object = data.get("links")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise SidecarError(path, "`links` must be a list")

    links: list[Link] = []
    for index, item in enumerate(cast(list[object], raw)):
        where = f"`links[{index}]`"
        if not isinstance(item, dict):
            raise SidecarError(path, f"{where} must be a mapping with `to` and `rel`")
        entry = cast(dict[str, Any], item)
        target: object = entry.get("to")
        rel: object = entry.get("rel")
        if not isinstance(target, str):
            raise SidecarError(path, f"{where} needs a `to` URI")
        if not isinstance(rel, str) or not rel.strip():
            raise SidecarError(path, f"{where} needs a non-empty `rel`")
        try:
            links.append(resolve_link(target, rel, owner=owner))
        except (InvalidUriError, InvalidIdError) as exc:
            raise SidecarError(path, f"{where}: {exc.message}", remedy=exc.remedy) from exc
    return tuple(links)
