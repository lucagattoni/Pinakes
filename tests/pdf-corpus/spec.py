"""The corpus's own table — one entry per fixture, matching `plans/v0.2.md`'s I2 stratum table.

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
