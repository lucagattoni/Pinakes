"""`pnk doctor`: the checks that make the design's stated limits visible instead of mysterious."""

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
import yaml

from pinakes import store
from pinakes.budget.prices import Prices, load_prices
from pinakes.doctor import Status, diagnose, prune
from pinakes.embed import (
    ModelInfo,
    Vectors,
    register_embedding_backend,
    register_reranker,
)
from pinakes.ids import mint_doc_id
from pinakes.init import init
from pinakes.manifest import load
from pinakes.sidecar import SIDECAR_SUFFIX
from pinakes.sync import SyncOptions, sync

DIM = 3


class FakeBackend:
    def embed(self, texts: Sequence[str]) -> Vectors:
        rows = [np.ones(DIM, dtype=np.float32) for _ in texts]
        if not rows:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", "rev1", DIM, 512)


class FakeReranker:
    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        return [0.0] * len(passages)

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-reranker", "v1", 0, 512)


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    register_embedding_backend("fake", lambda section, offline: FakeBackend())
    register_reranker("fake", lambda section, offline: FakeReranker())

    result = init(tmp_path / "kb", now="20260725 17:30")
    path = result.root / "pinakes.toml"
    text = path.read_text(encoding="utf-8")
    text = text.replace('provider = "sentence-transformers"', 'provider = "fake"')
    text = text.replace('model    = "BAAI/bge-small-en-v1.5"', 'model    = "fake-model"')
    text = text.replace("dim      = 384", f"dim      = {DIM}")
    text = text.replace('model    = "BAAI/bge-reranker-base"', 'model    = "fake-reranker"')
    path.write_text(text, encoding="utf-8")

    (result.root / "docs" / "a.md").write_text("# A\n\nSome text.\n", encoding="utf-8")
    return result.root


def checks(root: Path) -> dict[str, tuple[Status, str]]:
    return {c.name: (c.status, c.detail) for c in diagnose(load(root)).checks}


def test_a_fresh_kb_reports_no_index_yet(kb: Path) -> None:
    found = checks(kb)
    assert found["index"][0] is Status.WARN
    assert "not built yet" in found["index"][1]
    assert found["sqlite"][0] is Status.OK
    assert "FTS5 present" in found["sqlite"][1]


def test_a_synced_kb_is_healthy(kb: Path) -> None:
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    found = checks(kb)
    assert found["index"][0] is Status.OK
    assert found["model coherence"][0] is Status.OK
    assert found["duplicate ids"][0] is Status.OK
    assert found["scale"][0] is Status.OK
    assert found["failures"][0] is Status.OK


def test_an_incoherent_index_is_reported_as_a_failure(kb: Path) -> None:
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    connection = store.connect_rw(kb / ".pinakes" / "index.db")
    store.set_meta(connection, {"embedding_model": "something-else"})
    connection.commit()
    connection.close()

    report = diagnose(load(kb))
    assert report.worst is Status.FAIL
    assert checks(kb)["model coherence"][0] is Status.FAIL


def test_an_uncalibrated_kb_is_a_warning_not_a_failure(kb: Path) -> None:
    """`unknown` is honest; it is worth reporting, but it is not broken."""
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    assert checks(kb)["calibration"][0] is Status.WARN


def _add_pdf(kb: Path) -> None:
    path = kb / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'include = ["**/*.md", "**/*.txt"]', 'include = ["**/*.md", "**/*.txt", "**/*.pdf"]'
        )
        + '\n[extraction]\nbackend = "fake"\n',
        encoding="utf-8",
    )


def _mark_paid(
    kb: Path, name: str, *, backend: str = "claude-vision", fingerprint: str = "fp1"
) -> None:
    """Simulate a prior paid extraction directly — `claude-vision`'s own loader is a permanent
    I7b stub, so no real one exists yet to sync through. Writes exactly what a real paid sync
    would have: the sidecar's `provenance.extraction` and the index's own two columns."""
    sidecar_file = kb / "docs" / f"{name}{SIDECAR_SUFFIX}"
    data = yaml.safe_load(sidecar_file.read_text(encoding="utf-8"))
    data.setdefault("provenance", {})["extraction"] = {
        "backend": backend,
        "fingerprint": fingerprint,
        "extracted": "20260725 17:31",
    }
    sidecar_file.write_text(yaml.safe_dump(data), encoding="utf-8")
    connection = store.connect_rw(kb / ".pinakes" / "index.db")
    try:
        connection.execute(
            "UPDATE documents SET extraction_backend = ?, extraction_fingerprint = ? "
            "WHERE path = ?",
            (backend, fingerprint, f"docs/{name}"),
        )
        connection.commit()
    finally:
        connection.close()


