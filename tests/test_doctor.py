"""`pnk doctor`: the checks that make the design's stated limits visible instead of mysterious.

**The template-drift tests at the end of this file run against a synthetic two-version template,
not against `notes`.** D-2b leaves the shipped template with exactly one archived version, so the
only outcome `notes` can reach is *cannot compare* — one test asserts exactly that, deliberately,
because it is the path every KB in existence takes. Everything that asserts a line count, an
absent hunk or a rendered variable builds its own template. A suite that quietly exercised only the
reachable path would report green over a feature nobody had run.
"""

import difflib
import importlib
import itertools
import re
import shutil
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
import yaml
from conftest import pdf_extraction_runnable

from pinakes import store, template
from pinakes.budget.prices import Prices, load_prices
from pinakes.doctor import Check, Status, diagnose, prune
from pinakes.embed import (
    ModelInfo,
    Vectors,
    register_embedding_backend,
    register_reranker,
)
from pinakes.errors import TemplateError
from pinakes.ids import mint_doc_id, mint_kb_id
from pinakes.init import init
from pinakes.manifest import load
from pinakes.sidecar import SIDECAR_SUFFIX, minted_title
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


def template_check(root: Path) -> Check:
    """The whole `template` check, remedy included — `checks` drops the remedy, and for this check
    the remedy is the part the user acts on."""
    (check,) = (c for c in diagnose(load(root)).checks if c.name == "template")
    return check


def _document_ids(root: Path, where: str = "state = 'active'") -> list[str]:
    """Read document ULIDs and **close the connection** — a generator expression over
    `connect_ro(...).execute(...)` leaks one, which pytest raises as an unraisable exception."""
    connection = store.connect_ro(root / ".pinakes" / "index.db")
    try:
        return [
            str(row["id"]) for row in connection.execute(f"SELECT id FROM documents WHERE {where}")
        ]
    finally:
        connection.close()


def _remedy(root: Path, name: str) -> str:
    """Every new WARN must carry one, and `test_every_problem_carries_a_remedy` cannot see these:
    it runs on a fixture that declares no `[[links.kb]]` and authors no link, where both new
    checks are `OK` and carry no problem.

    **Returns it for the caller to assert content against.** Asserting `is not None` here matched
    `""` — measured: four of the five new remedies could be blanked with the whole suite green,
    while the meta-guard this stands in for asserts truthiness.
    """
    remedy = next(c.remedy for c in diagnose(load(root)).checks if c.name == name)
    assert remedy, f"{name} warned without a remedy"
    return remedy


def test_a_fresh_kb_reports_no_index_yet(kb: Path) -> None:
    found = checks(kb)
    assert found["index"][0] is Status.WARN
    assert "not built yet" in found["index"][1]
    assert found["sqlite"][0] is Status.OK
    assert "FTS5 present" in found["sqlite"][1]


def test_an_unsynced_kb_says_the_link_checks_did_not_run(kb: Path) -> None:
    """Every check in `_index` is yielded from inside it, so an absent index silently removes them
    — `links` included, which is the one a reader consults `pnk doctor` for after authoring any.

    L8's verification asks for this in as many words: on an unsynced KB, doctor must still exit 0
    **and say the link checks could not run**. It exited 0 and said nothing; a report that stops
    listing a check reads as "nothing to report about it".
    """
    found = checks(kb)
    assert "links" not in found, "the fixture is meant to have no index"
    assert "the link checks did not run" in found["index"][1]
    assert "coverage" in (_remedy(kb, "index") or "")


# --- doctor never prints an absolute path under the KB root (open-corrections item 5) -----------


def test_model_cache_path_outside_the_kb_root_is_left_absolute(kb: Path) -> None:
    """The model cache is not under the KB root, so it is deliberately never rewritten — see the
    doctor module's `_de_homed` docstring for why (relativising a path outside the KB would either
    be a no-op full of `..` noise, or invent a base that means nothing). Pins the boundary the two
    leak tests below rely on: only a path under `manifest.root` gets rewritten, everything else is
    printed exactly as the module that raised it wrote it."""
    from pinakes.embed import hf_cache_dir

    status, detail = checks(kb)["model cache"]
    assert status is Status.OK
    assert str(hf_cache_dir()) in detail


def test_an_unreadable_sidecar_error_does_not_leak_the_kb_root(kb: Path) -> None:
    """`sidecar.read` builds `SidecarError` from the absolute `Path` it was given
    (`f"{path} {message}."`), and `_sidecars` used to forward that text verbatim after its own
    relative-path prefix — so the absolute path still appeared, once, right after the relative one
    doctor.py had just constructed correctly."""
    broken = kb / "docs" / f"broken.md{SIDECAR_SUFFIX}"
    broken.write_text("{not: valid: yaml:", encoding="utf-8")

    status, detail = checks(kb)["sidecars"]
    assert status is Status.FAIL
    assert str(kb) not in detail, "the KB root must not appear in doctor's own output"
    assert "docs/broken.md.pnk.yaml" in detail, "the file is still named, relative to the KB root"


def test_a_schema_mismatch_error_does_not_leak_the_kb_root(kb: Path) -> None:
    """`store._open` builds `IndexSchemaError`/`StoreError` from the absolute index path — reached
    here without a real sync, since `store.create` plus a bad `schema_version` is enough to make
    `connect_ro` refuse it, exactly as `_index` does on every `pnk doctor` run."""
    connection = store.create(load(kb).index_path)
    store.set_meta(connection, {"schema_version": "999"})
    connection.commit()
    connection.close()

    status, detail = checks(kb)["index"]
    assert status is Status.FAIL
    assert str(kb) not in detail
    assert ".pinakes/index.db" in detail


def test_a_ledger_read_error_does_not_leak_the_kb_root(kb: Path) -> None:
    """`budget.ledger.read` builds `LedgerError` from the absolute ledger path on any `OSError`
    other than a missing file. A directory sitting where the ledger file should be is the simplest
    portable way to force one — `Path.read_text()` on a directory raises `IsADirectoryError`."""
    from pinakes.budget.ledger import ledger_path

    manifest = load(kb)
    manifest.state_dir.mkdir(parents=True, exist_ok=True)
    ledger_path(manifest.state_dir).mkdir()

    status, detail = checks(kb)["unknown outcomes"]
    assert status is Status.FAIL
    assert str(kb) not in detail
    assert ".pinakes/ledger.jsonl" in detail


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


def test_an_interrupted_first_sync_warns_and_never_says_rebuild(kb: Path) -> None:
    """Item 11 — the RFC corpus's near-hour-of-work loss. `sync.py` writes the embedding identity
    keys with `set_meta` only after the document loop finishes, so a first sync killed mid-run
    leaves `meta` holding `schema_version` and nothing else. That is "never finished", not "built
    under a different model", and it must not be reported (or remedied) as the latter: `--rebuild`
    on an interrupted index discards every embedding that survived.

    The `--rebuild` assertion is the one that actually carries the fix — a test that only checks
    the check's *name* or *status* would still pass with the destructive remedy printed underneath.
    """
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    connection = store.connect_rw(kb / ".pinakes" / "index.db")
    connection.execute(
        "DELETE FROM meta WHERE key IN ('embedding_provider', 'embedding_model', 'embedding_dim')"
    )
    connection.commit()
    connection.close()

    report = diagnose(load(kb))
    assert report.worst is Status.WARN

    found = checks(kb)
    assert "model coherence" not in found, "not a coherence failure — must not share its name"
    status, detail = found["sync completeness"]
    assert status is Status.WARN
    assert "never finished" in detail or "did not finish" in detail

    remedy = _remedy(kb, "sync completeness")
    assert "pnk sync" in remedy
    assert "--rebuild" not in remedy, "the destructive remedy must never appear on this branch"


def test_a_partially_written_meta_is_still_a_coherence_failure(kb: Path) -> None:
    """Some embedding identity keys present, some absent, is neither "never finished" (all absent)
    nor a clean mismatch — item 11 requires it fall to the FAIL side, never silently into the
    benign incomplete-sync branch a careless `not all(...)` check would put it in."""
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    connection = store.connect_rw(kb / ".pinakes" / "index.db")
    connection.execute("DELETE FROM meta WHERE key = 'embedding_dim'")
    connection.commit()
    connection.close()

    report = diagnose(load(kb))
    assert report.worst is Status.FAIL
    found = checks(kb)
    assert found["model coherence"][0] is Status.FAIL
    assert "sync completeness" not in found


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


def _reserve(kb: Path, *, call_id: str, cost_usd: str, rate: str = "1.00") -> None:
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
            usd_per_eur=Decimal(rate),
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


def test_hooks_are_found_inside_a_git_worktree(kb: Path, tmp_path: Path) -> None:
    """In a worktree or submodule `.git` is a *file* pointing elsewhere. Probing
    `root/.git/hooks` directly names a directory that does not exist, so every hook reads as
    absent and both hook checks quietly report the wrong thing on exactly the layout this
    project's own docs/BUILDING.md mandates for every change."""
    from pinakes.hooks import install

    real_gitdir = tmp_path / "real-gitdir"
    real_gitdir.mkdir()
    (kb / ".git").write_text(f"gitdir: {real_gitdir}\n", encoding="utf-8")
    install(kb)
    assert (real_gitdir / "hooks" / "pre-commit").is_file()

    status, detail = checks(kb)["git hooks"]
    assert status is Status.OK, detail


def test_the_unknown_outcome_total_is_formatted_not_a_raw_decimal(kb: Path) -> None:
    """`cost_eur` is a division: $0.10 at 1.08 is €0.0925925925925925925925925926, and a bare
    f-string puts all 28 significant digits into a health-check line."""
    _reserve(kb, call_id="C1", cost_usd="0.10", rate="1.08")
    _status, detail = checks(kb)["unknown outcomes"]
    assert "€0.0926" in detail
    assert "0.09259259" not in detail


def test_completeness_is_quiet_when_nothing_paid_has_been_extracted(kb: Path) -> None:
    status, detail = checks(kb)["completeness"]
    assert status is Status.OK
    assert "no paid extractions to audit" in detail


