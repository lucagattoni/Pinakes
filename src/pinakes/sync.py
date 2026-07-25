"""`pnk sync` — walk the sources, decide what changed, and rebuild only that.

The decisions all live in `pairing.py` (§6.4); this module does the I/O around them and holds the
properties that make a half-finished sync harmless:

* **One document per transaction.** A file that will not parse or embed is recorded in `failures`,
  the run continues, and the command exits non-zero listing them. The index never half-describes a
  document, and one broken file cannot block a thousand good ones (§6.4).
* **Sidecars and the index are separable.** `--sidecars-only` writes ids into `docs/`;
  `--index-only` never touches `docs/`. That split is what lets the pre-commit hook mint ids into
  the commit while post-commit does the slow indexing (§6.3).
* **`--rebuild` swaps atomically.** A new database is built beside the old one, checkpointed so no
  `-wal` companion survives, closed, and renamed into place. `ledger.jsonl` is never touched — a
  routine rebuild must not reset the spend history (§6.3).
"""

import hashlib
import os
import sqlite3
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pinakes import store
from pinakes.chunk import assert_chunkable, chunk_document, source_type
from pinakes.embed import EmbeddingBackend, load_backend
from pinakes.errors import PinakesError, SyncError
from pinakes.ids import DocId
from pinakes.lock import LockOutcome, SyncLock
from pinakes.manifest import Manifest
from pinakes.pairing import (
    Action,
    Adopt,
    Ambiguity,
    IndexedDocument,
    IndexSnapshot,
    Mint,
    Reembed,
    RefreshMetadata,
    Rename,
    Skip,
    SoftDelete,
    WalkedFile,
    WalkedSidecar,
    WalkSnapshot,
    pair,
)
from pinakes.sidecar import (
    SIDECAR_SUFFIX,
    Sidecar,
    document_for,
    is_sidecar,
    sidecar_path,
    skeleton,
)
from pinakes.sidecar import (
    read as read_sidecar,
)
from pinakes.sidecar import (
    write as write_sidecar,
)

type BackendFactory = Callable[[Manifest, bool], EmbeddingBackend]


@dataclass(frozen=True, slots=True)
class SyncOptions:
    rebuild: bool = False
    sidecars_only: bool = False
    index_only: bool = False
    stage: bool = False
    offline: bool = False
    force_unlock: bool = False


@dataclass(slots=True)
class SyncReport:
    skipped: int = 0
    refreshed: int = 0
    embedded: int = 0
    renamed: int = 0
    minted: int = 0
    deleted: int = 0
    sidecars_written: list[str] = field(default_factory=list[str])
    failures: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    ambiguities: tuple[Ambiguity, ...] = ()
    orphaned_sidecars: tuple[str, ...] = ()
    moved_without_sidecar: tuple[str, ...] = ()
    busy: bool = False
    reclaimed_lock: bool = False

    @property
    def ok(self) -> bool:
        return not self.failures

    def lines(self) -> list[str]:
        """What `pnk sync` prints. Counts first, then anything needing a human."""
        summary = [
            f"{self.embedded} indexed",
            f"{self.renamed} renamed",
            f"{self.refreshed} metadata-only",
            f"{self.skipped} unchanged",
            f"{self.deleted} removed",
        ]
        lines = [", ".join(summary)]
        for path in self.moved_without_sidecar:
            lines.append(f"moved without its sidecar, so a new id was minted: {path}")
        for ambiguity in self.ambiguities:
            lines.append(
                f"ambiguous duplicate of {ambiguity.old_path}: "
                f"{', '.join(ambiguity.candidates)} — fresh ids minted, nothing guessed"
            )
        for orphan in self.orphaned_sidecars:
            lines.append(f"orphaned sidecar (kept; remove with `pnk doctor --prune`): {orphan}")
        for path, error in self.failures:
            lines.append(f"failed: {path}: {error}")
        return lines


def hash_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def hash_file(path: Path) -> str:
    return hash_bytes(path.read_bytes())


