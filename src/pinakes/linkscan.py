"""Reverse-scan: what the *other* KBs say points at this one (docs/DESIGN.md §6.2).

A `links[]` entry is written in the source document's sidecar and points forward. That is the whole
authoring model, and it means a KB has no way of knowing who links *to* it without asking. This
module asks: for each `[[links.kb]]`, read that KB's committed sidecars and keep the entries whose
target is us.

**Committed sidecars, never the partner's index.** An index is disposable, machine-local, and may
not exist at all — a freshly cloned KB has sidecars and nothing else. Reading one would also mean
holding a second KB's lock, which §6.2 forbids: a cross-KB read must never be able to block a
partner's own sync.

**But the partner's `pinakes.toml` is read too, and must be.** A sidecar carries `id`, `title`,
`tags`, `created`, `links`, `provenance` — and *not* the KB it belongs to. So "sidecars alone"
cannot supply `links.src_kb_id`, cannot key `kb_refs.kb_id`, and cannot even locate the sidecars,
which live under the partner's own `[sources] roots` and need not be in `docs/`. Three rules follow:

1. `src_kb_id` comes from the partner's **`[kb] id`**, never from the local manifest's declared
   `[[links.kb]] id`. When they disagree that is a recorded failure, not a guess — attributing one
   KB's links to another is exactly the confusion permanent ULIDs exist to prevent.
2. Sidecars are enumerated from the partner's `[sources]`.
3. **Partner sidecars are read with the partner's own id as `owner`.** Both pre-existing
   `read_sidecar` call sites hard-code the *local* KB, and reusing either would expand a partner's
   `pnk://self/<doc>` to us — minting rows claiming the partner links to local documents it never
   named. That defect was found and fixed once already (docs/RETROSPECTIVES.md: *"a sidecar copied
   into another KB would silently retarget its link at the new KB"*), and `tests/partner-kb/`
   carries a hand-authored `self` link so it cannot come back unnoticed.

**Only links targeting *this* KB are kept.** A partner's link to a third KB is read and discarded.
Recording it would accumulate a foreign graph this index can never complete, and a partial view of
someone else's links is the silently-incomplete answer §6.2 refuses.

**Nothing here raises.** Every failure is a `LinkScanError` *constructed* and returned, because
`pnk sync` runs on three git hooks and a partner that is simply not on this machine must not turn
every commit red. The caller decides what to do with them; `SyncReport.ok` does not count them.
"""

import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import cast

from pinakes.errors import (
    LinkedKbIdMismatchError,
    LinkedKbUnreachableError,
    LinkedSidecarUnreadableError,
    LinkScanError,
    LinkTargetMissingError,
    PinakesError,
)
from pinakes.ids import DocId, KbId, parse_kb_id
from pinakes.manifest import LinkedKb, Manifest
from pinakes.sidecar import SIDECAR_SUFFIX
from pinakes.sidecar import read as read_sidecar

MANIFEST_NAME = "pinakes.toml"

TTL_MINUTES = 60
"""How stale an inbound-link picture may be before a plain `pnk sync` re-reads a partner.

A code constant rather than a manifest key, deliberately: "how stale may a cross-KB link be" is a
question about *this* engine's cost model, not about a KB, and a per-KB knob would be one more
thing to get wrong in a file people hand-edit. `--scan-links` forces a re-read regardless.

Sixty minutes because the walk runs on `post-commit` and `post-merge`: a partner with a thousand
sidecars costs a thousand small reads, and paying that on every commit to make an *inbound* link
appear an hour sooner is the wrong trade. `pnk doctor` reports the age.
"""


@dataclass(frozen=True, slots=True)
class ReverseRow:
    """One inbound edge: `src` is a document in the *other* KB, `dst` is one of ours."""

    src_kb_id: KbId
    src_doc_id: DocId
    dst_doc_id: DocId
    rel: str


@dataclass(frozen=True, slots=True)
class ScannedKb:
    """The outcome of walking one `[[links.kb]]`."""

    alias: str
    declared_id: KbId
    path: Path
    """Resolved against the local KB root — what `kb_refs.path` records."""

    kb_id: KbId | None = None
    """The partner's *own* `[kb] id`. `None` when it could not be established."""

    rows: tuple[ReverseRow, ...] = ()
    issues: tuple[LinkScanError, ...] = ()

    complete: bool = False
    """The walk finished with no failure that could have hidden rows.

    **This is what licenses the delete.** Replacing a partner's rows means deleting all of them
    first, and they only come back if every sidecar was then re-read successfully — so a vanished
    file or an unparseable sidecar mid-walk would be a mass deletion of edges that are still true.
    An incomplete walk keeps whatever was already known and records why.

    A *missing target* does not clear this: the row is still recorded, and the partner's claim is
    real whether or not we have the document it names.
    """

    skipped_fresh: bool = False
    """Skipped because `kb_refs.last_scan` is inside the TTL. Distinct from `complete`: nothing was
    read, so nothing may be deleted either."""


