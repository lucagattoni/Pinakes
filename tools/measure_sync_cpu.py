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

**Not a CI gate.** Nothing in `check.sh` calls this — it is an operator tool, run by hand against
a real `pnk sync`, on a real corpus, because the number it exists to produce is meaningless on a
fixture too small to saturate anything. Its own test exercises the sampling and reporting logic
against a synthetic CPU-bound child process instead, so it stays fast, needs no model weights, and
proves the *sampler* correct independently of any particular sync run.
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


def sample_percent(pid: int) -> float | None:
    """This process's current aggregate `%cpu` across every thread, or `None` once it has exited.

    `ps -p <pid>` prints nothing (empty stdout, exit code 1) for a pid that is no longer running —
    the process ended between the caller's `poll()` and this call, which is a race, not an error.
    """
    result = subprocess.run(
        ["ps", "-o", "%cpu=", "-p", str(pid)],
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    if not output:
        return None
    return float(output.splitlines()[0])


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
