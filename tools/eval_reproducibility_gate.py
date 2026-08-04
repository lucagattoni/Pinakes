"""The golden set answers the same way however the index was built — a gate, not a comment.

**Why this is a gate and not only a test.** The graph release's decision is an exact per-question
sign test (`plans/20260729_0256-links-and-graph.md`, G5): five questions improving against one
regressing is the
difference between shipping a schema bump and not. That arithmetic reads per-question movement as
evidence about *retrieval*, so any per-question movement caused by anything else is not noise, it
is a wrong answer. Until G1 there was nothing standing behind that: every tiebreak in the pipeline
resolved to `chunks.id`, the rowid, which `store.py` says outright has no identity across rebuilds.

**What it adds over `tests/test_search_reproducibility.py`, which asserts the same property.** It
sweeps four ways of reaching the same corpus state where the tests exercise one — a document
edited, added, removed and renamed take different paths through `sync.py` — and it is independent
of the test suite, a gate sharing a fixture with the thing it gates being one refactor away from
vacuity.

**Two of those four have never been observed to catch anything, and saying so is the point.** Swept
against the genuine pre-G1 code at five embedding widths (the table under `DIM`), *added* and
*removed* reported zero differences every time; only *edited* and *renamed* ever bit. They are kept
because they cost half a second and exercise sync paths the others do not, but a reader must not
count four independent probes here — there are two, plus two that are currently along for the ride.
`--inject-difference` cannot tell the difference, since it corrupts every perturbation alike.

**The predicate.** For each perturbation: sync the committed demo corpus, apply the change, sync
incrementally, evaluate the committed golden set; then `--rebuild` the same tree and evaluate
again. Both indexes describe byte-identical sources. The gate fails if any question's outcome —
retrieved documents, their order, the confidence label, the hit rank — differs between the two. All
four are compared for real: `_plant` rewrites `[retrieval.confidence]` as well as the model names,
because thresholds fitted for a different reranker make `_confidence` return `unknown` for every
question and quietly retire the field this sentence promises.

The backend is a deliberately tie-heavy fake, and that is the point rather than a shortcut. Ties
are the phenomenon: real 384-dimensional cosines almost never tie exactly, so the shipped models
were reproducible **by luck** and stayed that way while every tiebreak underneath them was unstable
(measured 20260801 — see `docs/STATUS.md`). A low-dimensional integer word-count embedding ties
constantly, which is what makes the property observable at all; `DIM` below records how that width
was chosen, because the obvious answer turned out to be a vacuous gate. It also keeps this gate
offline and free, so `./check.sh` can run it in a second.

**`--record-outcomes` is the other half, and it is not a gate.** One machine cannot answer whether
two machines agree, and the fake above deliberately does not exercise the real model — where a
different CPU, a different ONNX build or a different BLAS could reorder results without either being
wrong. So CI runs this mode on `ubuntu-latest` and on `macos-latest` with the *real* `[light]`
models and diffs the two files. It writes a throwaway measurement to a path you name; making
per-question outcomes a **committed artifact** beside `baseline.json` is G2's, and deliberately not
done here.

Usage:
    python3 tools/eval_reproducibility_gate.py
    python3 tools/eval_reproducibility_gate.py --inject-difference     # prove it can still fail
    python3 tools/eval_reproducibility_gate.py --record-outcomes o.json  # real models, for CI
"""

import argparse
import shutil
import sys
import tempfile
import zlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from pinakes import store
from pinakes.embed import ModelInfo, Vectors, register_embedding_backend, register_reranker
from pinakes.eval import evaluate, load_questions
from pinakes.manifest import load
from pinakes.sync import SyncOptions, sync

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "tests" / "demo-kb"

DIM = 32
"""Chosen by measurement, not by taste — and the taste-driven answer was wrong.

The first version used eight, reasoning that fewer dimensions mean more ties. Run against the
pre-fix code it reported **zero** differences on all four perturbations: collapse the space far
enough and every candidate ties, so the ordering underneath stops reaching the top-k at all. The
relationship is not monotonic either. Swept 20260801 over the genuine pre-G1 code — differing
questions per perturbation, edited / added / removed / renamed:

    dim   8: 0 0 0 0     <- vacuous
    dim  16: 0 0 0 0     <- vacuous
    dim  32: 1 0 0 1     <- chosen
    dim  64: 1 0 0 0
    dim 128: 1 0 0 1

Thirty-two catches the most. Re-run after the fixture's confidence thresholds were made live
(`_plant`), which changed none of these numbers — worth knowing, since it means the defect shows up
in *which documents came back*, not in the label attached to them.

A gate that cannot observe the defect it was written for is worse than no gate, because it reports
success. That is why the sweep is recorded here rather than its conclusion alone: the next person's
intuition about dimension count will be the same as this one's, and it was wrong.
"""

