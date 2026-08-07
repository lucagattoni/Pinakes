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
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Final, cast

import numpy as np

from pinakes.errors import IndexSchemaError, StoreError

SCHEMA_VERSION: Final = 3
BUSY_TIMEOUT_MS: Final = 5_000
VECTOR_DTYPE: Final = np.float32

# Mirrored by CHECK constraints in SCHEMA below; `test_constants_match_the_check_constraints`
# fails if the two ever drift.
DOCUMENT_STATES: Final = ("active", "deleted")
LINK_ORIGINS: Final = ("sidecar", "reverse-scan")
NODE_KINDS: Final = ("doc", "chunk", "tag", "heading", "dir")
STRUCTURAL_EDGE_KINDS: Final = (
    "membership",
    "sibling",
    "parent-child",
    "in-section",
    "co-located",
    "shared-tag",
)
"""The six kinds `edges` stores (G3). `authored` is deliberately absent: it is resolved from
`links` at read time, so an authored link keeps exactly one home — see `pinakes.graph.edges`."""

SCHEMA: Final = """
CREATE TABLE documents (
    id                     TEXT PRIMARY KEY,
    path                   TEXT NOT NULL UNIQUE,        -- KB-root-relative, POSIX separators
    content_hash           TEXT NOT NULL,
    sidecar_hash           TEXT,                        -- lets §6.4 notice a sidecar-only edit
    mtime                  REAL NOT NULL,
    source_type            TEXT NOT NULL,
    title                  TEXT,
    metadata               TEXT NOT NULL DEFAULT '{}',  -- JSON: tags, provenance, user keys
    state                  TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'deleted')),
    -- NULL for a non-extracted source (markdown/text/code). The index's own *cache* of the
    -- sidecar's `provenance.extraction` (I5) — reseeded from there on a rebuild, since this row
    -- does not survive one. §4.4 re-derives each backend's current fingerprint and compares.
    extraction_backend     TEXT,
    extraction_fingerprint TEXT
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
    page_start   INTEGER,  -- 1-indexed, NULL for a non-paged source (I5)
    page_end     INTEGER,  -- >= page_start; a chunk may legitimately span two pages
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

-- G3's node model (docs/graph/PINAKES_APPROACH.md §3). Five node kinds span incompatible id
-- spaces, so identity is `(kind, key)` and `id` is a surrogate minted here. The keys are what
-- carry meaning across a rebuild:
--
--   doc      the document ULID
--   chunk    `<doc-ulid>:<ordinal>` — **never** `chunks.id`, which this file's own comment says
--            has no identity across rebuilds
--   tag      the tag string
--   heading  `<doc-ulid>:<heading_path>` — scoped per document, so no global "Introduction" hub
--            can weld every document into one noise clique
--   dir      the KB-root-relative directory path
CREATE TABLE nodes (
    id   INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('doc', 'chunk', 'tag', 'heading', 'dir')),
    key  TEXT NOT NULL,
    UNIQUE (kind, key)
);

-- One row per edge, never two. A hub spoke always carries the hub as `src`, which is what makes
-- the read-time damping divisor — `count(*) WHERE src = ? AND kind = ?` — well defined. The
-- symmetric kinds are stored once too, under an explicit orientation rule: `sibling`
-- lower→higher ordinal, `parent-child` parent→child, `membership` doc→chunk. Readers query
-- `src = ? OR dst = ?` for those; a `src`-only query would silently drop half of every one.
--
-- `authored` is not here. It lives in `links`, and the channel resolves both of its ends to `doc`
-- nodes at read time.
CREATE TABLE edges (
    src  INTEGER NOT NULL REFERENCES nodes (id) ON DELETE CASCADE,
    dst  INTEGER NOT NULL REFERENCES nodes (id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN (
        'membership', 'sibling', 'parent-child', 'in-section', 'co-located', 'shared-tag'
    )),
    PRIMARY KEY (src, dst, kind)
);

-- Indexed on **both** ends, and on `kind` with each: the divisor reads `(src, kind)`, a member
-- finds its hubs through `(dst, kind)`, and a symmetric walk needs both halves to be lookups
-- rather than scans. No stored `degree` column — that would be derived state inside derived
-- state, and it is one `count(*)` on an indexed column.
CREATE INDEX edges_src ON edges (src, kind);
CREATE INDEX edges_dst ON edges (dst, kind);
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


def chunking_identity(
    *, headings: str, max_tokens: int, overlap: int, metadata: str
) -> dict[str, str]:
    """The `[chunking]` settings an index was built under, as `meta` keys.

    Recorded because an incremental sync re-chunks a document only when *the document* changed, so
    a manifest-only edit leaves every content hash intact, reports `unchanged`, and does nothing —
    measured 20260805 on `headings`, and true of `max_tokens` and `overlap` since v0.1. Without
    this, the tool cannot tell the user what it just failed to do.

    `metadata` is here for a sharper version of the same reason: it changes what is *embedded*
    rather than what is chunked, so flipping it leaves every chunk's text, hash and offsets
    identical and an incremental sync has nothing to notice at all. Without this key the user
    searches uninjected vectors with every command reporting success.

    Deliberately plain values rather than a hash: the point is to name *which* key moved and to
    what, and a fingerprint can only say "something".
    """
    return {
        "chunking_headings": headings,
        "chunking_max_tokens": str(max_tokens),
        "chunking_overlap": str(overlap),
        "chunking_metadata": metadata,
    }


ABSENT_MEANS: dict[str, str] = {"chunking_metadata": "off"}
"""Identity keys whose **absence is known**, not unknown — the exception to `chunking_drift`'s rule.

