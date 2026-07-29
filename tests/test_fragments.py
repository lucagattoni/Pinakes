"""The fragment assembler, driven as a subprocess against a temp tree.

A subprocess rather than an import, for the reason `tests/test_paid_path.py` gives about
`tools/paid_path_gate.py`: it exercises **the same artifact** the release procedure and `check.sh`
run, argument parsing included, and it needs no `sys.path` surgery the type checkers then cannot
resolve. `--repo` exists so this can point the real tool at a temp directory.

The failure that matters is not a crash — it is `--apply` silently corrupting `CHANGELOG.md`, found
at release time with the fragments it consumed already deleted. Most assertions here are therefore
about what splicing must leave *untouched*.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).parent.parent / "tools" / "fragments.py"

CHANGELOG_BEFORE = (
    "# Changelog\n\n"
    "## [Unreleased]\n\n"
    "- a pre-existing entry nobody migrated\n\n"
    "## [0.1.0] - 20260101 09:00\n\n"
    "- older\n"
)

RETRO_BEFORE = (
    "# Retrospectives\n\n"
    "## I1 - first (20260725 13:40)\n\n"
    "body\n\n"
    "## Design review passes 1-7 (pre-implementation)\n\n"
    "footer\n"
)


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "--repo", str(repo), *args],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "retro.d").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG_BEFORE, encoding="utf-8")
    (tmp_path / "docs" / "RETROSPECTIVES.md").write_text(RETRO_BEFORE, encoding="utf-8")
    return tmp_path


def write(repo: Path, rel: str, body: str) -> None:
    (repo / rel).write_text(body, encoding="utf-8")


def changelog(repo: Path) -> str:
    return (repo / "CHANGELOG.md").read_text(encoding="utf-8")


def test_a_category_comes_from_the_filename_and_groups_the_body(repo: Path) -> None:
    write(repo, "changelog.d/added-one.md", "- **A new thing.**")
    write(repo, "changelog.d/fixed-two.md", "- **A fixed thing.**")
    write(repo, "changelog.d/added-three.md", "- **Another new thing.**")

    out = run(repo, "--stream", "changelog", "--render").stdout

    assert "### Added" in out and "### Fixed" in out
    assert out.index("### Added") < out.index("### Fixed"), (
        "categories follow the stream's declared order, not the filesystem's"
    )
    added = out[out.index("### Added") : out.index("### Fixed")]
    assert "A new thing." in added and "Another new thing." in added


def test_an_unknown_category_is_refused_by_name(repo: Path) -> None:
    write(repo, "changelog.d/improved-something.md", "- **No such category.**")

    result = run(repo, "--check")

    assert result.returncode == 1
    assert "improved-something.md" in result.stderr
    assert "added" in result.stderr, "the message must name the vocabulary it expected"


def test_an_empty_fragment_is_refused(repo: Path) -> None:
    """An empty fragment renders an empty bullet and reads as a tooling bug at release time, when
    the fragment that would have explained it has already been deleted."""
    write(repo, "changelog.d/added-nothing.md", "   \n\n")

    result = run(repo, "--check")

    assert result.returncode == 1
    assert "is empty" in result.stderr


def test_check_reports_every_problem_not_just_the_first(repo: Path) -> None:
    write(repo, "changelog.d/improved-a.md", "- x")
    write(repo, "changelog.d/added-b.md", "")

    assert "2 malformed" in run(repo, "--check").stderr


def test_apply_leaves_existing_unreleased_prose_exactly_where_it_was(repo: Path) -> None:
    """Adoption must not require migrating what is already in `[Unreleased]` — a migration commit
    would itself collide with whatever the other agents are holding."""
    write(repo, "changelog.d/added-one.md", "- **A new thing.**")

    assert run(repo, "--stream", "changelog", "--apply").returncode == 0

    after = changelog(repo)
    assert "- a pre-existing entry nobody migrated" in after
    assert "## [0.1.0] - 20260101 09:00" in after
    assert "- older" in after
    assert after.index("### Added") < after.index("- a pre-existing entry"), (
        "fragments splice directly under the anchor, above what was already there"
    )
    assert CHANGELOG_BEFORE.count("## [") == after.count("## ["), (
        "no release heading gained or lost"
    )


def test_apply_deletes_the_fragments_it_consumed(repo: Path) -> None:
    """Consumed, not copied: leaving them behind would re-splice the same entry into the next
    release as well."""
    write(repo, "changelog.d/added-one.md", "- **A new thing.**")

    run(repo, "--stream", "changelog", "--apply")

    assert list((repo / "changelog.d").glob("*.md")) == []
    assert "A new thing." in changelog(repo)


def test_a_missing_anchor_is_an_error_rather_than_a_silent_append(repo: Path) -> None:
    """Appending to the end of a changelog whose anchor was renamed would bury the entry under
    every historical release, where nobody would look for it."""
    write(repo, "CHANGELOG.md", "# Changelog\n\n## [0.1.0]\n")
    write(repo, "changelog.d/added-one.md", "- **A new thing.**")

    result = run(repo, "--stream", "changelog", "--apply")

    assert result.returncode != 0
    assert "anchor" in (result.stderr + result.stdout)


def test_nothing_to_apply_is_not_an_error(repo: Path) -> None:
    result = run(repo, "--apply")

    assert result.returncode == 0
    assert changelog(repo) == CHANGELOG_BEFORE, "an empty run must not touch the document at all"


def test_the_readme_is_not_treated_as_a_fragment(repo: Path) -> None:
    """Each fragment directory documents itself in place, where somebody about to add a fragment
    will actually see it."""
    write(repo, "changelog.d/README.md", "# Changelog fragments\n\nnot an entry")

    assert run(repo, "--check").returncode == 0
    assert changelog(repo) == CHANGELOG_BEFORE


def test_the_retrospectives_stream_splices_above_its_footer(repo: Path) -> None:
    """`docs/RETROSPECTIVES.md` ends with the pre-implementation design-review passes, which must
    stay last — so this stream inserts *before* an anchor rather than after one."""
    write(repo, "retro.d/i7d-recorded.md", "## I7d - Recording (20260729 03:36)\n\n**HIGH - x.**\n")

    assert run(repo, "--stream", "retrospectives", "--apply").returncode == 0

    after = (repo / "docs" / "RETROSPECTIVES.md").read_text(encoding="utf-8")
    assert after.index("## I7d") > after.index("## I1")
    assert after.index("## I7d") < after.index("## Design review passes"), (
        "the design-review footer must stay at the foot"
    )


def test_a_free_form_stream_needs_no_category_prefix(repo: Path) -> None:
    write(repo, "retro.d/i7d-recorded.md", "## I7d - Recording\n\nbody\n")

    assert run(repo, "--check").returncode == 0
    assert "## I7d" in run(repo, "--stream", "retrospectives", "--render").stdout


def test_both_streams_apply_in_one_run(repo: Path) -> None:
    """The release procedure runs this once, with no `--stream`. If the default silently did one
    document, a release would ship with its retrospectives still sitting in `retro.d/`."""
    write(repo, "changelog.d/added-one.md", "- **A new thing.**")
    write(repo, "retro.d/i7d-recorded.md", "## I7d - Recording\n\nbody\n")

    assert run(repo, "--apply").returncode == 0

    assert "A new thing." in changelog(repo)
    assert "## I7d" in (repo / "docs" / "RETROSPECTIVES.md").read_text(encoding="utf-8")
    assert list((repo / "changelog.d").glob("*.md")) == []
    assert list((repo / "retro.d").glob("*.md")) == []