def walk_sources(manifest: Manifest) -> tuple[list[WalkedFile], list[WalkedSidecar]]:
    """Collect source files and sidecars, KB-root-relative with POSIX separators.

    Sidecars are excluded from the *document* set categorically, whatever the include patterns say:
    an `include = ["**/*.yaml"]` must never ingest a document's own metadata as a document.
    """
    files: dict[str, WalkedFile] = {}
    sidecars: dict[str, WalkedSidecar] = {}

    for root_name in manifest.sources.roots:
        root = (manifest.root / root_name).resolve()
        if not root.is_dir():
            continue
        for pattern in manifest.sources.include:
            for candidate in sorted(root.glob(pattern)):
                if not candidate.is_file():
                    continue
                relative = candidate.relative_to(manifest.root).as_posix()
                if _excluded(relative, manifest.sources.exclude, manifest.root, candidate):
                    continue
                if is_sidecar(candidate):
                    continue
                files[relative] = WalkedFile(path=relative, content_hash=hash_file(candidate))

        for candidate in sorted(root.rglob(f"*{SIDECAR_SUFFIX}")):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(manifest.root).as_posix()
            document = document_for(candidate).relative_to(manifest.root).as_posix()
            try:
                parsed = read_sidecar(candidate, owner=manifest.kb.id)
            except PinakesError:
                continue  # reported by `pnk doctor`; a broken sidecar must not stop the walk
            sidecars[relative] = WalkedSidecar(
                path=relative,
                document_path=document,
                id=parsed.id,
                file_hash=hash_file(candidate),
            )

    return sorted(files.values(), key=lambda f: f.path), sorted(
        sidecars.values(), key=lambda s: s.path
    )


def _excluded(relative: str, patterns: Sequence[str], root: Path, candidate: Path) -> bool:
    return any(candidate.match(pattern) or Path(relative).match(pattern) for pattern in patterns)


def read_index_snapshot(connection: sqlite3.Connection) -> IndexSnapshot:
    rows = connection.execute("SELECT id, path, content_hash, sidecar_hash, state FROM documents")
    return IndexSnapshot(
        tuple(
            IndexedDocument(
                id=DocId(str(row["id"])),
                path=str(row["path"]),
                content_hash=str(row["content_hash"]),
                sidecar_hash=None if row["sidecar_hash"] is None else str(row["sidecar_hash"]),
                state=str(row["state"]),
            )
            for row in rows
        )
    )


def _default_backend(manifest: Manifest, offline: bool) -> EmbeddingBackend:
    return load_backend(manifest.embedding, offline=offline)


def sync(
    manifest: Manifest,
    *,
    options: SyncOptions | None = None,
    backend_factory: BackendFactory = _default_backend,
    now: str | None = None,
) -> SyncReport:
    options = options or SyncOptions()
    stamp = now or datetime.now().strftime("%Y%m%d %H:%M")

    with SyncLock(manifest.state_dir, force=options.force_unlock) as lock:
        if not lock.acquired:
            return SyncReport(busy=True)
        report = SyncReport(reclaimed_lock=lock.outcome is LockOutcome.RECLAIMED)
        _run(manifest, options, backend_factory, stamp, report)
        return report


def _run(
    manifest: Manifest,
    options: SyncOptions,
    backend_factory: BackendFactory,
    stamp: str,
    report: SyncReport,
) -> None:
    files, sidecars = walk_sources(manifest)

    if options.sidecars_only:
        _write_missing_sidecars(manifest, files, sidecars, options, stamp, report)
        return

    index_path = manifest.index_path
    target = index_path.with_suffix(".db.new") if options.rebuild else index_path
    if options.rebuild:
        target.unlink(missing_ok=True)

    connection = (
        store.create(target)
        if options.rebuild or not index_path.exists()
        else store.connect_rw(index_path)
    )
    try:
        before = read_index_snapshot(connection)
        result = pair(before, WalkSnapshot(tuple(files), tuple(sidecars)))
        report.ambiguities = result.ambiguities
        report.orphaned_sidecars = result.orphaned_sidecars
        report.moved_without_sidecar = result.moved_without_sidecar

        backend = _backend_if_needed(manifest, options, result.actions, backend_factory)
        sidecar_by_document = {sidecar.document_path: sidecar for sidecar in sidecars}

        for action in result.actions:
            _apply(
                action,
                manifest=manifest,
                connection=connection,
                backend=backend,
                options=options,
                sidecar_by_document=sidecar_by_document,
                stamp=stamp,
                report=report,
            )

        store.set_meta(
            connection,
            {
                "embedding_provider": manifest.embedding.provider,
                "embedding_model": manifest.embedding.model,
                "embedding_revision": manifest.embedding.revision or "",
                "embedding_dim": str(manifest.embedding.dim),
                "vector_tier": "numpy",
                "built_at": stamp,
            },
        )
        connection.commit()
        if options.rebuild:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()

    if options.rebuild:
        # Rename only after the checkpoint above and this close: a stale -wal beside a new
        # index.db is a corrupt read waiting to happen (§6.5). ledger.jsonl is untouched.
        os.replace(target, index_path)
        # And remove the *old* file's companions. They are named after the path, not the inode, so
        # after the rename they would sit beside the new database claiming to be its write-ahead
        # log — which is precisely the corruption the checkpoint above exists to avoid. The new
        # database was checkpointed and closed cleanly, so it has none of its own.
        for companion in ("-wal", "-shm"):
            index_path.with_name(index_path.name + companion).unlink(missing_ok=True)


