"""Per-change fragment files for the documents every agent appends to.

Several agents work in this repo at once. `CHANGELOG.md` and `docs/RETROSPECTIVES.md` are the two
documents *every* piece of work must write to, which makes them the two files most likely to be
edited twice in an hour — and the collision has a quiet shape as well as a loud one:

    the loud one   `git merge` conflicts.
    the quiet one  `git merge` succeeds because the edits landed on different lines. Git merged
                   them because they did not overlap textually, never because they agree.

`tools/shared_file_overlap.py` *reports* both. This removes the cause for these two documents: a
change writes `changelog.d/<category>-<slug>.md` instead of editing `CHANGELOG.md`, so two agents
cannot touch the same file — the conflict class stops existing rather than being managed. The
fragments are spliced into the real document at release time, by one actor, with nothing else
running. That is the towncrier/scriv/reno model, and this is a small stdlib implementation of it.

**Traceability is unchanged, which is the point.** `CLAUDE.md` requires the changelog entry to land
in the same commit as the code; a fragment lands in the same commit as the code. What changes is
only which file it lands in.

**Category lives in the filename**, never inside the file: `added-record-fixtures.md`. A category
that cannot drift from its content is one fewer thing to check, and `ls changelog.d/` is then a
readable summary of everything unreleased.

**Existing `[Unreleased]` prose is left exactly where it is.** Splicing puts fragments *after* the
anchor without touching what is already below, so this can be adopted without a migration commit
that would itself collide with whatever the other agents are holding.

Stdlib only, importing nothing from this project — same constraint as `tools/paid_path_gate.py`.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REPO = Path(__file__).resolve().parent.parent

#: Keep a Changelog's six, lowercased for use as a filename prefix.
CHANGELOG_CATEGORIES = ("added", "changed", "deprecated", "removed", "fixed", "security")


@dataclass(frozen=True)
class Stream:
    """One fragment-backed document."""

    name: str
    directory: str
    target: str
    #: Fragments are spliced immediately after the first line equal to this.
    insert_after: str | None = None
    #: …or immediately before the first line starting with this, for a document with a footer.
    insert_before: str | None = None
    #: Filename-prefix vocabulary, or None when a fragment is free-form prose.
    categories: tuple[str, ...] | None = None

    def path(self, repo: Path) -> Path:
        return repo / self.directory


STREAMS: dict[str, Stream] = {
    "changelog": Stream(
        name="changelog",
        directory="changelog.d",
        target="CHANGELOG.md",
        insert_after="## [Unreleased]",
        categories=CHANGELOG_CATEGORIES,
    ),
    "retrospectives": Stream(
        name="retrospectives",
        directory="retro.d",
        target="docs/RETROSPECTIVES.md",
        # This file ends with the pre-implementation design-review passes, which must stay last.
        insert_before="## Design review passes",
    ),
}

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class FragmentError(Exception):
    """A fragment that would produce a malformed document. Reported with its filename."""


def fragments_of(stream: Stream, repo: Path) -> list[Path]:
    directory = stream.path(repo)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.md") if p.name != "README.md")


#: `YYYYMMDD_HHMM-`, the timestamp prefix every fragment and plan carries.
_STAMP = re.compile(r"^\d{8}_\d{4}-")


def body_of(path: Path) -> str:
    """The filename with its `YYYYMMDD_HHMM-` prefix removed.

    The prefix orders `ls` chronologically and dates a fragment without opening it. Everything
    downstream — the category, the slug — reads what follows it, so the stem is stripped once
    here rather than at each caller. A fragment *without* a prefix is not an error: the
    convention began 20260804 07:00 and refusing files that predate it buys nothing.
    """
    return _STAMP.sub("", path.stem, count=1)


def category_of(stream: Stream, path: Path) -> str | None:
    """The category a fragment's filename declares, validated against the stream's vocabulary."""
    if stream.categories is None:
        return None
    head = body_of(path).split("-", 1)[0]
    if head not in stream.categories:
        raise FragmentError(
            f"{stream.directory}/{path.name}: filename must be "
            f"`YYYYMMDD_HHMM-<category>-<slug>.md` with a category from "
            f"{', '.join(stream.categories)} — found {head!r}"
        )
    return head


def check(stream: Stream, repo: Path) -> list[str]:
    """Every problem found, rather than the first.

    A caller fixing fragments wants the whole list.
    """
    problems: list[str] = []
    for path in fragments_of(stream, repo):
        try:
            category = category_of(stream, path)
        except FragmentError as exc:
            problems.append(str(exc))
            continue
        stem = body_of(path)
        slug = stem.split("-", 1)[1] if category and "-" in stem else stem
        if not _SLUG.fullmatch(slug):
            problems.append(f"{stream.directory}/{path.name}: name must be lowercase-with-hyphens")
        if not path.read_text(encoding="utf-8").strip():
            problems.append(f"{stream.directory}/{path.name}: is empty")
    return problems


def render(stream: Stream, repo: Path) -> str:
    """The fragments as one markdown block, grouped by category in the stream's declared order."""
    paths = fragments_of(stream, repo)
    if not paths:
        return ""

    def body(path: Path) -> str:
        return path.read_text(encoding="utf-8").strip("\n")

    if stream.categories is None:
        return "\n\n".join(body(p) for p in paths) + "\n"

    grouped: dict[str, list[str]] = {}
    for path in paths:
        category = category_of(stream, path)
        assert category is not None
        grouped.setdefault(category, []).append(body(path))

    blocks: list[str] = []
    for category in stream.categories:
        if category not in grouped:
            continue
        blocks.append(f"### {category.capitalize()}\n\n" + "\n\n".join(grouped[category]))
    return "\n\n".join(blocks) + "\n"


