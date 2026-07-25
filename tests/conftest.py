"""Shared fixtures.

`valid_manifest_text` is the design's own §2.1 example, kept literal on purpose: if the schema and
the documented example drift apart, these tests are where it shows up.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pinakes.ids import mint_kb_id

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
