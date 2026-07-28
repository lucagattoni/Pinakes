"""`pnk doctor` — everything the design promises to *report* rather than enforce.

Several of this system's honest limitations are only honest if something surfaces them: the linear
search ceiling (§3.1), link coverage (§6.2), orphaned sidecars (§6.4), a held lock (§6.5), an
environment missing FTS5 (§3.1), calibration that no longer matches the reranker in use (§4.2).
Each check returns a status and, when anything is wrong, a remedy — a report that says "problem"
without saying "do this" is just anxiety.

Nothing here changes anything, with one exception behind an explicit flag: `--prune` deletes
orphaned sidecars, after printing every path it is about to remove (§6.4).
"""

import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath

from pinakes import store, template
from pinakes.embed import hf_cache_dir, load_backend, load_reranker
from pinakes.errors import ExtractionError, ExtractorMissingError, PinakesError
from pinakes.extract import cache as extract_cache
from pinakes.extract import load_extractor
from pinakes.ids import DocId
from pinakes.lock import LOCK_NAME, read_holder
from pinakes.manifest import Manifest
from pinakes.search import check_coherence
from pinakes.sidecar import SIDECAR_SUFFIX, Sidecar, document_for, find_duplicate_ids
from pinakes.sidecar import read as read_sidecar

LARGE_CORPUS_CHUNKS = 50_000
HOOK_MARKER = "pinakes"