def test_completeness_warns_about_a_page_below_its_documents_median(kb: Path) -> None:
    """Read from the cache entry the extraction already wrote — a health check must never be able
    to spend money, and re-running the audit would mean re-extracting."""
    import json as json_module

    cache = kb / ".pinakes" / "cache" / "extract"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "abc-fp.json").write_text(
        json_module.dumps(
            {
                "schema": 1,
                "content_hash": "sha256:abc",
                "backend": "claude-vision",
                "fingerprint": "fp",
                "page_count": 3,
                "page_spans": [[0, 1], [1, 2], [2, 3]],
                "text": "abc",
                "per_page_provenance": [
                    {"audit": "0.980"},
                    {"audit": "0.310 below-median"},
                    {"audit": "0.990"},
                ],
                "operation_id": "OP1",
                "call_ids": ["CALL-A"],
            }
        ),
        encoding="utf-8",
    )
    status, detail = checks(kb)["completeness"]
    assert status is Status.WARN
    assert "abc-fp:2" in detail

    remedy = {c.name: c.remedy for c in diagnose(load(kb)).checks}["completeness"]
    assert remedy is not None and "nothing spent" in remedy


def test_an_unaudited_entry_is_left_out_rather_than_counted_as_a_pass(kb: Path) -> None:
    """A free extraction carries no audit. Counting it as "no page below median" would be a pass
    rate inflated by everything that was never measured."""
    import json as json_module

    cache = kb / ".pinakes" / "cache" / "extract"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "free-fp.json").write_text(
        json_module.dumps(
            {
                "schema": 1,
                "content_hash": "sha256:free",
                "backend": "pypdfium2",
                "fingerprint": "fp",
                "page_count": 1,
                "page_spans": [[0, 1]],
                "text": "x",
                "per_page_provenance": [],
                "operation_id": None,
                "call_ids": None,
            }
        ),
        encoding="utf-8",
    )
    status, detail = checks(kb)["completeness"]
    assert status is Status.OK
    assert "no paid extractions to audit" in detail, "not '1 paid extraction, nothing below median'"


# --- text yield: per page, never per document ---------------------------------------------------


PDF_CORPUS = Path(__file__).parent / "pdf-corpus"


@pytest.fixture
def pdf_kb(kb: Path) -> Path:
    """The healthy 12-page baseline beside a wholly scanned 3-page fixture.

    A real mixed corpus rather than a hand-built cache entry: the check reads what `pnk sync`
    wrote, so a fixture that wrote it by hand would be testing the test.
    """
    path = kb / "pinakes.toml"
    body = path.read_text(encoding="utf-8")
    include = 'include = ["**/*.md", "**/*.txt"]'
    assert include in body, "the template's include line has changed shape"
    path.write_text(
        body.replace(include, 'include = ["**/*.md", "**/*.txt", "**/*.pdf"]'), encoding="utf-8"
    )
    for name in ("baseline-12p.pdf", "scanned-clean.pdf"):
        (kb / "docs" / name).write_bytes((PDF_CORPUS / name).read_bytes())
    sync(load(kb), options=SyncOptions(), now="20260729 05:10")
    return kb


