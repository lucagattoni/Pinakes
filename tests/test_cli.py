"""CLI contract: the surface is complete, the behaviour is honest, exit codes mean something."""

import argparse
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from pinakes import __version__
from pinakes.cli import COMMANDS, EXIT_FAILURE, EXIT_OK, EXIT_USAGE, main
from pinakes.errors import NotImplementedYetError, PinakesError
from pinakes.manifest import Manifest

# docs/DESIGN.md §8's command list, by the release that introduced each. Hard-coded rather than
# derived from COMMANDS: a test that reads the same source it checks would pass even if a command
# were dropped.
DESIGN_V01_COMMANDS = frozenset({"init", "sync", "search", "doctor", "install-hooks", "serve"})
# `budget` lands in I6b (v0.2); `links` in L4 and `link` in L6 (the links release); `upgrade` in T3
# (the template release), declared by docs/DESIGN.md §6.1 rather than §8.
# `templates` in T7, on the same footing as `upgrade`: its declaration is docs/CLI.md's row, added
# when decision O-1 accepted the surface (20260804 10:30) and **before** the command existed, so
# that the repository never held a command with no prior decision record.
DESIGN_COMMANDS = DESIGN_V01_COMMANDS | frozenset(
    {"budget", "links", "link", "upgrade", "templates"}
)


def test_version_is_set() -> None:
    # Asserts the *shape*, not a literal: pinning the exact string made every release edit a test
    # for no functional reason, and the release workflow already refuses a tag that disagrees with
    # __version__. What still matters is that the 0.0.0 development placeholder never ships.
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__
    assert __version__ != "0.0.0"


def test_surface_matches_the_design() -> None:
    assert {command.name for command in COMMANDS} == DESIGN_COMMANDS


def test_bare_invocation_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == EXIT_OK
    out = capsys.readouterr().out
    assert "portable, agent-first knowledge base" in out
    for name in DESIGN_COMMANDS:
        assert name in out


IMPLEMENTED = frozenset(
    {
        "sync",
        "init",
        "search",
        "doctor",
        "install-hooks",
        "serve",
        "budget",
        "links",
        "link",
        "upgrade",
        # T7. Deliberately **not** added to `DESIGN_COMMANDS` above: that set is docs/DESIGN.md
        # §8's list, hard-coded so a dropped command fails loudly, and §8 does not name this one —
        # `pnk templates` was decided by O-1 of the template release plan and is carried by
        # docs/CLI.md. Adding it here says it is built; adding it there would claim §8 says so.
        "templates",
    }
)


