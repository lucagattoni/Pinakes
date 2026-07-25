"""`<file>.pnk.yaml` — the document's identity and metadata, next to the document itself.

A sidecar is **committed, user-editable, and owned by the user** (docs/DESIGN.md §2.2). Three
consequences shape this module:

* **Unknown keys are preserved.** A sidecar is a file a person may add their own fields to. Reading
  one and writing it back must never silently drop what pinakes does not understand — that is data
  loss dressed up as normalisation.
* **`id` is permanent.** It is minted once, at first ingest, and never regenerated. Writing a
  sidecar that already has an id keeps that id.
* **Links are resolved before they are written.** Aliases and `self` are expanded to ULIDs on the
  way in (§2.2), so what lands on disk survives being shared.

There is deliberately no `content_hash` here: change detection is the index's job, and a hash in a
committed file would dirty two files per edit and go stale whenever sync had not run (§2.2).

In v0.1 sidecars are *created* and *moved*, never rewritten in place, so PyYAML dropping comments on
dump costs nothing yet. `pnk link` (v0.3) is what will need a comment-preserving writer.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from pinakes.errors import InvalidIdError, InvalidUriError, SidecarError
from pinakes.ids import DocId, KbId, mint_doc_id, parse_doc_id
from pinakes.uri import ParsedUri, PnkUri
from pinakes.uri import parse as parse_uri

SIDECAR_SUFFIX = ".pnk.yaml"

# Keys this module understands. Anything else is preserved verbatim under `extra`.
KNOWN_KEYS = frozenset({"id", "title", "tags", "created", "links", "provenance"})


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
    """Keys pinakes does not know. Round-tripped untouched — the file belongs to the user."""

    present: frozenset[str] = frozenset()
    """Known keys the file actually carried.

    An explicit `tags: []` is not the same as no `tags` at all: the first is something the user
    wrote and expects to still be there. Without this, writing back would quietly delete it.
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
        loaded: object = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SidecarError(path, f"is not valid YAML: {exc}") from exc

    if loaded is None:
        raise SidecarError(path, "is empty", remedy="Every sidecar must carry at least an `id`.")
    if not isinstance(loaded, dict):
        raise SidecarError(path, f"must be a mapping, found {type(loaded).__name__}")

    data = cast(dict[str, Any], loaded)
    return Sidecar(
        id=_id(path, data),
        title=_optional_str(path, data, "title"),
        tags=_tags(path, data),
        created=_optional_str(path, data, "created"),
        links=_links(path, data, owner=owner),
        provenance=_mapping(path, data, "provenance"),
        extra={key: value for key, value in data.items() if key not in KNOWN_KEYS},
        present=frozenset(key for key in KNOWN_KEYS if key in data),
    )


def write(path: Path, sidecar: Sidecar) -> None:
    """Write a sidecar. Unknown keys are written back; ordering is stable so diffs stay small."""
    document: dict[str, Any] = {"id": str(sidecar.id)}
    if sidecar.title is not None or "title" in sidecar.present:
        document["title"] = sidecar.title
    if sidecar.tags or "tags" in sidecar.present:
        document["tags"] = list(sidecar.tags)
    if sidecar.created is not None or "created" in sidecar.present:
        document["created"] = sidecar.created
    if sidecar.links or "links" in sidecar.present:
        document["links"] = [{"to": str(link.to), "rel": link.rel} for link in sidecar.links]
    if sidecar.provenance or "provenance" in sidecar.present:
        document["provenance"] = dict(sidecar.provenance)
    for key in sorted(sidecar.extra):
        document[key] = sidecar.extra[key]

    rendered = yaml.safe_dump(
        document, sort_keys=False, allow_unicode=True, default_flow_style=False
    )

    # Atomically: write beside the target, then rename over it. A truncated sidecar would lose the
    # document's permanent ULID, and every inbound pnk:// link with it — the one failure in this
    # module that no later command could repair.
    temporary = path.with_name(f"{path.name}.new")
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def skeleton(document: Path, *, title: str | None = None, created: str | None = None) -> Sidecar:
    """The sidecar minted for a newly ingested document: an id, and as little else as possible."""
    return Sidecar(
        id=mint_doc_id(),
        title=title if title is not None else document.stem.replace("-", " ").replace("_", " "),
        created=created,
    )


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
        raise SidecarError(path, f"`id` must be a string, found {type(raw).__name__}")
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
        raise SidecarError(path, f"`{key}` must be a string, found {type(raw).__name__}")
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
            raise SidecarError(path, f"`tags` must be strings, found {type(item).__name__}")
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
