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

import codecs
import hashlib
import os
import sqlite3
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pinakes import store
from pinakes.chunk import PDF_SUFFIXES, assert_chunkable, chunk_document, source_type
from pinakes.embed import EmbeddingBackend, load_backend
from pinakes.errors import (
    BackendUnknownError,
    ExtractionError,
    ExtractorMissingError,
    PaidExtractionRequiredError,
    PaidExtractionUnavailableError,
    PinakesError,
    SyncError,
)
from pinakes.extract import (
    ExtractedText,
    ExtractionContext,
    fingerprint,
    load_extractor,
    paid_backend_names,
    registered_extractors,
)
from pinakes.extract import cache as extract_cache
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
    PaidExtractionRequired,
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
    extraction_provenance,
    is_sidecar,
    sidecar_path,
    skeleton,
    with_extraction_provenance,
    without_extraction_provenance,
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
    extract: str | None = None  # overrides `[extraction] backend` for one run
    clear_cache: bool = False  # a standalone mode (I4): empties the extraction cache, nothing else
    yes: bool = False  # skip --clear-cache's confirmation (cron use)
    force: bool = False
    """Only meaningful together with an explicit `extract=` naming a *free* backend (I5): the one
    combination allowed to overwrite a paid extraction. `--force` alone changes nothing."""


@dataclass(slots=True)
class SyncReport:
    skipped: int = 0
    refreshed: int = 0
    embedded: int = 0
    renamed: int = 0
    minted: int = 0
    deleted: int = 0
    sidecars_written: list[str] = field(default_factory=list[str])
    # (path, error, remedy) — "" when the failure carried none (a bare OSError/ValueError)
    failures: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])
    ambiguities: tuple[Ambiguity, ...] = ()
    orphaned_sidecars: tuple[str, ...] = ()
    moved_without_sidecar: tuple[str, ...] = ()
    paid_extraction_protected: tuple[str, ...] = ()
    """Kept at their paid extraction despite a free-effective run — printed once, not per path
    (I5, decision 9)."""
    paid_extraction_overwritten: tuple[str, ...] = ()
    """`--force` plus an explicit free `--extract` discarded these paid extractions — named, not
    just counted, since discarding paid work is the one thing this design must never do quietly."""
    unmatched: tuple[str, ...] = ()
    """Files under `[sources] roots` that no `include` pattern matched (`walk_sources`). Summarised
    by extension in `lines()`: the individual paths are rarely interesting, but "you have PDFs and
    no glob for them" always is."""
    unmatched_truncated: bool = False
    """The walk stopped probing at `MAX_PROBED_PER_ROOT`, so `unmatched` is a sample."""
    unmatched_pdf_extra: str | None = None
    """The extra a `.pdf` in `unmatched` would still need after the glob is added — set only when
    the extractor is genuinely not importable, so the hint is never redundant advice."""
    busy: bool = False
    reclaimed_lock: bool = False
    # --clear-cache's own outcome; None on every other run (see `sync()`'s early return for it).
    cache_cleared: int | None = None
    cache_cleared_bytes: int = 0
    cache_clear_aborted: bool = False  # requested but not confirmed (no --yes)
    cache_pending_entries: int = 0  # what --clear-cache *would* remove, for the caller's prompt
    cache_pending_bytes: int = 0

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
        if self.unmatched:
            lines.append(self.unmatched_line())
        for path in self.paid_extraction_overwritten:
            lines.append(f"paid extraction discarded (--force --extract): {path}")
        if self.paid_extraction_protected:
            sample = ", ".join(self.paid_extraction_protected[:3])
            more = len(self.paid_extraction_protected) - 3
            lines.append(
                f"{len(self.paid_extraction_protected)} paid extraction(s) kept as-is "
                f"(this run's backend would have downgraded them): {sample}"
                + (f" and {more} more" if more > 0 else "")
            )
        for path in self.moved_without_sidecar:
            lines.append(f"moved without its sidecar, so a new id was minted: {path}")
        for ambiguity in self.ambiguities:
            lines.append(
                f"ambiguous duplicate of {ambiguity.old_path}: "
                f"{', '.join(ambiguity.candidates)} — fresh ids minted, nothing guessed"
            )
        for orphan in self.orphaned_sidecars:
            lines.append(f"orphaned sidecar (kept; remove with `pnk doctor --prune`): {orphan}")
        lines.extend(self.failure_lines())
        return lines

    def unmatched_line(self) -> str:
        """One line, grouped by extension, naming the glob that would pick the commonest up.

        By extension rather than by path because the actionable unit is the *pattern*: twelve
        unindexed PDFs are one missing glob, and printing twelve paths would obscure that. The
        `exclude` half is named too — a KB with images beside its notes should be able to silence
        this rather than being nagged by it on every sync.

        Suffixes are grouped **as they appear on disk**, never lowercased: `pathlib` glob is
        case-sensitive on POSIX whatever the filesystem does, so `"**/*.pdf"` does not match
        `Report.PDF`, and a remedy that fails to fix the file it was printed for is the very thing
        `_indexable` exists to avoid.
        """
        counts: dict[str, int] = {}
        for path in self.unmatched:
            suffix = Path(path).suffix or "(no extension)"
            counts[suffix] = counts.get(suffix, 0) + 1
        # Ties break toward a real suffix: "(no extension)" sorts before ".pdf" by codepoint, and
        # would otherwise win the hint slot while carrying no usable glob.
        ranked = sorted(
            counts.items(), key=lambda item: (-item[1], not item[0].startswith("."), item[0])
        )
        shown = ", ".join(f"{suffix} ({count})" for suffix, count in ranked[:3])
        if len(ranked) > 3:
            shown += f" and {len(ranked) - 3} more extension(s)"
        commonest = ranked[0][0]
        hint = (
            f'add "**/*{commonest}" to `[sources] include` to index them'
            if commonest.startswith(".")
            else "add a matching glob to `[sources] include` to index them"
        )
        counted = (
            f"{len(self.unmatched)}+" if self.unmatched_truncated else f"{len(self.unmatched)}"
        )
        line = (
            f"{counted} file(s) matched no `include` pattern: {shown} — "
            f"{hint}, or `exclude` them to silence this."
        )
        if self.unmatched_pdf_extra:
            line += f' Indexing PDFs also needs `uv add "pinakes[{self.unmatched_pdf_extra}]"`.'
        return line

    def failure_lines(self) -> list[str]:
        """One line per failing path, then each distinct remedy **once** - never per path.

        Several documents can fail identically (a whole `[pdf]`-less KB full of PDFs, say), and a
        remedy that only needs saying once should not scroll past N times.
        """
        lines = [f"failed: {path}: {error}" for path, error, _ in self.failures]
        seen: list[str] = []
        for _, _, remedy in self.failures:
            if remedy and remedy not in seen:
                seen.append(remedy)
        lines.extend(seen)
        return lines


