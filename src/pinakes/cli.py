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

from pinakes import __version__
from pinakes.errors import NotImplementedYetError, PinakesError

DESIGN_URL = "https://github.com/lucagattoni/Pinakes/blob/main/docs/DESIGN.md"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

type CommandRunner = Callable[[argparse.Namespace], int]


class Command:
    """One `pnk` subcommand: its help text, the increment that implements it, and its runner."""

    def __init__(self, name: str, help_: str, increment: str) -> None:
        self.name = name
        self.help = help_
        self.increment = increment

    def run(self, args: argparse.Namespace) -> int:
        raise NotImplementedYetError(self.name, increment=self.increment)


# The v0.1 surface (docs/DESIGN.md §8), in the order a user meets it. `increment` points at
# plans/v0.1.md, so an unimplemented command tells the user exactly when it arrives.
COMMANDS: tuple[Command, ...] = (
    Command("init", "Create a KB from a template", "I10"),
    Command("sync", "Index changed sources (--rebuild for a full rebuild)", "I8b"),
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
        sub.set_defaults(run=command.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    runner: CommandRunner | None = getattr(args, "run", None)
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