def grouped_bodies(stream: Stream, repo: Path) -> dict[str, list[str]]:
    """Fragment bodies keyed by category, for a stream that has one."""
    grouped: dict[str, list[str]] = {}
    for path in fragments_of(stream, repo):
        category = category_of(stream, path)
        assert category is not None
        grouped.setdefault(category, []).append(path.read_text(encoding="utf-8").strip("\n"))
    return grouped


def _merge_into_section(
    stream: Stream, lines: list[str], anchor_index: int, grouped: dict[str, list[str]]
) -> str:
    """Merge fragments into the anchor's section, reusing a `### Category` heading if one is there.

    Found by cutting a release with it: dumping every rendered `### Category` block under the anchor
    produced a `[Unreleased]` with **two** `### Added` headings, because the section already had one
    from prose nobody had migrated. Keep a Changelog expects one heading per category, and a reader
    scanning for "what was added" would stop at the first.

    The region is the anchor's own section — up to the next `##` heading — so a `### Added`
    belonging to an *older release* further down is never written into.
    """
    end = len(lines)
    for index in range(anchor_index + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break

    existing: dict[str, int] = {}
    for index in range(anchor_index + 1, end):
        heading = lines[index].rstrip("\n")
        if heading.startswith("### "):
            existing.setdefault(heading[4:].strip().lower(), index)

    # Applied last-first so that an insertion never shifts an index still to be used.
    additions: list[tuple[int, str]] = []
    fresh: list[str] = []
    for category in stream.categories or ():
        if category not in grouped:
            continue
        body = "\n\n".join(grouped[category])
        if category in existing:
            additions.append((existing[category] + 1, "\n" + body + "\n"))
        else:
            fresh.append(f"### {category.capitalize()}\n\n{body}\n")

    out = list(lines)
    for index, block in sorted(additions, reverse=True):
        out.insert(index, block)
    if fresh:
        out.insert(anchor_index + 1, "\n" + "\n".join(fresh))
    return "".join(out)


def splice(stream: Stream, rendered: str, repo: Path) -> str:
    """`rendered` inserted at the stream's anchor, leaving everything else byte-identical."""
    text = (repo / stream.target).read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    if stream.insert_after is not None:
        for index, line in enumerate(lines):
            if line.rstrip("\n") == stream.insert_after:
                if stream.categories is not None:
                    return _merge_into_section(stream, lines, index, grouped_bodies(stream, repo))
                head, tail = lines[: index + 1], lines[index + 1 :]
                return "".join(head) + "\n" + rendered + "".join(tail)
        raise FragmentError(f"{stream.target}: anchor {stream.insert_after!r} not found")

    assert stream.insert_before is not None
    for index, line in enumerate(lines):
        if line.startswith(stream.insert_before):
            head, tail = lines[:index], lines[index:]
            return "".join(head) + rendered + "\n" + "".join(tail)
    raise FragmentError(f"{stream.target}: anchor {stream.insert_before!r} not found")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stream", choices=[*sorted(STREAMS), "all"], default="all", help="which document"
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="validate fragments (a gate)")
    action.add_argument("--render", action="store_true", help="print the assembled markdown")
    action.add_argument(
        "--apply",
        action="store_true",
        help="splice fragments into the document and delete them (the release step)",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=DEFAULT_REPO,
        help="repository root (default: this script's own). Lets the tests drive the real "
        "artifact against a temp tree rather than importing it.",
    )
    args = parser.parse_args()
    repo: Path = args.repo

    streams = list(STREAMS.values()) if args.stream == "all" else [STREAMS[args.stream]]

    if args.check:
        problems = [p for stream in streams for p in check(stream, repo)]
        for problem in problems:
            print(problem, file=sys.stderr)
        if problems:
            print(f"{len(problems)} malformed fragment(s).", file=sys.stderr)
            return 1
        counts = ", ".join(f"{len(fragments_of(s, repo))} {s.name}" for s in streams)
        print(f"fragments: {counts} — all well-formed.")
        return 0

    for stream in streams:
        if problems := check(stream, repo):
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1
        rendered = render(stream, repo)
        if not rendered:
            if args.apply:
                print(f"fragments: nothing to apply for {stream.name}.")
            continue
        if args.render:
            print(rendered, end="")
            continue
        (repo / stream.target).write_text(splice(stream, rendered, repo), encoding="utf-8")
        for path in fragments_of(stream, repo):
            path.unlink()
        print(f"fragments: applied {stream.name} into {stream.target}, fragments removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
