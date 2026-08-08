"""G5's gate, computed rather than argued — three legs, both p-values, a clause-by-clause verdict.

**The gate is an artifact, not a paragraph.** Without this file the plan's four clauses have no
checker, `tests/test_graph_channel.py`'s four gate tests have no subject, and "the numbers say
`expand` may default on" is a claim somebody made by hand.

## The three legs, and why the *before* leg is measured at G5's own HEAD

    off                      →  --before
    expand, without authored →  --after-without
    expand, with authored    →  --after-with

G2's per-question artifact owns the row *schema*; it never owns the row *values*. G3 bumped
`schema_version` and forced a rebuild between the two increments, and G1 exists precisely because a
rebuild's effect on per-question outcomes was unmeasured — one question in 41 changed answer under
ties. Comparing across that rebuild would attribute every rebuild-induced flip to the channel, and
at ~20 questions against a five-improvement threshold two spurious flips are a third of the
required signal. So every leg is produced by the binary under test, and this tool **refuses**
artifacts whose headers say otherwise: a leg is identified by its `graph_channel` and its edge-set
variant, never by its filename.

## Both runs bind, and the more conservative one licenses

The *without*-authored run is the anti-circularity guard: L1 hand-authored the links and G2 the
questions that traverse them, so a gate passed only with authored edges is evidence that a human's
links help, not that derived structure does. The *with*-authored run is **the configuration that
actually ships**, since G3 unions `links` into the channel at read time. An earlier revision made
only the first binding, which would license a default that does nothing in its shipped form through
three green clauses. **Both must reach p < 0.05, and `max(p)` is the licensing number.**

*"Without authored edges"* means every `links`-derived edge regardless of `origin` — a
`reverse-scan` row is hand-authored too, by the partner KB's human. That is one `--drop authored`,
and this tool checks the header says so.

**Cross-KB rows are inert in both directions** (G3: only a *local* document has a `doc` node), so
the with-authored leg measures **intra-KB authored links only**. Report that wherever both numbers
appear: a reader assuming every authored link is in play reads the with/without gap as weaker
evidence of circularity than it is.

## The four clauses

1. Exact one-sided sign test on the **discordant** questions of the gated class, p < 0.05, in both
   runs. Not "≥ 5 net": 8 improved / 3 regressed is also net +5 and gives p = 0.113.
2. No class regresses beyond `compare()`'s `tolerance` — at these class sizes, "no class loses a
   question". `by_kind["no-answer"]` is the *non-hit* rate, so its regression is a no-answer
   question **becoming** a hit; the arithmetic needs no special case, only the gloss does.
3. `false_abstain` does not rise **among questions that were already hits**. Converting misses into
   low-confidence hits raises the rate, and an unqualified clause would veto the very win clause 1
   demands — so the rise is decomposed and only the confidence-lost term is a regression.
4. The re-baseline absorbs no regression other than that term. `write_baseline` rewrites the whole
   dict in one statement, so rewriting it disarms **every** guard in it; all six of `compare()`'s
   families are checked here with the direction `eval.py` actually applies.

A result short of the table ships the channel `off`, with counts and p-value recorded, untuned.

Usage:

    python3 tools/graph_gate.py --before off.json \\
        --after-without expand-no-authored.json --after-with expand-authored.json \\
        [--baseline eval/baseline.json] [--rebaseline eval/baseline-expand.json] \\
        [--kind multi-hop] [--tolerance 0.02] [--json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pinakes.eval import OutcomeRow, compare, read_outcomes, score_rows
from pinakes.graph.edges import AUTHORED
from pinakes.search import LOW

ALPHA = 0.05
GATED_KIND = "multi-hop"
TOLERANCE = 0.02


# --------------------------------------------------------------------------------------------
# The statistic


def sign_test(improved: int, regressed: int) -> float:
    """Exact one-sided sign test on the discordant pairs — McNemar's exact form.

    p is the probability of seeing **at least** this many improvements out of the discordant
    pairs when improving and regressing are equally likely. No discordant pair at all is p = 1.0:
    nothing moved, so nothing was shown.
    """
    discordant = improved + regressed
    if discordant == 0:
        return 1.0
    return sum(math.comb(discordant, i) for i in range(improved, discordant + 1)) / 2**discordant


# --------------------------------------------------------------------------------------------
# Legs


@dataclass(frozen=True, slots=True)
class Leg:
    """One per-question artifact, with the identity its header claims."""

    path: Path
    header: dict[str, Any]
    rows: tuple[OutcomeRow, ...]

    @property
    def channel(self) -> str:
        return str(self.header.get("graph_channel", "(absent)"))

    @property
    def dropped(self) -> tuple[str, ...]:
        raw: object = self.header.get("dropped", [])
        if not isinstance(raw, list):
            return ()
        return tuple(str(item) for item in cast(list[Any], raw))

    @property
    def by_id(self) -> dict[str, OutcomeRow]:
        return {row.id: row for row in self.rows}

    def label(self) -> str:
        variant = f"drop {'+'.join(self.dropped)}" if self.dropped else "all kinds"
        return f"{self.channel} / {variant}"


def read_leg(path: Path) -> Leg:
    header, rows = read_outcomes(path)
    return Leg(path=path, header=header, rows=tuple(rows))


def check_identity(before: Leg, without: Leg, with_authored: Leg) -> list[str]:
    """Refuse a leg that is not the leg it was passed as. Headers, never filenames.

    Every complaint here is a *silent* wrong answer otherwise: a `--before` produced with the
    channel already on makes the gate compare a configuration against itself and report p = 1.0
    with no error; a `--after-without` that never dropped `authored` runs the anti-circularity
    guard on the circular configuration and passes it.
    """
    problems: list[str] = []
    if before.channel != "off":
        problems.append(f"--before {before.path} has graph_channel {before.channel!r}, not 'off'")
    for leg, name in ((without, "--after-without"), (with_authored, "--after-with")):
        if leg.channel != "expand":
            problems.append(f"{name} {leg.path} has graph_channel {leg.channel!r}, not 'expand'")
    if AUTHORED not in without.dropped:
        problems.append(
            f"--after-without {without.path} did not drop {AUTHORED!r} "
            f"(dropped: {list(without.dropped) or 'nothing'}) — that leg is the "
            "anti-circularity guard and this one is not it"
        )
    if AUTHORED in with_authored.dropped:
        problems.append(
            f"--after-with {with_authored.path} dropped {AUTHORED!r} — that leg is the "
            "configuration that actually ships, and it ships with authored links in the channel"
        )
    # The arms are reported beside the headline, never gated. Two legs differing in *which*
    # structural kind they dropped are two arms, not a with/without pair.
    structural = [
        frozenset(set(leg.dropped) - {AUTHORED}) for leg in (before, without, with_authored)
    ]
    if len(set(structural)) != 1:
        problems.append(
            "the three legs drop different structural kinds "
            f"({[sorted(kinds) for kinds in structural]}) — an arm is compared against its own "
            "before leg, never against the headline's"
        )
    # Everything else the header records and a comparison assumes constant. `k`, the embedding,
    # the reranker and the ranking knobs each move rows on their own, and `graph_matrix.py`
    # deliberately varies the last — so an arm accidentally passed as the headline's `--after-with`
    # would otherwise be scored against a before leg it shares no configuration with. Same
    # argument as the structural-kind check above, and it was missing.
    #
    # `chunking` is here for a sharper version of that reason, and `5993521` added it to
    # `eval.header` precisely so a leg could say what it was built under. A rechunk between legs
    # does not merely add noise — it changes *which texts exist*, so rows paired on `id` were
    # produced by searching two different corpora. Measured: `max_tokens` 510 against 480 moves
    # 63 of 1 858 chunk texts on one RFC, and `tools/eval_reproducibility_gate.py` exists because
    # one question in 41 moved across a plain rebuild. Whatever the gate was asked to measure, a
    # rechunk between its legs is reported as that.
    #
    # The whole block, with nothing excepted — unlike `tools/two_leg_gate.py`, which excepts
    # `chunking.metadata` because there that key *is* the independent variable. Nothing under
    # `chunking` is this gate's independent variable; `graph_channel` is, and it is checked above.
    for field_ in ("k", "embedding", "rerank", "ranking", "retrieval", "chunking"):
        values = [leg.header.get(field_) for leg in (before, without, with_authored)]
        if any(value != values[0] for value in values):
            problems.append(
                f"the three legs disagree on `{field_}` ({values}) — a leg is compared against a "
                "before leg produced by the same pipeline, or it is not compared at all"
            )
    for leg in (without, with_authored):
        missing = set(before.by_id) ^ set(leg.by_id)
        if missing:
            problems.append(
                f"{leg.path} and {before.path} do not cover the same questions "
                f"({len(missing)} unpaired: {sorted(missing)[:5]}) — a sign test pairs on id"
            )
    return problems


def check_baseline(
    baseline: Mapping[str, Any], rows: Sequence[OutcomeRow], where: str
) -> list[str]:
    """A baseline and an artifact from two different runs pair aggregates against rows that never
    described them. `eval.main` writes both or neither; a gate assembled by hand can still mix
    them, and every number below would be quietly about two runs."""
    derived = score_rows(rows).as_dict()
    differing = sorted(
        key
        for key in ("questions", "recall_at_k", "mrr", "false_abstain", "false_confidence")
        if key in baseline and baseline[key] != derived[key]
    )
    if not differing:
        return []
    return [
        f"{where}: the baseline disagrees with its own per-question rows on "
        f"{', '.join(differing)} — they are from two different runs"
    ]


# --------------------------------------------------------------------------------------------
# Clauses


@dataclass(frozen=True, slots=True)
class RunVerdict:
    label: str
    improved: tuple[str, ...]
    regressed: tuple[str, ...]
    p: float
    class_regressions: tuple[str, ...]
    confidence_lost: tuple[str, ...]
    newly_found_low: tuple[str, ...]
    other_regressions: tuple[str, ...]

    @property
    def clause1(self) -> bool:
        return self.p < ALPHA

    @property
    def clause2(self) -> bool:
        return not self.class_regressions

    @property
    def clause3(self) -> bool:
        return not self.confidence_lost

    @property
    def clause4(self) -> bool:
        return not self.other_regressions

    @property
    def passed(self) -> bool:
        return self.clause1 and self.clause2 and self.clause3 and self.clause4


@dataclass
class Verdict:
    runs: list[RunVerdict] = field(default_factory=list[RunVerdict])
    problems: list[str] = field(default_factory=list[str])

    @property
    def licensing_p(self) -> float:
        """The more conservative of the two — `max`, because both runs bind."""
        return max((run.p for run in self.runs), default=1.0)

    @property
    def passed(self) -> bool:
        return not self.problems and len(self.runs) == 2 and all(run.passed for run in self.runs)


def judge(before: Leg, after: Leg, *, kind: str, tolerance: float) -> RunVerdict:
    """One run's four clauses, against the same before leg."""
    baseline = before.by_id
    current = after.by_id

    improved = tuple(
        sorted(
            identifier
            for identifier, row in current.items()
            if row.kind == kind and row.hit and not baseline[identifier].hit
        )
    )
    regressed = tuple(
        sorted(
            identifier
            for identifier, row in current.items()
            if row.kind == kind and not row.hit and baseline[identifier].hit
        )
    )

    before_metrics = score_rows(before.rows).as_dict()
    regressions = compare(score_rows(after.rows), before_metrics, tolerance=tolerance)
    class_regressions = tuple(line for line in regressions if line.startswith("by_kind["))

    # Clause 3's decomposition. `false_abstain`'s numerator requires a hit, so a miss that becomes
    # a LOW-confidence hit raises the rate without anything having got worse; only a question that
    # was already a hit and *lost* confidence is a regression.
    confidence_lost = tuple(
        sorted(
            identifier
            for identifier, row in current.items()
            if row.hit
            and row.confidence == LOW
            and baseline[identifier].hit
            and baseline[identifier].confidence != LOW
        )
    )
    newly_found_low = tuple(
        sorted(
            identifier
            for identifier, row in current.items()
            if row.hit and row.confidence == LOW and not baseline[identifier].hit
        )
    )

    # Clause 4: every family `compare()` checks **except** the one clause 3 decomposes. A
    # re-baseline rewrites the whole dict, so anything left here would be disarmed silently.
    other_regressions = tuple(
        line
        for line in regressions
        if not line.startswith("by_kind[") and not line.startswith("false_abstain:")
    )
    return RunVerdict(
        label=after.label(),
        improved=improved,
        regressed=regressed,
        p=sign_test(len(improved), len(regressed)),
        class_regressions=class_regressions,
        confidence_lost=confidence_lost,
        newly_found_low=newly_found_low,
        other_regressions=other_regressions,
    )


