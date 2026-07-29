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
uv run --frozen pytest -q -rs

# paid-path allowlist, gates 1 and 2 (I7a): every path in .paid-path-allowlist exists, and no file
# under src/ outside that list imports a paid-API client. Replaces the unconditional grep that
# lived only in CI's build job — unconditional admits no exceptions, so it would have turned main
# red the moment I7b adds `import anthropic` to the one module allowed to have it.
#
# Plain `python3`, not `uv run`: the script is stdlib-only and imports nothing from this project,
# which is what lets CI's build job run it without installing the package first.
python3 tools/paid_path_gate.py

# extras-not-core (I1), reused as the allowlist's gate 3: pypdfium2/anthropic must never enter
# [project.dependencies] — a light core install is torch-free by design, and a PDF extractor is
# opt-in (docs/DESIGN.md §4.5). Also asserted from the other side by
# tests/test_packaging.py::test_paid_and_pdf_clients_stay_out_of_core, which is how CI gets it.
if awk '/^dependencies = \[/,/^\]/' pyproject.toml | grep -qiE 'pypdfium2|anthropic'; then
    echo "pypdfium2 or anthropic found inside [project.dependencies] — they must stay extras" >&2
    exit 1
fi

# Gate 4 — the free path never imports a paid client, observed at runtime rather than grepped —
# runs inside `pytest` above (tests/test_paid_path.py). It is named here because it is the gate
# that actually matters and the one a reader of this file would otherwise assume is missing; it
# skips with a printed reason when pinakes[claude] is absent, and CI's [light,pdf,claude] leg is
# where it is meaningful.

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

# changelog/retrospective fragments are well-formed. Cheap, offline, and it fails *here* rather
# than at release time — `--apply` deletes the fragments it consumed, so a malformed one found then
# would be found with the evidence already gone.
python3 tools/fragments.py --check

# shared-file overlap: which files this branch touches that the default branch has touched too.
# Deliberately NOT --strict and NOT --fetch here: several agents work in this repo at once, so
# overlap is common and normal mid-development, and a routine `./check.sh` must stay offline-capable
# and fast. It reports; the landing checklist runs `--fetch --strict` before a merge, which is the
# moment the answer can still change what you do.
python3 tools/shared_file_overlap.py

echo "all gates green"
