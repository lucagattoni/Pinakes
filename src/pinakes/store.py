"""`.pinakes/index.db` — the derived state, and the only thing in a KB that is disposable.

One SQLite file in WAL mode holds documents, chunks, the FTS5 lexical index, vectors, links and the
failure log (docs/DESIGN.md §3). There are **no migrations, by design**: on a `schema_version`
mismatch the index refuses to open and instructs a rebuild. Because `docs/` and `pinakes.toml` are
the truth and a rebuild is free, migration code would be pure liability.

Two connection modes, because a git hook can fire while an MCP server is answering (§6.5):

* `connect_rw` — WAL, foreign keys on. One writer, guarded by the sync lock (I8b).
* `connect_ro` — `mode=ro`, so the server physically cannot write, plus a `busy_timeout`.

Vectors are float32 BLOBs in a single `embeddings` table — one representation, not two. The NumPy
tier loads them into one contiguous array at open (§3.1); `load_vectors` is that loader, and it
returns the chunk ids in the same row order so a matrix index can be turned back into a chunk.
"""

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final, cast

import numpy as np

from pinakes.errors import IndexSchemaError, StoreError

SCHEMA_VERSION: Final = 1
BUSY_TIMEOUT_MS: Final = 5_000
VECTOR_DTYPE: Final = np.float32

# Mirrored by CHECK constraints in SCHEMA below; `test_constants_match_the_check_constraints`
# fails if the two ever drift.
DOCUMENT_STATES: Final = ("active", "deleted")
LINK_ORIGINS: Final = ("sidecar", "reverse-scan")