EDITED = "docs/storage-environment.md"
REMOVED = "docs/opening-hours.md"
RENAMED_FROM = "docs/copying-service.md"
RENAMED_TO = "docs/copying-service-renamed.md"

APPENDED = "\n\nA sentence appended so this document has to be re-chunked.\n"
ADDED_TEXT = "# Added\n\nA document added after the first sync, to move every later rowid.\n"


class TyingBackend:
    """Deterministic and deliberately tie-heavy. `crc32`, never `hash()`, which Python randomises
    per process unless `PYTHONHASHSEED` is set — and a fake that is not itself reproducible cannot
    measure reproducibility."""

    def embed(self, texts: Sequence[str]) -> Vectors:
        rows: list[Vectors] = []
        for text in texts:
            vector = np.zeros(DIM, dtype=np.float32)
            for word in text.lower().split():
                vector[zlib.crc32(word.strip(".,:;()").encode("utf-8")) % DIM] += 1.0
            rows.append(vector)
        if not rows:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "tying", "v1", DIM, 512)


class CoarseReranker:
    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        terms = set(query.lower().split())
        return [float(len(terms & set(passage.lower().split()))) - 3.0 for passage in passages]

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "coarse-reranker", "v1", 0, 512)


def _plant(destination: Path) -> Path:
    """A copy of the committed demo corpus, wired to the fake models.

    Never `.pinakes/`: it is generated, gitignored, and on a developer machine holds an index built
    with the real 384-dimensional model, which the store's width check refuses.
    """
    root = destination / "demo-kb"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns(".pinakes"))

    path = root / "pinakes.toml"
    text = path.read_text(encoding="utf-8")
    for before, after in (
        ('provider = "fastembed"', 'provider = "fake"'),
        ('model    = "BAAI/bge-small-en-v1.5"', 'model    = "tying"'),
        ("dim      = 384", f"dim      = {DIM}"),
        ('model    = "BAAI/bge-reranker-base"', 'model    = "coarse-reranker"'),
        # `fitted_for` too, and leaving it out made a field this gate claims to compare dead.
        # `_confidence` short-circuits to `unknown` when the thresholds name a different reranker
        # than the one in use, so every question scored `unknown` and the confidence label — the
        # outcome field most sensitive to a tie, being one float against a threshold — could not
        # move whatever the ordering did.
        ('fitted_for = "BAAI/bge-reranker-base"', 'fitted_for = "coarse-reranker@v1"'),
        # ...and thresholds that sit *inside* the fake reranker's range. The committed pair was
        # fitted on a real cross-encoder's logits and lies below every score this one can emit, so
        # naming the reranker alone bought a label that was constantly `high` instead of constantly
        # `unknown` — still a field that cannot move, still unable to witness a tie flipping which
        # passage lands on top.
        ("low_below  = -5.4213", "low_below  = -1.0"),
        ("high_above = -3.5016", "high_above = 1.0"),
    ):
        if before not in text:
            raise SystemExit(
                f"eval-reproducibility: the demo manifest no longer contains {before!r}; "
                "this gate rewrites it to run offline and cannot any more."
            )
        text = text.replace(before, after)
    path.write_text(text, encoding="utf-8")
    return root


def _outcomes(root: Path) -> list[tuple[str, tuple[str, ...], str, int | None, int]]:
    """Per question, never aggregate: two runs can score an identical `recall@k` while disagreeing
    about half the questions, and per-question movement is what the graph release's gate reads."""
    manifest = load(root)
    questions = load_questions(root / "eval" / "questions.yaml")
    connection = store.connect_ro(manifest.index_path)
    try:
        _, outcomes = evaluate(
            connection, manifest, questions, backend=TyingBackend(), reranker=CoarseReranker()
        )
    finally:
        connection.close()
    return [
        (o.question.question, o.retrieved, o.confidence, o.hit_rank, o.hops_followed)
        for o in outcomes
    ]


