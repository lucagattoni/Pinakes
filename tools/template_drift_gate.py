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
    (vii) no archived version has changed since it was published

**`template.toml` is excluded from the content hash, and that exclusion is what makes leg (ii)
able to fail.** Hashing the file that declares the version would make every bump change the hash
by construction, so "a version bumped with no content change" could never be detected.

**Three honest limits, so the gate never claims the stronger reading of itself.**

(a) Leg (vii) is the only leg that can see a *coordinated* edit — an author who changes
    `pinakes.toml.j2`, copies it over the archived copy and updates the ledger row passes (i)-(iv)
    with the version untouched. Without git history — a shallow CI clone, an sdist, a vendored
    copy — or without a published branch to compare against, the gate degrades to (i)-(vi), which
    that three-file edit passes. The gate prints which mode it ran in every time; it never claims
    the stronger one silently.
(b) An archived `template.toml` is outside the content hash, so its *description* could be edited
    without (i)-(iv) noticing. Its presence and its declared version are checked against the
    directory name; **its `files` list is folded into the content hash** (T7 made that key decide
    what a KB is stamped with, so leaving it out would let a template change what it writes with no
    version bump); nothing else in it is. Leg (vii) covers the rest once the version is published.
(c) **Leg (vii) reads history, and history can be rewritten.** Squashing or amending the commits
    that added an archived version, then editing it, leaves one commit and content identical to
    the published ref — and passes. That is unavoidable for anything that reasons about git, and it
    is why the ledger exists alongside: rewriting history to hide an archive edit is a much louder
    act than making one.
(d) Leg (vii) has a false-positive mode: a tree-wide move, a licence-header sweep or a
    `git filter-repo` adds a second landed commit to an untouched archive directory. The remedy is
    that the failure names the directory and every commit, so a human can see it was not a content
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
from pinakes.template import CONTEXT_KEYS

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
# the **key set** is the whole point. **The keys come from `template.CONTEXT_KEYS`** — the same
# union `pnk doctor` renders both sides of a comparison through — rather than being written out
# again here. A literal copy would let this gate stay green while `doctor` raised on a KB it could
# not render: the gate would be asserting that the archive renders under a context the product
# does not use. A template version needing a variable outside the union fails leg (vi), which is
# the intended coupling: this build must be able to render every version it ships, or `pnk upgrade`
# cannot read its own archive.
_STOCK_VALUES: dict[str, Any] = {
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
STOCK_CONTEXT: dict[str, Any] = {key: _STOCK_VALUES.get(key, "stock") for key in CONTEXT_KEYS}


def _plural(count: int, noun: str, plural: str | None = None) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {plural or noun + 's'}"


class GateFailureError(Exception):
    """Operator-facing lines, never a traceback."""

    def __init__(self, *lines: str) -> None:
        super().__init__(lines[0] if lines else "")
        self.lines: tuple[str, ...] = lines


def _git_ignored(directory: Path, candidates: list[Path]) -> set[Path]:
    """The subset of `candidates` git ignores. Empty whenever git cannot answer.

    **Ignored, not untracked, and the difference is the whole design.** The hash must cover what
    *ships*, and hatchling packages the working tree (`pyproject.toml`'s
    `artifacts = ["src/pinakes/templates/**"]`). Measured, both directions: a gitignored
    `.DS_Store` under the template directory does **not** reach the wheel, while an untracked but
    un-ignored `pinakes.toml.j2.orig` **does**. So hashing git's *tracked* set would be wrong twice
    over — it would hash away a stray file that really publishes, and it would give a brand-new
    archive the digest of the empty string, because the increment that adds one runs `./check.sh`
    before committing it. Ignoring what git ignores is the only rule that matches what travels.

    **This does not make the hash environment-dependent.** A file git ignores is never committed,
    so it is absent from CI, from a fresh clone and from the sdist: on every tree a ledger row is
    computed or checked against, "skip what git ignores" and "hash everything" agree. What it
    removes is the one case where they differed — a working copy with editor or Finder droppings in
    the template directory, which turned `./check.sh` red on a clean checkout and, worse, could be
    folded into a `--print-hash` value and committed as a ledger row that only CI rejects.

    The residual risk, stated rather than hidden: a *global* `core.excludesFile` ignoring a
    genuinely consumed file would make one machine disagree with CI. That surfaces as a ledger
    mismatch, which is the right way round.
    """
    if not candidates:
        return set()
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-z", "--stdin"],
            cwd=directory,
            input="\0".join(str(path) for path in candidates),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # pragma: no cover — git absent from the machine
        return set()
    # 0 = at least one path is ignored, 1 = none is. Anything else (128 outside a repository) means
    # git could not answer, and an unanswered question must never drop a file from the hash.
    if result.returncode not in (0, 1):
        return set()
    return {Path(line) for line in result.stdout.split("\0") if line}


def _hashed_files(directory: Path) -> Iterator[tuple[str, Path]]:
    """Every file a version's content hash covers, as `(relative POSIX path, path)`.

    An **exclude**-list, so a template that gains a new consumed file is covered without editing
    this gate. Three exclusions, each load-bearing:

    * anything under a `_versions/` component — the archive is not part of the live content, and
      hashing it would make the live hash depend on its own history;
    * `template.toml` at the top of the hashed directory — see the module docstring: this is the
      exclusion leg (ii) exists on top of;
    * anything git ignores — see `_git_ignored`. Asked of git rather than kept as a list of junk
      filenames, because that list is never finished: `check.sh`'s NUL scan records the same lesson
      about binary suffixes, and answers it the same way.
    """
    candidates: list[Path] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory)
        if VERSIONS_DIR in relative.parts:
            continue
        if relative.as_posix() == DECLARATION:
            continue
        candidates.append(path)

    ignored = _git_ignored(directory, candidates)
    for path in candidates:
        if path not in ignored:
            yield path.relative_to(directory).as_posix(), path


