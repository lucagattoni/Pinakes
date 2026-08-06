"""The frozen RFC golden set: what can be checked without the corpus, and what cannot.

The corpus is regenerated rather than committed, so nothing here can confirm that a question's
`expect` is the document that answers it — `tools/verify_rfc_golden_set.py` does that against a
built KB, using the `evidence` sentence each question carries. These are the properties that hold
independently of any corpus, and every one of them is a way the set could silently stop being an
instrument: a kind nothing scores, an unanswerable question that expects a document, a set with
nothing to calibrate against.
"""

import re
import sys
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from pinakes.eval import NO_ANSWER, load_questions

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from build_rfc_corpus import GOLDEN_SET, write_golden_set  # noqa: E402

USED_KINDS = {"lexical", "simple-lookup", "paraphrase", NO_ANSWER}


@pytest.fixture(scope="module")
def questions():
    return load_questions(GOLDEN_SET)


def evidence_by_id() -> dict[str, str]:
    document = YAML(typ="safe").load(GOLDEN_SET.read_text(encoding="utf-8")) or {}
    return {str(e.get("id", "")): str(e.get("evidence") or "") for e in document["questions"]}


def test_the_set_loads_and_every_question_has_a_written_id(questions) -> None:
    """`load_questions` derives an id from the question text when one is absent, and a derived id
    moves the moment the wording does — which silently drops that question from every before/after
    comparison. The committed set writes its ids out, so this asserts the file does, not that the
    loader can cope."""
    document = YAML(typ="safe").load(GOLDEN_SET.read_text(encoding="utf-8"))
    written = [entry.get("id") for entry in document["questions"]]

    assert questions
    assert all(written), "every question must carry an explicit id"
    assert len(set(written)) == len(written)
    assert {q.id for q in questions} == set(written)


def test_only_the_four_scored_kinds_are_used(questions) -> None:
    """`filter` and `multi-hop` are absent by decision, not by oversight. `filter` needs metadata
    worth filtering on and these sidecars carry a title and nothing else; `multi-hop` is the graph
    channel's class and `graph_channel` is off for this corpus, so such a question would score as
    an ordinary lookup while claiming to measure something else. A question in either kind would be
    scored and reported as if it measured what its name says."""
    assert {q.kind for q in questions} == USED_KINDS


def test_every_answerable_question_names_one_document_and_cites_a_sentence(questions) -> None:
    """One document, because `hit_rank` is the rank of the *first* expected path found: a second
    path makes the question easier in a way nothing records. A sentence, because a wrong `expect`
    is indistinguishable from a retrieval miss and would inflate the improvable pool."""
    evidence = evidence_by_id()
    answerable = [q for q in questions if q.answerable]

    assert answerable
    for question in answerable:
        assert len(question.expect) == 1, question.id
        assert question.expect[0].startswith("docs/rfc"), question.id
        assert evidence.get(question.id, "").strip(), question.id


def test_the_set_can_be_calibrated_against(questions) -> None:
    """`calibrate.py` fits **both** confidence thresholds against the scores of the unanswerable
    questions, "because those are the ones whose correct outcome is known absolutely". A set
    without them cannot be calibrated at all — and on this corpus an uncalibrated manifest makes
    every confidence `unknown`, which reports `false_abstain` as a vacuous 0.0 rather than as
    unmeasured."""
    unanswerable = [q for q in questions if not q.answerable]

    assert len(unanswerable) >= 5
    for question in unanswerable:
        assert question.expect == (), question.id
        assert not evidence_by_id().get(question.id, ""), question.id


def test_no_question_names_a_document_or_a_section(questions) -> None:
    """A question naming an RFC number hands the retriever the answer through the filename, and one
    naming a section is asking about the corpus's structure rather than its subject. Both would be
    measuring the wrong thing while looking like ordinary questions."""
    offenders = [
        q.id for q in questions if re.search(r"\brfc\s?\d{3,4}\b|\bsection\s+\d", q.question, re.I)
    ]

    assert offenders == []


def test_a_built_corpus_gets_the_committed_set_copied_into_it(tmp_path: Path) -> None:
    """`pinakes.eval` defaults to `<kb>/eval/questions.yaml`, so the documented run works with no
    path flag only if the build puts it there. Unlike `pinakes.toml`, this file is overwritten on
    every build: the repository copy is the source of truth, and a corpus evaluated against a
    stale one would be answering questions nobody could find."""
    assert write_golden_set(tmp_path) is True

    copied = tmp_path / "eval" / "questions.yaml"
    assert copied.read_text(encoding="utf-8") == GOLDEN_SET.read_text(encoding="utf-8")
    assert len(load_questions(copied)) == len(load_questions(GOLDEN_SET))
