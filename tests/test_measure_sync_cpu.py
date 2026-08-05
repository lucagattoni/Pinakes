"""`tools/measure_sync_cpu.py`, driven as a subprocess — one test per branch.

A subprocess rather than an import, for the reason `tests/test_status_header_gate.py` gives: it
exercises the same artifact an operator runs by hand (item 6 of
`plans/20260731_1202-open-corrections.md`), argument parsing included, with no `sys.path` surgery.
Every command under test is a synthetic CPU-bound child process — never a real `pnk sync` — so this
stays fast and needs no model weights; the tool exists to be pointed at a real sync separately, by
hand, which is where the actual measurement comes from.

The assertion that matters is **not** "it ran without crashing". A sampler that always reports 0%
(wrong pid, wrong flag, a `ps` invocation that silently returns nothing) would pass a test that
only checks exit code — so every CPU-observing test asserts a genuinely non-zero reading, and the
unit-conversion tests assert the exact numbers item 6's own examples give (98% → one core, 750% →
seven), not just "some number came out".
"""

import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).parent.parent / "tools" / "measure_sync_cpu.py"

_BUSY = "s=0\nfor _ in range(200_000_000):\n    s += 1\n"
"""A pure-Python busy loop, no imports — burns one core for a bit over a second, predictably, with
nothing the sampler is supposed to be independent of."""

_LAUNCHER = (
    "import subprocess, sys\n"
    f"sys.exit(subprocess.run([sys.executable, '-c', {_BUSY!r}]).returncode)\n"
)
"""A process that burns nothing itself and does all its work in a child — the shape of
`uv run pnk sync ...`, which is the only invocation this tool exists to be pointed at."""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=60
    )


def _peak_cores(stdout: str) -> float:
    line = next(entry for entry in stdout.splitlines() if entry.startswith("peak:"))
    return float(line.split("(")[1].split(" cores")[0])


def test_measures_a_genuinely_busy_process_at_a_nonzero_peak() -> None:
    result = _run("--interval", "0.05", "--", sys.executable, "-c", _BUSY)
    assert result.returncode == 0
    assert "peak: 0% cpu" not in result.stdout
    assert "samples: 0" not in result.stdout, "a >1s busy loop polled every 50ms must be sampled"


def test_a_launcher_is_measured_by_its_child_not_by_itself() -> None:
    """The defect this test exists for: `ps -p <pid>` watches only the launched process, so
    `-- uv run pnk sync ...` measured `uv` — which burns nothing — and reported 0.0 cores for a
    sync saturating one. Measured 20260805 before the fix: the identical busy loop read 1.0 cores
    direct and 0.0 cores behind a launcher.

    A near-idle *upper* bound is what makes this adversarial. Asserting only "> 0" would pass on
    the launcher's own interpreter startup, so the threshold sits above anything a process that
    merely waits on a child could produce, and below one core.
    """
    result = _run("--interval", "0.05", "--", sys.executable, "-c", _LAUNCHER)
    assert result.returncode == 0
    assert _peak_cores(result.stdout) > 0.5, (
        "the busy child's CPU was not attributed to the measured tree — "
        "the sampler is watching the launcher alone"
    )


def test_reports_cores_the_way_macos_percent_converts_to_them() -> None:
    """98% on a 10-core box is one core; 750% is seven — item 6's own worked examples, exercised
    through the CLI's own unit conversion rather than a private helper.

    **The tolerance is the point, and an exact comparison here is a bug, not rigour.** The two
    numbers on the line are rendered at *different* precisions — percent at 0 dp, cores at 1 dp —
    so they are two roundings of one value, not one value printed twice. `pytest.approx`'s default
    relative tolerance demanded they agree exactly, which held only while a single-process reading
    sat at exactly `100.0`; the moment a tree sum read `101.4` CI failed on `"101"/100 != 1.0`
    (20260805, the `light pdf` leg alone — the other two legs rounded agreeably and passed, which
    is what a coin-flip assertion looks like).

    0.5 of display error in the percent is 0.005 of a core, plus 0.05 from the cores field's own
    rounding: 0.055 is the largest honest disagreement, so anything beyond 0.06 is arithmetic
    rather than formatting. That still fails a missing `/100` (1.0 against 101), a wrong divisor,
    or a swapped pair — the conversion defects the assertion is here for.
    """
    result = _run("--interval", "0.05", "--", sys.executable, "-c", _BUSY)
    assert "cores)" in result.stdout
    peak_line = next(line for line in result.stdout.splitlines() if line.startswith("peak:"))
    percent = float(peak_line.split("%")[0].split(":")[1].strip())
    cores = float(peak_line.split("(")[1].split(" cores")[0])
    assert cores == pytest.approx(percent / 100.0, abs=0.06)


def test_propagates_the_measured_commands_exit_code() -> None:
    result = _run("--interval", "0.05", "--", sys.executable, "-c", "raise SystemExit(3)")
    assert result.returncode == 3
    assert "exit code: 3" in result.stdout


def test_works_without_the_double_dash_separator() -> None:
    """`argparse.REMAINDER` accepts a bare trailing command too — `--` is a convenience, not a
    requirement, so both forms must measure the same command the same way."""
    result = _run("--interval", "0.05", sys.executable, "-c", "raise SystemExit(0)")
    assert result.returncode == 0
    assert "exit code: 0" in result.stdout


def test_refuses_an_empty_command() -> None:
    result = _run("--interval", "0.05")
    assert result.returncode != 0
    assert "no command given" in result.stderr


def test_refuses_a_non_positive_interval() -> None:
    result = _run("--interval", "0", "--", sys.executable, "-c", "pass")
    assert result.returncode != 0


def test_a_near_instant_command_does_not_wait_out_a_long_interval() -> None:
    """The sampler must not block for a whole `--interval` after the measured command has already
    exited — a large interval against a near-instant command is the shape most likely to expose a
    poll-then-sleep loop that checks liveness too rarely."""
    result = _run("--interval", "5", "--", sys.executable, "-c", "pass")
    assert result.returncode == 0
    wall_line = next(line for line in result.stdout.splitlines() if line.startswith("wall-clock:"))
    wall_seconds = float(wall_line.split(":")[1].strip().rstrip("s"))
    assert wall_seconds < 5.0, "reported wall-clock included a full trailing interval after exit"