class Status(Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: Status
    detail: str
    remedy: str | None = None

    def line(self) -> str:
        head = f"{self.status.value.upper():<4} {self.name}: {self.detail}"
        return f"{head}\n     → {self.remedy}" if self.remedy else head


@dataclass(frozen=True, slots=True)
class Report:
    checks: tuple[Check, ...]
    orphans: tuple[Path, ...] = ()

    @property
    def worst(self) -> Status:
        if any(check.status is Status.FAIL for check in self.checks):
            return Status.FAIL
        if any(check.status is Status.WARN for check in self.checks):
            return Status.WARN
        return Status.OK


def diagnose(manifest: Manifest) -> Report:
    checks: list[Check] = []
    checks.extend(_environment())
    checks.append(_template(manifest))
    checks.extend(_backends(manifest))
    checks.append(_extraction(manifest))

    orphans, sidecar_checks = _sidecars(manifest)
    checks.extend(sidecar_checks)
    checks.extend(_index(manifest))
    checks.append(_lock(manifest))
    checks.append(_hooks(manifest))
    return Report(tuple(checks), tuple(orphans))


def _environment() -> Iterator[Check]:
    version = sqlite3.sqlite_version
    connection = sqlite3.connect(":memory:")
    try:
        has_fts5 = bool(
            connection.execute(
                "SELECT count(*) FROM pragma_compile_options WHERE compile_options LIKE '%FTS5%'"
            ).fetchone()[0]
        )
        can_load_extensions = hasattr(connection, "enable_load_extension")
    finally:
        connection.close()

    yield Check(
        "sqlite",
        Status.OK if has_fts5 else Status.FAIL,
        f"{version}, FTS5 {'present' if has_fts5 else 'MISSING'}",
        None
        if has_fts5
        else "This Python's sqlite3 was built without FTS5, so lexical search cannot work. "
        "uv-managed CPython 3.13 includes it: `uv python install 3.13`.",
    )
    yield Check(
        "extensions",
        Status.OK if can_load_extensions else Status.WARN,
        "loadable extensions " + ("available" if can_load_extensions else "unavailable"),
        None
        if can_load_extensions
        else "Only needed for the sqlite-vec tier (v0.5); the NumPy tier is unaffected.",
    )


def _template(manifest: Manifest) -> Check:
    recorded = manifest.kb.template
    if recorded is None:
        return Check("template", Status.OK, "none recorded")
    name, _, version = recorded.partition("@")
    try:
        installed = template.describe(name)
    except PinakesError:
        return Check(
            "template",
            Status.WARN,
            f"{recorded} is not installed here",
            "The KB still works; `pnk upgrade` (v0.5) is what will diff templates.",
        )
    if installed.version != version:
        return Check(
            "template",
            Status.WARN,
            f"KB says {recorded}, installed is {installed.reference}",
            "Templates version independently of the package; nothing is applied automatically.",
        )
    return Check("template", Status.OK, recorded)


def _backends(manifest: Manifest) -> Iterator[Check]:
    for label, section, loader in (
        ("embedding", manifest.embedding, lambda: load_backend(manifest.embedding, offline=True)),
        ("reranker", manifest.rerank, lambda: load_reranker(manifest.rerank, offline=True)),
    ):
        if label == "reranker" and manifest.retrieval.rerank != "local":
            yield Check("reranker", Status.OK, "disabled in the manifest")
            continue
        try:
            info = loader().info()
        except PinakesError as exc:
            yield Check(label, Status.FAIL, exc.message, exc.remedy)
            continue

        detail = f"{info.model} ({info.provider})"
        if section.revision is None:
            yield Check(
                label,
                Status.WARN,
                f"{detail}, revision unpinned",
                f"Pin it in the manifest to make rebuilds reproducible: revision = "
                f'"{info.revision or "<hf commit sha>"}".',
            )
        else:
            yield Check(label, Status.OK, f"{detail}@{section.revision}")

    yield Check("model cache", Status.OK, f"weights resolve under {hf_cache_dir()}")


def _could_match_pdf(include: Sequence[str]) -> bool:
    """Whether an `include` pattern could ever match a `.pdf`.

    `walk_sources` applies each pattern via `root.glob(pattern)`, where `root` is already
    `sources.roots` resolved — a pattern is relative to that root, never to the KB root. A probe
    prefixed with the root's own name (e.g. "docs/") would make a bare pattern like `*.pdf` look
    like it cannot match, when `root.glob("*.pdf")` matches it directly.
    """
    probe = PurePosixPath("__pdf_probe__.pdf")
    return any(probe.full_match(pattern) for pattern in include)


def _extraction(manifest: Manifest) -> Check:
    backend = manifest.extraction.backend
    try:
        load_extractor(backend)
    except ExtractorMissingError as exc:
        if _could_match_pdf(manifest.sources.include):
            return Check(
                "pdf extractor",
                Status.WARN,
                f"`include` can match .pdf, but {backend} is not installed",
                f'Install it with `uv add "pinakes[{exc.extra}]"`, or PDFs will fail to index.',
            )
        return Check("pdf extractor", Status.OK, f"{backend} not installed (no .pdf in `include`)")
    except ExtractionError:
        pass  # the library imported; the adapter just is not implemented yet (I1)
    return Check("pdf extractor", Status.OK, f"{backend} importable")


def _sidecars(manifest: Manifest) -> tuple[list[Path], list[Check]]:
    sidecars: dict[Path, Sidecar] = {}
    orphans: list[Path] = []
    broken: list[str] = []

    for root_name in manifest.sources.roots:
        root = manifest.root / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob(f"*{SIDECAR_SUFFIX}")):
            try:
                sidecars[path] = read_sidecar(path, owner=manifest.kb.id)
            except PinakesError as exc:
                broken.append(f"{path.relative_to(manifest.root)}: {exc.message}")
                continue
            if not document_for(path).is_file():
                orphans.append(path)

    checks: list[Check] = []
    checks.append(
        Check("sidecars", Status.OK, f"{len(sidecars)} readable")
        if not broken
        else Check(
            "sidecars",
            Status.FAIL,
            f"{len(broken)} unreadable: {'; '.join(broken[:3])}",
            "Fix or remove them; a document with an unreadable sidecar cannot keep its id.",
        )
    )

    duplicates = find_duplicate_ids(sidecars)
    checks.append(
        Check("duplicate ids", Status.OK, "none")
        if not duplicates
        else Check(
            "duplicate ids",
            Status.FAIL,
            "; ".join(
                f"{doc_id} in {', '.join(str(p.relative_to(manifest.root)) for p in paths)}"
                for doc_id, paths in duplicates.items()
            ),
            "Give one of them a fresh sidecar. Never renumber a document other KBs link to.",
        )
    )
    checks.append(
        Check("orphaned sidecars", Status.OK, "none")
        if not orphans
        else Check(
            "orphaned sidecars",
            Status.WARN,
            f"{len(orphans)}: {', '.join(str(p.relative_to(manifest.root)) for p in orphans[:3])}",
            "Kept on purpose — a moved document may still want its id. Remove with "
            "`pnk doctor --prune`, which prints every path first.",
        )
    )
    return orphans, checks