def evaluate_gate(
    before: Leg,
    without: Leg,
    with_authored: Leg,
    *,
    kind: str = GATED_KIND,
    tolerance: float = TOLERANCE,
    baseline: Mapping[str, Any] | None = None,
    rebaseline: Mapping[str, Any] | None = None,
) -> Verdict:
    verdict = Verdict(problems=check_identity(before, without, with_authored))
    if baseline is not None:
        verdict.problems.extend(check_baseline(baseline, before.rows, "--baseline"))
    if rebaseline is not None:
        verdict.problems.extend(check_baseline(rebaseline, with_authored.rows, "--rebaseline"))
    if verdict.problems:
        return verdict
    verdict.runs = [
        judge(before, without, kind=kind, tolerance=tolerance),
        judge(before, with_authored, kind=kind, tolerance=tolerance),
    ]
    return verdict


# --------------------------------------------------------------------------------------------
# Reporting


def report(verdict: Verdict, *, kind: str) -> str:
    if verdict.problems:
        return "\n".join(
            [
                "the legs are not the legs they were passed as:",
                *(f"  - {problem}" for problem in verdict.problems),
            ]
        )

    lines = [f"G5's gate, on the `{kind}` class. Both runs bind; the more conservative licenses."]
    for run in verdict.runs:
        lines += [
            "",
            f"## {run.label}",
            f"  improved  {len(run.improved):>3}  {', '.join(run.improved) or '—'}",
            f"  regressed {len(run.regressed):>3}  {', '.join(run.regressed) or '—'}",
            f"  p = {run.p:.4f}   ({'<' if run.clause1 else '>='} {ALPHA})",
            f"  1 sign test          {_mark(run.clause1)}",
            f"  2 no class regresses {_mark(run.clause2)}"
            + (f"  {'; '.join(run.class_regressions)}" if run.class_regressions else ""),
            f"  3 false-abstain      {_mark(run.clause3)}"
            f"  confidence lost: {len(run.confidence_lost)}, "
            f"newly found at low: {len(run.newly_found_low)}",
            f"  4 re-baseline        {_mark(run.clause4)}"
            + (f"  {'; '.join(run.other_regressions)}" if run.other_regressions else ""),
        ]
    lines += [
        "",
        f"licensing p = {verdict.licensing_p:.4f} (the more conservative of the two)",
        f"VERDICT: `expand` defaults {'ON' if verdict.passed else 'OFF'}.",
    ]
    if not verdict.passed:
        lines.append(
            "A result short of the table ships the channel off, with counts and p recorded, "
            "untuned. Fitting afterwards is exploratory and cannot flip this gate without a "
            "newly authored question set."
        )
    return "\n".join(lines)


