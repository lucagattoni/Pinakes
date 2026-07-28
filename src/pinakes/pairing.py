"""Two-phase sync pairing — deciding what each file *is* before touching anything.

This is docs/DESIGN.md §6.4 as a **pure function**: no filesystem, no SQLite, no clock. Everything
it needs arrives as two snapshots, and it returns a list of actions for I8b to execute. That shape
is deliberate — this is the logic that silently corrupts a KB when it is wrong, and a pure function
can be tested exhaustively against the design's table, row by row.

Pairing is *set-wise*, not per-file: a path that vanished might be a delete, or it might be half of
a rename, and you cannot tell which until you have looked at every other file. Phase 1 is the caller
walking the tree; phase 2 is this module resolving the whole picture at once.

The rules, in the order they are applied:

| Case | Action |
|---|---|
| Path and content unchanged | `Skip` — or `RefreshMetadata` if only the sidecar changed |
| Path unchanged, content changed | `Reembed`, keeping the id |
| Path gone, exactly one new path with the same content | `Rename`, keeping the id |
| Path gone, several share it | prefer the one whose sidecar carries the old id; else report |
| New path with an adjacent sidecar | `Adopt` its id (also how rename+edit keeps its identity) |
| New path, no sidecar | `Mint` |
| Path gone, nothing matches | `SoftDelete` |
| One id in two sidecars | raise — never renumber |

Two consequences worth stating, because both are ways a KB quietly rots:

* **Adoption beats deletion.** When a file is moved *and* edited in one sync, the content hash no
  longer ties the two paths together — but the sidecar travelled with it. The id continues at the
  new path and **no delete is emitted for it**, so inbound links survive.
* **A duplicated id is fatal, not repairable.** Renumbering would break links that were fine, so
  this raises and names both paths (§6.4).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from pinakes.errors import DuplicateIdsError
from pinakes.ids import DocId

ACTIVE = "active"
DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    """One `documents` row, as the previous sync left it."""

    id: DocId
    path: str
    content_hash: str
    sidecar_hash: str | None = None
    state: str = ACTIVE
    extraction_backend: str | None = None
    """`None` for a non-extracted source. `--rebuild` cannot read this from an empty new database
    (I5, decision 11) — its caller seeds it from the sidecar's `provenance.extraction` instead."""


@dataclass(frozen=True, slots=True)
class WalkedFile:
    """One source file found on disk."""

    path: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class WalkedSidecar:
    """One `.pnk.yaml` found on disk, and the document path it sits beside."""

    path: str
    document_path: str
    id: DocId
    file_hash: str


@dataclass(frozen=True, slots=True)
class IndexSnapshot:
    documents: tuple[IndexedDocument, ...] = ()


@dataclass(frozen=True, slots=True)
class WalkSnapshot:
    files: tuple[WalkedFile, ...] = ()
    sidecars: tuple[WalkedSidecar, ...] = ()


@dataclass(frozen=True, slots=True)
class Skip:
    doc_id: DocId
    path: str


@dataclass(frozen=True, slots=True)
class RefreshMetadata:
    """The document is untouched; only its sidecar changed. Re-read metadata, do not re-embed."""

    doc_id: DocId
    path: str
    sidecar_hash: str | None


@dataclass(frozen=True, slots=True)
class Reembed:
    doc_id: DocId
    path: str
    content_hash: str
    sidecar_hash: str | None


@dataclass(frozen=True, slots=True)
class Rename:
    doc_id: DocId
    old_path: str
    path: str
    content_hash: str
    sidecar_hash: str | None


@dataclass(frozen=True, slots=True)
class Adopt:
    """A new path whose sidecar carries an id — either a first ingest of a shared doc, or a move."""

    doc_id: DocId
    path: str
    content_hash: str
    sidecar_hash: str | None
    old_path: str | None


@dataclass(frozen=True, slots=True)
class Mint:
    path: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class SoftDelete:
    doc_id: DocId
    path: str


@dataclass(frozen=True, slots=True)
class PaidExtractionRequired:
    """A paid-extracted document's content changed under a free-effective run (I5, decision 14).

    Neither re-extracting with the downgraded free backend (silently discarding paid quality)
    nor leaving the stale text indexed (silently wrong) is honest — this becomes a `failures` row
    naming the path and the paid backend, so the remedy is a deliberate, paid re-extraction.
    """

    doc_id: DocId
    path: str
    recorded_backend: str


type Action = (
    Skip | RefreshMetadata | Reembed | Rename | Adopt | Mint | SoftDelete | PaidExtractionRequired
)


@dataclass(frozen=True, slots=True)
class Ambiguity:
    """Several new paths carry the content of one vanished document, and nothing breaks the tie."""

    old_doc_id: DocId
    old_path: str
    candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PairingResult:
    actions: tuple[Action, ...] = ()
    ambiguities: tuple[Ambiguity, ...] = ()
    orphaned_sidecars: tuple[str, ...] = ()
    moved_without_sidecar: tuple[str, ...] = ()
    """Paths that were soft-deleted and re-minted because their sidecar did not travel (§9)."""
    paid_extraction_protected: tuple[str, ...] = ()
    """Paths kept at their paid extraction despite a free-effective run — printed once, not
    silently (I5, decision 9)."""
    paid_extraction_overwritten: tuple[str, ...] = ()
    """Paths where `--force` plus an explicit free `--extract` discarded a paid extraction —
    printed *before* it happens, naming what is about to be lost (I5, decision 9)."""


