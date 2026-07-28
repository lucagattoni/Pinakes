"""`pnk sync` end to end, against a real index and a fake backend."""

import shutil
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest
import yaml

from pinakes import store
from pinakes.embed import EmbeddingBackend, ModelInfo, Vectors
from pinakes.errors import DuplicateIdsError
from pinakes.extract import (
    ExtractedText,
    ExtractionContext,
    ExtractorEntry,
    register_extractor,
    unregister_extractor,
)
from pinakes.ids import mint_doc_id
from pinakes.manifest import Manifest, load
from pinakes.sidecar import SIDECAR_SUFFIX
from pinakes.sync import MAX_PROBED_PER_ROOT, SyncOptions, SyncReport, sync

DIM = 8


class FakeBackend:
    """Deterministic and instant: sync's behaviour is what is under test, not a model's."""

    def embed(self, texts: Sequence[str]) -> Vectors:
        listed = list(texts)
        if not listed:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.ascontiguousarray(
            np.vstack([np.full(DIM, (len(text) % 7) / 7.0, dtype=np.float32) for text in listed]),
            dtype=np.float32,
        )

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", None, DIM, 512)


def fake_factory(manifest: Manifest, offline: bool) -> EmbeddingBackend:
    return FakeBackend()


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "docs").mkdir(parents=True)
    (root / "pinakes.toml").write_text(
        "\n".join(
            [
                "[kb]",
                'name = "test"',
                'id = "01KYCJ8ZVMBJDB4FKRJRNYS5DT"',
                "",
                "[sources]",
                'roots = ["docs/"]',
                'include = ["**/*.md"]',
                "",
                "[embedding]",
                'provider = "fake"',
                'model = "fake-model"',
                f"dim = {DIM}",
                "",
                "[chunking]",
                "max_tokens = 40",
                "overlap = 4",
            ]
        ),
        encoding="utf-8",
    )
    return root


class _FakePaidExtractor:
    """A working *paid* extractor, standing in for `claude-vision` — whose own loader is a
    permanent I7b stub that always raises (`test_extract.py`'s own
    `test_claude_vision_stub_names_its_own_landing_increment`), so it cannot drive an actual
    free-to-paid re-embed end to end. Deterministic and instant, like `FakeBackend` above; the
    point under test is I5's backend bookkeeping, not a real paid call."""

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractedText:
        text = "Paid extraction output.\n"
        return ExtractedText(text=text, page_spans=((0, len(text)),))


@pytest.fixture
def fake_paid() -> Iterator[str]:
    """Registers a second, real paid backend for the duration of one test — unregistered again on
    teardown regardless of how the test exits, so it never leaks into another test's
    `registered_extractors()`/`paid_backend_names()`."""
    name = "test-paid"
    entry = ExtractorEntry(
        load=_FakePaidExtractor,
        fingerprint_inputs=lambda: {"backend": name},
        paid=True,
    )
    register_extractor(name, entry)
    try:
        yield name
    finally:
        unregister_extractor(name)


def write(kb: Path, name: str, text: str) -> Path:
    path = kb / "docs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run(kb: Path, *, extract: str | None = None, **options: bool) -> SyncReport:
    return sync(
        load(kb),
        options=SyncOptions(extract=extract, **options),
        backend_factory=fake_factory,
        now="20260725 16:00",
    )


def index(kb: Path) -> list[dict[str, object]]:
    """Read every document row and close immediately.

    Deliberately not a generator: an earlier version was one, and a caller using `next()` left the
    connection open, which kept `-wal`/`-shm` alive and made a rebuild assertion fail for a reason
    that had nothing to do with the rebuild.
    """
    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        return [dict(row) for row in connection.execute("SELECT * FROM documents ORDER BY path")]
    finally:
        connection.close()


def test_first_sync_mints_sidecars_indexes_and_embeds(kb: Path) -> None:
    write(kb, "a.md", "# Alpha\n\nThe first document about retrieval.\n")
    write(kb, "b.md", "# Beta\n\nThe second document about ranking.\n")

    report = run(kb)
    assert report.embedded == 2
    assert report.ok

    documents = list(index(kb))
    assert [doc["path"] for doc in documents] == ["docs/a.md", "docs/b.md"]
    assert all(doc["state"] == "active" for doc in documents)

    for name in ("a.md", "b.md"):
        sidecar = kb / "docs" / f"{name}{SIDECAR_SUFFIX}"
        assert sidecar.is_file()
        assert yaml.safe_load(sidecar.read_text(encoding="utf-8"))["id"]

    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        chunk_ids, matrix = store.load_vectors(connection, dim=DIM)
        assert len(chunk_ids) == matrix.shape[0] > 0
        hits = connection.execute(
            "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'retrieval'"
        ).fetchone()[0]
        assert hits == 1
    finally:
        connection.close()


def test_a_second_sync_changes_nothing(kb: Path) -> None:
    write(kb, "a.md", "# Alpha\n\nStable text.\n")
    run(kb)
    report = run(kb)
    assert (report.skipped, report.embedded) == (1, 0)


