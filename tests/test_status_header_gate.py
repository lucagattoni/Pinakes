"""`tools/status_header_gate.py`, driven as a subprocess — one test per branch.

A subprocess rather than an import, for the reason `tests/test_fragments.py` gives: it exercises
the same artifact `check.sh` and CI run, argument parsing included, with no `sys.path` surgery.
`--status-file` exists so a mutated header is only ever written to a temp copy, never to the real
`docs/STATUS.md`; `--expect-version` exists so the disagreeing branch needs no fake package.

The recurring defect these tests exist to catch is a gate that reads the file and never compares
— which would pass any test that only checks exit 0. So every failing branch asserts the *stated
reason*, and the disagreeing branch asserts **both** values appear in it: a message naming only
one version is compatible with comparing that version to itself.
"""

import subprocess
import sys
from pathlib import Path

from pinakes import __version__

TOOL = Path(__file__).parent.parent / "tools" / "status_header_gate.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args], capture_output=True, text=True, check=False
    )


def test_the_real_status_file_agrees_with_the_real_version() -> None:
    """The invariant itself, with no flags: on a correct tree the gate is green. This is the run
    `check.sh` performs, and it holds between releases because a release bumps `__version__` and
    the header in the same commit (docs/RELEASING.md step 2 + sweep table)."""
    result = run()
    assert result.returncode == 0, result.stderr
    assert f"agree on {__version__}" in result.stdout


def test_agreeing_versions_pass(tmp_path: Path) -> None:
    copy = tmp_path / "STATUS.md"
    copy.write_text("# Status\n\n**Latest release: 1.2.3** · last reviewed 20260803 22:23\n")
    result = run("--status-file", str(copy), "--expect-version", "1.2.3")
    assert result.returncode == 0, result.stderr
    assert "agree on 1.2.3" in result.stdout


def test_disagreeing_versions_fail_naming_both(tmp_path: Path) -> None:
    copy = tmp_path / "STATUS.md"
    copy.write_text("# Status\n\n**Latest release: 1.2.3** · last reviewed 20260803 22:23\n")
    result = run("--status-file", str(copy), "--expect-version", "9.9.9")
    assert result.returncode == 1
    assert "1.2.3" in result.stderr, "the failure must name the version the header states"
    assert "9.9.9" in result.stderr, "the failure must name the version the package states"
    assert "STATUS.md" in result.stderr, "the failure must name the file to fix"


def test_a_missing_line_fails(tmp_path: Path) -> None:
    """A file too short to have a line 3 at all — the header was deleted, not reworded."""
    copy = tmp_path / "STATUS.md"
    copy.write_text("# Status\n")
    result = run("--status-file", str(copy), "--expect-version", "1.2.3")
    assert result.returncode == 1
    assert "header is gone" in result.stderr


def test_a_reformatted_line_fails(tmp_path: Path) -> None:
    """The right version in the wrong shape — bold stripped, wording changed — must fail too:
    the parse is anchored to the exact shape precisely so reformatting cannot silence the gate."""
    copy = tmp_path / "STATUS.md"
    copy.write_text("# Status\n\nLatest release: 1.2.3 · last reviewed 20260803 22:23\n")
    result = run("--status-file", str(copy), "--expect-version", "1.2.3")
    assert result.returncode == 1
    assert "does not start with" in result.stderr


def test_the_header_on_the_wrong_line_fails(tmp_path: Path) -> None:
    """The exact header, one line lower than docs/RELEASING.md's sweep table names. A gate that
    scanned the whole file would pass this file — and would equally pass a stale line 3 with the
    current version buried further down, which is the drift this gate exists to stop."""
    copy = tmp_path / "STATUS.md"
    copy.write_text("# Status\n\n\n**Latest release: 1.2.3** · last reviewed 20260803 22:23\n")
    result = run("--status-file", str(copy), "--expect-version", "1.2.3")
    assert result.returncode == 1
    assert "does not start with" in result.stderr
