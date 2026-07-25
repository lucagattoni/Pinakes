"""Command-line entry point.

A deliberate stub. `--version` works; every command documented in docs/DESIGN.md §8 exits
non-zero with a pointer to the design, so the CLI never implies capability it lacks.

The CLI framework is intentionally not chosen yet — argparse keeps the bootstrap free of a
dependency the design has not decided on.
"""

import argparse
import sys

from pinakes import __version__

DESIGN_URL = "https://github.com/lucagattoni/Pinakes/blob/main/docs/DESIGN.md"

# Planned for v0.1 (docs/DESIGN.md §8).
COMMANDS = {
    "init": "Create a KB from a template",
    "sync": "Index changed sources (add --rebuild for a full rebuild)",
    "search": "Hybrid retrieval: BM25 + vector + rerank",
    "doctor": "Check environment, model coherence, orphans, link coverage",
    "install-hooks": "Install git hooks that keep the index fresh",
    "serve": "Run the MCP server",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="pnk",
        description="pinakes — a portable, agent-first knowledge base.",
        epilog=f"Design specification: {DESIGN_URL}",
    )
    parser.add_argument("--version", action="version", version=f"pinakes {__version__}")
    parser.add_argument(
        "command",
        nargs="?",
        choices=sorted(COMMANDS),
        help="; ".join(f"{name}: {help_}" for name, help_ in sorted(COMMANDS.items())),
    )
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    print(
        f"pnk {args.command} is not implemented yet — pinakes is at the design stage.\n"
        f"See {DESIGN_URL} for the specification and delivery plan.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
