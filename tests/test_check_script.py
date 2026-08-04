"""`check.sh`'s own pdf-quality gate: skips with a printed reason when the extra is absent, and the
script still exits 0 — never silently, never a failure.

Faithfully re-synchronising this repo's `.venv` without `[pdf]` just to prove the skip branch would
make this test as expensive as the gate it is checking; instead, `test_check_sh_declares_the_guard`
pins down that `check.sh` *itself* contains the exact guard, with `make pdf-eval` specifically
inside the `then` branch and specifically absent from the `else` branch — not merely present
*somewhere* in the file, which an explanatory comment sitting next to a silently gutted call would
also satisfy — and `test_the_skip_and_continue_shape_exits_zero` proves the shape that guard is
written in — "a failed import check prints a reason and the script still exits 0" — actually
behaves that way, using a subprocess and an import guaranteed to fail rather than trying to fake
pypdfium2's absence inside an environment where it is, in this checkout, actually installed.
"""

import re
import subprocess
import sys
from pathlib import Path

CHECK_SH = Path(__file__).parent.parent / "check.sh"
WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_check_sh_declares_the_pdf_quality_guard() -> None:
    """A bare substring check (`"make pdf-eval" in text`) would still pass if the real call were
    replaced with a no-op while the explanatory comment above it stayed put — verified directly:
    doing exactly that left every bare-substring assertion green. Matching the actual
    `if ... then / else / fi` block and asserting *where* each string falls (inside `then`, absent
    from `else`) is what a silently gutted gate cannot survive.
    """
    text = CHECK_SH.read_text(encoding="utf-8")
    match = re.search(
        r'if uv run --frozen python3 -c "import pypdfium2" 2>/dev/null; then\n'
        r"(?P<then>.*?)\n"
        r"else\n"
        r"(?P<else>.*?)\n"
        r"fi",
        text,
        re.DOTALL,
    )
    assert match is not None, "check.sh's pdf-quality if/then/else/fi block was not found"
    then_branch, else_branch = match.group("then"), match.group("else")
    assert "make pdf-eval" in then_branch
    assert "make pdf-eval" not in else_branch
    assert "pdf-quality: skipped" in else_branch
    assert "pdf-quality: skipped" not in then_branch


def test_the_skip_and_continue_shape_exits_zero() -> None:
    """The exact shape `check.sh` uses for every extras-dependent gate: `if <python import check>;
    then <run the gate>; else echo '<name>: skipped -- <reason>'; fi`, followed by more script. An
    import guaranteed to fail stands in for "pypdfium2 not installed" — the shape under test is
    generic to every such guard in `check.sh`, not specific to which module it names.
    """
    script = f"""
set -e
if {sys.executable} -c "import definitely_not_a_real_module_xyz" 2>/dev/null; then
    echo "gate ran"
else
    echo "some-gate: skipped -- reason"
fi
echo "all gates green"
"""
    result = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0
    assert "some-gate: skipped -- reason" in result.stdout
    assert "gate ran" not in result.stdout
    assert "all gates green" in result.stdout


def test_check_sh_declares_the_prices_toml_gate() -> None:
    """I6a: unlike the extras-gated checks above, this one has no skip branch — `budget/` has no
    extra to be absent — so nothing else would notice if it were quietly deleted or reduced to a
    no-op. `pyright`/`ruff` never see it: it is shell embedding Python, not a module either
    checker parses."""
    text = CHECK_SH.read_text(encoding="utf-8")
    assert "load_prices" in text
    assert "strptime" in text
    assert "%Y%m%d %H:%M" in text


def test_check_sh_declares_the_link_density_gate() -> None:
    """L1 added a gate to `check.sh` and a job to `ci.yml` and asserted neither, so deleting
    either left the whole suite green. Same reasoning as the pdf-quality guard above: match the
    real invocation, not a substring an explanatory comment would also satisfy."""
    text = CHECK_SH.read_text(encoding="utf-8")
    assert re.search(
        r"^uv run --frozen python3 tools/link_density_gate\.py\s*$", text, re.MULTILINE
    ), "check.sh no longer invokes the link-density gate"


def test_ci_runs_the_link_density_gate_and_proves_it_can_fail() -> None:
    """`ci.yml` never invokes `check.sh`, so a gate living only there runs only where someone
    remembers. The negative step matters as much as the positive one: a gate nobody has watched
    fail is a gate nobody knows works."""
    workflow = _workflow()
    job = re.search(r"^  link-density:\n(?P<body>(?:    .*\n|\n)*)", workflow, re.MULTILINE)
    assert job is not None, "ci.yml has no link-density job"
    body = job.group("body")
    assert "tools/link_density_gate.py" in body
    assert "--max-degree 0" in body, "the negative check is gone — nothing proves the gate gates"
    assert "exit 1" in body, "the negative check no longer fails the job"