SCHEMA: Final = """
CREATE TABLE documents (
    id            TEXT PRIMARY KEY,
    path          TEXT NOT NULL UNIQUE,        -- KB-root-relative, POSIX separators
    content_hash  TEXT NOT NULL,
    sidecar_hash  TEXT,                        -- lets §6.4 notice a sidecar-only edit
    mtime         REAL NOT NULL,
    source_type   TEXT NOT NULL,
    title         TEXT,
    metadata      TEXT NOT NULL DEFAULT '{}',  -- JSON: tags, provenance, user keys
    state         TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'deleted'))
);

CREATE INDEX documents_state ON documents (state);
CREATE INDEX documents_hash ON documents (content_hash);

-- INTEGER PRIMARY KEY, not a ULID: a chunk has no identity across rebuilds, and FTS5's
-- external-content mapping needs a rowid it can align to.
CREATE TABLE chunks (
    id           INTEGER PRIMARY KEY,
    doc_id       TEXT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    ordinal      INTEGER NOT NULL,
    text         TEXT NOT NULL,
    char_start   INTEGER NOT NULL,
    char_end     INTEGER NOT NULL,
    token_count  INTEGER NOT NULL,
    heading_path TEXT,
    UNIQUE (doc_id, ordinal)
);

CREATE INDEX chunks_doc ON chunks (doc_id);

CREATE VIRTUAL TABLE chunks_fts USING fts5 (
    text,
    content='chunks',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts (rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO chunks_fts (rowid, text) VALUES (new.id, new.text);
END;

CREATE TABLE embeddings (
    chunk_id INTEGER PRIMARY KEY REFERENCES chunks (id) ON DELETE CASCADE,
    vector   BLOB NOT NULL
);

-- src_kb_id is required: a reverse link's source lives in another KB, and without it an inbound
-- edge is indistinguishable from an outbound one (§3).
CREATE TABLE links (
    src_kb_id  TEXT NOT NULL,
    src_doc_id TEXT NOT NULL,
    dst_kb_id  TEXT NOT NULL,
    dst_doc_id TEXT NOT NULL,
    rel        TEXT NOT NULL,
    origin     TEXT NOT NULL CHECK (origin IN ('sidecar', 'reverse-scan')),
    PRIMARY KEY (src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel)
);

CREATE INDEX links_dst ON links (dst_kb_id, dst_doc_id);

CREATE TABLE kb_refs (
    kb_id     TEXT PRIMARY KEY,
    alias     TEXT,
    path      TEXT,
    last_scan TEXT
);

CREATE TABLE failures (
    id       INTEGER PRIMARY KEY,
    path     TEXT NOT NULL,
    stage    TEXT NOT NULL,
    error    TEXT NOT NULL,
    happened TEXT NOT NULL
);

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _configure(connection: sqlite3.Connection, *, writable: bool) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys = ON")
    if writable:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")


def create(path: Path) -> sqlite3.Connection:
    """Create a fresh index. Fails if one already exists — replacing it is `--rebuild`'s job."""
    if path.exists():
        raise StoreError(
            f"{path} already exists.",
            remedy="Rebuild with `pnk sync --rebuild`, which swaps a new index in atomically.",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    _configure(connection, writable=True)
    connection.executescript(SCHEMA)
    set_meta(connection, {"schema_version": str(SCHEMA_VERSION)})
    connection.commit()
    return connection


def _open(path: Path, *, writable: bool) -> sqlite3.Connection:
    """Open an existing index, turning sqlite's own errors into ones that carry a remedy.

    `PRAGMA journal_mode` is the first statement to touch the file, so a non-database file fails
    *there* — before any version check could run. Without this wrapper the user gets
    `sqlite3.DatabaseError: file is not a database` and no idea what to do about it.
    """
    if not path.exists():
        raise StoreError(f"no index at {path}.", remedy="Build one with `pnk sync`.")
    target = str(path) if writable else f"file:{path}?mode=ro"
    connection = sqlite3.connect(target, uri=not writable)
    try:
        _configure(connection, writable=writable)
        _check_schema_version(connection, path)
    except sqlite3.DatabaseError as exc:
        connection.close()
        raise StoreError(
            f"{path} is not a usable pinakes index ({exc}).",
            remedy="Delete it and run `pnk sync --rebuild` — the index is always regenerable.",
        ) from exc
    except Exception:
        connection.close()
        raise
    return connection


def connect_rw(path: Path) -> sqlite3.Connection:
    return _open(path, writable=True)


def connect_ro(path: Path) -> sqlite3.Connection:
    """Open read-only. The MCP server uses this: it cannot write even by mistake (§6.5)."""
    return _open(path, writable=False)


def _check_schema_version(connection: sqlite3.Connection, path: Path) -> None:
    try:
        found = get_meta(connection).get("schema_version")
    except sqlite3.DatabaseError as exc:
        raise StoreError(
            f"{path} is not a pinakes index ({exc}).",
            remedy="Delete it and run `pnk sync --rebuild`.",
        ) from exc
    if found != str(SCHEMA_VERSION):
        raise IndexSchemaError(path, found=found, expected=SCHEMA_VERSION)


def set_meta(connection: sqlite3.Connection, values: dict[str, str]) -> None:
    connection.executemany(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        sorted(values.items()),
    )


def get_meta(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row["key"]): str(row["value"])
        for row in connection.execute("SELECT key, value FROM meta")
    }


def active_content_hashes(connection: sqlite3.Connection) -> set[str]:
    """Every `content_hash` an active (non-deleted) document currently claims — what the
    extraction cache's eviction sweep and `pnk doctor`'s report both call "still in use"."""
    return {
        str(row["content_hash"])
        for row in connection.execute("SELECT content_hash FROM documents WHERE state = 'active'")
    }


def pack_vector(vector: "np.ndarray[Any, np.dtype[np.float32]]") -> bytes:
    """Serialise one embedding: float32 throughout, so storage and maths agree by construction."""
    return np.ascontiguousarray(vector, dtype=VECTOR_DTYPE).tobytes()


def unpack_vector(blob: bytes) -> "np.ndarray[Any, np.dtype[np.float32]]":
    return np.frombuffer(blob, dtype=VECTOR_DTYPE)


