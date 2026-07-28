"""Score an extraction against a ground truth — five metrics, each shipping its own denominator.

Rule 3 (`plans/v0.2.md` I3b): v0.1's `false_abstain: 0.0` was vacuous and would have passed a CI
gate forever, because a rate with no visible denominator cannot be told apart from "measured and
zero." Every metric here returns a `Rate`, never a bare float — `Rate.value` is `None`, not `0.0`,
when the denominator is legitimately zero, so a stratum with nothing to measure is declared, never
silently scored as perfect or as failing.

Each metric is a pure function of two strings (`score_document`, and the five below it) —
testable against hand-built text with hand-computed answers, never only through an end-to-end
corpus score (the same reason `layout.py`'s own logic lives apart from the pdfium adapter, rule
11). Only `score_corpus`/`main` touch a filesystem or pdfium: they extract each fixture, score it,
and aggregate per stratum by summing numerators and denominators across a stratum's documents —
never averaging per-document ratios, which would let one thin document's lucky 1/1 outweigh
another's honest 40/400.

`word_coverage` is the PDFScout completeness audit (I7c's future re-extraction trigger):
"significant" words are lowercase alphabetic tokens of at least four characters, outside a small
stopword list — a metric that cannot be wrong on a known input is not fit to gate anything, so
both the word filter and every other metric here are checked against hand-computed cases before
they ever touch a real PDF.

`pair_adjacency` needs per-fixture (label, value) pairs to assert — that is corpus-specific
knowledge the corpus itself declares (`tests/pdf-corpus/spec.py::PAIR_ADJACENCY_PAIRS`), never
hard-coded here, so this module stays a generic scorer over *any* corpus shaped like this one (one
`spec.py`, paired `.pdf`/`.expected.txt` files), not a script wired to one fixture set.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

TEXT_YIELD_METRIC = "text_yield"
_METRIC_NAMES = ("char_recall", "order_fidelity", "junk_rate", "pair_adjacency", "word_coverage")

# Rule 3's corollary: "every stratum's denominators are non-zero" cannot hold and should never have
# been an exit criterion. `pair_adjacency` has no pairs to assert outside the tables stratum;
# `scanned` has no native text layer, so `word_coverage`'s denominator is zero by design and it
# extracts no words at all, so `junk_rate` is `0/0` too. Every other (metric, stratum) pair's
# denominator is real — `char_recall`/`order_fidelity` are measured against `expected`, which is
# never empty even for a scanned fixture (it is the ground truth a human would perceive, reused
# verbatim from the page it was rastered from). `write_baseline` asserts this map matches the
# corpus exactly, so a declaration cannot go stale in either direction without the gate refusing
# to write.
_NO_PAIRS_STRATA = (
    "two-column",
    "headers-footers",
    "ligatures-hyphenation",
    "scanned",
    "pathological",
    "baseline",
)
EXEMPTIONS: dict[str, dict[str, str]] = {
    "pair_adjacency": dict.fromkeys(
        _NO_PAIRS_STRATA, "no (label, value) pairs asserted for this stratum"
    ),
    "word_coverage": {"scanned": "no native text layer"},
    "junk_rate": {"scanned": "no words extracted (no native text layer)"},
}


@dataclass(frozen=True, slots=True)
class Rate:
    """A rate that carries its own denominator — `value` is `None`, never `0.0`, when the
    denominator is legitimately zero, so a declared "nothing to measure here" is never
    indistinguishable from a measured, failing zero."""

    numerator: float
    denominator: float

    @property
    def value(self) -> float | None:
        return self.numerator / self.denominator if self.denominator else None

    def as_dict(self) -> dict[str, float]:
        return {"numerator": self.numerator, "denominator": self.denominator}


def _lcs_length(a: Sequence[object], b: Sequence[object]) -> int:
    """Longest common subsequence length — a rolling one-row DP: O(len(a)*len(b)) time, O(min)
    space. Used by both `char_recall` and `order_fidelity`, at the character and word level
    respectively, because "found, in order" is exactly what a subsequence match (not a
    set-membership count) means.
    """
    if len(a) < len(b):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    for x in a:
        curr = [0] * (len(b) + 1)
        for j, y in enumerate(b, start=1):
            curr[j] = prev[j - 1] + 1 if x == y else max(prev[j], curr[j - 1])
        prev = curr
    return prev[-1]


def char_recall(extracted: str, expected: str) -> Rate:
    """Expected non-space characters found, in order, over expected non-space characters."""
    exp_chars = [c for c in expected if not c.isspace()]
    ext_chars = [c for c in extracted if not c.isspace()]
    return Rate(numerator=_lcs_length(exp_chars, ext_chars), denominator=len(exp_chars))


def order_fidelity(extracted: str, expected: str) -> Rate:
    """LCS length over word sequences, over expected word count."""
    exp_words = expected.split()
    ext_words = extracted.split()
    return Rate(numerator=_lcs_length(exp_words, ext_words), denominator=len(exp_words))


def junk_rate(extracted: str, expected: str) -> Rate:
    """Extracted words absent from the ground truth, over extracted word count.

    Set membership, not a sequence match: a word repeated in `extracted` but present even once in
    `expected` is not junk each time it recurs — junk means "this word should not be here at all,"
    not "this word is not in this exact position."
    """
    ext_words = extracted.split()
    expected_words = set(expected.split())
    junk = sum(1 for w in ext_words if w not in expected_words)
    return Rate(numerator=junk, denominator=len(ext_words))


def pair_adjacency(extracted: str, pairs: Sequence[tuple[str, str]], *, window: int = 80) -> Rate:
    """Asserted (label, value) pairs within `window` characters of each other in `extracted`.

    80 is a stated basis, not a fit (`plans/v0.2.md` I3b): correct reading order puts a label and
    its value 0-40 characters apart (adjacent cells read in the same row), a reading-order
    failure puts them hundreds apart (every label read together, then every value); any value in
    ~50-150 separates the two cases, and 80 is the midpoint. `str.find` locates each string's
    first occurrence — sufficient for this corpus's small, controlled fixtures, where every
    asserted label and value is otherwise unique in the document; a corpus with repeated labels
    would need the nearest occurrence, not the first, which this function does not attempt.
    """
    matched = 0
    for label, value in pairs:
        label_pos = extracted.find(label)
        value_pos = extracted.find(value)
        if label_pos != -1 and value_pos != -1 and abs(label_pos - value_pos) <= window:
            matched += 1
    return Rate(numerator=matched, denominator=len(pairs))


_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to", "for", "is", "are",
        "was", "were", "by", "with", "that", "this", "from", "as", "it", "its", "each", "any",
        "before", "after", "under", "once", "so", "not", "into", "than", "then", "when", "where",
    }
)  # fmt: skip
_WORD_PATTERN = re.compile(r"[a-zA-Z]+")


def _significant_words(text: str) -> set[str]:
    return {
        word
        for word in (m.group(0).lower() for m in _WORD_PATTERN.finditer(text))
        if len(word) >= 4 and word not in _STOPWORDS
    }


def word_coverage(extracted: str, expected: str) -> Rate:
    """Significant ground-truth words present anywhere in the extraction, over significant
    ground-truth words. "Anywhere," not "in order": this is a completeness audit (did the content
    survive at all), not a reading-order check — `order_fidelity` already covers order."""
    significant = _significant_words(expected)
    extracted_words = {m.group(0).lower() for m in _WORD_PATTERN.finditer(extracted)}
    present = sum(1 for word in significant if word in extracted_words)
    return Rate(numerator=present, denominator=len(significant))


def text_yield(extracted: str, *, pages: int) -> Rate:
    """Non-whitespace characters per page — the floor I3b fits, over nothing at all: it counts
    characters, so its denominator is `pages`, never `1`, and a Rate whose numerator alone
    already answers "did anything come out" for the one caller (`pnk doctor`, I7b) that only
    ever asks that."""
    non_whitespace = sum(1 for c in extracted if not c.isspace())
    return Rate(numerator=non_whitespace, denominator=pages)


@dataclass(frozen=True, slots=True)
class DocumentResult:
    name: str
    stratum: str
    pages: int
    scored: bool
    reason: str | None = None
    rates: Mapping[str, Rate] = field(default_factory=dict[str, Rate])

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stratum": self.stratum,
            "pages": self.pages,
            "scored": self.scored,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.rates:
            payload["rates"] = {name: rate.as_dict() for name, rate in self.rates.items()}
        return payload


def score_document(
    *,
    name: str,
    stratum: str,
    pages: int,
    extracted: str,
    expected: str,
    pairs: Sequence[tuple[str, str]] = (),
    has_native_layer: bool = True,
) -> DocumentResult:
    """Score one already-extracted document against its ground truth — pure, no I/O, no pdfium.

    Both strings are whitespace-flattened first (`" ".join(text.split())`): every metric here judges
    *content* (which characters, which words, in what order) never exact newline placement, which
    `layout.py`'s own line-level `Block` granularity makes incidental to correctness.

    `has_native_layer=False` (the scanned stratum) forces `word_coverage` to a declared `0/0` rather
    than computing it against `expected`: for a scanned fixture, `expected` is *ground truth* — what
    a human perceives from the image, reused verbatim from the fixture it was rastered from — not
    the PDF's own *native text layer*, which for an image-only PDF has zero words in it, full stop.
    Every other metric here is legitimately compared against `expected` regardless of native-layer
    status, since they ask "did we recover what a human would see," which is exactly the question
    that should score near-zero for a scanned page on the free path — `word_coverage` alone asks a
    different question ("did we lose something that was actually embedded"), and conflating the two
    would score a metric against ground truth it structurally cannot be judged by.
    """
    ext_flat = " ".join(extracted.split())
    exp_flat = " ".join(expected.split())
    rates = {
        "char_recall": char_recall(ext_flat, exp_flat),
        "order_fidelity": order_fidelity(ext_flat, exp_flat),
        "junk_rate": junk_rate(ext_flat, exp_flat),
        "word_coverage": word_coverage(ext_flat, exp_flat) if has_native_layer else Rate(0, 0),
        TEXT_YIELD_METRIC: text_yield(ext_flat, pages=pages),
    }
    if pairs:
        rates["pair_adjacency"] = pair_adjacency(ext_flat, pairs)
    return DocumentResult(name=name, stratum=stratum, pages=pages, scored=True, rates=rates)


def unscored_document(*, name: str, stratum: str, pages: int, reason: str) -> DocumentResult:
    return DocumentResult(name=name, stratum=stratum, pages=pages, scored=False, reason=reason)


@dataclass(frozen=True, slots=True)
class StratumReport:
    documents_scored: int
    documents_total: int
    pages_scored: int
    pages_total: int
    rates: Mapping[str, Rate]

    def as_dict(self) -> dict[str, Any]:
        return {
            "documents_scored": self.documents_scored,
            "documents_total": self.documents_total,
            "pages_scored": self.pages_scored,
            "pages_total": self.pages_total,
            "rates": {name: rate.as_dict() for name, rate in self.rates.items()},
        }


@dataclass(frozen=True, slots=True)
class CorpusReport:
    documents: tuple[DocumentResult, ...]
    strata: Mapping[str, StratumReport]

    def as_dict(self) -> dict[str, Any]:
        return {
            "documents": {d.name: d.as_dict() for d in self.documents},
            "strata": {name: stratum.as_dict() for name, stratum in self.strata.items()},
        }


def aggregate(documents: Sequence[DocumentResult]) -> Mapping[str, StratumReport]:
    """Sum numerators and denominators across each stratum's documents, then take the ratio of the
    sums — never average per-document ratios, which would let one thin document's lucky 1/1 outweigh
    another's honest 40/400 by counting them equally."""
    strata: dict[str, list[DocumentResult]] = {}
    for doc in documents:
        strata.setdefault(doc.stratum, []).append(doc)

    reports: dict[str, StratumReport] = {}
    for stratum, docs in strata.items():
        scored = [d for d in docs if d.scored]
        rates: dict[str, Rate] = {}
        for metric in (*_METRIC_NAMES, TEXT_YIELD_METRIC):
            num = sum(d.rates[metric].numerator for d in scored if metric in d.rates)
            den = sum(d.rates[metric].denominator for d in scored if metric in d.rates)
            rates[metric] = Rate(numerator=num, denominator=den)
        reports[stratum] = StratumReport(
            documents_scored=len(scored),
            documents_total=len(docs),
            pages_scored=sum(d.pages for d in scored),
            pages_total=sum(d.pages for d in docs),
            rates=rates,
        )
    return reports