def test_check_sh_declares_the_traversal_cap_gate() -> None:
    """L3's caps are the only thing between an agent's `depth=99` and most of a KB in one
    response. Same pinning as the two gates above: match the real invocation."""
    text = CHECK_SH.read_text(encoding="utf-8")
    assert re.search(
        r"^uv run --frozen python3 tools/traversal_cap_gate\.py\s*$", text, re.MULTILINE
    ), "check.sh no longer invokes the traversal-cap gate"


def test_ci_runs_the_traversal_cap_gate() -> None:
    workflow = _workflow()
    job = re.search(r"^  traversal-caps:\n(?P<body>(?:    .*\n|\n)*)", workflow, re.MULTILINE)
    assert job is not None, "ci.yml has no traversal-caps job"
    body = job.group("body")
    assert "tools/traversal_cap_gate.py" in body
    assert "--expect-depth 99" in body, "the negative check is gone — nothing proves it gates"
    assert "the caps moved" in body, "the negative check no longer requires the stated reason"


def test_check_sh_declares_the_eval_reproducibility_gate() -> None:
    """G1. Same pinning as its three siblings: match the real invocation, never a substring that an
    explanatory comment would also satisfy."""
    text = CHECK_SH.read_text(encoding="utf-8")
    assert re.search(
        r"^uv run --frozen python3 tools/eval_reproducibility_gate\.py\s*$", text, re.MULTILINE
    ), "check.sh no longer invokes the eval-reproducibility gate"


def test_ci_runs_the_eval_reproducibility_gate_and_proves_it_can_fail() -> None:
    workflow = _workflow()
    job = re.search(r"^  eval-reproducibility:\n(?P<body>(?:    .*\n|\n)*)", workflow, re.MULTILINE)
    assert job is not None, "ci.yml has no eval-reproducibility job"
    body = job.group("body")
    assert "tools/eval_reproducibility_gate.py" in body
    assert "--inject-difference" in body, "the negative check is gone — nothing proves it gates"
    assert "questions changed outcome" in body, (
        "the negative check no longer requires the stated reason, so a crash would satisfy it"
    )


def test_check_sh_declares_the_status_header_gate() -> None:
    """docs/STATUS.md's header drifted from `__version__` for four consecutive releases because
    only a checklist watched it (plans/20260731_1202-open-corrections.md, 20260803). Same pinning
    as its
    siblings: match the real invocation, never a substring that an explanatory comment would also
    satisfy."""
    text = CHECK_SH.read_text(encoding="utf-8")
    assert re.search(
        r"^uv run --frozen python3 tools/status_header_gate\.py\s*$", text, re.MULTILINE
    ), "check.sh no longer invokes the status-header gate"


def test_ci_runs_the_status_header_gate_and_proves_it_can_fail() -> None:
    """Its four siblings above assert the negative check by bare substring, which a comment
    quoting the same phrase would satisfy after the real `grep` line was deleted. Here the two
    halves of the negative check are matched as *commands* — a line whose first non-space
    character is not `#` — so a comment cannot stand in for either.
    """
    workflow = _workflow()
    job = re.search(r"^  status-header:\n(?P<body>(?:    .*\n|\n)*)", workflow, re.MULTILINE)
    assert job is not None, "ci.yml has no status-header job"
    body = job.group("body")
    assert re.search(r"^\s*[^#\s].*tools/status_header_gate\.py\s*$", body, re.MULTILINE), (
        "ci.yml no longer invokes the status-header gate"
    )
    assert re.search(r"^\s*[^#\s].*--expect-version 99\.99\.99", body, re.MULTILINE), (
        "the negative check is gone — nothing proves it gates"
    )
    assert re.search(
        r"^\s*[^#\s].*grep -q \"the header drifted from the release\"", body, re.MULTILINE
    ), "the negative check no longer requires the stated reason, so a crash would satisfy it"


def test_ci_compares_per_question_outcomes_across_two_operating_systems() -> None:
    """The half a single machine cannot answer (G1).

    The point of the job is that the two legs are *different architectures*. A matrix that quietly
    lost one of them would still be green, still upload an artifact, and prove nothing — so the two
    runner names are asserted here rather than left to the reader of the workflow.
    """
    workflow = _workflow()
    job = re.search(r"^  eval-cross-machine:\n(?P<body>(?:    .*\n|\n)*)", workflow, re.MULTILINE)
    assert job is not None, "ci.yml has no eval-cross-machine job"
    body = job.group("body")
    assert "ubuntu-latest" in body and "macos-latest" in body, (
        "the cross-machine comparison is down to one machine, which compares nothing"
    )
    assert "--record-outcomes" in body

    compare = re.search(
        r"^  eval-cross-machine-compare:\n(?P<body>(?:    .*\n|\n)*)", workflow, re.MULTILINE
    )
    assert compare is not None, "the two legs are recorded and never compared"
    assert "diff" in compare.group("body")
    assert "needs: eval-cross-machine" in compare.group("body")