def store_embedding(
    connection: sqlite3.Connection,
    chunk_id: int,
    vector: "np.ndarray[Any, np.dtype[np.float32]]",
) -> None:
    connection.execute(
        "INSERT INTO embeddings (chunk_id, vector) VALUES (?, ?) "
        "ON CONFLICT (chunk_id) DO UPDATE SET vector = excluded.vector",
        (chunk_id, pack_vector(vector)),
    )


def load_vectors(
    connection: sqlite3.Connection, *, dim: int, active_only: bool = True
) -> tuple[list[int], "np.ndarray[Any, np.dtype[np.float32]]"]:
    """Load every embedding into one contiguous array — the NumPy tier's substrate (§3.1).

    Returns chunk ids in the array's row order, so a row index maps straight back to a chunk. A
    stored vector whose width disagrees with the manifest is a hard error: a silently reshaped or
    truncated embedding would return plausible, wrong neighbours.
    """
    source = (
        "FROM embeddings e JOIN chunks c ON c.id = e.chunk_id JOIN documents d ON d.id = c.doc_id "
    )
    where = "WHERE d.state = 'active' " if active_only else ""

    # Count first and fill a preallocated array. Collecting rows into a list and vstacking them
    # peaks at roughly twice the final size — 669 MB measured for 200k x 384, which at 1M chunks
    # would be ~3.4 GB against the ~1.5 GB §3.1 promises.
    expected = int(connection.execute(f"SELECT count(*) {source}{where}").fetchone()[0])
    matrix = np.empty((expected, dim), dtype=VECTOR_DTYPE)

    chunk_ids: list[int] = []
    rows = connection.execute(
        f"SELECT e.chunk_id AS chunk_id, e.vector AS vector {source}{where}ORDER BY e.chunk_id"
    )
    for row in rows:
        vector = unpack_vector(bytes(row["vector"]))
        if vector.shape[0] != dim:
            raise StoreError(
                f"chunk {row['chunk_id']} has a {vector.shape[0]}-dimensional embedding, "
                f"but the manifest says {dim}.",
                remedy="The index was built with a different model. Run `pnk sync --rebuild`.",
            )
        if len(chunk_ids) == expected:  # pragma: no cover — single writer holds the sync lock
            raise StoreError(
                "the index grew while it was being read.",
                remedy="Re-run the command; `pnk sync` holds a lock so this should not recur.",
            )
        matrix[len(chunk_ids)] = vector
        chunk_ids.append(int(row["chunk_id"]))

    return chunk_ids, matrix[: len(chunk_ids)]


def record_failure(
    connection: sqlite3.Connection, *, path: str, stage: str, error: str, happened: str
) -> None:
    connection.execute(
        "INSERT INTO failures (path, stage, error, happened) VALUES (?, ?, ?, ?)",
        (path, stage, error, happened),
    )


def dumps_metadata(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, sort_keys=True, ensure_ascii=False)


def loads_metadata(raw: str) -> dict[str, Any]:
    parsed: object = json.loads(raw)
    if not isinstance(parsed, dict):
        return {}
    return cast(dict[str, Any], parsed)


type ChunkRow = tuple[str, int, int, int, str | None]
"""(text, char_start, char_end, token_count, heading_path) — typed so a misordered field fails."""


def replace_chunks(
    connection: sqlite3.Connection, doc_id: str, chunks: Iterable[ChunkRow]
) -> list[int]:
    """Replace a document's chunks wholesale, returning the new rowids in order.

    Replacement, not append: re-chunking a changed document must not leave the old chunks behind,
    and ordinals are positions within the document, so they always start at 0. Deleting first also
    keeps the FTS index and embeddings correct — both follow `chunks` by trigger and cascade.
    """
    connection.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    ids: list[int] = []
    for ordinal, chunk in enumerate(chunks):
        cursor = connection.execute(
            "INSERT INTO chunks (doc_id, ordinal, text, char_start, char_end, token_count, "
            "heading_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, ordinal, *chunk),
        )
        ids.append(int(cursor.lastrowid or 0))
    return ids
