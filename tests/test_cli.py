"""CLI contract: the surface is complete, the behaviour is honest, exit codes mean something."""

import argparse
import re
from pathlib import Path

import pytest

from pinakes import __version__
from pinakes.cli import COMMANDS, EXIT_FAILURE, EXIT_OK, EXIT_USAGE, main
from pinakes.errors import NotImplementedYetError, PinakesError

# docs/DESIGN.md §8's v0.1 command list. Hard-coded rather than derived from COMMANDS: a test that
# reads the same source it checks would pass even if a command were dropped.
DESIGN_V01_COMMANDS = frozenset({"init", "sync", "search", "doctor", "install-hooks", "serve"})


def test_version_is_set() -> None:
    # Asserts the *shape*, not a literal: pinning the exact string made every release edit a test
    # for no functional reason, and the release workflow already refuses a tag that disagrees with
    # __version__. What still matters is that the 0.0.0 development placeholder never ships.
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__
    assert __version__ != "0.0.0"


def test_surface_matches_the_design() -> None:
    assert {command.name for command in COMMANDS} == DESIGN_V01_COMMANDS


def test_bare_invocation_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == EXIT_OK
    out = capsys.readouterr().out
    assert "portable, agent-first knowledge base" in out
    for name in DESIGN_V01_COMMANDS:
        assert name in out


IMPLEMENTED = frozenset({"sync", "init", "search", "doctor", "install-hooks", "serve"})


@pytest.mark.parametrize("command", sorted(DESIGN_V01_COMMANDS - IMPLEMENTED))
def test_unimplemented_commands_fail_loudly_rather_than_pretending(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unimplemented command must exit non-zero — silence would imply it worked."""
    assert main([command]) == EXIT_FAILURE
    err = capsys.readouterr().err
    assert "not implemented yet" in err
    assert "plans/v0.1.md" in err  # the remedy, not just the complaint


def test_unknown_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["definitely-not-a-command"])
    assert exc_info.value.code == EXIT_USAGE


def test_version_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == EXIT_OK
    assert __version__ in capsys.readouterr().out


def test_every_unimplemented_command_names_the_increment_that_will_land_it() -> None:
    for command in COMMANDS:
        if command.name in IMPLEMENTED:
            continue
        with pytest.raises(NotImplementedYetError) as exc_info:
            command.run(argparse.Namespace())
        assert exc_info.value.increment == command.increment


def test_dispatch_target_is_hidden_from_the_option_namespace() -> None:
    """The runner must not sit on a name a future command could take as its own option."""
    from pinakes.cli import RUNNER_DEST, build_parser

    assert RUNNER_DEST.startswith("_")
    namespace = vars(build_parser().parse_args(["sync"]))
    assert RUNNER_DEST in namespace
    public_callables = [
        name for name in namespace if not name.startswith("_") and callable(namespace[name])
    ]
    assert not public_callables


def test_errors_survive_pickling() -> None:
    """Exceptions cross process boundaries (xdist, multiprocessing) and must rebuild intact."""
    import pickle

    restored = pickle.loads(pickle.dumps(PinakesError("broke", remedy="fix it")))
    assert restored.message == "broke"
    assert restored.remedy == "fix it"

    original = NotImplementedYetError("sync", increment="I8b")
    restored_subclass = pickle.loads(pickle.dumps(original))
    assert restored_subclass.message == original.message
    assert restored_subclass.remedy == original.remedy
    # The subclass survives: an error caught by type on the far side of a process boundary must
    # still be that type.
    assert type(restored_subclass) is NotImplementedYetError


def test_errors_carry_a_remedy() -> None:
    error = PinakesError("something broke", remedy="try this instead")
    assert error.message == "something broke"
    assert error.remedy == "try this instead"
    assert str(error) == "something broke"


def test_unknown_extract_flag_is_rejected(
    kb_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rejected before anything is imported — even a KB with zero documents still refuses."""
    assert main(["sync", "--kb", str(kb_root), "--extract", "telepathy"]) == EXIT_FAILURE
    assert "telepathy" in capsys.readouterr().err
