"""The scoreboard: recall@k, MRR, rerank precision, false-abstain and false-confidence (§7).

This is what makes fusion weights, chunk sizes and reranker choices *decidable* instead of
superstitious. Every retrieval change in this repository has to move numbers here, and the
`--baseline` comparison is what turns that from an intention into a CI gate.

Two measurements deserve their names spelled out, because they are the ones that keep §4.2 honest:

* **false-abstain** — the corpus contained the answer and the system reported low confidence anyway.
  Abstention is only a virtue if it is rare when it is wrong.
* **false-confidence** — the corpus contained no answer and the system reported high confidence. The
  golden set carries deliberate no-answer questions precisely so this can be counted rather than
  assumed.

Multi-hop questions are scored without an agent: each ships the hop sequence a reader would follow,
the harness runs them in order, and scores the final hop. That tests whether the corpus *supports*
the §4.3 loop, not whether some particular agent drives it well.
"""

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from pinakes import store
from pinakes.embed import EmbeddingBackend, Reranker, load_backend, load_reranker
from pinakes.errors import EvalError
from pinakes.manifest import Manifest
from pinakes.search import HIGH, LOW, UNKNOWN, Filters, search

DEFAULT_K = 5


@dataclass(frozen=True, slots=True)
class Hop:
    query: str
    expect: str


@dataclass(frozen=True, slots=True)
class Question:
    question: str
    kind: str
    expect: tuple[str, ...] = ()
    filters: Filters = field(default_factory=Filters)
    hops: tuple[Hop, ...] = ()

    @property
    def answerable(self) -> bool:
        return self.kind != "no-answer"


@dataclass(frozen=True, slots=True)
class Outcome:
    question: Question
    retrieved: tuple[str, ...]
    confidence: str
    hit_rank: int | None
    hops_followed: int = 0

    @property
    def hit(self) -> bool:
        """A scripted question is a hit only when **every** hop landed its own document.

        Before 20260729 this read `hit_rank is not None`, which ignored `hops` entirely:
        `hops_followed` was computed and never consulted, so a multi-hop question scored as a
        single-shot search of its last hop's query and the class measured nothing about hopping.
        Deleting the hop loop left `by_kind["multi-hop"]` bit-identical — the definition of a
        vacuous metric (§7).
        """
        return self.hit_rank is not None and self.hops_followed == len(self.question.hops)


@dataclass(frozen=True, slots=True)
class Metrics:
    questions: int
    recall_at_k: float
    mrr: float
    rerank_precision: float
    false_abstain: float
    false_confidence: float
    confidence_coverage: float
    """Fraction of questions where confidence was anything other than `unknown`.

    Without this, the two error rates below read a flattering 0.000 on any KB that has no fitted
    thresholds — not because the system is never wrong, but because it never claims anything. A CI
    gate on false-confidence alone would be vacuous exactly when calibration is missing, which is
    the case it most needs to catch.
    """

    by_kind: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "questions": self.questions,
            "recall_at_k": round(self.recall_at_k, 4),
            "mrr": round(self.mrr, 4),
            "rerank_precision": round(self.rerank_precision, 4),
            "false_abstain": round(self.false_abstain, 4),
            "false_confidence": round(self.false_confidence, 4),
            "confidence_coverage": round(self.confidence_coverage, 4),
            "by_kind": {kind: round(value, 4) for kind, value in sorted(self.by_kind.items())},
        }


def load_questions(path: Path) -> list[Question]:
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise EvalError(f"{path} must be a mapping with a `questions` key.", remedy="See §7.")
    entries: object = cast(dict[str, Any], raw).get("questions") or []
    if not isinstance(entries, list):
        raise EvalError(f"{path}: `questions` must be a list.", remedy="See §7.")

    questions: list[Question] = []
    for entry in cast(list[Any], entries):
        if not isinstance(entry, dict):
            raise EvalError(f"{path}: every question must be a mapping.", remedy="See §7.")
        item = cast(dict[str, Any], entry)
        filters_raw = cast(dict[str, Any], item.get("filters") or {})
        questions.append(
            Question(
                question=str(item["question"]),
                kind=str(item.get("kind", "lexical")),
                expect=tuple(str(path_) for path_ in item.get("expect", ())),
                filters=Filters(
                    tags=tuple(filters_raw.get("tags", ())),
                    path_prefix=filters_raw.get("path_prefix"),
                    source_type=filters_raw.get("source_type"),
                ),
                hops=tuple(
                    Hop(query=str(hop["query"]), expect=str(hop["expect"]))
                    for hop in cast(list[Any], item.get("hops", ()))
                ),
            )
        )
    return questions


