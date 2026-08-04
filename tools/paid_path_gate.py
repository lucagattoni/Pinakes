"""The paid-path allowlist gate — gates 1 and 2 of plans/20260727_1543-v0.2.md I7a, in one "
"implementation.

`CLAUDE.md` calls "the free path stays free" non-negotiable, and v0.1 promised a CI grep enforcing
it under a heading with no increment number, so nobody owned it and it never shipped
(docs/RETROSPECTIVES.md, 20260727 15:35). This is that gate, owned, with the list of exceptions in
one file — `.paid-path-allowlist` — that `check.sh`, `.github/workflows/ci.yml` and
`tests/test_paid_path.py` all read, so three copies cannot drift apart.

    gate 1  every path the allowlist names must exist, and must live under src/. A stale entry is a
            silent widening: the module it exempted was renamed, and the exemption stayed behind.
    gate 2  the paid-client import grep runs over src/ *excluding* the listed paths. Any hit fails.

**What gate 2 does not see, on purpose.** It matches `import X` / `from X import ...` statements —
the same shape the CI grep it replaces matched. A dynamic `__import__("anthropic")` is invisible to
it, and `src/pinakes/extract/__init__.py` contains exactly that: the registry imports a backend's
client lazily inside its factory so a missing extra reports the precise `uv add` line
(`extract/__init__.py:147-151`). That is not a hole to be plugged here. Exempting the registry from
gate 2 would exempt the file where a real static import is most likely to be added by accident, and
the registry's `__import__` only ever runs when a caller has explicitly *selected* `claude-vision`
— an allowlisted entry point. The dynamic direction is covered where it can actually be observed:
**gate 4** (`tests/test_paid_path.py::test_the_free_path_never_imports_the_paid_client`) runs the
whole free path in a fresh subprocess and asserts `anthropic` never lands in `sys.modules`,
which no import spelling can evade.

Stdlib only, and no import of `pinakes` itself: CI's `build` job runs this without installing the
project, and a gate that needed the package it guards could not run before the package builds.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ALLOWLIST_NAME = ".paid-path-allowlist"
SRC_DIRNAME = "src"

# The clients that cost money. Kept identical to the grep this replaced, plus the alternation the
# plan names (plans/20260727_1543-v0.2.md, I7a gate 2) — adding a provider here is a one-line
# change.
PAID_CLIENTS = ("anthropic", "openai", "cohere", "mistralai", r"google\.generativeai")

# `import anthropic`, `import anthropic.types`, `from anthropic import ...`, at any indentation.
# `\b` after the name is what stops `anthropic_version` or a module named `openai_shim` matching.
_IMPORT_RE = re.compile(
    rf"^[ \t]*(?:import|from)[ \t]+(?:{'|'.join(PAID_CLIENTS)})\b",
    re.MULTILINE,
)

FAILURE_MESSAGE = (
    "A paid-API client is imported in src/ outside the allowlist. "
    "CLAUDE.md: paid entry points are an enumerated allowlist; docs/DESIGN.md §1."
)


class GateFailureError(Exception):
    """A gate refused. Carries the operator-facing lines, never a traceback."""

    def __init__(self, *lines: str) -> None:
        super().__init__("\n".join(lines))
        self.lines: tuple[str, ...] = lines


def read_allowlist(root: Path) -> list[str]:
    """The allowlist's entries, in file order, as repo-relative POSIX strings.

    Comments and blank lines are dropped here rather than at each call site, so "the file is empty"
    and "the file is all comments" are the same thing to every gate — which is what I7a ships.
    """
    path = root / ALLOWLIST_NAME
    if not path.is_file():
        raise GateFailureError(
            f"{ALLOWLIST_NAME} is missing from {root}. The gate cannot run without it."
        )

    entries: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    return entries


def gate_1_listed_paths_exist(root: Path, entries: list[str]) -> set[Path]:
    """Every entry names a real file under src/. Returns the resolved exclusion set.

    Four separate failures, because they fail for different reasons and a single "bad entry"
    message would send the reader looking in the wrong place:
      - absolute or `..`-escaping: the entry is not repo-relative, so it excludes nothing
      - not under src/: gate 2 only ever walks src/, so such an entry is inert — it reads like an
        exemption and grants none, which is worse than being absent
      - a directory: gate 2's exclusion is exact path equality, so a directory exempts *nothing*
        while reading, to anyone scanning this file, like it exempts the whole tree. Rejected here
        rather than tolerated, because "list the package instead of the module" is the cheapest way
        someone would try to widen the allowlist, and it deserves an answer rather than silence
      - does not exist: the classic stale entry, left behind by a rename
    """
    excluded: set[Path] = set()
    problems: list[str] = []
    src_root = (root / SRC_DIRNAME).resolve()

    for entry in entries:
        candidate = Path(entry)
        if candidate.is_absolute() or ".." in candidate.parts:
            problems.append(f"  {entry} — must be a repo-relative path with no '..' segment")
            continue

        resolved = (root / candidate).resolve()
        if not resolved.is_relative_to(src_root):
            problems.append(
                f"  {entry} — must live under {SRC_DIRNAME}/, which is all gate 2 walks"
            )
            continue
        if resolved.is_dir():
            problems.append(
                f"  {entry} — names a directory; the allowlist exempts files, never a tree"
            )
            continue
        if not resolved.is_file():
            problems.append(f"  {entry} — listed in {ALLOWLIST_NAME} but does not exist")
            continue

        excluded.add(resolved)

    if problems:
        raise GateFailureError(
            f"{ALLOWLIST_NAME} has entries that do not name a real file:", *problems
        )
    return excluded


def gate_2_no_paid_import_outside_the_allowlist(root: Path, excluded: set[Path]) -> int:
    """Grep src/ for a paid-client import, skipping exactly the allowlisted files.

    The exclusion is **exact path equality**, never a prefix or substring match. An entry of
    `src/pinakes/extract/claude.py` implemented as `str(path).startswith(entry)` would also exempt
    `claude.py.bak` and `claude.py/`-shaped siblings, and a substring match would exempt a whole
    directory — neither of which gate 1 can see, since the listed path itself exists either way.
    `tests/test_paid_path.py::test_a_paid_import_outside_the_allowlist_fails_gate_2` is the test
    that holds this down.

    Returns the number of files scanned, so the caller can report a gate that silently walked
    nothing — an empty walk passes every assertion here for the wrong reason.
    """
    src_root = root / SRC_DIRNAME
    if not src_root.is_dir():
        raise GateFailureError(
            f"{SRC_DIRNAME}/ not found under {root}. The gate has nothing to scan."
        )

    hits: list[str] = []
    scanned = 0
    for path in sorted(src_root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.resolve() in excluded:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: no import statement can hide in it
        scanned += 1
        for match in _IMPORT_RE.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            line = text.splitlines()[line_number - 1].strip()
            hits.append(f"  {path.relative_to(root)}:{line_number}: {line}")

    if hits:
        raise GateFailureError(FAILURE_MESSAGE, *hits)
    return scanned


def run(root: Path) -> int:
    entries = read_allowlist(root)
    excluded = gate_1_listed_paths_exist(root, entries)
    scanned = gate_2_no_paid_import_outside_the_allowlist(root, excluded)
    print(
        f"paid-path allowlist: {len(entries)} exempt path(s), "
        f"{scanned} file(s) scanned under {SRC_DIRNAME}/, no paid-API import outside the allowlist"
    )
    return scanned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help=f"repository root holding {ALLOWLIST_NAME} and {SRC_DIRNAME}/ "
        "(default: this script's repo)",
    )
    args = parser.parse_args(argv)

    try:
        run(args.root.resolve())
    except GateFailureError as failure:
        for line in failure.lines:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