`chunking_max_tokens` and `chunking_overlap` have been settable since v0.1, so an index that does
not record them could genuinely have been built under any value: absence there is ignorance, and
reporting it as drift would demand a rebuild of every KB on upgrade. `chunking_metadata` is not
like that. **No release that could have written any existing index was able to inject anything** —
the option arrives with this one — so absence proves the value was `off`.

Reading it as `off` therefore fires only for a user who has explicitly set `metadata = "prefix"`,
which is exactly the case where a rebuild really is required, and never for anyone left on the
default. Without it the whole `[chunking]`-over-`[retrieval]` argument in `manifest.CHUNK_METADATA`
is false for every KB in existence on the day this ships: the flip would be silent, nothing would
re-embed, and `pnk doctor` would print `OK  chunking coherence: index matches the configured
chunking` over vectors with no prefix in them.
"""


def chunking_drift(meta: dict[str, str], expected: dict[str, str]) -> dict[str, tuple[str, str]]:
    """`{key: (built_with, configured_now)}` for every key that is **recorded and different**.

    **A key absent from `meta` is unknown, never drifted — except for the keys in `ABSENT_MEANS`,
    whose absence is *known*. That is the whole compatibility story.** Every index built before
    this existed has none of these keys; reading absence as a mismatch would demand a full rebuild
    of every KB on upgrade — a cost nobody agreed to, for a setting that probably never changed. It
    also keeps the check forward-compatible: a *future* key is absent from today's indexes for the
    same reason and must not fire either. `ABSENT_MEANS` is the narrow exception, and it earns its
    place only where no release could have written a different value.

    That is the opposite reading from `search.check_coherence`, and deliberately so. There, a
    partial `meta` means an interrupted sync and must not be waved through. Here, absence carries
    no such signal — nothing is being protected from, only reported on.
    """
    known = ABSENT_MEANS | meta
    return {
        key: (known[key], value)
        for key, value in expected.items()
        if key in known and known[key] != value
    }


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

    **Ordered by `(documents.path, chunks.ordinal)`, never by `chunks.id`** (G1). This row order is
    what breaks ties in the caller's `argsort`, so it decides which of two equally-similar chunks is
    retrieved — and `chunks.id` is the rowid, which this module's own schema comment says has no
    identity across rebuilds. Measured 20260801: an incremental sync appends a re-chunked
    document's rows at the end while a `--rebuild` writes them in walk order, and one golden-set
    question in 41 retrieved a different document as a result. `(path, ordinal)` survives both —
    `documents.path` is `UNIQUE` and an ordinal is a position inside a document.
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
        f"SELECT e.chunk_id AS chunk_id, e.vector AS vector {source}{where}"
        "ORDER BY d.path, c.ordinal"
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


type ChunkRow = tuple[str, int, int, int, str | None, int | None, int | None]
"""(text, char_start, char_end, token_count, heading_path, page_start, page_end) — typed so a
misordered field fails. The last two are always `None` for a non-paged source (I5)."""


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
            "heading_path, page_start, page_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, ordinal, *chunk),
        )
        ids.append(int(cursor.lastrowid or 0))
    return ids


def read_kb_refs(connection: sqlite3.Connection) -> dict[str, str]:
    """`kb_id -> last_scan` for every linked KB this index has scanned (§3, §6.2)."""
    return {
        str(row["kb_id"]): str(row["last_scan"] or "")
        for row in connection.execute("SELECT kb_id, last_scan FROM kb_refs")
    }


def replace_reverse_links(
    connection: sqlite3.Connection,
    *,
    src_kb_id: str,
    rows: Sequence[tuple[str, str, str, str]],
) -> int:
    """Replace one partner's inbound rows: `(src_doc_id, dst_kb_id, dst_doc_id, rel)` each.

    **Scoped by `src_kb_id` *and* `origin`, and both matter.** Under a manifest that lists itself
    as a `[[links.kb]]` — which nothing forbids, and which is the only way an authored row and a
    reverse row can ever collide — the scanned `src_kb_id` *is* the local KB, so an origin-blind
    delete would take out exactly the authored rows the insert below is written to protect.

    `ON CONFLICT DO NOTHING`, because `origin` is not in the primary key: a plain
    `INSERT OR REPLACE` would flip a colliding authored row's origin to `reverse-scan` and drop it
    out of the authored-only population `pnk doctor` and the density gate both count.

    The caller runs this **only for a partner whose walk completed** — the delete is unconditional
    within its scope, so a half-read partner would lose edges that are still true.
    """
    connection.execute(
        "DELETE FROM links WHERE src_kb_id = ? AND origin = 'reverse-scan'", (src_kb_id,)
    )
    written = 0
    for src_doc_id, dst_kb_id, dst_doc_id, rel in rows:
        cursor = connection.execute(
            "INSERT INTO links VALUES (?, ?, ?, ?, ?, 'reverse-scan') ON CONFLICT DO NOTHING",
            (src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel),
        )
        written += cursor.rowcount or 0
    # The count of rows *written*, not rows read: a duplicate entry in one sidecar, or (under a
    # self-listing manifest) a collision with an authored row, is dropped by DO NOTHING — so the
    # two numbers differ exactly when something interesting happened, and reporting the larger one
    # would overstate what is in the table.
    return written


def forget_reverse_links(connection: sqlite3.Connection, *, keep: Sequence[str]) -> int:
    """Drop inbound rows (and `kb_refs`) for every KB not in `keep`. Returns rows removed.

    Nothing else would ever remove them: `replace_reverse_links` is scoped to the KB being scanned,
    and a KB dropped from `[[links.kb]]` is never scanned again. Without this, disconnecting a
    partner — or correcting a mistyped `[[links.kb]] id` — left its edges being served indefinitely.
    """
    placeholders = ",".join("?" for _ in keep)
    predicate = f"src_kb_id NOT IN ({placeholders})" if keep else "1"
    cursor = connection.execute(
        f"DELETE FROM links WHERE origin = 'reverse-scan' AND {predicate}", tuple(keep)
    )
    removed = cursor.rowcount or 0
    ref_predicate = f"kb_id NOT IN ({placeholders})" if keep else "1"
    connection.execute(f"DELETE FROM kb_refs WHERE {ref_predicate}", tuple(keep))
    return removed


def record_kb_ref(
    connection: sqlite3.Connection, *, kb_id: str, alias: str, path: str, last_scan: str
) -> None:
    """What was scanned, where it was found, and when (§3's four columns, finally written)."""
    connection.execute(
        "INSERT INTO kb_refs (kb_id, alias, path, last_scan) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(kb_id) DO UPDATE SET alias = excluded.alias, path = excluded.path, "
        "last_scan = excluded.last_scan",
        (kb_id, alias, path, last_scan),
    )
