"""Which files this branch touches that the default branch has touched too, since they diverged.

Several agents work in this repo at once, each in its own worktree. They collide in a small set of
shared, append-oriented documents — `CHANGELOG.md`, `docs/STATUS.md`, `docs/DESIGN.md` — and the
collision has two shapes, only one of which anybody notices:

    the loud one   `git merge` conflicts. Annoying, and self-announcing.
    the quiet one  `git merge` *succeeds*, because the two edits landed on different lines. Git
                   merged them because they did not overlap textually, never because they agree.
                   Two agents can state contradictory things in one file and every command reports
                   success.

The quiet one is why this is a gate rather than a note in a playbook. It cannot be caught by
resolving conflicts carefully, because there is no conflict to resolve — it is caught only by
knowing that somebody else edited the same file and going to read the result. This prints exactly
that list.

**It reports; it does not adjudicate.** Whether two edits to `docs/STATUS.md` contradict each other
is a question about meaning, and nothing here can answer it. The gate's whole job is to make sure
the question gets asked.

**No network by default.** It compares against the `origin/<default>` ref already in this clone and
says how old that ref is, so `check.sh` stays fast and works on a plane. `--fetch` refreshes it
first, which is what the pre-merge check does — comparing against a week-old ref would report
"no overlap" with total confidence and no information.

Exit status is 0 on overlap unless `--strict`: during development the answer is "go look at that
file", not "stop working". Before merging it is a gate, and `--strict` is how `check.sh` and the
landing checklist ask for that.

Stdlib only, and it imports nothing from this project — the same constraint
`tools/paid_path_gate.py` carries, so it can run before the package builds.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime

#: Files where a quiet merge is most likely to produce a contradiction rather than a conflict:
#: every agent appends to them, and they make *claims* rather than holding code. Called out by name
#: in the report so the ones that matter are not lost in a list of thirty test files.
HIGH_CONTENTION = (
    "CHANGELOG.md",
    "docs/STATUS.md",
    "docs/DESIGN.md",
    "docs/RETROSPECTIVES.md",
    "CLAUDE.md",
    "README.md",
)


class GitError(Exception):
    """A git command failed, or this is not a usable clone. Reported, never raised at the user."""


def git(*args: str) -> str:
    """Trailing newlines only — **never** `.strip()`.

    `git status --porcelain` encodes the status in the first two columns, so ` M CHANGELOG.md`
    begins with a significant space. Stripping the whole output ate it, and the first modified file
    in every listing parsed one character short: `HANGELOG.md`, which matches nothing, so the gate
    reported "no overlap" with total confidence. Callers wanting a single token strip it themselves.
    """
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout.rstrip("\n")


def default_ref() -> str:
    """The upstream default branch, asked of the remote rather than assumed to be `main`."""
    try:
        # e.g. "refs/remotes/origin/main" -> "origin/main"
        head = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD").strip()
        return head.removeprefix("refs/remotes/")
    except GitError:
        for candidate in ("origin/main", "origin/master"):
            try:
                git("rev-parse", "--verify", "--quiet", candidate)
            except GitError:
                continue
            return candidate
        raise GitError("no origin/HEAD, origin/main or origin/master in this clone") from None


def ref_age(ref: str) -> str:
    """How stale the comparison is, in the report's own words — an unfetched ref is the one way
    this gate can be confidently wrong."""
    try:
        committed = int(git("log", "-1", "--format=%ct", ref).strip())
    except (GitError, ValueError):
        return "age unknown"
    delta = datetime.now(UTC) - datetime.fromtimestamp(committed, tz=UTC)
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"tip is {int(delta.total_seconds() / 60)} min old"
    if hours < 48:
        return f"tip is {hours:.0f} h old"
    return f"tip is {hours / 24:.0f} days old"


def changed_files(from_ref: str, to_ref: str) -> set[str]:
    out = git("diff", "--name-only", f"{from_ref}...{to_ref}")
    return {line for line in out.splitlines() if line}


def working_tree_files() -> set[str]:
    """Uncommitted work counts. The collision this gate exists for is usually found *while*
    editing, not after committing — a report that ignored the working tree would arrive too late
    to be worth having."""
    out = git("status", "--porcelain")
    files: set[str] = set()
    for line in out.splitlines():
        if not line:
            continue
        path = line[3:]
        # Renames arrive as "old -> new"; both sides can collide, so both are reported.
        if " -> " in path:
            old, new = path.split(" -> ", 1)
            files.update({old.strip('"'), new.strip('"')})
        else:
            files.add(path.strip('"'))
    return files


def report(overlap: set[str], base: str, ref: str, age: str) -> None:
    ranked = sorted(overlap, key=lambda p: (p not in HIGH_CONTENTION, p))
    print()
    print("!" * 78)
    print(f"  {len(ranked)} file(s) changed BOTH here and on {ref} since {base[:9]} ({age})")
    print("!" * 78)
    for path in ranked:
        mark = "  <-- shared doc" if path in HIGH_CONTENTION else ""
        print(f"    {path}{mark}")
    print()
    print("  A clean auto-merge is not a correct merge: git merges edits that do not overlap")
    print("  textually, never edits that agree. Rebase onto the current default branch, re-run")
    print("  the gate on the new base, and READ these files' merged state before landing.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fetch", action="store_true", help="refresh the remote ref first (network)"
    )
    parser.add_argument("--strict", action="store_true", help="exit non-zero when there is overlap")
    parser.add_argument("--ref", default=None, help="compare against this ref (default: detected)")
    args = parser.parse_args()

    try:
        ref = args.ref or default_ref()
        if args.fetch:
            remote = ref.split("/", 1)[0]
            git("fetch", "--quiet", remote)
        base = git("merge-base", "HEAD", ref).strip()
        theirs = changed_files(base, ref)
        mine = changed_files(base, "HEAD") | working_tree_files()
    except GitError as exc:
        # Never fatal: a shallow clone, a detached CI checkout or no network must not fail a build
        # over an advisory check. Silence would be worse than the check being unavailable.
        print(f"shared-file overlap: skipped — {exc}", file=sys.stderr)
        return 0

    overlap = mine & theirs
    if not overlap:
        print(f"shared-file overlap: none against {ref} ({ref_age(ref)}).")
        return 0

    report(overlap, base, ref, ref_age(ref))
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
