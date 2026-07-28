#!/bin/sh
# Every gate, in order, stopping at the first failure. Run this before every commit.
#
# Exists because `uv run pyright | tail -1 && git commit` reports the *tail* exit status, so a
# failing checker looks green. Two commits landed that way before this script did.
set -e
uv run --frozen ruff format --check .
uv run --frozen ruff check .
# --extra-search-path stubs/: pypdfium2 ships no py.typed marker (stubs/pypdfium2.pyi covers it
# for pyright); ty has no pyproject-level stubPath equivalent yet, so it needs the same path named
# on its own command line, or it hard-errors on a [light]-only checkout where pypdfium2 isn't
# installed — unlike pyright, which only warns (I2, docs/RETROSPECTIVES.md).
uv run --frozen ty check --extra-search-path stubs .
uv run --frozen pyright
uv run --frozen pytest -q

# extras-not-core (I1): pypdfium2/anthropic must never enter [project.dependencies] — a light
# core install is torch-free by design, and a PDF extractor is opt-in (docs/DESIGN.md §4.5).
if awk '/^dependencies = \[/,/^\]/' pyproject.toml | grep -qiE 'pypdfium2|anthropic'; then
    echo "pypdfium2 or anthropic found inside [project.dependencies] — they must stay extras" >&2
    exit 1
fi

# corpus-regenerates (I2): the sixteen text-layer fixtures must reproduce byte-identically from
# their own committed generator, and the three scanned ones within the pixel tolerance.
# SOURCE_DATE_EPOCH exported here explicitly — belt and suspenders alongside the generator's own
# fallback when unset (plans/v0.2.md, I2): neither should be the only thing standing between a
# regeneration and a fresh CreationDate rewriting every fixture.
#
# The text-layer half always runs — `--skip-scanned` drops the only fixtures needing pypdfium2 and
# Pillow — so a [light]-only checkout still gets the gate. Only the *scanned half* skips, printing
# its reason, which is what the plan asks for.
SOURCE_DATE_EPOCH=1785181219 uv run --frozen pytest -q \
    tests/test_pdf_corpus.py::test_regeneration_is_reproducible
if uv run --frozen python3 -c "import pypdfium2, PIL" 2>/dev/null; then
    SOURCE_DATE_EPOCH=1785181219 uv run --frozen pytest -q \
        tests/test_pdf_corpus.py::test_scanned_regeneration_within_tolerance
else
    echo "corpus-regenerates (scanned half): skipped — pinakes[pdf] and/or Pillow not installed"
fi

# pdf-quality (I3b): the extraction-quality baseline must not drift beyond tolerance, and neither
# fitted floor may drift from a fresh re-fit — a gate, never a one-time ceremony (plans/v0.2.md).
# Skips with its reason when pinakes[pdf] is absent (I1's own exit criterion: green under
# `--extra light` alone), never silently — `make pdf-eval` is the same command CI runs as its own
# job, in this commit, not deferred the way the draft plan would have left it until I9.
if uv run --frozen python3 -c "import pypdfium2" 2>/dev/null; then
    make pdf-eval
else
    echo "pdf-quality: skipped — pinakes[pdf] not installed"
fi

# prices-toml-parses (I6a): `as_of` must exist and parse as `YYYYMMDD HH:MM` — a build-time gate,
# never a staleness check (a wall-clock gate would fail a quiet weekend with no code change;
# staleness is a `pnk doctor` WARN and a runtime refusal instead, docs/DESIGN.md §5). This only
# ever catches a *malformed* file, which a code change could actually introduce.
uv run --frozen python3 -c "
import sys
from datetime import datetime
from pinakes.budget.prices import load_prices

prices = load_prices()
try:
    datetime.strptime(prices.as_of, '%Y%m%d %H:%M')
except ValueError as exc:
    print(
        f'prices.toml: as_of {prices.as_of!r} does not parse as YYYYMMDD HH:MM: {exc}',
        file=sys.stderr,
    )
    sys.exit(1)
"

echo "all gates green"
