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
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path, PurePosixPath
from statistics import median
from zoneinfo import ZoneInfo

from pinakes import store, template
from pinakes.budget.estimate import TIMESTAMP_FORMAT as PRICE_TIMESTAMP_FORMAT
from pinakes.budget.ledger import CallState, ledger_path
from pinakes.budget.ledger import read as read_ledger
from pinakes.budget.ledger import resolve as ledger_resolve
from pinakes.budget.prices import load_prices
from pinakes.budget.summary import euros
from pinakes.budget.window import in_window
from pinakes.embed import hf_cache_dir, load_backend, load_reranker
from pinakes.errors import (
    CoherenceError,
    ExtractionCoherenceError,
    ExtractionError,
    ExtractorMissingError,
    FloorsMissingError,
    HookError,
    LedgerError,
    PinakesError,
    PricesMissingError,
)
from pinakes.extract import (
    backend_requirement,
    is_backend_installed,
    is_paid_backend,
    load_extractor,
    pageyield,
    paid_backend_names,
    registered_extractors,
)
from pinakes.extract import cache as extract_cache
from pinakes.extract.floors import load_floors
from pinakes.hooks import FREE_BACKEND_FLAG, HOOKS, hooks_dir
from pinakes.ids import DocId
from pinakes.linkscan import (
    MANIFEST_NAME,
    partner_sources,
    resolve_path,
    sidecars_under,
    why_not_a_kb,
    why_unresolvable,
)
from pinakes.lock import LOCK_NAME, read_holder
from pinakes.manifest import Manifest
from pinakes.search import check_coherence
from pinakes.sidecar import SIDECAR_SUFFIX, Sidecar, document_for, find_duplicate_ids
from pinakes.sidecar import read as read_sidecar
from pinakes.sync import hash_file

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
    checks.append(_linked_kbs(manifest))
    checks.extend(_backends(manifest))
    checks.append(_extraction(manifest))

    orphans, sidecar_checks = _sidecars(manifest)
    checks.extend(sidecar_checks)
    checks.extend(_index(manifest))
    checks.append(_lock(manifest))
    checks.append(_hooks(manifest))
    checks.append(_machine_driven_split(manifest))
    checks.append(_completeness(manifest))
    checks.append(_prices(manifest))
    checks.append(_unknown_outcomes(manifest))
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
        else (
            "Only needed for the sqlite-vec tier (the template release); "
            "the NumPy tier is unaffected."
        ),
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
            "The KB still works; `pnk upgrade` (the template release) is what will diff templates.",
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


def _not_installed(manifest: Manifest, backend: str, extra: str) -> Check:
    """The one report for "the backend's library is absent", shared by both branches below."""
    if _could_match_pdf(manifest.sources.include):
        return Check(
            "pdf extractor",
            Status.WARN,
            f"`include` can match .pdf, but {backend} is not installed",
            f'Install it with `uv add "pinakes[{extra}]"`, or PDFs will fail to index.',
        )
    return Check("pdf extractor", Status.OK, f"{backend} not installed (no .pdf in `include`)")


def _extraction(manifest: Manifest) -> Check:
    backend = manifest.extraction.backend

    if is_paid_backend(backend):
        # A paid backend is probed, never loaded. `load_extractor` runs the registry's factory,
        # which imports the client — so on a KB configured for `claude-vision`, the old code made
        # `pnk doctor` import `anthropic`, on a command that cannot spend and reports availability
        # every run. That is precisely what I7a's gate 4 forbids, and doctor is in the gate's run
        # list to keep it forbidden. `is_backend_installed` answers through `find_spec`, which for
        # a top-level module adds nothing to `sys.modules`.
        requires = backend_requirement(backend)
        extra = requires[1] if requires is not None else backend
        if not is_backend_installed(backend):
            return _not_installed(manifest, backend, extra)
        return Check("pdf extractor", Status.OK, f"{backend} importable")

    try:
        load_extractor(backend)
    except ExtractorMissingError as exc:
        return _not_installed(manifest, backend, exc.extra)
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


