"""Template drift — the gate that makes a template version number mean something.

**Why a gate at all.** `pnk doctor` has compared a KB's recorded template reference against the
installed one since 0.1, and it has never once been able to fire: `notes`' `template.toml` has
said `version = "1.0"` in every commit since the template was created, while the files that
version *denotes* changed in ten later commits. Every KB in existence therefore recorded
`notes@1.0`, the installed template was also `notes@1.0`, and the check returned OK — for eleven
different template contents. The rule "bump the version when you change the template" existed and
was silently not followed, which is this project's threshold for replacing a convention with a
gate.

**What a version denotes: any byte under the hashed set.** Comments included. The comment block in
`pinakes.toml.j2` explaining that PDFs need an `include` glob *is* the product — it is how a user
learns the thing — so a rule that hashed only keys and values would ignore the half of the
template's real drift that users are actually harmed by missing.

The seven legs, per template:

    (i)   the live files hash equal to `_versions/<the live version>/`
    (ii)  no two archived versions share a content hash — a bump with no change
    (iii) every archived version hashes equal to its `_versions.toml` row
    (iv)  `_versions.toml` and the archive directories agree, in both directions
    (v)   the live version is archived at all
    (vi)  every archived version still renders
    (vii) no archived directory has been touched by a second commit

**`template.toml` is excluded from the content hash, and that exclusion is what makes leg (ii)
able to fail.** Hashing the file that declares the version would make every bump change the hash
by construction, so "a version bumped with no content change" could never be detected.

**Three honest limits, so the gate never claims the stronger reading of itself.**

(a) Leg (vii) is the only leg that can see a *coordinated* edit — an author who changes
    `pinakes.toml.j2`, copies it over the archived copy and updates the ledger row passes (i)-(iv)
    with the version untouched. Without git history — a shallow CI clone, an sdist, a vendored
    copy — the gate degrades to (i)-(vi), which that three-file edit passes. The gate prints which
    mode it ran in every time; it never claims the stronger one silently.
(b) An archived `template.toml` is outside the content hash, so its declared version could be
    edited without (i)-(iv) noticing. Only its presence and its directory name are checked. Leg
    (vii) covers this when history is available.
(c) Leg (vii) has a false-positive mode: a tree-wide move, a licence-header sweep or a
    `git filter-repo` adds a second commit to an untouched archive directory. The remedy is that
    the failure names the directory and every commit, so a human can see it was not a content
    edit — not to weaken the leg.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, cast

from jinja2 import StrictUndefined, Template, TemplateError, UndefinedError

from pinakes.init import DEFAULT_EMBEDDING, DEFAULT_RERANK

ROOT = Path(__file__).resolve().parent.parent
VERSIONS_DIR = "_versions"
LEDGER_NAME = "_versions.toml"
DECLARATION = "template.toml"
MANIFEST_TEMPLATE = "pinakes.toml.j2"
PREFIX = "template-drift"

SKIPPED_REASON = "no git history here (shallow clone or not a checkout)"

_EMBEDDING_PROVIDER, _EMBEDDING_MODEL, _EMBEDDING_DIM = DEFAULT_EMBEDDING
_RERANK_PROVIDER, _RERANK_MODEL = DEFAULT_RERANK

# Leg (vi) only asks whether an archived version *renders*, so the values here are arbitrary and
# the **key set** is the whole point. It is the set `pnk init` passes (`init.py`), sourced from
# init's own constants where they exist so the two cannot drift apart. A template version that
# needs a variable absent here fails leg (vi) — which is the intended coupling: this build must be
# able to render every version it ships, or `pnk upgrade` cannot read its own archive.
STOCK_CONTEXT: dict[str, Any] = {
    "name": "stock",
    "kb_id": "01JZZZZZZZZZZZZZZZZZZZZZZZ",
    "template": "stock@0",
    "created": "20200101 00:00",
    "embedding_provider": _EMBEDDING_PROVIDER,
    "embedding_model": _EMBEDDING_MODEL,
    "embedding_dim": _EMBEDDING_DIM,
    "rerank_provider": _RERANK_PROVIDER,
    "rerank_model": _RERANK_MODEL,
}


def _plural(count: int, noun: str, plural: str | None = None) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {plural or noun + 's'}"


class GateFailureError(Exception):
    """Operator-facing lines, never a traceback."""

    def __init__(self, *lines: str) -> None:
        super().__init__(lines[0] if lines else "")
        self.lines: tuple[str, ...] = lines


def _hashed_files(directory: Path) -> Iterator[tuple[str, Path]]:
    """Every file a version's content hash covers, as `(relative POSIX path, path)`.

    An **exclude**-list, so a template that gains a new consumed file is covered without editing
    this gate. Two exclusions, and both are load-bearing:

    * anything under a `_versions/` component — the archive is not part of the live content, and
      hashing it would make the live hash depend on its own history;
    * `template.toml` at the top of the hashed directory — see the module docstring: this is the
      exclusion leg (ii) exists on top of.
    """
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory)
        if VERSIONS_DIR in relative.parts:
            continue
        if relative.as_posix() == DECLARATION:
            continue
        yield relative.as_posix(), path


def content_hash(directory: Path) -> str:
    """SHA-256 over a version's consumed files: each entry `path\\0bytes`, sorted by path.

    **The one definition.** Fixtures in later increments build synthetic archives and write
    ledger rows the gate must accept; a fixture that re-implemented this would drift from the gate
    and the gate would win, surfacing as an unrelated red test in an unrelated increment.

    The path is hashed as well as the bytes, so moving a file between two names — same bytes,
    different layout — is a change.
    """
    digest = hashlib.sha256()
    for relative, path in _hashed_files(directory):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def declared_version(directory: Path) -> str:
    declaration = directory / DECLARATION
    if not declaration.is_file():
        raise GateFailureError(f"{directory} has no {DECLARATION}.")
    data: dict[str, Any] = tomllib.loads(declaration.read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise GateFailureError(f"{declaration} declares no version.")
    return version


def template_dirs(templates: Path) -> list[Path]:
    return sorted(
        entry for entry in templates.iterdir() if entry.is_dir() and not entry.name.startswith("_")
    )


def archived_dirs(template: Path) -> list[Path]:
    archive = template / VERSIONS_DIR
    if not archive.is_dir():
        return []
    return sorted(entry for entry in archive.iterdir() if entry.is_dir())


def read_ledger(templates: Path) -> dict[tuple[str, str], str]:
    """`(template name, version) -> sha256`, from the committed `_versions.toml`."""
    ledger = templates / LEDGER_NAME
    if not ledger.is_file():
        raise GateFailureError(
            f"{ledger} is missing.",
            "It is the record that makes editing an archived version a two-file commit.",
        )
    data: dict[str, Any] = tomllib.loads(ledger.read_text(encoding="utf-8"))
    rows: object = data.get("template", [])
    if not isinstance(rows, list):
        raise GateFailureError(f"{ledger}: `template` must be an array of tables.")
    out: dict[tuple[str, str], str] = {}
    for row in cast("list[object]", rows):
        if not isinstance(row, dict):
            raise GateFailureError(f"{ledger}: every `[[template]]` entry must be a table.")
        entry = cast("dict[str, object]", row)
        name, version, sha = entry.get("name"), entry.get("version"), entry.get("sha256")
        if not (isinstance(name, str) and isinstance(version, str) and isinstance(sha, str)):
            raise GateFailureError(f"{ledger}: a row is missing `name`, `version` or `sha256`.")
        key = (name, version)
        if key in out:
            raise GateFailureError(f"{ledger}: two rows for {name}@{version}.")
        out[key] = sha
    return out


def git_history_reason(repo: Path) -> str | None:
    """`None` when leg (vii) can run; otherwise why it cannot.

    Detected explicitly rather than inferred from an empty `git log`, because in a shallow clone
    `git log -- <path>` returns nothing for *every* path — which reads as "one commit or fewer"
    and would let the gate report the strong mode while checking nothing.

    **One probe, not two.** `--is-shallow-repository` answers both questions this leg has: outside
    a checkout it exits 128 (measured), and inside a shallow one it prints `true`. An
    `--is-inside-work-tree` call ahead of it looked like defensive care and was dead weight —
    mutation testing could not find an input that told the two apart, and a branch nothing can
    distinguish is a branch nobody knows works.
    """
    try:
        probe = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover — git absent from the machine
        return f"git is not runnable here ({exc})"
    if probe.returncode != 0 or probe.stdout.strip() != "false":
        return SKIPPED_REASON
    return None


def commits_touching(repo: Path, path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "log", "--format=%H", "--", str(path)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GateFailureError(f"git log failed for {path}: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line]


def _render(source_path: Path) -> None:
    body = source_path.read_text(encoding="utf-8")
    Template(body, undefined=StrictUndefined, keep_trailing_newline=True).render(**STOCK_CONTEXT)


def check(templates: Path, *, repo: Path | None = None) -> list[str]:
    """Run every leg. Returns the report lines; raises `GateFailureError` with the reason."""
    report: list[str] = []
    if not templates.is_dir():
        raise GateFailureError(f"{templates} is not a directory.")

    ledger = read_ledger(templates)
    seen: set[tuple[str, str]] = set()
    names = template_dirs(templates)
    if not names:
        raise GateFailureError(f"{templates} holds no templates.")

    for template in names:
        name = template.name
        live_version = declared_version(template)
        archive = archived_dirs(template)
        versions = [entry.name for entry in archive]

        # (v) the live version is archived at all.
        if live_version not in versions:
            raise GateFailureError(
                f"{name}@{live_version} is the live version but is not archived.",
                f"Expected {template / VERSIONS_DIR / live_version}/ to exist.",
                "Archive the live files under that directory and add its `_versions.toml` row.",
            )

        # The archive is checked against the ledger **before** the live files are compared against
        # it, and the order is the whole difference between two opposite remedies. Editing a frozen
        # `_versions/<live version>/` file also makes the live files differ from it, so a
        # live-first gate reports "the live files drifted" and sends the reader to bump a version —
        # when what actually happened is that a published version was edited and must be restored.
        by_hash: dict[str, str] = {}
        for entry in archive:
            version = entry.name
            entry_hash = content_hash(entry)

            # (iii) every archived version hashes equal to its ledger row.
            row = ledger.get((name, version))
            if row is None:
                raise GateFailureError(
                    f"{name}@{version} is archived but has no `_versions.toml` row.",
                    "The ledger is what makes editing an archive a two-file commit. Add:",
                    "",
                    "[[template]]",
                    f'name    = "{name}"',
                    f'version = "{version}"',
                    f'sha256  = "{entry_hash}"',
                )
            if row != entry_hash:
                raise GateFailureError(
                    f"{name}@{version} does not match its `_versions.toml` row.",
                    f"  ledger:   {row}",
                    f"  archived: {entry_hash}",
                    "An archived version is frozen; edit the live template and bump instead.",
                )
            seen.add((name, version))

            # (ii) no two archived versions share a content hash.
            if entry_hash in by_hash:
                raise GateFailureError(
                    f"{name}: versions {by_hash[entry_hash]} and {version} have identical "
                    "content — a version was bumped with no change to what it denotes.",
                )
            by_hash[entry_hash] = version

            # (vi) it still renders. An archive `pnk upgrade` cannot render is not an archive.
            manifest_template = entry / MANIFEST_TEMPLATE
            if not manifest_template.is_file():
                raise GateFailureError(f"{name}@{version} has no {MANIFEST_TEMPLATE}.")
            try:
                _render(manifest_template)
            except UndefinedError as exc:
                raise GateFailureError(
                    f"{name}@{version} no longer renders: {exc}.",
                    "Every archived version must render under the variables this build supplies,"
                    " or `pnk upgrade` cannot read its own archive.",
                ) from exc
            except TemplateError as exc:
                raise GateFailureError(f"{name}@{version} no longer renders: {exc}.") from exc

        # (i) the live files hash equal to their own archived copy. Last, so that every archive has
        # already been proved intact against the ledger: reaching here means a difference really is
        # the live files having moved, which is what the remedy below assumes.
        live_archive = template / VERSIONS_DIR / live_version
        if content_hash(template) != content_hash(live_archive):
            raise GateFailureError(
                f"{name}: the live files differ from archived {live_version}, "
                "which is the version they still declare.",
                f"First difference: {_first_difference(template, live_archive)}.",
                "Bump `version` in template.toml and archive the new files, or revert the edit.",
            )

        if len(archive) == 1:
            report.append(
                f"{PREFIX}: leg (ii) is vacuous for {name} — 1 archived version, so no pair of "
                "versions can collide. It has never run against this template."
            )
        report.append(
            f"{PREFIX}: {name}@{live_version} matches its archived copy "
            f"({_plural(len(list(_hashed_files(template))), 'file')} hashed, "
            f"{_plural(len(archive), 'version')} archived)."
        )

    # (iv) the ledger and the archive agree in the other direction too.
    orphans = sorted(f"{name}@{version}" for name, version in set(ledger) - seen)
    if orphans:
        raise GateFailureError(
            f"`_versions.toml` has rows with no archived directory: {', '.join(orphans)}.",
        )

    report.append(_history_leg(templates, names, repo=repo))
    return report


def _first_difference(live: Path, archived: Path) -> str:
    """Name the file that diverged, so the failure sends the reader to the right place."""
    live_files = dict(_hashed_files(live))
    archived_files = dict(_hashed_files(archived))
    for relative in sorted(set(live_files) | set(archived_files)):
        if relative not in archived_files:
            return f"{relative} is live-only"
        if relative not in live_files:
            return f"{relative} is archived-only"
        if live_files[relative].read_bytes() != archived_files[relative].read_bytes():
            return f"{relative} differs"
    return "the file set is identical (a bug in this gate)"  # pragma: no cover


def _history_leg(templates: Path, names: Sequence[Path], *, repo: Path | None) -> str:
    """Leg (vii). Always returns a line naming which mode it ran in — a skip is not a pass."""
    where = repo if repo is not None else templates
    reason = git_history_reason(where)
    if reason is not None:
        return f"{PREFIX}: history leg (vii) skipped: {reason}."

    edited: list[str] = []
    checked = 0
    for template in names:
        for entry in archived_dirs(template):
            commits = commits_touching(where, entry)
            checked += 1
            # **Zero commits is allowed and is not a hole.** The increment that adds an archive
            # runs `./check.sh` before committing it, so the directory is untracked at the moment
            # the gate first sees it. What the leg forbids is a *second* commit: an archived
            # version that was added and later edited. Zero means "not committed yet"; one means
            # "added once, never touched"; two or more is the property violation.
            if len(commits) > 1:
                edited.append(
                    f"  {entry.relative_to(templates)} — {len(commits)} commits: "
                    + ", ".join(commit[:12] for commit in commits)
                )
    if edited:
        raise GateFailureError(
            "an archived version was edited after it was added. An archive is frozen: the "
            "whole point is that it still says what the version said when it shipped.",
            *edited,
            "If this was a tree-wide move or a header sweep rather than a content edit, the "
            "commits above will show it — the remedy is to say so in review, not to weaken "
            "the leg.",
        )
    return (
        f"{PREFIX}: history leg (vii) ran — "
        f"{_plural(checked, 'archived directory', 'archived directories')}, "
        "none edited after the commit that added it."
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=ROOT / "src" / "pinakes" / "templates",
        help="the directory holding the template directories and _versions.toml",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="repository root for leg (vii); defaults to --templates",
    )
    # `content_hash` is importable, and a caller inside this repository still must not re-implement
    # it — but importing across `tools/` needs a `sys.path` insert that neither type checker can
    # follow. This flag is the same one function with a command line in front of it, so a test or a
    # fixture can ask for the authoritative hash without either compromise. Read-only by design:
    # nothing here writes a ledger, because a gate that can silently repair what it checks is not
    # one.
    parser.add_argument(
        "--print-hash",
        type=Path,
        default=None,
        metavar="DIR",
        help="print the content hash of one directory and exit — the value a ledger row needs",
    )
    args = parser.parse_args(argv)
    templates: Path = args.templates
    repo: Path | None = args.repo
    one_directory: Path | None = args.print_hash
    if one_directory is not None:
        if not one_directory.is_dir():
            print(f"{PREFIX}: {one_directory} is not a directory.", file=sys.stderr)
            return 1
        print(content_hash(one_directory))
        return 0
    try:
        for line in check(templates, repo=repo):
            print(line)
    except GateFailureError as exc:
        for line in exc.lines:
            print(
                f"{PREFIX}: {line}" if line and not line.startswith(" ") else line, file=sys.stderr
            )
        return 1
    print(f"{PREFIX}: all legs green.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
