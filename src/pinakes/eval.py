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

**Aggregates are not the only output** (G2). `write_baseline` records six rates; a paired
before/after test over the *same* questions needs to know which ones moved, and an aggregate cannot
say. So every run can also emit a per-question artifact — one row per question, keyed on a stable
`id` — and `score_rows` recomputes every metric from those rows alone. Two consequences worth
stating, because both are load-bearing:

* A committed artifact makes the golden set's per-question history checkable **offline**, with no
  model weights: `tests/test_eval.py` re-scores the committed rows and compares them against the
  preserved pre-growth baseline.
* The row schema is fixed here and the *values* belong to whichever run wrote them. A file's header
  records the configuration it was produced under, because otherwise two artifacts from two
  different configurations are indistinguishable on inspection.
"""

import json
import re
import sqlite3
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML, YAMLError
from ruamel.yaml.constructor import DuplicateKeyError

from pinakes import store
from pinakes.embed import EmbeddingBackend, Reranker, load_backend, load_reranker
from pinakes.errors import EvalError
from pinakes.graph.edges import ALL_KINDS, select_kinds
from pinakes.manifest import Manifest
from pinakes.search import HIGH, LOW, UNKNOWN, Filters, search

DEFAULT_K = 5

NO_ANSWER = "no-answer"

KINDS = frozenset(
    {
        "lexical",
        "simple-lookup",
        "paraphrase",
        "filter",
        "multi-hop",
        NO_ANSWER,
    }
)
"""What a question's `kind` may be.

`simple-lookup` is the newest and is the *control* class (APPROACH §9): plainly-phrased factual
questions the two-list pipeline already answers, carried so that a change which lifts `multi-hop`
by damaging ordinary lookup is visible per class rather than averaged away. It is deliberately not
a synonym for `lexical`, which is authored to share words with its document on purpose.

Validated rather than defaulted (G2). `kind` used to default to `"lexical"` when absent, which put
unclassified questions into a class they were never written for and made `by_kind["lexical"]` a
number about two different things.
"""

OUTCOMES_SCHEMA = 1
"""Version of the per-question artifact's *shape*, bumped when a row gains or loses a field.

Not the index's `schema_version` and not a release: an artifact written by an older Pinakes must be
recognisable as such by a reader that has since changed the row.
"""

EMPTY_SET_SKIP = (
    "no questions in {path} — skipping the evaluation, not failing it. A template scaffolds an "
    "empty docs/, so it cannot ship a golden set naming documents that do not exist (§7)."
)
"""Printed when the golden set is empty. A gate that cannot run says so and is still a gate.

