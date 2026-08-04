"""`tools/land.py`, driven as a subprocess — one test per branch.

A subprocess rather than an import, for the reason `tests/test_status_header_gate.py` gives: it
exercises the same artifact a human runs, argument parsing included, with no `sys.path` surgery.

The assertion that matters is **not** "landing works". It is that landing *refuses* when the default
branch did not move — the silent failure the script exists for. A branch merged into itself prints
"Already up to date", the push prints "Everything up-to-date", and nothing landed. A suite that only
exercised the happy path would pass with the guard deleted, which is this project's recurring defect
class: an assertion satisfied by something other than the property it names. So every failing branch
asserts the **stated reason**, not merely a non-zero exit.
"""

import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).parent.parent / "tools" / "land.py"


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def land(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args], cwd=cwd, capture_output=True, text=True, check=False
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A primary checkout on `main`, with a real `origin` it can push to."""
    origin = tmp_path / "origin.git"
    git("init", "--bare", "--initial-branch=main", str(origin), cwd=tmp_path)

    root = tmp_path / "checkout"
    git("clone", str(origin), str(root), cwd=tmp_path)
    git("config", "user.email", "test@example.invalid", cwd=root)
    git("config", "user.name", "Test", cwd=root)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "-m", "base", cwd=root)
    git("push", "-u", "origin", "main", cwd=root)
    return root


def make_branch(root: Path, name: str) -> Path:
    """A feature branch with one commit, in its own linked worktree — the real shape."""
    worktree = root.parent / name
    git("worktree", "add", "-q", "-b", name, str(worktree), "main", cwd=root)
    (worktree / f"{name}.md").write_text("work\n", encoding="utf-8")
    git("add", "-A", cwd=worktree)
    git("commit", "-m", f"add {name}", cwd=worktree)
    return worktree


def test_landing_moves_the_default_branch_and_pushes(repo: Path) -> None:
    make_branch(repo, "feature")
    before = git("rev-parse", "main", cwd=repo)

    result = land("feature", cwd=repo)

    assert result.returncode == 0, result.stderr
    after = git("rev-parse", "main", cwd=repo)
    assert after != before
    assert git("rev-parse", "origin/main", cwd=repo) == after, (
        "push not verified against the remote"
    )
    assert (repo / "feature.md").exists(), "the branch's content is not on the default branch"


def test_refuses_when_the_default_branch_did_not_move(repo: Path) -> None:
    """The whole point. An already-merged branch is refused, not reported as landed."""
    make_branch(repo, "feature")
    assert land("feature", cwd=repo).returncode == 0
    landed = git("rev-parse", "main", cwd=repo)

    result = land("feature", cwd=repo)

    assert result.returncode == 1
    assert "did not move" in result.stderr, result.stderr
    assert "landed nothing" in result.stderr, "the reason must name what actually happened"
    assert git("rev-parse", "main", cwd=repo) == landed, "a refused landing must change nothing"


def test_merges_in_the_primary_checkout_even_when_invoked_from_the_feature_worktree(
    repo: Path,
) -> None:
    """The mistake this replaces: `cd <worktree> && git merge` merges the branch into itself."""
    worktree = make_branch(repo, "feature")
    before = git("rev-parse", "main", cwd=repo)

    result = land("feature", cwd=worktree)

    assert result.returncode == 0, result.stderr
    assert git("rev-parse", "main", cwd=repo) != before, "landed nothing from inside the worktree"
    assert git("rev-parse", "origin/main", cwd=repo) == git("rev-parse", "main", cwd=repo)


def test_refuses_to_merge_the_default_branch_into_itself(repo: Path) -> None:
    result = land("main", cwd=repo)
    assert result.returncode == 1
    assert "into itself" in result.stderr, result.stderr


def test_refuses_an_unknown_branch(repo: Path) -> None:
    result = land("never-existed", cwd=repo)
    assert result.returncode == 1
    assert "no local branch" in result.stderr, result.stderr


def test_refuses_a_dirty_primary_checkout(repo: Path) -> None:
    """Landing on top of uncommitted work would silently fold it into the merge."""
    make_branch(repo, "feature")
    (repo / "README.md").write_text("edited but not committed\n", encoding="utf-8")

    result = land("feature", cwd=repo)

    assert result.returncode == 1
    assert "uncommitted changes" in result.stderr, result.stderr
    assert git("rev-parse", "main", cwd=repo) == git("rev-parse", "origin/main", cwd=repo)


def test_cleanup_removes_the_worktree_and_both_copies_of_the_branch(repo: Path) -> None:
    """Deleting one copy leaves the branch there for the next `git branch -a`."""
    worktree = make_branch(repo, "feature")
    git("push", "-u", "origin", "feature", cwd=worktree)

    result = land("feature", "--cleanup", cwd=repo)

    assert result.returncode == 0, result.stderr
    assert not worktree.exists(), "worktree survived"
    assert "feature" not in git("branch", cwd=repo), "local ref survived"
    assert not git("ls-remote", "--heads", "origin", "feature", cwd=repo), "remote ref survived"


def test_cleanup_does_not_run_when_the_landing_was_refused(repo: Path) -> None:
    """Nothing is destroyed on a path that landed nothing."""
    worktree = make_branch(repo, "feature")
    assert land("feature", cwd=repo).returncode == 0

    result = land("feature", "--cleanup", cwd=repo)

    assert result.returncode == 1
    assert worktree.exists(), "a refused landing destroyed the worktree"
    assert "feature" in git("branch", cwd=repo), "a refused landing deleted the branch"
