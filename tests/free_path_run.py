"""The whole free path in one process, then a record of everything it imported.

Gate 4 of plans/v0.2.md I7a. `tests/test_paid_path.py` runs this as a **fresh subprocess** and
asserts no paid-API client appears in the `sys.modules` it writes out. In-process the check would
be defeated by any earlier test's import — the same shape as v0.1's `-wal` test, which was correct
and then quietly defeated by an environmental fact.

Deliberately *not* named `test_*`: pytest must not collect it. It is a script, run through
`runpy` so the caller can inject a prelude (that is how gate 4's negative test plants an
`import anthropic` and proves the checker fails).

    python tests/free_path_run.py <modules.json>

The run covers every free surface the design has: `pnk init`, `pnk sync`, `pnk search`,
`pnk links`,
`pnk doctor`, and an MCP handshake — through `cli.main`, so CLI dispatch is in the graph too, not
only the libraries beneath it.

**Two KBs, and the second is the point.** The first is an ordinary free KB. The second is
configured for `claude-vision` and gets a `pnk doctor`, because that is the combination where the
paid client used to be imported: doctor reported a backend's availability by *loading* it, and the
registry's factory imports the client. A gate-4 run against a free-only KB would never touch that
path and would pass whether or not the leak existed — a gate observed passing for the wrong reason.
`pnk sync` runs against it too, with an unmatched `.pdf` present, which is where `sync`'s own
skipped-file hint made the identical probe.

Nothing here can spend: `claude-vision` is configured, never invoked. No document in either KB is a
PDF that any extractor is asked to read.
"""

import io
import json
import sys
from collections.abc import Sequence
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from pinakes.cli import main
from pinakes.embed import ModelInfo, Vectors, register_embedding_backend, register_reranker
from pinakes.extract import CLAUDE_VISION
from pinakes.manifest import load

DIM = 3
VOCABULARY = ("retrieval", "ranking", "sourdough")


class FakeBackend:
    """Instant and weightless — gate 4 is about the import graph, never about retrieval quality.

    A real backend would make this gate depend on cached model weights, so it would skip on a cold
    checkout: the flagship safety check, silently not running.
    """

    def embed(self, texts: Sequence[str]) -> Vectors:
        rows = [
            np.array([1.0 if w in t.lower() else 0.0 for w in VOCABULARY], dtype=np.float32)
            for t in texts
        ]
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


def _replace_once(text: str, old: str, new: str) -> str:
    """`str.replace`, but a substitution that matched nothing is a hard error.

    Written after this script's first version silently failed exactly that way: it "configured"
    the paid KB with `text.replace('backend = "pypdfium2"', ...)` against a template that has no
    `[extraction]` section at all, so the KB stayed on the free backend and gate 4 passed while
    never once exercising the paid-availability probe it exists to guard. A no-op `str.replace`
    returns the string unchanged and reports nothing — which is how a gate ends up observed
    passing for the wrong reason.
    """
    if old not in text:
        raise SystemExit(f"free-path run: manifest rewrite matched nothing: {old!r}")
    return text.replace(old, new)


def _point_at_the_fake_backend(manifest_path: Path, *, backend: str) -> None:
    """Rewrite a freshly `init`ed manifest onto the in-process fakes and a chosen extractor.

    `pnk init` stamps sentence-transformers (docs/RETROSPECTIVES.md, 20260727 15:35), which this
    process has no intention of downloading. It stamps no `[extraction]` section whatsoever, so
    the backend is *appended* rather than replaced — `manifest.extraction.backend` otherwise falls
    back to its `pypdfium2` default.
    """
    text = manifest_path.read_text(encoding="utf-8")
    text = _replace_once(text, 'provider = "sentence-transformers"', 'provider = "fake"')
    text = _replace_once(text, 'model    = "BAAI/bge-small-en-v1.5"', 'model    = "fake-model"')
    text = _replace_once(text, "dim      = 384", f"dim      = {DIM}")
    text = _replace_once(text, 'model    = "BAAI/bge-reranker-base"', 'model    = "fake-reranker"')
    if "[extraction]" in text:
        raise SystemExit("free-path run: the template grew an [extraction] section; append below")
    text += f'\n[extraction]\nbackend = "{backend}"\nmodel   = "claude-opus-5"\n'
    manifest_path.write_text(text, encoding="utf-8")


def _build(root: Path, *, backend: str) -> Path:
    if main(["init", str(root)]) != 0:
        raise SystemExit(f"free-path run: `pnk init {root}` failed")
    _point_at_the_fake_backend(root / "pinakes.toml", backend=backend)

    # Read the manifest back through the real loader and check it says what we meant. The whole
    # value of the paid KB is that `extraction.backend` really is `claude-vision`; the first
    # version of this script "configured" it with a `str.replace` that matched nothing, so the KB
    # silently stayed free and the gate exercised none of the probes it exists to guard.
    # A rewrite this load-bearing gets checked against the parser, not against its own intent.
    configured = load(root).extraction.backend
    if configured != backend:
        raise SystemExit(
            f"free-path run: asked for backend {backend!r}, manifest loads as {configured!r}"
        )

    (root / "docs" / "a.md").write_text(
        "# Retrieval\n\nHybrid retrieval fuses lexical and dense candidates.\n", encoding="utf-8"
    )
    return root


