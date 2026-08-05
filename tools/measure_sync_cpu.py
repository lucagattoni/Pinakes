"""How many cores a long-running command actually keeps busy — the number
`plans/20260731_1202-open-corrections.md` item 6 requires before anything about `sync.py`'s
per-document embedding loop may change ("nothing else in this item may be built before that
number exists").

**Why a subprocess sampler, not something wired into `sync.py` itself.** The question is not "is
this code single-threaded" — it plainly is, one `backend.embed()` call per document — but "does
that matter", and that depends on whether `fastembed`'s ONNX Runtime or `sentence-transformers`'
torch is already saturating the machine *underneath* the loop. Only an external, black-box CPU
sample answers that; instrumenting the loop would only ever show the loop's own single thread.

**macOS `ps -o %cpu` is per core, not per machine.** A process using every thread of one core
reports ~100%; seven cores busy reports ~700%. `CpuTrace.cores()` divides by 100 to turn a sampled
percentage into "how many cores", which is the only unit item 6's write-up asks for.

**The whole process tree is sampled, never just the launched pid — and that is the difference
between a right answer and a confident wrong one.** The invocation this tool exists for wraps the
real work in a launcher: `-- uv run pnk sync ...` makes `uv` the measured process and `pnk` its
*child*, and `uv` itself burns nothing. Measured 20260805 on this repo, one identical one-core busy
loop: **1.0 cores** when launched directly, **0.0 cores** through `uv run`. A tool answering "how
many cores does sync keep busy" with `0.0` because it watched the launcher would not read as broken
— it would read as a finding. So `sample_percent` sums `%cpu` across the root pid and every
descendant, from a single `ps` snapshot.

**`%cpu` is a decaying average over up to a minute of previous real time** (`man ps`), not an
instantaneous reading. For the multi-minute, steady-state embedding loop this tool is pointed at,
that is what you want. It does mean `peak` is the peak of a *smoothed* series: a burst shorter than
the decay window is averaged away rather than reported, so a low peak is weaker evidence of an idle
machine than a high peak is of a busy one.

**Not a CI gate.** Nothing in `check.sh` calls this — it is an operator tool, run by hand against
a real `pnk sync`, on a real corpus, because the number it exists to produce is meaningless on a
fixture too small to saturate anything. Its own test exercises the sampling and reporting logic
against synthetic CPU-bound child processes instead — direct *and* behind a launcher — so it stays
fast, needs no model weights, and proves the *sampler* correct independently of any sync run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass, field


@dataclass
class CpuTrace:
    """One measured run: wall-clock seconds, every `%cpu` sample taken while it ran, and how it
    exited. Empty `samples_percent` means the command exited before the first poll — reported, not
    hidden, since a wall-clock so short the sampler never got a reading is itself informative.
    """

    wall_seconds: float
    samples_percent: list[float] = field(default_factory=list[float])
    exit_code: int = 0

    @property
    def peak_percent(self) -> float:
        return max(self.samples_percent, default=0.0)

    @property
    def mean_percent(self) -> float:
        if not self.samples_percent:
            return 0.0
        return sum(self.samples_percent) / len(self.samples_percent)

    @staticmethod
    def cores(percent: float) -> float:
        """macOS `ps -o %cpu` is per core: 100% is one core busy, 750% is seven (item 6)."""
        return percent / 100.0


def _process_table() -> dict[int, tuple[int, float]]:
    """Every visible process as `pid -> (ppid, %cpu)`, from one `ps` snapshot.

    One snapshot rather than a `ps` call per pid: the tree must be summed from a *single* moment,
    or a child that starts or exits mid-walk is counted twice or not at all.
    """
    result = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,%cpu="], capture_output=True, text=True)
    table: dict[int, tuple[int, float]] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 3:  # a command name with spaces cannot appear — no `comm` is requested
            continue
        try:
            table[int(fields[0])] = (int(fields[1]), float(fields[2]))
        except ValueError:  # pragma: no cover — a malformed row is skipped, never fatal
            continue
    return table


def sample_percent(pid: int) -> float | None:
    """Aggregate `%cpu` across `pid` **and every descendant**, or `None` once `pid` has exited.

    Summing the tree rather than the one pid is the point: the measured command is normally a
    launcher (`uv run pnk sync ...`), whose own CPU is ~0 while its child does all the work. See
    the module docstring for the measurement that establishes it.

    `None` means the root pid is no longer in the process table — it ended between the caller's
    `wait()` timing out and this call, which is a race, not an error. Descendants that outlive
    their parent are re-parented away from it and cannot be attributed to it, so they are lost
    either way; a command whose work outlives the process this tool waits on is outside what a
    wall-clock-bounded sampler can measure at all.
    """
    table = _process_table()
    if pid not in table:
        return None
    children: dict[int, list[int]] = {}
    for child, (parent, _) in table.items():
        children.setdefault(parent, []).append(child)

    total = 0.0
    seen: set[int] = set()
    frontier = [pid]
    while frontier:  # breadth-first with `seen`, so a pid cycle cannot loop forever
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        total += table[current][1]
        frontier.extend(kid for kid in children.get(current, []) if kid not in seen)
    return total


def measure(command: list[str], *, interval: float) -> CpuTrace:
    """Run `command` to completion, sampling its `%cpu` every `interval` seconds.

    Samples first, *then* waits up to `interval` for exit (`Popen.wait(timeout=...)`) rather than
    sleeping the full interval unconditionally — a `sleep(interval)` between polls would keep the
    reported wall-clock (and every real sync waited on by this tool) padded by up to one whole
    interval past the command's actual exit, which matters at the coarse intervals a multi-minute
    sync is reasonably polled at.
    """
    if interval <= 0:
        raise ValueError(f"interval must be positive, got {interval!r}")
    start = time.monotonic()
    process = subprocess.Popen(command)
    samples: list[float] = []
    try:
        while True:
            percent = sample_percent(process.pid)
            if percent is not None:
                samples.append(percent)
            try:
                exit_code = process.wait(timeout=interval)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:  # pragma: no cover — only on an exception path above
            exit_code = process.wait()
    wall = time.monotonic() - start
    return CpuTrace(wall_seconds=wall, samples_percent=samples, exit_code=exit_code)


def report(trace: CpuTrace) -> str:
    peak_cores = CpuTrace.cores(trace.peak_percent)
    mean_cores = CpuTrace.cores(trace.mean_percent)
    return (
        f"wall-clock: {trace.wall_seconds:.1f}s\n"
        f"samples: {len(trace.samples_percent)}\n"
        f"peak: {trace.peak_percent:.0f}% cpu  ({peak_cores:.1f} cores)\n"
        f"mean: {trace.mean_percent:.0f}% cpu  ({mean_cores:.1f} cores)\n"
        f"exit code: {trace.exit_code}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="measure_sync_cpu", description=__doc__)
    parser.add_argument("--interval", type=float, default=0.5, help="poll interval, in seconds")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="the command to run and measure, e.g. -- uv run pnk sync --kb my-kb --rebuild",
    )
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("no command given — usage: measure_sync_cpu.py [--interval S] -- <cmd> ...")

    trace = measure(command, interval=args.interval)
    print(report(trace))
    return trace.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