@dataclass(frozen=True, slots=True)
class ScanResult:
    scanned: tuple[ScannedKb, ...] = ()
    delisted: tuple[str, ...] = field(default=())
    """KB ULIDs with reverse rows here that the manifest no longer lists.

    Their rows are removed. Nothing else would ever remove them: the per-partner delete is scoped
    to the KB being scanned, and a KB dropped from `[[links.kb]]` is never scanned again — so
    without this, disconnecting a partner left `pnk links --direction in` serving its edges until
    someone happened to rebuild.
    """

    @property
    def issues(self) -> tuple[LinkScanError, ...]:
        return tuple(issue for kb in self.scanned for issue in kb.issues)


def resolve_path(root: Path, raw: str) -> Path:
    """`[[links.kb]] path` → an absolute path. Relative to the *KB root*, with `~` expanded.

    Relative to the KB root rather than the process's working directory, because a manifest is
    committed and shared: `../partner-kb` has to mean the same thing whatever directory `pnk` was
    invoked from. An absolute path is honoured as given — and warned about by `pnk doctor` (L7),
    since a committed absolute path publishes a filesystem layout.
    """
    expanded = Path(raw).expanduser()
    return expanded if expanded.is_absolute() else (root / expanded).resolve()


def partner_sources(root: Path) -> tuple[KbId, list[str], list[str]]:
    """`([kb] id, [sources] roots, [sources] include)` from a partner's manifest.

    Read with `tomllib` directly rather than through `manifest.load`, which validates the *whole*
    file against this pinakes' schema. A partner may legitimately be running a newer version with
    keys we do not know — `[kb] requires_pinakes` (G4) exists precisely for that — and refusing to
    read a neighbour's inbound links because its manifest mentions a key we have not shipped yet
    would make every connected KB a version dependency of every other.
    """
    with (root / MANIFEST_NAME).open("rb") as handle:
        data = tomllib.load(handle)

    def table(name: str) -> dict[str, object]:
        raw: object = data.get(name)
        if not isinstance(raw, dict):
            raise ValueError(f"no [{name}] table")
        return cast(dict[str, object], raw)

    identifier = table("kb").get("id")
    if not isinstance(identifier, str):
        raise ValueError("no [kb] id")

    sources = table("sources")

    def strings(key: str, default: list[str]) -> list[str]:
        raw = sources.get(key)
        if not isinstance(raw, list):
            return default
        values = [value for value in cast(list[object], raw) if isinstance(value, str)]
        return values or default

    return parse_kb_id(identifier), strings("roots", ["docs/"]), strings("include", ["**/*.md"])


def sidecars_under(root: Path, roots: list[str], include: list[str]) -> list[Path]:
    """Every sidecar beside a document the partner's own `[sources]` would ingest.

    Driven from the *documents* rather than by globbing `**/*.pnk.yaml`, so a stray sidecar outside
    the partner's roots — or one whose document was excluded — contributes nothing. What the
    partner does not consider part of its KB is not something this KB should be recording links
    from.
    """
    found: set[Path] = set()
    for name in roots:
        base = (root / name).resolve()
        if not base.is_dir():
            continue
        for pattern in include:
            for candidate in base.glob(pattern):
                if not candidate.is_file() or candidate.name.endswith(SIDECAR_SUFFIX):
                    continue
                sidecar = candidate.with_name(candidate.name + SIDECAR_SUFFIX)
                if sidecar.is_file():
                    found.add(sidecar)
    return sorted(found)