def _run_free_surfaces(root: Path) -> None:
    """Every free command, in the order a user meets them.

    `sync` and `search` must succeed, and the index must exist afterwards — a run that failed at
    the first command would import almost nothing and satisfy "no paid client" for the emptiest of
    reasons. `doctor`'s exit code is deliberately **not** asserted: it legitimately returns non-zero
    on a WARN (an unpinned revision, a missing extra), and gate 4's claim is about the import graph,
    never about the health of a throwaway KB.
    """
    if main(["sync", "--kb", str(root)]) != 0:
        raise SystemExit(f"free-path run: `pnk sync` failed on {root}")
    if not (root / ".pinakes" / "index.db").is_file():
        raise SystemExit(f"free-path run: `pnk sync` wrote no index under {root}")
    if main(["search", "retrieval", "--kb", str(root)]) != 0:
        raise SystemExit(f"free-path run: `pnk search` failed on {root}")
    # `pnk budget` reads the spend ledger and the price table (I6b). It can never spend — which is
    # exactly why it belongs here: a money-shaped command is the most plausible future home for an
    # accidental paid import, and it is on the free path by definition.
    if main(["budget", "--kb", str(root)]) != 0:
        raise SystemExit(f"free-path run: `pnk budget` failed on {root}")
    # `pnk links` walks the link graph — no models, no extractor, and nothing that could spend.
    # It is here because gate 4 asserts a *property of the import graph*, and a surface left out
    # of the run is a surface the property was never checked on.
    if main(["links", "docs/a.md", "--kb", str(root)]) != 0:
        raise SystemExit(f"free-path run: `pnk links` failed on {root}")
    main(["doctor", "--kb", str(root)])


def _mcp_handshake(root: Path) -> None:
    """Build the MCP server, list its tools, and **call** one — `pnk serve`'s import graph.

    Listing alone was never enough: `list_tools` walks signatures and docstrings, so a tool whose
    *body* imports a paid client would list perfectly and never be seen by this gate. Calling one
    is what makes the import graph include what the tool actually does.

    `pinakes_links` is the one called because it is the newest, and because a traversal touches the
    graph core and its provider — territory the gate had no coverage of at all before L3 and L4.
    """
    import asyncio

    from pinakes.graph import provider as provider_module
    from pinakes.serve import build

    mcp, server = build([root])
    try:
        tools = asyncio.run(mcp.list_tools())
        if not tools:
            raise SystemExit("free-path run: the MCP server listed no tools")
        if "pinakes_links" not in {tool.name for tool in tools}:
            raise SystemExit("free-path run: the MCP server does not expose pinakes_links")

        served = server.resolve(None)
        document = provider_module.resolve_document(served.connection(), "docs/a.md")
        if document is None:
            raise SystemExit("free-path run: the fixture KB has no docs/a.md to traverse from")
        payload = server.links(str(document))
        if "frontier" not in payload or payload.get("confidence") != "unknown":
            raise SystemExit(f"free-path run: pinakes_links returned {sorted(payload)}")
    finally:
        server.close()


def main_script(output: Path) -> None:
    register_embedding_backend("fake", lambda section, offline: FakeBackend())
    register_reranker("fake", lambda section, offline: FakeReranker())

    with TemporaryDirectory() as workspace:
        area = Path(workspace)

        free_kb = _build(area / "free-kb", backend="pypdfium2")
        _run_free_surfaces(free_kb)
        _mcp_handshake(free_kb)

        # The KB that makes this gate real: a paid backend configured, never invoked.
        paid_kb = _build(area / "paid-kb", backend=CLAUDE_VISION)
        (paid_kb / "docs" / "scan.pdf").write_bytes(b"%PDF-1.4\n")  # unmatched by `include`

        # Captured, then echoed, so the run can *prove* it reached the paid-availability probe
        # instead of assuming it. "The KB is configured for claude-vision" and "doctor actually
        # ran the paid branch" are different claims, and only the second is the one gate 4 leans
        # on — a future refactor could skip the branch entirely and leave every other assertion
        # here green.
        report = io.StringIO()
        with redirect_stdout(report):
            main(["sync", "--kb", str(paid_kb)])
            main(["doctor", "--kb", str(paid_kb)])
            main(["budget", "--kb", str(paid_kb)])
        printed = report.getvalue()
        print(printed, end="")
        if CLAUDE_VISION not in printed:
            raise SystemExit(
                f"free-path run: neither `pnk sync` nor `pnk doctor` mentioned {CLAUDE_VISION!r} "
                "on the paid KB, so the paid-availability probe this KB exists to exercise never "
                "ran — gate 4 would be passing for the wrong reason"
            )

    output.write_text(json.dumps(sorted(sys.modules)), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main_script(Path(sys.argv[1]))