def pair(
    before: IndexSnapshot,
    after: WalkSnapshot,
    *,
    effective_backend: str | None = None,
    paid_backend_names: frozenset[str] = frozenset(),
    force: bool = False,
    explicit_extract: bool = False,
) -> PairingResult:
    """`effective_backend`/`paid_backend_names` classify only the *recorded-paid* direction here
    (decision 9's other two clauses): a document whose `IndexedDocument.extraction_backend` is
    paid, compared against whether the backend in effect *for this run* is paid too. Left at their
    defaults, no document can ever be "recorded paid" against an empty `paid_backend_names`, so
    every existing call site and test that never heard of backends keeps its exact old behaviour.
    """
    _reject_duplicate_ids(after.sidecars)

    sidecar_by_document = {sidecar.document_path: sidecar for sidecar in after.sidecars}
    before_by_path = {document.path: document for document in before.documents}
    before_by_id = {document.id: document for document in before.documents}
    after_by_path = {file.path: file for file in after.files}

    effective_is_paid = effective_backend is not None and effective_backend in paid_backend_names

    actions: list[Action] = []
    ambiguities: list[Ambiguity] = []
    moved_without_sidecar: list[str] = []
    paid_extraction_protected: list[str] = []
    paid_extraction_overwritten: list[str] = []
    handled_ids: set[DocId] = set()
    handled_paths: set[str] = set()

    # --- Same path: skip, refresh, or re-embed -------------------------------------------------
    for path, file in after_by_path.items():
        document = before_by_path.get(path)
        if document is None:
            continue
        sidecar = sidecar_by_document.get(path)
        sidecar_hash = sidecar.file_hash if sidecar else None

        # The sidecar is committed truth for identity; the index row is derived. If they disagree,
        # the sidecar wins, and the stale row is retired rather than silently kept.
        if sidecar is not None and sidecar.id != document.id:
            actions.append(SoftDelete(doc_id=document.id, path=path))
            actions.append(
                Adopt(
                    doc_id=sidecar.id,
                    path=path,
                    content_hash=file.content_hash,
                    sidecar_hash=sidecar_hash,
                    old_path=before_by_id[sidecar.id].path if sidecar.id in before_by_id else None,
                )
            )
            handled_ids.update({document.id, sidecar.id})
            handled_paths.add(path)
            continue

        handled_ids.add(document.id)
        handled_paths.add(path)
        hash_changed = document.content_hash != file.content_hash or document.state == DELETED
        recorded_backend = document.extraction_backend
        recorded_is_paid = recorded_backend is not None and recorded_backend in paid_backend_names
        override = force and explicit_extract

        if recorded_is_paid and not effective_is_paid and not override:
            # Decision 9's paid-protection clauses: never silently re-extract with a downgraded
            # backend, and never silently keep indexing text a changed file no longer matches.
            if hash_changed:
                assert recorded_backend is not None  # implied by recorded_is_paid
                actions.append(
                    PaidExtractionRequired(
                        doc_id=document.id, path=path, recorded_backend=recorded_backend
                    )
                )
            else:
                actions.append(Skip(doc_id=document.id, path=path))
                paid_extraction_protected.append(path)
            continue

        if recorded_is_paid and not effective_is_paid and override:
            # `--force` with an explicit free `--extract` is the one path allowed to discard paid
            # text — reported *before* the fact, since a plain Reembed is silent about what a
            # backend downgrade costs. Emitted directly, not left to fall through to the
            # hash-changed check below: an *unchanged* hash is exactly the case this whole branch
            # exists to override, so it must still produce Reembed even though nothing else here
            # would consider that file re-processable.
            paid_extraction_overwritten.append(path)
            actions.append(
                Reembed(
                    doc_id=document.id,
                    path=path,
                    content_hash=file.content_hash,
                    sidecar_hash=sidecar_hash,
                )
            )
            continue

        if not recorded_is_paid and effective_is_paid and recorded_backend is not None:
            # Free-recorded, paid-effective: stale regardless of hash — a content-hash check
            # cannot tell "the file is unchanged" from "the last extraction undersold it" either
            # way (decision 9).
            actions.append(
                Reembed(
                    doc_id=document.id,
                    path=path,
                    content_hash=file.content_hash,
                    sidecar_hash=sidecar_hash,
                )
            )
            continue

        if hash_changed:
            actions.append(
                Reembed(
                    doc_id=document.id,
                    path=path,
                    content_hash=file.content_hash,
                    sidecar_hash=sidecar_hash,
                )
            )
        elif document.sidecar_hash != sidecar_hash:
            actions.append(
                RefreshMetadata(doc_id=document.id, path=path, sidecar_hash=sidecar_hash)
            )
        else:
            actions.append(Skip(doc_id=document.id, path=path))

    # --- New paths carrying a sidecar id we already know: adoption (this covers rename+edit) -----
    for path, file in after_by_path.items():
        if path in handled_paths:
            continue
        sidecar = sidecar_by_document.get(path)
        if sidecar is None:
            continue
        known = before_by_id.get(sidecar.id)
        if known is not None and known.id in handled_ids:
            continue
        actions.append(
            Adopt(
                doc_id=sidecar.id,
                path=path,
                content_hash=file.content_hash,
                sidecar_hash=sidecar.file_hash,
                old_path=known.path if known is not None else None,
            )
        )
        handled_paths.add(path)
        handled_ids.add(sidecar.id)

    # --- Vanished paths: rename by content, ambiguity, or soft delete ---------------------------
    unclaimed = [file for path, file in after_by_path.items() if path not in handled_paths]
    by_hash: dict[str, list[WalkedFile]] = {}
    for file in unclaimed:
        by_hash.setdefault(file.content_hash, []).append(file)

    for document in before.documents:
        if document.id in handled_ids or document.state == DELETED:
            continue
        candidates = [
            file
            for file in by_hash.get(document.content_hash, [])
            if file.path not in handled_paths
        ]

        if len(candidates) == 1:
            file = candidates[0]
            sidecar = sidecar_by_document.get(file.path)
            actions.append(
                Rename(
                    doc_id=document.id,
                    old_path=document.path,
                    path=file.path,
                    content_hash=file.content_hash,
                    sidecar_hash=sidecar.file_hash if sidecar else None,
                )
            )
            handled_paths.add(file.path)
            handled_ids.add(document.id)
            continue

        if len(candidates) > 1:
            # Prefer a candidate whose own sidecar already carries this id — that is the one piece
            # of evidence strong enough to break the tie. Otherwise do not guess: attaching an id
            # to the wrong duplicate silently redirects every inbound link.
            preferred = next(
                (
                    file
                    for file in candidates
                    if (sidecar := sidecar_by_document.get(file.path)) is not None
                    and sidecar.id == document.id
                ),
                None,
            )
            if preferred is not None:
                actions.append(
                    Rename(
                        doc_id=document.id,
                        old_path=document.path,
                        path=preferred.path,
                        content_hash=preferred.content_hash,
                        sidecar_hash=sidecar_by_document[preferred.path].file_hash,
                    )
                )
                handled_paths.add(preferred.path)
                handled_ids.add(document.id)
                continue

            ambiguities.append(
                Ambiguity(
                    old_doc_id=document.id,
                    old_path=document.path,
                    candidates=tuple(sorted(file.path for file in candidates)),
                )
            )

        actions.append(SoftDelete(doc_id=document.id, path=document.path))
        handled_ids.add(document.id)
        if document.path not in after_by_path:
            moved_without_sidecar.append(document.path)

    # --- Everything still unclaimed is new ------------------------------------------------------
    for path, file in after_by_path.items():
        if path in handled_paths:
            continue
        actions.append(Mint(path=path, content_hash=file.content_hash))

    return PairingResult(
        actions=tuple(actions),
        ambiguities=tuple(ambiguities),
        orphaned_sidecars=_orphans(after),
        moved_without_sidecar=tuple(sorted(moved_without_sidecar)),
        paid_extraction_protected=tuple(sorted(paid_extraction_protected)),
        paid_extraction_overwritten=tuple(sorted(paid_extraction_overwritten)),
    )