def test_text_yield_is_quiet_when_there_are_no_pdfs(kb: Path) -> None:
    sync(load(kb), options=SyncOptions(), now="20260729 05:10")
    status, detail = checks(kb)["text yield"]
    assert status is Status.OK
    assert detail == "no PDF documents"


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_text_yield_flags_pages_not_documents(pdf_kb: Path) -> None:
    """The whole reason the check reports per page: the median is healthy — twelve good pages
    against six empty ones — and it must fire anyway, naming the pages that have no text.

    A document-level median against a per-page floor would stay silent here *and* the paid path's
    own pre-check would still refuse to pay for the healthy document. Both quietly right, jointly
    useless.
    """
    status, detail = checks(pdf_kb)["text yield"]

    assert status is Status.WARN
    assert "scanned-clean.pdf p1-6" in detail, "by path and page, as a range rather than a list"
    assert "baseline-12p" not in detail, "the healthy document must not be named as a problem"
    assert "pages below the" in detail and "6 of 18" in detail

    match = re.search(r"median (\d+) chars/page", detail)
    assert match is not None, "the check must report the distribution it judged against"
    median_reported = int(match.group(1))
    assert median_reported > 100, (
        f"the median is healthy ({median_reported}/page) and the check fired regardless — "
        "that is the statistic the plan says a document-level check would get wrong"
    )


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_text_yield_names_the_paid_path_and_its_cost_in_the_remedy(pdf_kb: Path) -> None:
    """ "Out of scope" is not a remedy. The pages have no text layer; something can read them, it
    costs money, and the check says which and that it does."""
    remedy = next(c.remedy for c in diagnose(load(pdf_kb)).checks if c.name == "text yield")
    assert remedy is not None
    assert "--extract=claude-vision" in remedy
    assert "spends" in remedy and "pnk budget" in remedy
    assert "--force" in remedy


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_with_no_fitted_floor_the_distribution_is_reported_and_nothing_is_judged(
    pdf_kb: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent the floor, the check reports what it measured and says the floor is missing — it
    does not invent a threshold, and it does not fall silent either."""
    from pinakes import doctor as doctor_module
    from pinakes.errors import FloorsMissingError

    def no_floors() -> object:
        raise FloorsMissingError(reason="floors.toml is missing")

    monkeypatch.setattr(doctor_module, "load_floors", no_floors)
    status, detail = checks(pdf_kb)["text yield"]

    assert status is Status.WARN
    assert "no fitted floor" in detail
    assert "median" in detail, "the distribution is still reported"
    assert "below the" not in detail, "nothing may be judged against a floor that is not installed"


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_swept_cache_entry_is_counted_as_unmeasured_rather_than_as_a_pass(
    pdf_kb: Path,
) -> None:
    """`.pinakes/cache` is disposable by design, so an absent entry is expected — but a document
    nobody measured must never be reported as one that cleared the floor."""
    for entry in (pdf_kb / ".pinakes" / "cache" / "extract").glob("*.json"):
        entry.unlink()

    status, detail = checks(pdf_kb)["text yield"]
    assert status is Status.WARN
    assert "0 of 2 PDF document(s) could be measured" in detail


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_partly_swept_cache_still_names_what_it_could_not_measure(pdf_kb: Path) -> None:
    """The mixed case, and the one a wholly-swept cache cannot cover: when *some* documents were
    measured, the ones that were not must be named in the same line as the median — otherwise a
    reader takes a healthy-looking distribution for a statement about the whole corpus.

    Found by mutation: deleting the unmeasured tally left the wholly-swept test green, because
    that test reads a branch which counts documents rather than the tally.
    """
    connection = store.connect_ro(load(pdf_kb).index_path)
    try:
        row = connection.execute(
            "SELECT content_hash FROM documents WHERE path = 'docs/scanned-clean.pdf'"
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    bare = str(row["content_hash"]).removeprefix("sha256:")

    removed = [
        entry
        for entry in (pdf_kb / ".pinakes" / "cache" / "extract").glob(f"{bare}-*.json")
        if not entry.unlink()  # unlink() returns None, so this keeps every path it deleted
    ]
    assert len(removed) == 1, "exactly one document's entry must go, or this is the swept case"

    status, detail = checks(pdf_kb)["text yield"]
    assert "1 of 2 PDF document(s)" in detail
    assert "1 not in the extraction cache" in detail
    assert status is Status.OK, "the one document still measurable is healthy"


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_kb_whose_pdfs_are_all_paid_extracted_is_ok_rather_than_permanently_warned(
    pdf_kb: Path,
) -> None:
    """Skipped deliberately is not the same as lost.

    Reporting "0 of N could be measured" with a `pnk sync` remedy would be a warning nothing can
    clear — and on a KB whose PDFs are paid-extracted, a remedy that *spends*. The check has no
    question to ask about these documents, and saying so is the honest answer.
    """
    connection = store.connect_rw(pdf_kb / ".pinakes" / "index.db")
    try:
        connection.execute(
            "UPDATE documents SET extraction_backend = 'claude-vision' WHERE source_type = 'pdf'"
        )
        connection.commit()
    finally:
        connection.close()

    status, detail = checks(pdf_kb)["text yield"]
    assert status is Status.OK
    assert "all paid-extracted" in detail
    assert "could be measured" not in detail


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_an_unknown_extraction_backend_does_not_crash_the_health_check(pdf_kb: Path) -> None:
    """A future version's KB, or an extra since uninstalled. `is_paid_backend` raises on a name it
    does not know, and `pnk doctor` is precisely the command someone runs when a KB is in a state
    they do not understand — it may not be the thing that crashes.

    §4.4's coherence check already carries this guard for the same reason.
    """
    connection = store.connect_rw(pdf_kb / ".pinakes" / "index.db")
    try:
        connection.execute(
            "UPDATE documents SET extraction_backend = 'from-the-future' "
            "WHERE path = 'docs/scanned-clean.pdf'"
        )
        connection.commit()
    finally:
        connection.close()

    status, detail = checks(pdf_kb)["text yield"]  # must not raise
    assert status is Status.OK, "the one document still measurable is healthy"
    assert "1 extracted by an unknown backend" in detail


def test_every_doctor_check_is_exercised_by_a_test(kb: Path) -> None:
    """A check that ships with no test at all is the failure this catches.

    `pnk doctor` is a bag of independent checks, each appended to one list. Adding a check is one
    line, and nothing about that line requires a test to exist — so the coverage gap is invisible
    to review and invisible to a green suite. This asserts every check name `diagnose` can produce
    is named somewhere in this file.

    Named in `plans/20260727_1543-v0.2.md`'s verification table as `test_every_v02_check_appears`,
    assigned to
    I8, and not written there — found by I9's audit of that table, which is exactly what the audit
    is for.
    """
    sync(load(kb), options=SyncOptions(), now="20260729 05:30")
    produced = {check.name for check in diagnose(load(kb)).checks}

    # Checks that only appear on a KB this fixture is not: they have their own tests, which is what
    # this assertion is about, so each is listed with the test that covers it rather than skipped.
    conditional = {
        "text yield": "test_text_yield_flags_pages_not_documents",
        "awaiting paid extraction": (
            "test_awaiting_paid_extraction_lists_a_free_indexed_pdf_when_manifest_wants_paid"
        ),
        "paid extraction not requested": (
            "test_paid_extraction_not_requested_lists_a_paid_indexed_pdf_when_manifest_wants_free"
        ),
        "paid extraction stale": "test_paid_extraction_stale_lists_a_changed_file",
        "pdf extractor": (
            "test_pdf_extractor_check_warns_when_include_can_match_pdf_and_backend_is_missing"
        ),
    }
    source = Path(__file__).read_text(encoding="utf-8")
    for name, covering in conditional.items():
        assert f"def {covering}(" in source, f"{name}'s named test is gone: {covering}"

    unexercised = sorted(name for name in produced | set(conditional) if f'"{name}"' not in source)
    assert not unexercised, (
        f"these `pnk doctor` checks are not named by any test in this file: {unexercised}"
    )


# --- the checks the coverage test above found untested (I9's audit) -----------------------------


def test_the_template_check_reports_the_recorded_reference(kb: Path) -> None:
    status, detail = checks(kb)["template"]
    assert status is Status.OK
    assert detail.startswith("notes@"), "the KB records the template it was stamped from"


def test_a_template_the_install_does_not_have_is_a_warning_not_a_failure(kb: Path) -> None:
    """A KB stamped from someone else's template still works — nothing is applied automatically,
    so this may not be a failure."""
    path = kb / "pinakes.toml"
    body = path.read_text(encoding="utf-8")
    recorded = re.search(r'^template = "(.+)"$', body, re.MULTILINE)
    assert recorded is not None
    path.write_text(body.replace(recorded.group(1), "someone-elses@1.0.0"), encoding="utf-8")

    status, detail = checks(kb)["template"]
    assert status is Status.WARN
    assert "not installed here" in detail


def test_a_template_version_drift_is_reported_with_both_versions(kb: Path) -> None:
    """Both references still reach the reader — the recorded one in the detail, the installed one
    in the remedy that says what this build actually ships.

    Against `notes` the outcome is *cannot compare* rather than a line count, because `1.0` is
    deliberately unarchived (D-2b). That split is what
    `test_an_unarchived_recorded_version_says_it_cannot_compare_rather_than_ok` is about; this test
    is only about neither version going unnamed.
    """
    path = kb / "pinakes.toml"
    body = path.read_text(encoding="utf-8")
    recorded = re.search(r'^template = "notes@(.+)"$', body, re.MULTILINE)
    assert recorded is not None
    path.write_text(body.replace(f"notes@{recorded.group(1)}", "notes@0.0.1"), encoding="utf-8")

    check = template_check(kb)
    assert check.status is Status.WARN
    assert "notes@0.0.1" in check.detail
    assert f"notes@{recorded.group(1)}" in (check.remedy or "")


def test_the_reranker_check_says_when_reranking_is_off_rather_than_loading_one(kb: Path) -> None:
    """`rerank = "none"` is a supported configuration, not a missing model — loading a reranker to
    report on one nobody asked for would download weights during a health check."""
    path = kb / "pinakes.toml"
    body = path.read_text(encoding="utf-8")
    assert 'rerank                = "local"' in body
    path.write_text(
        body.replace('rerank                = "local"', 'rerank                = "none"'),
        encoding="utf-8",
    )

    status, detail = checks(kb)["reranker"]
    assert status is Status.OK
    assert detail == "disabled in the manifest"


def test_the_model_cache_check_names_the_directory_weights_resolve_under(kb: Path) -> None:
    """Where weights land is the question behind most "why is it downloading again" reports, so
    the check answers it rather than reporting a boolean."""
    from pinakes.embed import hf_cache_dir

    status, detail = checks(kb)["model cache"]
    assert status is Status.OK
    assert str(hf_cache_dir()) in detail


def test_the_extensions_check_explains_that_it_only_gates_an_unshipped_tier(kb: Path) -> None:
    """Loadable extensions are unavailable on some Python builds, and that is not a problem for
    anything shipped — so a WARN here must say what it does *not* affect, or it reads as a fault."""
    status, detail = checks(kb)["extensions"]
    assert status in (Status.OK, Status.WARN)
    if status is Status.WARN:
        remedy = next(c.remedy for c in diagnose(load(kb)).checks if c.name == "extensions")
        assert remedy is not None
        assert "NumPy tier is unaffected" in remedy
    else:
        assert "available" in detail


def test_a_kb_with_no_authored_links_nudges(kb: Path) -> None:
    """Link coverage is the ceiling on cross-KB answers (§6.2), so zero is a number worth printing
    rather than a check that stays quiet — and now a WARN, because a KB where nothing links to
    anything gives `pnk links` nothing to traverse.

    **KB-wide, never per-document.** L1's ≤ 35% density cap guarantees a per-document rule would
    fire on both committed corpora by construction, which is a check that cannot pass.
    """
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    status, detail = checks(kb)["links"]
    assert status is Status.WARN
    assert "none authored" in detail
    assert "0 of 1 documents linked (0%)" in detail
    assert "pnk link" in _remedy(kb, "links")


def _link_to(kb: Path, uri: str, *, rel: str = "cites") -> None:
    """Author one link by hand and re-sync, so the index has it."""
    sidecar = kb / "docs" / f"a.md{SIDECAR_SUFFIX}"
    body = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    body["links"] = [{"to": uri, "rel": rel}]
    sidecar.write_text(yaml.safe_dump(body), encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260729 05:32")


def _declare_partner(kb: Path, *, name: str, kb_id: str, path: str) -> None:
    manifest = kb / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + f'\n[[links.kb]]\nname = "{name}"\nid   = "{kb_id}"\npath = "{path}"\n',
        encoding="utf-8",
    )


def _partner(tmp_path: Path, name: str) -> Path:
    """A second real KB with one document, synced, so its index can answer."""
    result = init(tmp_path / name, now="20260725 17:30")
    text = (result.root / "pinakes.toml").read_text(encoding="utf-8")
    text = text.replace('provider = "sentence-transformers"', 'provider = "fake"')
    text = text.replace('model    = "BAAI/bge-small-en-v1.5"', 'model    = "fake-model"')
    text = text.replace("dim      = 384", f"dim      = {DIM}")
    text = text.replace('model    = "BAAI/bge-reranker-base"', 'model    = "fake-reranker"')
    (result.root / "pinakes.toml").write_text(text, encoding="utf-8")
    (result.root / "docs" / "p.md").write_text("# P\n\nText.\n", encoding="utf-8")
    sync(load(result.root), options=SyncOptions(), now="20260729 05:30")
    return result.root


def test_link_coverage_reports_the_ratio_not_the_edge_count(kb: Path) -> None:
    """DESIGN §6.2 promises *"linked docs / total docs"*, and the shipped check printed an edge
    count — `16 links, 4 cross-KB` — with a ratio only in the branch where it is zero.

    The two are different numbers: on `tests/demo-kb` those 16 edges come from 8 of 30 documents,
    so the 27% ceiling the §6.2 row is tabled against was never printed. Two links out of one
    document is the same shape in miniature: 1 of 1 linked, 2 links.
    """
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    kb_id = load(kb).kb.id
    (kb / "docs" / "b.md").write_text("# B\n\nMore.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260729 05:32")
    b_id = _document_ids(kb, "path LIKE '%b.md'")[0]
    sidecar = kb / "docs" / f"a.md{SIDECAR_SUFFIX}"
    body = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    body["links"] = [
        {"to": f"pnk://{kb_id}/{b_id}", "rel": "cites"},
        {"to": f"pnk://{kb_id}/{b_id}", "rel": "supersedes"},
    ]
    sidecar.write_text(yaml.safe_dump(body), encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260729 05:33")

    status, detail = checks(kb)["links"]
    assert status is Status.OK
    assert "1 of 2 documents linked (50%)" in detail
    assert "2 links" in detail  # ...and the edge count is still there, as a second number
    assert "as of the last sync" in detail  # it counts index rows, not sidecar files


def test_link_coverage_counts_authored_links_only(kb: Path) -> None:
    """`origin = 'sidecar'` — the filter shipped in v0.1 and is verified here, not rebuilt.

    Coverage means *links this KB's authors wrote*. Anything else — a reverse-scanned row, or a
    derived edge a later release adds — would report a ceiling nobody raised.

    **The row has to carry this KB's own `src_kb_id`**, or it never reaches the `origin` filter:
    the `src_kb_id = ?` clause excludes it first, and the test passes with the filter deleted. A
    reverse-scan row does carry a partner's id, which is exactly why one makes a *worse* fixture
    than it looks — it exercises the wrong clause. Measured: with a partner's id, dropping
    `origin = 'sidecar'` leaves every test green.
    """
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    kb_id = load(kb).kb.id
    local_doc = _document_ids(kb)[0]
    connection = store.connect_rw(kb / ".pinakes" / "index.db")
    try:
        connection.execute(
            "INSERT INTO links (src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel, origin) "
            "VALUES (?, ?, ?, ?, 'cites', 'reverse-scan')",
            (str(kb_id), local_doc, str(kb_id), str(mint_doc_id())),
        )
        connection.commit()
    finally:
        connection.close()

    status, detail = checks(kb)["links"]
    assert status is Status.WARN, "a reverse-scanned row was counted as authored coverage"
    assert "none authored (0 of 1 documents linked (0%))" in detail


def test_a_dangling_cross_kb_target_warns_with_a_reason(kb: Path, tmp_path: Path) -> None:
    """A cross-KB target whose own KB **is** here and does not have the document.

    This is the case that can be checked, so it is the only one that warns: the KB resolved, its
    index answered, and the document is not in it.
    """
    partner = _partner(tmp_path, "partner")
    partner_id = load(partner).kb.id
    _declare_partner(kb, name="partner", kb_id=str(partner_id), path="../partner")
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{partner_id}/{mint_doc_id()}")

    status, detail = checks(kb)["links"]
    assert status is Status.WARN
    assert "1 cross-KB unresolved" in detail
    assert "Re-sync that KB" in _remedy(kb, "links")


def test_a_cross_kb_target_that_its_own_kb_does_have_is_not_unresolved(
    kb: Path, tmp_path: Path
) -> None:
    """The other half of the same check — without this, `unresolved` counting *every* cross-KB
    target would pass the test above just as well."""
    partner = _partner(tmp_path, "partner")
    partner_id = load(partner).kb.id
    real = _document_ids(partner)[0]
    _declare_partner(kb, name="partner", kb_id=str(partner_id), path="../partner")
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{partner_id}/{real}")

    status, detail = checks(kb)["links"]
    assert status is Status.OK, detail
    assert "1 cross-KB" in detail
    assert "unresolved" not in detail


def test_a_deleted_document_leaves_the_coverage_ratio_honest(kb: Path) -> None:
    """A soft delete keeps the links. `sync`'s `SoftDelete` sets `state = 'deleted'` and drops the
    chunks; it never deletes that document's `origin = 'sidecar'` rows.

    So an unjoined numerator counted a population the denominator did not: two documents linking to
    each other, delete one, and the check reported **`2 of 1 documents linked (200%)`** — the
    headline metric of this increment, above 100%.
    """
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    kb_id = load(kb).kb.id
    (kb / "docs" / "b.md").write_text("# B\n\nMore.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260729 05:32")
    a_id, b_id = (
        _document_ids(kb, "path LIKE '%a.md'")[0],
        _document_ids(kb, "path LIKE '%b.md'")[0],
    )
    for name, target in (("a", b_id), ("b", a_id)):
        sidecar = kb / "docs" / f"{name}.md{SIDECAR_SUFFIX}"
        body = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        body["links"] = [{"to": f"pnk://{kb_id}/{target}", "rel": "cites"}]
        sidecar.write_text(yaml.safe_dump(body), encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260729 05:33")
    assert "2 of 2 documents linked (100%)" in checks(kb)["links"][1]

    (kb / "docs" / "b.md").unlink()
    (kb / "docs" / f"b.md{SIDECAR_SUFFIX}").unlink()
    sync(load(kb), options=SyncOptions(), now="20260729 05:34")

    status, detail = checks(kb)["links"]
    assert "1 of 1 documents linked (100%)" in detail, detail
    assert "200%" not in detail
    assert "2 links" not in detail, "a deleted document's links were still counted"
    # The *other* side of the same interaction: `a` still points at the deleted `b`, and a target
    # that is soft-deleted is dangling. `known` filters on `state = 'active'` for this reason.
    assert status is Status.WARN
    assert "1 dangling inside this KB" in detail
    assert "no longer exists here" in _remedy(kb, "links")


def test_a_cross_kb_target_is_resolved_against_the_partners_own_id(
    kb: Path, tmp_path: Path
) -> None:
    """The declared `[[links.kb]] id` is not evidence of which KB sits at that path.

    `linkscan.scan_one` refuses a mismatch with `LinkedKbIdMismatchError` because trusting the
    manifest files another KB's links under this alias. Keying on `linked.id` did exactly that:
    with a manifest declaring `X` over a partner whose real id is `Y`, a `pnk://X/...` target was
    resolved against `Y`'s documents — silently OK for one that did not exist there, and WARN for
    one that did.

    Nothing at `X` is on this machine, so the honest answer is to say nothing about it.
    """
    partner = _partner(tmp_path, "partner")
    declared = mint_kb_id()  # not the partner's own id
    assert str(declared) != str(load(partner).kb.id)
    _declare_partner(kb, name="partner", kb_id=str(declared), path="../partner")
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{declared}/{mint_doc_id()}")

    status, detail = checks(kb)["links"]
    assert status is Status.OK, detail
    assert "unresolved" not in detail


def test_a_partner_is_found_by_its_own_id_even_when_the_manifest_declares_another(
    kb: Path, tmp_path: Path
) -> None:
    """The other direction of the same rule, and the one that *misses* rather than misattributes.

    Filtering the walk on the **declared** `[[links.kb]] id` skips a partner whose real id is the
    one actually wanted — so a genuinely dangling target goes unreported. Here the manifest declares
    `X` over a partner whose own id is `Y`, and the link targets `Y`: the partner is on this
    machine, its sidecars answer, and the target is not among them.
    """
    partner = _partner(tmp_path, "partner")
    partner_id = load(partner).kb.id
    _declare_partner(kb, name="partner", kb_id=str(mint_kb_id()), path="../partner")
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{partner_id}/{mint_doc_id()}")

    status, detail = checks(kb)["links"]
    assert status is Status.WARN, detail
    assert "1 cross-KB unresolved" in detail


def test_a_partner_whose_sources_are_unusable_is_not_used_as_evidence(
    kb: Path, tmp_path: Path
) -> None:
    """`sidecars_under` reports a problem rather than raising when a partner's `[sources]` cannot
    be walked — an `include` reaching outside its KB, for instance. The walk that produced it is
    not exhaustive, so its document set is a subset of the truth and cannot show a target absent.
    """
    partner = _partner(tmp_path, "partner")
    partner_id = load(partner).kb.id
    manifest = partner / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md", "**/*.txt"]', 'include = ["**/*.md", "../../outside/*.md"]'
        ),
        encoding="utf-8",
    )
    _declare_partner(kb, name="partner", kb_id=str(partner_id), path="../partner")
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{partner_id}/{mint_doc_id()}")

    status, detail = checks(kb)["links"]
    assert status is Status.OK, detail
    assert "unresolved" not in detail


def test_a_partner_roots_entry_that_cannot_be_resolved_is_not_a_traceback(
    kb: Path, tmp_path: Path
) -> None:
    """The second guard in `_unresolved_cross_kb`, around `sidecars_under`.

    `tomllib` accepts a `\\u0000` escape and `Path.resolve()` does not, so a partner `roots` entry
    carrying one raises `ValueError` out of the walk. Partner-controlled input reaching a
    diagnostic command must not become a traceback.
    """
    partner = _partner(tmp_path, "partner")
    partner_id = load(partner).kb.id
    manifest = partner / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'roots   = ["docs/"]', 'roots   = ["docs/", "\\u0000bad"]'
        ),
        encoding="utf-8",
    )
    _declare_partner(kb, name="partner", kb_id=str(partner_id), path="../partner")
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{partner_id}/{mint_doc_id()}")

    status, detail = checks(kb)["links"]
    assert status is Status.OK, detail
    assert "unresolved" not in detail


def test_an_unreadable_linked_kb_path_is_a_warning_not_a_traceback(
    kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`why_not_a_kb` raises `OSError` on an unreadable parent, and its docstring names this command
    as the third caller needing the same `try` that `linkscan.scan_one` and `link._via_alias` have.

    A diagnostic command reporting a traceback is the one outcome `pnk doctor` may not have.
    """
    locked = tmp_path / "locked"
    (locked / "kb").mkdir(parents=True)
    walled_id = mint_kb_id()
    _declare_partner(kb, name="walled", kb_id=str(walled_id), path=str(locked / "kb"))
    # **A cross-KB link, so `_unresolved_cross_kb` actually runs.** Without one, `wanted` is empty
    # and it returns before touching the partner — so this test, named for "the third caller
    # needing the same `try`", reached only `_linked_kbs`'s guard and neither of the two in the
    # function the review added. Same class as the fixtures L6 kept shipping.
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{walled_id}/{mint_doc_id()}")

    # **Injected, not chmod'd.** `chmod(0o000)` is not a portable way to deny a read: root ignores
    # it, and CI's runner produced a stat that neither succeeded nor raised, so two runs of `main`
    # went red on fixtures that could not build their own precondition. What is under test is that
    # an `OSError` from the probe becomes a WARN rather than a traceback — so raise one.
    real_is_file = Path.is_file

    def denied(self: Path) -> bool:
        if self.is_relative_to(locked):
            raise PermissionError(13, "Permission denied")
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", denied)
    report = {c.name: (c.status, c.detail) for c in diagnose(load(kb)).checks}
    monkeypatch.undo()

    status, detail = report["linked KBs"]
    assert status is Status.WARN
    assert "walled" in detail
    assert report["links"][0] is Status.OK, "an unreadable partner was used as evidence of absence"


def test_a_partner_whose_sidecars_cannot_all_be_read_is_not_used_as_evidence(
    kb: Path, tmp_path: Path
) -> None:
    """An incomplete walk proves nothing — the rule `ScannedKb.complete` encodes for the delete.

    If one of the partner's sidecars is unreadable, its document set is a subset of the truth, and
    reporting a target "missing" on that basis reports absence of evidence as evidence of absence.
    """
    partner = _partner(tmp_path, "partner")
    partner_id = load(partner).kb.id
    real = _document_ids(partner)[0]
    (partner / "docs" / "broken.md").write_text("# broken\n", encoding="utf-8")
    (partner / "docs" / f"broken.md{SIDECAR_SUFFIX}").write_text(
        "id: not-a-ulid\n", encoding="utf-8"
    )
    _declare_partner(kb, name="partner", kb_id=str(partner_id), path="../partner")
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{partner_id}/{mint_doc_id()}")

    status, detail = checks(kb)["links"]
    assert status is Status.OK, detail
    assert "unresolved" not in detail
    assert real  # the readable sidecar exists; the point is that a partial set is not used


def test_doctor_writes_nothing_into_a_partner_kb(kb: Path, tmp_path: Path) -> None:
    """DESIGN §6.2: a partner's index is *"not"* what cross-KB questions are answered from, *"and
    which could not be read without holding a second KB's lock"*.

    Reading it with `mode=ro` is not enough — measured, SQLite materialises `index.db-shm` and
    `index.db-wal` inside the partner's `.pinakes/` and a read-only connection cannot checkpoint
    them away on close. A diagnostic command must not write into a KB it was asked to look at.
    """
    partner = _partner(tmp_path, "partner")
    partner_id = load(partner).kb.id
    _declare_partner(kb, name="partner", kb_id=str(partner_id), path="../partner")
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{partner_id}/{mint_doc_id()}")
    before = sorted(p.name for p in (partner / ".pinakes").iterdir())

    assert checks(kb)["links"][0] is Status.WARN  # the check really ran and found the target absent

    assert sorted(p.name for p in (partner / ".pinakes").iterdir()) == before


def test_a_partner_without_an_index_still_answers(kb: Path, tmp_path: Path) -> None:
    """Committed sidecars, not the index — so a freshly cloned partner with no `.pinakes/` at all
    answers exactly as well. That is the case §6.2 gives as the reason for the rule."""
    partner = _partner(tmp_path, "partner")
    partner_id = load(partner).kb.id
    real = _document_ids(partner)[0]
    _declare_partner(kb, name="partner", kb_id=str(partner_id), path="../partner")
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    shutil.rmtree(partner / ".pinakes")

    _link_to(kb, f"pnk://{partner_id}/{mint_doc_id()}")
    assert "1 cross-KB unresolved" in checks(kb)["links"][1]

    _link_to(kb, f"pnk://{partner_id}/{real}")
    detail = checks(kb)["links"][1]
    assert "unresolved" not in detail, detail


def test_an_internal_link_is_not_counted_as_cross_kb(kb: Path) -> None:
    """`0 cross-KB` is the assertion that stops the count meaning "every authored link"."""
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    _link_to(kb, f"pnk://{load(kb).kb.id}/{mint_doc_id()}")

    assert "0 cross-KB" in checks(kb)["links"][1]


def test_a_tilde_linked_kb_path_is_warned_as_absolute(kb: Path) -> None:
    """`Path("~/kb").is_absolute()` is `False`, but `linkscan._resolve` expands first and *then*
    takes the absolute branch — so a `~` path is never resolved relative to the KB root, which is
    the property this warning defends. Checking the unexpanded string let every `~` path through."""
    _declare_partner(kb, name="home", kb_id=str(mint_kb_id()), path="~/definitely-not-here-xyz")

    status, detail = checks(kb)["linked KBs"]
    assert status is Status.WARN
    assert "absolute: home" in detail


def test_a_linked_kb_absent_from_this_machine_warns(kb: Path) -> None:
    """A fact about this machine, not about the KB — so a WARN, never a FAIL: `cli.py`'s `doctor`
    exits non-zero only on `Status.FAIL`, and a partner you have not cloned is not a broken KB."""
    _declare_partner(kb, name="ghost", kb_id=str(mint_kb_id()), path="../not-cloned")

    status, detail = checks(kb)["linked KBs"]
    assert status is Status.WARN
    assert "ghost (no such directory)" in detail
    assert "Clone it" in _remedy(kb, "linked KBs")


def test_a_linked_kb_path_that_resolves_to_nothing_warns_with_the_reason(kb: Path) -> None:
    """`resolve_path` answers `None` for text that names no path at all, and `why_unresolvable`
    gives the reason — the fault, not the category."""
    _declare_partner(kb, name="broken", kb_id=str(mint_kb_id()), path="~nosuchuser12345/kb")

    status, detail = checks(kb)["linked KBs"]
    assert status is Status.WARN
    assert "broken (the `~` cannot be expanded" in detail
    assert str(kb) not in detail  # names what the author wrote, never the local KB root
    assert "names no path at all" in _remedy(kb, "linked KBs")
    # ...and not *also* reported absolute: `expanduser()` raises for an unknown user, and a path
    # that names nothing is unresolvable rather than escaping. A documented decision needs a test.
    assert "absolute" not in detail


def test_an_absolute_linked_kb_path_warns(kb: Path, tmp_path: Path) -> None:
    """Reported **whether or not it resolves**: a committed absolute path publishes one machine's
    filesystem layout to everyone who clones the KB, and stops working the moment anyone checks it
    out elsewhere. Here it resolves and the KB is really there, so nothing else fires."""
    partner = _partner(tmp_path, "partner")
    _declare_partner(kb, name="abs", kb_id=str(load(partner).kb.id), path=str(partner))

    status, detail = checks(kb)["linked KBs"]
    assert status is Status.WARN
    assert "absolute: abs" in detail
    assert "not here" not in detail
    assert "publishes this machine's" in _remedy(kb, "linked KBs")


def test_a_kb_declaring_no_linked_kbs_still_produces_the_check(kb: Path) -> None:
    """**One `Check`, always.** `test_every_doctor_check_is_exercised_by_a_test` builds its set
    from `diagnose()` on a fixture that declares no `[[links.kb]]`, so a check that disappears
    there is one the coverage guard cannot see. Returning it unconditionally exposes this check to
    that guard instead of exempting it via the `conditional` map."""
    status, detail = checks(kb)["linked KBs"]
    assert status is Status.OK
    assert detail == "none declared"


def test_the_linked_kbs_check_runs_without_an_index(kb: Path) -> None:
    """It lives outside `_index`, which returns at its first branch when `.pinakes/` is absent —
    and a freshly cloned KB with no index is exactly when a committed absolute path matters."""
    assert not (kb / ".pinakes" / "index.db").exists()
    _declare_partner(kb, name="ghost", kb_id=str(mint_kb_id()), path="../not-cloned")

    assert checks(kb)["linked KBs"][0] is Status.WARN


def test_a_dangling_link_inside_this_kb_is_a_warning_naming_how_many(kb: Path) -> None:
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    kb_id = load(kb).kb.id
    sidecar = kb / "docs" / f"a.md{SIDECAR_SUFFIX}"
    body = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    body["links"] = [{"to": f"pnk://{kb_id}/{mint_doc_id()}", "rel": "cites"}]
    sidecar.write_text(yaml.safe_dump(body), encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260729 05:32")

    status, detail = checks(kb)["links"]
    assert status is Status.WARN
    assert "1 dangling inside this KB" in detail


def test_a_cross_kb_link_into_a_kb_not_here_is_counted_but_not_called_unresolved(
    kb: Path,
) -> None:
    """A target in a KB this machine does not have is **not** evidence of anything.

    `graph/provider.py` refuses to call one `unresolved` for exactly this reason, and doctor may
    not assert what the index has no standing to know either. It is counted as cross-KB and left
    at OK; the absent KB itself is `_linked_kbs`'s business, as a fact about this machine.
    """
    sync(load(kb), options=SyncOptions(), now="20260729 05:31")
    sidecar = kb / "docs" / f"a.md{SIDECAR_SUFFIX}"
    body = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    body["links"] = [{"to": f"pnk://{mint_kb_id()}/{mint_doc_id()}", "rel": "cites"}]
    sidecar.write_text(yaml.safe_dump(body), encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260729 05:32")

    status, detail = checks(kb)["links"]
    assert status is Status.OK
    assert "1 cross-KB" in detail
    assert "unresolved" not in detail


# --- edge-hub reporting (G6) -------------------------------------------------------------------


def _write_tagged_doc(kb: Path, path: str, *, tags: Sequence[str] = ()) -> None:
    """A document with an explicit `tags` sidecar, for building `shared-tag` hub fixtures."""
    target = kb / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"# {Path(path).stem}\n\nSome text.\n", encoding="utf-8")
    sidecar: dict[str, object] = {"id": str(mint_doc_id()), "title": Path(path).stem}
    if tags:
        sidecar["tags"] = list(tags)
    (kb / f"{path}{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8"
    )


def test_a_kb_with_no_edges_reports_none(kb: Path) -> None:
    """The default fixture's one document shares no tag, heading or directory with anything, so
    G3 derives zero hub edges. The check must say so cleanly — not crash, and not print an empty
    table with only a header, which would read as a report that forgot to finish."""
    sync(load(kb), options=SyncOptions(), now="20260805 05:00")

    status, detail = checks(kb)["edge hubs"]
    assert status is Status.OK
    assert detail == "none"


def test_edge_hubs_are_reported_highest_degree_first(kb: Path) -> None:
    """A fixture where mint order and degree order disagree, so a missing or reversed sort passes
    on the "natural" order and is caught here — the failure class this project keeps finding: an
    assertion satisfied by something other than the property it names.

    `derive()` mints a tag hub the first time its tag is seen, scanning documents **by path**.
    `low` is first seen on `docs/aa1/x.md`, `high` on `docs/aa2/y.md` — `aa1` sorts before `aa2` —
    so `low` mints a lower node id than `high`. `low` ends at degree 2 (`x`, `y`), `high` at degree
    4 (`y`, `z`, `w`, `v`): printing in insertion order would put `low` first, exactly the
    unsorted-output bug this pins against.

    Each new document lives in its own directory, so no `co-located` hub reaches degree ≥ 2 and
    neither can the fixture's existing `docs/a.md`, left as the sole, untagged member of `docs/` —
    both would otherwise compete with the two tag hubs for the top of the list.
    """
    _write_tagged_doc(kb, "docs/aa1/x.md", tags=["low"])
    _write_tagged_doc(kb, "docs/aa2/y.md", tags=["low", "high"])
    _write_tagged_doc(kb, "docs/zz1/z.md", tags=["high"])
    _write_tagged_doc(kb, "docs/zz2/w.md", tags=["high"])
    _write_tagged_doc(kb, "docs/zz3/v.md", tags=["high"])
    sync(load(kb), options=SyncOptions(), now="20260805 05:01")

    status, detail = checks(kb)["edge hubs"]
    assert status is Status.OK
    assert "2 hub(s)" in detail
    high_at = detail.index('tag "high"')
    low_at = detail.index('tag "low"')
    assert high_at < low_at, f"the degree-4 hub must print before the degree-2 hub: {detail!r}"
    assert "degree 4" in detail
    assert "degree 2" in detail


def test_an_edge_hub_report_names_a_document_path_never_a_bare_node_id(kb: Path) -> None:
    """A `heading` node's key is `<doc-ulid>:<heading_path>` (G3) — the one node kind whose key is
    not already the human-facing value. Pasted raw into an issue it identifies nothing; this
    asserts the check resolves it against `documents.path` instead, and never leaks the ULID.
    """
    (kb / "docs" / "a.md").write_text(
        "# A\n\n## Same\n\nOne.\n\n## Same\n\nTwo.\n", encoding="utf-8"
    )
    sync(load(kb), options=SyncOptions(), now="20260805 05:02")
    doc_id = _document_ids(kb)[0]

    status, detail = checks(kb)["edge hubs"]
    assert status is Status.OK
    assert "heading" in detail
    assert "a.md" in detail
    assert doc_id not in detail, f"a raw document ULID leaked into the report: {detail!r}"


def test_a_directory_hub_is_named_by_its_kb_root_relative_path(kb: Path) -> None:
    """The one hub kind the first review round left untested: `co-located` mints a `dir` node
    whose key already *is* the KB-root-relative directory (`derive()`'s `directory_of`), so
    `_hub_label` prints it verbatim rather than resolving anything — unlike `heading`, it needs no
    lookup, and this is the test that would catch a label reverting to a bare `nodes.id` here too.
    """
    for name in ("one.md", "two.md"):
        (kb / "docs" / "pair" / name).parent.mkdir(parents=True, exist_ok=True)
        (kb / "docs" / "pair" / name).write_text(f"# {name}\n\nText.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260805 05:03")

    status, detail = checks(kb)["edge hubs"]
    assert status is Status.OK
    assert 'directory "docs/pair"' in detail
    assert "degree 2" in detail


def test_a_degree_tie_breaks_deterministically_and_the_rest_are_counted(kb: Path) -> None:
    """Four tags, each on exactly two documents — every hub tied at degree 2 — so nothing but an
    explicit tiebreak decides print order, and the review that found this gap showed the *implicit*
    order (whatever `SELECT DISTINCT src` happens to return) is mint order: `d` first, `a` last,
    because each document's path sorts in that order and mints its tag the first time it is seen
    (`derive()`'s `_active_documents` scans by path). The tiebreak sorts on `(kind, key)`, so the
    printed order is alphabetical — `a`, `b`, `c` — the reverse of mint order, and a tiebreak that
    quietly fell back to insertion order would print `d`, `c`, `b` here instead.

    `EDGE_HUB_SAMPLE = 3` also gets its only exercise here: four equally-tied hubs is the smallest
    fixture that forces the "and N more" branch.
    """
    for tag, prefix in (("d", "n1"), ("c", "n2"), ("b", "n3"), ("a", "n4")):
        _write_tagged_doc(kb, f"docs/{prefix}a/x.md", tags=[tag])
        _write_tagged_doc(kb, f"docs/{prefix}b/y.md", tags=[tag])
    sync(load(kb), options=SyncOptions(), now="20260805 05:04")

    status, detail = checks(kb)["edge hubs"]
    assert status is Status.OK
    assert "4 hub(s)" in detail
    assert "and 1 more" in detail
    shown = detail.partition(": ")[2].split(", and")[0]
    assert shown.startswith('tag "a" (degree 2), tag "b" (degree 2), tag "c" (degree 2)'), (
        f"a degree tie must break on (kind, key), not on arrival order: {detail!r}"
    )
    assert 'tag "d"' not in detail, f"the fourth tied hub must be counted, not printed: {detail!r}"


def test_a_cross_kind_tie_breaks_on_kind_before_key(kb: Path) -> None:
    """The `kind` half of the tiebreak, which the same-kind fixture above cannot reach.

    `nodes` is `UNIQUE (kind, key)` — **the pair, not the key** — so `key` alone is not a total
    order over hubs and the `kind` term is doing real work whenever two kinds tie on degree.

    **The fixture makes key order oppose kind order, deliberately.** Two documents in
    `docs/shared/` carry the tag `aaa`, so a `dir` hub keyed `docs/shared` and a `tag` hub keyed
    `aaa` both reach degree 2. Correct code sorts `(-degree, kind, key)` and prints the directory
    first, because `"dir" < "tag"`. Drop the `kind` term and `"aaa" < "docs/shared"` puts the tag
    first instead.

    A first version of this test gave both hubs the *same* key, and a mutant with `kind` removed
    **passed it** — Python's sort is stable, and the hubs already arrived directory-first, so the
    assertion was satisfied by mint order rather than by the property it names. Opposing the two
    orders is what makes the mutation observable.
    """
    for name in ("one", "two"):
        _write_tagged_doc(kb, f"docs/shared/{name}.md", tags=["aaa"])
    sync(load(kb), options=SyncOptions(), now="20260805 05:04")

    status, detail = checks(kb)["edge hubs"]
    assert status is Status.OK
    shown = detail.partition(": ")[2]
    assert shown.startswith('directory "docs/shared" (degree 2), tag "aaa" (degree 2)'), (
        f"a cross-kind tie must break on kind before key: {detail!r}"
    )


def test_heading_coverage_is_full_on_an_all_markdown_kb(kb: Path) -> None:
    """The fixture's one document is `# A` plus a paragraph, so its single chunk carries a heading
    path. Measured the same way on the committed corpora before this check was written: demo-kb
    60/60 and partner-kb 55/55, which is the 100% end of the bimodal distribution the predicate
    relies on."""
    sync(load(kb), options=SyncOptions(), now="20260805 07:50")

    status, detail = checks(kb)["heading coverage"]
    assert status is Status.OK
    assert detail == "1 of 1 chunks carry a heading path (100%)"


def test_a_plain_text_source_type_is_reported_at_zero(kb: Path) -> None:
    """The RFC case, in miniature — and the reason this check exists.

    `chunk.py` routes `text` to `_plain_blocks` — which sets `heading_path=None` unconditionally —
    **unless `[chunking] headings = "numbered"` is set**, which this fixture does not set. So the
    absence here is the *grammar not being offered*, not a `.txt` file being unable to carry a
    heading path: that stopped being true in 0.13.0, and the assertions below turn on the
    difference, since the note has to point at the unset key rather than declare a limit of the
    tool. This document is written with a heading that looks exactly like an RFC's, so the
    distinction is load-bearing: the same bytes under `headings = "numbered"` do carry one.

    **Two chunks, not one**, and the count is the point: `_plain_blocks` splits on blank lines, so
    the `1.  Introduction` line becomes a chunk *of its own* with no heading path and no body —
    exactly the shape that made 106 806 RFC chunks look like prose with no structure in it.
    """
    (kb / "docs" / "rfc.txt").write_text(
        "1.  Introduction\n\nThis document specifies a thing.\n", encoding="utf-8"
    )
    sync(load(kb), options=SyncOptions(), now="20260805 07:51")

    status, detail = checks(kb)["heading coverage"]
    assert status is Status.OK, "only `markdown` at 0% warns — decided by the user 20260805"
    assert "text (2)" in detail
    assert "`in-section`, `parent` and `child` derive nothing" in detail
    # `[chunking] headings` is unset on this fixture, so the note must point at it rather than
    # claiming plain text cannot carry a heading path — which stopped being true in 0.13.0.
    assert "`[chunking] headings" in detail
    assert "currently unset" in detail


def test_a_markdown_kb_with_no_headings_gets_the_other_remedy(kb: Path) -> None:
    """A markdown document *can* carry a heading path and does not, which is a fact about the
    document rather than a limit of the chunker — so the remedy must say something different from
    the plain-text one. A single remedy for both would send someone to change `[chunking]
    strategy` when what they have is a file with no `#` in it."""
    (kb / "docs" / "a.md").write_text("Just a paragraph, no heading.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260805 07:52")

    status, _ = checks(kb)["heading coverage"]
    assert status is Status.WARN, "the one fixable case, and the only one that warns"
    remedy = _remedy(kb, "heading coverage")
    assert "ATX headings" in remedy
    assert "chunked by size alone" in remedy


def test_a_partial_share_within_a_source_type_is_not_a_warning(kb: Path) -> None:
    """**The predicate is zero per source type, never "any chunk missing one".**

    Text before a document's first heading legitimately has no heading path, so an "any missing"
    rule would warn on an ordinary corpus and this check would be noise inside a week. This fixture
    has both in one source type: one chunk with a heading path and one without.

    The paragraph before the heading is padded past `max_tokens` so it cannot be folded into the
    same block as the heading that follows it — without that the document yields a single chunk and
    the test passes for the wrong reason, asserting nothing about partial coverage at all.
    """
    body = " ".join(["filler"] * 600)
    (kb / "docs" / "a.md").write_text(f"{body}\n\n# Heading\n\nUnder it.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260805 07:53")

    status, detail = checks(kb)["heading coverage"]
    named, total = _heading_counts(kb)
    assert 0 < named < total, f"fixture must be partial, got {named}/{total}"
    assert status is Status.OK, detail


def test_a_removed_documents_chunks_stop_being_counted(kb: Path) -> None:
    """Deleting the only plain-text document must take the check back to OK.

    **This test does *not* exercise the `state = 'active'` filter, and is deliberately not named
    as though it does.** It was written as `..._counts_only_active_documents` and mutation testing
    refuted that immediately: deleting the filter left it green. The reason is that `SoftDelete`
    drops a document's chunks as well as flipping its state, so the join has nothing to over-count
    either way — the filter is defensive consistency with `_links`, not a guard this fixture can
    reach. `_links` needs its own filter because it counts *documents*; this counts *chunks*, and
    the chunks are already gone.

    Kept because the property it does prove is worth pinning: the check reflects the current index
    rather than every document that has ever been in it."""
    (kb / "docs" / "rfc.txt").write_text("1.  Introduction\n\nBody.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260805 07:54")
    # The signal is the *note*, not the status: since 20260805 a non-markdown type at 0% is
    # reported as OK rather than WARN, so status alone can no longer distinguish before from after.
    assert "text" in checks(kb)["heading coverage"][1]

    (kb / "docs" / "rfc.txt").unlink()
    (kb / f"docs/rfc.txt{SIDECAR_SUFFIX}").unlink()
    sync(load(kb), options=SyncOptions(), now="20260805 07:55")

    status, detail = checks(kb)["heading coverage"]
    assert status is Status.OK, detail
    assert "1 of 1 chunks" in detail


def _heading_counts(root: Path) -> tuple[int, int]:
    connection = store.connect_ro(root / ".pinakes" / "index.db")
    try:
        row = connection.execute(
            "SELECT count(c.heading_path) AS named, count(*) AS total FROM chunks c "
            "JOIN documents d ON d.id = c.doc_id WHERE d.state = 'active'"
        ).fetchone()
        return int(row["named"]), int(row["total"])
    finally:
        connection.close()


def test_chunking_coherence_is_ok_on_a_freshly_synced_kb(kb: Path) -> None:
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    status, detail = checks(kb)["chunking coherence"]
    assert status is Status.OK
    assert "matches" in detail


def test_chunking_coherence_warns_after_a_manifest_only_edit(kb: Path) -> None:
    """The other half of the fix. `pnk sync` catches the user who just made the edit; this catches
    the one who made it last week and is now asking why `heading_path` is empty."""
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    manifest = kb / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "[chunking]\n", '[chunking]\nheadings = "numbered"\n', 1
        ),
        encoding="utf-8",
    )
    status, detail = checks(kb)["chunking coherence"]
    assert status is Status.WARN
    assert "none -> numbered" in detail
    assert "--rebuild" in _remedy(kb, "chunking coherence")