def _extraction_backend_drift(
    manifest: Manifest, connection: sqlite3.Connection
) -> Iterator[Check]:
    """The three by-path gaps decision 9's backend-aware pairing rules exist to close (I5): a
    normal sync resolves all three the moment it runs, but nothing surfaces them *before* that —
    and "paid extraction not requested" specifically stays green even after a sync, since it is
    the protection working as designed, not a problem to fix.
    """
    paid_names = paid_backend_names()
    configured_is_paid = manifest.extraction.backend in paid_names

    rows = connection.execute(
        "SELECT path, content_hash, extraction_backend FROM documents "
        "WHERE state = 'active' AND extraction_backend IS NOT NULL"
    ).fetchall()

    awaiting_paid: list[str] = []
    paid_not_requested: list[str] = []
    paid_stale: list[str] = []
    for row in rows:
        path = str(row["path"])
        recorded_is_paid = str(row["extraction_backend"]) in paid_names

        if recorded_is_paid and not configured_is_paid:
            paid_not_requested.append(path)
        elif not recorded_is_paid and configured_is_paid:
            awaiting_paid.append(path)

        if recorded_is_paid:
            source = manifest.root / path
            if source.is_file() and hash_file(source) != str(row["content_hash"]):
                paid_stale.append(path)

    yield _drift_check(
        "awaiting paid extraction",
        awaiting_paid,
        "still indexed with a free backend though the manifest now asks for a paid one",
        "Run `pnk sync` to extract them with the configured paid backend.",
    )
    yield _drift_check(
        "paid extraction not requested",
        paid_not_requested,
        "kept at their paid extraction though the manifest currently asks for a free backend",
        "Nothing to do — decision 9's protection is working. `pnk sync --force "
        "--extract=<free-backend>` overwrites it deliberately, printing what it discards.",
    )
    yield _drift_check(
        "paid extraction stale",
        paid_stale,
        "changed on disk since their paid extraction",
        "Run `pnk sync --extract=<paid-backend>` to pay for a fresh extraction — a plain "
        "`pnk sync` will report these as failures rather than silently downgrade them.",
    )


def _drift_check(name: str, paths: list[str], situation: str, remedy: str) -> Check:
    if not paths:
        return Check(name, Status.OK, "none")
    sample = ", ".join(sorted(paths)[:3])
    more = len(paths) - 3
    detail = f"{len(paths)} {situation}: {sample}" + (f" and {more} more" if more > 0 else "")
    return Check(name, Status.WARN, detail, remedy)