def hash_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def hash_file(path: Path) -> str:
    return hash_bytes(path.read_bytes())


@dataclass(frozen=True, slots=True)
class UnmatchedFiles:
    """Files under the roots that no `include` pattern picked up, and whether the walk gave up
    before seeing them all."""

    paths: tuple[str, ...] = ()
    truncated: bool = False


def walk_sources(
    manifest: Manifest,
) -> tuple[list[WalkedFile], list[WalkedSidecar], UnmatchedFiles]:
    """Collect source files, sidecars, and files no `include` pattern matched.

    Sidecars are excluded from the *document* set categorically, whatever the include patterns say:
    an `include = ["**/*.yaml"]` must never ingest a document's own metadata as a document.

    The third element exists because a file silently absent from the index is indistinguishable
    from one that was never there. `pnk init` stamps no `**/*.pdf` glob, so a PDF dropped into a
    fresh KB matched nothing and `pnk sync` reported `0 indexed` explaining nothing — the file was
    skipped for a reason the user configured without realising, which is exactly the class of thing
    a tool should say out loud.
    """
    files: dict[str, WalkedFile] = {}
    sidecars: dict[str, WalkedSidecar] = {}
    unmatched: set[str] = set()

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

    # A second pass, deliberately *after* every root's include walk rather than inside it: with two
    # roots (or one nested in another) the first pass would test a file against a `files` that the
    # later roots had not contributed to yet, reporting an indexed document as unmatched and making
    # the output depend on the order roots happen to be listed in.
    truncated = False
    for root_name in manifest.sources.roots:
        root = (manifest.root / root_name).resolve()
        if root.is_dir():
            found, hit_cap = _unmatched_under(root, manifest, matched=files)
            unmatched.update(found)
            truncated = truncated or hit_cap

    return (
        sorted(files.values(), key=lambda f: f.path),
        sorted(sidecars.values(), key=lambda s: s.path),
        UnmatchedFiles(paths=tuple(sorted(unmatched)), truncated=truncated),
    )


#: Bytes sampled to decide whether a file is text pinakes could index. A prefix is enough: a binary
#: format's magic number is at the front, and no realistic document is valid UTF-8 for 8 KB and
#: then not.
_TEXT_PROBE_BYTES = 8192

#: Files probed per root before giving up on completeness. Bounds the cost on a tree this walk has
#: no business reading in full — a `node_modules/` under a KB root is thousands of files, each an
#: `open()` (a network round trip on an SMB or NFS mount) on every sync, to produce advice nobody
#: wants. Truncation is reported, never silent.
MAX_PROBED_PER_ROOT = 500