def test_chunking_coherence_warns_when_metadata_injection_was_turned_on(kb: Path) -> None:
    """`doctor` is the command a user runs to ask exactly this question, and it was the untested
    half: `manifest.py`'s own docstring promises the flip is reported by `pnk sync` **and**
    `pnk doctor`, but only the sync side had a test — a `doctor` that read a constant here would
    report a healthy KB while every search ran against uninjected vectors.

    It is also the key with the least visible effect: flipping it changes no chunk's text, hash or
    span, so an incremental sync finds nothing changed and re-embeds nothing.
    """
    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    manifest = kb / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "[chunking]\n", '[chunking]\nmetadata = "prefix"\n', 1
        ),
        encoding="utf-8",
    )
    status, detail = checks(kb)["chunking coherence"]
    assert status is Status.WARN
    assert "chunking_metadata off -> prefix" in detail
    assert "--rebuild" in _remedy(kb, "chunking coherence")


def test_chunking_coherence_stays_ok_when_the_index_recorded_no_identity(kb: Path) -> None:
    """Every KB indexed before this existed. **WARN here would fire on all of them at once**, which
    is the unclearable-warning failure the heading-coverage check already has to answer for — and
    it would demand a full rebuild of every KB for a setting that probably never changed."""
    import sqlite3

    sync(load(kb), options=SyncOptions(), now="20260725 17:31")
    connection = sqlite3.connect(kb / ".pinakes" / "index.db")
    connection.execute("DELETE FROM meta WHERE key LIKE 'chunking_%'")
    connection.commit()
    connection.close()

    manifest = kb / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "[chunking]\n", '[chunking]\nheadings = "numbered"\n', 1
        ),
        encoding="utf-8",
    )
    assert checks(kb)["chunking coherence"][0] is Status.OK


