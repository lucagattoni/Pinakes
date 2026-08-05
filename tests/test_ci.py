"""`pnk init --ci` — the workflow §6.3 designed in v0.1 and I6b finally writes."""

from pathlib import Path

import pytest

from pinakes.ci import WORKFLOW, WORKFLOW_PATH, write_workflow
from pinakes.cli import EXIT_FAILURE, EXIT_OK, main
from pinakes.errors import InitError
from pinakes.hooks import FREE_BACKEND_FLAG
from pinakes.init import init


def test_init_without_ci_writes_no_workflow(tmp_path: Path) -> None:
    result = init(tmp_path / "kb", now="20260728 12:00")
    assert result.workflow is None
    assert not (result.root / WORKFLOW_PATH).exists()


def test_init_ci_writes_the_workflow_and_reports_it(tmp_path: Path) -> None:
    result = init(tmp_path / "kb", now="20260728 12:00", ci=True)
    assert result.workflow == result.root / WORKFLOW_PATH
    assert result.workflow in result.created
    assert result.workflow.is_file()


def test_the_workflow_forces_the_free_backend(tmp_path: Path) -> None:
    """CI is the most non-interactive caller there is: no terminal to answer a confirmation from,
    and no CI job in this project ever holds an API key."""
    result = init(tmp_path / "kb", now="20260728 12:00", ci=True)
    body = result.workflow.read_text(encoding="utf-8") if result.workflow else ""
    assert f"pnk sync {FREE_BACKEND_FLAG}" in body
    assert "must never spend" in body


def test_the_workflow_and_the_hooks_cannot_disagree() -> None:
    """One constant, two writers. Two literals would be two places for the forced backend to
    drift, and the drift would be invisible until a CI run spent money."""
    assert WORKFLOW.count(FREE_BACKEND_FLAG) >= 1
    assert "--extract=claude-vision" not in WORKFLOW


def test_the_workflow_caches_the_state_directory_that_holds_the_ledger(tmp_path: Path) -> None:
    result = init(tmp_path / "kb", now="20260728 12:00", ci=True)
    body = result.workflow.read_text(encoding="utf-8") if result.workflow else ""
    assert "path: .pinakes" in body


def test_an_existing_workflow_is_never_overwritten(tmp_path: Path) -> None:
    """The same trust rule `install-hooks` applies to a foreign git hook: it may be hand-edited,
    so it is refused rather than clobbered."""
    root = tmp_path / "kb"
    target = root / WORKFLOW_PATH
    target.parent.mkdir(parents=True)
    target.write_text("# mine\n", encoding="utf-8")

    with pytest.raises(InitError) as exc_info:
        write_workflow(root)
    assert "never overwritten" in exc_info.value.remedy
    assert target.read_text(encoding="utf-8") == "# mine\n"


def test_the_cli_flag_is_wired_and_says_what_it_did(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["init", str(tmp_path / "kb"), "--ci"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "workflow:" in out
    assert FREE_BACKEND_FLAG in out
    assert (tmp_path / "kb" / WORKFLOW_PATH).is_file()


def test_init_ci_refuses_a_directory_that_already_holds_the_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`init` refuses an existing workflow; this asserts the *reported* failure rather than a
    traceback, which is the only difference a user sees.

    It used to be refused as "not empty" — incidentally, by a blanket emptiness check that has
    since been removed so a directory with content can be adopted (20260805). The refusal now
    names the workflow itself, which is both more precise and the only thing actually in the way.
    """
    root = tmp_path / "kb"
    (root / WORKFLOW_PATH).parent.mkdir(parents=True)
    (root / WORKFLOW_PATH).write_text("# mine\n", encoding="utf-8")

    assert main(["init", str(root), "--ci"]) == EXIT_FAILURE
    assert "already exists" in capsys.readouterr().err


def test_the_generated_workflow_is_valid_yaml(tmp_path: Path) -> None:
    """The interpolated cache key carries literal `${{ }}`, which is exactly the shape an f-string
    breaks. Parsing it is how that stays true."""
    import yaml

    result = init(tmp_path / "kb", now="20260728 12:00", ci=True)
    assert result.workflow is not None
    parsed = yaml.safe_load(result.workflow.read_text(encoding="utf-8"))
    steps = parsed["jobs"]["sync"]["steps"]
    cache = next(step for step in steps if step.get("uses", "").startswith("actions/cache"))
    assert "${{ runner.os }}" in cache["with"]["key"]
    assert "${{ hashFiles(" in cache["with"]["key"]
    assert cache["with"]["path"] == ".pinakes"


def test_the_init_line_describes_the_workflow_not_the_hooks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One notice, two writers. Printing "hooks run …" beneath a line announcing a workflow
    describes a different file from the one just written."""
    assert main(["init", str(tmp_path / "kb"), "--ci"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "workflow:" in out
    assert "hooks" not in out