This is deliberately *not* an error any more. `pnk init` writes `questions: []`, so every freshly
scaffolded KB failed `make eval` by construction. What stops an emptied golden set from passing CI
silently is the other end: `test_the_committed_golden_set_is_well_formed` asserts the committed set
has questions in it, so this path can only be reached by a KB that never had one.
"""

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _yaml() -> YAML:
    """A fresh safe loader per call — the golden set is data, never a document to round-trip.

    Fresh for the same reason `sidecar.py`'s is: ruamel keeps the `%YAML` directive from the last
    `load()` on the instance, so one golden set carrying one would silently change how the next is
    parsed. Read-only here and so lower stakes than a sidecar, but it is the same defect and the
    same one-line prevention.

    Duplicate keys are mapped the same way in both places: `load_questions` has no `try/except` of
    its own, so a repeated question key would otherwise escape `make eval` as a bare
    `DuplicateKeyError`.
    """
    return YAML(typ="safe")


@dataclass(frozen=True, slots=True)
class Hop:
    query: str
    expect: str


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    """Stable across runs, and the only thing that pairs a before row with an after row.

    Authored in the golden set. Derived from the question text when absent, which keeps an existing
    hand-written `questions.yaml` loadable — at the cost the derivation cannot avoid: reword the
    question and its id moves, so a paired comparison sees one question leave and another arrive.
    That is why the committed set writes its ids out.
    """

    question: str
    kind: str
    expect: tuple[str, ...] = ()
    filters: Filters = field(default_factory=Filters)
    hops: tuple[Hop, ...] = ()

    @property
    def answerable(self) -> bool:
        return self.kind != NO_ANSWER


@dataclass(frozen=True, slots=True)
class OutcomeRow:
    """One question's result, and everything `score_rows` needs to recompute every metric.

    Deliberately narrow: no retrieved paths, no query text. It is a comparison key, not a debugging
    log — and a row that carried the retrieved list would turn a per-question artifact into a
    second copy of the corpus.
    """

    id: str
    kind: str
    hit: bool
    hit_rank: int | None
    confidence: str

    @property
    def answerable(self) -> bool:
        return self.kind != NO_ANSWER

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "hit": self.hit,
            "hit_rank": self.hit_rank,
            "confidence": self.confidence,
        }


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

    def row(self) -> OutcomeRow:
        return OutcomeRow(
            id=self.question.id,
            kind=self.question.kind,
            hit=self.hit,
            hit_rank=self.hit_rank,
            confidence=self.confidence,
        )


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
    try:
        raw: object = _yaml().load(path.read_text(encoding="utf-8"))
    except DuplicateKeyError as exc:
        raise EvalError(
            f"{path} repeats a question key: {str(exc).splitlines()[0]}",
            remedy="Delete the duplicate — which of the two was meant is not recoverable.",
        ) from exc
    except YAMLError as exc:
        raise EvalError(
            f"{path} is not valid YAML: {exc}",
            remedy="Fix the syntax the parser names, then re-run `make eval`.",
        ) from exc
    if not isinstance(raw, dict):
        raise EvalError(f"{path} must be a mapping with a `questions` key.", remedy="See §7.")
    document = cast(dict[str, Any], raw)
    # An *absent* `questions` key is still an error, and the distinction is the whole safety of the
    # empty-set skip: `questions: []` is a template deliberately shipping none, while a file with
    # no such key is a golden set with a typo in it — and under the skip it would otherwise pass
    # `make eval` in silence.
    if "questions" not in document:
        raise EvalError(
            f"{path} has no `questions` key.",
            remedy="A golden set with no questions is written `questions: []`, not omitted (§7).",
        )
    entries: object = document["questions"] or []
    if not isinstance(entries, list):
        raise EvalError(f"{path}: `questions` must be a list.", remedy="See §7.")

    questions: list[Question] = []
    seen: dict[str, str] = {}
    for entry in cast(list[Any], entries):
        if not isinstance(entry, dict):
            raise EvalError(f"{path}: every question must be a mapping.", remedy="See §7.")
        item = cast(dict[str, Any], entry)
        text = str(item["question"])
        identifier = _identifier(item, text, path)
        if identifier in seen:
            raise EvalError(
                f"{path}: two questions share the id {identifier!r} — "
                f"{seen[identifier]!r} and {text!r}.",
                remedy=(
                    "Give one of them its own `id`. An id is what pairs a before row with an "
                    "after row, so a repeated one silently drops a question from every comparison."
                ),
            )
        seen[identifier] = text
        filters_raw = cast(dict[str, Any], item.get("filters") or {})
        questions.append(
            Question(
                id=identifier,
                question=text,
                kind=_kind(item, text, path),
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


def _identifier(item: dict[str, Any], text: str, path: Path) -> str:
    raw: object = item.get("id")
    if raw is None:
        return _slug(text)
    if not isinstance(raw, str) or not raw.strip():
        raise EvalError(
            f"{path}: the id of {text!r} must be a non-empty string, not {raw!r}.",
            remedy="Ids are compared as strings; YAML will read a bare `id: 12` as an integer.",
        )
    return raw


def _slug(text: str) -> str:
    """A readable, deterministic id for a question that did not author one.

    Not a hash: a comparison whose keys are opaque is one nobody reads. Truncated, because the id
    is a key and a whole sentence makes an artifact harder to scan, not safer — `load_questions`
    refuses a collision outright rather than relying on the slug to be unique.
    """
    slug = _SLUG_STRIP.sub("-", text.lower()).strip("-")
    return slug[:60].rstrip("-") or "question"


def _kind(item: dict[str, Any], text: str, path: Path) -> str:
    """Validated, never defaulted (G2).

    An absent `kind` used to become `"lexical"`. That is not a safe default: it is a claim about
    how a question was authored, and a wrong one puts a question into a class whose `by_kind` score
    then measures two different things.
    """
    raw: object = item.get("kind")
    known = ", ".join(sorted(KINDS))
    if raw is None:
        raise EvalError(
            f"{path}: {text!r} has no `kind`.",
            remedy=f"Give it one of: {known}. `kind` is what per-class reporting groups on (§7).",
        )
    if not isinstance(raw, str) or raw not in KINDS:
        raise EvalError(
            f"{path}: {text!r} has an unknown kind {raw!r}.",
            remedy=f"Use one of: {known}.",
        )
    return raw


def evaluate(
    connection: sqlite3.Connection,
    manifest: Manifest,
    questions: Sequence[Question],
    *,
    backend: EmbeddingBackend,
    reranker: Reranker | None,
    k: int = DEFAULT_K,
    edge_kinds: Collection[str] | None = None,
) -> tuple[Metrics, list[Outcome]]:
    outcomes = [
        _run_question(
            connection,
            manifest,
            question,
            backend=backend,
            reranker=reranker,
            k=k,
            edge_kinds=edge_kinds,
        )
        for question in questions
    ]
    return score_rows([outcome.row() for outcome in outcomes]), outcomes


def _run_question(
    connection: sqlite3.Connection,
    manifest: Manifest,
    question: Question,
    *,
    backend: EmbeddingBackend,
    reranker: Reranker | None,
    k: int,
    edge_kinds: Collection[str] | None = None,
) -> Outcome:
    followed = 0
    for hop in question.hops[:-1]:
        result = search(
            connection,
            manifest,
            hop.query,
            backend=backend,
            reranker=reranker,
            limit=k,
            edge_kinds=edge_kinds,
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
        edge_kinds=edge_kinds,
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


def score_rows(rows: Sequence[OutcomeRow]) -> Metrics:
    """Every metric, from per-question rows alone.

    The whole scoreboard is a function of five fields per question, so a committed artifact can be
    re-scored with no index, no weights and no network — which is what lets a test check that
    growing the golden set left the questions already in it scoring exactly what they scored
    before (G2).
    """
    answerable = [row for row in rows if row.answerable]
    unanswerable = [row for row in rows if not row.answerable]

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
    for kind in sorted({o.kind for o in rows}):
        group = [o for o in rows if o.kind == kind]
        if kind == NO_ANSWER:
            by_kind[kind] = _ratio(sum(1 for o in group if not o.hit), len(group))
        else:
            by_kind[kind] = _ratio(sum(1 for o in group if o.hit), len(group))

    return Metrics(
        questions=len(rows),
        recall_at_k=recall,
        mrr=mrr,
        rerank_precision=top1,
        false_abstain=false_abstain,
        false_confidence=false_confidence,
        confidence_coverage=_ratio(sum(1 for o in rows if o.confidence != UNKNOWN), len(rows)),
        by_kind=by_kind,
    )


def _ratio(numerator: float, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def run(
    kb_root: Path,
    *,
    questions_path: Path | None = None,
    k: int = DEFAULT_K,
    drop: Collection[str] = (),
) -> tuple[Metrics, list[OutcomeRow], dict[str, Any]] | None:
    """Evaluate a KB against its golden set, loading whatever backend its manifest names.

    `None` when the golden set is empty — a skip, not a failure. The caller prints
    `EMPTY_SET_SKIP`; a library function that printed its own reason would do it from inside
    someone else's stdout.
    """
    from pinakes import manifest as manifest_module

    manifest = manifest_module.load(kb_root)
    path = questions_path or (kb_root / "eval" / "questions.yaml")
    questions = load_questions(path)
    if not questions:
        return None

    # Refused here rather than at the walk, so a mistyped `--drop sibbling` cannot produce a green
    # run of the arm nobody measured (`edges.select_kinds`). Computed even when the channel is off,
    # because the header records it either way and a typo must not survive to the artifact.
    edge_kinds = select_kinds(drop=drop)

    backend = load_backend(manifest.embedding)
    reranker = load_reranker(manifest.rerank) if manifest.retrieval.rerank == "local" else None
    connection = store.connect_ro(manifest.index_path)
    try:
        metrics, outcomes = evaluate(
            connection,
            manifest,
            questions,
            backend=backend,
            reranker=reranker,
            k=k,
            edge_kinds=edge_kinds,
        )
    finally:
        connection.close()
    return (
        metrics,
        [outcome.row() for outcome in outcomes],
        _header(manifest, k=k, edge_kinds=edge_kinds),
    )


def _header(
    manifest: Manifest, *, k: int, edge_kinds: Collection[str] = ALL_KINDS
) -> dict[str, Any]:
    """What an artifact was produced under — every setting that can move a row.

    Two artifacts compared against each other must have been produced by the same pipeline in the
    same configuration, and nothing else in the file says so: rows carry ids and verdicts, and a
    before file and an after file are otherwise indistinguishable on inspection.

    Explicit rather than a dump of `manifest.retrieval`, so that adding a retrieval field is a
    decision about this header rather than a silent change to every artifact's bytes.

    **`graph_channel` and `edge_kinds` are the two G5 added, and they are not one field.** The
    gate's three legs are `off`, `expand` without authored edges and `expand` with them: the first
    differs from the other two in the channel setting and the last two differ only in the edge-set
    variant, so an artifact recording one of the pair would leave two of the three legs
    indistinguishable on inspection — the exact failure this header exists to prevent.
    """
    settings = manifest.retrieval
    return {
        "graph_channel": settings.graph_channel,
        "edge_kinds": sorted(edge_kinds),
        "dropped": sorted(set(ALL_KINDS) - set(edge_kinds)),
        "schema": OUTCOMES_SCHEMA,
        "k": k,
        "embedding": {
            "provider": manifest.embedding.provider,
            "model": manifest.embedding.model,
            "dim": manifest.embedding.dim,
        },
        "rerank": (
            {"provider": manifest.rerank.provider, "model": manifest.rerank.model}
            if settings.rerank == "local"
            else None
        ),
        "retrieval": {
            "candidates_per_source": settings.candidates_per_source,
            "fusion": settings.fusion,
            "fusion_top_k": settings.fusion_top_k,
            "final_k": settings.final_k,
            "rerank": settings.rerank,
            "vector_tier": settings.vector_tier,
        },
    }


def write_outcomes(path: Path, rows: Sequence[OutcomeRow], header: dict[str, Any]) -> None:
    """The per-question artifact, rows sorted by id so a diff shows movement, not reordering."""
    document = dict(header) | {
        "questions": [row.as_dict() for row in sorted(rows, key=lambda row: row.id)]
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def read_outcomes(path: Path) -> tuple[dict[str, Any], list[OutcomeRow]]:
    """The header and the rows. Refuses a file whose rows are not rows — never a partial read."""
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(
        cast(dict[str, Any], raw).get("questions"), list
    ):
        raise EvalError(
            f"{path} is not a per-question outcomes artifact.",
            remedy="Regenerate it with `python -m pinakes.eval <kb> --write-baseline`.",
        )
    document = cast(dict[str, Any], raw)
    rows: list[OutcomeRow] = []
    for entry in cast(list[Any], document["questions"]):
        if not isinstance(entry, dict):
            raise EvalError(f"{path}: every row must be a mapping.", remedy="Regenerate it.")
        item = cast(dict[str, Any], entry)
        # Named rather than indexed: every one of the five reaches a metric (`score_rows`), so a
        # row missing one is not a row that can be scored — and a bare `KeyError` out of a reader
        # that promises to refuse a malformed file is the promise not being kept.
        missing = [field_ for field_ in ("id", "kind", "hit", "confidence") if field_ not in item]
        if missing:
            raise EvalError(
                f"{path}: a row is missing {', '.join(missing)}.",
                remedy="Every field is read by `score_rows`. Regenerate the artifact.",
            )
        rank: object = item.get("hit_rank")
        rows.append(
            OutcomeRow(
                id=str(item["id"]),
                kind=str(item["kind"]),
                hit=bool(item["hit"]),
                hit_rank=None if rank is None else int(cast(int, rank)),
                confidence=str(item["confidence"]),
            )
        )
    header = {key: value for key, value in document.items() if key != "questions"}
    return header, rows


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
    parser.add_argument(
        "--outcomes",
        type=Path,
        default=None,
        help="where --write-baseline puts the per-question artifact "
        "(default <kb>/eval/outcomes.json)",
    )
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("-k", type=int, default=DEFAULT_K)
    parser.add_argument(
        "--drop",
        action="append",
        default=[],
        metavar="KIND",
        help=(
            "edge kind the graph channel may not walk, repeatable "
            f"({', '.join(ALL_KINDS)}). Ignored when graph_channel is off"
        ),
    )
    args = parser.parse_args(argv)

    result = run(args.kb, questions_path=args.questions, k=args.k, drop=args.drop)
    if result is None:
        print(EMPTY_SET_SKIP.format(path=args.questions or (args.kb / "eval" / "questions.yaml")))
        return 0
    metrics, rows, header = result
    print(json.dumps(metrics.as_dict(), indent=2))

    baseline_path = args.baseline or (args.kb / "eval" / "baseline.json")
    if args.write_baseline:
        # Both files or neither: a baseline and a per-question artifact from two different runs
        # would pair rows against aggregates that never described them.
        write_baseline(baseline_path, metrics)
        outcomes_path = args.outcomes or (args.kb / "eval" / "outcomes.json")
        write_outcomes(outcomes_path, rows, header)
        print(f"\nwrote {baseline_path}\nwrote {outcomes_path}")
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
