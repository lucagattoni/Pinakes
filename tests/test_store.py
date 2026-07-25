"""Storage: the schema applies, FTS tracks its content table, and mismatches refuse to open."""

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from pinakes.errors import IndexSchemaError, StoreError
from pinakes.store import (
    SCHEMA_VERSION,
    connect_ro,
    connect_rw,
    create,
    dumps_metadata,
    get_meta,
    load_vectors,
    loads_metadata,
    pack_vector,
    record_failure,
    replace_chunks,
    set_meta,
    store_embedding,
    unpack_vector,
)

DIM = 4


@pytest.fixture
def index_path(tmp_path: Path) -> Path:
    return tmp_path / ".pinakes" / "index.db"


def _document(
    connection: sqlite3.Connection, doc_id: str = "D1", *, path: str = "docs/a.md"
) -> str:
    connection.execute(
        "INSERT INTO documents (id, path, content_hash, mtime, source_type, title, metadata) "
        "VALUES (?, ?, 'h', 0.0, 'markdown', 't', '{}')",
        (doc_id, path),
    )
    return doc_id


def _chunks(connection: sqlite3.Connection, doc_id: str, *texts: str) -> list[int]:
    return replace_chunks(connection, doc_id, [(text, 0, len(text), 3, "H1") for text in texts])


def _chunk(connection: sqlite3.Connection, doc_id: str, text: str) -> int:
    return _chunks(connection, doc_id, text)[0]


def _fts_hits(connection: sqlite3.Connection, term: str) -> list[int]:
    rows = connection.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", (term,))
    return [int(row["rowid"]) for row in rows]


def test_create_builds_the_schema_and_stamps_the_version(index_path: Path) -> None:
    connection = create(index_path)
    tables = {
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"documents", "chunks", "embeddings", "links", "kb_refs", "failures", "meta"} <= tables
    assert get_meta(connection)["schema_version"] == str(SCHEMA_VERSION)
    assert str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"


def test_create_refuses_to_clobber_an_existing_index(index_path: Path) -> None:
    create(index_path).close()
    with pytest.raises(StoreError) as exc_info:
        create(index_path)
    assert "--rebuild" in exc_info.value.remedy


def test_fts_follows_inserts_updates_and_deletes(index_path: Path) -> None:
    """External-content FTS is only correct while its triggers are; this is that guarantee."""
    connection = create(index_path)
    doc = _document(connection)
    chunk_id = _chunk(connection, doc, "transformers changed retrieval")

    assert _fts_hits(connection, "transformers") == [chunk_id]

    connection.execute("UPDATE chunks SET text = 'diffusion models' WHERE id = ?", (chunk_id,))
    assert _fts_hits(connection, "transformers") == []
    assert _fts_hits(connection, "diffusion") == [chunk_id]

    connection.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))
    assert _fts_hits(connection, "diffusion") == []


def test_deleting_a_document_cascades_to_chunks_and_embeddings(index_path: Path) -> None:
    connection = create(index_path)
    doc = _document(connection)
    chunk_id = _chunk(connection, doc, "text")
    store_embedding(connection, chunk_id, np.ones(DIM, dtype=np.float32))

    connection.execute("DELETE FROM documents WHERE id = ?", (doc,))
    assert connection.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM embeddings").fetchone()[0] == 0
    assert _fts_hits(connection, "text") == []


def test_vectors_round_trip_bit_exactly(index_path: Path) -> None:
    connection = create(index_path)
    doc = _document(connection)
    chunk_id = _chunk(connection, doc, "text")
    vector = np.array([0.1, -2.5, 3.75, 1e-8], dtype=np.float32)
    store_embedding(connection, chunk_id, vector)

    stored = connection.execute("SELECT vector FROM embeddings").fetchone()["vector"]
    assert np.array_equal(unpack_vector(bytes(stored)), vector)
    assert unpack_vector(pack_vector(vector)).dtype == np.float32


def test_load_vectors_returns_one_contiguous_array_aligned_to_chunk_ids(index_path: Path) -> None:
    connection = create(index_path)
    doc = _document(connection)
    ids = _chunks(connection, doc, "chunk 0", "chunk 1", "chunk 2")
    for index, chunk_id in enumerate(ids):
        store_embedding(connection, chunk_id, np.full(DIM, index, dtype=np.float32))

    chunk_ids, matrix = load_vectors(connection, dim=DIM)
    assert chunk_ids == ids
    assert matrix.shape == (3, DIM)
    assert matrix.dtype == np.float32
    assert matrix.flags["C_CONTIGUOUS"]
    assert np.array_equal(matrix[1], np.full(DIM, 1, dtype=np.float32))


def test_load_vectors_skips_deleted_documents(index_path: Path) -> None:
    connection = create(index_path)
    live = _document(connection, "D1", path="docs/a.md")
    gone = _document(connection, "D2", path="docs/b.md")
    for doc in (live, gone):
        store_embedding(connection, _chunk(connection, doc, "t"), np.ones(DIM, dtype=np.float32))
    connection.execute("UPDATE documents SET state = 'deleted' WHERE id = ?", (gone,))

    chunk_ids, matrix = load_vectors(connection, dim=DIM)
    assert len(chunk_ids) == 1
    assert matrix.shape == (1, DIM)


