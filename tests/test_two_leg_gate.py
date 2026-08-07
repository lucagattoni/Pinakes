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
    """The gap this tool exists to close. `graph_gate.check_identity` checks `k`, `embedding`,
    `rerank`, `ranking` and `retrieval` — not `chunking` — so two legs chunked at different
    `max_tokens` compared clean, and measured on one RFC that is 63 of 1 858 chunk texts differing
    between 510 and 480. The rechunk would be reported as the effect under test."""
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
