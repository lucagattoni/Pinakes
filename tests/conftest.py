"""Shared fixtures.

`valid_manifest_text` is the design's own §2.1 example, kept literal on purpose: if the schema and
the documented example drift apart, these tests are where it shows up.
"""

import importlib
import itertools
import os
import re
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from importlib.util import find_spec
from pathlib import Path

import numpy as np
import pytest

from pinakes import template
from pinakes.embed import ModelInfo, Vectors, register_embedding_backend, register_reranker
from pinakes.ids import mint_kb_id
from pinakes.init import init

# Pinned once, here, for whatever fixture-generation code reads it (I2's corpus generator).
# Only its stability matters, not its value: set 20260727 21:40, changing it invalidates nothing
# that exists yet, only a byte-identical regeneration a later increment may want.
os.environ.setdefault("SOURCE_DATE_EPOCH", "1785181219")

PDF_CORPUS = Path(__file__).parent / "pdf-corpus"


def pdf_runnable() -> bool:
    """All three must hold: `pinakes[pdf]` importable, Pillow importable, and the corpus present.

    Mirrors `test_embed.py`'s `_runnable` — checking fewer than every part proved wrong there (a
    real absent-dependency failure instead of a skip), for the same reason here: the three facts
    vary independently (an installed extra with no corpus checked out; a corpus with no extra
    installed; pypdfium2 present but Pillow — dev-group-only, never core, never an extra — is
    not). Pillow joins the predicate in I2, the increment that first needs it (ground rules, rule
    5): I1 only needed the first two.
    """
    return (
        find_spec("pypdfium2") is not None and find_spec("PIL") is not None and PDF_CORPUS.is_dir()
    )


def pdf_extraction_runnable() -> bool:
    """`pinakes[pdf]` importable and the corpus present — never Pillow, unlike `pdf_runnable()`.

    I3b's own tests (`test_extract_pdfium.py`, `test_extract_quality.py`) extract text; nothing
    in that path renders or compares pixels, so requiring Pillow too would skip them on a
    `[pdf]`-only install that could actually run them (Pillow is dev-group-only, per
    `pdf_runnable()`'s own note).
    """
    return find_spec("pypdfium2") is not None and PDF_CORPUS.is_dir()


def paid_runnable() -> bool:
    """All three: `anthropic` importable, a key present, and the pytest-only spend opt-in set.

    `PINAKES_ALLOW_SPEND` is a pytest condition only, never a product guard (ground rules) — the
    product's own opt-in is `[extraction] backend`/`--extract=`/the accountant.
    """
    return (
        find_spec("anthropic") is not None
        and bool(os.environ.get("PINAKES_ANTHROPIC_API_KEY"))
        and os.environ.get("PINAKES_ALLOW_SPEND") == "1"
    )


VALID_MANIFEST = """\
[kb]
name     = "research"
id       = "{kb_id}"
template = "notes@1.1"
created  = "20260725 09:14"

[sources]
roots   = ["docs/"]
include = ["**/*.md", "**/*.txt"]
exclude = ["**/drafts/**"]

[embedding]
provider = "sentence-transformers"
model    = "BAAI/bge-small-en-v1.5"
dim      = 384

[extraction]
backend = "pypdfium2"
model   = "claude-opus-5"

[chunking]
strategy   = "structural"
max_tokens = 510
overlap    = 64

[retrieval]
candidates_per_source = 50
fusion                = "rrf"
fusion_top_k          = 20
final_k               = 8
rerank                = "local"
vector_tier           = "auto"

[retrieval.confidence]
fitted_for = "BAAI/bge-reranker-base@abc123"
low_below  = 0.31
high_above = 0.62

[rerank]
provider = "sentence-transformers"
model    = "BAAI/bge-reranker-base"

[budget]
confirm_above_eur = 0.01
per_operation_eur = 0.30
monthly_eur       = 30.00
timezone          = "UTC"
on_exceed         = "abort"
"""


@pytest.fixture
def kb_root(tmp_path: Path) -> Path:
    """A minimal, valid KB directory."""
    root = tmp_path / "kb"
    (root / "docs").mkdir(parents=True)
    (root / "pinakes.toml").write_text(VALID_MANIFEST.format(kb_id=mint_kb_id()), encoding="utf-8")
    return root


FAKE_DIM = 3


class _FakeBackend:
    """Instant and deterministic — the tests using this are about money, not embeddings."""

    def embed(self, texts: Sequence[str]) -> Vectors:
        rows = list(texts)
        if not rows:
            return np.zeros((0, FAKE_DIM), dtype=np.float32)
        return np.ascontiguousarray(
            np.vstack([np.ones(FAKE_DIM, dtype=np.float32) for _ in rows]), dtype=np.float32
        )

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", "rev1", FAKE_DIM, 512)


class _FakeReranker:
    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        return [0.0] * len(passages)

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-reranker", "v1", 0, 512)