def test_a_code_file_never_warns_because_nothing_can_clear_it(kb: Path) -> None:
    """The defect this change fixes: a KB holding one `.py` file warned on **every run, forever**,
    with a remedy that amounted to "this is a limit of the tool". An un-actionable warning that
    cannot be cleared is how doctor output stops being read at all — which costs the actionable
    warnings too, so it is a larger loss than the one signal it gives up."""
    manifest = kb / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md", "**/*.txt"]', 'include = ["**/*.md", "**/*.txt", "**/*.py"]', 1
        ),
        encoding="utf-8",
    )
    (kb / "docs" / "thing.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (kb / "docs" / "titled.md").write_text("# Title\n\nBody.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260805 21:20")

    status, detail = checks(kb)["heading coverage"]
    assert "code" in detail, "precondition: the .py file must actually be indexed"
    assert status is Status.OK
    assert "code" in detail
    assert "cannot carry one today" in detail


def test_text_at_zero_with_the_grammar_on_says_the_documents_were_refused(kb: Path) -> None:
    """Two different facts wear the same 0%, and the note must tell them apart. With
    `[chunking] headings` unset, the user has an action. With it set, the grammar was *offered*
    these documents and declined them — their numbering does not form an outline it will trust —
    and telling someone to set a key they already set is worse than saying nothing."""
    manifest = kb / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "[chunking]\n", '[chunking]\nheadings = "numbered"\n', 1
        ),
        encoding="utf-8",
    )
    # Numbered like a list that restarts, so the outline walk refuses it — the safe fallback.
    (kb / "docs" / "notes.txt").write_text(
        "Steps:\n\n1. Do this.\n\n2. Do that.\n\n1. Start over.\n", encoding="utf-8"
    )
    sync(load(kb), options=SyncOptions(), now="20260805 21:21")

    status, detail = checks(kb)["heading coverage"]
    assert status is Status.OK
    assert "refused" in detail
    assert "currently unset" not in detail


