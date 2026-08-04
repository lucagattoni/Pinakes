"""The corpus's own table — one entry per fixture, matching `plans/20260727_1543-v0.2.md`'s I2 "
"stratum table.

Both `generate.py` (what to build) and `tests/test_pdf_corpus.py` (what must exist) import this
same list, so the two cannot silently drift apart from each other. They can still both drift from
the plan, which is why the test *also* hardcodes the plan's own per-stratum totals rather than only
checking files against this module.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    name: str
    stratum: str
    pages: int
    paid_twin: bool = False
    scanned: bool = False
    corrupt: bool = False


FIXTURES: tuple[FixtureSpec, ...] = (
    # two-column: 3 fixtures, 6 pages
    FixtureSpec("two-column-a", "two-column", 2, paid_twin=True),
    FixtureSpec("two-column-b", "two-column", 2),
    FixtureSpec("two-column-c", "two-column", 2),
    # tables: 3 fixtures, 6 pages
    FixtureSpec("tables-bordered", "tables", 2, paid_twin=True),
    FixtureSpec("tables-borderless", "tables", 2),
    FixtureSpec("tables-spanning", "tables", 2),
    # headers/footers: 3 fixtures, 16 pages (10 + 3 + 3)
    FixtureSpec("headers-repeating", "headers-footers", 10, paid_twin=True),
    FixtureSpec("footers-pagenum", "headers-footers", 3),
    FixtureSpec("footer-first-page-only", "headers-footers", 3),
    # ligatures & hyphenation: 3 fixtures, 6 pages
    FixtureSpec("ligatures-a", "ligatures-hyphenation", 2, paid_twin=True),
    FixtureSpec("hyphenation-soft", "ligatures-hyphenation", 2),
    FixtureSpec("hyphenation-page-break", "ligatures-hyphenation", 2),
    # scanned / image-only: 3 fixtures, 10 pages (6 + 2 + 2)
    FixtureSpec("scanned-clean", "scanned", 6, scanned=True),
    FixtureSpec("scanned-skewed", "scanned", 2, scanned=True),
    FixtureSpec("scanned-low-contrast", "scanned", 2, scanned=True),
    # pathological: 2 fixtures, 2 pages
    FixtureSpec("pathological-invisible-text", "pathological", 1),
    FixtureSpec("pathological-corrupt-header", "pathological", 1, corrupt=True),
    # baseline: 2 fixtures, 13 pages
    FixtureSpec("baseline-1p", "baseline", 1),
    FixtureSpec("baseline-12p", "baseline", 12, paid_twin=True),
)

STRATA_ORDER: tuple[str, ...] = (
    "two-column",
    "tables",
    "headers-footers",
    "ligatures-hyphenation",
    "scanned",
    "pathological",
    "baseline",
)

# I3b's `quality.py::pair_adjacency` metric: the (label, value) pairs a correctly-read table asserts
# are near each other in the extracted text — a row's own year beside its own count, never a
# different row's. All three table fixtures share one underlying data table (`generate.py`,
# `TABLE_DATA`), so the same four pairs apply to each. No other stratum asserts any pairs: nothing
# else in this corpus has a label/value relationship for adjacency to mean anything about.
PAIR_ADJACENCY_PAIRS: dict[str, tuple[tuple[str, str], ...]] = {
    "tables-bordered": (("2019", "142"), ("2020", "88"), ("2021", "165"), ("2022", "121")),
    "tables-borderless": (("2019", "142"), ("2020", "88"), ("2021", "165"), ("2022", "121")),
    "tables-spanning": (("2019", "142"), ("2020", "88"), ("2021", "165"), ("2022", "121")),
}

# I3b's fit of `layout.py`'s running-head threshold *T*: for each headers-footers fixture, the exact
# digit-normalised signature (`_DIGITS.sub("#", text.strip())`, matching `strip_running_heads`'s own
# key) of its one genuine running head or footer — `None` where the fixture plants no genuine one at
# all. `footer-first-page-only`'s whole point is a footer that appears once, so `None` is the
# correct declaration, not an oversight: it is the fixture that sets *T*'s lower bound, not an
# exemption from needing one. Verified (not assumed) against real pdfium extraction of every fixture
# in this stratum before committing to it: every non-running-head line here recurs on exactly 1 of
# its own fixture's pages (docs/RETROSPECTIVES.md, I3b) — there is no line anywhere in this stratum
# recurring on 2 of 3 or more pages without being one of the two declared running heads below.
KNOWN_RUNNING_HEAD_SIGNATURES: dict[str, str | None] = {
    "headers-repeating": "PINAKES ARCHIVE REVIEW",
    "footers-pagenum": "Page #",
    "footer-first-page-only": None,
}