def _mark(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def as_dict(verdict: Verdict, *, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "alpha": ALPHA,
        "problems": verdict.problems,
        "licensing_p": verdict.licensing_p,
        "passed": verdict.passed,
        "runs": [
            {
                "label": run.label,
                "improved": list(run.improved),
                "regressed": list(run.regressed),
                "p": run.p,
                "clauses": {
                    "sign_test": run.clause1,
                    "no_class_regresses": run.clause2,
                    "false_abstain": run.clause3,
                    "rebaseline": run.clause4,
                },
                "class_regressions": list(run.class_regressions),
                "confidence_lost": list(run.confidence_lost),
                "newly_found_at_low_confidence": list(run.newly_found_low),
                "other_regressions": list(run.other_regressions),
            }
            for run in verdict.runs
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="graph_gate", description=__doc__)
    parser.add_argument("--before", type=Path, required=True, help="the `off` leg's artifact")
    parser.add_argument("--after-without", type=Path, required=True)
    parser.add_argument("--after-with", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--rebaseline", type=Path, default=None)
    parser.add_argument("--kind", default=GATED_KIND)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    verdict = evaluate_gate(
        read_leg(args.before),
        read_leg(args.after_without),
        read_leg(args.after_with),
        kind=args.kind,
        tolerance=args.tolerance,
        baseline=_read_json(args.baseline),
        rebaseline=_read_json(args.rebaseline),
    )
    print(
        json.dumps(as_dict(verdict, kind=args.kind), indent=2)
        if args.json
        else report(verdict, kind=args.kind)
    )
    return 0 if verdict.passed else 1


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else None


if __name__ == "__main__":
    raise SystemExit(main())
