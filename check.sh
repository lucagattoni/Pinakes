#!/bin/sh
# Every gate, in order, stopping at the first failure. Run this before every commit.
#
# Exists because `uv run pyright | tail -1 && git commit` reports the *tail* exit status, so a
# failing checker looks green. Two commits landed that way before this script did.
set -e
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen ty check .
uv run --frozen pyright
uv run --frozen pytest -q

# extras-not-core (I1): pypdfium2/anthropic must never enter [project.dependencies] — a light
# core install is torch-free by design, and a PDF extractor is opt-in (docs/DESIGN.md §4.5).
if awk '/^dependencies = \[/,/^\]/' pyproject.toml | grep -qiE 'pypdfium2|anthropic'; then
    echo "pypdfium2 or anthropic found inside [project.dependencies] — they must stay extras" >&2
    exit 1
fi

echo "all gates green"