def _rewrite(text: str, pattern: str, replacement: str) -> str:
    """Substitute once, refusing a no-op. `str.replace` and `re.sub` both return the string
    unchanged when they match nothing and report it to nobody — which is exactly how I7a built a
    "paid" KB that was never paid (docs/RETROSPECTIVES.md, 20260728)."""
    edited, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise AssertionError(f"manifest rewrite matched nothing: {pattern!r}")
    return edited


@pytest.fixture
def make_fake_kb(tmp_path: Path) -> Callable[..., Path]:
    """Build a real KB from the shipped template, with instant fake models.

    A factory rather than a KB, so a test can vary the one thing it is about — the extraction
    backend, `[budget] timezone`, a cap — without hand-stamping a manifest that then quietly
    diverges from the template the product actually writes.
    """
    register_embedding_backend("fake", lambda section, offline: _FakeBackend())
    register_reranker("fake", lambda section, offline: _FakeReranker())

    counter = {"n": 0}

    def _make(
        *, extraction_backend: str | None = None, budget: dict[str, str] | None = None
    ) -> Path:
        counter["n"] += 1
        result = init(tmp_path / f"fake-kb{counter['n']}", now="20260728 12:00")
        path = result.root / "pinakes.toml"
        text = path.read_text(encoding="utf-8")
        for pattern, replacement in (
            (r'^provider = "sentence-transformers"$', 'provider = "fake"'),
            (r'^model    = "BAAI/bge-small-en-v1\.5"$', 'model    = "fake-model"'),
            (r"^dim      = 384$", f"dim      = {FAKE_DIM}"),
            (r'^model    = "BAAI/bge-reranker-base"$', 'model    = "fake-reranker"'),
        ):
            text = _rewrite(text, pattern, replacement)
        # `[budget]` already exists in the template, so its keys are edited in place: a second
        # `[budget]` table is a TOML duplicate-key error, not an override. A key the template does
        # not stamp (it omits `daily_eur`, leaving the parser's default) is inserted into the
        # existing table instead of replaced.
        for key, value in (budget or {}).items():
            if re.search(rf"^{key}\s*=", text, flags=re.MULTILINE):
                text = _rewrite(text, rf"^{key}\s*=.*$", f"{key} = {value}")
            else:
                text = _rewrite(text, r"^\[budget\]$", f"[budget]\n{key} = {value}")
        # `[extraction]` does not exist in the template, so it is appended.
        if extraction_backend is not None:
            text += f'\n[extraction]\nbackend = "{extraction_backend}"\nmodel   = "claude-opus-5"\n'
        path.write_text(text, encoding="utf-8")
        return result.root

    return _make


@pytest.fixture
def fake_kb(make_fake_kb: Callable[..., Path]) -> Path:
    return make_fake_kb()


_SYNTHETIC_PACKAGES = itertools.count()


@pytest.fixture
def synthetic_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., str]]:
    """Build a template with any number of archived versions, in a package of its own.

    A real importable package rather than a monkeypatched `_root`, so `describe`,
    `archived_versions`, `archived_root` and `render_archived` all run their real
    `importlib.resources` paths — the ones that have to work from inside a wheel.

    **Shared because the shipped template cannot reach the paths under test.** D-2b leaves `notes`
    with exactly one archived version, so *every* positive outcome — a diff, a hunk that places, a
    hunk that conflicts — is unreachable from it and needs a template built for the purpose.
    `test_doctor.py` needed that first (T2); `test_cli_upgrade.py` needs the same fixture (T3),
    and a second copy of it would be a second thing to keep true.
    """
    package = f"synthetic_templates_{next(_SYNTHETIC_PACKAGES)}"
    root = tmp_path / package
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    # `monkeypatch.syspath_prepend` is untyped, and the test suite is checked under pyright strict.
    sys.path.insert(0, str(tmp_path))
    monkeypatch.setattr(template, "PACKAGE", package)
    importlib.invalidate_caches()

    def _make(
        name: str,
        *,
        versions: Mapping[str, str],
        current: str,
        files: Sequence[str] | None = None,
        extras: Mapping[str, str] | None = None,
    ) -> str:
        """`files` declares the template's `files = [...]`; `extras` writes files into its tree.

        Both are optional and default to absent, so every caller written before T7 keeps building
        exactly the template it built before — an absent `files` key is itself the thing T7's
        historical-two test asserts on, and it must stay reachable from this fixture.
        """

        def declaration(version: str) -> str:
            body = f'name = "{name}"\nversion = "{version}"\ndescription = "synthetic"\n'
            if files is not None and version == current:
                rendered = ", ".join(f'"{entry}"' for entry in files)
                body += f"files = [{rendered}]\n"
            return body

        directory = root / name
        directory.mkdir()
        for relative, content in (extras or {}).items():
            destination = directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
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


@pytest.fixture
def write_manifest(tmp_path: Path) -> Callable[[str], Path]:
    """Write an arbitrary manifest body into a fresh KB root and return that root."""

    counter = {"n": 0}

    def _write(body: str) -> Path:
        counter["n"] += 1
        root = tmp_path / f"kb{counter['n']}"
        root.mkdir()
        (root / "pinakes.toml").write_text(body, encoding="utf-8")
        return root

    return _write