def evaluate(
    connection: sqlite3.Connection,
    manifest: Manifest,
    questions: Sequence[Question],
    *,
    backend: EmbeddingBackend,
    reranker: Reranker | None,
    k: int = DEFAULT_K,
) -> tuple[Metrics, list[Outcome]]:
    outcomes = [
        _run_question(connection, manifest, question, backend=backend, reranker=reranker, k=k)
        for question in questions
    ]
    return _score(outcomes, k=k), outcomes


def _run_question(
    connection: sqlite3.Connection,
    manifest: Manifest,
    question: Question,
    *,
    backend: EmbeddingBackend,
    reranker: Reranker | None,
    k: int,
) -> Outcome:
    followed = 0
    for hop in question.hops[:-1]:
        result = search(
            connection, manifest, hop.query, backend=backend, reranker=reranker, limit=k
        )
        if hop.expect in {passage.path for passage in result.passages}:
            followed += 1

    final_query = question.hops[-1].query if question.hops else question.question
    result = search(
        connection,
        manifest,
        final_query,
        backend=backend,
        reranker=reranker,
        filters=question.filters,
        limit=k,
    )

    retrieved: list[str] = []
    for passage in result.passages:
        if passage.path not in retrieved:
            retrieved.append(passage.path)

    # The last hop is a hop like any other: its own document has to be found by its own query.
    # It is scored here rather than in the loop above only because its search carries the
    # question's filters and is the one whose ranking feeds MRR.
    if question.hops and question.hops[-1].expect in retrieved:
        followed += 1

    hit_rank = next(
        (index + 1 for index, path in enumerate(retrieved) if path in question.expect), None
    )
    return Outcome(
        question=question,
        retrieved=tuple(retrieved),
        confidence=result.confidence,
        hit_rank=hit_rank,
        hops_followed=followed,
    )


def _score(outcomes: Sequence[Outcome], *, k: int) -> Metrics:
    answerable = [outcome for outcome in outcomes if outcome.question.answerable]
    unanswerable = [outcome for outcome in outcomes if not outcome.question.answerable]

    recall = _ratio(sum(1 for o in answerable if o.hit), len(answerable))
    mrr = _ratio(
        sum(1.0 / o.hit_rank for o in answerable if o.hit_rank is not None), len(answerable)
    )
    top1 = _ratio(sum(1 for o in answerable if o.hit_rank == 1), len(answerable))

    # An answerable question the system found, but reported as low confidence anyway.
    false_abstain = _ratio(
        sum(1 for o in answerable if o.hit and o.confidence == LOW), len(answerable)
    )
    # A question with no answer in the corpus, reported as high confidence.
    false_confidence = _ratio(
        sum(1 for o in unanswerable if o.confidence == HIGH), len(unanswerable)
    )

    by_kind: dict[str, float] = {}
    for kind in sorted({o.question.kind for o in outcomes}):
        group = [o for o in outcomes if o.question.kind == kind]
        if kind == "no-answer":
            by_kind[kind] = _ratio(sum(1 for o in group if not o.hit), len(group))
        else:
            by_kind[kind] = _ratio(sum(1 for o in group if o.hit), len(group))

    return Metrics(
        questions=len(outcomes),
        recall_at_k=recall,
        mrr=mrr,
        rerank_precision=top1,
        false_abstain=false_abstain,
        false_confidence=false_confidence,
        confidence_coverage=_ratio(
            sum(1 for o in outcomes if o.confidence != UNKNOWN), len(outcomes)
        ),
        by_kind=by_kind,
    )


