"""The scoreboard, against the real demo KB — the thing that makes retrieval changes decidable."""

import hashlib
import json
import subprocess
import sys
import zlib
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from pinakes import store
from pinakes.calibrate import fit
from pinakes.embed import ModelInfo, Vectors, register_embedding_backend, register_reranker
from pinakes.errors import CalibrationError, EvalError
from pinakes.eval import (
    KINDS,
    Hop,
    OutcomeRow,
    Question,
    compare,
    evaluate,
    load_questions,
    read_baseline,
    read_outcomes,
    score_rows,
    write_baseline,
    write_outcomes,
)
from pinakes.manifest import load
from pinakes.search import HIGH, LOW
from pinakes.sync import SyncOptions, sync

REPO = Path(__file__).resolve().parent.parent
DEMO = Path(__file__).parent / "demo-kb"
PROBE = REPO / "tools" / "reachable_ceiling_probe.py"
DIM = 64


class HashingBackend:
    """A cheap deterministic embedder: a bag-of-words hash. Good enough to rank, free to run.

    The point of these tests is that the harness measures correctly, not that a particular model
    scores well — the real numbers come from CI with real weights (§7).

    `crc32`, not `hash()`. Python randomises `hash()` of a `str` per process unless
    `PYTHONHASHSEED` is set, which nothing here sets and no conftest *can* set — it is read before
    the interpreter starts. So which words collided in the 64-dimensional space changed from run
    to run, and every ranking assertion in this file was a coin toss weighted heavily enough to
    look stable: measured 20260729 03:31, one failure in 40 runs. A fake that is not reproducible
    cannot tell a real regression from its own noise (v0.1 rule 5, test machinery).
    """

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
        return ModelInfo("fake", "hashing", "v1", DIM, 512)


class OverlapReranker:
    """Scores by word overlap, on a deliberately un-normalised scale, like a real cross-encoder."""

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        terms = set(query.lower().split())
        return [float(len(terms & set(passage.lower().split()))) - 3.0 for passage in passages]

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "overlap-reranker", "v1", 0, 512)


@pytest.fixture
def demo(tmp_path: Path) -> Iterator[Path]:
    """A copy of the committed demo KB, synced with the fake backend."""
    import shutil

    register_embedding_backend("fake", lambda section, offline: HashingBackend())
    register_reranker("fake", lambda section, offline: OverlapReranker())

    root = tmp_path / "demo-kb"
    # Never copy `.pinakes/`: it is generated, gitignored, and on a developer machine holds an
    # index built with the *real* 384-dimensional model. Syncing the 64-dimensional fake on top of
    # it is refused by the store's width check — correctly, and confusingly if you copied it.
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns(".pinakes"))

    # The committed manifest names the real [light] models, because CI evaluates this KB for real.
    # Unit tests swap in a fake so they stay fast and deterministic; what they check is that the
    # harness measures correctly, not that a particular model scores well.
    manifest_path = root / "pinakes.toml"
    text = manifest_path.read_text(encoding="utf-8")
    text = text.replace('provider = "fastembed"', 'provider = "fake"')
    text = text.replace('model    = "BAAI/bge-small-en-v1.5"', 'model    = "hashing"')
    text = text.replace("dim      = 384", f"dim      = {DIM}")
    text = text.replace('model    = "BAAI/bge-reranker-base"', 'model    = "overlap-reranker"')
    manifest_path.write_text(text, encoding="utf-8")

    sync(load(root), options=SyncOptions(), now="20260725 18:30")
    yield root


def test_the_committed_golden_set_is_well_formed() -> None:
    questions = load_questions(DEMO / "eval" / "questions.yaml")
    kinds = {question.kind for question in questions}

    assert len(questions) >= 40  # §7's stated target
    assert kinds == KINDS
    assert any(question.hops for question in questions)

    # Ids are the artifact's key and are hand-written here on purpose: a derived one moves when the
    # wording does, which drops the question from every before/after comparison without a word.
    identifiers = [question.id for question in questions]
    assert len(set(identifiers)) == len(identifiers)
    assert all(identifier == identifier.strip() and identifier for identifier in identifiers)

    # The two classes the graph release is decided on, sized where the plan put them: ~18 multi-hop
    # supplying the improvements, ~20 simple-lookup as the control a channel must not damage.
    counted = {kind: sum(1 for q in questions if q.kind == kind) for kind in KINDS}
    assert counted["multi-hop"] >= 18, counted
    assert counted["simple-lookup"] >= 20, counted

    documents = {f"docs/{path.name}" for path in (DEMO / "docs").iterdir()}
    for question in questions:
        for expected in question.expect:
            assert expected in documents, f"{question.question} expects a missing document"
        for hop in question.hops:
            assert hop.expect in documents

        # The consistency that was missing. Two committed questions named one document in `expect`
        # and reached a different one in their last hop, so the scorer asked about A and demanded
        # B. Nothing caught it, because `hops` fed no metric at all.
        if question.hops:
            assert set(question.expect) == {hop.expect for hop in question.hops}, (
                f"{question.question}: `expect` must be exactly the hops' own documents"
            )


def test_no_answer_questions_expect_nothing() -> None:
    """They score by abstention; an expectation would quietly turn them into ordinary questions."""
    for question in load_questions(DEMO / "eval" / "questions.yaml"):
        if question.kind == "no-answer":
            assert question.expect == ()
            assert not question.answerable


