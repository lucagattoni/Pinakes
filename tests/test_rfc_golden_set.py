"""The frozen RFC golden set: what can be checked without the corpus, and what cannot.

The corpus is regenerated rather than committed, so nothing here can confirm that a question's
`expect` really is the document that answers it — `tools/verify_rfc_golden_set.py` does that
against a built KB, using the `evidence` sentence each question carries. What is asserted here are
the properties that hold independently of any corpus, and each one is a way the set could quietly
stop being an instrument: a kind nothing scores, an unanswerable question that expects a document,
a set with nothing left to calibrate against, a baseline describing a set that has moved on.

The build itself is exercised in `tests/test_build_rfc_corpus.py`, as a subprocess — this repo's
convention for `tools/`, so that what is tested is the artifact an operator runs.
"""

import json
import re
from pathlib import Path
from typing import cast

import pytest
from ruamel.yaml import YAML

from pinakes.eval import NO_ANSWER, Question, load_questions

RFC_CORPUS = Path(__file__).resolve().parent.parent / "tools" / "rfc_corpus"
GOLDEN_SET = RFC_CORPUS / "questions.yaml"
USED_KINDS = {"lexical", "simple-lookup", "paraphrase", NO_ANSWER}


@pytest.fixture(scope="module")
def questions() -> list[Question]:
    return load_questions(GOLDEN_SET)


def entries() -> list[dict[str, object]]:
    """The set as written, before `load_questions` drops the keys it does not know about.

    `cast`, not `isinstance`: a parsed mapping narrows only to `dict[Unknown, Unknown]`, which
    neither checker will index — the same note `tests/test_build_rfc_corpus.py` carries.
    """
    loaded: object = YAML(typ="safe").load(GOLDEN_SET.read_text(encoding="utf-8"))
    document = cast("dict[str, object]", loaded)
    return cast("list[dict[str, object]]", document["questions"])


def evidence_by_id() -> dict[str, str]:
    return {str(e.get("id", "")): str(e.get("evidence") or "") for e in entries()}


def test_every_question_carries_a_written_id(questions: list[Question]) -> None:
    """`load_questions` derives an id from the question text when one is absent, and a derived id
    moves the moment the wording does — which silently drops that question from every before/after
    comparison. This asserts the *file* writes its ids out, not that the loader can cope without
    them."""
    written = [entry.get("id") for entry in entries()]

    assert questions
    assert all(written), "every question must carry an explicit id"
    assert len(set(written)) == len(written)
    assert {q.id for q in questions} == set(written)


def test_only_the_four_scored_kinds_are_used(questions: list[Question]) -> None:
    """`filter` and `multi-hop` are absent by decision, not by oversight. `filter` needs metadata
    worth filtering on and these sidecars carry a title and nothing else; `multi-hop` is the graph
    channel's class and `graph_channel` is off for this corpus, so such a question would score as
    an ordinary lookup while being reported under a name claiming it measured something else."""
    assert {q.kind for q in questions} == USED_KINDS


def test_every_answerable_question_names_one_document_and_cites_a_sentence(
    questions: list[Question],
) -> None:
    """One document, because `hit_rank` is the rank of the *first* expected path found: a second
    path makes a question easier in a way nothing records. A sentence, because a wrong `expect` is
    indistinguishable from a retrieval miss and would inflate the improvable pool below."""
    evidence = evidence_by_id()
    answerable = [q for q in questions if q.answerable]

    assert answerable
    for question in answerable:
        assert len(question.expect) == 1, question.id
        assert question.expect[0].startswith("docs/rfc"), question.id
        assert evidence.get(question.id, "").strip(), question.id


def test_the_set_can_be_calibrated_against(questions: list[Question]) -> None:
    """`calibrate.py` fits **both** confidence thresholds against the scores of the unanswerable
    questions, "because those are the ones whose correct outcome is known absolutely". A set
    without them cannot be calibrated at all — and on this corpus an uncalibrated manifest makes
    every confidence `unknown`, reporting `false_abstain` as a vacuous 0.0 rather than as
    unmeasured."""
    evidence = evidence_by_id()
    unanswerable = [q for q in questions if not q.answerable]

    assert len(unanswerable) >= 5
    for question in unanswerable:
        assert question.expect == (), question.id
        assert not evidence.get(question.id, ""), question.id


def test_no_question_names_a_document_or_a_section(questions: list[Question]) -> None:
    """A question naming an RFC number hands the retriever its answer through the filename, and one
    naming a section asks about the corpus's structure rather than its subject. Either would be
    measuring something other than retrieval while looking like an ordinary question."""
    offenders = [
        q.id for q in questions if re.search(r"\brfc\s?\d{3,4}\b|\bsection\s+\d", q.question, re.I)
    ]

    assert offenders == []