def _indexable(candidate: Path) -> bool:
    """Whether pinakes could read this file at all, tested the way indexing itself tests it.

    `_index_document` reads every non-PDF source with `read_text(encoding="utf-8")`, so a file whose
    bytes are not UTF-8 cannot be indexed however the manifest is configured — suggesting a glob for
    one would hand the user a remedy that produces a `UnicodeDecodeError` failure row when followed.
    Deciding by *decodability* rather than by an extension allowlist keeps `.rst`, `.org`, `.tex`
    and every other text format working without a list anybody has to maintain, since
    `chunk.source_type` already falls back to `"text"` for an unknown suffix.

    Decoded **incrementally**, because a fixed byte cut lands mid-character in any script whose
    codepoints are multi-byte: a plain `bytes.decode()` of the first 8 KB of CJK, Cyrillic or Greek
    prose raises `UnicodeDecodeError` on the split trailing character about two times in three, and
    would have handed exactly this feature's silence back to every non-English corpus. An
    incremental decoder holds a partial character instead of failing on it.

    `.pdf` is the one exception, admitted explicitly: binary on purpose, and indexable through
    `pinakes[pdf]`.
    """
    if candidate.suffix.lower() in PDF_SUFFIXES:
        return True
    try:
        with candidate.open("rb") as handle:
            codecs.getincrementaldecoder("utf-8")().decode(handle.read(_TEXT_PROBE_BYTES))
    except UnicodeDecodeError:
        return False
    except OSError:
        return False  # unreadable is not actionable either; `pnk doctor` owns permissions
    return True


def _unmatched_under(
    root: Path, manifest: Manifest, *, matched: Mapping[str, WalkedFile]
) -> tuple[set[str], bool]:
    """Files under `root` that no `include` pattern picked up, that the user did not ask to ignore,
    and that pinakes could actually index if a pattern did match. The flag is `True` when probing
    stopped at `MAX_PROBED_PER_ROOT` and the set is therefore incomplete.

    Deliberately silent about four classes, none of them a surprise worth reporting: anything
    `exclude` already names (the user said so), sidecars (metadata, never documents), anything under
    a dotted path segment (`.git/`, `.DS_Store` — never the corpus), and anything `_indexable`
    rejects. Reporting an image beside someone's notes would bury the one line that matters under
    noise they cannot act on.
    """
    found: set[str] = set()
    probed = 0
    for candidate in sorted(root.rglob("*")):
        if not candidate.is_file():
            continue
        try:
            relative = candidate.relative_to(manifest.root).as_posix()
        except ValueError:
            # A symlinked root resolves outside the KB. Nothing here can be addressed by a
            # KB-relative path, so there is no advice to give — and a raw ValueError out of a walk
            # would reach the CLI as a traceback rather than a sync.
            continue
        if relative in matched or is_sidecar(candidate):
            continue
        if _excluded(relative, manifest.sources.exclude, manifest.root, candidate):
            continue
        if any(part.startswith(".") for part in candidate.relative_to(root).parts):
            continue
        if probed >= MAX_PROBED_PER_ROOT:
            return found, True
        probed += 1
        if not _indexable(candidate):
            continue
        found.add(relative)
    return found, False


def _missing_pdf_extra(unmatched: Sequence[str], extraction_backend: str) -> str | None:
    """The extra an unmatched `.pdf` would *still* need once its glob is added, or `None`.

    Adding `"**/*.pdf"` on a core-only install turns every PDF from a silently skipped file into a
    loudly failed one — which is the same trap `_indexable` refuses to set for images, so the hint
    has to carry the second half. Only when the extractor genuinely will not import: telling someone
    to install what they already have is noise, and this line is competing for the attention of a
    person who has just been told something was skipped.
    """
    if not any(Path(path).suffix.lower() in PDF_SUFFIXES for path in unmatched):
        return None
    try:
        load_extractor(extraction_backend)
    except ExtractorMissingError as exc:
        return exc.extra
    except (ExtractionError, PinakesError):
        return None  # registered but unimplemented, or unknown — not a missing-extra story
    return None


def _excluded(relative: str, patterns: Sequence[str], root: Path, candidate: Path) -> bool:
    return any(candidate.match(pattern) or Path(relative).match(pattern) for pattern in patterns)


