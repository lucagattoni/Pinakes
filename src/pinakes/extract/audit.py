"""The completeness audit — **report-only in this release** (decision 12).

Did the paid extraction keep what the free one already had? `word_coverage` is computed per page
against pypdfium2's native text layer and **reported**. Nothing is re-extracted and nothing is
spent, and that restraint is the whole content of the decision rather than an omission:

**A re-extraction loop needs a floor, and no honest floor exists yet.** The pair it would have to
be fitted against is (native layer → Claude output), and there is no Claude output at fitting time.
So this release ships the *measurement*, and the loop is fitted on the distribution the first real
runs produce. That is this project's own rule applied to itself — a threshold that spends money is
fitted or it does not exist — and it also dissolves a contradiction the loop had inherited: the
audit would have re-extracted a **page**, while the paid extractor forbids re-asking a single page
from a slice and the estimator has only a per-slice formula. Nothing that does not run needs that
contradiction resolved.

**Pages with no usable native layer are exempt, and reported as exempt with their denominator.**
A scanned page has nothing to compare against — `word_coverage` against an empty ground truth is
not zero coverage, it is *no measurement* — and silently scoring those pages 0 would make the
scanned stratum, the exact case the paid path exists for, look like its worst failure.

**"Below median" rather than "below a threshold"**, for the same reason the loop is deferred: a
relative measure needs no fitted constant, and it answers the question a human actually has —
*which pages of this document look unlike the rest of it* — without implying a bar nobody has
measured.
"""

from dataclasses import dataclass
from statistics import median

from pinakes.extract import ExtractedText
from pinakes.extract.quality import text_yield, word_coverage


@dataclass(frozen=True, slots=True)
class PageAudit:
    """One page's completeness. `coverage` is `None` exactly when the page is exempt."""

    page: int
    """1-based, matching how a citation names it."""
    exempt: bool
    coverage: float | None = None
    native_words: int = 0


@dataclass(frozen=True, slots=True)
class DocumentAudit:
    pages: tuple[PageAudit, ...]

    @property
    def total(self) -> int:
        return len(self.pages)

    @property
    def audited(self) -> tuple[PageAudit, ...]:
        return tuple(page for page in self.pages if not page.exempt)

    @property
    def exempt(self) -> tuple[PageAudit, ...]:
        return tuple(page for page in self.pages if page.exempt)

    @property
    def median_coverage(self) -> float | None:
        scores = [page.coverage for page in self.audited if page.coverage is not None]
        return median(scores) if scores else None

    @property
    def below_median(self) -> tuple[PageAudit, ...]:
        """Audited pages scoring strictly below the document's own median.

        Strictly, so a document whose pages all score identically — including a perfect one —
        reports nothing below median rather than half of itself.
        """
        middle = self.median_coverage
        if middle is None:
            return ()
        return tuple(
            page for page in self.audited if page.coverage is not None and page.coverage < middle
        )

    def line(self) -> str:
        """The one-line summary, always carrying its denominators: `audited N of M` is a fact,
        `N pages audited` is a number with nothing to judge it against."""
        summary = (
            f"audited {len(self.audited)} of {self.total}, "
            f"exempt {len(self.exempt)} of {self.total}, "
            f"below-median {len(self.below_median)}"
        )
        middle = self.median_coverage
        return summary if middle is None else f"{summary} (median coverage {middle:.2f})"

    def low_coverage_paths(self, path: str) -> tuple[str, ...]:
        """`path:page` for each below-median page — what `pnk doctor` and the sync report surface,
        so a human can look at the actual page rather than at a percentage."""
        return tuple(f"{path}:{page.page}" for page in self.below_median)


def audit_completeness(
    paid: ExtractedText, native: ExtractedText, *, text_yield_floor: float
) -> DocumentAudit:
    """Compare a paid extraction against the free one, page by page.

    Both are page-span-addressed, so the comparison is per page rather than per document: a
    document-level score would let one well-transcribed page hide a dropped one, which is the only
    failure this audit exists to find.

    A page count mismatch is not reconciled or truncated — it is a defect in whichever extractor
    produced the shorter one, and quietly zipping to the shorter length would compare page *n* of
    one document with page *n* of a different one.
    """
    if len(paid.page_spans) != len(native.page_spans):
        raise ValueError(
            f"cannot audit: the paid extraction has {len(paid.page_spans)} page(s) and the native "
            f"layer {len(native.page_spans)} — comparing them positionally would score each page "
            "against a different page"
        )

    audits: list[PageAudit] = []
    for index, (paid_span, native_span) in enumerate(
        zip(paid.page_spans, native.page_spans, strict=True)
    ):
        native_text = native.text[native_span[0] : native_span[1]]
        paid_text = paid.text[paid_span[0] : paid_span[1]]
        if text_yield(native_text, pages=1).numerator < text_yield_floor:
            # No usable native layer: there is nothing to measure against, which is not the same
            # as measuring zero.
            audits.append(PageAudit(page=index + 1, exempt=True))
            continue
        rate = word_coverage(paid_text, native_text)
        if rate.denominator == 0 or rate.value is None:
            # Text above the yield floor, but no *significant* words in it — a page of figures, a
            # table of numbers, a page of stopwords. There is nothing to look for, so there is
            # nothing to measure, which is the same situation as a scanned page and gets the same
            # answer. Scoring it 1.0 would claim full preservation of something never checked, and
            # would drag the median *up*, making the real outliers look less unusual than they are.
            audits.append(PageAudit(page=index + 1, exempt=True))
            continue
        audits.append(
            PageAudit(
                page=index + 1,
                exempt=False,
                coverage=rate.value,
                native_words=rate.denominator,
            )
        )
    return DocumentAudit(tuple(audits))
