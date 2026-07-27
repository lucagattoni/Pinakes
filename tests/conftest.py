"""Shared fixtures.

`valid_manifest_text` is the design's own §2.1 example, kept literal on purpose: if the schema and
the documented example drift apart, these tests are where it shows up.
"""

import os
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path

import pytest

from pinakes.ids import mint_kb_id

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


def paid_runnable() -> bool:
    """All three: `anthropic` importable, a key present, and the pytest-only spend opt-in set.

    `PINAKES_ALLOW_SPEND` is a pytest condition only, never a product guard (ground rules) — the
    product's own opt-in is `[extraction] backend`/`--extract=`/the accountant.
    """
    return (
        find_spec("anthropic") is not None
        and bool(os.environ.get("ANTHROPIC_API_KEY"))
        and os.environ.get("PINAKES_ALLOW_SPEND") == "1"
    )


VALID_MANIFEST = """\
[kb]
name     = "research"
id       = "{kb_id}"
template = "notes@1.0"
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
per_operation_eur = 0.05
monthly_eur       = 5.00
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
