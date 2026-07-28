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
from pinakes.manifest import Manifest

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


def _init_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", type=Path, help="directory to create the KB in")
    parser.add_argument("--name", default=None, help="human-facing name (default: the directory)")
    parser.add_argument("--template", default="notes", help="blueprint to stamp from")


def run_init(args: argparse.Namespace) -> int:
    from pinakes.init import init

    result = init(args.path, name=args.name, template_name=args.template)
    print(f"created {result.root} from {result.template}")
    print(f"  kb id: {result.kb_id}  (permanent — never edit it)")
    print("\nNext:")
    print(f"  1. put Markdown files in {result.root / 'docs'}")
    print("  2. `pnk sync` to index them, then commit the sidecars it writes")
    print('  3. `pnk search "…"` to search, for free, offline')
    return EXIT_OK


def _search_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("query", help="what to search for")
    _kb_argument(parser)
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        metavar="TAG",
        help="only documents carrying this tag (repeatable)",
    )
    parser.add_argument(
        "--path-prefix",
        default=None,
        metavar="PREFIX",
        help="only documents whose path starts with this",
    )
    parser.add_argument(
        "--source-type", default=None, metavar="TYPE", help="markdown, text, code or pdf"
    )
    parser.add_argument(
        "--modified-after",
        default=None,
        metavar="YYYYMMDD",
        help="only documents modified on or after this date",
    )
    parser.add_argument(
        "--modified-before",
        default=None,
        metavar="YYYYMMDD",
        help="only documents modified on or before this date",
    )
    parser.add_argument("-k", type=int, default=None, help="how many passages to return")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--offline", action="store_true", help="never reach out for model weights")


def _as_timestamp(value: str | None) -> float | None:
    from datetime import datetime

    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").timestamp()
    except ValueError as exc:
        raise PinakesError(
            f"{value!r} is not a date.", remedy="Use YYYYMMDD, for example 20260725."
        ) from exc


def run_search(args: argparse.Namespace) -> int:
    """`pnk search`. Prints cited passages and an honest confidence line."""
    import json as json_module

    from pinakes import manifest as manifest_module
    from pinakes import store
    from pinakes.embed import load_backend, load_reranker
    from pinakes.search import Filters, search

    loaded = manifest_module.discover(args.kb)
    backend = load_backend(loaded.embedding, offline=args.offline)
    reranker = (
        load_reranker(loaded.rerank, offline=args.offline)
        if loaded.retrieval.rerank == "local"
        else None
    )

    connection = store.connect_ro(loaded.index_path)
    try:
        result = search(
            connection,
            loaded,
            args.query,
            backend=backend,
            reranker=reranker,
            filters=Filters(
                tags=tuple(args.tag),
                path_prefix=args.path_prefix,
                source_type=args.source_type,
                modified_after=_as_timestamp(args.modified_after),
                modified_before=_as_timestamp(args.modified_before),
            ),
            limit=args.k,
        )
    finally:
        connection.close()

    if args.json:
        print(
            json_module.dumps(
                {
                    "query": result.query,
                    "confidence": result.confidence,
                    "confidence_reason": result.confidence_reason,
                    "considered": result.considered,
                    "passages": [
                        {
                            "doc_id": passage.doc_id,
                            "path": passage.path,
                            "title": passage.title,
                            "heading_path": passage.heading_path,
                            "char_start": passage.char_start,
                            "char_end": passage.char_end,
                            "text": passage.text,
                            "rerank_score": passage.rerank_score,
                            "fused_score": passage.fused_score,
                        }
                        for passage in result.passages
                    ],
                },
                indent=2,
            )
        )
        return EXIT_OK

    if not result.passages:
        print("no passages matched.")
        print(f"confidence: {result.confidence} — {result.confidence_reason}")
        return EXIT_OK

    for position, passage in enumerate(result.passages, start=1):
        heading = f" — {passage.heading_path}" if passage.heading_path else ""
        print(f"[{position}] {passage.path}{heading}")
        for line in passage.text.strip().splitlines():
            print(f"    {line}")
        print(f"    ({passage.citation()})")
        print()

    print(f"confidence: {result.confidence} — {result.confidence_reason}")
    if result.confidence in ("low", "unknown"):
        # Never advertise a command that does not exist yet: --deep lands in v0.4 (§4.2).
        print(
            "retrieval-only result. Paid synthesis (`pnk ask --deep`) is planned for v0.4; "
            "until then, narrowing the query or adding a filter is the lever you have."
        )
    return EXIT_OK


def _doctor_arguments(parser: argparse.ArgumentParser) -> None:
    _kb_argument(parser)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="delete orphaned sidecars, after printing every path",
    )


def run_doctor(args: argparse.Namespace) -> int:
    """`pnk doctor`. Exit 1 on any FAIL; warnings are reported but do not fail the command."""
    from pinakes import manifest as manifest_module
    from pinakes.doctor import Status, diagnose, prune

    loaded = manifest_module.discover(args.kb)
    report = diagnose(loaded)
    for check in report.checks:
        print(check.line())

    if args.prune:
        if not report.orphans:
            print("\nnothing to prune.")
        else:
            print("\nremoving these orphaned sidecars:")
            for path in report.orphans:
                print(f"  {path.relative_to(loaded.root)}")
            removed = prune(report.orphans)
            print(f"removed {len(removed)}.")

    return EXIT_FAILURE if report.worst is Status.FAIL else EXIT_OK


