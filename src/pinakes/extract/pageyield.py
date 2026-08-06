"""How much text the *free* backend already gets out of a PDF, measured per page.

One measurement, two consumers, and neither may define it for the other:

* **the paid path's pre-check** (`check_worth_paying_for`) — refuses to spend on a document
  pypdfium2 already reads, which is the most likely way a user loses money by accident;
* **`pnk doctor`** — reports the same distribution so the user can see *which* pages have no text
  layer before deciding whether to pay for any of them.

**This module is free, and must stay free.** It lived inside `extract/claude.py` while it had only
the one caller, which put it inside the single module in `src/` allowed to import `anthropic` — so
`pnk doctor`, a free command, could not have consumed it without importing the paid path to ask a
question that has nothing to do with paying (docs/INVARIANTS.md: "never probe a backend's
availability by
loading it"). Moving it here is what lets both callers share one definition, rather than the free
command growing a second copy of the per-page loop that could disagree with the one that spends.

The floor itself belongs to neither: it is fitted by `make pdf-eval` and shipped in `floors.toml`
(plans/20260727_1543-v0.2.md, I3b). **Its blind spot is stated rather than discovered** — the
fitting population
contained no bad-but-nonzero case, so the floor separates *empty* from *non-empty* and nothing
finer. A page rendered in an invisible text mode yields characters while being useless text, clears
the floor, and still needs the paid path. `--force` is the documented escape.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pinakes.errors import ExtractionError
from pinakes.extract import ExtractedText, ExtractionContext
from pinakes.extract.floors import load_floors
from pinakes.extract.quality import text_yield

#: The paid path refuses to spend when fewer than this fraction of pages fall below I3b's fitted
#: text-yield floor. Per page for the measurement, per document for the decision: a 200-page report
#: with eight scanned inserts has a healthy median and still needs the paid path, so a median would
#: be the wrong statistic.
SCANNED_PAGE_FRACTION: Final = 0.10


@dataclass(frozen=True, slots=True)
class FreeYield:
    """What the *free* backend already got out of this document, per page."""

    pages_total: int
    pages_below_floor: int
    floor: float
    native: ExtractedText | None = None
    """The extraction the measurement was taken from, kept rather than discarded: it is also the
    completeness audit's ground truth, and running the free backend a second time to recover text
    this function already had would double the cost of the one step that is supposed to be free."""
    below: tuple[int, ...] = ()
    """Which pages, 1-indexed. The count alone answers the paid path's question ("enough of this
    document is scanned to be worth paying for"); `pnk doctor` has to *name* them, because "8 of
    200 pages are empty" without saying which is a fact nobody can act on (I8)."""

    @property
    def scanned_fraction(self) -> float:
        return self.pages_below_floor / self.pages_total if self.pages_total else 0.0

    @property
    def chars_per_page(self) -> tuple[int, ...]:
        """Non-whitespace characters per page, in page order — the distribution `pnk doctor`
        reports a median over, and what it prints instead of a verdict when no floor is installed.
        """
        if self.native is None:  # pragma: no cover — every constructor here passes the extraction
            return ()
        return tuple(
            text_yield(self.native.text[start:end], pages=1).numerator
            for start, end in self.native.page_spans
        )

    @property
    def needs_the_paid_path(self) -> bool:
        """At least `SCANNED_PAGE_FRACTION` of pages yielded nothing.

        The floor is per page and the decision is per document, and the aggregation is stated
        rather than left to the reader: a median would be the wrong statistic, because a 200-page
        report with eight scanned inserts has a healthy median and still needs the paid path.
        """
        return self.scanned_fraction >= SCANNED_PAGE_FRACTION


def survey_free_yield(path: Path) -> FreeYield:
    """Run the free extractor and measure each page against I3b's fitted floor.

    Free, and it is the check that stops the most likely way a user loses money by accident:
    paying to re-extract a PDF that already has a perfectly good text layer.
    """
    from pinakes.extract.pdfium import Pypdfium2Extractor

    floors = load_floors()
    extracted = Pypdfium2Extractor().extract(path, ExtractionContext())
    return measure(extracted, floor=floors.text_yield_floor)


def measure(extracted: ExtractedText, *, floor: float) -> FreeYield:
    """The per-page comparison itself, over text somebody else already has.

    Split out from `survey_free_yield` so `pnk doctor` can measure a *cached* extraction without
    running the extractor again — the cache entry is the same text the index was built from, so
    re-extracting to measure it would be both slower and, on a stale cache, a different answer.
    """
    below = tuple(
        page
        for page, (start, end) in enumerate(extracted.page_spans, start=1)
        if text_yield(extracted.text[start:end], pages=1).numerator < floor
    )
    return FreeYield(
        pages_total=len(extracted.page_spans),
        pages_below_floor=len(below),
        floor=floor,
        native=extracted,
        below=below,
    )


def check_worth_paying_for(path: Path, *, force: bool) -> FreeYield:
    """Refuse to spend on a document the free path already handles, unless `--force`.

    With **no fitted floor installed this refuses to spend at all** rather than proceeding without
    its guard: a paid path running with its own cost-control check disabled is worse than one that
    does not run.
    """
    survey = survey_free_yield(path)
    if survey.needs_the_paid_path or force:
        return survey
    raise ExtractionError(
        f"{path.name}: the free extractor already reads "
        f"{survey.pages_total - survey.pages_below_floor} of {survey.pages_total} page(s) "
        f"({survey.scanned_fraction:.0%} below the fitted floor of {survey.floor:g} "
        f"non-whitespace characters per page), so a paid extraction would spend money to "
        f"re-read text you already have.",
        remedy=(
            "Run `pnk sync` with the free backend, or pass `--force` if you have a reason to pay "
            "for a re-extraction anyway."
        ),
    )