def test_minted_titles_are_reported_but_never_warned(kb: Path) -> None:
    """**The decision, and it is deliberate**: a filename-derived title is a legitimate state — the
    fallback was kept on purpose — so warning would fire on every KB whose titles nobody has
    curated, which is most of them and *both committed corpora at 100%*. That is the unclearable
    warning the heading-coverage check already had to answer for, and repeating it one check later
    would cost the warnings that do mean something."""
    # No `# ` heading: since 20260805 a Markdown H1 titles the document, so a file with one is
    # *authored*, not minted — which is exactly what this check must not count.
    (kb / "docs" / "access-restrictions.md").write_text("Body, no heading.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260805 22:15")

    status, detail = checks(kb)["titles"]
    assert status is Status.OK, "a minted title is reported, never warned"
    assert "access-restrictions.md" in detail
    assert "carry the title minted from their filename" in detail


def test_an_authored_title_is_not_counted_as_minted(kb: Path) -> None:
    """Otherwise the check reports a number nobody can act on and everybody learns to ignore."""
    # No `# ` heading: since 20260805 a Markdown H1 titles the document, so a file with one is
    # *authored*, not minted — which is exactly what this check must not count.
    (kb / "docs" / "access-restrictions.md").write_text("Body, no heading.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260805 22:16")

    counted_before = checks(kb)["titles"][1]
    sidecar = kb / "docs" / f"access-restrictions.md{SIDECAR_SUFFIX}"
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace(
            "title: access restrictions", "title: Who may see what"
        ),
        encoding="utf-8",
    )
    sync(load(kb), options=SyncOptions(), now="20260805 22:17")

    after = checks(kb)["titles"][1]
    assert "access-restrictions.md" in counted_before, "precondition: it started out minted"
    assert "access-restrictions.md" not in after, (
        "an authored title must stop being counted; the fixture's own documents still are"
    )
    assert checks(kb)["titles"][0] is Status.OK


