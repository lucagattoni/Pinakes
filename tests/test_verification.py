"""`docs/VERIFICATION.md` names a test for every promise. This is what stops it becoming fiction.

`plans/20260727_1543-v0.2.md`'s verification table wrote its test paths *before* the tests existed,
and
implementation renamed most of them: at I9, **61 of its 98 references did not resolve**. Nobody
noticed, because nothing read the table — a table of test paths is prose until something executes
it. That is the failure this file exists to make impossible for its successor: every
`tests/x.py::test_y` in `docs/VERIFICATION.md` must resolve to a test that exists, or this fails.

It deliberately checks *existence*, not that the named test asserts the claimed property — no test
can check that. What it buys is that the document can only go stale in the commit that breaks it.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERIFICATION = REPO / "docs" / "VERIFICATION.md"

#: `tests/test_x.py::test_y`, the only form the document uses. A bare `::name` continuing a previous
#: file is deliberately not supported: it is what made the plan's own table ambiguous to read.
REFERENCE = re.compile(r"`(tests/[\w/]+\.py)::(\w+)`")


def _named_tests() -> list[tuple[str, str]]:
    return REFERENCE.findall(VERIFICATION.read_text(encoding="utf-8"))


def _defined_in(path: Path) -> set[str]:
    return set(re.findall(r"^def (\w+)", path.read_text(encoding="utf-8"), re.MULTILINE))


def test_every_test_named_in_the_verification_table_exists() -> None:
    missing: list[str] = []
    for file, name in _named_tests():
        path = REPO / file
        if not path.is_file():
            missing.append(f"{file} (file does not exist) :: {name}")
        elif name not in _defined_in(path):
            missing.append(f"{file}::{name}")

    assert not missing, (
        "docs/VERIFICATION.md names tests that do not exist. Rename the row, or write the test — "
        "a verification table that cannot be resolved verifies nothing:\n  " + "\n  ".join(missing)
    )


def test_the_table_is_not_empty_and_covers_every_test_module_that_holds_a_promise() -> None:
    """A regex that matched nothing would make the test above vacuously green — the
    `false_abstain: 0.0` failure this project keeps finding in its own gates."""
    named = _named_tests()
    assert len(named) > 80, f"only {len(named)} references parsed; the document's format has moved"

    files = {file for file, _ in named}
    assert "tests/test_paid_path.py" in files, "the paid-path gates must be represented"
    assert "tests/test_ledger.py" in files, "the ledger's protocol must be represented"


def test_every_row_names_a_test_or_says_none() -> None:
    """A row with no `Where it is checked` entry is the wish the table exists to prevent. `none`
    is allowed — an honest gap is worth recording — but silence is not."""
    rows = [
        line
        for line in VERIFICATION.read_text(encoding="utf-8").splitlines()
        if line.startswith("|") and line.count("|") >= 4 and not set(line) <= set("|- ")
    ]
    header_words = {"what must be true", "increment"}
    unowned: list[str] = []
    for row in rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if cells[0].lower() in header_words:
            continue
        where = cells[-1]
        # `check.sh`, `make eval` and CI steps are owners too — they execute.
        executes = any(token in where for token in ("check.sh", "make ", "CI ", "committed file"))
        named = bool(REFERENCE.search(where)) or "none" in where.lower()
        if not where or not (named or executes):
            unowned.append(cells[0])
    assert not unowned, f"rows with no owner: {unowned}"


def test_the_measured_paid_delta_is_present_and_dated() -> None:
    """DESIGN §9's free-vs-paid numbers come from a human-gated run, so no test can produce them.
    What *is* repo-verifiable — and is the row the plan explicitly carved out — is that they are
    present, dated, and attributed to a model rather than asserted in the abstract.
    """
    design = (REPO / "docs" / "DESIGN.md").read_text(encoding="utf-8")
    row = next(
        (line for line in design.splitlines() if "PDF extraction quality" in line and "|" in line),
        None,
    )
    assert row is not None, "DESIGN §9 no longer has a PDF-extraction-quality risk row"
    assert re.search(r"measured 20\d{6} \d{2}:\d{2}", row), "the delta must carry its date and time"
    assert "claude-opus-5" in row, "…and the model that produced it"
    assert "€" in row, "…and what it cost"
    assert "synthetic rasters" in row, "…and the caveat that they are not real scans"