def test_editing_a_document_re_embeds_it_and_keeps_the_id(kb: Path) -> None:
    write(kb, "a.md", "# Alpha\n\nOriginal.\n")
    run(kb)
    before = index(kb)[0]["id"]

    write(kb, "a.md", "# Alpha\n\nRewritten entirely.\n")
    report = run(kb)

    assert report.embedded == 1
    after = index(kb)[0]
    assert after["id"] == before
    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        assert (
            connection.execute(
                "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'Original'"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()


def test_a_sidecar_only_edit_refreshes_metadata_without_re_embedding(kb: Path) -> None:
    write(kb, "a.md", "# Alpha\n\nText.\n")
    run(kb)
    sidecar = kb / "docs" / f"a.md{SIDECAR_SUFFIX}"
    data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    data["tags"] = ["physics"]
    sidecar.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = run(kb)
    assert (report.refreshed, report.embedded) == (1, 0)
    assert "physics" in str(index(kb)[0]["metadata"])


def test_deleting_a_document_soft_deletes_it_and_removes_its_chunks(kb: Path) -> None:
    write(kb, "a.md", "# Alpha\n\nDisappearing text.\n")
    run(kb)
    (kb / "docs" / "a.md").unlink()

    report = run(kb)
    assert report.deleted == 1
    assert index(kb)[0]["state"] == "deleted"

    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        assert (
            connection.execute(
                "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'Disappearing'"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()
    assert (kb / "docs" / f"a.md{SIDECAR_SUFFIX}").exists()  # never removed automatically


def test_a_rename_keeps_the_id_because_the_sidecar_travels(kb: Path) -> None:
    write(kb, "a.md", "# Alpha\n\nTravelling text.\n")
    run(kb)
    original = index(kb)[0]["id"]

    (kb / "docs" / "a.md").rename(kb / "docs" / "moved.md")
    (kb / "docs" / f"a.md{SIDECAR_SUFFIX}").rename(kb / "docs" / f"moved.md{SIDECAR_SUFFIX}")

    run(kb)
    live = [doc for doc in index(kb) if doc["state"] == "active"]
    assert len(live) == 1
    assert live[0]["id"] == original
    assert live[0]["path"] == "docs/moved.md"


def test_one_broken_document_does_not_block_the_others(kb: Path) -> None:
    """§6.4: per-document transactions; the run continues and the exit code still says it failed."""
    write(kb, "good.md", "# Good\n\nFine text.\n")
    (kb / "docs" / "bad.md").write_bytes(b"\xff\xfe not valid utf-8 \xff")

    report = run(kb)
    assert not report.ok
    assert len(report.failures) == 1
    assert "bad.md" in report.failures[0][0]
    assert [doc["path"] for doc in index(kb)] == ["docs/good.md"]

    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        assert connection.execute("SELECT count(*) FROM failures").fetchone()[0] == 1
    finally:
        connection.close()


def test_a_pdf_fails_at_extraction_but_does_not_block_the_rest(kb: Path) -> None:
    """§6.4 isolation extended to extraction: no adapter yet, and says so once, not per path."""
    manifest_path = kb / "pinakes.toml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', 'include = ["**/*.md", "**/*.pdf"]'
        ),
        encoding="utf-8",
    )
    write(kb, "good.md", "# Good\n\nFine text.\n")
    (kb / "docs" / "a.pdf").write_bytes(b"not a real pdf, and it must not matter")
    (kb / "docs" / "b.pdf").write_bytes(b"neither is this one")

    report = run(kb)
    assert not report.ok
    assert {path for path, _, _ in report.failures} == {"docs/a.pdf", "docs/b.pdf"}
    assert [doc["path"] for doc in index(kb)] == ["docs/good.md"]

    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        stages = {
            str(row["stage"]) for row in connection.execute("SELECT DISTINCT stage FROM failures")
        }
        assert stages == {"extract"}
    finally:
        connection.close()

    remedy = report.failures[0][2]
    assert remedy  # every failure here is a PinakesError; none should carry an empty remedy
    printed = report.lines()
    assert printed.count(remedy) == 1  # once, not once per failing path


def test_sidecars_are_never_ingested_as_documents(kb: Path) -> None:
    """An include pattern must not turn a document's own metadata into a document."""
    write(kb, "a.md", "# Alpha\n\nText.\n")
    run(kb)
    manifest_path = kb / "pinakes.toml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', 'include = ["**/*.md", "**/*.yaml"]'
        ),
        encoding="utf-8",
    )
    run(kb)
    assert [doc["path"] for doc in index(kb)] == ["docs/a.md"]


def test_rebuild_replaces_the_index_and_keeps_the_ledger(kb: Path) -> None:
    write(kb, "a.md", "# Alpha\n\nText.\n")
    run(kb)
    ledger = kb / ".pinakes" / "ledger.jsonl"
    ledger.write_text('{"spend": 1}\n', encoding="utf-8")
    original = index(kb)[0]["id"]

    run(kb, rebuild=True)

    # Checked *before* anything reads the index: opening even a read-only connection to a WAL
    # database creates `-shm`/`-wal` itself, so a later read would mask what the swap left behind.
    state = kb / ".pinakes"
    assert not (state / "index.db.new").exists()
    assert not list(state.glob("index.db-wal"))
    assert not list(state.glob("index.db-shm"))

    assert ledger.read_text(encoding="utf-8") == '{"spend": 1}\n'
    assert index(kb)[0]["id"] == original  # the sidecar carried the id through


def test_sidecars_only_never_touches_the_index(kb: Path) -> None:
    write(kb, "a.md", "# Alpha\n\nText.\n")
    report = run(kb, sidecars_only=True)

    assert report.minted == 1
    assert (kb / "docs" / f"a.md{SIDECAR_SUFFIX}").is_file()
    assert not (kb / ".pinakes" / "index.db").exists()


def test_index_only_never_writes_into_docs(kb: Path) -> None:
    """The post-commit half: the tree it just committed must stay clean (§6.3)."""
    write(kb, "a.md", "# Alpha\n\nText.\n")
    report = run(kb, index_only=True)

    assert report.embedded == 1
    assert not (kb / "docs" / f"a.md{SIDECAR_SUFFIX}").exists()
    assert list(index(kb))