def test_the_check_recomputes_minting_the_way_sync_does_it(kb: Path) -> None:
    """`minted_title` is shared by the minter and this check precisely so they cannot disagree.
    Underscores *and* hyphens both become spaces, and a check carrying its own copy of that rule
    would go quietly wrong — in the direction of reporting nothing — the day either copy changed."""
    (kb / "docs" / "annual_report-2026.md").write_text("Body, no heading.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260805 22:18")

    assert minted_title(Path("docs/annual_report-2026.md")) == "annual report 2026"
    assert "annual_report-2026.md" in checks(kb)["titles"][1]


# --- T2: template drift reported as a diff, not a version string --------------------------------
#
# **Every positive path here needs a synthetic two-version template, never `notes`.** D-2b leaves
# the shipped template with exactly one archived version, so the only outcome reachable against
# `notes` is *cannot compare*. One test below runs against `notes` deliberately, because that is
# the path 100% of real KBs take; the rest build the template they need.


_SYNTHETIC_PACKAGES = itertools.count()


def _manifest_template(
    *, final_k: int, comments: Sequence[str] = (), rerank: bool = True, extra: str = ""
) -> str:
    """A manifest template shaped like the real one: an identity block whose every field is a
    rendered variable, some rendered values, and literals a user is free to edit.

    The `[kb]` block matters most — it is the one the report must never produce a hunk for.
    """
    body = [
        "[kb]",
        'name     = "{{ name }}"',
        'id       = "{{ kb_id }}"',
        'template = "{{ template }}"',
        'created  = "{{ created }}"',
        "",
        "[embedding]",
        'provider = "{{ embedding_provider }}"',
        'model    = "{{ embedding_model }}"',
        "dim      = {{ embedding_dim }}",
        "",
    ]
    if rerank:
        body += ["[rerank]", 'model    = "{{ rerank_model }}"', ""]
    body += ["[retrieval]", *comments, f"final_k = {final_k}"]
    if extra:
        body.append(extra)
    return "\n".join(body) + "\n"


@pytest.fixture
def synthetic_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., str]]:
    """Build a template with any number of archived versions, in a package of its own.

    A real importable package rather than a monkeypatched `_root`, so `describe`,
    `archived_versions`, `archived_root` and `render_archived` all run their real
    `importlib.resources` paths — the ones that have to work from inside a wheel.
    """
    package = f"synthetic_templates_{next(_SYNTHETIC_PACKAGES)}"
    root = tmp_path / package
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    # `monkeypatch.syspath_prepend` is untyped, and this file is checked under pyright strict.
    sys.path.insert(0, str(tmp_path))
    monkeypatch.setattr(template, "PACKAGE", package)
    importlib.invalidate_caches()

    def _make(name: str, *, versions: Mapping[str, str], current: str) -> str:
        def declaration(version: str) -> str:
            return f'name = "{name}"\nversion = "{version}"\ndescription = "synthetic"\n'

        directory = root / name
        directory.mkdir()
        (directory / "template.toml").write_text(declaration(current), encoding="utf-8")
        (directory / "pinakes.toml.j2").write_text(versions[current], encoding="utf-8")
        for version, source in versions.items():
            archived = directory / template.VERSIONS_DIR / version
            archived.mkdir(parents=True)
            (archived / "template.toml").write_text(declaration(version), encoding="utf-8")
            (archived / "pinakes.toml.j2").write_text(source, encoding="utf-8")
        return name

    yield _make
    sys.modules.pop(package, None)
    sys.path.remove(str(tmp_path))


