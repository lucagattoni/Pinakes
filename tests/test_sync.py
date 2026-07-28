"""`pnk sync` end to end, against a real index and a fake backend."""

import subprocess
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest
import yaml

from pinakes import store
from pinakes.embed import EmbeddingBackend, ModelInfo, Vectors
from pinakes.errors import DuplicateIdsError
from pinakes.ids import mint_doc_id
from pinakes.manifest import Manifest, load
from pinakes.sidecar import SIDECAR_SUFFIX
from pinakes.sync import SyncOptions, SyncReport, sync

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
