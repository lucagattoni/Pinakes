"""The shared-file overlap gate, driven by real diverging git histories.

Built with actual `git` calls in a temp directory rather than by mocking `subprocess`: the gate is
almost entirely a claim *about git's behaviour* — what `diff A...B` means, what `merge-base` picks,
how a rename is spelled in `status --porcelain` — and a mock would assert my belief about each of
those rather than the behaviour. The one bug this gate cannot afford is reporting "no overlap"
when there is one, and that bug lives precisely in those beliefs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

GATE = Path(__file__).parent.parent / "tools" / "shared_file_overlap.py"


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def run_gate(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), *args], cwd=repo, capture_output=True, text=True
    )


@pytest.fixture
def diverged(tmp_path: Path) -> Path:
    """An `origin` and a clone whose branch and whose `origin/main` have both moved since the fork.

    `--bare` for the origin so it can be pushed to, and the clone's `origin/main` is refreshed by an
    explicit fetch — which is the state a real worktree is in after another agent lands.
    """
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "--bare", "--initial-branch=main")

    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "--initial-branch=main")
    git(seed, "config", "user.email", "t@example.com")
    git(seed, "config", "user.name", "T")
    # Deliberately long: the quiet-merge case needs the two agents' edits far enough apart that
    # git's 3-line context windows do not touch, which is exactly the real file's shape.
    filler = "\n".join(f"- an older entry, line {n}" for n in range(40))
    (seed / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [Unreleased]\n\n{filler}\n", encoding="utf-8"
    )
    (seed / "untouched.txt").write_text("stable\n", encoding="utf-8")
    git(seed, "add", "-A")
    git(seed, "commit", "-m", "seed")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-q", "origin", "main")

    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "T")

    # Another agent lands on main, editing CHANGELOG.md and a file this branch never sees.
    theirs = (
        (seed / "CHANGELOG.md")
        .read_text(encoding="utf-8")
        .replace("## [Unreleased]\n", "## [Unreleased]\n\n- their entry, at the top\n", 1)
    )
    (seed / "CHANGELOG.md").write_text(theirs, encoding="utf-8")
    (seed / "theirs-only.txt").write_text("theirs\n", encoding="utf-8")
    git(seed, "add", "-A")
    git(seed, "commit", "-m", "their work")
    git(seed, "push", "-q", "origin", "main")

    git(work, "checkout", "-q", "-b", "feature")
    git(work, "fetch", "-q", "origin")
    return work


def test_it_names_a_file_both_sides_committed(diverged: Path) -> None:
    (diverged / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n- my entry\n", encoding="utf-8"
    )
    git(diverged, "add", "-A")
    git(diverged, "commit", "-m", "my work")

    result = run_gate(diverged)
    assert "CHANGELOG.md" in result.stdout
    assert "shared doc" in result.stdout, "a high-contention file must be marked as one"
    assert result.returncode == 0, "advisory by default"


def test_uncommitted_work_counts(diverged: Path) -> None:
    """The collision is usually found while editing. A report that waited for a commit would
    arrive after the work it was meant to redirect."""
    (diverged / "CHANGELOG.md").write_text("# Changelog\n\n- uncommitted\n", encoding="utf-8")

    result = run_gate(diverged)
    assert "CHANGELOG.md" in result.stdout


def test_strict_turns_overlap_into_a_failure(diverged: Path) -> None:
    (diverged / "CHANGELOG.md").write_text("# Changelog\n\n- mine\n", encoding="utf-8")

    assert run_gate(diverged).returncode == 0
    assert run_gate(diverged, "--strict").returncode == 1


def test_a_file_only_one_side_touched_is_not_overlap(diverged: Path) -> None:
    """The gate's value is that its output is short enough to read. A file only this branch
    changed, or only they changed, is not a collision and must not be listed."""
    (diverged / "mine-only.txt").write_text("mine\n", encoding="utf-8")

    result = run_gate(diverged)
    assert "none against" in result.stdout
    assert "mine-only.txt" not in result.stdout
    assert "theirs-only.txt" not in result.stdout, "a file only they touched is not a collision"


def test_an_edit_they_made_elsewhere_in_the_same_file_still_counts(diverged: Path) -> None:
    """The quiet failure this gate exists for: two edits far apart in one file, which git merges
    without a conflict and without either being read against the other."""
    text = (diverged / "CHANGELOG.md").read_text(encoding="utf-8")
    (diverged / "CHANGELOG.md").write_text(text + "\n## [0.1.0]\n\n- far below\n", encoding="utf-8")
    git(diverged, "add", "-A")
    git(diverged, "commit", "-m", "my entry, far from theirs")

    assert "CHANGELOG.md" in run_gate(diverged).stdout

    # The half that makes this test worth having: git merges the two edits with no conflict at all,
    # so nothing but the gate would ever have told anyone the file had two authors this round.
    merged = subprocess.run(
        ["git", "merge", "--no-commit", "--no-ff", "origin/main"],
        cwd=diverged,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "merge", "--abort"], cwd=diverged, capture_output=True)
    assert merged.returncode == 0, "this fixture must merge cleanly, or it tests the loud case"


def test_it_is_never_fatal_outside_a_usable_clone(tmp_path: Path) -> None:
    """A shallow CI checkout or a directory with no remote must not fail a build over an advisory
    check — but it must say it was skipped, because a silent skip reads exactly like a pass."""
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    git(lonely, "init", "--initial-branch=main")

    result = run_gate(lonely, "--strict")
    assert result.returncode == 0
    assert "skipped" in result.stderr


def test_the_report_says_how_stale_its_comparison_is(diverged: Path) -> None:
    """Without the age, "no overlap" against a week-old ref reads identically to "no overlap"
    against a current one — the one way this gate can be confidently wrong."""
    result = run_gate(diverged)
    assert "old" in result.stdout or "min" in result.stdout