def _load_spec(corpus_dir: Path) -> Any:
    """`tests/pdf-corpus/spec.py` has a hyphen in its directory, so it cannot be a dotted import —
    loaded by path, the same technique `test_pdf_corpus.py` already uses for the same reason."""
    import importlib.util

    spec_path = corpus_dir / "spec.py"
    spec = importlib.util.spec_from_file_location("pdf_corpus_spec", spec_path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"no spec.py found in {corpus_dir}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score_corpus(corpus_dir: Path) -> CorpusReport:
    """Extract and score every fixture `corpus_dir`'s own `spec.py` declares. Needs `pinakes[pdf]`
    installed — this function imports the pdfium adapter, unlike every pure metric above it."""
    from pinakes.errors import ExtractionError
    from pinakes.extract import ExtractionContext
    from pinakes.extract.pdfium import Pypdfium2Extractor

    spec_module = _load_spec(corpus_dir)
    pair_adjacency_pairs: Mapping[str, tuple[tuple[str, str], ...]] = getattr(
        spec_module, "PAIR_ADJACENCY_PAIRS", {}
    )
    extractor = Pypdfium2Extractor()

    documents: list[DocumentResult] = []
    for fixture in spec_module.FIXTURES:
        path = corpus_dir / f"{fixture.name}.pdf"
        expected_path = corpus_dir / f"{fixture.name}.expected.txt"
        expected = expected_path.read_text(encoding="utf-8")
        try:
            result = extractor.extract(path, ExtractionContext())
        except ExtractionError as exc:
            documents.append(
                unscored_document(
                    name=fixture.name,
                    stratum=fixture.stratum,
                    pages=fixture.pages,
                    reason=str(exc),
                )
            )
            continue
        documents.append(
            score_document(
                name=fixture.name,
                stratum=fixture.stratum,
                pages=fixture.pages,
                extracted=result.text,
                expected=expected,
                pairs=pair_adjacency_pairs.get(fixture.name, ()),
                has_native_layer=not fixture.scanned,
            )
        )
    return CorpusReport(documents=tuple(documents), strata=aggregate(documents))


def fit_running_head_threshold(corpus_dir: Path) -> tuple[float, str]:
    """Fit `layout.py`'s running-head threshold *T* over the headers-footers stratum.

    `spec.py::KNOWN_RUNNING_HEAD_SIGNATURES` states, per fixture, which digit-normalised signature
    (if any) is its one genuine running head or footer — every *other* signature observed anywhere
    in the stratum is a true negative, and its recurrence fraction is a lower bound *T* must clear
    without touching it. *T* is the midpoint between the lowest true-positive recurrence and the
    highest true-negative recurrence actually observed: a value chosen from the data, not merely
    consistent with it, and reproducible by re-running this same function against the same corpus.
    """
    import pypdfium2 as pdfium

    from pinakes.extract.layout import Page, block_signatures, blocks_from_chars, reading_order
    from pinakes.extract.pdfium import chars_from_page

    spec_module = _load_spec(corpus_dir)
    known: Mapping[str, str | None] = getattr(spec_module, "KNOWN_RUNNING_HEAD_SIGNATURES", {})
    headers_footers = [f for f in spec_module.FIXTURES if f.stratum == "headers-footers"]
    if not headers_footers:
        raise ValueError(f"{corpus_dir} declares no headers-footers fixtures to fit against")

    true_positive_fractions: list[float] = []
    true_negative_fractions: list[float] = []
    for fixture in headers_footers:
        doc = pdfium.PdfDocument(str(corpus_dir / f"{fixture.name}.pdf"))
        try:
            pages = tuple(
                reading_order(
                    Page(blocks=tuple(blocks_from_chars(chars_from_page(page), page_index=index)))
                )
                for index, page in enumerate(doc)
            )
        finally:
            doc.close()
        total = len(pages)
        signatures, _ = block_signatures(pages)
        declared = known.get(fixture.name)
        for (_, text), pages_seen in signatures.items():
            fraction = len(pages_seen) / total
            if declared is not None and text == declared:
                true_positive_fractions.append(fraction)
            else:
                true_negative_fractions.append(fraction)

    if not true_positive_fractions:
        raise ValueError(
            "no declared running-head signature (spec.py::KNOWN_RUNNING_HEAD_SIGNATURES) was ever "
            "observed recurring — the fit has no true positive to anchor on"
        )
    min_true_positive = min(true_positive_fractions)
    max_true_negative = max(true_negative_fractions) if true_negative_fractions else 0.0
    threshold = (min_true_positive + max_true_negative) / 2
    justification = (
        f"midpoint of the lowest true-positive recurrence ({min_true_positive:.3f}) and the "
        f"highest true-negative recurrence ({max_true_negative:.3f}) observed across "
        f"{len(headers_footers)} headers-footers fixtures"
    )
    return threshold, justification


def fit_text_yield_floor(report: CorpusReport) -> tuple[float, str]:
    """Fit the text-yield floor: non-whitespace characters per page.

    The scanned stratum is the positive control at zero (no native text layer exists to extract at
    all); every other scored, non-exempt document is the negative control. Decision 12
    (`plans/v0.2.md`, I3b) states the floor separates *empty* from *non-empty* and nothing finer, so
    the midpoint between the highest observed scanned yield and the lowest observed real yield is
    exactly that separator — not a quality bar, just a "did anything come out" check.
    """
    scanned_yields: list[float] = []
    real_yields: list[float] = []
    for doc in report.documents:
        if not doc.scored:
            continue
        rate = doc.rates.get(TEXT_YIELD_METRIC)
        if rate is None or rate.value is None:
            continue
        (scanned_yields if doc.stratum == "scanned" else real_yields).append(rate.value)

    max_scanned = max(scanned_yields) if scanned_yields else 0.0
    if not real_yields:
        raise ValueError("no non-scanned document was scored — the fit has no negative control")
    min_real = min(real_yields)
    floor = (max_scanned + min_real) / 2
    justification = (
        f"midpoint of the highest scanned-stratum yield ({max_scanned:.3f}/page) and the lowest "
        f"non-scanned yield ({min_real:.3f}/page)"
    )
    return floor, justification


def compare_to_baseline(
    report: CorpusReport, baseline: Mapping[str, Any], *, tolerance: float = 0.02
) -> list[str]:
    """Regressions beyond `tolerance`, per stratum per metric — lower is better for `junk_rate`,
    higher for everything else. A metric legitimately exempt in the baseline (declared `null`) is
    never compared; a metric that *stops* being exempt (goes from `null` to a real value, or the
    reverse) is reported as a structural change, since that is not a magnitude regression a
    tolerance can express.
    """
    baseline_strata = cast(dict[str, Any], baseline.get("strata", {}))
    regressions: list[str] = []
    for stratum_name, stratum in report.strata.items():
        baseline_stratum = cast(dict[str, Any], baseline_strata.get(stratum_name, {}))
        for metric, rate in stratum.rates.items():
            before = baseline_stratum.get(metric)
            after = rate.value
            if before is None and after is None:
                continue
            if before is None or after is None:
                regressions.append(
                    f"{stratum_name}.{metric}: exemption changed (baseline {before!r} -> {after!r})"
                )
                continue
            before = float(before)
            if metric == "junk_rate":
                if after > before + tolerance:
                    regressions.append(f"{stratum_name}.{metric}: {before:.3f} -> {after:.3f}")
            elif after < before - tolerance:
                regressions.append(f"{stratum_name}.{metric}: {before:.3f} -> {after:.3f}")
    return regressions


def write_baseline(path: Path, report: CorpusReport) -> None:
    """Write `strata` (each metric's value, `null` where the denominator is zero) and `exemptions`
    (why each `null` is expected, never merely that it is). Refuses to write if `EXEMPTIONS` and the
    corpus disagree about which (metric, stratum) pairs actually have a zero denominator — an
    exemption that goes stale in either direction (something newly zero with no declared reason, or
    a declared reason for something no longer zero) is exactly the silent drift rule 3 exists to
    catch, so it is caught here rather than written past.
    """
    strata_payload: dict[str, dict[str, float | None]] = {
        name: {metric: rate.value for metric, rate in stratum.rates.items()}
        for name, stratum in report.strata.items()
    }
    actual_exempt = {
        (metric, stratum_name)
        for stratum_name, values in strata_payload.items()
        for metric, value in values.items()
        if value is None
    }
    declared_exempt = {
        (metric, stratum_name)
        for metric, by_stratum in EXEMPTIONS.items()
        for stratum_name in by_stratum
    }
    if actual_exempt != declared_exempt:
        raise ValueError(
            "EXEMPTIONS is out of sync with the corpus: "
            f"undeclared zero-denominators {actual_exempt - declared_exempt}, "
            f"stale declarations {declared_exempt - actual_exempt}"
        )

    payload = {"strata": strata_payload, "exemptions": EXEMPTIONS}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_baseline(path: Path) -> dict[str, Any]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a baseline (expected a JSON object)")
    return cast(dict[str, Any], raw)


def check_floor_drift(
    corpus_dir: Path, floors_path: Path, report: CorpusReport, *, tolerance: float = 0.05
) -> list[str]:
    """Re-fit both floors from the current corpus and compare against the committed
    `floors.toml` — "nothing here re-fits automatically, so `fitted_on` can go stale while still
    reading as evidence... `make pdf-eval` recomputes the floors and fails if a committed value has
    drifted" (`plans/v0.2.md`, I3b). A `layout.py`/`textpolicy.py` change that moves either fitted
    value is exactly the drift this exists to catch — re-fitting is a gate, not a one-time ceremony.
    """
    import tomllib

    committed = tomllib.loads(floors_path.read_text(encoding="utf-8"))
    fresh_t, t_reason = fit_running_head_threshold(corpus_dir)
    fresh_floor, floor_reason = fit_text_yield_floor(report)

    drift: list[str] = []
    committed_t = float(committed["running_head_threshold"])
    if abs(fresh_t - committed_t) > tolerance:
        drift.append(
            f"running_head_threshold drifted: committed {committed_t:.6f}, "
            f"fresh fit {fresh_t:.6f} ({t_reason})"
        )
    committed_floor = float(committed["text_yield_floor"])
    if abs(fresh_floor - committed_floor) > tolerance * max(1.0, committed_floor):
        drift.append(
            f"text_yield_floor drifted: committed {committed_floor:.3f}, "
            f"fresh fit {fresh_floor:.3f} ({floor_reason})"
        )
    return drift


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m pinakes.extract.quality <corpus_dir> [--baseline path] [--write-baseline]
    [--check-floors path]`."""
    parser = argparse.ArgumentParser(prog="pinakes.extract.quality", description=__doc__)
    parser.add_argument("corpus_dir", type=Path)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument(
        "--check-floors", type=Path, default=None, help="floors.toml to check for drift"
    )
    args = parser.parse_args(argv)

    report = score_corpus(args.corpus_dir)
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))

    exit_code = 0

    baseline_path = args.baseline or (args.corpus_dir / "baseline.json")
    if args.write_baseline:
        write_baseline(baseline_path, report)
        print(f"\nwrote {baseline_path}")
    elif not baseline_path.exists():
        print(f"\nno baseline at {baseline_path}; nothing to compare against.")
    else:
        regressions = compare_to_baseline(
            report, read_baseline(baseline_path), tolerance=args.tolerance
        )
        if regressions:
            print("\nregressions beyond tolerance:")
            for line in regressions:
                print(f"  {line}")
            exit_code = 1
        else:
            print("\nno regressions beyond tolerance.")

    if args.check_floors is not None:
        drift = check_floor_drift(args.corpus_dir, args.check_floors, report)
        if drift:
            print(f"\n{args.check_floors} has drifted from a fresh fit:")
            for line in drift:
                print(f"  {line}")
            exit_code = 1
        else:
            print(f"\n{args.check_floors}: no drift.")

    return exit_code


if __name__ == "__main__":
    import sys

    sys.exit(main())