def _orphans(after: WalkSnapshot) -> tuple[str, ...]:
    """Sidecars whose document is gone. Reported, never deleted — that needs `--prune` (§6.4)."""
    documents = {file.path for file in after.files}
    return tuple(
        sorted(sidecar.path for sidecar in after.sidecars if sidecar.document_path not in documents)
    )


def _reject_duplicate_ids(sidecars: Sequence[WalkedSidecar]) -> None:
    by_id: dict[DocId, list[str]] = {}
    for sidecar in sidecars:
        by_id.setdefault(sidecar.id, []).append(sidecar.path)
    duplicates = {str(doc_id): sorted(paths) for doc_id, paths in by_id.items() if len(paths) > 1}
    if duplicates:
        raise DuplicateIdsError(duplicates)


def describe(result: PairingResult) -> Mapping[str, int]:
    """Counts by action kind — what `pnk sync` prints, and what tests assert against."""
    counts: dict[str, int] = {}
    for action in result.actions:
        counts[type(action).__name__] = counts.get(type(action).__name__, 0) + 1
    return counts


def actions_of[T](result: PairingResult, kind: type[T]) -> list[T]:
    return [action for action in result.actions if isinstance(action, kind)]


def hash_of(files: Iterable[WalkedFile]) -> dict[str, str]:
    return {file.path: file.content_hash for file in files}


_ = field  # dataclasses.field is re-exported for callers building snapshots in tests