def content_hash(directory: Path) -> str:
    """SHA-256 over a version's consumed files: `path\\0length\\0bytes` each, sorted by path.

    **The one definition.** Fixtures in later increments build synthetic archives and write
    ledger rows the gate must accept; a fixture that re-implemented this would drift from the gate
    and the gate would win, surfacing as an unrelated red test in an unrelated increment.

    The path is hashed as well as the bytes, so moving a file between two names — same bytes,
    different layout — is a change. **The length is hashed because `path\\0bytes\\0` alone was
    ambiguous**: a path cannot hold a NUL but file content can, so one file containing `y\\0z\\0`
    and the two files `y` and `z` containing nothing produced the same digest. Length-framing
    removes the collision instead of resting on template files never holding a NUL byte.

    **`template.toml`'s `files` list is folded in, and it is the one part of that file that is.**
    T7 made `files = [...]` decide *which* files a KB is stamped with, which put a behaviour-bearing
    key inside the one file this hash excludes — so a template could change what it writes into
    every new KB without any version bump being required, which is the property the archive exists
    to hold. Only the list is hashed: `name`, `version` and `description` stay out, so leg (ii) can
    still fail (hashing the version would make every bump change the hash by construction) and
    limit (b) still holds for the description.

    **An absent key contributes nothing, so every hash written before T7 is unchanged** and the
    `_versions.toml` rows already published still match. An *empty* list is not absent and does
    change the hash — correctly: absent means the historical two files, `[]` means none.
    """
    digest = hashlib.sha256()
    for relative, path in _hashed_files(directory):
        data = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)

    declared = _declared_files(directory)
    if declared is not None:
        # A leading NUL opens the block, which no file entry can produce: an entry starts with its
        # relative path, and a path cannot hold a NUL. So a template with a real file named `files`
        # cannot collide with a template declaring that list.
        digest.update(b"\0files\0")
        for entry in declared:
            data = entry.encode("utf-8")
            digest.update(str(len(data)).encode("ascii"))
            digest.update(b"\0")
            digest.update(data)
    return digest.hexdigest()


def _declared_files(directory: Path) -> list[str] | None:
    """A version's declared `files` list, or `None` when the key is absent.

    `None` rather than `[]` for absent, because the two mean different things to `copy_extras` and
    must therefore hash differently.
    """
    declaration = directory / DECLARATION
    if not declaration.is_file():
        return None
    data: dict[str, Any] = tomllib.loads(declaration.read_text(encoding="utf-8"))
    if "files" not in data:
        return None

    declared: object = data["files"]
    if not isinstance(declared, list):
        raise GateFailureError(f"{declaration} declares a `files` that is not a list.")
    entries: list[str] = []
    for item in cast(list[object], declared):
        if not isinstance(item, str):
            raise GateFailureError(f"{declaration} declares a `files` entry that is not a string.")
        entries.append(item)
    return entries


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


def published_ref(repo: Path) -> str | None:
    """The ref an archived version counts as **published** against, or `None`.

    Leg (vii) asks whether a version that already shipped has been edited, and "already shipped"
    means *landed*, never *committed*. Counting every commit that touched the directory conflates
    the two, and the project's own procedure produces the difference: `docs/BUILDING.md` requires a
    green `./check.sh` before review **and** review fixes in their own commit, so a branch that adds
    an archive and then corrects it has two commits on a version that has never shipped.
    """
    for ref in ("origin/main", "origin/HEAD", "main"):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return ref
    return None


