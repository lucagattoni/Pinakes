#!/bin/sh
# Every gate, in order, stopping at the first failure. Run this before every commit.
#
# Exists because `uv run pyright | tail -1 && git commit` reports the *tail* exit status, so a
# failing checker looks green. Two commits landed that way before this script did.
set -e
uv run --frozen ruff format --check .
uv run --frozen ruff check .
# --extra-search-path stubs/: two stubs live there for two different reasons. pypdfium2 ships no
# py.typed marker (stubs/pypdfium2.pyi covers it for pyright); ruamel.yaml *does* ship one, and is
# stubbed anyway because `load`/`dump` take an untyped `stream` that pyright strict will not accept
# at the call sites (L5b, decision 20). ty has no pyproject-level stubPath equivalent yet, so it
# needs the same path named on its own command line, or it hard-errors on a [light]-only checkout
# where pypdfium2 isn't installed — unlike pyright, which only warns (I2,
# docs/RETROSPECTIVES.md).
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
# fallback when unset (plans/20260727_1543-v0.2.md, I2): neither should be the only thing standing between a
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
# fitted floor may drift from a fresh re-fit — a gate, never a one-time ceremony (plans/20260727_1543-v0.2.md).
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

# traversal-cap (L3): a walk asked for more than it may have gets less, and is told so. Drives the
# *shipped* core at depth=99 and adjacent_k=10000 against a 500-wide, 12-deep fixture graph and
# checks three things — the depth cap, the fan-out cap, and that `truncated` reports a cap that
# bit. A unit test proves the clamp works today; this proves nobody has turned a `min()` into a
# pass-through since, which is cheap to do by accident and expensive to notice, because the failure
# is a slow query and an enormous answer rather than an exception.
uv run --frozen python3 tools/traversal_cap_gate.py

# link-density (L1): authored links in the two committed corpora stay sparse — a ceiling on
# density, a ceiling on any one document's degree, and at least one intra-KB link per corpus.
# One author writes the corpus, its links and (later) the questions that traverse them, so a
# quietly over-linked fixture would make cross-KB traversal look easy and the graph release's eval
# look better than any real corpus ever will.
#
# Reads the committed sidecars, never an index — which is what lets it run here at all, and what
# makes the number it enforces the same population `pnk doctor` reports to a user (L7). Those two
# numbers disagreeing by three is how 0.4.1's data-loss bug was found; keeping them the same
# population is not tidiness.
#
# `uv run` rather than plain `python3`: it needs ruamel.yaml — the same library the product reads
# sidecars with, so the gate counts the same population it enforces. (It read through PyYAML until
# L5b; on a library the product no longer uses it would have counted sidecars the product now
# refuses.) Unlike the paid-path gate, nothing has to run this before the package is installed.
uv run --frozen python3 tools/link_density_gate.py

# eval-reproducibility (G1): the golden set answers the same way however the index was built. The
# graph release's gate reads per-question movement as evidence about *retrieval*, so movement caused
# by a rebuild is not noise, it is a wrong answer — and until G1 every tiebreak in the pipeline
# resolved to `chunks.id`, the rowid, which store.py says has no identity across rebuilds. Measured
# then: one golden-set question in 41 already differed between an incremental sync and a --rebuild.
#
# Offline and about a second, on a deliberately tie-heavy fake backend, so it needs no weights and
# no network. It sweeps four ways of reaching the same corpus state — a document edited, added,
# removed, renamed — because each takes a different path through sync.py and the tests cover one.
uv run --frozen python3 tools/eval_reproducibility_gate.py

# status-header: docs/STATUS.md line 3 — `**Latest release: x.y.z**` — must name
# pinakes.__version__. It drifted for four consecutive releases while the same sweeps updated
# every table below it (plans/20260731_1202-open-corrections.md, 20260803); a checklist missed it four times,
# which is this project's threshold for turning the item into a gate. Only the version is gated,
# never the `last reviewed` date beside it — a wall-clock staleness check fails on a quiet
# weekend with no code change, the same reasoning recorded at prices-toml-parses above. On main
# the invariant has no exception window: a release bumps `__version__` and the header in one
# commit (docs/RELEASING.md step 2 + sweep table), and between releases neither moves.
uv run --frozen python3 tools/status_header_gate.py

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

# No NUL byte in a tracked text file. git calls such a file **binary**: no diff, no review, and
# `grep` skips it silently — so a document can go wrong in a way this project's whole process
# (read the diff, grep for the sentence) cannot see. Caught 20260801, in a bullet warning about
# raw NUL bytes reaching output, written with a raw NUL byte in it.
python3 - <<'NULSCAN'
import pathlib, subprocess, sys
TEXT = {".md", ".py", ".toml", ".yaml", ".yml", ".sh", ".txt", ".cfg", ".ini", ".json",
        ".lock", ".pyi", ".gitignore", ".gitattributes", ""}
tracked = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout.split(b"\0")
bad, scanned = [], 0
for name in filter(None, tracked):
    path = pathlib.Path(name.decode())
    # An **allowlist** of text suffixes, not a denylist of binary ones: the first draft excluded
    # png/jpg/pdf and was immediately caught by a committed .ttf. A denylist of binary formats is
    # never finished.
    if not path.is_file() or path.suffix not in TEXT:
        continue
    scanned += 1
    if b"\0" in path.read_bytes():
        bad.append(str(path))
if bad:
    sys.exit("nul-scan: NUL byte in tracked text file(s): " + ", ".join(bad))
print(f"nul-scan: {scanned} text file(s) scanned, no NUL byte.")
NULSCAN

echo "all gates green"