def _backend_if_needed(
    manifest: Manifest,
    options: SyncOptions,
    actions: Iterable[object],
    backend_factory: BackendFactory,
) -> EmbeddingBackend | None:
    """Load model weights only if something actually needs embedding."""
    if not any(isinstance(action, Reembed | Rename | Adopt | Mint) for action in actions):
        return None
    backend = backend_factory(manifest, options.offline)
    assert_chunkable(manifest.chunking.max_tokens, model_max_tokens=backend.info().max_seq_length)
    return backend


def _apply(
    action: Action,
    *,
    manifest: Manifest,
    connection: sqlite3.Connection,
    backend: EmbeddingBackend | None,
    options: SyncOptions,
    sidecar_by_document: dict[str, WalkedSidecar],
    stamp: str,
    report: SyncReport,
) -> None:
    match action:
        case Skip():
            report.skipped += 1
            return
        case SoftDelete(doc_id=doc_id):
            connection.execute("UPDATE documents SET state = 'deleted' WHERE id = ?", (doc_id,))
            connection.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            connection.commit()
            report.deleted += 1
            return
        case RefreshMetadata(doc_id=doc_id, path=path, sidecar_hash=sidecar_hash):
            _refresh_metadata(manifest, connection, doc_id, path, sidecar_hash)
            connection.commit()
            report.refreshed += 1
            return
        case Reembed() | Rename() | Adopt() | Mint():
            pass

    assert isinstance(action, Reembed | Rename | Adopt | Mint)  # match above handled the rest
    path, content_hash, doc_id, sidecar_hash, is_rename = _target(action)
    try:
        if doc_id is None:
            doc_id, sidecar_hash = _mint(manifest, path, options, stamp, report)
        _index_document(
            manifest=manifest,
            connection=connection,
            backend=backend,
            doc_id=doc_id,
            path=path,
            content_hash=content_hash,
            sidecar_hash=sidecar_hash,
            sidecar_by_document=sidecar_by_document,
        )
        connection.commit()
    except (PinakesError, OSError, ValueError) as exc:
        connection.rollback()
        store.record_failure(
            connection,
            path=path,
            stage="index",
            error=f"{type(exc).__name__}: {exc}",
            happened=stamp,
        )
        connection.commit()
        report.failures.append((path, str(exc)))
        return

    if is_rename:
        report.renamed += 1
    else:
        report.embedded += 1


def _target(
    action: Reembed | Rename | Adopt | Mint,
) -> tuple[str, str, DocId | None, str | None, bool]:
    match action:
        case Reembed(doc_id=doc_id, path=path, content_hash=h, sidecar_hash=s):
            return path, h, doc_id, s, False
        case Rename(doc_id=doc_id, path=path, content_hash=h, sidecar_hash=s):
            return path, h, doc_id, s, True
        case Adopt(doc_id=doc_id, path=path, content_hash=h, sidecar_hash=s, old_path=old):
            return path, h, doc_id, s, old is not None
        case Mint(path=path, content_hash=h):
            return path, h, None, None, False


def _mint(
    manifest: Manifest, path: str, options: SyncOptions, stamp: str, report: SyncReport
) -> tuple[DocId, str | None]:
    """Create the sidecar that gives a new document its permanent id."""
    document = manifest.root / path
    made = skeleton(document, created=stamp)
    if options.index_only:
        return made.id, None
    target = sidecar_path(document)
    write_sidecar(target, made)
    report.sidecars_written.append(target.relative_to(manifest.root).as_posix())
    return made.id, hash_file(target)


def _write_missing_sidecars(
    manifest: Manifest,
    files: Sequence[WalkedFile],
    sidecars: Sequence[WalkedSidecar],
    options: SyncOptions,
    stamp: str,
    report: SyncReport,
) -> None:
    """The pre-commit half: give new documents their ids, and nothing else (§6.3)."""
    have = {sidecar.document_path for sidecar in sidecars}
    candidates = [file.path for file in files if file.path not in have]
    if options.stage:
        staged = _staged_paths(manifest.root)
        candidates = [path for path in candidates if path in staged]

    written: list[Path] = []
    for path in candidates:
        target = sidecar_path(manifest.root / path)
        write_sidecar(target, skeleton(manifest.root / path, created=stamp))
        report.sidecars_written.append(target.relative_to(manifest.root).as_posix())
        report.minted += 1
        written.append(target)

    if options.stage and written:
        _git(manifest.root, "add", "--", *[str(path) for path in written])