def _ratio(numerator: float, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def run(kb_root: Path, *, questions_path: Path | None = None, k: int = DEFAULT_K) -> Metrics:
    """Evaluate a KB against its golden set, loading whatever backend its manifest names."""
    from pinakes import manifest as manifest_module

    manifest = manifest_module.load(kb_root)
    path = questions_path or (kb_root / "eval" / "questions.yaml")
    questions = load_questions(path)
    if not questions:
        raise EvalError(
            f"{path} contains no questions.",
            remedy="A scoreboard with nothing on it cannot make a retrieval change decidable (§7).",
        )

    backend = load_backend(manifest.embedding)
    reranker = load_reranker(manifest.rerank) if manifest.retrieval.rerank == "local" else None
    connection = store.connect_ro(manifest.index_path)
    try:
        metrics, _ = evaluate(
            connection, manifest, questions, backend=backend, reranker=reranker, k=k
        )
    finally:
        connection.close()
    return metrics


def compare(metrics: Metrics, baseline: dict[str, Any], *, tolerance: float = 0.02) -> list[str]:
    """Regressions beyond `tolerance`: lower is better for the error rates, higher for the rest."""
    current = metrics.as_dict()
    regressions: list[str] = []
    for name in ("recall_at_k", "mrr", "rerank_precision"):
        before, after = float(baseline.get(name, 0.0)), float(current[name])
        if after < before - tolerance:
            regressions.append(f"{name}: {before:.3f} -> {after:.3f}")
    for name in ("false_abstain", "false_confidence"):
        before, after = float(baseline.get(name, 1.0)), float(current[name])
        if after > before + tolerance:
            regressions.append(f"{name}: {before:.3f} -> {after:.3f} (higher is worse)")

    # Losing the ability to *say* anything is a regression too: the error rates would improve to a
    # meaningless zero while the system got quieter, not better.
    before_coverage = float(baseline.get("confidence_coverage", 0.0))
    if metrics.confidence_coverage < before_coverage - tolerance:
        regressions.append(
            f"confidence_coverage: {before_coverage:.3f} -> {metrics.confidence_coverage:.3f}"
        )

    # Per-class, because an aggregate hides the trade. A change that lifts one kind and drops
    # another by the same amount moves `recall_at_k` by almost nothing, and that is exactly the
    # shape a graph channel has: gains on multi-hop paid for out of simple lookup (§7).
    before_kinds = baseline.get("by_kind")
    if isinstance(before_kinds, dict):
        for kind, before_value in sorted(cast(dict[str, Any], before_kinds).items()):
            after_kind = metrics.by_kind.get(kind)
            if after_kind is None:
                regressions.append(f"by_kind[{kind}]: the class vanished from the golden set")
            elif after_kind < float(before_value) - tolerance:
                regressions.append(
                    f"by_kind[{kind}]: {float(before_value):.3f} -> {after_kind:.3f}"
                )

    # A set that shrank scores better by losing its hard questions, and every rate above would
    # improve while the system got worse.
    before_questions = int(baseline.get("questions", 0))
    if metrics.questions < before_questions:
        regressions.append(
            f"questions: {before_questions} -> {metrics.questions} (the golden set shrank)"
        )
    return regressions


def write_baseline(path: Path, metrics: Metrics) -> None:
    path.write_text(json.dumps(metrics.as_dict(), indent=2) + "\n", encoding="utf-8")


def read_baseline(path: Path) -> dict[str, Any]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise EvalError(
            f"{path} is not a baseline.", remedy="Regenerate it with `--write-baseline`."
        )
    return cast(dict[str, Any], raw)


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m pinakes.eval <kb> [--baseline path] [--write-baseline]`."""
    import argparse

    parser = argparse.ArgumentParser(prog="pinakes.eval", description=__doc__)
    parser.add_argument("kb", type=Path, help="KB root to evaluate")
    parser.add_argument("--questions", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("-k", type=int, default=DEFAULT_K)
    args = parser.parse_args(argv)

    metrics = run(args.kb, questions_path=args.questions, k=args.k)
    print(json.dumps(metrics.as_dict(), indent=2))

    baseline_path = args.baseline or (args.kb / "eval" / "baseline.json")
    if args.write_baseline:
        write_baseline(baseline_path, metrics)
        print(f"\nwrote {baseline_path}")
        return 0

    if not baseline_path.exists():
        print(f"\nno baseline at {baseline_path}; nothing to compare against.")
        return 0

    regressions = compare(metrics, read_baseline(baseline_path))
    if regressions:
        print("\nregressions:")
        for line in regressions:
            print(f"  {line}")
        return 1
    print("\nno regression against the baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
