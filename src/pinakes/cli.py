"""Command-line entry point.

The whole v0.1 command surface (docs/DESIGN.md §8) is declared here from the start, with each
command dispatching to a `run(args) -> int`. Commands whose increment has not landed raise
`NotImplementedYetError`, so the CLI never implies a capability it lacks.

Exit codes are a contract, not an accident:

    0  success
    1  operational failure — a `PinakesError`; message and remedy printed to stderr
    2  usage error — argparse's own code for a malformed invocation

The framework is stdlib `argparse`: v0.1's flag surface is small and a dependency would buy
nothing (plans/v0.1.md, decisions table).
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pinakes import __version__
from pinakes.errors import NotImplementedYetError, PinakesError

DESIGN_URL = "https://github.com/lucagattoni/Pinakes/blob/main/docs/DESIGN.md"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

# Where the dispatch target is stashed on the parsed namespace. Underscore-prefixed so it can never
# collide with a future command's own option: argparse would silently let `--runner` overwrite the
# dispatch target, and the CLI would call the wrong thing (or a string).
RUNNER_DEST = "_runner"

type CommandRunner = Callable[[argparse.Namespace], int]


class Command:
    """One `pnk` subcommand: its help text, the increment that implements it, and its runner."""

    def __init__(
        self,
        name: str,
        help_: str,
        increment: str,
        *,
        runner: CommandRunner | None = None,
        arguments: Callable[[argparse.ArgumentParser], None] | None = None,
    ) -> None:
        self.name = name
        self.help = help_
        self.increment = increment
        self._runner = runner
        self._arguments = arguments

    def configure(self, parser: argparse.ArgumentParser) -> None:
        if self._arguments is not None:
            self._arguments(parser)

    def run(self, args: argparse.Namespace) -> int:
        if self._runner is None:
            raise NotImplementedYetError(self.name, increment=self.increment)
        return self._runner(args)


def _kb_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--kb",
        type=Path,
        default=None,
        metavar="PATH",
        help="KB root (default: the nearest pinakes.toml, searching upwards)",
    )


def _sync_arguments(parser: argparse.ArgumentParser) -> None:
    _kb_argument(parser)
    parser.add_argument(
        "--rebuild", action="store_true", help="rebuild the index from scratch (keeps the ledger)"
    )
    parser.add_argument(
        "--sidecars-only",
        action="store_true",
        help="only mint missing sidecars; never touch the index (the pre-commit half)",
    )
    parser.add_argument(
        "--index-only",
        action="store_true",
        help="only update the index; never write into docs/ (the post-commit half)",
    )
    parser.add_argument(
        "--stage",
        action="store_true",
        help="with --sidecars-only: limit to staged files, and git add them",
    )
    parser.add_argument("--offline", action="store_true", help="never reach out for model weights")
    parser.add_argument(
        "--force-unlock", action="store_true", help="take a lock held by another machine"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="print only problems")


def run_sync(args: argparse.Namespace) -> int:
    """`pnk sync`. Exit 0 on success (including a busy lock), 1 if any document failed."""
    from pinakes import manifest as manifest_module
    from pinakes.sync import SyncOptions, sync

    loaded = manifest_module.discover(args.kb)
    report = sync(
        loaded,
        options=SyncOptions(
            rebuild=args.rebuild,
            sidecars_only=args.sidecars_only,
            index_only=args.index_only,
            stage=args.stage,
            offline=args.offline,
            force_unlock=args.force_unlock,
        ),
    )

    if report.busy:
        if not args.quiet:
            print("another sync is already running; nothing to do.")
        return EXIT_OK

    if report.reclaimed_lock:
        print(
            "took over a stale sync lock left by a process that is no longer running.",
            file=sys.stderr,
        )
    if not args.quiet:
        for line in report.lines():
            print(line)
    elif not report.ok:
        for path, error in report.failures:
            print(f"failed: {path}: {error}", file=sys.stderr)

    return EXIT_OK if report.ok else EXIT_FAILURE


# The v0.1 surface (docs/DESIGN.md §8), in the order a user meets it. `increment` points at
# plans/v0.1.md, so an unimplemented command tells the user exactly when it arrives.
COMMANDS: tuple[Command, ...] = (
    Command("init", "Create a KB from a template", "I10"),
    Command(
        "sync",
        "Index changed sources (--rebuild for a full rebuild)",
        "I8b",
        runner=lambda args: run_sync(args),
        arguments=_sync_arguments,
    ),
    Command("search", "Hybrid retrieval: BM25 + vector + rerank", "I10"),
    Command("doctor", "Check environment, coherence, orphans, links, hooks", "I11"),
    Command("install-hooks", "Install git hooks that keep the index fresh", "I12"),
    Command("serve", "Run the MCP server", "I13"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pnk",
        description="pinakes — a portable, agent-first knowledge base.",
        epilog=f"Design specification: {DESIGN_URL}",
    )
    parser.add_argument("--version", action="version", version=f"pinakes {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for command in COMMANDS:
        sub = subparsers.add_parser(command.name, help=command.help, description=command.help)
        command.configure(sub)
        sub.set_defaults(_runner=command.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    runner: CommandRunner | None = getattr(args, RUNNER_DEST, None)
    if runner is None:
        parser.print_help()
        return EXIT_OK

    try:
        return runner(args)
    except PinakesError as exc:
        print(f"error: {exc.message}\n{exc.remedy}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