def test_load_vectors_on_an_empty_index_still_has_the_right_width(index_path: Path) -> None:
    chunk_ids, matrix = load_vectors(create(index_path), dim=DIM)
    assert chunk_ids == []
    assert matrix.shape == (0, DIM)


def test_a_vector_of_the_wrong_width_is_a_hard_error(index_path: Path) -> None:
    """A silently reshaped embedding would return plausible, wrong neighbours."""
    connection = create(index_path)
    doc = _document(connection)
    store_embedding(connection, _chunk(connection, doc, "t"), np.ones(DIM + 1, dtype=np.float32))

    with pytest.raises(StoreError) as exc_info:
        load_vectors(connection, dim=DIM)
    assert "--rebuild" in exc_info.value.remedy


def test_a_read_only_connection_cannot_write(index_path: Path) -> None:
    create(index_path).close()
    connection = connect_ro(index_path)
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("INSERT INTO meta (key, value) VALUES ('x', 'y')")


def test_a_schema_version_mismatch_refuses_to_open_and_says_rebuild(index_path: Path) -> None:
    connection = create(index_path)
    set_meta(connection, {"schema_version": "999"})
    connection.commit()
    connection.close()

    for opener in (connect_rw, connect_ro):
        with pytest.raises(IndexSchemaError) as exc_info:
            opener(index_path)
        assert exc_info.value.found == "999"
        assert "pnk sync --rebuild" in exc_info.value.remedy
        assert "no migration machinery" in exc_info.value.remedy


def test_opening_a_missing_index_is_a_clear_error(index_path: Path) -> None:
    for opener in (connect_rw, connect_ro):
        with pytest.raises(StoreError) as exc_info:
            opener(index_path)
        assert "pnk sync" in exc_info.value.remedy


def test_opening_something_that_is_not_an_index(tmp_path: Path) -> None:
    stranger = tmp_path / "index.db"
    stranger.write_text("not a database")
    with pytest.raises(StoreError):
        connect_rw(stranger)


def test_foreign_keys_are_enforced(index_path: Path) -> None:
    connection = create(index_path)
    with pytest.raises(sqlite3.IntegrityError):
        replace_chunks(connection, "no-such-document", [("t", 0, 1, 1, None)])


def test_document_state_is_constrained(index_path: Path) -> None:
    connection = create(index_path)
    _document(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE documents SET state = 'maybe'")


def test_link_origin_is_constrained(index_path: Path) -> None:
    connection = create(index_path)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO links VALUES ('K', 'D', 'K2', 'D2', 'cites', 'invented')")


def test_failures_are_recorded_with_their_stage(index_path: Path) -> None:
    connection = create(index_path)
    record_failure(
        connection, path="docs/broken.pdf", stage="parse", error="boom", happened="20260725 14:30"
    )
    row = connection.execute("SELECT * FROM failures").fetchone()
    assert row["stage"] == "parse"
    assert row["path"] == "docs/broken.pdf"


def test_replacing_chunks_leaves_no_orphans_behind(index_path: Path) -> None:
    """Re-chunking a changed document must not leave the old text searchable."""
    connection = create(index_path)
    doc = _document(connection)
    _chunks(connection, doc, "alpha text", "beta text")
    store_embedding(connection, _chunks(connection, doc, "gamma text")[0], np.ones(DIM, np.float32))

    assert _fts_hits(connection, "alpha") == []
    assert len(_fts_hits(connection, "gamma")) == 1
    assert connection.execute("SELECT count(*) FROM chunks").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM embeddings").fetchone()[0] == 1


def test_constants_match_the_check_constraints(index_path: Path) -> None:
    """The DDL enforces these; the constants are what the code reads. They must not drift."""
    from pinakes.store import DOCUMENT_STATES, LINK_ORIGINS, SCHEMA

    for state in DOCUMENT_STATES:
        assert f"'{state}'" in SCHEMA
    for origin in LINK_ORIGINS:
        assert f"'{origin}'" in SCHEMA


def test_loading_vectors_does_not_double_the_peak(index_path: Path) -> None:
    """The array is allocated once and filled, not built from a list and copied."""
    import tracemalloc

    connection = create(index_path)
    doc = _document(connection)
    wide = 256
    ids = replace_chunks(connection, doc, [(f"c{n}", 0, 1, 1, None) for n in range(2000)])
    for chunk_id in ids:
        store_embedding(connection, chunk_id, np.ones(wide, dtype=np.float32))

    tracemalloc.start()
    _, matrix = load_vectors(connection, dim=wide)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    assert matrix.nbytes == 2000 * wide * 4
    assert peak < matrix.nbytes * 1.6


def test_metadata_json_round_trips_and_tolerates_rubbish() -> None:
    assert loads_metadata(dumps_metadata({"tags": ["a", "b"]})) == {"tags": ["a", "b"]}
    assert loads_metadata("[1, 2]") == {}


def test_meta_upserts_rather_than_duplicating(index_path: Path) -> None:
    connection = create(index_path)
    set_meta(connection, {"build_id": "one"})
    set_meta(connection, {"build_id": "two"})
    assert get_meta(connection)["build_id"] == "two"