def _extraction_cache(manifest: Manifest, connection: sqlite3.Connection) -> Check:
    active_hashes = store.active_content_hashes(connection)
    found = extract_cache.survey(manifest.extract_cache_dir, active_content_hashes=active_hashes)
    detail = (
        f"{found.entries} entries, {found.bytes_used} bytes "
        f"({len(found.orphans)}/{found.entries} orphaned, {len(found.paid_orphans)} paid orphans)"
    )
    if found.corrupt:
        detail += f", {len(found.corrupt)} unreadable (left alone)"
    remedies: list[str] = []
    if found.paid_orphans:
        remedies.append(
            "Paid extractions with no matching active document are kept, never swept "
            "automatically — selective removal is not implemented yet (I7c)."
        )
    if found.corrupt:
        remedies.append(
            "Unreadable cache entries are left alone rather than swept (a paid one can't be "
            "ruled out for a file that can't be read) — safe to delete by hand if you confirm "
            "they're junk, or clear the whole cache with `pnk sync --clear-cache`."
        )
    if remedies:
        return Check("extraction cache", Status.WARN, detail, " ".join(remedies))
    return Check("extraction cache", Status.OK, detail)


def _index(manifest: Manifest) -> Iterator[Check]:
    if not manifest.index_path.exists():
        yield Check("index", Status.WARN, "not built yet", "Run `pnk sync`.")
        return

    try:
        connection = store.connect_ro(manifest.index_path)
    except PinakesError as exc:
        yield Check("index", Status.FAIL, exc.message, exc.remedy)
        return

    try:
        counts = {
            name: int(connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0])
            for name in ("documents", "chunks", "failures")
        }
        active = int(
            connection.execute("SELECT count(*) FROM documents WHERE state = 'active'").fetchone()[
                0
            ]
        )
        yield Check(
            "index",
            Status.OK,
            f"{active} active documents, {counts['chunks']} chunks",
        )
        yield _extraction_cache(manifest, connection)

        try:
            check_coherence(connection, manifest)
            yield Check("model coherence", Status.OK, "index matches the configured model")
        except PinakesError as exc:
            yield Check("model coherence", Status.FAIL, exc.message, exc.remedy)

        yield _calibration(manifest)
        yield _links(connection, manifest, active)

        if counts["chunks"] > LARGE_CORPUS_CHUNKS:
            yield Check(
                "scale",
                Status.WARN,
                f"{counts['chunks']} chunks is past the {LARGE_CORPUS_CHUNKS} NumPy-tier threshold",
                "Every tier is a linear scan; the sqlite-vec tier (v0.5) bounds memory, and "
                "splitting the KB is the documented answer past ~2M chunks.",
            )
        else:
            yield Check("scale", Status.OK, f"{counts['chunks']} chunks, within the NumPy tier")

        if counts["failures"]:
            rows = connection.execute(
                "SELECT path, stage, error FROM failures ORDER BY id DESC LIMIT 3"
            )
            detail = "; ".join(f"{row['path']} ({row['stage']})" for row in rows)
            yield Check(
                "failures",
                Status.WARN,
                f"{counts['failures']} recorded: {detail}",
                "These documents are not searchable. Fix them and re-run `pnk sync`.",
            )
        else:
            yield Check("failures", Status.OK, "none recorded")
    finally:
        connection.close()