def _staged_paths(root: Path) -> set[str]:
    output = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return {line.strip() for line in output.splitlines() if line.strip()}


def _git(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise SyncError(
            "git is not on PATH.", remedy="`--stage` only makes sense inside a git repository."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise SyncError(
            f"git {' '.join(args)} failed: {exc.stderr.strip()}",
            remedy="`--stage` only makes sense inside a git repository.",
        ) from exc
    return completed.stdout


def _refresh_metadata(
    manifest: Manifest,
    connection: sqlite3.Connection,
    doc_id: DocId,
    path: str,
    sidecar_hash: str | None,
) -> None:
    parsed = _read_sidecar_for(manifest, path)
    connection.execute(
        "UPDATE documents SET title = ?, metadata = ?, sidecar_hash = ? WHERE id = ?",
        (
            parsed.title if parsed else None,
            store.dumps_metadata(_metadata(parsed)),
            sidecar_hash,
            doc_id,
        ),
    )
    _replace_links(connection, manifest, doc_id, parsed)


def _read_sidecar_for(manifest: Manifest, path: str) -> Sidecar | None:
    target = sidecar_path(manifest.root / path)
    if not target.is_file():
        return None
    return read_sidecar(target, owner=manifest.kb.id)


def _metadata(parsed: Sidecar | None) -> dict[str, object]:
    if parsed is None:
        return {}
    return {"tags": list(parsed.tags), "provenance": dict(parsed.provenance), **parsed.extra}


def _replace_links(
    connection: sqlite3.Connection, manifest: Manifest, doc_id: DocId, parsed: Sidecar | None
) -> None:
    connection.execute(
        "DELETE FROM links WHERE src_kb_id = ? AND src_doc_id = ? AND origin = 'sidecar'",
        (manifest.kb.id, doc_id),
    )
    for link in parsed.links if parsed else ():
        connection.execute(
            "INSERT OR REPLACE INTO links VALUES (?, ?, ?, ?, ?, 'sidecar')",
            (manifest.kb.id, doc_id, link.to.kb, link.to.doc, link.rel),
        )


def _index_document(
    *,
    manifest: Manifest,
    connection: sqlite3.Connection,
    backend: EmbeddingBackend | None,
    doc_id: DocId,
    path: str,
    content_hash: str,
    sidecar_hash: str | None,
    sidecar_by_document: dict[str, WalkedSidecar],
) -> None:
    if backend is None:  # pragma: no cover — only when nothing needed embedding
        raise SyncError("no embedding backend was loaded.", remedy="This is a bug; report it.")

    source = manifest.root / path
    text = source.read_text(encoding="utf-8")
    parsed = _read_sidecar_for(manifest, path)

    chunks = chunk_document(
        text,
        counter=backend,
        max_tokens=manifest.chunking.max_tokens,
        overlap=manifest.chunking.overlap,
        kind=source_type(path),
    )

    connection.execute(
        "INSERT INTO documents (id, path, content_hash, sidecar_hash, mtime, source_type, title, "
        "metadata, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active') "
        "ON CONFLICT (id) DO UPDATE SET path = excluded.path, content_hash = excluded.content_hash,"
        " sidecar_hash = excluded.sidecar_hash, mtime = excluded.mtime, "
        "source_type = excluded.source_type, title = excluded.title, "
        "metadata = excluded.metadata, state = 'active'",
        (
            doc_id,
            path,
            content_hash,
            sidecar_hash if sidecar_hash is not None else _sidecar_hash(sidecar_by_document, path),
            source.stat().st_mtime,
            source_type(path),
            parsed.title if parsed else None,
            store.dumps_metadata(_metadata(parsed)),
        ),
    )
    _replace_links(connection, manifest, doc_id, parsed)

    chunk_ids = store.replace_chunks(connection, doc_id, [chunk.as_row() for chunk in chunks])
    if chunk_ids:
        vectors = backend.embed([chunk.text for chunk in chunks])
        for chunk_id, vector in zip(chunk_ids, vectors, strict=True):
            store.store_embedding(connection, chunk_id, vector)


def _sidecar_hash(sidecar_by_document: dict[str, WalkedSidecar], path: str) -> str | None:
    found = sidecar_by_document.get(path)
    return found.file_hash if found else None