def test_stage_limits_to_staged_files_and_adds_the_sidecars(kb: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=kb, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=kb, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=kb, check=True)
    write(kb, "staged.md", "# Staged\n\nText.\n")
    write(kb, "unstaged.md", "# Unstaged\n\nText.\n")
    subprocess.run(["git", "add", "docs/staged.md"], cwd=kb, check=True)

    report = run(kb, sidecars_only=True, stage=True)

    assert report.minted == 1
    assert (kb / "docs" / f"staged.md{SIDECAR_SUFFIX}").is_file()
    assert not (kb / "docs" / f"unstaged.md{SIDECAR_SUFFIX}").exists()

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=kb,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert f"docs/staged.md{SIDECAR_SUFFIX}" in staged


def test_duplicate_ids_stop_the_sync(kb: Path) -> None:
    write(kb, "a.md", "# A\n\nText.\n")
    write(kb, "b.md", "# B\n\nOther text.\n")
    shared = mint_doc_id()
    for name in ("a.md", "b.md"):
        (kb / "docs" / f"{name}{SIDECAR_SUFFIX}").write_text(
            yaml.safe_dump({"id": shared}), encoding="utf-8"
        )

    with pytest.raises(DuplicateIdsError):
        run(kb)


def test_a_busy_lock_reports_and_exits_cleanly(kb: Path) -> None:
    import json
    import os
    import socket

    state = kb / ".pinakes"
    state.mkdir(parents=True, exist_ok=True)
    (state / "sync.lock").write_text(
        json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "started": "20260725 16:00"}),
        encoding="utf-8",
    )

    report = run(kb)
    assert report.busy


def _add_pdf_support(kb: Path) -> None:
    """`fake` needs no `pypdfium2` and ignores file content, so these tests exercise the cache's
    wiring into `_index_document` without depending on which optional extras are installed."""
    manifest_path = kb / "pinakes.toml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', 'include = ["**/*.md", "**/*.pdf"]'
        )
        + '\n[extraction]\nbackend = "fake"\n',
        encoding="utf-8",
    )


def _cache_files(kb: Path) -> list[Path]:
    return sorted((kb / ".pinakes" / "cache" / "extract").glob("*.json"))