def _set_extraction_backend(kb: Path, backend: str) -> None:
    path = kb / "pinakes.toml"
    text = path.read_text(encoding="utf-8")
    if "[extraction]" in text:
        text = re.sub(r'backend = ".*"', f'backend = "{backend}"', text)
    else:
        text += f'\n[extraction]\nbackend = "{backend}"\n'
    path.write_text(text, encoding="utf-8")


def test_extraction_coherence_is_ok_with_nothing_stale(kb: Path) -> None:
    _add_pdf(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")

    assert checks(kb)["extraction coherence"] == (Status.OK, "none stale")


def test_extraction_coherence_warns_on_a_stale_paid_backend(kb: Path) -> None:
    """Decision 13: a paid mismatch warns and marks — it must never refuse the whole KB, unlike a
    free mismatch (`test_search.py` covers the free-refuses half directly)."""
    _add_pdf(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    _mark_paid(kb, "a.pdf", fingerprint="a-fingerprint-claude-vision-no-longer-has")

    status, detail = checks(kb)["extraction coherence"]
    assert status is Status.WARN
    assert "stale paid extraction" in detail


def test_awaiting_paid_extraction_lists_a_free_indexed_pdf_when_manifest_wants_paid(
    kb: Path,
) -> None:
    _add_pdf(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")  # indexed free, via "fake"

    _set_extraction_backend(kb, "claude-vision")  # manifest now wants paid — no sync run yet

    found = next(c for c in diagnose(load(kb)).checks if c.name == "awaiting paid extraction")
    assert found.status is Status.WARN
    assert "docs/a.pdf" in found.detail
    assert found.remedy is not None and "pnk sync" in found.remedy

    # The counterpart stays green: a free-indexed document is not "kept at a paid extraction".
    assert checks(kb)["paid extraction not requested"] == (Status.OK, "none")


def test_paid_extraction_not_requested_lists_a_paid_indexed_pdf_when_manifest_wants_free(
    kb: Path,
) -> None:
    """Decision 9 in `pnk doctor`'s own words: this one must stay green even though it lists a
    path, since it reports the protection working, not a problem (`_extraction_backend_drift`'s
    own docstring)."""
    _add_pdf(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    _mark_paid(kb, "a.pdf")  # manifest's own backend stays "fake" (free)

    found = next(c for c in diagnose(load(kb)).checks if c.name == "paid extraction not requested")
    assert found.status is Status.WARN
    assert "docs/a.pdf" in found.detail
    assert found.remedy is not None
    assert "Nothing to do" in found.remedy
    assert "--force" in found.remedy

    assert checks(kb)["awaiting paid extraction"] == (Status.OK, "none")


def test_paid_extraction_stale_lists_a_changed_file(kb: Path) -> None:
    _add_pdf(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"original content")
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    _mark_paid(kb, "a.pdf")

    (kb / "docs" / "a.pdf").write_bytes(b"changed, invalidating the paid extraction")

    found = next(c for c in diagnose(load(kb)).checks if c.name == "paid extraction stale")
    assert found.status is Status.WARN
    assert "docs/a.pdf" in found.detail
    assert found.remedy is not None
    assert "pnk sync --extract=" in found.remedy


def test_extraction_cache_check_is_ok_with_nothing_orphaned(kb: Path) -> None:
    _add_pdf(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")

    status, detail = checks(kb)["extraction cache"]
    assert status is Status.OK
    assert "1 entries" in detail
    assert "0/1 orphaned" in detail
    assert "0 paid orphans" in detail


def test_extraction_cache_check_warns_on_a_paid_orphan(kb: Path) -> None:
    """Simulates I7c's future shape directly: no real paid backend exists yet to produce one."""
    from pinakes.extract import ExtractedText
    from pinakes.extract import cache as extract_cache

    _add_pdf(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")

    paid = ExtractedText(text="paid text", page_spans=((0, 9),))
    extract_cache.get_or_extract(
        load(kb).extract_cache_dir,
        content_hash="sha256:not-any-active-document",
        backend="claude-vision",
        fingerprint="fp-paid",
        extract=lambda: paid,
        operation_id="op-999",
    )

    found = next(c for c in diagnose(load(kb)).checks if c.name == "extraction cache")
    assert found.status is Status.WARN
    assert "1 paid orphans" in found.detail
    assert found.remedy is not None
    assert "Paid extractions" in found.remedy
    assert "Unreadable" not in found.remedy  # no corrupt entries here — remedy must not mix in


def test_extraction_cache_check_warns_on_a_corrupt_entry_with_its_own_distinct_remedy(
    kb: Path,
) -> None:
    """A corrupt-only cache (zero paid orphans) must not print the paid-orphan remedy verbatim —
    that told the operator nothing about the actual trigger and nothing to do about it."""
    _add_pdf(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")

    cache_dir = load(kb).extract_cache_dir
    (cache_dir / "not-valid-json.json").write_text("{not json", encoding="utf-8")

    found = next(c for c in diagnose(load(kb)).checks if c.name == "extraction cache")
    assert found.status is Status.WARN
    assert "1 unreadable" in found.detail
    assert "0 paid orphans" in found.detail
    assert found.remedy is not None
    assert "Unreadable" in found.remedy
    assert "Paid extractions" not in found.remedy  # distinct from the paid-orphan remedy above


def test_pdf_extractor_check_is_ok_when_include_cannot_match_pdf(kb: Path) -> None:
    """The template's default `include` never matches `.pdf`, regardless of the environment."""
    assert checks(kb)["pdf extractor"][0] is Status.OK


@pytest.mark.parametrize("pdf_pattern", ["**/*.pdf", "*.pdf"])
def test_pdf_extractor_check_warns_when_include_can_match_pdf_and_backend_is_missing(
    monkeypatch: pytest.MonkeyPatch, kb: Path, pdf_pattern: str
) -> None:
    """Both a `**`-prefixed and a bare pattern must be caught — `root.glob` honours both."""
    import builtins

    real_import = builtins.__import__

    def refuse(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        if name == "pypdfium2":
            raise ImportError("no module named pypdfium2")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", refuse)

    path = kb / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'include = ["**/*.md", "**/*.txt"]',
            f'include = ["**/*.md", "**/*.txt", "{pdf_pattern}"]',
        ),
        encoding="utf-8",
    )

    found = next(c for c in diagnose(load(kb)).checks if c.name == "pdf extractor")
    assert found.status is Status.WARN
    assert "pypdfium2" in found.detail
    assert found.remedy is not None
    assert "pinakes[pdf]" in found.remedy


def test_thresholds_fitted_for_another_reranker_fail(kb: Path) -> None:
    path = kb / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n[retrieval.confidence]\nfitted_for = "someone-else@v9"\n'
        "low_below = 0.3\nhigh_above = 0.7\n",
        encoding="utf-8",
    )
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    status, detail = checks(kb)["calibration"]
    assert status is Status.FAIL
    assert "someone-else@v9" in detail


def test_an_unpinned_revision_is_a_warning_with_the_value_to_pin(kb: Path) -> None:
    status, detail = checks(kb)["embedding"]
    assert status is Status.WARN
    assert "revision unpinned" in detail


def test_orphaned_sidecars_are_reported_and_only_pruned_on_request(kb: Path) -> None:
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    (kb / "docs" / "a.md").unlink()

    report = diagnose(load(kb))
    orphan_check = next(c for c in report.checks if c.name == "orphaned sidecars")
    assert orphan_check.status is Status.WARN
    assert report.orphans and report.orphans[0].name.endswith(SIDECAR_SUFFIX)
    assert report.orphans[0].is_file()  # reported, not removed

    removed = prune(report.orphans)
    assert removed and not removed[0].exists()


def test_duplicate_ids_are_a_failure_naming_both_paths(kb: Path) -> None:
    shared = mint_doc_id()
    for name in ("a.md", "b.md"):
        (kb / "docs" / name).write_text(f"# {name}\n\ntext\n", encoding="utf-8")
        (kb / "docs" / f"{name}{SIDECAR_SUFFIX}").write_text(f"id: {shared}\n", encoding="utf-8")

    status, detail = checks(kb)["duplicate ids"]
    assert status is Status.FAIL
    assert "a.md" in detail and "b.md" in detail


def test_a_broken_sidecar_is_a_failure(kb: Path) -> None:
    (kb / "docs" / f"a.md{SIDECAR_SUFFIX}").write_text("id: not-a-ulid\n", encoding="utf-8")
    assert checks(kb)["sidecars"][0] is Status.FAIL


def test_a_held_lock_is_reported_with_its_holder(kb: Path) -> None:
    import json
    import os
    import socket

    state = kb / ".pinakes"
    state.mkdir(parents=True, exist_ok=True)
    (state / "sync.lock").write_text(
        json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "started": "20260725 17:00"}),
        encoding="utf-8",
    )
    status, detail = checks(kb)["sync lock"]
    assert status is Status.WARN
    assert str(os.getpid()) in detail


def test_a_loose_folder_is_told_it_is_not_hook_managed(kb: Path) -> None:
    status, detail = checks(kb)["git hooks"]
    assert status is Status.WARN
    assert "not a git repository" in detail


def test_recorded_failures_are_surfaced(kb: Path) -> None:
    (kb / "docs" / "bad.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    status, detail = checks(kb)["failures"]
    assert status is Status.WARN
    assert "bad.md" in detail


def test_every_problem_carries_a_remedy(kb: Path) -> None:
    """A report that says "problem" without saying "do this" is just anxiety."""
    (kb / "docs" / f"a.md{SIDECAR_SUFFIX}").write_text("id: nope\n", encoding="utf-8")
    for check in diagnose(load(kb)).checks:
        if check.status is not Status.OK:
            assert check.remedy, f"{check.name} has no remedy"


# --- the budget checks (I6b) -----------------------------------------------------------------


def test_the_price_table_is_reported_with_its_date(kb: Path) -> None:
    status, detail = checks(kb)["price table"]
    assert status is Status.OK
    assert "dated " in detail


def test_a_stale_price_table_warns_and_names_the_setting(
    kb: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Staleness is a WARN here and a refusal at estimate time — deliberately never a CI gate, or
    a quiet weekend with no code change would fail the build.

    The shipped table is current by construction, so the *table* is aged rather than the clock:
    moving `max_price_age_days` cannot reach this branch (its minimum is 1 day and today's table
    is 0 days old), and freezing the clock would test a mock rather than the comparison.
    """
    import pinakes.doctor as doctor_module

    current = load_prices()
    aged = Prices(as_of="20200101 00:00", usd_per_eur=current.usd_per_eur, models=current.models)
    monkeypatch.setattr(doctor_module, "load_prices", lambda: aged)

    status, detail = checks(kb)["price table"]
    assert status is Status.WARN
    assert "max_price_age_days" in detail
    assert "20200101 00:00" in detail


def test_a_ledger_with_no_unknown_outcomes_is_quiet(kb: Path) -> None:
    status, detail = checks(kb)["unknown outcomes"]
    assert status is Status.OK
    assert detail == "none"


def _reserve(kb: Path, *, call_id: str, cost_usd: str) -> None:
    from datetime import UTC, datetime
    from decimal import Decimal

    from pinakes.budget.ledger import Record, RecordKind, append, ledger_path

    append(
        ledger_path(kb / ".pinakes"),
        Record(
            kind=RecordKind.RESERVATION,
            at=datetime.now(UTC),
            operation_id="OP1",
            call_id=call_id,
            operation="sync",
            kb_id=load(kb).kb.id,
            model="claude-opus-5",
            cost_usd=Decimal(cost_usd),
            usd_per_eur=Decimal("1.00"),
            prices_as_of="20260728 12:00",
        ),
    )


def test_an_unknown_outcome_is_warned_about_with_the_way_out(kb: Path) -> None:
    _reserve(kb, call_id="C1", cost_usd="0.01")
    status, detail = checks(kb)["unknown outcomes"]
    assert status is Status.WARN
    assert "1 call(s)" in detail

    remedy = {c.name: c.remedy for c in diagnose(load(kb)).checks}["unknown outcomes"]
    assert remedy is not None and "pnk budget --resolve" in remedy


def test_unknown_outcomes_past_a_quarter_of_a_window_say_which_one(kb: Path) -> None:
    """Three timeouts consume a €1.00 day; sixteen consume a €5.00 month. The threshold is what
    turns "there are some unknowns" into "this is about to lock you out"."""
    path = kb / "pinakes.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("[budget]", "[budget]\ndaily_eur = 1.00"), encoding="utf-8")
    _reserve(kb, call_id="C1", cost_usd="0.30")

    status, detail = checks(kb)["unknown outcomes"]
    assert status is Status.WARN
    assert "over a quarter of daily_eur" in detail
    assert "monthly_eur" not in detail  # €0.30 is well under a quarter of €5.00


def test_a_free_backend_reports_nothing_to_explain_about_machine_driven_spend(kb: Path) -> None:
    status, detail = checks(kb)["machine-driven spend"]
    assert status is Status.OK
    assert "cannot spend" in detail


def test_a_paid_backend_with_hooks_says_the_hooks_force_the_free_one(kb: Path) -> None:
    """The split is deliberate and invisible: a user who configured `claude-vision` and installed
    hooks would otherwise have no way to know why commits never produce a paid extraction."""
    from pinakes.extract import CLAUDE_VISION
    from pinakes.hooks import FREE_BACKEND_FLAG, install

    path = kb / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + f'\n[extraction]\nbackend = "{CLAUDE_VISION}"\nmodel   = "claude-opus-5"\n',
        encoding="utf-8",
    )
    (kb / ".git").mkdir()
    install(kb)

    status, detail = checks(kb)["machine-driven spend"]
    assert status is Status.OK
    assert FREE_BACKEND_FLAG in detail
    assert CLAUDE_VISION in detail


def test_a_paid_backend_without_hooks_says_no_automatic_sync_runs(kb: Path) -> None:
    from pinakes.extract import CLAUDE_VISION

    path = kb / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + f'\n[extraction]\nbackend = "{CLAUDE_VISION}"\nmodel   = "claude-opus-5"\n',
        encoding="utf-8",
    )
    status, detail = checks(kb)["machine-driven spend"]
    assert status is Status.OK
    assert "no pinakes hooks installed" in detail