def read_index_snapshot(connection: sqlite3.Connection) -> IndexSnapshot:
    rows = connection.execute(
        "SELECT id, path, content_hash, sidecar_hash, state, extraction_backend FROM documents"
    )
    return IndexSnapshot(
        tuple(
            IndexedDocument(
                id=DocId(str(row["id"])),
                path=str(row["path"]),
                content_hash=str(row["content_hash"]),
                sidecar_hash=None if row["sidecar_hash"] is None else str(row["sidecar_hash"]),
                state=str(row["state"]),
                extraction_backend=(
                    None if row["extraction_backend"] is None else str(row["extraction_backend"])
                ),
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

    if options.clear_cache:
        # A standalone mode: empties `cache/extract/` and nothing else (§6.3) — never the walk,
        # never the index, never `ledger.jsonl`. Needs no extraction backend to be valid, so it is
        # checked before that validation below, not after.
        with SyncLock(manifest.state_dir, force=options.force_unlock) as lock:
            if not lock.acquired:
                return SyncReport(busy=True)
            return _clear_cache(manifest, options)

    # Resolved and validated before the lock is even taken: an unknown backend is a configuration
    # mistake, not a per-document failure, and it should fail the same way on a KB with zero PDFs
    # as on one full of them (I1's exit criterion).
    extraction_backend = options.extract or manifest.extraction.backend
    if extraction_backend not in registered_extractors():
        raise BackendUnknownError(extraction_backend, known=registered_extractors())

    with SyncLock(manifest.state_dir, force=options.force_unlock) as lock:
        if not lock.acquired:
            return SyncReport(busy=True)
        report = SyncReport(reclaimed_lock=lock.outcome is LockOutcome.RECLAIMED)
        _run(manifest, options, backend_factory, stamp, report, extraction_backend)
        return report


def _clear_cache(manifest: Manifest, options: SyncOptions) -> SyncReport:
    """`--clear-cache`'s whole effect. No prompt lives here (§ module docstring's own I/O rule):
    the caller (`cli.py`) checks a TTY and asks the user, then re-calls with `yes=True` — this
    function only ever does the deletion, and only when told to."""
    cache_dir = manifest.extract_cache_dir
    pending_entries, pending_bytes = extract_cache.total_stats(cache_dir)
    if pending_entries == 0:
        return SyncReport(cache_cleared=0, cache_cleared_bytes=0)
    if not options.yes:
        return SyncReport(
            cache_clear_aborted=True,
            cache_pending_entries=pending_entries,
            cache_pending_bytes=pending_bytes,
        )
    removed, removed_bytes = extract_cache.clear_all(cache_dir)
    return SyncReport(cache_cleared=removed, cache_cleared_bytes=removed_bytes)


def _run(
    manifest: Manifest,
    options: SyncOptions,
    backend_factory: BackendFactory,
    stamp: str,
    report: SyncReport,
    extraction_backend: str,
) -> None:
    files, sidecars, unmatched = walk_sources(manifest)
    report.unmatched = unmatched.paths
    report.unmatched_truncated = unmatched.truncated
    report.unmatched_pdf_extra = _missing_pdf_extra(unmatched.paths, extraction_backend)

    if options.sidecars_only:
        _write_missing_sidecars(manifest, files, sidecars, options, stamp, report)
        return

    index_path = manifest.index_path
    protected_by_hash = (
        _paid_rebuild_survivors(
            manifest,
            effective_backend=extraction_backend,
            force=options.force,
            explicit_extract=options.extract is not None,
        )
        if options.rebuild
        else {}
    )
    target = index_path.with_suffix(".db.new") if options.rebuild else index_path
    if options.rebuild:
        target.unlink(missing_ok=True)

    connection = (
        store.create(target)
        if options.rebuild or not index_path.exists()
        else store.connect_rw(index_path)
    )
    active_hashes: set[str] | None = None
    try:
        before = read_index_snapshot(connection)
        result = pair(
            before,
            WalkSnapshot(tuple(files), tuple(sidecars)),
            effective_backend=extraction_backend,
            paid_backend_names=paid_backend_names(),
            force=options.force,
            explicit_extract=options.extract is not None,
        )
        report.ambiguities = result.ambiguities
        report.orphaned_sidecars = result.orphaned_sidecars
        report.moved_without_sidecar = result.moved_without_sidecar
        report.paid_extraction_protected = result.paid_extraction_protected
        report.paid_extraction_overwritten = result.paid_extraction_overwritten

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
                extraction_backend=extraction_backend,
                protected_by_hash=protected_by_hash,
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
        # Captured now, while the connection is still open — never after a run that recorded a
        # failure, so a document that never got its final content_hash written cannot cost its
        # own cache entry (or anyone else's) an eviction it didn't earn (I4).
        if report.ok:
            active_hashes = store.active_content_hashes(connection)
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

    # After the swap (if any), never before: sweeping against `.db.new`'s data is fine (renaming
    # only moves the file, not what it says), but deleting cache files before we know the rename
    # itself succeeded would strand `.db.new` with cache misses waiting for it if a later step in
    # a future increment ever intervened here.
    if active_hashes is not None:
        extract_cache.evict_orphans(manifest.extract_cache_dir, active_content_hashes=active_hashes)


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
    extraction_backend: str,
    protected_by_hash: dict[DocId, tuple[str, str]],
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
        case PaidExtractionRequired(path=path, recorded_backend=recorded_backend):
            # Decision 14: neither a Reembed nor a silent Skip is honest here — the file changed
            # under a run whose effective backend cannot honour what was paid for. Decided by
            # pairing.py directly, not raised, so it is recorded the same way any other failure
            # is, with no extraction ever attempted.
            error = (
                f"PaidExtractionRequiredError: {path} was extracted with the paid "
                f"`{recorded_backend}` backend, but its content changed."
            )
            remedy = f"Run `pnk sync --extract={recorded_backend}` to pay for a fresh extraction."
            store.record_failure(
                connection, path=path, stage="extract", error=error, happened=stamp
            )
            connection.commit()
            report.failures.append((path, error, remedy))
            return
        case Reembed() | Rename() | Adopt() | Mint():
            pass

    assert isinstance(action, Reembed | Rename | Adopt | Mint)  # match above handled the rest
    path, content_hash, doc_id, sidecar_hash, is_rename = _target(action)
    try:
        if doc_id is None:
            doc_id, sidecar_hash = _mint(manifest, path, options, stamp, report)
        override = options.force and options.extract is not None
        survivor = protected_by_hash.get(doc_id)
        in_place_backend = (
            _paid_survivor_in_current_index(connection, doc_id=doc_id, content_hash=content_hash)
            if survivor is None and extraction_backend not in paid_backend_names() and not override
            else None
        )
        if survivor is not None:
            # `--rebuild` only: the file's own old row in the index being replaced proves a paid
            # extraction, without touching the (possibly just-cleared) extraction cache at all
            # (`_paid_rebuild_survivors`'s own docstring). Copied forward at its *old* content_hash
            # regardless of whether the file has since changed — see below.
            recorded_backend, old_content_hash = survivor
            _copy_forward_protected_document(
                manifest,
                connection,
                old_index_path=manifest.index_path,
                old_doc_id=str(doc_id),
                new_doc_id=doc_id,
                path=path,
                content_hash=old_content_hash,
                sidecar_hash=sidecar_hash,
            )
            if old_content_hash == content_hash:
                report.paid_extraction_protected = (*report.paid_extraction_protected, path)
            else:
                # Decision 14, reached the moment `--rebuild` is what happens to run into it:
                # `pair()`'s own `PaidExtractionRequired` action can never fire here (`before` is
                # empty, so nothing looks "changed" to it) — this applies the identical guarantee
                # from what `_paid_rebuild_survivors` already proved by reading the *old* index.
                # The document stays searchable at its last paid extraction, exactly as a normal
                # sync leaves it, rather than vanishing the instant a rebuild hits this case.
                error = (
                    f"PaidExtractionRequiredError: {path} was extracted with the paid "
                    f"`{recorded_backend}` backend, but its content has changed since; kept at "
                    "its last paid extraction rather than dropped from the index."
                )
                remedy = (
                    f"Run `pnk sync --extract={recorded_backend}` to pay for a fresh extraction."
                )
                store.record_failure(
                    connection, path=path, stage="extract", error=error, happened=stamp
                )
                report.failures.append((path, error, remedy))
        elif in_place_backend is not None:
            # Not a rebuild: `doc_id` is already an active, paid-recorded row in *this*
            # connection, same content_hash — a rename, or an `Adopt` reaching the same document
            # some other way. `_paid_survivor_in_current_index`'s own docstring explains why this
            # cannot be left to `_extract_for_index`'s cache-based fallback alone.
            _reindex_paid_document_in_place(
                manifest,
                connection,
                doc_id=doc_id,
                path=path,
                content_hash=content_hash,
                sidecar_hash=sidecar_hash,
            )
            report.paid_extraction_protected = (*report.paid_extraction_protected, path)
        else:
            _index_document(
                manifest=manifest,
                connection=connection,
                backend=backend,
                doc_id=doc_id,
                path=path,
                content_hash=content_hash,
                sidecar_hash=sidecar_hash,
                sidecar_by_document=sidecar_by_document,
                extraction_backend=extraction_backend,
                options=options,
                stamp=stamp,
            )
        connection.commit()
    except (PinakesError, OSError, ValueError) as exc:
        connection.rollback()
        extract_stage = (
            ExtractionError
            | ExtractorMissingError
            | PaidExtractionRequiredError
            | PaidExtractionUnavailableError
        )
        stage = "extract" if isinstance(exc, extract_stage) else "index"
        remedy = exc.remedy if isinstance(exc, PinakesError) else ""
        error = f"{type(exc).__name__}: {exc}"
        store.record_failure(connection, path=path, stage=stage, error=error, happened=stamp)
        connection.commit()
        report.failures.append((path, error, remedy))
        return

    if survivor is not None or in_place_backend is not None:
        report.skipped += 1
    elif is_rename:
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


def _paid_survivor_in_current_index(
    connection: sqlite3.Connection, *, doc_id: DocId, content_hash: str
) -> str | None:
    """The recorded backend, if `doc_id` is already an *active* row in this same connection with
    this exact `content_hash` and a paid `extraction_backend` — i.e., nothing about its paid text
    needs to change, only bookkeeping like `path` might (a rename, or an `Adopt` reaching the same
    document some other way).

    Returns `None` when `doc_id` has no row yet at all — the ordinary case for a genuinely new
    document, and also the case that matters most: the *first* sync of a document in a freshly
    cloned KB, where nothing about it has ever been indexed on this machine before (I5's own
    retrospective finding — `_extract_for_index`'s cache-based check alone cannot tell "just
    renamed" or "just cloned" apart from "content actually changed", because a cache miss looks
    identical in all three cases; this check answers the question a different way, from data this
    same sync already has open, before ever reaching that cache-dependent code path at all).
    """
    paid_names = paid_backend_names()
    row = connection.execute(
        "SELECT content_hash, extraction_backend FROM documents WHERE id = ? AND state = 'active'",
        (doc_id,),
    ).fetchone()
    if row is None or str(row["content_hash"]) != content_hash:
        return None
    backend = row["extraction_backend"]
    if backend is None or str(backend) not in paid_names:
        return None
    return str(backend)


def _reindex_paid_document_in_place(
    manifest: Manifest,
    connection: sqlite3.Connection,
    *,
    doc_id: DocId,
    path: str,
    content_hash: str,
    sidecar_hash: str | None,
) -> None:
    """A rename (or an `Adopt` reaching the same conclusion some other way) of a paid-protected,
    content-unchanged PDF: the document's chunks and embeddings, already sitting in this same
    connection under this same `doc_id`, remain exactly correct as they are — only `documents`'
    own bookkeeping needs to move to the new path. No extraction, no re-chunking, no re-embedding,
    and no sidecar rewrite (the provenance it already carries is still accurate)."""
    source = manifest.root / path
    parsed = _read_sidecar_for(manifest, path)
    connection.execute(
        "UPDATE documents SET path = ?, content_hash = ?, sidecar_hash = ?, mtime = ?, "
        "title = ?, metadata = ?, state = 'active' WHERE id = ?",
        (
            path,
            content_hash,
            sidecar_hash,
            source.stat().st_mtime,
            parsed.title if parsed else None,
            store.dumps_metadata(_metadata(parsed)),
            doc_id,
        ),
    )
    _replace_links(connection, manifest, doc_id, parsed)


def _paid_rebuild_survivors(
    manifest: Manifest, *, effective_backend: str, force: bool, explicit_extract: bool
) -> dict[DocId, tuple[str, str]]:
    """`doc_id` -> (recorded_backend, old_content_hash) for every actively-indexed, paid-extracted
    document in the index `--rebuild` is about to replace.

    Keyed on `doc_id` alone — this table's own primary key, therefore unique by construction —
    not on content_hash or path, for two independent reasons: (1) two *different* documents can
    legitimately share one content_hash with only one of them paid, and a content_hash-only key
    would let the free one's rebuild incorrectly inherit the paid one's chunks, embeddings and
    backend label; (2) `--rebuild`'s own `before` is empty (module docstring), so pairing can never
    detect a rename *as* a rename during a rebuild — the action reaching `_apply` for a renamed
    document only ever carries its *current* path, which the old index's own recorded path would
    no longer match. `doc_id` is the one identifier a renamed sidecar still carries unchanged, so
    it is the only key that survives both cases correctly.

    Read *before* anything is unlinked or created, while `manifest.index_path` still holds the
    database `_run` is discarding (module docstring: the swap is atomic and happens last) — this is
    deliberately independent of `extract/cache.py`: a `--clear-cache` immediately before
    `--rebuild` empties the cache but never touches the index file, so relying on the old index
    itself (rather than the cache) is what lets a rebuild survive that sequence without either
    downgrading a paid extraction or wrongly demanding to pay for it again.

    Empty whenever there is nothing to protect: this run's own effective backend is already paid,
    `--force` with an explicit free `--extract` says to override anyway (decision 9), or no prior
    index exists yet.
    """
    if effective_backend in paid_backend_names() or (force and explicit_extract):
        return {}
    old_path = manifest.index_path
    if not old_path.exists():
        return {}
    try:
        connection = store.connect_ro(old_path)
    except PinakesError:
        # Most commonly a pre-I5 (schema_version 1) index: it never tracked paid extractions at
        # all, so there is nothing here to carry forward — not a reason to fail the rebuild.
        return {}
    try:
        rows = connection.execute(
            "SELECT id, content_hash, extraction_backend FROM documents "
            "WHERE state = 'active' AND extraction_backend IS NOT NULL"
        ).fetchall()
    finally:
        connection.close()
    paid_names = paid_backend_names()
    return {
        DocId(str(row["id"])): (str(row["extraction_backend"]), str(row["content_hash"]))
        for row in rows
        if str(row["extraction_backend"]) in paid_names
    }


def _copy_forward_protected_document(
    manifest: Manifest,
    connection: sqlite3.Connection,
    *,
    old_index_path: Path,
    old_doc_id: str,
    new_doc_id: DocId,
    path: str,
    content_hash: str,
    sidecar_hash: str | None,
) -> None:
    """Populate one document's row, chunks and embeddings straight from the index `--rebuild` is
    replacing — never re-extracted, never re-embedded, because `_paid_rebuild_survivors` already
    proved nothing about its paid extraction needs to change. Title, tags and links still come from
    the *current* sidecar (not the old row): those can have changed even when the file's content,
    and hence its extraction, has not.
    """
    source = manifest.root / path
    parsed = _read_sidecar_for(manifest, path)
    connection.execute("ATTACH DATABASE ? AS old_index", (str(old_index_path),))
    try:
        old_row = connection.execute(
            "SELECT source_type, extraction_backend, extraction_fingerprint "
            "FROM old_index.documents WHERE id = ?",
            (old_doc_id,),
        ).fetchone()
        assert old_row is not None, "content_hash lookup that found this id proves the row exists"
        connection.execute(
            "INSERT INTO documents (id, path, content_hash, sidecar_hash, mtime, source_type, "
            "title, metadata, state, extraction_backend, extraction_fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET path = excluded.path, "
            "content_hash = excluded.content_hash, sidecar_hash = excluded.sidecar_hash, "
            "mtime = excluded.mtime, source_type = excluded.source_type, "
            "title = excluded.title, metadata = excluded.metadata, state = 'active', "
            "extraction_backend = excluded.extraction_backend, "
            "extraction_fingerprint = excluded.extraction_fingerprint",
            (
                new_doc_id,
                path,
                content_hash,
                sidecar_hash,
                source.stat().st_mtime,
                old_row["source_type"],
                parsed.title if parsed else None,
                store.dumps_metadata(_metadata(parsed)),
                old_row["extraction_backend"],
                old_row["extraction_fingerprint"],
            ),
        )
        connection.execute(
            "INSERT INTO chunks (doc_id, ordinal, text, char_start, char_end, token_count, "
            "heading_path, page_start, page_end) "
            "SELECT ?, ordinal, text, char_start, char_end, token_count, heading_path, "
            "page_start, page_end FROM old_index.chunks WHERE doc_id = ? ORDER BY ordinal",
            (new_doc_id, old_doc_id),
        )
        connection.execute(
            "INSERT INTO embeddings (chunk_id, vector) "
            "SELECT c.id, oe.vector FROM chunks c "
            "JOIN old_index.chunks oc ON oc.doc_id = ? AND oc.ordinal = c.ordinal "
            "JOIN old_index.embeddings oe ON oe.chunk_id = oc.id "
            "WHERE c.doc_id = ?",
            (old_doc_id, new_doc_id),
        )
    finally:
        connection.commit()
        connection.execute("DETACH DATABASE old_index")
    _replace_links(connection, manifest, new_doc_id, parsed)


def _extract_for_index(
    *,
    manifest: Manifest,
    source: Path,
    path: str,
    content_hash: str,
    extraction_backend: str,
    sidecar: Sidecar | None,
    options: SyncOptions,
) -> tuple[ExtractedText, str, str]:
    """Extract a PDF, honouring decision 9's paid-protection rule: a document whose sidecar
    records a *paid* extraction is never silently re-extracted with a *free* effective backend,
    unless `--force` and an explicit free `--extract` both say so.

    Returns the extracted text plus the backend/fingerprint that actually produced it — which is
    not always `extraction_backend`: when a paid original is preserved, both name the *recorded*
    backend instead, so `documents.extraction_backend` never claims a downgrade that did not
    happen.
    """
    paid_names = paid_backend_names()
    effective_is_paid = extraction_backend in paid_names
    override = options.force and options.extract is not None

    recorded = extraction_provenance(sidecar) if sidecar is not None else None
    if recorded is not None and not effective_is_paid and not override:
        recorded_backend, recorded_fingerprint, recorded_content_hash = recorded
        if recorded_backend in paid_names:
            if recorded_content_hash != content_hash:
                raise PaidExtractionRequiredError(path, recorded_backend=recorded_backend)
            # Unchanged since the paid extraction — decided directly from the sidecar's own
            # recorded content_hash, never from a cache lookup (I5's own retrospective finding: a
            # cache-miss is not proof of a content change — a `--clear-cache`, a rename, or a
            # first sync after a fresh clone all miss the cache without the file having changed at
            # all). Whether the *text* is still available locally, to avoid paying again, is a
            # separate question the cache can still answer when it's warm:
            cached = extract_cache.peek(
                manifest.extract_cache_dir,
                content_hash=content_hash,
                fingerprint=recorded_fingerprint,
            )
            if cached is not None:
                return cached, recorded_backend, recorded_fingerprint
            raise PaidExtractionUnavailableError(path, recorded_backend=recorded_backend)

    if options.index_only and effective_is_paid:
        # `--index-only` never writes into `docs/` (`_mint` already honours this for a brand new
        # document) — and recording a paid extraction's provenance requires exactly that write.
        # Refusing costs nothing: `--index-only` is what the post-commit/post-merge hooks run, and
        # I6b already forbids hooks from spending.
        raise SyncError(
            f"{path}: a paid extraction cannot run under --index-only.",
            remedy="Run a normal `pnk sync` (without --index-only) to extract and record it.",
        )

    def _extract() -> ExtractedText:
        # Loading the extractor (importing pypdfium2, say) is deferred inside this closure, so a
        # cache hit never pays for it — only a miss does (I4).
        ctx = ExtractionContext(model=manifest.extraction.model)
        return load_extractor(extraction_backend).extract(source, ctx)

    used_fingerprint = fingerprint(extraction_backend)
    extracted = extract_cache.get_or_extract(
        manifest.extract_cache_dir,
        content_hash=content_hash,
        backend=extraction_backend,
        fingerprint=used_fingerprint,
        extract=_extract,
    )
    return extracted, extraction_backend, used_fingerprint


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
    extraction_backend: str,
    options: SyncOptions,
    stamp: str,
) -> None:
    if backend is None:  # pragma: no cover — only when nothing needed embedding
        raise SyncError("no embedding backend was loaded.", remedy="This is a bug; report it.")

    source = manifest.root / path
    kind = source_type(path)
    parsed = _read_sidecar_for(manifest, path)
    page_spans: Sequence[tuple[int, int]] | None = None
    used_backend: str | None = None
    used_fingerprint: str | None = None
    fresh_sidecar_hash: str | None = None
    if kind == "pdf":
        extracted, used_backend, used_fingerprint = _extract_for_index(
            manifest=manifest,
            source=source,
            path=path,
            content_hash=content_hash,
            extraction_backend=extraction_backend,
            sidecar=parsed,
            options=options,
        )
        text = extracted.text
        page_spans = extracted.page_spans

        # Additive read-merge-write, only when something about the recorded provenance actually
        # changes: a paid extraction is a human invocation, and only a genuinely fresh one is
        # worth the sidecar losing its comments over (module docstring; not the mere fact that a
        # paid backend happens to be in effect this run, e.g. an unchanged, cache-preserved hit).
        recorded = extraction_provenance(parsed) if parsed is not None else None
        used_is_paid = used_backend in paid_backend_names()
        changed = recorded != (used_backend, used_fingerprint, content_hash)
        if parsed is not None and changed and used_is_paid:
            target = sidecar_path(source)
            write_sidecar(
                target,
                with_extraction_provenance(
                    parsed,
                    backend=used_backend,
                    fingerprint=used_fingerprint,
                    extracted=stamp,
                    content_hash=content_hash,
                ),
            )
            # `sidecar_hash` was decided from the walk, before this write happened — recompute it
            # from the file we just wrote, or the very next sync would see a "changed" sidecar
            # hash it did not expect and spend a whole extra cycle on a spurious
            # `RefreshMetadata` before it settles.
            fresh_sidecar_hash = hash_file(target)
        elif parsed is not None and changed and recorded is not None:
            # The only way a *paid*-recorded document reaches here with a *free* `used_backend` is
            # `--force` plus an explicit free `--extract` (decision 9's override) — the sidecar's
            # claim is now false and must be cleared, not left to mislead a later sync (or a
            # different clone reading the same committed sidecar) into thinking it is still
            # paid-protected.
            target = sidecar_path(source)
            write_sidecar(target, without_extraction_provenance(parsed))
            fresh_sidecar_hash = hash_file(target)
    else:
        text = source.read_text(encoding="utf-8")

    chunks = chunk_document(
        text,
        counter=backend,
        max_tokens=manifest.chunking.max_tokens,
        overlap=manifest.chunking.overlap,
        kind=kind,
        page_spans=page_spans,
    )

    connection.execute(
        "INSERT INTO documents (id, path, content_hash, sidecar_hash, mtime, source_type, title, "
        "metadata, state, extraction_backend, extraction_fingerprint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET path = excluded.path, content_hash = excluded.content_hash,"
        " sidecar_hash = excluded.sidecar_hash, mtime = excluded.mtime, "
        "source_type = excluded.source_type, title = excluded.title, "
        "metadata = excluded.metadata, state = 'active', "
        "extraction_backend = excluded.extraction_backend, "
        "extraction_fingerprint = excluded.extraction_fingerprint",
        (
            doc_id,
            path,
            content_hash,
            fresh_sidecar_hash
            if fresh_sidecar_hash is not None
            else (
                sidecar_hash
                if sidecar_hash is not None
                else _sidecar_hash(sidecar_by_document, path)
            ),
            source.stat().st_mtime,
            kind,
            parsed.title if parsed else None,
            store.dumps_metadata(_metadata(parsed)),
            used_backend,
            used_fingerprint,
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
