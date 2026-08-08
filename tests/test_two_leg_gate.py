"""`tools/two_leg_gate.py`, driven as a subprocess — one test per way it can be wrong.

A subprocess rather than an import, for the reason `tests/test_status_header_gate.py` gives: it
exercises the same artifact a run of the experiment invokes, argument parsing included, with no
`sys.path` surgery.

**The defect these exist to catch is a comparison that always produces numbers.** A rank
comparison cannot fail loudly on its own — two unrelated artifacts compare perfectly happily and
report a count — so every refusal below asserts the *stated reason*, not merely a non-zero exit.
"""

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

TOOL = Path(__file__).parent.parent / "tools" / "two_leg_gate.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args], capture_output=True, text=True, check=False
    )


def header(metadata: str = "off", **overrides: Any) -> dict[str, Any]:
    """A header shaped like `eval.header`'s, with the one key the legs may differ on."""
    base: dict[str, Any] = {
        "graph_channel": "off",
        "edge_kinds": ["authored"],
        "dropped": [],
        "ranking": {"link_distance": True, "in_degree_salience": False},
        "schema": 1,
        "k": 5,
        "chunking": {
            "max_tokens": 414,
            "overlap": 64,
            "headings": "numbered",
            "metadata": metadata,
        },
        "embedding": {"provider": "fastembed", "model": "bge-small", "dim": 384},
        "rerank": None,
        "retrieval": {"rerank": "none", "final_k": 8},
    }
    return base | overrides