def _record_template(root: Path, reference: str) -> Path:
    """Point a KB's manifest at *reference*, refusing a no-op substitution.

    `str.replace` returns the string unchanged when it matches nothing and reports it to nobody,
    which is how I7a built a "paid" KB that was never paid (docs/RETROSPECTIVES.md).
    """
    path = root / "pinakes.toml"
    edited, count = re.subn(
        r'^template = ".+"$',
        f'template = "{reference}"',
        path.read_text(encoding="utf-8"),
        count=1,
        flags=re.MULTILINE,
    )
    assert count == 1, "the manifest's template line has changed shape"
    path.write_text(edited, encoding="utf-8")
    return root


def _reported_lines(detail: str) -> int:
    found = re.search(r"(\d+) lines? differs?\b", detail)
    assert found is not None, f"no line count in {detail!r}"
    return int(found.group(1))


def test_a_kb_recording_an_older_template_version_reports_the_line_count(
    kb: Path, synthetic_template: Callable[..., str]
) -> None:
    """The literal `2` is safe here in a way it would never be against `notes`: this pair is built
    three lines above the assertion, so it cannot drift under a commit to the shipped template —
    which is exactly how an earlier draft of the plan got its count, its composition *and* its
    claim that the lines were comments wrong."""
    synthetic_template(
        "synth",
        versions={"1.0": _manifest_template(final_k=5), "2.0": _manifest_template(final_k=8)},
        current="2.0",
    )
    check = template_check(_record_template(kb, "synth@1.0"))

    assert check.status is Status.WARN
    assert "synth@1.0" in check.detail and "synth@2.0" in check.detail
    assert _reported_lines(check.detail) == 2, check.detail  # one line removed, one added


def test_a_user_edited_manifest_value_never_appears_in_the_template_drift_report(
    kb: Path, synthetic_template: Callable[..., str]
) -> None:
    """The test that catches D-2 option B being implemented by accident — a report built from the
    user's own `pinakes.toml` rather than from two archived templates.

    Both halves of the property, because they fail for different reasons: a **rendered** variable
    (`embedding_model`) is identical on both sides and so cancels; a **literal** (`final_k`) never
    enters either side, because neither side is the user's file.

    **The third edit adds a line rather than substituting one, and it is the only one that kills
    the mutant.** Measured: with `base` swapped for the user's raw `pinakes.toml` — D-2 option B,
    implemented by accident — the two substitutions above left the count *identical*, because one
    line replaced by another line is still one line on each side of the diff. The count was
    invariant under an implementation that had the user's file in it, which is the exact defect
    class this test exists to catch. An added line is not absorbed that way.
    """
    synthetic_template(
        "synth",
        versions={"1.0": _manifest_template(final_k=5), "2.0": _manifest_template(final_k=8)},
        current="2.0",
    )
    root = _record_template(kb, "synth@1.0")
    before = template_check(root).detail
    assert _reported_lines(before) > 0, "a comparison that reported nothing would be invariant too"

    path = root / "pinakes.toml"
    body = path.read_text(encoding="utf-8")
    body, rendered_edits = re.subn(
        r'^model    = "fake-model"$', 'model    = "fastembed-model"', body, flags=re.MULTILINE
    )
    body, literal_edits = re.subn(r"^final_k\s*=.*$", "final_k = 4", body, flags=re.MULTILINE)
    assert rendered_edits == 1 and literal_edits == 1, "the manifest's shape has changed"
    path.write_text(
        body + "\n# A comment of my own, which is nobody's business but mine.\n",
        encoding="utf-8",
    )

    assert template_check(root).detail == before


def test_a_comment_only_template_change_is_reported(
    kb: Path, synthetic_template: Callable[..., str]
) -> None:
    """The live gap this release exists for is *entirely* comments (F3, M3): the PDF-glob block
    added four comment lines and changed no key. A report that missed a comment-only change would
    report nothing on the case that motivated the work."""
    synthetic_template(
        "synth",
        versions={
            "1.0": _manifest_template(final_k=5),
            "2.0": _manifest_template(
                final_k=5,
                comments=[
                    '# Add "**/*.pdf" to `include` above to index PDFs.',
                    "# Left out rather than commented into place: `init` cannot see the extractor.",
                ],
            ),
        },
        current="2.0",
    )
    check = template_check(_record_template(kb, "synth@1.0"))

    assert check.status is Status.WARN
    assert _reported_lines(check.detail) == 2, check.detail  # two comment lines added, none removed


def test_the_kb_identity_block_never_produces_a_hunk(
    kb: Path, synthetic_template: Callable[..., str]
) -> None:
    """The `{{ template }}` choice, asserted where it can actually fail.

    Rendering `base` with the recorded reference and `ours` with the *installed* one is what a
    reader of `init.py:75` would write, and it puts a `[kb]` hunk in every report on every KB —
    which under T4's all-or-nothing conflict rule would make `--apply` refuse for every user who
    has ever touched their `[kb]` block.

    **Asserted through `pnk doctor`, not only through `render_archived`.** The direct-render half
    below pins `render_context`'s contract, and it is worth having — but on its own it left the
    mutant alive: feeding `ours` the installed reference *inside `doctor`* changed nothing the test
    looked at, because the test never called `doctor`. Measured, not reasoned about. The count is
    what `doctor` exposes, so the pair below differs by exactly one line outside `[kb]`; a leaking
    identity block adds two more and the count says so.
    """
    name = synthetic_template(
        "synth",
        versions={"1.0": _manifest_template(final_k=5), "2.0": _manifest_template(final_k=8)},
        current="2.0",
    )
    root = _record_template(kb, "synth@1.0")
    context = template.render_context(load(root))
    base = template.render_archived(name, "1.0", context)
    ours = template.render_archived(name, "2.0", context)

    assert 'template = "synth@1.0"' in base, "the recorded reference, not the installed one"
    assert 'template = "synth@1.0"' in ours, "both sides render what the KB recorded"
    assert "synth@2.0" not in base and "synth@2.0" not in ours

    changed = [
        line
        for line in list(
            difflib.unified_diff(base.splitlines(), ours.splitlines(), lineterm="", n=0)
        )[2:]
        if line[:1] in ("+", "-")
    ]
    assert changed, "a pair that does not differ would satisfy the next assertion vacuously"
    assert not [line for line in changed if "template =" in line or "id " in line]

    # The half that reaches `doctor`. `final_k` is the only line these two versions differ on, so
    # a correct report counts exactly the two lines that change; an identity block leaking into the
    # comparison would put `template = ` on both sides of the diff and make it four.
    assert _reported_lines(template_check(root).detail) == 2


def test_an_unarchived_recorded_version_says_it_cannot_compare_rather_than_ok(kb: Path) -> None:
    """Run against the shipped `notes`, because under D-2b this is what 100% of real KBs do.

    `WARN` alone does not discriminate — the version-mismatch line on `main` before this increment
    was also a `WARN` — so the remedy is what is asserted: it has to name the comparison that is
    available to someone who did nothing wrong.
    """
    check = template_check(_record_template(kb, "notes@1.0"))

    assert check.status is Status.WARN
    assert "cannot compare" in check.detail
    assert "notes@1.0" in check.detail
    remedy = check.remedy or ""
    assert "compare it by hand" in remedy
    assert "pnk init" in remedy, "the manual comparison has to be named, not alluded to"
    assert "nothing needs changing" in remedy, "written for a user who did nothing wrong"


def test_a_template_version_needing_an_unknown_variable_refuses_with_a_message(
    kb: Path, synthetic_template: Callable[..., str]
) -> None:
    """A third-party template can need a variable no union contains. `jinja2.UndefinedError` is not
    a `PinakesError`, so without the mapping `cli.main` prints a traceback.

    Asserted on the **message**, not on the fact that something was raised — the weaker form is
    satisfied by any error at all, including the traceback this exists to prevent.
    """
    name = synthetic_template(
        "synth",
        versions={
            "1.0": _manifest_template(final_k=5, extra='owner    = "{{ unknown_variable }}"'),
            "2.0": _manifest_template(final_k=8),
        },
        current="2.0",
    )
    root = _record_template(kb, "synth@1.0")

    with pytest.raises(TemplateError) as caught:
        template.render_archived(name, "1.0", template.render_context(load(root)))
    assert "synth@1.0" in str(caught.value), "the message names the version"
    assert "unknown_variable" in str(caught.value), "and the variable"
    assert "cannot render synth@1.0" in (caught.value.remedy or "")

    check = template_check(root)
    assert check.status is Status.WARN, "one unrenderable template does not take the report down"
    assert "unknown_variable" in check.detail, "the row names the variable, not just the failure"
    assert "cannot render synth@1.0" in (check.remedy or "")


def test_a_template_with_no_drift_reports_ok_and_renders_nothing(
    kb: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pnk doctor` on a current KB pays nothing for this check — no archive read, no render."""
    calls: list[tuple[str, str]] = []

    def _record(name: str, version: str, context: Mapping[str, object]) -> str:
        calls.append((name, version))
        return ""

    monkeypatch.setattr(template, "render_archived", _record)
    check = template_check(kb)

    assert check.status is Status.OK
    assert calls == [], "a KB on the installed version has nothing to compare"


def test_an_archived_version_needing_a_variable_the_current_one_dropped_still_renders(
    kb: Path, synthetic_template: Callable[..., str]
) -> None:
    """The union context, as the failure it prevents.

    `render_manifest` uses `StrictUndefined`, so a context built for the *current* version cannot
    render an older one that needs a variable since dropped — and it fails on one side of the
    comparison only, which turns `pnk doctor` into a traceback on a KB whose only fault is age.
    """
    synthetic_template(
        "synth",
        versions={
            "1.0": _manifest_template(final_k=5, rerank=True),
            "2.0": _manifest_template(final_k=8, rerank=False),
        },
        current="2.0",
    )
    check = template_check(_record_template(kb, "synth@1.0"))

    assert check.status is Status.WARN
    assert _reported_lines(check.detail) > 0, "it rendered both sides rather than raising"
