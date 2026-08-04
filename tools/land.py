"""Land a feature branch on the default branch — from the primary checkout, always.

**Why this exists.** Running `git merge <branch>` from inside that branch's own worktree merges the
branch into itself: git reports *"Already up to date"*, the push reports *"Everything up-to-date"*,
and a tag created there points off the default branch. **Three successful commands and nothing
landed.** It has happened repeatedly in this repository, always the same way — a single `&&` chain
that begins `cd <worktree>` and later contains `git merge`.

**Git cannot catch this on its own.** A branch merged into itself creates no commit, so
`pre-merge-commit` never fires. The no-op is silent by design. So the guard has to be here:

* this script finds the **primary checkout itself** and merges there, whatever directory it was
  invoked from — the wrong-directory mistake becomes unreachable rather than remembered;
* it records the default branch's sha before the merge and **fails loudly if it did not move**,
  which is the assertion the silent no-op would otherwise slip past;
* it re-reads `origin/<default>` after pushing, because a push reporting success is a claim.

It does not remove the need to *choose* to run it. That is the one remaining human step, and it is
one thing to remember rather than a rule to apply in the middle of a command chain.

    python3 tools/land.py <branch>              # merge, verify, push
    python3 tools/land.py <branch> --cleanup    # also remove the worktree and both branch copies
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_BRANCH = "main"


class LandingError(Exception):
    """A refusal with a remedy. Never raised for a condition the script could fix itself."""


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    """Run a git command and return its stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise LandingError(
            f"`git {' '.join(args)}` failed ({result.returncode}):\n{result.stderr.strip()}"
        )
    return result.stdout.strip()


def primary_checkout() -> Path:
    """The main working tree, which is always the first entry `git worktree list` prints.

    Linked worktrees follow it. Reading this rather than trusting the caller's cwd is the whole
    point of the script: it is what makes merging from inside a feature worktree impossible.
    """
    first = git("worktree", "list", "--porcelain").splitlines()
    if not first or not first[0].startswith("worktree "):
        raise LandingError("could not read `git worktree list --porcelain`")
    return Path(first[0][len("worktree ") :])


def ensure_landable(root: Path, branch: str) -> None:
    """Refuse anything that would land nothing, or land it somewhere unexpected."""
    if branch == DEFAULT_BRANCH:
        raise LandingError(
            f"refusing to merge {DEFAULT_BRANCH!r} into itself — pass the feature branch instead."
        )
    if not git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", cwd=root, check=False):
        raise LandingError(f"no local branch {branch!r}. `git branch -a` to see what exists.")

    current = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    if current != DEFAULT_BRANCH:
        raise LandingError(
            f"the primary checkout is on {current!r}, not {DEFAULT_BRANCH!r}. "
            f"Switch it before landing: `git -C {root} switch {DEFAULT_BRANCH}`."
        )
    dirty = git("status", "--porcelain", cwd=root)
    if dirty:
        raise LandingError(
            f"the primary checkout has uncommitted changes:\n{dirty}\n"
            "Landing would merge on top of them. Commit or stash first."
        )


def land(branch: str, *, cleanup: bool) -> None:
    root = primary_checkout()
    ensure_landable(root, branch)
    print(f"landing {branch} → {DEFAULT_BRANCH} in {root}")

    git("fetch", "--quiet", "origin", cwd=root)
    before = git("rev-parse", DEFAULT_BRANCH, cwd=root)
    git("merge", "--no-ff", "--quiet", branch, "-m", f"Merge branch '{branch}'", cwd=root)
    after = git("rev-parse", DEFAULT_BRANCH, cwd=root)

    # The assertion this script exists for. A branch merged into itself lands here reporting
    # success, having done nothing at all.
    if after == before:
        raise LandingError(
            f"{DEFAULT_BRANCH} did not move ({before[:7]}). The merge reported success and landed "
            f"nothing — {branch!r} was most likely already merged, or is an ancestor of "
            f"{DEFAULT_BRANCH}. Nothing was pushed."
        )
    print(f"  merged: {before[:7]} → {after[:7]}")

    git("push", "--quiet", "origin", DEFAULT_BRANCH, cwd=root)
    remote = git("rev-parse", f"origin/{DEFAULT_BRANCH}", cwd=root)
    if remote != after:
        raise LandingError(
            f"push reported success but origin/{DEFAULT_BRANCH} is {remote[:7]}, not {after[:7]}. "
            "Nothing was cleaned up; investigate before retrying."
        )
    print(f"  pushed: origin/{DEFAULT_BRANCH} at {remote[:7]}")

    if cleanup:
        remove_branch_everywhere(root, branch)
    else:
        print(
            f"  worktree and branch kept. `python3 tools/land.py {branch} --cleanup` removes them."
        )


def remove_branch_everywhere(root: Path, branch: str) -> None:
    """Remove the worktree, the local ref and the remote ref — deleting only one leaves it there.

    Safe only because `land` has already verified the default branch moved and the push took: the
    content is on the remote before anything is destroyed.
    """
    for line in git("worktree", "list", "--porcelain", cwd=root).split("\n\n"):
        if f"branch refs/heads/{branch}" in line:
            path = line.splitlines()[0][len("worktree ") :]
            git("worktree", "remove", path, cwd=root)
            print(f"  worktree removed: {path}")
    git("worktree", "prune", cwd=root)

    git("branch", "-D", branch, cwd=root)
    print(f"  local branch deleted: {branch}")

    if git("ls-remote", "--heads", "origin", branch, cwd=root):
        git("push", "origin", "--delete", branch, cwd=root)
        print(f"  remote branch deleted: origin/{branch}")
    git("remote", "prune", "origin", cwd=root)

    if git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", cwd=root, check=False):
        raise LandingError(f"local branch {branch!r} survived deletion")
    if git("ls-remote", "--heads", "origin", branch, cwd=root):
        raise LandingError(f"remote branch {branch!r} survived deletion")
    print("  verified gone: worktree, local ref, remote ref")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Merge a feature branch into {DEFAULT_BRANCH} from the primary checkout.",
    )
    _ = parser.add_argument("branch", help="the feature branch to land")
    _ = parser.add_argument(
        "--cleanup",
        action="store_true",
        help="after a verified push, remove the worktree and both copies of the branch",
    )
    args = parser.parse_args()
    branch: str = args.branch
    cleanup: bool = args.cleanup

    try:
        land(branch, cleanup=cleanup)
    except LandingError as exc:
        print(f"land: {exc}", file=sys.stderr)
        return 1
    print("landed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