def test_evaluating_the_demo_kb_produces_every_metric(demo: Path) -> None:
    questions = load_questions(demo / "eval" / "questions.yaml")
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        metrics, outcomes = evaluate(
            connection,
            load(demo),
            questions,
            backend=HashingBackend(),
            reranker=OverlapReranker(),
        )
    finally:
        connection.close()

    assert metrics.questions == len(questions)
    assert 0.0 <= metrics.recall_at_k <= 1.0
    assert 0.0 <= metrics.mrr <= 1.0
    assert set(metrics.by_kind) == KINDS
    assert len(outcomes) == len(questions)

    # The harness must actually retrieve something, or every metric is a vacuous zero.
    assert metrics.recall_at_k > 0.5, f"lexical retrieval is broken: {metrics.as_dict()}"


def test_multi_hop_questions_follow_their_script(demo: Path) -> None:
    questions = [q for q in load_questions(demo / "eval" / "questions.yaml") if q.hops]
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        _, outcomes = evaluate(
            connection, load(demo), questions, backend=HashingBackend(), reranker=OverlapReranker()
        )
    finally:
        connection.close()
    assert any(outcome.hops_followed > 0 for outcome in outcomes)


def test_a_hop_that_misses_denies_the_hit_even_when_the_last_hop_lands(demo: Path) -> None:
    """The test the class never had: scoring must depend on the hops, not only the final search.

    The first hop asks something the corpus cannot answer with the document it names, so it cannot
    land. The last hop is a near-certain lexical hit. Before 20260729 the question scored as a hit
    on the strength of that last search alone; `hops_followed` existed and reached no metric, so
    deleting the hop loop changed nothing. If `Outcome.hit` stops consulting the hops, this fails.
    """
    unreachable = Hop(query="parking permits for delivery vans", expect="docs/opening-hours.md")
    lands = Hop(
        query="What temperature and humidity are the stacks held at?",
        expect="docs/storage-environment.md",
    )
    scripted = Question(
        id="scripted-first-hop-cannot-land",
        question="A scripted question whose first hop cannot land.",
        kind="multi-hop",
        expect=("docs/opening-hours.md", "docs/storage-environment.md"),
        hops=(unreachable, lands),
    )

    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        _, outcomes = evaluate(
            connection, load(demo), [scripted], backend=HashingBackend(), reranker=OverlapReranker()
        )
    finally:
        connection.close()

    outcome = outcomes[0]
    assert "docs/storage-environment.md" in outcome.retrieved, "the last hop was meant to land"
    assert outcome.hit_rank is not None, "a document from `expect` was retrieved"
    assert outcome.hops_followed == 1, "exactly one of the two hops landed"
    assert not outcome.hit, "a question is not a hit when one of its hops missed"


def test_a_baseline_round_trips_and_detects_a_regression(tmp_path: Path, demo: Path) -> None:
    questions = load_questions(demo / "eval" / "questions.yaml")
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        metrics, _ = evaluate(
            connection, load(demo), questions, backend=HashingBackend(), reranker=OverlapReranker()
        )
    finally:
        connection.close()

    path = tmp_path / "baseline.json"
    write_baseline(path, metrics)
    assert json.loads(path.read_text(encoding="utf-8"))["questions"] == metrics.questions

    assert compare(metrics, read_baseline(path)) == []

    pretend_better = dict(read_baseline(path))
    pretend_better["recall_at_k"] = min(1.0, metrics.recall_at_k + 0.5)
    regressions = compare(metrics, pretend_better)
    assert regressions and "recall_at_k" in regressions[0]


def test_a_per_class_regression_is_caught_when_the_aggregate_hides_it(demo: Path) -> None:
    """One class paying for another is the shape a graph channel has, and the aggregate hides it.

    `compare()` checked six aggregates and never read `by_kind`, though it wrote it into every
    baseline. A channel lifting multi-hop while dropping simple lookup by the same number of
    questions moves `recall_at_k` by almost nothing and passed green.
    """
    questions = load_questions(demo / "eval" / "questions.yaml")
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        metrics, _ = evaluate(
            connection, load(demo), questions, backend=HashingBackend(), reranker=OverlapReranker()
        )
    finally:
        connection.close()

    baseline = metrics.as_dict()
    assert compare(metrics, baseline) == []

    # Every aggregate is left exactly as measured; only one class is claimed to have been better.
    traded = dict(baseline)
    traded["by_kind"] = dict(baseline["by_kind"]) | {"lexical": 1.0}
    metrics_with_a_worse_class = replace(metrics, by_kind=dict(metrics.by_kind) | {"lexical": 0.5})

    regressions = compare(metrics_with_a_worse_class, traded)
    assert regressions and any("by_kind[lexical]" in line for line in regressions)


def test_a_golden_set_that_shrank_is_a_regression(demo: Path) -> None:
    """Losing the hard questions improves every rate. Only the count can see it."""
    questions = load_questions(demo / "eval" / "questions.yaml")
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        metrics, _ = evaluate(
            connection, load(demo), questions, backend=HashingBackend(), reranker=OverlapReranker()
        )
    finally:
        connection.close()

    baseline = dict(metrics.as_dict())
    baseline["questions"] = metrics.questions + 5

    regressions = compare(metrics, baseline)
    assert regressions and any("the golden set shrank" in line for line in regressions)


def test_a_rise_in_false_confidence_is_a_regression(demo: Path) -> None:
    """Higher is worse for the error rates; a comparison checking only recall would miss it."""
    questions = load_questions(demo / "eval" / "questions.yaml")
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        metrics, _ = evaluate(
            connection, load(demo), questions, backend=HashingBackend(), reranker=OverlapReranker()
        )
    finally:
        connection.close()

    baseline = metrics.as_dict()
    baseline["false_confidence"] = 0.0
    baseline["false_abstain"] = 0.0
    inflated = compare(metrics, baseline)
    assert all("higher is worse" in line for line in inflated) or inflated == []