def _record(destination: Path) -> int:
    """Evaluate the committed demo KB with the models its *own* manifest names, and write the
    per-question outcomes as canonical JSON — one machine's half of the cross-machine comparison.

    No fake anywhere: this is the one measurement where the real model is the point, because what
    it looks for is a CPU, an ONNX build or a BLAS reordering results. `pnk sync` must have run.
    Floats are deliberately absent from the record — a cosine differing in its last bit is not
    interesting, and would make the comparison fail for a reason nobody should act on. What is
    recorded is what the *harness scores*: which documents came back, in what order, with what
    confidence label.
    """
    import json

    from pinakes.embed import load_backend, load_reranker

    manifest = load(DEMO)
    questions = load_questions(DEMO / "eval" / "questions.yaml")
    reranker = load_reranker(manifest.rerank) if manifest.retrieval.rerank == "local" else None
    connection = store.connect_ro(manifest.index_path)
    try:
        _, outcomes = evaluate(
            connection,
            manifest,
            questions,
            backend=load_backend(manifest.embedding),
            reranker=reranker,
        )
    finally:
        connection.close()

    destination.write_text(
        json.dumps(
            [
                {
                    "question": o.question.question,
                    "kind": o.question.kind,
                    "retrieved": list(o.retrieved),
                    "confidence": o.confidence,
                    "hit_rank": o.hit_rank,
                    "hops_followed": o.hops_followed,
                }
                for o in outcomes
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"eval-reproducibility: wrote {len(outcomes)} per-question outcomes to {destination}")
    return 0


def _edit(root: Path) -> None:
    target = root / EDITED
    target.write_text(target.read_text(encoding="utf-8") + APPENDED, encoding="utf-8")


def _add(root: Path) -> None:
    (root / "docs" / "zzz-added.md").write_text(ADDED_TEXT, encoding="utf-8")


def _remove(root: Path) -> None:
    (root / REMOVED).unlink()
    sidecar = root / f"{REMOVED}.pnk.yaml"
    if sidecar.exists():
        sidecar.unlink()


def _rename(root: Path) -> None:
    (root / RENAMED_FROM).rename(root / RENAMED_TO)
    sidecar = root / f"{RENAMED_FROM}.pnk.yaml"
    if sidecar.exists():
        sidecar.rename(root / f"{RENAMED_TO}.pnk.yaml")


PERTURBATIONS = (
    ("a document edited", _edit),
    ("a document added", _add),
    ("a document removed", _remove),
    ("a document renamed", _rename),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_reproducibility_gate", description=__doc__)
    parser.add_argument(
        "--inject-difference",
        action="store_true",
        help=(
            "Corrupt one question's outcome on the rebuilt side before comparing, and require the "
            "gate to notice. CI's `the gate can still fail` step — a gate nobody has watched fail "
            "is a gate nobody knows works. It proves the comparison fires and names the question; "
            "that the *ordering* is right is held by the mutation-verified tests in "
            "tests/test_search_reproducibility.py, which is a different claim and needs saying."
        ),
    )
    parser.add_argument(
        "--record-outcomes",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Evaluate tests/demo-kb with its own real models and write per-question outcomes "
            "there, then exit. CI runs this on two operating systems and diffs the results — the "
            "half of reproducibility one machine cannot answer. Not a committed artifact: that is "
            "G2's."
        ),
    )
    args = parser.parse_args(argv)

    if args.record_outcomes is not None:
        return _record(args.record_outcomes)

    register_embedding_backend("fake", lambda section, offline: TyingBackend())
    register_reranker("fake", lambda section, offline: CoarseReranker())

    problems: list[str] = []
    lines: list[str] = []

    for label, perturb in PERTURBATIONS:
        with tempfile.TemporaryDirectory(prefix="pnk-repro-") as raw:
            root = _plant(Path(raw))
            sync(load(root), options=SyncOptions(), now="20260801 00:30")

            perturb(root)
            sync(load(root), options=SyncOptions(), now="20260801 00:31")
            incremental = _outcomes(root)

            sync(load(root), options=SyncOptions(rebuild=True), now="20260801 00:32")
            rebuilt = _outcomes(root)

        if args.inject_difference:
            question, retrieved, confidence, hit_rank, hops = rebuilt[0]
            rebuilt[0] = (question, (*retrieved, "docs/injected.md"), confidence, hit_rank, hops)

        differing = [a for a, b in zip(incremental, rebuilt, strict=True) if a != b]
        lines.append(
            f"{label}: {len(differing)} of {len(incremental)} questions differ between an "
            f"incremental sync and a --rebuild"
        )
        if differing:
            problems.append(
                f"{label}: {len(differing)} of {len(incremental)} questions changed outcome "
                f"between an incremental sync and a --rebuild of the same corpus — first: "
                f"{differing[0][0]!r}"
            )

    for line in lines:
        print(f"eval-reproducibility: {line}")
    for problem in problems:
        print(f"eval-reproducibility: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