def _index(manifest: Manifest) -> Iterator[Check]:
    if not manifest.index_path.exists():
        # **Naming what is missing, not only that something is.** Every check below is yielded from
        # inside this function, so an absent index silently removes them — including `links`, which
        # is the one a reader consults `pnk doctor` for after authoring any. A report that simply
        # stops listing a check reads as "nothing to report about it".
        yield Check(
            "index",
            Status.WARN,
            "not built yet, so the link checks did not run",
            "Run `pnk sync`. Link coverage, dangling targets and cross-KB resolution are all "
            "read from the index, so none of them is reported until there is one.",
        )
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
        yield from _extraction_backend_drift(manifest, connection)

        try:
            stale_paid = check_coherence(connection, manifest)
            yield Check("model coherence", Status.OK, "index matches the configured model")
            if stale_paid:
                sample = ", ".join(sorted(str(doc_id) for doc_id in stale_paid)[:3])
                more = len(stale_paid) - 3
                yield Check(
                    "extraction coherence",
                    Status.WARN,
                    f"{len(stale_paid)} document(s) have a stale paid extraction: {sample}"
                    + (f" and {more} more" if more > 0 else ""),
                    "The text is still correct, merely older, and every affected result is "
                    "marked `stale_extraction` rather than withheld. Run `pnk sync --rebuild` "
                    "to refresh it, or leave it — nothing is silently wrong (§4.4, decision 13).",
                )
            else:
                yield Check("extraction coherence", Status.OK, "none stale")
        except CoherenceError as exc:
            yield Check("model coherence", Status.FAIL, exc.message, exc.remedy)
        except ExtractionCoherenceError as exc:
            yield Check("extraction coherence", Status.FAIL, exc.message, exc.remedy)

        yield _text_yield(manifest, connection)
        yield _calibration(manifest)
        yield _links(connection, manifest, active)

        if counts["chunks"] > LARGE_CORPUS_CHUNKS:
            yield Check(
                "scale",
                Status.WARN,
                f"{counts['chunks']} chunks is past the {LARGE_CORPUS_CHUNKS} NumPy-tier threshold",
                "Every tier is a linear scan; the sqlite-vec tier (the template release) "
                "bounds memory, and splitting the KB is the documented answer past ~2M chunks.",
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


def _text_yield(manifest: Manifest, connection: sqlite3.Connection) -> Check:
    """How much text the free extractor got out of each PDF page (plans/v0.2.md, I8).

    **Per page, never per document.** A document-level median against a per-page floor is a
    different statistic from the one the paid path spends against, and it hides the case that
    matters: a 200-page report with eight scanned inserts has a healthy median, so a document-level
    check stays silent *and* the paid path's own pre-check refuses to pay for it. Both would be
    quietly right and jointly useless.

    **Measured from the extraction cache, never by re-extracting.** The cache entry is the same
    text the index was built from; re-running the extractor over every PDF on every `pnk doctor`
    would be slow, and on a stale cache would report a number no other command agrees with. A
    document whose entry has been swept is counted as unmeasured and said to be.
    """
    rows = connection.execute(
        "SELECT path, content_hash, extraction_backend, extraction_fingerprint FROM documents "
        "WHERE state = 'active' AND source_type = 'pdf' ORDER BY path"
    ).fetchall()
    if not rows:
        return Check("text yield", Status.OK, "no PDF documents")

    try:
        floor = load_floors().text_yield_floor
    except FloorsMissingError:
        floor = None

    per_page: list[int] = []
    below: list[tuple[str, tuple[int, ...]]] = []
    pages_total = 0
    measured = 0
    uncached: list[str] = []
    paid: list[str] = []
    unknown: list[str] = []
    known = set(registered_extractors())

    for row in rows:
        path = str(row["path"])
        recorded = row["extraction_backend"]
        backend = None if recorded is None else str(recorded)
        if backend is None or backend not in known:
            # A future version's KB, or an extra no longer installed. `is_paid_backend` raises on a
            # name it does not know, and a health check that crashes on an unhealthy KB is the one
            # failure `pnk doctor` may not have — the same guard §4.4's coherence check already
            # carries for the same reason.
            unknown.append(path)
            continue
        if is_paid_backend(backend):
            # Its cached text is the *paid* extraction, so measuring it would answer "did the paid
            # backend produce text" — a real question, and the completeness audit's, not this
            # check's. This one asks whether the free path suffices, which for these is settled.
            paid.append(path)
            continue
        cached = extract_cache.peek(
            manifest.extract_cache_dir,
            content_hash=str(row["content_hash"]),
            fingerprint=str(row["extraction_fingerprint"]),
        )
        if cached is None:
            uncached.append(path)
            continue
        survey = pageyield.measure(cached, floor=floor if floor is not None else 0.0)
        measured += 1
        pages_total += survey.pages_total
        per_page.extend(survey.chars_per_page)
        if floor is not None and survey.below:
            below.append((path, survey.below))

    if not per_page:
        if not uncached and not unknown:
            # Every PDF was skipped deliberately, not lost. Reporting "0 could be measured" with a
            # `pnk sync` remedy would be a permanent warning nothing can clear — and on a KB whose
            # PDFs are paid-extracted, a remedy that spends.
            return Check(
                "text yield",
                Status.OK,
                f"{len(paid)} PDF document(s), all paid-extracted — whether the free path "
                f"suffices is settled for them",
            )
        return Check(
            "text yield",
            Status.WARN,
            f"0 of {len(rows)} PDF document(s) could be measured"
            + (f"; {len(paid)} paid-extracted" if paid else "")
            + (
                f"; {len(unknown)} extracted by a backend this install does not know"
                if unknown
                else ""
            ),
            "The extraction cache holds no entry for the rest. Run `pnk sync` to repopulate it; "
            "`.pinakes/cache` is disposable, so this is expected after clearing it.",
        )

    detail = (
        f"median {median(per_page):.0f} chars/page over {measured} of {len(rows)} "
        f"PDF document(s), {pages_total} page(s)"
    )
    if paid:
        detail += f"; {len(paid)} paid-extracted, not measured here"
    if uncached:
        detail += f"; {len(uncached)} not in the extraction cache"
    if unknown:
        detail += f"; {len(unknown)} extracted by an unknown backend"

    if floor is None:
        return Check(
            "text yield",
            Status.WARN,
            f"{detail} — no fitted floor is installed, so nothing is judged",
            "floors.toml is missing from this install, so there is no threshold to compare "
            "against and this check will not invent one. Reinstall pinakes.",
        )

    if not below:
        return Check("text yield", Status.OK, f"{detail}; every page clears the {floor:g} floor")

    flagged = sum(len(pages) for _, pages in below)
    listed = ", ".join(f"{path} p{_ranges(pages)}" for path, pages in below[:3])
    more = len(below) - 3
    return Check(
        "text yield",
        Status.WARN,
        f"{detail}; pages below the {floor:g} floor: {flagged} of {pages_total} — {listed}"
        + (f", and {more} more document(s)" if more > 0 else ""),
        "Those pages have no text layer, so nothing on them is searchable. The paid Claude-vision "
        "extractor reads them: `pnk sync --extract=claude-vision` (it spends — `pnk budget` "
        "reports what, and it refuses documents the free path already handles). The floor "
        "separates empty from non-empty and nothing finer, so a page of unusable-but-present text "
        "clears it; `--force` is the escape when you know better.",
    )


def _ranges(pages: Sequence[int]) -> str:
    """`1-3,7` rather than `1,2,3,7` — a scanned insert is a run, and printing every page of a
    200-page scan would bury the check's own verdict in its evidence."""
    out: list[str] = []
    start = previous = pages[0]
    for page in pages[1:]:
        if page == previous + 1:
            previous = page
            continue
        out.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = page
    out.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(out)


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
    """Link coverage is the ceiling on cross-KB answers, so it is reported, not hidden (§6.2).

    **The ratio, not the edge count.** §6.2 promises "linked docs / total docs", and the shipped
    check printed `16 links, 4 cross-KB` — an edge count, with a ratio only in the branch where it
    is zero. On `tests/demo-kb` those 16 edges come from 8 of 30 documents, so the 27% ceiling the
    §6.2 row is tabled against was never printed. `COUNT(DISTINCT src_doc_id)` over the same
    `origin = 'sidecar'` filter is the metric; the filter itself was already right.

    **This number is as of the last sync**, because it counts index rows where L1's
    `tools/link_density_gate.py` counts sidecar files. One `pnk link` without a re-sync makes them
    disagree — measured on a copy of the committed corpus: gate 17, doctor 16. The detail line says
    so rather than pretending they cannot differ.
    """
    # **Joined to `documents`, because a soft delete leaves the links behind.** `sync`'s
    # `SoftDelete` sets `state = 'deleted'` and drops the chunks; it never deletes that document's
    # `origin = 'sidecar'` rows. `active` counts active documents only, so an unjoined numerator
    # came from a different population than its denominator — measured at `2 of 1 documents linked
    # (200%)` after deleting one of two documents that linked to each other.
    rows = connection.execute(
        "SELECT l.src_doc_id, l.dst_kb_id, l.dst_doc_id FROM links l "
        "JOIN documents d ON d.id = l.src_doc_id AND d.state = 'active' "
        "WHERE l.src_kb_id = ? AND l.origin = 'sidecar'",
        (manifest.kb.id,),
    )
    authored = [
        (DocId(str(row["src_doc_id"])), str(row["dst_kb_id"]), DocId(str(row["dst_doc_id"])))
        for row in rows
    ]
    linked = len({src for src, _, _ in authored})
    share = f"{linked} of {active} documents linked ({linked / active:.0%})" if active else "0 of 0"

    if not authored:
        # **A nudge, KB-wide.** Not per-document: L1's ≤ 35% cap guarantees a per-document rule
        # would fire on both committed corpora by construction, which is a check that cannot pass.
        return Check(
            "links",
            Status.WARN,
            f"none authored ({share})",
            "Nothing links to anything, so `pnk links` has nothing to traverse and a cross-KB "
            "answer has no path to follow. `pnk link <source> <target> --rel <relation>` "
            "authors one.",
        )

    known = {
        DocId(str(row["id"]))
        for row in connection.execute("SELECT id FROM documents WHERE state = 'active'")
    }
    dangling = [doc for _, kb_id, doc in authored if kb_id == manifest.kb.id and doc not in known]
    external = [(kb_id, doc) for _, kb_id, doc in authored if kb_id != manifest.kb.id]
    unresolved = _unresolved_cross_kb(manifest, external)

    detail = f"{share}, {len(authored)} links, {len(external)} cross-KB (as of the last sync)"
    remedies: list[str] = []
    if dangling:
        detail += f"; {len(dangling)} dangling inside this KB"
        remedies.append("A dangling link points at a document that no longer exists here.")
    if unresolved:
        detail += f"; {len(unresolved)} cross-KB unresolved"
        remedies.append(
            "A cross-KB target names a document its own KB does not have. Re-sync that KB, or "
            "the link was written against a document since removed."
        )
    if remedies:
        return Check("links", Status.WARN, detail, " ".join(remedies))
    return Check("links", Status.OK, detail)


def _unresolved_cross_kb(
    manifest: Manifest, external: list[tuple[str, DocId]]
) -> list[tuple[str, DocId]]:
    """Cross-KB targets whose own KB is on this machine and does not have the document.

    **The partner's committed sidecars, never its index** — DESIGN §6.2, verbatim: reverse links
    come from the other KB's sidecars, *"not its index, which is gitignored and simply absent in a
    fresh clone, and which could not be read without holding a second KB's lock"*. The first
    version of this function opened `<partner>/.pinakes/index.db` read-only, which breaks that rule
    two ways: measured, a `mode=ro` connection still materialises `index.db-shm` and `index.db-wal`
    inside the partner's `.pinakes/` and cannot checkpoint them away on close, so a *diagnostic*
    command writes into a KB it was only asked to look at.

    **Keyed on the partner's own `[kb] id`, never the local declaration.** `linkscan.scan_one`
    refuses a mismatch with `LinkedKbIdMismatchError` because trusting the manifest files another
    KB's links under this alias; the first version keyed on `linked.id` and so resolved targets
    against whichever KB happened to sit at that path — measured both ways, it silently resolved a
    target that did not exist and reported one that did.

    **An incomplete walk proves nothing.** If any sidecar cannot be read, or `[sources]` reports a
    problem, that partner is skipped rather than treated as "does not have it" — the same rule
    `ScannedKb.complete` encodes for the delete, for the same reason: absence of evidence here
    would be reported to a user as evidence of absence.

    **Only KBs that resolved.** A target in a KB not checked out here is not evidence of anything —
    `graph/provider.py` refuses to call one `unresolved` for exactly this reason, and doctor may not
    assert what it has no standing to know either. Absent KBs are `_linked_kbs`'s business, as a
    fact about this machine.

    **`owner=partner_id` is the correct value and is unobservable**, measured: only `.id` is kept,
    and `owner` reaches nothing but `resolve_link`, which expands `pnk://self/…` in links that are
    then discarded. Substituting the local id is caught by no test and changes no output. It stays
    because it is what this argument means, and because a later reader keeping the links — which is
    the shape `linkscan` exists to get right — would need it. Recorded so nobody re-derives it.

    **Cost: linear in the partner's corpus, uncached, on every `pnk doctor`.** Measured at
    ~0.38ms per sidecar, dominated by `read_sidecar`: 100 documents 0.04s, 1 000 0.38s, 5 000 1.9s.
    `linkscan.scan` amortises the identical walk behind `TTL_MINUTES`; this has no equivalent
    because a diagnostic is expected to be current, and caching a health check is how a health
    check comes to report yesterday's health. Acceptable at the sizes pinakes targets — the
    corpus-size warning fires at 50k *chunks* — and stated here rather than discovered later.
    """
    wanted = {kb_id for kb_id, _ in external}
    if not wanted:
        return []

    have: dict[str, set[DocId]] = {}
    for linked in manifest.links:
        root = resolve_path(manifest.root, linked.path)
        if root is None:
            continue
        try:
            partner_id, roots, include, exclude = partner_sources(root)
        except (OSError, ValueError, tomllib.TOMLDecodeError, PinakesError):
            continue
        if str(partner_id) not in wanted:
            continue
        try:
            sidecars, problems = sidecars_under(root, roots, include, exclude)
        except (OSError, ValueError, NotImplementedError, PinakesError):
            continue
        if problems:
            continue  # `[sources]` itself is unusable — the walk cannot have been exhaustive
        ids: set[DocId] = set()
        for path in sidecars:
            try:
                ids.add(read_sidecar(path, owner=partner_id).id)
            except PinakesError:
                break
        else:
            have[str(partner_id)] = ids

    return [(kb, doc) for kb, doc in external if kb in have and doc not in have[kb]]


def _is_absolute_once_expanded(raw: str) -> bool:
    """Whether a `[[links.kb]] path` escapes the KB root — after `~` expansion, as `resolve_path`
    does it.

    `Path("~/kb").is_absolute()` is `False`, but `linkscan._resolve` expands first and *then* takes
    the absolute branch, so `~/kb` is never resolved relative to the KB root — which is the property
    this warning defends. Checking the unexpanded string let every `~` path through.

    `expanduser()` raises `RuntimeError` for an unknown user; that path is unresolvable and reported
    as such by the caller, so it is not additionally absolute.
    """
    try:
        return Path(raw).expanduser().is_absolute()
    except RuntimeError:
        return False


def _linked_kbs(manifest: Manifest) -> Check:
    """Every `[[links.kb]]` entry: is its path usable, and is that KB actually here?

    **One `Check`, always** — `OK, "none declared"` when there are none, never an absent check.
    `test_every_doctor_check_is_exercised_by_a_test` builds its set from `diagnose()` on a fixture
    that declares no linked KB, so a check that disappears there is a check the coverage guard
    cannot see. Returning one unconditionally exposes this to that guard rather than exempting it.

    **Outside `_index`,** which returns at its first branch when `.pinakes/` is absent. This needs
    only the manifest, and a freshly cloned KB with no index is exactly when a committed absolute
    path matters most.

    **Nothing here is FAIL.** `cli.py`'s `doctor` exits non-zero only on `Status.FAIL`, and none of
    these is a broken KB — a partner not checked out on this machine is a fact about the machine.
    """
    if not manifest.links:
        return Check("linked KBs", Status.OK, "none declared")

    unresolvable: list[str] = []
    absent: list[str] = []
    absolute: list[str] = []
    resolvable = 0

    for linked in manifest.links:
        if _is_absolute_once_expanded(linked.path):
            # Reported whether or not it resolves: a committed absolute path publishes one
            # machine's filesystem layout to everyone who clones the KB, and stops working the
            # moment anyone checks it out elsewhere.
            absolute.append(linked.name)
        root = resolve_path(manifest.root, linked.path)
        if root is None:
            unresolvable.append(f"{linked.name} ({why_unresolvable(manifest.root, linked.path)})")
            continue
        try:
            if (root / MANIFEST_NAME).is_file():
                resolvable += 1
            else:
                absent.append(f"{linked.name} ({why_not_a_kb(root)})")
        except OSError as exc:
            # `why_not_a_kb` raises on an unreadable parent (`~root` is mode 0700 on macOS) and on
            # ENAMETOOLONG, and so does the probe. Its docstring names this as its third caller
            # needing the same `try` that `linkscan.scan_one` and `link._via_alias` have: a
            # diagnostic command reporting a traceback is the one outcome `pnk doctor` may not have.
            absent.append(f"{linked.name} ({exc.strerror or exc})")

    detail = f"{len(manifest.links)} declared, {resolvable} resolvable"
    remedies: list[str] = []
    if unresolvable:
        detail += f"; unresolvable: {', '.join(unresolvable)}"
        remedies.append(
            "A `[[links.kb]] path` that names no path at all cannot be read on any machine. "
            "Correct it in `pinakes.toml`."
        )
    if absent:
        detail += f"; not here: {', '.join(absent)}"
        remedies.append(
            "That KB is not on this machine, so its inbound links cannot be read. Clone it to "
            "the declared path, or drop the `[[links.kb]]` entry."
        )
    if absolute:
        detail += f"; absolute: {', '.join(absolute)}"
        remedies.append(
            "An absolute `path` is committed to `pinakes.toml` and publishes this machine's "
            "layout. Make it relative to the KB root, for example `../partner-kb`."
        )
    if remedies:
        return Check("linked KBs", Status.WARN, detail, " ".join(remedies))
    return Check("linked KBs", Status.OK, detail)


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
    if not (manifest.root / ".git").exists():
        return Check(
            "git hooks",
            Status.WARN,
            "not a git repository",
            "Freshness is git-triggered by design; a loose folder needs manual or cron `pnk sync`.",
        )
    installed = _installed_hooks(manifest)
    if len(installed) == len(HOOKS):
        return Check("git hooks", Status.OK, "pre-commit, post-commit and post-merge installed")
    return Check(
        "git hooks",
        Status.WARN,
        f"{len(installed)} of {len(HOOKS)} installed",
        "Run `pnk install-hooks` to keep the index fresh automatically.",
    )


def _installed_hooks(manifest: Manifest) -> list[str]:
    """Which of our hooks are installed. Resolved through `hooks.hooks_dir`, not
    `root/.git/hooks`: inside a git worktree or submodule `.git` is a *file* pointing elsewhere, so
    the naive path names a directory that does not exist and every hook reads as absent."""
    try:
        directory = hooks_dir(manifest.root)
    except HookError:
        return []
    return [
        name
        for name in HOOKS
        if (directory / name).is_file()
        and HOOK_MARKER in (directory / name).read_text(encoding="utf-8", errors="replace")
    ]


def _machine_driven_split(manifest: Manifest) -> Check:
    """Make the paid/free split visible rather than surprising (I6b, §6.3).

    On a KB configured for a paid backend, every machine-driven sync — the three hooks and the
    `pnk init --ci` workflow — forces `--extract=pypdfium2`. That is deliberate and it is also
    invisible: a user who configured `claude-vision` and installed hooks would otherwise have no
    way to know why their commits never produce a paid extraction. The count of documents this
    leaves waiting is already reported by the `awaiting paid extraction` check, which is why it is
    named here rather than recomputed.
    """
    backend = manifest.extraction.backend
    if not is_paid_backend(backend):
        return Check("machine-driven spend", Status.OK, "the configured backend cannot spend")
    installed = _installed_hooks(manifest)
    if not installed:
        return Check(
            "machine-driven spend",
            Status.OK,
            f"{backend} configured; no pinakes hooks installed, so no automatic sync runs",
        )
    return Check(
        "machine-driven spend",
        Status.OK,
        f"{backend} configured, but {len(installed)} hook(s) force {FREE_BACKEND_FLAG} — a hook "
        "is non-interactive and can never spend",
        "Paid extraction is a `pnk sync` you run. See `awaiting paid extraction` above for how "
        "many documents that leaves.",
    )


def _completeness(manifest: Manifest) -> Check:
    """Report pages a paid extraction scored below their own document's median (I7c).

    Read from the cache entries the extraction already wrote, so this costs a few file reads and
    **never** a re-extraction — the audit is report-only, and a health check that could spend money
    would be the last place anyone would look for one.

    An entry with no audit is "not audited", which is not "audited and fine": it is left out of
    both numbers rather than counted as a pass, which is the vacuous-metric failure §7 exists to
    avoid.
    """
    from pinakes.extract.audit import from_provenance

    cache_dir = manifest.extract_cache_dir
    if not cache_dir.is_dir():
        return Check("completeness", Status.OK, "no paid extractions to audit")

    audited = 0
    flagged: list[str] = []
    for entry in sorted(cache_dir.glob("*.json")):
        cached = extract_cache.read_entry(entry)
        if cached is None:
            continue
        report = from_provenance(cached.per_page_provenance)
        if report is None:
            continue
        audited += 1
        flagged.extend(report.low_coverage_paths(entry.stem))
    if audited == 0:
        return Check("completeness", Status.OK, "no paid extractions to audit")
    if not flagged:
        return Check(
            "completeness", Status.OK, f"{audited} paid extraction(s), no page below median"
        )
    sample = ", ".join(flagged[:3])
    more = len(flagged) - 3
    return Check(
        "completeness",
        Status.WARN,
        f"{len(flagged)} page(s) across {audited} paid extraction(s) scored below their own "
        f"document's median: {sample}" + (f" and {more} more" if more > 0 else ""),
        "Report-only — nothing was re-extracted and nothing spent. Open the pages and decide; "
        "a low score can equally mean the native layer was junk the paid pass correctly dropped.",
    )


def _prices(manifest: Manifest) -> Check:
    """Staleness is a WARN here and a refusal at estimate time — deliberately never a CI gate, or a
    quiet weekend with no code change would fail the build (plans/v0.2.md, I6a)."""
    try:
        prices = load_prices()
    except PricesMissingError as exc:
        return Check("price table", Status.FAIL, exc.message, exc.remedy)
    try:
        as_of = datetime.strptime(prices.as_of, PRICE_TIMESTAMP_FORMAT)
    except ValueError:
        return Check(
            "price table",
            Status.FAIL,
            f"as_of {prices.as_of!r} is not a {PRICE_TIMESTAMP_FORMAT} timestamp",
            "This is a packaging defect in pinakes itself; report it.",
        )
    age = (datetime.now() - as_of).days
    limit = manifest.budget.max_price_age_days
    if age > limit:
        return Check(
            "price table",
            Status.WARN,
            f"prices.toml is dated {prices.as_of}, {age} days old "
            f"(`[budget] max_price_age_days` is {limit})",
            "Upgrade pinakes to refresh the bundled prices. Past this age estimation refuses "
            "outright rather than quietly using numbers that may no longer be true.",
        )
    return Check("price table", Status.OK, f"dated {prices.as_of}, {age} day(s) old")


def _unknown_outcomes(manifest: Manifest) -> Check:
    """A reservation with neither a reconciliation nor a void counts at its reserved amount
    forever (I6a's rule), so unknowns quietly eat the windows they belong to. Compared against the
    day and month caps only, and each against the unknowns that actually fall in *that* window —
    a per-operation cap bounds the run in progress, which past operations' unknowns do not touch.
    """
    path = ledger_path(manifest.state_dir)
    try:
        resolved = ledger_resolve(read_ledger(path).records)
    except LedgerError as exc:
        return Check("unknown outcomes", Status.FAIL, exc.message, exc.remedy)

    unknown = [call for call in resolved.calls if call.state is CallState.UNKNOWN]
    if not unknown:
        return Check("unknown outcomes", Status.OK, "none")

    now = datetime.now(UTC)
    timezone = ZoneInfo(manifest.budget.timezone)
    day_total = Decimal("0")
    month_total = Decimal("0")
    for call in unknown:
        in_day, in_month = in_window(call.reservation.at, now=now, timezone=timezone)
        if in_day:
            day_total += call.effective_eur
        if in_month:
            month_total += call.effective_eur

    breached = [
        name
        for name, total, cap in (
            ("daily_eur", day_total, manifest.budget.daily_eur),
            ("monthly_eur", month_total, manifest.budget.monthly_eur),
        )
        if total * 4 > cap
    ]
    # Formatted, never printed raw: `cost_eur` is a division, so a bare f-string renders it at
    # `Decimal`'s full 28 significant digits.
    detail = (
        f"{len(unknown)} call(s) neither reconciled nor voided — €{euros(month_total)} of this "
        f"month's budget, €{euros(day_total)} of today's"
    )
    remedy = (
        "`pnk budget` lists them; check the vendor's usage dashboard and close each with "
        "`pnk budget --resolve <call_id> --actual <eur>`, which appends a reconciliation rather "
        "than editing the ledger."
    )
    if not breached:
        return Check("unknown outcomes", Status.WARN, detail, remedy)
    return Check(
        "unknown outcomes",
        Status.WARN,
        f"{detail}; over a quarter of {', '.join(breached)}",
        remedy,
    )


def prune(orphans: Sequence[Path]) -> list[Path]:
    """Delete orphaned sidecars. The caller must have printed them first (§6.4)."""
    removed: list[Path] = []
    for path in orphans:
        path.unlink(missing_ok=True)
        removed.append(path)
    return removed