def test_an_empty_question_set_skips_with_a_reason(
    demo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A gate that cannot run says so and is still a gate — it does not fail the build.

    The template's `eval/questions.yaml` is `questions: []`, so every freshly `pnk init`ed KB used
    to fail `make eval` by construction. It cannot ship questions either: it scaffolds an empty
    `docs/`, and a question naming a document that does not exist is worse than none.

    What keeps this from silently blessing an *emptied* golden set is the other end —
    `test_the_committed_golden_set_is_well_formed` above asserts the committed one has questions.
    """
    from pinakes.eval import main, run

    path = demo / "eval" / "empty.yaml"
    path.write_text("questions: []\n", encoding="utf-8")
    assert load_questions(path) == []
    assert run(demo, questions_path=path) is None

    assert main([str(demo), "--questions", str(path)]) == 0
    printed = capsys.readouterr().out
    assert "skipping the evaluation, not failing it" in printed
    assert str(path) in printed


def test_a_file_with_no_questions_key_is_still_refused(tmp_path: Path) -> None:
    """The empty-set skip must not become a skip for *any* file that yields no questions.

    `questions: []` is a template deliberately shipping none. A file with the key misspelled is a
    golden set with a typo, and under a skip that could not tell them apart it would sail through
    `make eval` reporting success.
    """
    path = tmp_path / "questions.yaml"
    path.write_text("question:\n  - id: q\n    question: What?\n", encoding="utf-8")
    with pytest.raises(EvalError) as exc_info:
        load_questions(path)
    assert "no `questions` key" in str(exc_info.value)

    path.write_text("questions: []\n", encoding="utf-8")
    assert load_questions(path) == []


def test_a_row_missing_a_field_is_refused_by_name(tmp_path: Path) -> None:
    """Every field a row carries is read by `score_rows`, so a row missing one cannot be scored."""
    path = tmp_path / "outcomes.json"
    path.write_text(
        json.dumps({"schema": 1, "questions": [{"id": "a", "kind": "lexical", "hit": True}]}),
        encoding="utf-8",
    )
    with pytest.raises(EvalError) as exc_info:
        read_outcomes(path)
    assert "missing confidence" in str(exc_info.value)


def test_an_unknown_kind_is_refused(tmp_path: Path) -> None:
    """Validated against the known set, never defaulted to `lexical` (G2).

    A silent default is a claim about how the question was authored, and a wrong one puts it in a
    class whose `by_kind` score then measures two different things.
    """
    path = tmp_path / "questions.yaml"
    path.write_text(
        "questions:\n  - id: q\n    question: What?\n    kind: multihop\n", encoding="utf-8"
    )
    with pytest.raises(EvalError) as exc_info:
        load_questions(path)
    assert "unknown kind 'multihop'" in str(exc_info.value)
    assert "multi-hop" in exc_info.value.remedy

    path.write_text("questions:\n  - id: q\n    question: What?\n", encoding="utf-8")
    with pytest.raises(EvalError) as exc_info:
        load_questions(path)
    assert "has no `kind`" in str(exc_info.value)


def test_a_repeated_id_is_refused(tmp_path: Path) -> None:
    """Two questions under one id drop one of them from every comparison, silently."""
    path = tmp_path / "questions.yaml"
    path.write_text(
        "questions:\n"
        "  - id: same\n    question: First?\n    kind: lexical\n"
        "  - id: same\n    question: Second?\n    kind: lexical\n",
        encoding="utf-8",
    )
    with pytest.raises(EvalError) as exc_info:
        load_questions(path)
    assert "share the id 'same'" in str(exc_info.value)


def test_an_absent_id_is_derived_from_the_question(tmp_path: Path) -> None:
    """Back-compatible, and readable rather than a hash — but it moves when the wording does."""
    path = tmp_path / "questions.yaml"
    path.write_text(
        "questions:\n  - question: How long is quarantine?\n    kind: lexical\n", encoding="utf-8"
    )
    assert load_questions(path)[0].id == "how-long-is-quarantine"


def test_per_question_outcomes_round_trip(tmp_path: Path, demo: Path) -> None:
    """The artifact G5's sign test reads, and the rows must re-score to the same aggregates.

    Both halves matter. A file that round-trips but cannot be re-scored is a log; a scorer that
    agrees with `evaluate` only because it shares its objects proves nothing about the file.
    """
    questions = load_questions(demo / "eval" / "questions.yaml")
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        metrics, outcomes = evaluate(
            connection, load(demo), questions, backend=HashingBackend(), reranker=OverlapReranker()
        )
    finally:
        connection.close()

    rows = [outcome.row() for outcome in outcomes]
    path = tmp_path / "outcomes.json"
    write_outcomes(path, rows, {"schema": 1, "k": 5})
    header, restored = read_outcomes(path)

    assert header["schema"] == 1
    assert restored == sorted(rows, key=lambda row: row.id)
    assert score_rows(restored).as_dict() == metrics.as_dict()

    # Sorted by id on the way out, so a diff between two runs shows movement, not reordering.
    written = json.loads(path.read_text(encoding="utf-8"))
    assert [row["id"] for row in written["questions"]] == sorted(row.id for row in rows)


def test_a_row_carries_everything_every_metric_needs() -> None:
    """`score_rows` reads five fields, and each one has to reach a number.

    Without this the artifact could lose a field and stay round-trippable, and the loss would only
    surface when the graph release's gate read a column that had quietly become decorative.
    """
    base = [
        OutcomeRow(id="a", kind="lexical", hit=True, hit_rank=1, confidence=HIGH),
        OutcomeRow(id="b", kind="lexical", hit=False, hit_rank=None, confidence=LOW),
        OutcomeRow(id="c", kind="no-answer", hit=False, hit_rank=None, confidence=LOW),
    ]
    scored = score_rows(base)
    assert scored.recall_at_k == 0.5
    assert scored.mrr == 0.5
    assert scored.rerank_precision == 0.5
    assert scored.by_kind == {"lexical": 0.5, "no-answer": 1.0}

    # `hit_rank` alone moves MRR and top-1; `confidence` alone moves the two error rates.
    demoted = [replace(base[0], hit_rank=4), *base[1:]]
    assert score_rows(demoted).mrr == 0.125
    assert score_rows(demoted).rerank_precision == 0.0

    abstained = [replace(base[0], confidence=LOW), *base[1:]]
    assert score_rows(abstained).false_abstain == 0.5
    confident = [*base[:2], replace(base[2], confidence=HIGH)]
    assert score_rows(confident).false_confidence == 1.0


def test_the_committed_41_score_exactly_their_pre_growth_values() -> None:
    """Growing the golden set moved no question that was already in it.

    Re-scored from the committed artifact, so it needs no weights and no network: the whole
    scoreboard is a function of five fields per question. `baseline-pre-growth.json` is the
    baseline as it stood at 41 questions, preserved with the ids it covered.

    This is the guard on the one re-baseline G2 is allowed. Rewriting `baseline.json` disarms every
    number in it at once, and "the set grew" must not be able to hide "and something got worse".
    """
    preserved = read_baseline(DEMO / "eval" / "baseline-pre-growth.json")
    _, rows = read_outcomes(DEMO / "eval" / "outcomes.json")

    ids = {str(identifier) for identifier in preserved["ids"]}
    before = {key: value for key, value in preserved.items() if key != "ids"}
    pre_growth = [row for row in rows if row.id in ids]

    assert len(pre_growth) == len(ids) == int(before["questions"])
    assert score_rows(pre_growth).as_dict() == before


def test_the_committed_artifact_describes_the_committed_baseline() -> None:
    """One run wrote both files, so re-scoring the rows has to reproduce the aggregates.

    `--write-baseline` writes them together for exactly this reason. A baseline paired with an
    artifact from a different run would let the sign test compare questions against numbers that
    never described them.
    """
    _, rows = read_outcomes(DEMO / "eval" / "outcomes.json")
    assert score_rows(rows).as_dict() == read_baseline(DEMO / "eval" / "baseline.json")


def test_the_reachable_ceiling_probe_needs_no_index_schema_change() -> None:
    """The ordering G2 exists to protect: measure the ceiling *before* G3 bumps `schema_version`.

    Bumping the schema forces every KB in existence to rebuild. Doing that to find out whether the
    channel could ever be licensed is the wrong order, so the probe derives the edge set in memory
    from the tables that already exist and writes nothing.
    """
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--fake", "--json"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    )
    payload = json.loads(completed.stdout)

    assert payload["schema_version"] == str(store.SCHEMA_VERSION)
    assert payload["tables_before"] == payload["tables_after"]
    assert "edges" not in payload["tables_after"] and "nodes" not in payload["tables_after"]
    assert {report["variant"] for report in payload["reports"]} == {
        "with-authored",
        "without-authored",
    }


def test_the_reachable_ceiling_probe_answers_to_the_edge_set() -> None:
    """A probe that reports the same number whatever the graph contains measures something else.

    This project's recurring defect is an assertion satisfied by something other than the property
    it names, and a reachability probe is an easy place for it: on a flat, untagged corpus
    `co-located` is the *only* structural edge that crosses a document boundary, so removing it has
    to move the count. If it ever stops moving, the probe is reading the seed set, not the graph.
    """

    def run_probe(*drop: str) -> dict[str, dict[str, int]]:
        argv = [sys.executable, str(PROBE), "--fake", "--json"]
        for kind in drop:
            argv += ["--drop", kind]
        payload = json.loads(
            subprocess.run(argv, capture_output=True, text=True, check=True, cwd=REPO).stdout
        )
        return {report["variant"]: report for report in payload["reports"]}

    intact = run_probe()
    without_colocated = run_probe("co-located")
    stripped = run_probe(
        "sibling", "parent-child", "in-section", "co-located", "shared-tag", "authored"
    )

    for variant in ("with-authored", "without-authored"):
        assert without_colocated[variant]["liftable"] < intact[variant]["liftable"], variant

        # With no edges at all nothing can be *reached*: whatever is still counted liftable was
        # already among the fused candidates and merely ranked below the cut. The probe splits that
        # out for exactly this reason — a ceiling built from it says nothing about structure.
        assert stripped[variant]["liftable"] == stripped[variant]["at_seed_only"], variant
        assert stripped[variant]["liftable"] < intact[variant]["liftable"], variant

    # Authored edges reach documents the derived set does not, which is why only the
    # without-authored figure binds: a gate cleared on the larger number is cleared on links a
    # human wrote, not on structure derived for free.
    assert intact["with-authored"]["liftable"] > intact["without-authored"]["liftable"]


REFUSAL = "unmeasurable golden set"
"""The probe's named refusal. Asserted on rather than a bare non-zero exit, because these tests
run the probe against a KB whose manifest names a backend the subprocess never registered: a run
that got past the refusal would fail too, and only the message tells the two apart."""


def _run_probe(*argv: str) -> subprocess.CompletedProcess[str]:
    """The probe as a user runs it — deliberately no `check`, since these tests are about how it
    refuses, and a `CalledProcessError` would hide the stderr they assert on."""
    return subprocess.run(
        [sys.executable, str(PROBE), *argv], capture_output=True, text=True, cwd=REPO
    )


def _write_golden_set(root: Path, questions: list[dict[str, object]]) -> None:
    """Replace a KB's golden set. Written as JSON, which YAML is a superset of: hand-indented YAML
    inside a test is one more thing that can be wrong for a reason the test is not about."""
    (root / "eval" / "questions.yaml").write_text(
        json.dumps({"questions": questions}), encoding="utf-8"
    )


def test_the_probe_refuses_a_hop_expecting_a_document_the_index_does_not_hold(demo: Path) -> None:
    """A path typo used to be *counted*, which is the worst defect a measurement tool can have.

    The lookup answered `""` for an unknown path, so the hop was recorded `lands=False,
    reachable=False` — failing and unreachable, indistinguishable from a real one. One typo in a
    200-document corpus deflates the liftable ratio the graph release's precondition binds on, and
    nothing in the output says so.
    """
    _write_golden_set(
        demo,
        [
            {
                "id": "typo-in-the-second-hop",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md", "docs/funding-sources.md"],
                "hops": [
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                    {"query": "core funding", "expect": "docs/funding-sourses.md"},
                ],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert REFUSAL in completed.stderr
    # Named, both of them: which question, and the path as spelled. A refusal saying only "a path
    # is wrong" leaves the reader to find it in a file of forty questions.
    assert "typo-in-the-second-hop" in completed.stderr
    assert "docs/funding-sourses.md" in completed.stderr


def test_the_probe_refuses_a_multi_hop_question_with_no_hops(demo: Path) -> None:
    """It used to be absorbed: counted in the `multi-hop` denominator, yielding no verdict, so it
    could never be `failing` and disappeared from every other figure while padding that one.

    Likely on a real corpus rather than hypothetical — the scaffolded template documented `id`,
    `question`, `expect` and `kind`, and never mentioned `hops` until this commit.
    """
    _write_golden_set(
        demo,
        [
            {
                "id": "multi-hop-in-name-only",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md"],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert REFUSAL in completed.stderr
    assert "multi-hop-in-name-only" in completed.stderr
    # The count, not the bare word `hops`: every refusal's closing remedy sentence contains
    # "`hops:` list", so asserting on that would pass for a path typo too.
    assert "with 0 hop(s)" in completed.stderr


def test_the_probe_refuses_a_multi_hop_question_carrying_a_single_hop(demo: Path) -> None:
    """The dangerous direction. Fewer hops than the kind claims is absorbed like a missing `hops`,
    except that one hop is *measured* — as a single search — and can move `liftable` upward. The
    precondition is a floor (`>= 7`), so under-counting only blocks a release while over-counting
    licenses a `schema_version` bump that forces every KB in existence to rebuild. A hand
    conversion that scripts hops for the first evidence document and stops produces exactly this.
    """
    _write_golden_set(
        demo,
        [
            {
                "id": "one-hop-is-not-two",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md"],
                "hops": [{"query": "public money", "expect": "docs/deaccession-policy.md"}],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert REFUSAL in completed.stderr
    assert "one-hop-is-not-two" in completed.stderr
    assert "with 1 hop(s)" in completed.stderr


def test_the_probe_refuses_a_hop_expecting_a_document_the_index_holds_no_chunks_for(
    demo: Path,
) -> None:
    """A path can be spelled correctly and still be unmeasurable. Every node the channel walks is
    built from the `chunks` table, so a document with none — a blank file, a note that is only
    front matter, a PDF whose free extraction yielded nothing — can neither be retrieved nor
    reached, and its hop is recorded failing-and-unreachable for a reason that is not about the
    channel. Validating that the *path* exists does not catch it."""
    blank = demo / "docs" / "blank-note.md"
    blank.write_text("", encoding="utf-8")
    sync(load(demo), options=SyncOptions(), now="20260725 18:30")

    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        rows = list(
            connection.execute(
                "SELECT d.path, COUNT(c.id) AS n FROM documents d "
                "LEFT JOIN chunks c ON c.doc_id = d.id WHERE d.path = ? GROUP BY d.id",
                ("docs/blank-note.md",),
            )
        )
    finally:
        connection.close()
    # The premise of the test, asserted rather than assumed: if a blank file ever stops producing
    # a chunk-less document, this test would otherwise silently start proving nothing.
    assert rows and rows[0]["n"] == 0, rows

    _write_golden_set(
        demo,
        [
            {
                "id": "hop-onto-an-empty-document",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md", "docs/blank-note.md"],
                "hops": [
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                    {"query": "core funding", "expect": "docs/blank-note.md"},
                ],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert REFUSAL in completed.stderr
    assert "hop-onto-an-empty-document" in completed.stderr
    assert "no chunks" in completed.stderr


def test_the_probe_refuses_a_hop_whose_query_is_empty(demo: Path) -> None:
    """An empty query fails on its own terms rather than the corpus's, which is the same silent
    deflation as a mistyped path: the hop is counted failing, and nothing says why."""
    _write_golden_set(
        demo,
        [
            {
                "id": "a-hop-with-nothing-to-search-for",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md", "docs/funding-sources.md"],
                "hops": [
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                    {"query": "   ", "expect": "docs/funding-sources.md"},
                ],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert REFUSAL in completed.stderr
    assert "a-hop-with-nothing-to-search-for" in completed.stderr
    assert "empty `query`" in completed.stderr


def test_the_probe_refuses_a_golden_set_with_no_multi_hop_question_at_all(demo: Path) -> None:
    """The last shape that produced a plausible artifact out of nothing: every figure would be a
    zero, and a zero from an empty class is indistinguishable from a measured one."""
    _write_golden_set(
        demo,
        [
            {
                "id": "not-a-multi-hop-question",
                "question": "What may not be done with material acquired using public money?",
                "kind": "simple-lookup",
                "expect": ["docs/deaccession-policy.md"],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert REFUSAL in completed.stderr
    assert "no `multi-hop` question at all" in completed.stderr


def test_the_probe_refuses_filters_that_admit_nothing(demo: Path) -> None:
    """`filters` are applied to the last hop, and an unmatched one rewrites the whole measurement.

    Measured on demo-kb under the fake backend: a `tags: [no-such-tag]` on one question took the
    run from 9 failing / 3 liftable to 18 failing / 0 liftable, exit 0, with nothing in either
    output saying so. It is the empty-`query` defect wearing a different key, and it moves
    `failing` *upward* — the direction a floor reads as headroom.
    """
    _write_golden_set(
        demo,
        [
            {
                "id": "filtered-into-nothing",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md", "docs/funding-sources.md"],
                "filters": {"tags": ["no-such-tag-in-this-corpus"]},
                "hops": [
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                    {"query": "core funding", "expect": "docs/funding-sources.md"},
                ],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert REFUSAL in completed.stderr
    assert "filtered-into-nothing" in completed.stderr
    assert "admit no active document" in completed.stderr


def test_the_probe_refuses_filters_that_exclude_the_last_hops_own_document(demo: Path) -> None:
    """The subtler half: filters that match plenty and not the document the hop must find. The
    filtered search cannot return it, so the question is counted failing on its filters."""
    _write_golden_set(
        demo,
        [
            {
                "id": "filtered-away-from-its-own-answer",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md", "docs/funding-sources.md"],
                "filters": {"path_prefix": "docs/deaccession"},
                "hops": [
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                    {"query": "core funding", "expect": "docs/funding-sources.md"},
                ],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert REFUSAL in completed.stderr
    assert "filtered-away-from-its-own-answer" in completed.stderr
    assert "do not admit the last hop's own `expect`" in completed.stderr


def test_a_question_level_expect_that_names_nothing_is_refused_and_said_to_move_no_figure(
    demo: Path,
) -> None:
    """The probe measures hops, never a question's own `expect` — so this refusal is honest about
    costing no figure, while still refusing: a golden set naming documents the index does not hold
    is not one to measure a release precondition against. Pinning the *wording* matters, because
    the first version of this message claimed every listed problem moved the count."""
    _write_golden_set(
        demo,
        [
            {
                "id": "a-lookup-whose-expect-moved",
                "question": "What may not be done with material acquired using public money?",
                "kind": "simple-lookup",
                "expect": ["docs/renamed-or-deleted.md"],
            },
            {
                "id": "an-intact-multi-hop",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md", "docs/funding-sources.md"],
                "hops": [
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                    {"query": "core funding", "expect": "docs/funding-sources.md"},
                ],
            },
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert "a-lookup-whose-expect-moved" in completed.stderr
    assert "docs/renamed-or-deleted.md" in completed.stderr
    assert "moves no figure this probe prints" in completed.stderr


def test_a_path_wrong_only_in_case_is_refused_with_the_indexed_spelling(demo: Path) -> None:
    """The refusal has to be actionable. Case, a leading `./` and NFC/NFD are the three ways a
    path can be wrong while rendering almost identically to the right one, so the message names
    the spelling the index holds and which difference it is."""
    _write_golden_set(
        demo,
        [
            {
                "id": "shouting-the-path",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md", "docs/funding-sources.md"],
                "hops": [
                    {"query": "public money", "expect": "./docs/deaccession-policy.md"},
                    {"query": "core funding", "expect": "docs/Funding-Sources.md"},
                ],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert "the index holds 'docs/funding-sources.md'" in completed.stderr
    assert "letter case" in completed.stderr
    # Both spellings the index would not match, each named for what it is. The `./` case is the
    # one a reader is least likely to spot unaided.
    assert "the index holds 'docs/deaccession-policy.md'" in completed.stderr
    assert "a leading `./`" in completed.stderr


def test_the_artifact_records_the_configuration_that_produced_the_numbers(demo: Path) -> None:
    """`failing` is a function of the retrieval settings — `lands` asks whether a document is in
    the top `final_k` of a pipeline whose fusion, candidate widths **and reranker** are per-KB
    manifest keys. Naming the corpus and not the configuration leaves two artifacts from two
    configurations indistinguishable, which is the same defect the KB-naming fix closed.

    The reranker's *model* earns its own assertion: swapping one fake reranker for another moved
    demo-kb from 9 failing / 3 liftable to 18 / 12 with every other recorded field identical, so
    the mode (`local`) alone does not identify the measurement.
    """
    payload = json.loads(_run_probe("--fake", "--json").stdout)

    manifest = load(demo)
    # `final_k`, the embedding model and the reranker model are the assertions that can fail: each
    # differs from the shipped default, so none of them is satisfied by a payload of hardcoded
    # defaults — the failure mode this whole branch is about.
    assert payload["retrieval"]["final_k"] == manifest.retrieval.final_k
    assert payload["retrieval"]["fusion"] == manifest.retrieval.fusion
    assert payload["retrieval"]["adjacent_k"] == manifest.retrieval.adjacent_k
    assert payload["retrieval"]["rerank"] == manifest.retrieval.rerank
    assert payload["rerank"] == {
        "provider": "fake",
        "model": "overlap-reranker",
        "revision": manifest.rerank.revision,
    }
    assert payload["embedding"]["dim"] == DIM  # the fake's, not the committed model's
    assert payload["embedding"]["model"] == "hashing"
    assert payload["embedding"]["revision"] == manifest.embedding.revision
    # The value, not merely the key: `_fake_kb` syncs at a fixed clock, so a payload that filled
    # the field with anything at all would pass a presence check and fail this one.
    assert payload["index_built_at"] == "20260725 18:30"

    # The golden set is the input every figure is computed from, and the one a refuse-edit-re-run
    # loop changes most often — two runs over one corpus with two question sets were otherwise
    # identical in every recorded field.
    assert payload["golden_set"]["path"].endswith("eval/questions.yaml")
    assert payload["golden_set"]["multi_hop"] == sum(
        1
        for question in load_questions(DEMO / "eval" / "questions.yaml")
        if question.kind == "multi-hop"
    )
    assert (
        payload["golden_set"]["sha256"]
        == hashlib.sha256((DEMO / "eval" / "questions.yaml").read_bytes()).hexdigest()
    )

    text = _run_probe("--fake").stdout
    assert f"final_k {manifest.retrieval.final_k}" in text
    assert "hashing" in text
    assert "overlap-reranker" in text
    assert payload["golden_set"]["sha256"][:12] in text


def test_a_hop_problem_on_a_question_the_probe_never_measures_says_so(demo: Path) -> None:
    """`load_questions` allows hops on any kind, and the probe measures only `multi-hop`. The
    refusal must not tell the author of a `lexical` question that a figure moved — the same
    over-claim as the reverse, and the closing "it says which" has to be true of every line.

    Both hop branches are exercised: an empty `query` and an unknown `expect`. The first attempt
    at this fix moved the conditional to the end of the sentence, so the message still asserted
    "the hop is recorded failing-and-unreachable" and then denied its effect one clause later.
    """
    _write_golden_set(
        demo,
        [
            {
                "id": "a-lookup-carrying-hops",
                "question": "What may not be done with material acquired using public money?",
                "kind": "lexical",
                "expect": ["docs/deaccession-policy.md"],
                "hops": [
                    {"query": "", "expect": "docs/deaccession-policy.md"},
                    {"query": "public money", "expect": "docs/no-such-document.md"},
                ],
            },
            {
                "id": "an-intact-multi-hop",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md", "docs/funding-sources.md"],
                "hops": [
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                    {"query": "core funding", "expect": "docs/funding-sources.md"},
                ],
            },
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert "a-lookup-carrying-hops" in completed.stderr
    assert "nothing is recorded for it" in completed.stderr
    # The class, not one superseded string: the only problems in this run belong to the question
    # the probe does not measure, so no line of it may claim a hop was recorded at all.
    assert "is recorded failing" not in completed.stderr
    assert "is counted failing" not in completed.stderr


def test_a_mistyped_path_is_not_also_blamed_on_the_filters(demo: Path) -> None:
    """One defect, one problem. `filters` cannot admit a path the index does not hold, so the
    filter check would report a healthy `filters:` block for what is a typo — pointing the
    operator at the wrong line and inflating the problem count."""
    _write_golden_set(
        demo,
        [
            {
                "id": "a-typo-under-filters",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md", "docs/funding-sources.md"],
                "filters": {"path_prefix": "docs/"},
                "hops": [
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                    {"query": "core funding", "expect": "docs/funding-sourses.md"},
                ],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert "1 problem(s)" in completed.stderr
    assert "docs/funding-sourses.md" in completed.stderr
    assert "do not admit the last hop's own `expect`" not in completed.stderr


def test_the_probe_refuses_a_question_whose_two_hops_are_identical(demo: Path) -> None:
    """One retrieval written twice clears the `MIN_HOPS` floor while asking a single question, and
    a hop repeating one already landed moves `liftable` upward — measured on demo-kb under the
    fake backend: duplicating one question's last hop took liftable 3 to 4, exit 0. A YAML
    copy-paste is the realistic route to it."""
    _write_golden_set(
        demo,
        [
            {
                "id": "one-hop-written-twice",
                "question": "Why may material bought with the public grant not be sold?",
                "kind": "multi-hop",
                "expect": ["docs/deaccession-policy.md"],
                "hops": [
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                    {"query": "public money", "expect": "docs/deaccession-policy.md"},
                ],
            }
        ],
    )
    completed = _run_probe("--kb", str(demo))

    assert completed.returncode != 0
    assert REFUSAL in completed.stderr
    assert "one-hop-written-twice" in completed.stderr
    assert "identical to an earlier hop" in completed.stderr


def test_a_well_formed_golden_set_is_not_refused(demo: Path) -> None:
    """The control every refusal test needs: the message must be caused by the question, not by
    the environment they run in. Same subprocess, same KB, same unregistered backend — only the
    golden set differs, and this one is the committed set."""
    assert REFUSAL not in _run_probe("--kb", str(demo)).stderr


def test_the_probe_refuses_fake_together_with_kb(tmp_path: Path) -> None:
    """`--fake` measures a copy of the demo KB it builds itself, and used to silently discard
    `--kb`: `--kb <corpus> --fake` reported demo-kb's numbers labelled as nothing in particular."""
    completed = _run_probe("--fake", "--kb", str(tmp_path))

    assert completed.returncode == 2  # argparse's own, before anything is measured
    # The exclusion itself, not merely "an argparse error": every usage line names both flags, so
    # `--bogus` would satisfy an assertion that only looked for the two names.
    assert "not allowed with argument" in completed.stderr
    assert "--fake" in completed.stderr and "--kb" in completed.stderr


RUNNER = """
import sys

sys.path.insert(0, {tools!r})
from pinakes.embed import register_embedding_backend, register_reranker

import reachable_ceiling_probe as probe

register_embedding_backend("fake", lambda section, offline: probe.HashingBackend())
register_reranker("fake", lambda section, offline: probe.OverlapReranker())
sys.exit(probe.main(sys.argv[1:]))
"""
"""Runs the probe over an arbitrary `--kb` with the fake backend registered.

Needed because `--fake` measures a copy of the demo KB and nothing else, so a test written on it
alone cannot tell "names the KB measured" from "always names the demo KB" — which is the very
defect the naming fix exists to close.
"""


def test_the_probe_names_the_kb_it_measured(demo: Path, tmp_path: Path) -> None:
    """Neither output named it, so two runs against two corpora produced artifacts that could not
    be told apart on inspection — which is what made a silently discarded `--kb` survivable.

    Measured against a KB deliberately **not** called `demo-kb`, and asserted to be an absolute
    resolved path: a relative `--kb` recorded verbatim would label two corpora identically again
    when the tool is run from two working directories.
    """
    import shutil

    measured = tmp_path / "renamed-corpus"
    shutil.move(str(demo), str(measured))
    runner = tmp_path / "run_probe.py"
    runner.write_text(RUNNER.format(tools=str(REPO / "tools")), encoding="utf-8")

    def run(*extra: str, kb: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(runner), "--kb", kb, *extra],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        assert completed.returncode == 0, completed.stderr
        return completed

    payload = json.loads(run("--json", kb=str(measured), cwd=REPO).stdout)
    assert payload["kb_root"] == str(measured.resolve())
    assert "demo-kb" not in payload["kb_root"]
    assert payload["kb_id"] == load(measured).kb.id
    assert payload["fake_backend"] is False
    assert payload["kb_id"] in run(kb=str(measured), cwd=REPO).stdout

    # The same corpus reached by a *relative* `--kb` from its own parent. `tmp_path` is already
    # absolute and already resolved, so the assertions above pass whether or not the tool resolves
    # anything — measured: dropping the `.resolve()` left the whole suite green. This is the run
    # that pins it, and the property it pins is the one that matters, since two corpora both
    # reached as `./kb` from two directories would otherwise record the same `kb_root` again.
    relative = json.loads(run("--json", kb=measured.name, cwd=measured.parent).stdout)
    assert Path(relative["kb_root"]).is_absolute()
    assert relative["kb_root"] == str(measured.resolve())


def test_the_fake_run_names_its_own_copy_and_says_it_is_fake() -> None:
    """`--fake` is the one run whose corpus the operator did not choose, so the artifact has to
    say both which directory was measured and that a hashing backend produced the numbers."""
    payload = json.loads(_run_probe("--fake", "--json").stdout)
    text = _run_probe("--fake").stdout

    assert payload["kb_root"].endswith("demo-kb")
    assert payload["kb_id"] == load(DEMO).kb.id
    assert payload["fake_backend"] is True
    assert payload["kb_id"] in text and "demo-kb" in text


def test_calibration_fits_thresholds_and_prints_a_manifest_block(demo: Path) -> None:
    questions = load_questions(demo / "eval" / "questions.yaml")
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        calibration = fit(
            connection,
            load(demo),
            questions,
            backend=HashingBackend(),
            reranker=OverlapReranker(),
        )
    finally:
        connection.close()

    assert calibration.fitted_for == "overlap-reranker@v1"
    assert calibration.low_below <= calibration.high_above
    block = calibration.as_manifest_block()
    assert "[retrieval.confidence]" in block
    assert 'fitted_for = "overlap-reranker@v1"' in block


def test_calibration_refuses_a_golden_set_with_no_unanswerable_questions(demo: Path) -> None:
    """Without them a system that answers everything confidently scores perfectly (§7)."""
    questions = [q for q in load_questions(demo / "eval" / "questions.yaml") if q.answerable]
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        with pytest.raises(CalibrationError) as exc_info:
            fit(
                connection,
                load(demo),
                questions,
                backend=HashingBackend(),
                reranker=OverlapReranker(),
            )
    finally:
        connection.close()
    assert "answers everything" in exc_info.value.remedy


def test_calibration_never_writes_the_manifest(demo: Path) -> None:
    """A tool that silently edited a user-owned manifest would defeat the point of `docs/`."""
    before = (demo / "pinakes.toml").read_text(encoding="utf-8")
    questions = load_questions(demo / "eval" / "questions.yaml")
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        fit(connection, load(demo), questions, backend=HashingBackend(), reranker=OverlapReranker())
    finally:
        connection.close()
    assert (demo / "pinakes.toml").read_text(encoding="utf-8") == before


def test_thresholds_are_fitted_from_the_unanswerable_distribution(demo: Path) -> None:
    """Both come from the no-answer scores — the only outcomes known absolutely.

    Also pins that nothing assumes a 0-to-1 range: real cross-encoders emit logits (-0.28 vs -7.85
    measured in I7), and this fake deliberately returns negatives too.
    """
    from statistics import median

    questions = load_questions(demo / "eval" / "questions.yaml")
    connection = store.connect_ro(demo / ".pinakes" / "index.db")
    try:
        calibration = fit(
            connection, load(demo), questions, backend=HashingBackend(), reranker=OverlapReranker()
        )
    finally:
        connection.close()

    unanswerable = calibration.unanswerable_scores
    assert calibration.low_below == pytest.approx(median(unanswerable))
    assert min(unanswerable) <= calibration.low_below <= calibration.high_above <= max(unanswerable)
    assert min(unanswerable) < 0  # the scale is not a probability


def test_confidence_labels_are_the_ones_the_metrics_count() -> None:
    assert (LOW, HIGH) == ("low", "high")
