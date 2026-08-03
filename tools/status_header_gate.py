"""`docs/STATUS.md`'s header names the released version — a gate, not a checklist item.

**Why a gate at all.** The header — line 3, `**Latest release: x.y.z**` — drifted from
`pinakes.__version__` for four consecutive releases (0.5.0 → 0.7.1) while the same release sweeps
updated every table below it, in the file whose own preamble says it is the only place in the repo
that says what is built — and this repo is public. A written checklist missed it four times
running, which is this project's own threshold for turning the item into a gate: the same reason
`changelog.d/`, `retro.d/` and `nul-scan` exist (plans/open-corrections.md, 20260803).

**The invariant holds with no exception window.** On `main`, `__version__` *is* the latest
release: the release commit bumps `__version__` (`docs/RELEASING.md` step 2) and its sweep table
puts the header bump in that same commit; between releases neither moves. So this gate never goes
red on a correct tree, and a red run means the tree is wrong, not the gate.

**Only the version is gated — never the `last reviewed` date beside it.** A wall-clock staleness
check fails on a quiet weekend with no code change; decided at `prices-toml-parses` (`check.sh`),
where staleness is a runtime concern rather than a build gate. The same reasoning, not re-decided.

**The shape and the position are gated as well as the value.** The header must sit on line 3 —
the line `docs/RELEASING.md`'s sweep table names, the first line a reader sees — and must start
with exactly `**Latest release: x.y.z**`. A gate that scanned the whole file for the pattern
would stay green while a stale header sat where every reader looks, and a gate that accepted any
shape could be silenced by reformatting the line. Not found, or not that shape → fail.

`--status-file` and `--expect-version` exist for the unit tests and for CI's negative check
("the gate can still fail"); with neither, it checks the real file against the real version.
"""

import argparse
import re
import sys
from pathlib import Path

from pinakes import __version__

REPO = Path(__file__).resolve().parent.parent
STATUS = REPO / "docs" / "STATUS.md"

HEADER_LINE = 3
"""1-based, matching what `docs/RELEASING.md`'s sweep table and every editor display."""

SHAPE = re.compile(r"^\*\*Latest release: (\d+\.\d+\.\d+)\*\*")
"""Anchored at the start of the line. What follows the closing `**` — the `last reviewed` date —
is deliberately unconstrained, because it is deliberately ungated."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="status_header_gate", description=__doc__)
    parser.add_argument(
        "--status-file",
        type=Path,
        default=STATUS,
        help="the file to check (default: the real docs/STATUS.md; tests point this at a copy)",
    )
    parser.add_argument(
        "--expect-version",
        default=__version__,
        help="the version the header must name (default: pinakes.__version__)",
    )
    args = parser.parse_args(argv)
    status_file: Path = args.status_file
    expected: str = args.expect_version

    lines = status_file.read_text(encoding="utf-8").splitlines()
    if len(lines) < HEADER_LINE:
        print(
            f"status-header: {status_file} has fewer than {HEADER_LINE} lines — "
            f"the '**Latest release: x.y.z**' header is gone",
            file=sys.stderr,
        )
        return 1

    line = lines[HEADER_LINE - 1]
    match = SHAPE.match(line)
    if match is None:
        print(
            f"status-header: {status_file} line {HEADER_LINE} does not start with "
            f"'**Latest release: x.y.z**' — found {line!r}. Deleting or reformatting "
            f"the header does not silence this gate; restore the line",
            file=sys.stderr,
        )
        return 1

    stated = match.group(1)
    if stated != expected:
        print(
            f"status-header: {status_file} line {HEADER_LINE} says the latest release is "
            f"{stated}, but pinakes.__version__ is {expected} — the header drifted from the "
            f"release. Bump it in the release commit (docs/RELEASING.md, sweep table)",
            file=sys.stderr,
        )
        return 1

    print(
        f"status-header: {status_file.name} line {HEADER_LINE} and "
        f"pinakes.__version__ agree on {stated}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