def is_published(repo: Path, ref: str, path: Path) -> bool:
    """Does `ref` carry this archived directory at all? If not, the version is new."""
    result = subprocess.run(
        ["git", "ls-tree", "-d", "--name-only", ref, "--", str(path)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def differs_from(repo: Path, ref: str, path: Path) -> bool:
    """Has this archived directory changed since `ref`? The in-flight half of leg (vii)."""
    result = subprocess.run(
        ["git", "diff", "--quiet", ref, "--", str(path)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode != 0


def commits_touching(repo: Path, path: Path, ref: str) -> list[str]:
    """Commits reachable from `ref` that touched `path`. Absolute `path`, always.

    A relative pathspec is resolved against `cwd`, not against the caller's working directory, so
    passing one here matched nothing and the leg reported the strong mode having checked nothing.
    """
    result = subprocess.run(
        ["git", "log", "--format=%H", ref, "--", str(path)],
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

            # An archived version declares itself. Outside the content hash by design (limit (b)),
            # so only its presence and its directory name are checked — but *checked*: the docstring
            # claimed this and the code did not do it, and an archive missing its `template.toml`
            # passed all seven legs.
            if not (entry / DECLARATION).is_file():
                raise GateFailureError(
                    f"{name}@{version} is archived without a {DECLARATION}.",
                    "An archived version declares its own name and version; `pnk upgrade` reads "
                    "them back when it reconstructs what a KB was stamped from.",
                )
            archived_declares = declared_version(entry)
            if archived_declares != version:
                raise GateFailureError(
                    f"{name}@{version} is archived in a directory named {version} but its "
                    f"{DECLARATION} declares {archived_declares}.",
                )

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
    """Leg (vii). Always returns a line naming which mode it ran in — a skip is not a pass.

    **Two halves, because no single one of them is complete.** The question is whether a version
    that already *shipped* has been edited, and an archive can be wronged from either side of the
    publication line:

    * **landed history** — at most one commit *reachable from the published ref* may touch an
      archived directory. Catches an add and a later edit that both landed.
    * **in-flight content** — if the published ref carries the directory at all, the working tree's
      copy must be byte-identical to it. Catches the coordinated three-file edit **before** it
      merges, which is the case worth catching.

    Counting every commit instead — the first version of this leg — failed a branch that adds an
    archive and then corrects it during review, which is the sequence `docs/BUILDING.md` requires
    (green `./check.sh` before review, review fixes in their own commit). An archive the published
    ref does not carry is **new**, and neither half constrains it.
    """
    where = (repo if repo is not None else templates).resolve()
    reason = git_history_reason(where)
    if reason is not None:
        return f"{PREFIX}: history leg (vii) skipped: {reason}."

    ref = published_ref(where)
    if ref is None:
        return (
            f"{PREFIX}: history leg (vii) skipped: no published branch here "
            "(looked for origin/main, origin/HEAD, main)."
        )

    problems: list[str] = []
    checked = 0
    fresh = 0
    for template in names:
        for entry in archived_dirs(template):
            absolute = entry.resolve()
            if not is_published(where, ref, absolute):
                fresh += 1
                continue
            checked += 1
            commits = commits_touching(where, absolute, ref)
            if len(commits) > 1:
                problems.append(
                    f"  {entry.relative_to(templates)} — {len(commits)} commits on {ref}: "
                    + ", ".join(commit[:12] for commit in commits)
                )
            elif differs_from(where, ref, absolute):
                problems.append(
                    f"  {entry.relative_to(templates)} — differs from {ref} in this working tree"
                )
    if problems:
        raise GateFailureError(
            "an archived version was edited after it shipped. An archive is frozen: the whole "
            "point is that it still says what the version said when it was published.",
            *problems,
            "If this was a tree-wide move or a header sweep rather than a content edit, the "
            "commits above will show it — the remedy is to say so in review, not to weaken "
            "the leg.",
        )
    if checked == 0:
        return (
            f"{PREFIX}: history leg (vii) ran against {ref} — every archived version here is new "
            f"({_plural(fresh, 'directory', 'directories')} not on {ref}), so nothing was frozen "
            "yet for it to check."
        )
    return (
        f"{PREFIX}: history leg (vii) ran against {ref} — "
        f"{_plural(checked, 'published archived directory', 'published archived directories')} "
        f"unchanged since it shipped, {fresh} new."
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
    # Resolved here, once. A relative `--templates` used to leave leg (vii) building a pathspec
    # relative to the process cwd while git resolved it against the templates directory: it matched
    # nothing, and the gate printed `history leg (vii) ran` over a tree it had not looked at.
    templates: Path = args.templates.resolve()
    repo: Path | None = args.repo.resolve() if args.repo is not None else None
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
