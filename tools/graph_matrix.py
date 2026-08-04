"""G5's eval matrix — the three gate legs, the two arms, and the two reported knobs.

**One configuration is gated; everything else here is reported.** Three variables against one
threshold is not a decision procedure, so `tools/graph_gate.py` reads exactly three of the legs
below and the rest go into `docs/STATUS.md` beside the headline.

| leg | what it is | read by |
|---|---|---|
| `off` | today's two-list fusion, measured at **G5's own HEAD** | the gate (`--before`) |
| `expand` | every kind, authored included — what ships | the gate (`--after-with`) |
| `expand-no-authored` | `--drop authored`, the guard | the gate (`--after-without`) |
| `expand-no-sibling` | the arm the go decision added: 99.2% of the RFC graph's mass | reported |
| `expand-no-parent-child` | the arm the arity decision added | reported |
| `expand-no-link-distance` | APPROACH §4A's link-distance rerank, removed | reported |
| `expand-in-degree` | APPROACH §4A's in-degree salience prior, added | reported |

**Every leg is one run of the same binary against one index.** The channel's setting and its kind
selection are read at query time, so nothing here re-syncs, re-derives or rebuilds — which is the
only way the legs can be compared at all: G3 bumped `schema_version`, and a leg measured before
that bump would carry every rebuild-induced flip into the gate's arithmetic.

## Which edge kind carried a lifting path

For every question that the `off` leg missed and a leg hit, this reports the `via` of the channel
candidates that reached the question's own evidence documents. That is the only thing in the output
able to tell a result carried by `shared-tag` and `co-located` over a vocabulary and a directory
layout **the corpus author chose** from one carried by `sibling` or `in-section`. The first is a
weaker claim, and `docs/STATUS.md` records it as such.

Usage:

    python3 tools/graph_matrix.py --kb path/to/kb --out eval/g5 [-k 5] [--legs off,expand]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pinakes import manifest as manifest_module
from pinakes import store
from pinakes.embed import load_backend, load_reranker
from pinakes.eval import (
    DEFAULT_K,
    Metrics,
    Outcome,
    Question,
    evaluate,
    load_questions,
    write_outcomes,
)
from pinakes.eval import (
    header as eval_header,
)
from pinakes.graph.channel import GATED_RANKING, Ranking
from pinakes.graph.edges import AUTHORED, select_kinds
from pinakes.manifest import Manifest
from pinakes.search import fused_candidates

GATED_CLASS = "multi-hop"


@dataclass(frozen=True, slots=True)
class LegSpec:
    name: str
    channel: str
    drop: tuple[str, ...] = ()
    ranking: Ranking = GATED_RANKING
    gated: bool = False
    """Whether `tools/graph_gate.py` reads this leg. Three do; the rest are reported."""


LEGS: tuple[LegSpec, ...] = (
    LegSpec("off", "off", gated=True),
    LegSpec("expand", "expand", gated=True),
    LegSpec("expand-no-authored", "expand", drop=(AUTHORED,), gated=True),
    LegSpec("expand-no-sibling", "expand", drop=("sibling",)),
    LegSpec("expand-no-parent-child", "expand", drop=("parent-child",)),
    LegSpec("expand-no-link-distance", "expand", ranking=Ranking(link_distance=False)),
    LegSpec("expand-in-degree", "expand", ranking=Ranking(in_degree_salience=True)),
)


@dataclass(frozen=True, slots=True)
class LegResult:
    spec: LegSpec
    metrics: Metrics
    outcomes: tuple[Outcome, ...]
    seconds: float
    per_query_ms: float

    @property
    def by_id(self) -> dict[str, Outcome]:
        return {outcome.question.id: outcome for outcome in self.outcomes}


def run_leg(root: Path, questions: Sequence[Question], spec: LegSpec, *, k: int) -> LegResult:
    base = manifest_module.load(root)
    manifest = replace(base, retrieval=replace(base.retrieval, graph_channel=spec.channel))
    backend = load_backend(manifest.embedding)
    reranker = load_reranker(manifest.rerank) if manifest.retrieval.rerank == "local" else None
    connection = store.connect_ro(manifest.index_path)
    started = time.perf_counter()
    try:
        metrics, outcomes = evaluate(
            connection,
            manifest,
            questions,
            backend=backend,
            reranker=reranker,
            k=k,
            edge_kinds=select_kinds(drop=spec.drop),
            ranking=spec.ranking,
        )
    finally:
        connection.close()
    elapsed = time.perf_counter() - started
    # One "query" is one hop, because that is what actually runs the pipeline; a multi-hop
    # question is two or three of them and reporting per *question* would understate the cost of
    # the thing being measured by exactly the hop count.
    hops = sum(max(1, len(question.hops)) for question in questions)
    return LegResult(
        spec=spec,
        metrics=metrics,
        outcomes=tuple(outcomes),
        seconds=elapsed,
        per_query_ms=1000.0 * elapsed / hops if hops else 0.0,
    )


def leg_header(manifest: Manifest, spec: LegSpec, *, k: int) -> dict[str, Any]:
    """The artifact header, written by `eval.header` itself rather than reproduced here.

    The gate identifies a leg by its header — `graph_channel` and the edge-set variant — so a
    second header function beside `eval`'s is a second way to label a leg wrongly, and the two
    would drift the first time a retrieval field is added.
    """
    return eval_header(
        replace(manifest, retrieval=replace(manifest.retrieval, graph_channel=spec.channel)),
        k=k,
        edge_kinds=select_kinds(drop=spec.drop),
        ranking=spec.ranking,
    )


def lifting_kinds(root: Path, question: Question, spec: LegSpec) -> dict[str, list[list[str]]]:
    """Which edge kinds reached this question's evidence documents, per hop query.

    Re-runs the fusion stage — not the whole search — for each of the question's queries and reads
    `Fused.graph`, which is the walk's own record of the path it took. Nothing is recomputed from
    the edge set: a second traversal here could disagree with the one that produced the result.
    """
    base = manifest_module.load(root)
    manifest = replace(base, retrieval=replace(base.retrieval, graph_channel=spec.channel))
    backend = load_backend(manifest.embedding)
    connection = store.connect_ro(manifest.index_path)
    found: dict[str, list[list[str]]] = {}
    try:
        wanted = _document_ids(connection, question.expect)
        queries = [hop.query for hop in question.hops] or [question.question]
        for query in queries:
            fused = fused_candidates(
                connection,
                manifest,
                query,
                backend=backend,
                edge_kinds=select_kinds(drop=spec.drop),
                ranking=spec.ranking,
            )
            for reached in fused.graph:
                if reached.doc_id in wanted:
                    found.setdefault(wanted[reached.doc_id], []).append(list(reached.via))
    finally:
        connection.close()
    return found


def _document_ids(connection: Any, paths: Sequence[str]) -> dict[str, str]:
    if not paths:
        return {}
    placeholders = ",".join("?" for _ in paths)
    return {
        str(row[0]): str(row[1])
        for row in connection.execute(
            f"SELECT id, path FROM documents WHERE path IN ({placeholders})", list(paths)
        )
    }


def report(results: Sequence[LegResult], *, gated_class: str) -> str:
    """The table. **Without the `off` leg there is nothing to compare against**, so the discordant
    columns are blank rather than the function raising — `--legs` exists for a partial re-run, and
    a tool that crashes on its own documented flag is a tool that loses the run it just paid for.
    """
    baseline = next((result for result in results if result.spec.name == "off"), None)
    lines = [
        "leg                       questions  recall@k    mrr   "
        f"{gated_class:>10}  improved  regressed   ms/query",
    ]
    for result in results:
        improved, regressed = discordant(baseline, result, gated_class) if baseline else ([], [])
        lines.append(
            f"{result.spec.name:<24}  {result.metrics.questions:>9}  "
            f"{result.metrics.recall_at_k:>8.4f}  {result.metrics.mrr:>5.3f}  "
            f"{result.metrics.by_kind.get(gated_class, 0.0):>10.4f}  "
            f"{len(improved) if baseline else '—':>8}  "
            f"{len(regressed) if baseline else '—':>9}  {result.per_query_ms:>9.1f}"
        )
    return "\n".join(lines)


def discordant(
    baseline: LegResult, result: LegResult, gated_class: str
) -> tuple[list[str], list[str]]:
    before, after = baseline.by_id, result.by_id
    improved = sorted(
        identifier
        for identifier, outcome in after.items()
        if outcome.question.kind == gated_class and outcome.hit and not before[identifier].hit
    )
    regressed = sorted(
        identifier
        for identifier, outcome in after.items()
        if outcome.question.kind == gated_class and not outcome.hit and before[identifier].hit
    )
    return improved, regressed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="graph_matrix", description=__doc__)
    parser.add_argument("--kb", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--questions", type=Path, default=None)
    parser.add_argument("-k", type=int, default=DEFAULT_K)
    parser.add_argument(
        "--legs", default=None, help="comma-separated subset of the legs, for a partial re-run"
    )
    parser.add_argument("--no-lifting-kinds", action="store_true")
    args = parser.parse_args(argv)

    root: Path = args.kb
    manifest = manifest_module.load(root)
    questions = load_questions(args.questions or (root / "eval" / "questions.yaml"))
    if not questions:
        print("no questions — nothing to measure.")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    wanted = set(args.legs.split(",")) if args.legs else {spec.name for spec in LEGS}
    results: list[LegResult] = []
    for spec in LEGS:
        if spec.name not in wanted:
            continue
        print(f"running {spec.name} …", flush=True)
        result = run_leg(root, questions, spec, k=args.k)
        write_outcomes(
            args.out / f"{spec.name}.json",
            [outcome.row() for outcome in result.outcomes],
            leg_header(manifest, spec, k=args.k),
        )
        results.append(result)

    print()
    print(report(results, gated_class=GATED_CLASS))

    summary: dict[str, Any] = {
        "kb": str(root),
        "k": args.k,
        "gated_class": GATED_CLASS,
        "legs": {},
    }
    baseline = next((r for r in results if r.spec.name == "off"), None)
    for result in results:
        improved, regressed = discordant(baseline, result, GATED_CLASS) if baseline else ([], [])
        entry: dict[str, Any] = {
            "gated": result.spec.gated,
            "graph_channel": result.spec.channel,
            "dropped": list(result.spec.drop),
            "ranking": {
                "link_distance": result.spec.ranking.link_distance,
                "in_degree_salience": result.spec.ranking.in_degree_salience,
            },
            "metrics": result.metrics.as_dict(),
            "seconds": round(result.seconds, 3),
            "ms_per_query": round(result.per_query_ms, 2),
            "improved": improved,
            "regressed": regressed,
        }
        if improved and not args.no_lifting_kinds:
            by_question: dict[str, dict[str, list[list[str]]]] = {
                identifier: {} for identifier in improved
            }
            for question in questions:
                if question.id in by_question:
                    by_question[question.id] = lifting_kinds(root, question, result.spec)
            entry["lifting_kinds"] = by_question
        summary["legs"][result.spec.name] = entry

    (args.out / "matrix.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out / 'matrix.json'} and one artifact per leg")

    latencies = {r.spec.name: r.per_query_ms for r in results}
    if "off" in latencies and "expand" in latencies:
        print(
            f"latency: off {latencies['off']:.1f} ms/query, "
            f"expand {latencies['expand']:.1f} ms/query "
            f"({latencies['expand'] / latencies['off']:.2f}x)"
        )
    print(f"median across legs: {statistics.median(latencies.values()):.1f} ms/query")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
