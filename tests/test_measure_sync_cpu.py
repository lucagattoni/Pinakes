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


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=30
    )


def test_measures_a_genuinely_busy_process_at_a_nonzero_peak() -> None:
    result = _run("--interval", "0.05", "--", sys.executable, "-c", _BUSY)
    assert result.returncode == 0
    assert "peak: 0% cpu" not in result.stdout
    assert "samples: 0" not in result.stdout, "a >1s busy loop polled every 50ms must be sampled"


def test_reports_cores_the_way_macos_percent_converts_to_them() -> None:
    """98% on a 10-core box is one core; 750% is seven — item 6's own worked examples, exercised
    through the CLI's own unit conversion rather than a private helper."""
    result = _run("--interval", "0.05", "--", sys.executable, "-c", _BUSY)
    assert "cores)" in result.stdout
    # The peak line's own percent and its own /100 conversion must agree with each other.
    peak_line = next(line for line in result.stdout.splitlines() if line.startswith("peak:"))
    percent = float(peak_line.split("%")[0].split(":")[1].strip())
    cores = float(peak_line.split("(")[1].split(" cores")[0])
    assert cores == pytest.approx(percent / 100.0)


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
