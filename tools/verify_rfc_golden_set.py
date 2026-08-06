"""Check the RFC golden set against a built corpus: every `expect` is backed by its `evidence`.

**The error this exists to catch is self-concealing.** A question pointing at the wrong document
looks exactly like a retrieval miss — the system searches, does not find the expected path, and
scores a miss. Nothing distinguishes that from a genuine failure of retrieval, so a set with bad
`expect` values inflates the improvable pool and makes a power criterion pass for the wrong reason.
The measurement then rests on questions nobody could answer either.

So every answerable question records the sentence from its expected document that answers it, and
this tool refuses the set if a sentence is not there. `pinakes.eval` ignores the `evidence` key;
this is what reads it.

The corpus is regenerated rather than committed (`build_rfc_corpus.py`), so the check has to be
runnable against any rebuild:

    python3 tools/verify_rfc_golden_set.py --kb ~/pinakes-rfc-corpus

**Whitespace is normalised before matching, and that is not laziness.** RFC bodies are hard-wrapped
at about 72 columns, so most sentences span two lines and the recorded evidence is usually the
fragment carrying the answer. Matching a normalised substring is what makes a verbatim copy from a
column-formatted document checkable at all.

What it does *not* check: that the question is answerable only by that document. RFC subject matter
overlaps, and no mechanical test separates "the document that answers it" from "a document that
mentions the same protocol". That one is bounded by how the set was authored — one document per
question, anchored on something specific to it — and by review.
"""

import argparse
import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pinakes.eval import KINDS, NO_ANSWER, load_questions

DEFAULT_QUESTIONS = Path(__file__).resolve().parent / "rfc_corpus" / "questions.yaml"


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def evidence_of(path: Path) -> dict[str, str]:
    """The raw `evidence` strings by question id — `load_questions` drops the key it does not know.

    Read with the same YAML loader the eval uses, so a file that loads there loads here. Typed
    through `cast` rather than `isinstance`, which narrows a parsed mapping only to
    `dict[Unknown, Unknown]` and leaves every index unchecked.
    """
    from ruamel.yaml import YAML

    loaded: object = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    document = cast("dict[str, object]", loaded) if isinstance(loaded, dict) else {}
    raw: object = document.get("questions") or []
    entries = cast("list[dict[str, object]]", raw) if isinstance(raw, list) else []
    return {str(entry.get("id", "")): str(entry.get("evidence") or "") for entry in entries}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_rfc_golden_set", description=__doc__)
    parser.add_argument("--kb", type=Path, required=True, help="a corpus built by build_rfc_corpus")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    args = parser.parse_args(argv)

    kb: Path = args.kb.expanduser()
    questions = load_questions(args.questions)
    evidence = evidence_of(args.questions)
    bodies: dict[Path, str] = {}
    problems: list[str] = []

    for question in questions:
        if question.kind not in KINDS:  # pragma: no cover — load_questions refuses these first
            problems.append(f"{question.id}: unknown kind {question.kind!r}")
        if question.kind == NO_ANSWER:
            if question.expect or evidence.get(question.id, ""):
                problems.append(
                    f"{question.id}: a no-answer question expects nothing and cites nothing"
                )
            continue

        if len(question.expect) != 1:
            problems.append(f"{question.id}: expected exactly one document, got {question.expect}")
            continue
        source = kb / question.expect[0]
        if not source.exists():
            problems.append(f"{question.id}: {question.expect[0]} is not in {kb}")
            continue

        sentence = evidence.get(question.id, "")
        if not sentence.strip():
            problems.append(f"{question.id}: no evidence sentence")
            continue
        if source not in bodies:
            bodies[source] = normalise(source.read_text(encoding="utf-8"))
        if normalise(sentence) not in bodies[source]:
            problems.append(
                f"{question.id}: evidence is not in {question.expect[0]} — {sentence[:70]!r}"
            )

    answerable = [q for q in questions if q.answerable]
    print(
        f"golden set: {len(questions)} questions, {len(answerable)} answerable, "
        f"{len(questions) - len(answerable)} unanswerable, "
        f"{len({q.expect[0] for q in answerable if q.expect})} distinct documents"
    )
    if problems:
        print(f"\n{len(problems)} problems:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("every answerable question's evidence is present in the document it expects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