def scan_one(
    linked: LinkedKb, *, local_root: Path, local_kb: KbId, known_documents: frozenset[DocId]
) -> ScannedKb:
    """Walk one linked KB. Never raises: every failure comes back in `issues`."""
    path = resolve_path(local_root, linked.path)
    base = ScannedKb(alias=linked.name, declared_id=linked.id, path=path)

    if not (path / MANIFEST_NAME).is_file():
        reason = "no pinakes.toml there" if path.is_dir() else "no such directory"
        return _with(base, issues=(LinkedKbUnreachableError(linked.name, path, reason=reason),))

    try:
        partner_id, roots, include = partner_sources(path)
    except (OSError, ValueError, tomllib.TOMLDecodeError, PinakesError) as exc:
        return _with(base, issues=(LinkedKbUnreachableError(linked.name, path, reason=str(exc)),))

    if partner_id != linked.id:
        # Refused rather than resolved. Trusting the manifest's declaration would file another
        # KB's links under this alias; trusting the partner would silently redirect a link the
        # local author wrote deliberately. Both are wrong, and a permanent ULID means one of the
        # two is simply a mistake to fix.
        return _with(
            base,
            kb_id=partner_id,
            issues=(
                LinkedKbIdMismatchError(
                    linked.name, declared=str(linked.id), found=str(partner_id)
                ),
            ),
        )

    rows: list[ReverseRow] = []
    issues: list[LinkScanError] = []
    complete = True
    missing: list[DocId] = []

    for sidecar in sidecars_under(path, roots, include):
        try:
            # `owner=partner_id`, never the local KB — see the module docstring.
            parsed = read_sidecar(sidecar, owner=partner_id)
        except PinakesError as exc:
            issues.append(LinkedSidecarUnreadableError(linked.name, sidecar, reason=exc.message))
            complete = False
            continue
        for link in parsed.links:
            if link.to.kb != local_kb:
                continue  # a third KB's business, and a partial view of it would be a lie
            if link.to.doc not in known_documents:
                missing.append(link.to.doc)
            rows.append(
                ReverseRow(
                    src_kb_id=partner_id,
                    src_doc_id=parsed.id,
                    dst_doc_id=link.to.doc,
                    rel=link.rel,
                )
            )

    if missing:
        issues.append(
            LinkTargetMissingError(linked.name, doc_id=str(missing[0]), count=len(missing))
        )

    return _with(
        base,
        kb_id=partner_id,
        rows=tuple(rows),
        issues=tuple(issues),
        complete=complete,
    )


def _with(
    base: ScannedKb,
    *,
    kb_id: KbId | None = None,
    rows: tuple[ReverseRow, ...] = (),
    issues: tuple[LinkScanError, ...] = (),
    complete: bool = False,
) -> ScannedKb:
    """Explicit keywords, not `**changes: object`.

    `KbId` is a `NewType`, so the obvious `isinstance`-based unpacking of a `**kwargs` bag does not
    type-check at all — and a helper that has to lie to the checker about what it received is a
    helper that will eventually be handed the wrong thing.
    """
    return ScannedKb(
        alias=base.alias,
        declared_id=base.declared_id,
        path=base.path,
        kb_id=kb_id,
        rows=rows,
        issues=issues,
        complete=complete,
    )


def is_stale(last_scan: str | None, now: str, *, ttl_minutes: int = TTL_MINUTES) -> bool:
    """Whether a partner is due a re-read.

    Both stamps are `%Y%m%d %H:%M` — minute resolution, local time, no zone — because that is what
    `sync()` already writes everywhere else and a second time format in one index would be worse
    than the coarseness. So the TTL is whole minutes, and a scan is never *not* due when the answer
    is uncertain:

    * no `last_scan` at all → stale (nothing is known yet);
    * a stamp that will not parse → stale (a hand-edited or future-format value must not be read
      as "recent", which would suppress the scan silently and forever);
    * a stamp **in the future** → stale. The clock moved backwards, or the file came from another
      machine. Treating it as fresh would suppress every scan until real time caught up, which is
      the one failure mode with no symptom.
    """
    if last_scan is None:
        return True
    fmt = "%Y%m%d %H:%M"
    try:
        then = datetime.strptime(last_scan, fmt)
        current = datetime.strptime(now, fmt)
    except ValueError:
        return True
    if then > current:
        return True
    return (current - then).total_seconds() >= ttl_minutes * 60


def scan(
    manifest: Manifest,
    *,
    local_documents: frozenset[DocId],
    last_scans: dict[str, str],
    now: str,
    force: bool = False,
    known_kb_ids: frozenset[str] = frozenset(),
) -> ScanResult:
    """Walk every `[[links.kb]]`, skipping the ones still inside the TTL.

    `known_kb_ids` is what the index already holds reverse rows for; anything in it that the
    manifest no longer lists comes back in `delisted`.
    """
    scanned: list[ScannedKb] = []
    for linked in manifest.links:
        if not force and not is_stale(last_scans.get(str(linked.id)), now):
            scanned.append(
                ScannedKb(
                    alias=linked.name,
                    declared_id=linked.id,
                    path=resolve_path(manifest.root, linked.path),
                    kb_id=linked.id,
                    skipped_fresh=True,
                )
            )
            continue
        scanned.append(
            scan_one(
                linked,
                local_root=manifest.root,
                local_kb=manifest.kb.id,
                known_documents=local_documents,
            )
        )

    listed = {str(linked.id) for linked in manifest.links}
    return ScanResult(
        scanned=tuple(scanned),
        delisted=tuple(sorted(known_kb_ids - listed)),
    )