def test_the_committed_before_leg_still_describes_the_committed_set(
    questions: list[Question],
) -> None:
    """The baseline and the golden set are one artifact in two files, and nothing else pairs them.

    Adding a question without regenerating the `before` leg leaves an artifact silently describing
    a different set — and the gate compares against it. The improvable pool is asserted here too,
    because it is the exit criterion this increment had to **meet** rather than merely report: at
    least 10 answerable questions missed or below rank 1, since `sign_test(4, 0)` = 0.0625 fails
    the p < 0.05 bar the gate is held to while `sign_test(10, 0)` = 0.0010 passes.
    """
    leg = cast(
        "dict[str, object]", json.loads((RFC_CORPUS / "outcomes.json").read_text(encoding="utf-8"))
    )
    rows = cast("list[dict[str, object]]", leg["questions"])

    assert {str(row["id"]) for row in rows} == {q.id for q in questions}

    pool = [
        row
        for row in rows
        if row["kind"] != NO_ANSWER and (row["hit_rank"] is None or int(str(row["hit_rank"])) > 1)
    ]
    assert len(pool) >= 10, f"improvable pool is {len(pool)}; the gate cannot be reached"


def _tiny_corpus(root: Path, body: str) -> Path:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "rfc9999.txt").write_text(body, encoding="utf-8")
    return root


def _questions_file(path: Path, *, evidence: str) -> Path:
    path.write_text(
        "questions:\n"
        "  - id: lex-probe\n"
        "    question: What does the widget carry?\n"
        "    kind: lexical\n"
        "    expect: [docs/rfc9999.txt]\n"
        f"    evidence: {evidence!r}\n".replace("'", '"'),
        encoding="utf-8",
    )
    return path


def test_the_verifier_refuses_evidence_that_is_not_in_the_document(tmp_path: Path) -> None:
    """The tool exists for one failure, so it is tested against that failure and its inverse.

    A question pointing at the wrong document is indistinguishable from a retrieval miss, which is
    why `evidence` exists and why a verifier that passed everything would be worse than none — it
    would certify the set while checking nothing.
    """
    import subprocess
    import sys

    tool = Path(__file__).resolve().parent.parent / "tools" / "verify_rfc_golden_set.py"
    kb = _tiny_corpus(tmp_path / "kb", "The widget carries\na payload of bytes.\n")

    def run(questions: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(tool), "--kb", str(kb), "--questions", str(questions)],
            capture_output=True,
            text=True,
            timeout=120,
        )

    good = run(_questions_file(tmp_path / "good.yaml", evidence="The widget carries"))
    assert good.returncode == 0, good.stdout + good.stderr

    bad = run(_questions_file(tmp_path / "bad.yaml", evidence="The widget carries a warranty"))
    assert bad.returncode == 1
    assert "evidence is not in" in bad.stdout


def test_the_verifier_matches_across_the_line_wrapping_rfcs_use(tmp_path: Path) -> None:
    """RFC bodies are hard-wrapped at about 72 columns, so a sentence that reads as one line in the
    golden set spans two in the document. Matching raw text would reject correct evidence and push
    authors toward whatever fragment happened to fit on one line — the check would then be shaping
    the set instead of auditing it."""
    import subprocess
    import sys

    tool = Path(__file__).resolve().parent.parent / "tools" / "verify_rfc_golden_set.py"
    kb = _tiny_corpus(tmp_path / "kb", "   The widget carries a payload\n   of exactly 64 bytes.\n")
    questions = _questions_file(
        tmp_path / "wrapped.yaml", evidence="The widget carries a payload of exactly 64 bytes."
    )

    done = subprocess.run(
        [sys.executable, str(tool), "--kb", str(kb), "--questions", str(questions)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_before_leg_records_the_configuration_the_gate_must_reuse() -> None:
    """The `before` leg is only comparable against an `after` produced the same way, and these are
    the settings that decide that. They are pinned as literals because they *are* the frozen
    experimental configuration: `max_tokens` 414 is the corpus's reserve-bearing value, and a leg
    chunked at the default 510 would be a different corpus wearing the same filename.

    `k` is here because the improvable pool is defined against it — a question missed at k = 5 may
    be a hit at rank 7, so a pool measured at one k does not describe another. `rerank` is here
    because the gate is fixed to `local` in advance, and `graph_channel` because that channel's
    edge kinds partly duplicate what is under test.
    """
    leg = cast(
        "dict[str, object]", json.loads((RFC_CORPUS / "outcomes.json").read_text(encoding="utf-8"))
    )
    chunking = cast("dict[str, object]", leg["chunking"])
    retrieval = cast("dict[str, object]", leg["retrieval"])

    assert chunking["max_tokens"] == 414
    assert leg["k"] == 5
    assert retrieval["rerank"] == "local"
    assert leg["graph_channel"] == "off"
