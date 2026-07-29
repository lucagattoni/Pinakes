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
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path, PurePosixPath
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
    paid_backend_names,
)
from pinakes.extract import cache as extract_cache
from pinakes.hooks import FREE_BACKEND_FLAG, HOOKS, hooks_dir
from pinakes.ids import DocId
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

    detail = f"{len(targets)} links, {external} cross-KB (unchecked until the graph release)"
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
