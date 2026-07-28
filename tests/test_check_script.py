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