@pytest.mark.parametrize("command", sorted(DESIGN_COMMANDS - IMPLEMENTED))
def test_unimplemented_commands_fail_loudly_rather_than_pretending(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unimplemented command must exit non-zero — silence would imply it worked."""
    assert main([command]) == EXIT_FAILURE
    err = capsys.readouterr().err
    assert "not implemented yet" in err
    assert "plans/20260725_1317-v0.1.md" in err  # the remedy, not just the complaint


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


def test_no_help_text_carries_markdown_emphasis(capsys: pytest.CaptureFixture[str]) -> None:
    """`--help` renders in a terminal, where `**bold**` reaches the user as literal asterisks.

    Checked against the *rendered* output — the artefact a user sees — rather than argparse's
    internals. Backticks are deliberately allowed: `[extraction] backend` reads fine in a terminal
    and is the convention this CLI already uses, so flagging them would be a style crusade over
    pre-existing text rather than a defect.
    """
    for command in DESIGN_COMMANDS:
        with pytest.raises(SystemExit):
            main([command, "--help"])
        rendered = capsys.readouterr().out
        assert "**" not in rendered, f"`pnk {command} --help` shows literal asterisks"


def test_every_sync_flag_documents_its_scope(capsys: pytest.CaptureFixture[str]) -> None:
    """`pnk sync` is the only command that can spend money or destroy derived state, so a flag
    whose reach nobody wrote down grows one (plans/20260727_1543-v0.2.md, I7c).

    Read out of the `--help` a user actually sees, not out of the parser's internals: the promise
    is about what `pnk sync --help` tells someone, so that is the text asserted against.
    """
    with pytest.raises(SystemExit) as exit_info:
        main(["sync", "--help"])
    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out

    # Each of these states a *limit*, not only a capability. The words are the flag's own; a
    # rewrite that drops the limit fails here rather than shipping a wider flag than it documents.
    must_bound = {
        "--force": ("never widens", "exactly two"),
        "--yes": ("Raises no cap", "does not"),
        "--clear-cache": ("never the ledger",),
        "--estimate-only": ("generates nothing",),
    }
    flat = " ".join(help_text.split())
    for flag, phrases in must_bound.items():
        assert flag in flat, f"{flag} is gone from `pnk sync --help`; this list must change with it"
        for phrase in phrases:
            assert phrase in flat, (
                f"`pnk sync {flag}` no longer states its limit in --help: expected {phrase!r}"
            )


def test_progress_printer_throttles_shows_a_rate_and_always_shows_the_last_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Item 6: a multi-hour, silent `pnk sync` is what makes "working" and "hung" indistinguishable
    — `cli._progress_printer` is the TTY-side half of the fix. Throttled to about once a second so
    a fast sync does not spend more time printing than syncing, but the first and the final call
    (`done == total`) are never throttled away: the first proves the run started, the last must
    both show and end the line so nothing else prints on top of it.
    """
    from pinakes.cli import _progress_printer  # pyright: ignore[reportPrivateUsage]

    # One value consumed by `_progress_printer()` itself (`start`), then one per `progress()` call.
    clock = iter([0.0, 0.0, 0.3, 1.2, 2.5])
    monkeypatch.setattr("time.monotonic", lambda: next(clock))
    progress, finish = _progress_printer()

    progress(1, 4)  # t=0.0: first call, always shown
    progress(2, 4)  # t=0.3: <1s since last shown, suppressed
    progress(3, 4)  # t=1.2: >=1s since last shown, shown
    progress(4, 4)  # t=2.5: done == total, always shown, ends the line
    finish()  # a no-op here — `progress` already closed the line itself

    out = capsys.readouterr().out
    assert "1/4" in out and "3/4" in out and "4/4" in out
    assert "2/4" not in out, "the throttled call must not print at all"
    assert out.count("\r") == 3, "one overwrite per line actually shown"
    assert out.endswith("\n"), "the final call must end the line, not leave the cursor mid-line"
    assert out.count("\n") == 1, (
        "finish() must not print a second newline onto an already-closed line"
    )


def test_progress_printer_finish_closes_a_line_an_early_stop_left_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An adversarial review of this increment found the gap this test pins: a `[budget]` cap (or
    any early exit from `_run`'s loop, `sync.py`) stops before `done == total` ever fires, leaving
    the cursor mid-line — a printed `\\r`, no trailing newline — for whatever prints next (the sync
    report, an error) to land on top of. `run_sync` (`cli.py`) calls `finish()` unconditionally, in
    a `finally`, specifically to close that line before anything else reaches stdout.
    """
    from pinakes.cli import _progress_printer  # pyright: ignore[reportPrivateUsage]

    clock = iter([0.0, 0.0])
    monkeypatch.setattr("time.monotonic", lambda: next(clock))
    progress, finish = _progress_printer()

    progress(2, 5)  # done < total: the run stopped early, the line is left open
    left_open = capsys.readouterr().out
    assert not left_open.endswith("\n"), "an unfinished call must not end the line itself"

    finish()
    assert capsys.readouterr().out == "\n", "finish() closes the open line with exactly one newline"

    finish()  # idempotent — nothing left open, so a second call prints nothing
    assert capsys.readouterr().out == ""


def test_run_sync_wires_progress_only_for_a_quiet_free_tty(
    monkeypatch: pytest.MonkeyPatch, kb_root: Path
) -> None:
    """`-q` prints only problems (`print_sync_report`'s own rule) and a git hook can still inherit
    a real tty, so both gates must apply to progress, not just the tty check — otherwise `pnk sync
    --quiet` from a hook run interactively would print progress lines `-q` promises to suppress."""
    import pinakes.cli as cli_module
    from pinakes.sync import SyncOptions, SyncReport

    captured: dict[str, object] = {}

    def fake_sync(loaded: Manifest, *, options: SyncOptions) -> SyncReport:
        del loaded
        captured["progress"] = options.progress
        return SyncReport()

    monkeypatch.setattr("pinakes.sync.sync", fake_sync)

    for isatty, quiet, expect_progress in (
        (True, False, True),
        (True, True, False),
        (False, False, False),
        (False, True, False),
    ):
        captured.clear()
        monkeypatch.setattr(cli_module.sys.stdout, "isatty", lambda v=isatty: v)
        args = ["sync", "--kb", str(kb_root)]
        if quiet:
            args.append("--quiet")
        cli_module.main(args)
        has_progress = captured.get("progress") is not None
        assert has_progress is expect_progress, (isatty, quiet, expect_progress)


def test_pnk_templates_lists_notes_with_its_version(capsys: pytest.CaptureFixture[str]) -> None:
    """The listing exists because the information was reachable only by getting something wrong.

    Before T7, `template.available()` was called from one place: the error raised when
    `pnk init --template` names something that does not exist. Asserted against the *shipped*
    template rather than a synthetic one, because what a user needs the command to prove is that
    this build can stamp `notes` — a synthetic fixture would prove the formatting and nothing else.
    """
    from pinakes.template import describe

    assert main(["templates"]) == EXIT_OK
    out = capsys.readouterr().out

    installed = describe("notes")
    assert "notes" in out
    # The version, not merely the name: a listing that omits it cannot answer "which one am I on",
    # which is half of why the command was accepted.
    assert installed.version in out
    assert installed.description in out


def test_pnk_templates_json_matches_the_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    """Two renderings of one answer, so neither can drift into being the honest one on its own."""
    import json

    assert main(["templates", "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)

    assert main(["templates"]) == EXIT_OK
    human = capsys.readouterr().out

    assert payload, "`--json` listed no templates at all"
    for row in payload:
        assert set(row) == {"name", "version", "reference", "description"}
        # `reference` is emitted rather than left to be reassembled — assert it agrees with the
        # parts, or a consumer joining them itself would be a second definition of the format.
        assert row["reference"] == f"{row['name']}@{row['version']}"
        assert row["name"] in human
        assert row["version"] in human
    assert len(payload) == len([line for line in human.splitlines() if line.strip()])


def test_pnk_templates_takes_no_kb_flag() -> None:
    """It lists what this *build* installed, which does not vary by KB.

    Pinned because the omission looks like an oversight beside every other command here, and the
    obvious "fix" would make the answer look KB-dependent when it is not.
    """
    from pinakes.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["templates", "--kb", "."])


def test_pnk_templates_reports_a_damaged_template_without_hiding_the_good_ones(
    synthetic_template: Callable[..., str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One unreadable template must not cost the user the answer about every other one.

    Two separable properties, and the one asserted here belongs to *this command*: a listing that
    aborts on the first bad directory reports nothing about the good ones. The general defect —
    `template.describe` raising a bare `OSError` on a damaged install, which reached `init`,
    `doctor` and `upgrade` too — was open when this test was written and is closed by
    open-corrections item 3. **That closure changed the exception this command catches and not one
    assertion below**, which is the evidence the two properties really were separable.
    """
    from pinakes import template as template_module

    good = synthetic_template("good", versions={"1.0": "[kb]\n"}, current="1.0")
    root = template_module._root(good)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(root, Path)
    # A sibling directory with no `template.toml` at all — the shape a half-finished install leaves.
    (root.parent / "broken").mkdir()

    assert main(["templates"]) == EXIT_FAILURE
    out = capsys.readouterr().out

    assert "good" in out, "a damaged sibling hid a template that reads perfectly"
    assert "broken" in out
    assert "unreadable" in out
    assert "reinstall" in out
    assert "Traceback" not in out


def test_pnk_templates_json_reports_the_damaged_one_too(
    synthetic_template: Callable[..., str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--json` carries the same finding.

    A consumer must not be able to read a silently short list as a healthy one.
    """
    import json

    from pinakes import template as template_module

    good = synthetic_template("good", versions={"1.0": "[kb]\n"}, current="1.0")
    root = template_module._root(good)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(root, Path)
    (root.parent / "broken").mkdir()

    assert main(["templates", "--json"]) == EXIT_FAILURE
    payload = json.loads(capsys.readouterr().out)

    by_name = {row["name"]: row for row in payload}
    assert by_name["good"]["version"] == "1.0"
    assert "unreadable" in by_name["broken"]
    assert "version" not in by_name["broken"], "a damaged template must not claim a version"
