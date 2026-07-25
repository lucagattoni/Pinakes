"""Bootstrap tests: the package imports and the entry point behaves honestly."""

import pytest

from pinakes import __version__
from pinakes.cli import COMMANDS, main


def test_version_is_set() -> None:
    assert __version__ == "0.0.0"


def test_bare_invocation_prints_help_and_succeeds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["pnk"])
    assert main() == 0
    assert "portable, agent-first knowledge base" in capsys.readouterr().out


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_planned_commands_fail_loudly_rather_than_pretending(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unimplemented command must exit non-zero — silence would imply it worked."""
    monkeypatch.setattr("sys.argv", ["pnk", command])
    assert main() == 1
    assert "not implemented yet" in capsys.readouterr().err
