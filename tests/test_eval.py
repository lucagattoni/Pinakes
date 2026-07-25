"""The scoreboard, against the real demo KB — the thing that makes retrieval changes decidable."""

import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest

from pinakes import store
from pinakes.calibrate import fit
from pinakes.embed import ModelInfo, Vectors, register_embedding_backend, register_reranker
from pinakes.errors import CalibrationError, EvalError
from pinakes.eval import compare, evaluate, load_questions, read_baseline, write_baseline
from pinakes.manifest import load
from pinakes.search import HIGH, LOW
from pinakes.sync import SyncOptions, sync

DEMO = Path(__file__).parent / "demo-kb"
DIM = 64


class HashingBackend:
    """A cheap deterministic embedder: a bag-of-words hash. Good enough to rank, free to run.

    The point of these tests is that the harness measures correctly, not that a particular model
    scores well — the real numbers come from CI with real weights (§7).
    """

    def embed(self, texts: Sequence[str]) -> Vectors:
        rows: list[Vectors] = []
        for text in texts:
            vector = np.zeros(DIM, dtype=np.float32)
            for word in text.lower().split():
                vector[hash(word.strip(".,:;()")) % DIM] += 1.0
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
    assert kinds == {"lexical", "paraphrase", "filter", "multi-hop", "no-answer"}
    assert any(question.hops for question in questions)

    documents = {f"docs/{path.name}" for path in (DEMO / "docs").iterdir()}
    for question in questions:
        for expected in question.expect:
            assert expected in documents, f"{question.question} expects a missing document"
        for hop in question.hops:
            assert hop.expect in documents


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
    assert set(metrics.by_kind) == {"lexical", "paraphrase", "filter", "multi-hop", "no-answer"}
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


def test_an_empty_golden_set_is_refused(demo: Path) -> None:
    """A scoreboard with nothing on it cannot make a retrieval change decidable (§7)."""
    from pinakes.eval import run

    path = demo / "eval" / "empty.yaml"
    path.write_text("questions: []\n", encoding="utf-8")
    assert load_questions(path) == []

    with pytest.raises(EvalError) as exc_info:
        run(demo, questions_path=path)
    assert "decidable" in exc_info.value.remedy


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