def test_a_pdf_sync_writes_a_cache_entry_and_a_rebuild_reuses_it(kb: Path) -> None:
    """A second *plain* sync of an unchanged PDF never reaches `_index_document` at all — pairing's
    own `Skip` (content_hash unchanged) returns before the cache is ever consulted, so it would
    prove nothing about the cache to just call `run(kb)` twice. `--rebuild` is what actually forces
    every document back through `_index_document` regardless of pairing's skip (`before` is read
    from a brand-new, empty database, so nothing looks unchanged to it) — exactly the scenario the
    cache exists for (docs/DESIGN.md §6.3): re-processing the whole KB without re-paying to
    extract a single unchanged document."""
    _add_pdf_support(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder - the fake backend ignores this")

    first = run(kb)
    assert first.embedded == 1 and first.skipped == 0
    entries = _cache_files(kb)
    assert len(entries) == 1
    first_mtime = entries[0].stat().st_mtime_ns

    second = run(kb, rebuild=True)
    assert second.embedded == 1 and second.skipped == 0  # really went through _index_document again
    entries_again = _cache_files(kb)
    assert len(entries_again) == 1
    assert entries_again[0] == entries[0]
    assert entries_again[0].stat().st_mtime_ns == first_mtime  # unchanged: a hit, never a re-write


def test_a_fully_successful_sync_evicts_a_deleted_documents_cache_entry(kb: Path) -> None:
    _add_pdf_support(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    run(kb)
    assert len(_cache_files(kb)) == 1

    (kb / "docs" / "a.pdf").unlink()
    (kb / "docs" / f"a.pdf{SIDECAR_SUFFIX}").unlink()  # no hash match => soft delete, not a rename
    report = run(kb)
    assert report.ok
    assert _cache_files(kb) == []


def test_deleting_one_of_two_same_content_documents_keeps_the_shared_cache_entry(
    kb: Path,
) -> None:
    """Eviction keys on `content_hash`, not on any one document — as long as *some* active
    document still claims it, the shared entry must survive deleting the others."""
    _add_pdf_support(kb)
    same_bytes = b"identical content shared by two documents"
    (kb / "docs" / "a.pdf").write_bytes(same_bytes)
    (kb / "docs" / "b.pdf").write_bytes(same_bytes)
    run(kb)
    assert len(_cache_files(kb)) == 1  # one content_hash, one entry, regardless of path count

    (kb / "docs" / "b.pdf").unlink()
    (kb / "docs" / f"b.pdf{SIDECAR_SUFFIX}").unlink()
    report = run(kb)
    assert report.ok
    assert len(_cache_files(kb)) == 1  # a.pdf still claims the same content_hash


def test_clear_cache_preserves_the_ledger(kb: Path) -> None:
    _add_pdf_support(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    run(kb)
    assert len(_cache_files(kb)) == 1

    ledger = kb / ".pinakes" / "ledger.jsonl"
    ledger.write_text('{"spend": 1}\n', encoding="utf-8")

    report = sync(load(kb), options=SyncOptions(clear_cache=True, yes=True))

    assert report.cache_cleared == 1
    assert _cache_files(kb) == []
    assert ledger.read_text(encoding="utf-8") == '{"spend": 1}\n'


def test_clear_cache_without_yes_and_without_a_tty_aborts(kb: Path) -> None:
    _add_pdf_support(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    run(kb)
    assert len(_cache_files(kb)) == 1

    report = sync(load(kb), options=SyncOptions(clear_cache=True))

    assert report.cache_clear_aborted
    assert report.cache_pending_entries == 1
    assert len(_cache_files(kb)) == 1  # nothing removed


def test_clear_cache_on_an_empty_cache_is_a_no_op_not_a_prompt(kb: Path) -> None:
    report = sync(load(kb), options=SyncOptions(clear_cache=True))
    assert report.cache_cleared == 0
    assert not report.cache_clear_aborted
    assert report.ok


# --- I5: decision 9's six backend-drift cases, end to end ------------------------------------


def _paid_index(kb: Path, fake_paid: str) -> None:
    """Every case but `free_then_paid` starts from an already paid-indexed PDF."""
    _add_pdf_support(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
    first = run(kb, extract=fake_paid)
    assert first.embedded == 1
    assert index(kb)[0]["extraction_backend"] == fake_paid


@pytest.mark.parametrize(
    "case_id",
    [
        "free_then_paid",
        "protected_from_a_free_run",
        "protected_from_rebuild",
        "protected_from_an_explicit_free_extract",
        "force_overwrites",
        "changed_hash",
    ],
)
def test_backend_drift(kb: Path, fake_paid: str, case_id: str) -> None:
    """Decision 9's six named cases (plans/v0.2.md), addressed as `test_backend_drift[<case_id>]`.

    `pairing.py`'s own tests already cover the decision table in isolation; this is the same six
    rules wired all the way through a real `sync()` call — the actual DB row, the actual sidecar,
    the actual report the CLI would print.
    """
    if case_id == "free_then_paid":
        _add_pdf_support(kb)
        (kb / "docs" / "a.pdf").write_bytes(b"placeholder")
        first = run(kb)
        assert first.embedded == 1
        assert index(kb)[0]["extraction_backend"] == "fake"

        report = run(kb, extract=fake_paid)
        assert report.embedded == 1
        assert index(kb)[0]["extraction_backend"] == fake_paid
        return

    _paid_index(kb, fake_paid)

    if case_id == "protected_from_a_free_run":
        report = run(kb)  # the manifest's own [extraction] backend = "fake" — a hook-style run
        assert (report.skipped, report.embedded) == (1, 0)
        assert report.paid_extraction_protected == ("docs/a.pdf",)
    elif case_id == "protected_from_rebuild":
        report = run(kb, rebuild=True)
        assert report.ok
        assert report.paid_extraction_protected == ("docs/a.pdf",)
    elif case_id == "protected_from_an_explicit_free_extract":
        report = run(kb, extract="pypdfium2")  # explicit free backend, no --force
        assert (report.skipped, report.embedded) == (1, 0)
        assert report.paid_extraction_protected == ("docs/a.pdf",)
    elif case_id == "force_overwrites":
        report = run(kb, extract="fake", force=True)
        assert report.embedded == 1
        assert report.paid_extraction_overwritten == ("docs/a.pdf",)
        printed = report.lines()
        assert any("docs/a.pdf" in line and "discarded" in line for line in printed)
        assert index(kb)[0]["extraction_backend"] == "fake"
        return
    elif case_id == "changed_hash":
        (kb / "docs" / "a.pdf").write_bytes(b"changed, invalidating the paid extraction")
        report = run(kb)  # free effective backend
        assert not report.ok
        assert len(report.failures) == 1
        path, _error, remedy = report.failures[0]
        assert path == "docs/a.pdf"
        assert fake_paid in remedy
        assert index(kb)[0]["extraction_backend"] == fake_paid  # untouched, not silently downgraded
        return

    after = index(kb)[0]
    assert after["extraction_backend"] == fake_paid  # in every remaining case, still untouched


def test_force_alone_without_an_explicit_extract_does_not_override(
    kb: Path, fake_paid: str
) -> None:
    """`--force` protects nothing by itself — this is the manifest-default-backend counterpart to
    `pairing.py`'s own unit test of the same rule."""
    _paid_index(kb, fake_paid)

    report = run(kb, force=True)  # no explicit --extract
    assert (report.skipped, report.embedded) == (1, 0)
    assert report.paid_extraction_protected == ("docs/a.pdf",)
    assert index(kb)[0]["extraction_backend"] == fake_paid


def test_force_overwrite_clears_the_stale_sidecar_provenance(kb: Path, fake_paid: str) -> None:
    """After `--force` downgrades a paid extraction to free, the sidecar must stop claiming a paid
    extraction it no longer describes — otherwise a later sync (or a different clone reading the
    same committed sidecar) would wrongly believe the file is still protected."""
    _paid_index(kb, fake_paid)
    sidecar_file = kb / "docs" / f"a.pdf{SIDECAR_SUFFIX}"
    before = yaml.safe_load(sidecar_file.read_text(encoding="utf-8"))
    assert before["provenance"]["extraction"]["backend"] == fake_paid

    run(kb, extract="fake", force=True)

    after = yaml.safe_load(sidecar_file.read_text(encoding="utf-8"))
    assert "extraction" not in after.get("provenance", {})


# --- I5: rebuild-provenance -------------------------------------------------------------------


def test_a_rebuild_preserves_paid_provenance(kb: Path, fake_paid: str) -> None:
    """`--rebuild` under a free manifest must leave a paid-extracted document untouched: the same
    id, the same backend/fingerprint, and its chunks and vectors carried over rather than
    re-embedded — the sidecar's `provenance.extraction` is what makes this possible even though
    `--rebuild`'s own `before` snapshot is read from a brand-new, empty database (decision 11)."""
    _paid_index(kb, fake_paid)
    before = index(kb)[0]

    report = run(kb, rebuild=True)

    assert report.ok
    after = index(kb)[0]
    assert after["id"] == before["id"]
    assert after["extraction_backend"] == fake_paid
    assert after["extraction_fingerprint"] == before["extraction_fingerprint"]

    sidecar = yaml.safe_load((kb / "docs" / f"a.pdf{SIDECAR_SUFFIX}").read_text(encoding="utf-8"))
    assert sidecar["provenance"]["extraction"]["backend"] == fake_paid

    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        chunk_ids, matrix = store.load_vectors(connection, dim=DIM)
        assert len(chunk_ids) == matrix.shape[0] > 0  # the embeddings really did carry over
        hits = connection.execute(
            "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'Paid'"
        ).fetchone()[0]
        assert hits == 1  # the FTS index was rebuilt from the copied-forward chunk, not skipped
    finally:
        connection.close()


def test_a_rebuild_after_clear_cache_still_preserves_it(kb: Path, fake_paid: str) -> None:
    """The sequence a cache-based answer would have failed (plan text): if paid-extraction
    protection depended on `extract/cache.py` still holding the entry, `--clear-cache` immediately
    before `--rebuild` would empty it first, and the rebuild would either wrongly demand paying
    again or — worse — silently fall back to a free re-extraction. `_paid_rebuild_survivors` reads
    the *old index* being replaced instead, which `--clear-cache` never touches, so this sequence
    must come out identical to a rebuild with a warm cache."""
    _paid_index(kb, fake_paid)
    before = index(kb)[0]
    assert _cache_files(kb)  # confirm there is something for --clear-cache to actually remove

    cleared = sync(load(kb), options=SyncOptions(clear_cache=True, yes=True))
    assert cleared.cache_cleared == 1
    assert _cache_files(kb) == []

    report = run(kb, rebuild=True)

    assert report.ok
    assert not report.failures
    after = index(kb)[0]
    assert after["id"] == before["id"]
    assert after["extraction_backend"] == fake_paid
    assert after["extraction_fingerprint"] == before["extraction_fingerprint"]

    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        chunk_ids, matrix = store.load_vectors(connection, dim=DIM)
        assert len(chunk_ids) == matrix.shape[0] > 0
    finally:
        connection.close()


def test_a_rebuild_never_lets_a_free_twin_inherit_the_paid_ones_backend(
    kb: Path, fake_paid: str
) -> None:
    """Two different documents can share one content_hash with only one of them paid: `b.pdf` is
    minted later, under a free effective backend, and its own fresh sidecar carries no recorded
    provenance yet — so it gets a normal free extraction of its own, same as any first-time PDF,
    even though `a.pdf` (identical bytes) already has a paid one. `_paid_rebuild_survivors` must
    key on (content_hash, path), not content_hash alone, or `b.pdf`'s rebuild would incorrectly
    match `a.pdf`'s entry and inherit its chunks, embeddings and paid backend label."""
    _add_pdf_support(kb)
    same_bytes = b"identical content, only one of the two copies ever paid to extract"
    (kb / "docs" / "a.pdf").write_bytes(same_bytes)
    run(kb, extract=fake_paid)

    (kb / "docs" / "b.pdf").write_bytes(same_bytes)
    second = run(kb)  # manifest's own backend stays "fake" (free) — b.pdf is a brand-new Mint
    assert second.ok
    rows_by_path = {row["path"]: row for row in index(kb)}
    assert rows_by_path["docs/a.pdf"]["extraction_backend"] == fake_paid
    assert rows_by_path["docs/b.pdf"]["extraction_backend"] == "fake"
    b_id_before = rows_by_path["docs/b.pdf"]["id"]

    report = run(kb, rebuild=True)

    assert report.ok
    assert report.paid_extraction_protected == ("docs/a.pdf",)  # b.pdf must not appear here
    after_by_path = {row["path"]: row for row in index(kb)}
    assert after_by_path["docs/a.pdf"]["extraction_backend"] == fake_paid
    assert after_by_path["docs/b.pdf"]["extraction_backend"] == "fake"  # not silently upgraded
    assert after_by_path["docs/b.pdf"]["id"] == b_id_before


# --- I5 retrospective: protection must not depend on the extraction cache existing at all -----
#
# The original design only protected a paid extraction via `pairing.py`'s "same path" comparison
# (a normal sync) or `--rebuild`'s own copy-forward. Any *other* pairing outcome — a rename, or a
# document adopted some other way — fell through to `_extract_for_index`'s cache lookup alone,
# which cannot tell "just renamed" or "just cloned" apart from "content actually changed": all
# three look identical to it as a cache miss. These four tests each construct one specific gap
# an adversarial review caught, and were confirmed to fail without their corresponding fix.


def test_a_rename_after_clear_cache_does_not_falsely_claim_content_changed(
    kb: Path, fake_paid: str
) -> None:
    """A rename (sidecar travels) reaches pairing's `Adopt`/`Rename` branch, never the same-path
    comparison a normal unchanged sync uses — so protection has to survive `--clear-cache` here
    too, not only during `--rebuild`."""
    _paid_index(kb, fake_paid)
    sync(load(kb), options=SyncOptions(clear_cache=True, yes=True))

    (kb / "docs" / "a.pdf").rename(kb / "docs" / "b.pdf")
    (kb / "docs" / f"a.pdf{SIDECAR_SUFFIX}").rename(kb / "docs" / f"b.pdf{SIDECAR_SUFFIX}")

    report = run(kb)  # manifest's own backend stays "fake" (free)
    assert report.ok
    rows = {row["path"]: row for row in index(kb)}
    assert rows["docs/b.pdf"]["extraction_backend"] == fake_paid


def test_a_fresh_clone_with_no_local_cache_or_index_fails_honestly_not_falsely(
    kb: Path, fake_paid: str
) -> None:
    """Simulates cloning a KB whose paid PDFs were extracted on a different machine: `docs/` (with
    its committed sidecar) survives, `.pinakes/` (index and cache both, per DESIGN.md's own "a
    freshly cloned KB has no index at all") does not. The file is byte-identical; the failure must
    say so, never claim the content changed."""
    _paid_index(kb, fake_paid)
    shutil.rmtree(kb / ".pinakes")

    report = run(kb)
    assert not report.ok
    assert len(report.failures) == 1
    path, error, remedy = report.failures[0]
    assert path == "docs/a.pdf"
    assert "PaidExtractionUnavailableError" in error
    assert "PaidExtractionRequiredError" not in error
    assert "unchanged" in error
    assert fake_paid in remedy


def test_a_rebuild_keeps_a_changed_paid_document_searchable_but_flagged(
    kb: Path, fake_paid: str
) -> None:
    """A paid-recorded document whose content changed must not simply vanish from a rebuilt
    index — a normal sync leaves its old text searchable in the identical situation (decision 14),
    and `--rebuild` must match that rather than silently dropping it the moment the whole index
    happens to be under reconstruction."""
    _paid_index(kb, fake_paid)
    before = index(kb)[0]

    (kb / "docs" / "a.pdf").write_bytes(b"changed, invalidating the paid extraction")
    report = run(kb, rebuild=True)

    assert not report.ok
    assert len(report.failures) == 1
    path, error, remedy = report.failures[0]
    assert path == "docs/a.pdf"
    assert "kept at its last paid extraction" in error
    assert fake_paid in remedy

    after = index(kb)[0]
    assert after["id"] == before["id"]
    assert after["extraction_backend"] == fake_paid
    assert after["content_hash"] == before["content_hash"]  # the OLD hash, not the changed one

    connection = store.connect_ro(kb / ".pinakes" / "index.db")
    try:
        chunk_ids, matrix = store.load_vectors(connection, dim=DIM)
        assert len(chunk_ids) == matrix.shape[0] > 0  # still searchable, not dropped
    finally:
        connection.close()


def test_three_consecutive_paid_syncs_settle_after_the_first(kb: Path, fake_paid: str) -> None:
    """A fresh paid-provenance write must recompute `sidecar_hash` from the file it just wrote —
    otherwise the very next sync sees a sidecar hash it did not expect and spends a whole extra
    cycle on a spurious `RefreshMetadata` before settling."""
    _add_pdf_support(kb)
    (kb / "docs" / "a.pdf").write_bytes(b"placeholder")

    first = run(kb, extract=fake_paid)
    second = run(kb, extract=fake_paid)
    third = run(kb, extract=fake_paid)

    assert (first.embedded, first.refreshed, first.skipped) == (1, 0, 0)
    assert (second.embedded, second.refreshed, second.skipped) == (0, 0, 1)
    assert (third.embedded, third.refreshed, third.skipped) == (0, 0, 1)


# --- unmatched files: a file skipped for want of a glob must say so (0.2.2) -------------------


def test_a_pdf_with_no_matching_glob_is_named_not_silently_skipped(kb: Path) -> None:
    """The defect this fixes: `pnk init` stamps no `**/*.pdf`, so a PDF dropped into a fresh KB
    matched nothing and sync reported `0 indexed` explaining nothing — v0.2's headline feature
    silently off, with the output giving no hint why."""
    (kb / "docs" / "report.pdf").write_bytes(b"%PDF-1.4\nnot really a pdf\n")

    report = run(kb)

    assert report.embedded == 0
    assert report.unmatched == ("docs/report.pdf",)
    line = next(line for line in report.lines() if "matched no `include` pattern" in line)
    assert '"**/*.pdf"' in line  # the exact glob to add, not a vague pointer
    assert "`exclude`" in line  # and the way to silence it instead


def test_unmatched_files_are_reported_even_when_others_indexed_fine(kb: Path) -> None:
    """The mixed case is the dangerous one: a sync that indexes the Markdown and drops the PDFs
    reports success, so nothing prompts the user to look. Silence here is worse than silence on an
    empty KB, which at least invites investigation."""
    write(kb, "notes.md", "# Notes\n\nIndexed fine.\n")
    (kb / "docs" / "report.pdf").write_bytes(b"%PDF-1.4\n")

    report = run(kb)

    assert report.embedded == 1
    assert report.ok  # not a failure — the run succeeded, it just was not complete
    assert report.unmatched == ("docs/report.pdf",)


def test_binaries_are_never_reported_because_the_remedy_would_not_work(kb: Path) -> None:
    """A file pinakes could not read however the manifest is configured must stay silent: every
    non-PDF source goes through `read_text(encoding="utf-8")`, so telling the user to add
    `"**/*.png"` would hand them a remedy that produces a `UnicodeDecodeError` failure row when
    followed. A wrong hint is worse than none."""
    (kb / "docs" / "diagram.png").write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64)
    (kb / "docs" / "utf16.txt").write_text("hello", encoding="utf-16")

    report = run(kb)

    assert report.unmatched == ()
    assert not any("matched no `include` pattern" in line for line in report.lines())


def test_an_unknown_text_format_is_reported_since_it_indexes_as_text(kb: Path) -> None:
    """`chunk.source_type` falls back to `"text"` for any unrecognised suffix, so `.rst`/`.org`/
    `.tex` genuinely index once a glob matches them. A fixed extension allowlist would have stayed
    silent here; deciding by decodability does not."""
    (kb / "docs" / "guide.rst").write_text("Title\n=====\n\nBody.\n", encoding="utf-8")

    report = run(kb)

    assert report.unmatched == ("docs/guide.rst",)


def test_excluded_and_hidden_files_are_never_reported(kb: Path) -> None:
    """`exclude` is the user having already said "not this" — repeating it back as a suggestion
    would be noise. Dotted segments (`.git/`, `.DS_Store`) are never the corpus."""
    manifest = (kb / "pinakes.toml").read_text(encoding="utf-8")
    (kb / "pinakes.toml").write_text(
        manifest.replace(
            'include = ["**/*.md"]', 'include = ["**/*.md"]\nexclude = ["**/vendor/**"]'
        ),
        encoding="utf-8",
    )
    (kb / "docs" / "vendor").mkdir()
    (kb / "docs" / "vendor" / "third-party.rst").write_text("Vendored.\n", encoding="utf-8")
    (kb / "docs" / ".hidden").mkdir()
    (kb / "docs" / ".hidden" / "secret.rst").write_text("Hidden.\n", encoding="utf-8")
    (kb / "docs" / ".DS_Store").write_bytes(b"\x00\x01")

    report = run(kb)

    assert report.unmatched == ()


def test_a_matched_file_is_not_also_reported_as_unmatched(kb: Path) -> None:
    """The two sets must be disjoint — a document that indexed fine appearing in the "you have no
    glob for this" line would be a plain contradiction."""
    write(kb, "notes.md", "# Notes\n\nBody.\n")

    report = run(kb)

    assert report.embedded == 1
    assert report.unmatched == ()


def test_the_unmatched_line_groups_by_extension_and_caps_the_list(kb: Path) -> None:
    """By extension, not by path: twelve unindexed PDFs are one missing glob, and printing twelve
    paths would obscure that. Capped so a KB with many stray formats still prints one readable
    line."""
    for index_ in range(4):
        (kb / "docs" / f"doc{index_}.rst").write_text("Body.\n", encoding="utf-8")
    (kb / "docs" / "a.org").write_text("Body.\n", encoding="utf-8")
    (kb / "docs" / "b.tex").write_text("Body.\n", encoding="utf-8")
    (kb / "docs" / "c.adoc").write_text("Body.\n", encoding="utf-8")

    report = run(kb)

    line = next(line for line in report.lines() if "matched no `include` pattern" in line)
    assert "7 file(s)" in line
    assert ".rst (4)" in line  # commonest first
    assert '"**/*.rst"' in line  # and it is the one the remedy names
    assert "and 1 more" in line  # 4 distinct extensions, 3 shown


def test_a_cjk_document_is_reported_not_judged_unreadable(kb: Path) -> None:
    """The probe reads a fixed 8 KB prefix, and a fixed byte cut lands mid-character in any script
    whose codepoints are multi-byte — roughly two times in three for CJK. Decoded non-incrementally,
    the split trailing character raised `UnicodeDecodeError`, `_indexable` returned False, and every
    non-English corpus got this feature's silence handed straight back."""
    (kb / "docs" / "notes.rst").write_text(
        "中" * 5000, encoding="utf-8"
    )  # ~15 KB, valid throughout

    report = run(kb)

    assert report.unmatched == ("docs/notes.rst",)


@pytest.mark.parametrize("pad", [8189, 8190, 8191, 8192])
def test_the_probe_boundary_never_rejects_valid_utf8(kb: Path, pad: int) -> None:
    """Every offset where a multi-byte character can straddle the probe's last byte."""
    (kb / "docs" / "notes.rst").write_text("a" * pad + "中" * 20, encoding="utf-8")

    assert run(kb).unmatched == ("docs/notes.rst",)


def test_two_roots_never_report_a_file_the_other_root_indexed(kb: Path) -> None:
    """`matched` must be complete before anything is tested against it. Collecting unmatched files
    inside the per-root loop tested each file against a `files` the later roots had not contributed
    to yet — so a document indexed via root B was *also* reported as having no pattern, and swapping
    the two roots in the manifest made it disappear. An ordering artefact, in output whose entire
    job is to be trusted."""
    manifest = (kb / "pinakes.toml").read_text(encoding="utf-8")
    (kb / "pinakes.toml").write_text(
        manifest.replace('roots = ["docs/"]', 'roots = ["docs/", "docs/sub/"]'), encoding="utf-8"
    )
    (kb / "docs" / "sub").mkdir()
    write(kb, "a.md", "# A\n\nBody.\n")
    (kb / "docs" / "sub" / "b.md").write_text("# B\n\nBody.\n", encoding="utf-8")

    report = run(kb)

    assert report.embedded == 2
    assert set(report.unmatched) & {doc["path"] for doc in index(kb)} == set()
    assert report.unmatched == ()


def test_root_order_does_not_change_what_is_reported(kb: Path) -> None:
    """The same KB, the same two roots, listed the other way round — identical output or the
    reporting is an artefact of manifest ordering rather than a fact about the KB."""
    manifest = (kb / "pinakes.toml").read_text(encoding="utf-8")
    (kb / "docs" / "sub").mkdir()
    write(kb, "a.md", "# A\n\nBody.\n")
    (kb / "docs" / "sub" / "b.md").write_text("# B\n\nBody.\n", encoding="utf-8")
    (kb / "docs" / "sub" / "c.rst").write_text("Body.\n", encoding="utf-8")

    (kb / "pinakes.toml").write_text(
        manifest.replace('roots = ["docs/"]', 'roots = ["docs/", "docs/sub/"]'), encoding="utf-8"
    )
    forwards = run(kb, rebuild=True).unmatched
    (kb / "pinakes.toml").write_text(
        manifest.replace('roots = ["docs/"]', 'roots = ["docs/sub/", "docs/"]'), encoding="utf-8"
    )
    backwards = run(kb, rebuild=True).unmatched

    assert forwards == backwards == ("docs/sub/c.rst",)


def test_an_uppercase_extension_gets_a_glob_that_actually_matches_it(kb: Path) -> None:
    """`pathlib` glob is case-sensitive on POSIX whatever the filesystem does, so `"**/*.pdf"` does
    not match `Report.PDF`. Lowercasing the suffix for the hint produced a remedy that fails to fix
    the file it was printed for."""
    (kb / "docs" / "Report.PDF").write_bytes(b"%PDF-1.4\n")

    report = run(kb)

    line = next(line for line in report.lines() if "matched no `include` pattern" in line)
    assert '"**/*.PDF"' in line
    assert '"**/*.pdf"' not in line


def test_an_unmatched_pdf_names_the_extra_it_will_still_need(
    kb: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding the glob on a core-only install turns every PDF from silently skipped into loudly
    failed — the same trap `_indexable` refuses to set for images, so the hint carries both halves.

    The extractor is forced *missing* rather than left to the environment: this repo's CI runs a
    three-leg extras matrix, so whether `pypdfium2` imports differs per leg, and a test that only
    asserts "the line agrees with the flag" agrees with itself under every leg while proving
    nothing. Verified: that earlier shape survived deleting the whole feature.

    Forced through `is_backend_installed`, which is what `_missing_pdf_extra` probes since I7a —
    it asks the registry whether the backend's module is importable rather than loading it, so a
    paid backend cannot import its client here (gate 4)."""
    import pinakes.sync as sync_module

    def not_installed(_backend: str) -> bool:
        return False

    monkeypatch.setattr(sync_module, "is_backend_installed", not_installed)
    (kb / "docs" / "report.pdf").write_bytes(b"%PDF-1.4\n")

    report = run(kb)

    assert report.unmatched_pdf_extra == "pdf"
    line = next(line for line in report.lines() if "matched no `include` pattern" in line)
    assert 'uv add "pinakes[pdf]"' in line


def test_no_pdf_means_no_extra_hint(kb: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Telling someone to install a PDF extractor when nothing they own is a PDF is noise in a line
    competing for the attention of a person who was just told something got skipped. Forced missing
    for the same reason as above, so the assertion holds under every extras leg."""
    import pinakes.sync as sync_module

    def not_installed(_backend: str) -> bool:
        return False

    monkeypatch.setattr(sync_module, "is_backend_installed", not_installed)
    (kb / "docs" / "guide.rst").write_text("Body.\n", encoding="utf-8")

    report = run(kb)

    assert report.unmatched_pdf_extra is None
    assert "pinakes[pdf]" not in next(
        line for line in report.lines() if "matched no `include` pattern" in line
    )


def test_a_sidecar_is_never_reported_as_an_unindexed_document(kb: Path) -> None:
    """Load-bearing and previously untested: sidecars are `.pnk.yaml`, which no include glob
    matches, so without the guard every document's own metadata would be reported back as a file
    needing a pattern — on every sync after the first."""
    write(kb, "a.md", "# A\n\nBody.\n")
    run(kb)  # mints docs/a.md.pnk.yaml

    second = run(kb)

    assert (kb / "docs" / "a.md.pnk.yaml").exists()
    assert second.unmatched == ()


def test_a_dotted_root_is_walked_normally(kb: Path) -> None:
    """The dotted-segment test is relative to the *source root*, not the KB root — otherwise a KB
    whose root is itself dotted (`~/.config/mykb/`) or a root named `.notes/` would suppress its own
    entire corpus."""
    manifest = (kb / "pinakes.toml").read_text(encoding="utf-8")
    (kb / "pinakes.toml").write_text(
        manifest.replace('roots = ["docs/"]', 'roots = [".notes/"]'), encoding="utf-8"
    )
    (kb / ".notes").mkdir()
    (kb / ".notes" / "guide.rst").write_text("Body.\n", encoding="utf-8")

    assert run(kb).unmatched == (".notes/guide.rst",)


def test_probing_stops_at_the_cap_and_says_the_count_is_partial(kb: Path) -> None:
    """A `node_modules/` under a root is thousands of `open()` calls per sync — a network round trip
    each on an SMB or NFS mount — to produce advice nobody wants. Bounded, and the truncation is
    stated rather than silently capping the number."""
    for index_ in range(MAX_PROBED_PER_ROOT + 50):
        (kb / "docs" / f"f{index_}.rst").write_text("Body.\n", encoding="utf-8")

    report = run(kb)

    assert report.unmatched_truncated
    assert len(report.unmatched) == MAX_PROBED_PER_ROOT
    assert f"{MAX_PROBED_PER_ROOT}+ file(s)" in next(
        line for line in report.lines() if "matched no `include` pattern" in line
    )


def test_and_n_more_counts_extensions_not_files(kb: Path) -> None:
    """The cap shows three extensions; the residue is a count of *extensions*, and the wording has
    to say so. With 40 files across 5 extensions, "and 2 more" read as files makes the numbers in
    one line contradict each other."""
    for suffix, count in (("aa", 10), ("bb", 9), ("cc", 8), ("dd", 7), ("ee", 6)):
        for index_ in range(count):
            (kb / "docs" / f"{suffix}{index_}.{suffix}").write_text("Body.\n", encoding="utf-8")

    line = next(line for line in run(kb).lines() if "matched no `include` pattern" in line)

    assert "40 file(s)" in line
    assert "and 2 more extension(s)" in line


def test_quiet_still_prints_the_unmatched_line(
    kb: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`-q` prints only problems, and a file skipped for want of a glob is one. The git hooks
    `docs/GUIDE.md` recommends run `pnk sync --quiet`, so suppressing it under `-q` would leave the
    project's own documented workflow as the single place this fix never reaches."""
    from pinakes.cli import print_sync_report

    (kb / "docs" / "report.pdf").write_bytes(b"%PDF-1.4\n")
    report = run(kb)
    capsys.readouterr()

    print_sync_report(report, quiet=True)

    captured = capsys.readouterr()
    assert "matched no `include` pattern" in captured.err
    assert "0 indexed" not in (captured.out + captured.err)  # the counts stay suppressed
