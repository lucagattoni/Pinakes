"""G3's exit criterion: the authored-links surface is byte-identical across the schema bump.

Decision 16 makes the structural graph internal to the expansion channel: `pnk links` and
`pinakes_links` serve **document** neighbours read from the `links` table, and never a chunk, tag,
heading or directory node. "Inert" is the claim; this file is what makes it a measurement.

**Why a committed fixture and not a before/after run.** `schema_version` goes to 3 in this
increment and there are no migrations, so after the bump there is no pre-G3 index left to compare
against and no binary that can read one. The comparison is only executable against a stored
artifact, captured at G2's HEAD (`74f32f5`) and committed here.

**Why a fake embedding backend.** `pnk links` without `--query` loads no model at all — the payload
is a function of `links`, `documents.title` and the traversal core, none of which touch a vector.
So the fixture is deterministic, needs no weights, and runs on every CI leg including `[light]`.
Capturing it against a real backend would have measured the same bytes at the cost of a download.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pinakes import store
from pinakes.embed import EmbeddingBackend, ModelInfo, Vectors
from pinakes.graph.traverse import MAX_DEPTH
from pinakes.manifest import Manifest, load
from pinakes.sync import SyncOptions, sync

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "links-surface-at-g2.json"
CORPORA = ("demo-kb", "partner-kb")


class _FakeBackend:
    """Deterministic and instant. The surface under test never reads a vector."""

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> Vectors:
        listed = list(texts)
        if not listed:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.ascontiguousarray(
            np.vstack(
                [np.full(self.dim, (len(text) % 7) / 7.0, dtype=np.float32) for text in listed]
            ),
            dtype=np.float32,
        )

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", "rev1", self.dim, 512)


def _factory(manifest: Manifest, _offline: bool) -> EmbeddingBackend:
    return _FakeBackend(manifest.embedding.dim)


def _links_payload(root: Path, document: str) -> dict[str, Any]:
    from pinakes.cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(["links", document, "--kb", str(root), "--json", "--depth", str(MAX_DEPTH)])
    assert code == 0, buffer.getvalue()
    parsed: dict[str, Any] = json.loads(buffer.getvalue())
    return parsed


def capture(workspace: Path, *, mutate: Callable[[Path], None] | None = None) -> dict[str, Any]:
    """`pnk links --json` for every active document of both committed corpora.

    Both are copied into one directory so `[[links.kb]] path = "../partner-kb"` still resolves,
    and both are scanned, so the reverse-scanned rows — the ones keyed on a *foreign* document —
    are in the payload too.

    `mutate` runs on each **copied** root before it is synced, and exists for one caller:
    `tests/test_graph_channel.py` turns `[retrieval] graph_channel` on and re-captures, because
    decision 16's claim is that this same fixture still compares equal (G5). Nothing it does can
    reach the committed corpora, which is what keeps every other suite measuring the two-list
    pipeline.
    """
    for name in CORPORA:
        shutil.copytree(REPO / "tests" / name, workspace / name)
        if mutate is not None:
            mutate(workspace / name)

    surface: dict[str, Any] = {}
    for name in CORPORA:
        root = workspace / name
        sync(load(root), options=SyncOptions(scan_links=True), backend_factory=_factory)

    for name in CORPORA:
        root = workspace / name
        connection = store.connect_ro(load(root).index_path)
        try:
            paths = _active_paths(connection)
        finally:
            connection.close()
        surface[name] = {path: _links_payload(root, path) for path in paths}
    return surface


def _active_paths(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT path FROM documents WHERE state = 'active' ORDER BY path"
        )
    ]


def test_the_authored_links_surface_is_unchanged_by_the_schema_bump(tmp_path: Path) -> None:
    """G3's exit criterion, executed rather than asserted.

    A structural node reaching this surface, a changed neighbour ordering, a lost `terminal` flag
    or a new key in the payload all fail here — the fixture is compared whole, not field by field.
    """
    assert FIXTURE.is_file(), f"{FIXTURE} is missing; it is the only pre-G3 artifact that exists"
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert capture(tmp_path) == expected, (
        "`pnk links --json` moved across the schema bump. G3 is inert on this surface by "
        "decision 16: the structural graph is read only by the expansion channel."
    )


def test_the_fixture_covers_both_corpora_and_holds_real_neighbours(tmp_path: Path) -> None:
    """A fixture of empty payloads would make the comparison above vacuously green — this
    project's recurring defect, an assertion satisfied by something other than what it names."""
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(expected) == set(CORPORA)
    for name in CORPORA:
        assert len(expected[name]) > 15, f"{name} has too few documents to be the committed corpus"
    with_neighbours = [
        path
        for name in CORPORA
        for path, payload in expected[name].items()
        if payload["neighbours"]
    ]
    assert len(with_neighbours) >= 10, (
        f"only {len(with_neighbours)} documents have a neighbour; the fixture cannot detect a "
        "surface that stopped returning them"
    )
    terminal = [
        row
        for name in CORPORA
        for payload in expected[name].values()
        for row in payload["neighbours"]
        if row["terminal"]
    ]
    assert terminal, "no cross-KB neighbour in the fixture — the reverse scan did not run"
