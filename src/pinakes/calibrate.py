"""Fitting `[retrieval.confidence]` against a golden set (§4.2).

Cross-encoder scores are not comparable across queries, so an absolute threshold means nothing until
it has been fitted against questions whose answers are known. This module does that fitting and
nothing else: it prints a manifest block, it does not write one. A tool that silently edited a
user-owned manifest would be doing the one thing `docs/` and `pinakes.toml` exist to prevent.

Both thresholds are fitted against the scores of the **unanswerable** questions, because those are
the ones whose correct outcome is known absolutely — nothing in the corpus answers them, so any
confident result is wrong by construction. `low_below` is their median; `high_above` a high
percentile of them.

**These numbers are optimistic and the honest reason is stated here rather than buried:** the
thresholds are fitted on the same golden set the eval then scores against, so the false-confidence
rate it reports is partly a measurement of the fit. A held-out split is the correct fix and needs a
larger question set than v0.1 ships. Until then, treat calibration as a floor on quality, not a
measurement of it.

Real reranker scores are raw logits, not probabilities: `BAAI/bge-reranker-base` returned about
-0.28 for a relevant passage and -7.85 for an irrelevant one (measured 20260725 15:35). Nothing
assumes a 0-to-1 range.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from pinakes.embed import EmbeddingBackend, Reranker
from pinakes.errors import CalibrationError
from pinakes.eval import Question
from pinakes.manifest import Manifest
from pinakes.search import search


@dataclass(frozen=True, slots=True)
class Calibration:
    fitted_for: str
    low_below: float
    high_above: float
    answerable_scores: tuple[float, ...]
    unanswerable_scores: tuple[float, ...]

    def as_manifest_block(self) -> str:
        return "\n".join(
            [
                "[retrieval.confidence]",
                f'fitted_for = "{self.fitted_for}"',
                f"low_below  = {self.low_below:.4f}",
                f"high_above = {self.high_above:.4f}",
            ]
        )


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:  # pragma: no cover — callers check first
        return 0.0
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def fit(
    connection: sqlite3.Connection,
    manifest: Manifest,
    questions: Sequence[Question],
    *,
    backend: EmbeddingBackend,
    reranker: Reranker,
) -> Calibration:
    answerable: list[float] = []
    unanswerable: list[float] = []

    for question in questions:
        query = question.hops[-1].query if question.hops else question.question
        result = search(
            connection,
            manifest,
            query,
            backend=backend,
            reranker=reranker,
            filters=question.filters,
            limit=1,
        )
        if not result.passages or result.passages[0].rerank_score is None:
            continue
        score = result.passages[0].rerank_score
        (answerable if question.answerable else unanswerable).append(score)

    if not answerable:
        raise CalibrationError(
            "no answerable question produced a reranker score.",
            remedy='Check that the index is built and `[retrieval] rerank = "local"`.',
        )
    if not unanswerable:
        raise CalibrationError(
            "the golden set has no `no-answer` questions.",
            remedy=(
                "Without them, false confidence cannot be measured and a threshold cannot be "
                "fitted — a system that answers everything would score perfectly (§7)."
            ),
        )

    # Both thresholds are fitted against the *unanswerable* scores, because those are the ones
    # whose correct outcome is known absolutely: nothing in the corpus answers them.
    #
    #   low_below  = the median unanswerable score. Below it, a result looks like the questions the
    #                corpus cannot answer, so reporting `low` is warranted.
    #   high_above = a high percentile of them. Above it, no no-answer question scored, so claiming
    #                confidence is defensible.
    #
    # An earlier version used `min(answerable)` for the low threshold, which on real logits was
    # -9.885 — a floor almost nothing falls below, so `low` was effectively unreachable and the
    # false-abstain rate was a flattering zero by construction.
    low = median(unanswerable)
    high = _percentile(unanswerable, 0.9)
    if low > high:
        low, high = high, low

    return Calibration(
        fitted_for=reranker.info().fingerprint(),
        low_below=low,
        high_above=high,
        answerable_scores=tuple(sorted(answerable)),
        unanswerable_scores=tuple(sorted(unanswerable)),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m pinakes.calibrate <kb>` — prints a block to paste. It never edits the manifest."""
    import argparse
    from pathlib import Path

    from pinakes import manifest as manifest_module
    from pinakes import store
    from pinakes.embed import load_backend, load_reranker
    from pinakes.eval import load_questions

    parser = argparse.ArgumentParser(prog="pinakes.calibrate", description=__doc__)
    parser.add_argument("kb", type=Path)
    parser.add_argument("--questions", type=Path, default=None)
    args = parser.parse_args(argv)

    manifest = manifest_module.load(args.kb)
    questions = load_questions(args.questions or (args.kb / "eval" / "questions.yaml"))
    reranker = load_reranker(manifest.rerank)

    connection = store.connect_ro(manifest.index_path)
    try:
        calibration = fit(
            connection,
            manifest,
            questions,
            backend=load_backend(manifest.embedding),
            reranker=reranker,
        )
    finally:
        connection.close()

    answerable = calibration.answerable_scores
    unanswerable = calibration.unanswerable_scores
    print(
        f"fitted on {len(answerable)} answerable and {len(unanswerable)} unanswerable questions\n"
        f"  answerable scores:   {answerable[0]:.3f} .. {answerable[-1]:.3f}\n"
        f"  unanswerable scores: {unanswerable[0]:.3f} .. {unanswerable[-1]:.3f}\n"
    )
    print("Paste this into pinakes.toml — nothing here writes it for you:\n")
    print(calibration.as_manifest_block())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