def _calibration(manifest: Manifest) -> Check:
    thresholds = manifest.retrieval.confidence
    if thresholds is None:
        return Check(
            "calibration",
            Status.WARN,
            "no fitted thresholds; confidence will report `unknown`",
            "Honest, but uninformative. Fit thresholds against a golden set (§4.2/§7).",
        )
    try:
        active = load_reranker(manifest.rerank, offline=True).info().fingerprint()
    except PinakesError:
        return Check("calibration", Status.WARN, f"fitted for {thresholds.fitted_for}", None)
    if active != thresholds.fitted_for:
        return Check(
            "calibration",
            Status.FAIL,
            f"fitted for {thresholds.fitted_for}, but {active} is configured",
            "Thresholds do not transfer between rerankers. Re-fit, or confidence reports "
            "`unknown` rather than a number it cannot justify.",
        )
    return Check("calibration", Status.OK, f"fitted for {active}")


def _links(connection: sqlite3.Connection, manifest: Manifest, active: int) -> Check:
    """Link coverage is the ceiling on cross-KB answers, so it is reported, not hidden (§6.2)."""
    rows = connection.execute(
        "SELECT dst_kb_id, dst_doc_id FROM links WHERE src_kb_id = ? AND origin = 'sidecar'",
        (manifest.kb.id,),
    )
    targets = [(str(row["dst_kb_id"]), DocId(str(row["dst_doc_id"]))) for row in rows]
    if not targets:
        return Check("links", Status.OK, f"none authored (0 of {active} documents linked)")

    known = {
        DocId(str(row["id"]))
        for row in connection.execute("SELECT id FROM documents WHERE state = 'active'")
    }
    dangling = [doc for kb_id, doc in targets if kb_id == manifest.kb.id and doc not in known]
    external = sum(1 for kb_id, _ in targets if kb_id != manifest.kb.id)

    detail = f"{len(targets)} links, {external} cross-KB (unchecked until v0.3)"
    if dangling:
        return Check(
            "links",
            Status.WARN,
            f"{detail}; {len(dangling)} dangling inside this KB",
            "A dangling link points at a document that no longer exists here.",
        )
    return Check("links", Status.OK, detail)


def _lock(manifest: Manifest) -> Check:
    path = manifest.state_dir / LOCK_NAME
    holder = read_holder(path)
    if holder is None:
        return Check(
            "sync lock", Status.OK, "free" if not path.exists() else "present but unreadable"
        )
    return Check(
        "sync lock",
        Status.WARN,
        f"held by {holder.describe()}",
        "If no sync is running, the next `pnk sync` reclaims it automatically on this host; "
        "across hosts use `pnk sync --force-unlock`.",
    )


def _hooks(manifest: Manifest) -> Check:
    hooks = manifest.root / ".git" / "hooks"
    if not (manifest.root / ".git").exists():
        return Check(
            "git hooks",
            Status.WARN,
            "not a git repository",
            "Freshness is git-triggered by design; a loose folder needs manual or cron `pnk sync`.",
        )
    installed = [
        name
        for name in ("pre-commit", "post-commit", "post-merge")
        if (hooks / name).is_file() and HOOK_MARKER in (hooks / name).read_text(encoding="utf-8")
    ]
    if len(installed) == 3:
        return Check("git hooks", Status.OK, "pre-commit, post-commit and post-merge installed")
    return Check(
        "git hooks",
        Status.WARN,
        f"{len(installed)} of 3 installed",
        "Run `pnk install-hooks` to keep the index fresh automatically.",
    )


def prune(orphans: Sequence[Path]) -> list[Path]:
    """Delete orphaned sidecars. The caller must have printed them first (§6.4)."""
    removed: list[Path] = []
    for path in orphans:
        path.unlink(missing_ok=True)
        removed.append(path)
    return removed