def leg(path: Path, rows: Sequence[tuple[str, str, bool, int | None]], **kwargs: Any) -> Path:
    path.write_text(
        json.dumps(
            header(**kwargs)
            | {
                "questions": [
                    {"id": id_, "kind": kind, "hit": hit, "hit_rank": rank, "confidence": "high"}
                    for id_, kind, hit, rank in rows
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


PAIR = [
    ("q1", "paraphrase", True, 3),
    ("q2", "lexical", True, 1),
    ("q3", "paraphrase", False, None),
]


def test_more_improvements_than_regressions_passes_the_screen(tmp_path: Path) -> None:
    """2d's pre-registered criterion, and the only thing the screen decides: whether the schema
    bump at 2e is worth taking."""
    before = leg(tmp_path / "before.json", PAIR, metadata="off")
    after = leg(
        tmp_path / "after.json",
        [("q1", "paraphrase", True, 1), ("q2", "lexical", True, 1), ("q3", "paraphrase", True, 4)],
        metadata="prefix",
    )
    result = run("--before", str(before), "--after", str(after))

    assert result.returncode == 0, result.stderr
    assert "improved               2" in result.stdout
    assert "regressed              0" in result.stdout
    assert "unchanged              1" in result.stdout


def test_a_miss_is_worse_than_any_hit_in_both_directions(tmp_path: Path) -> None:
    """The one judgement call in the rank rule. Treating "no rank" as *unchanged* would let a
    change that loses an answer outright read as neutral — and losing answers is the outcome this
    comparison most needs to be able to see."""
    before = leg(tmp_path / "before.json", [("q1", "paraphrase", True, 5)], metadata="off")
    after = leg(tmp_path / "after.json", [("q1", "paraphrase", False, None)], metadata="prefix")
    lost = run("--before", str(before), "--after", str(after))

    assert lost.returncode == 1
    assert "regressed              1" in lost.stdout
    assert "q1 [paraphrase] 5 -> miss" in lost.stdout

    found = run("--before", str(after), "--after", str(before), "--excepting", "chunking.metadata")
    assert found.returncode == 0
    assert "q1 [paraphrase] miss -> 5" in found.stdout


def test_no_answer_questions_are_excluded(tmp_path: Path) -> None:
    """They have no rank to move: their correct outcome is an abstention, which `score_rows`
    already counts as `false_confidence`. Counting them here would score the same question twice
    under a criterion that cannot describe it."""
    before = leg(
        tmp_path / "before.json",
        [("q1", "paraphrase", True, 2), ("n1", "no-answer", True, None)],
        metadata="off",
    )
    after = leg(
        tmp_path / "after.json",
        [("q1", "paraphrase", True, 1), ("n1", "no-answer", False, None)],
        metadata="prefix",
    )
    result = run("--before", str(before), "--after", str(after))

    assert result.returncode == 0
    assert "answerable questions   1" in result.stdout
    assert "n1" not in result.stdout


def test_it_refuses_two_legs_chunked_differently(tmp_path: Path) -> None:
    """The gap this tool exists to close, and it was the general one: nothing compared `chunking`,
    so two legs chunked at different `max_tokens` compared clean — measured on one RFC, 63 of
    1 858 chunk texts differ between 510 and 480 — and the rechunk was reported as the effect under
    test.

    `graph_gate.check_identity` had the same hole and no longer does (open-corrections item 1). The
    two tools now differ only in what they except: this one excepts `chunking.metadata`, because
    here that key **is** the independent variable, and the graph gate excepts nothing under
    `chunking`, because there the independent variable is `graph_channel`."""
    before = leg(tmp_path / "before.json", PAIR, metadata="off")
    after = leg(tmp_path / "after.json", PAIR, metadata="prefix")
    rechunked = json.loads(after.read_text(encoding="utf-8"))
    rechunked["chunking"]["max_tokens"] = 480
    after.write_text(json.dumps(rechunked), encoding="utf-8")

    result = run("--before", str(before), "--after", str(after))

    assert result.returncode == 2
    assert "chunking.max_tokens" in result.stderr
    assert "414" in result.stderr and "480" in result.stderr


def test_it_refuses_a_leg_compared_against_itself(tmp_path: Path) -> None:
    """Both legs uninjected reports "nothing moved" — a clean null with no error, and the most
    expensive way to be wrong here, because it looks exactly like the result the screen might
    honestly return."""
    before = leg(tmp_path / "before.json", PAIR, metadata="off")
    same = leg(tmp_path / "same.json", PAIR, metadata="off")

    result = run("--before", str(before), "--after", str(same))

    assert result.returncode == 2
    assert "compares a configuration against itself" in result.stderr


def test_it_refuses_an_artifact_that_cannot_say_which_side_it_is(tmp_path: Path) -> None:
    """Every leg produced before 2d has no `chunking.metadata` key at all — including 2c's
    committed `before` leg, which is why the screen captured its own."""
    before = leg(tmp_path / "before.json", PAIR, metadata="off")
    old = json.loads(before.read_text(encoding="utf-8"))
    del old["chunking"]["metadata"]
    (tmp_path / "old.json").write_text(json.dumps(old), encoding="utf-8")

    result = run("--before", str(tmp_path / "old.json"), "--after", str(before))

    assert result.returncode == 2
    assert "cannot say which side of the change it is" in result.stderr


def test_it_refuses_legs_that_do_not_cover_the_same_questions(tmp_path: Path) -> None:
    """Rows pair on `id`. It is why the frozen golden set may never be reworded or renumbered:
    a renamed question is an unpaired row, and an unpaired row is a question dropped from the
    comparison rather than an error."""
    before = leg(tmp_path / "before.json", PAIR, metadata="off")
    after = leg(tmp_path / "after.json", PAIR[:2], metadata="prefix")

    result = run("--before", str(before), "--after", str(after))

    assert result.returncode == 2
    assert "do not cover the same questions" in result.stderr
    assert "q3" in result.stderr


def test_the_sign_test_is_opt_in_and_reports_its_own_verdict(tmp_path: Path) -> None:
    """The gate at 2f, layered on the same comparison — never the screen, whose criterion is
    deliberately looser and whose numbers are not evidence in either direction."""
    rows = [(f"q{n}", "paraphrase", True, 3) for n in range(6)]
    before = leg(tmp_path / "before.json", rows, metadata="off")
    after = leg(
        tmp_path / "after.json",
        [(f"q{n}", "paraphrase", True, 1) for n in range(6)],
        metadata="prefix",
    )

    plain = run("--before", str(before), "--after", str(after))
    assert "sign test" not in plain.stdout

    gated = run("--before", str(before), "--after", str(after), "--sign-test")
    assert "sign test p            0.0156   PASS at 0.05" in gated.stdout


def test_the_json_artifact_carries_every_moved_row(tmp_path: Path) -> None:
    before = leg(tmp_path / "before.json", PAIR, metadata="off")
    after = leg(
        tmp_path / "after.json",
        [("q1", "paraphrase", True, 1), ("q2", "lexical", True, 1), ("q3", "paraphrase", True, 4)],
        metadata="prefix",
    )
    out = tmp_path / "screen.json"

    run("--before", str(before), "--after", str(after), "--json", str(out))

    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["improved"] == 2 and written["regressed"] == 0
    assert written["screen_passes"] is True
    assert [move["id"] for move in written["moved"]] == ["q1", "q3"]
    # 2d's screen is pre-registered as having no p-value, and its numbers may not be cited as
    # evidence in either direction. One left in the file is one that gets quoted later.
    assert "sign_test_p" not in written

    gated = tmp_path / "gate.json"
    run("--before", str(before), "--after", str(after), "--sign-test", "--json", str(gated))
    assert "sign_test_p" in json.loads(gated.read_text(encoding="utf-8"))


def test_the_exit_code_answers_the_criterion_that_was_asked_for(tmp_path: Path) -> None:
    """**A gate that prints FAIL and exits 0.** `--sign-test` is the 2f criterion — the run that
    licenses an irreversible `schema_version` bump — so when it is asked for, it is what the exit
    code must answer. Six improvements against five regressions passes the screen (6 > 5) and fails
    the gate (p = 0.5), and a driver script branching on `$?` would otherwise take the bump."""
    rows = [(f"q{n}", "paraphrase", True, 3) for n in range(11)]
    before = leg(tmp_path / "before.json", rows, metadata="off")
    after = leg(
        tmp_path / "after.json",
        [(f"q{n}", "paraphrase", True, 1 if n < 6 else 5) for n in range(11)],
        metadata="prefix",
    )

    screen = run("--before", str(before), "--after", str(after))
    assert screen.returncode == 0, "6 improved > 5 regressed passes the screen"

    gate = run("--before", str(before), "--after", str(after), "--sign-test")
    assert "FAIL at 0.05" in gate.stdout
    assert gate.returncode == 1, "and the same run fails the gate, which the exit code must say"


def test_an_unreadable_leg_is_not_reported_as_a_no_go(tmp_path: Path) -> None:
    """Exit 3, never 1. A mistyped path or an eval run truncated mid-write would otherwise be
    indistinguishable from "the screen returned no-go" — and that verdict costs a 46-minute rebuild
    pair to re-derive."""
    before = leg(tmp_path / "before.json", PAIR, metadata="off")

    missing = run("--before", str(tmp_path / "nope.json"), "--after", str(before))
    assert missing.returncode == 3
    assert "could not read a leg" in missing.stderr

    (tmp_path / "truncated.json").write_text('{"questions": [', encoding="utf-8")
    malformed = run("--before", str(tmp_path / "truncated.json"), "--after", str(before))
    assert malformed.returncode == 3


def test_a_miss_is_null_in_the_artifact_because_json_has_no_infinity(tmp_path: Path) -> None:
    """`json.dumps(math.inf)` emits a bare `Infinity` token: `JSON.parse` rejects it outright and
    `jq` silently coerces it to 1.8e308 — turning the one outcome the rank ordering exists to make
    visible into a finite rank, and a very good one at that."""
    before = leg(tmp_path / "before.json", [("q1", "paraphrase", True, 3)], metadata="off")
    after = leg(tmp_path / "after.json", [("q1", "paraphrase", False, None)], metadata="prefix")
    out = tmp_path / "screen.json"

    run("--before", str(before), "--after", str(after), "--json", str(out))

    raw = out.read_text(encoding="utf-8")
    assert "Infinity" not in raw
    assert json.loads(raw)["moved"][0] == {
        "id": "q1",
        "kind": "paraphrase",
        "before": 3,
        "after": None,
    }


def test_the_report_and_the_artifact_both_name_which_leg_was_which(tmp_path: Path) -> None:
    """Transposing `--before` and `--after` inverts the verdict, and the identity check cannot
    catch it: the tool is never told which value is the baseline, only that the two must differ.
    So the legs are named — `eval.header`'s own docstring gives the reason, that a before file and
    an after file are "otherwise indistinguishable on inspection"."""
    before = leg(tmp_path / "before.json", PAIR, metadata="off")
    after = leg(
        tmp_path / "after.json",
        [("q1", "paraphrase", True, 1), ("q2", "lexical", True, 1), ("q3", "paraphrase", True, 4)],
        metadata="prefix",
    )
    out = tmp_path / "screen.json"

    result = run("--before", str(before), "--after", str(after), "--json", str(out))

    assert "before.json   (chunking.metadata = 'off')" in result.stdout
    assert "after.json   (chunking.metadata = 'prefix')" in result.stdout
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["excepting"] == "chunking.metadata"
    assert written["before"]["value"] == "off" and written["after"]["value"] == "prefix"
    assert written["before"]["path"].endswith("before.json")