def _install_hooks_arguments(parser: argparse.ArgumentParser) -> None:
    _kb_argument(parser)


def run_install_hooks(args: argparse.Namespace) -> int:
    """`pnk install-hooks`. Exits 1 if any existing hook was left alone rather than clobbered."""
    from pinakes import manifest as manifest_module
    from pinakes.hooks import install, suggestion

    loaded = manifest_module.discover(args.kb)
    written, refused = install(loaded.root)

    for status in written:
        print(f"installed {status.name}")
    for status in refused:
        print(f"\nleft {status.path} alone — it is not ours, and editing it is not our call.")
        print("To wire pinakes in yourself, add this line:")
        print(f"    {suggestion(status.name)}")

    return EXIT_FAILURE if refused else EXIT_OK


def _serve_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "kb_paths",
        nargs="*",
        type=Path,
        metavar="KB",
        help="KB directories to serve (default: the nearest one)",
    )
    parser.add_argument("--offline", action="store_true", help="never reach out for model weights")


def run_serve(args: argparse.Namespace) -> int:
    """`pnk serve`. Serves only the KBs named here — no tool argument accepts a path (§4.7)."""
    from pinakes import manifest as manifest_module
    from pinakes.serve import build

    roots = list(args.kb_paths) or [manifest_module.find_kb_root()]
    mcp, server = build(roots, offline=args.offline)
    try:
        mcp.run()
    finally:
        server.close()
    return EXIT_OK


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
    parser.add_argument(
        "--extract",
        default=None,
        metavar="BACKEND",
        help="override `[extraction] backend` for this run only",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="with an explicit free --extract: overwrite a paid extraction (prints what it drops)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="empty the extraction cache, after confirming (never the ledger)",
    )
    parser.add_argument(
        "--yes", action="store_true", help="skip --clear-cache's confirmation prompt (cron use)"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="print only problems")


def run_sync(args: argparse.Namespace) -> int:
    """`pnk sync`. Exit 0 on success (including a busy lock), 1 if any document failed."""
    from pinakes import manifest as manifest_module
    from pinakes.sync import SyncOptions, sync

    loaded = manifest_module.discover(args.kb)

    if args.clear_cache:
        return _run_clear_cache(loaded, args)

    report = sync(
        loaded,
        options=SyncOptions(
            rebuild=args.rebuild,
            sidecars_only=args.sidecars_only,
            index_only=args.index_only,
            stage=args.stage,
            offline=args.offline,
            force_unlock=args.force_unlock,
            extract=args.extract,
            force=args.force,
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
        for line in report.failure_lines():
            print(line, file=sys.stderr)

    return EXIT_OK if report.ok else EXIT_FAILURE


def _run_clear_cache(loaded: Manifest, args: argparse.Namespace) -> int:
    """`sync()` never prompts (it does no I/O beyond the filesystem, like every other function in
    that module) — this is the one place that reads a TTY and asks, then re-calls with `yes=True`
    once confirmed."""
    from pinakes.sync import SyncOptions, sync

    report = sync(loaded, options=SyncOptions(clear_cache=True, yes=args.yes))
    if report.busy:
        print("another sync is already running; nothing to do.")
        return EXIT_OK

    if report.cache_clear_aborted:
        print(
            f"this will remove {report.cache_pending_entries} cache entries "
            f"({report.cache_pending_bytes} bytes)."
        )
        if not sys.stdin.isatty():
            print("no terminal to confirm from; re-run with --yes.", file=sys.stderr)
            return EXIT_FAILURE
        answer = input("proceed? [y/N] ").strip().lower()
        if answer != "y":
            print("aborted; nothing removed.")
            return EXIT_OK
        report = sync(loaded, options=SyncOptions(clear_cache=True, yes=True))

    print(f"removed {report.cache_cleared} entries ({report.cache_cleared_bytes} bytes).")
    return EXIT_OK


# The v0.1 surface (docs/DESIGN.md §8), in the order a user meets it. `increment` points at
# plans/v0.1.md, so an unimplemented command tells the user exactly when it arrives.
COMMANDS: tuple[Command, ...] = (
    Command(
        "init",
        "Create a KB from a template",
        "I10",
        runner=lambda args: run_init(args),
        arguments=_init_arguments,
    ),
    Command(
        "sync",
        "Index changed sources (--rebuild for a full rebuild)",
        "I8b",
        runner=lambda args: run_sync(args),
        arguments=_sync_arguments,
    ),
    Command(
        "search",
        "Hybrid retrieval: BM25 + vector + rerank",
        "I10",
        runner=lambda args: run_search(args),
        arguments=_search_arguments,
    ),
    Command(
        "doctor",
        "Check environment, coherence, orphans, links, hooks",
        "I11",
        runner=lambda args: run_doctor(args),
        arguments=_doctor_arguments,
    ),
    Command(
        "install-hooks",
        "Install git hooks that keep the index fresh",
        "I12",
        runner=lambda args: run_install_hooks(args),
        arguments=_install_hooks_arguments,
    ),
    Command(
        "serve",
        "Run the MCP server",
        "I13",
        runner=lambda args: run_serve(args),
        arguments=_serve_arguments,
    ),
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
