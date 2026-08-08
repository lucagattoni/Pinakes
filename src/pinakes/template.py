"""Templates — the blueprint a KB is stamped from (docs/DESIGN.md §6.1).

Templates version independently of the package, so upgrading `pinakes` never silently re-chunks
someone's corpus. They are packaged inside the wheel and read through `importlib.resources`, so
nothing depends on the source tree being present.
"""

import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, cast

from jinja2 import StrictUndefined, Template, UndefinedError

from pinakes.errors import TemplateError
from pinakes.manifest import Manifest
from pinakes.paths import lands_inside

PACKAGE = "pinakes.templates"
MANIFEST_TEMPLATE = "pinakes.toml.j2"
DEFAULT_TEMPLATE = "notes"
VERSIONS_DIR = "_versions"

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

CONTEXT_KEYS: tuple[str, ...] = (
    "name",
    "kb_id",
    "template",
    "created",
    "embedding_provider",
    "embedding_model",
    "embedding_dim",
    "rerank_provider",
    "rerank_model",
)
"""Every variable this build can supply to a manifest template — the **union across versions**.

Not "the variables the current version uses". `render_manifest` renders under `StrictUndefined`, so
a variable a later version drops must keep being supplied or the *older archived* version stops
rendering — and it stops rendering on one side of a comparison only, which turns `pnk doctor` into
a traceback on a KB whose only fault is being old. A variable leaves a template; it does not leave
this tuple.

`tools/template_drift_gate.py` leg (vi) builds its context from exactly these keys, so an archived
version needing a variable outside the union is a red build rather than a user's crash.
"""


@dataclass(frozen=True, slots=True)
class TemplateInfo:
    name: str
    version: str
    description: str

    @property
    def reference(self) -> str:
        """`notes@1.0` — what the manifest records, so a later `pnk upgrade` can diff it."""
        return f"{self.name}@{self.version}"


def _unknown(name: str) -> TemplateError:
    return TemplateError(
        f"no template named {name!r}.",
        remedy=f"Available: {', '.join(available()) or '(none)'}.",
    )


def _root(name: str) -> Traversable:
    # A template name is **one path component**, checked before the join and not after. `joinpath`
    # happily accepts separators and `..`, so without this `describe("notes/../notes")` and
    # `describe("../templates/notes")` both succeed — measured, not theorised. That was harmless
    # only while every directory under the package root was a template; `_versions/` ends that,
    # because `--template notes/_versions/1.1` would stamp a KB from an archived version nobody
    # released. The pattern also excludes a leading `_`, which is what `available()` hides.
    if not _NAME.fullmatch(name):
        raise _unknown(name)
    try:
        root = resources.files(PACKAGE).joinpath(name)
    except ModuleNotFoundError as exc:  # pragma: no cover — packaging failure
        raise TemplateError(f"template package {PACKAGE} is missing.", remedy="Reinstall.") from exc
    if not root.is_dir():
        raise _unknown(name)
    return root


def available() -> list[str]:
    return sorted(
        entry.name
        for entry in resources.files(PACKAGE).iterdir()
        if entry.is_dir() and not entry.name.startswith("_")
    )


def describe(name: str) -> TemplateInfo:
    raw = _root(name).joinpath("template.toml").read_text(encoding="utf-8")
    data: dict[str, Any] = tomllib.loads(raw)
    return TemplateInfo(
        name=str(data.get("name", name)),
        version=str(data.get("version", "0")),
        description=str(data.get("description", "")),
    )


def render_context(manifest: Manifest) -> dict[str, Any]:
    """The one variable mapping both sides of a template comparison render through.

    **One context, rendered twice.** Two contexts would let a difference between the *contexts*
    appear as a difference between the *templates*, which is the one thing this report must never
    say. Everything below follows from that.

    **Every identity field comes from the KB's manifest, and `template` is the one that matters.**
    `pnk init` passes the *installed* reference (`init.py:75`) because at `init` time the recorded
    and installed references are the same string. They are not the same string here, and the
    obvious third choice — old side gets the recorded reference, new side gets the installed one —
    puts a `[kb] template` hunk in **every** report on **every** KB, which under T4's
    all-or-nothing conflict rule would make `--apply` refuse for every user who ever touched their
    `[kb]` block. Both sides therefore render the *recorded* reference and `[kb]` is byte-identical
    on both, so it can never produce a hunk.

    Two consequences, both of them the point rather than side-effects: a user's edit to a rendered
    variable (`provider = "fastembed"`) is identical on both sides and cannot appear in the diff,
    and a user's edit to a literal line (`final_k = 4`) never enters either side, because neither
    side is their file.

    `template` and `created` are optional in a manifest. Their fallback is `""` and it is
    unobservable by construction: the value is written to both sides or to neither.
    """
    return {
        "name": manifest.kb.name,
        "kb_id": str(manifest.kb.id),
        "template": manifest.kb.template or "",
        "created": manifest.kb.created or "",
        "embedding_provider": manifest.embedding.provider,
        "embedding_model": manifest.embedding.model,
        "embedding_dim": manifest.embedding.dim,
        "rerank_provider": manifest.rerank.provider,
        "rerank_model": manifest.rerank.model,
    }


def _render(source: str, context: dict[str, Any], *, name: str, version: str | None = None) -> str:
    """Render one manifest template, turning a missing variable into a message rather than a crash.

    `jinja2.UndefinedError` is not a `PinakesError`, so without this `cli.main` prints a traceback.
    `CONTEXT_KEYS` covers every version this build ships — so the templates in the wheel cannot
    reach here — but a third-party template, or an archived version that arrived on the machine
    some other way, can need a variable no union contains. That is a message, not a stack trace.

    The reference is assembled in the `except` branch and nowhere else: naming the version costs a
    second file read, and the successful render is the path that runs.
    """
    try:
        return Template(source, undefined=StrictUndefined, keep_trailing_newline=True).render(
            **context
        )
    except UndefinedError as exc:
        reference = f"{name}@{describe(name).version if version is None else version}"
        raise TemplateError(
            f"{reference} needs a variable this build does not supply: {exc.message}",
            remedy=f"This build of Pinakes cannot render {reference}. It supplies "
            f"{', '.join(CONTEXT_KEYS)}. A template needing anything else was written for a "
            "different build.",
        ) from exc


def render_manifest(name: str, context: dict[str, Any]) -> str:
    """Render `pinakes.toml`. `StrictUndefined`: a missing variable fails here, not at read time."""
    source = _root(name).joinpath(MANIFEST_TEMPLATE).read_text(encoding="utf-8")
    return _render(source, context, name=name)


def version_key(version: str) -> tuple[str, ...]:
    """Order versions the way a human reads them: `1.2` < `1.9` < `1.10`.

    A plain string sort puts `1.10` before `1.9`, which would make `archived_versions`' "oldest
    first" a lie the moment a template reaches its tenth revision. Numeric segments are zero-padded
    so they compare by magnitude; a non-numeric segment is prefixed with `~` (above every digit in
    ASCII) so it sorts after every number rather than interleaving with them.
    """
    return tuple(
        part.rjust(12, "0") if part.isdigit() else "~" + part for part in version.split(".")
    )


def archived_versions(name: str) -> list[str]:
    """Every version of `name` whose content is frozen under `_versions/`, oldest first.

    A KB records only a reference (`notes@1.1`), never the content it was stamped from, so the
    archive is the only thing that can say what that reference *meant*. Empty when the template
    has no archive at all — a third-party template need not carry one.
    """
    root = _root(name).joinpath(VERSIONS_DIR)
    if not root.is_dir():
        return []
    return sorted((entry.name for entry in root.iterdir() if entry.is_dir()), key=version_key)


def archived_root(name: str, version: str) -> Traversable:
    """The frozen directory for one version. Raises `TemplateError` naming it when absent.

    The version is validated as its own path component for the same reason the name is: it is
    joined onto a path, and it reaches here from a KB's manifest — a file Pinakes does not write.
    """
    root = _root(name)
    if not _VERSION.fullmatch(version):
        raise TemplateError(
            f"{name}@{version} is not a version this build can read.",
            remedy="A template version is one path component.",
        )
    archived = root.joinpath(VERSIONS_DIR).joinpath(version)
    if not archived.is_dir():
        known = ", ".join(archived_versions(name)) or "(none)"
        raise TemplateError(
            f"{name}@{version} is not archived in this build.",
            remedy=f"Archived versions of {name}: {known}.",
        )
    return archived


def render_archived(name: str, version: str, context: dict[str, Any]) -> str:
    """`render_manifest`'s archived counterpart — what `pnk upgrade` diffs against.

    Rendered rather than read, because the archived file is a template too: comparing a rendered
    manifest against an unrendered `.j2` would report every `{{ variable }}` as a difference.
    """
    source = archived_root(name, version).joinpath(MANIFEST_TEMPLATE).read_text(encoding="utf-8")
    return _render(source, context, name=name, version=version)


def cannot_compare(missing: Sequence[str], name: str, archived: Sequence[str]) -> tuple[str, str]:
    """The `(detail, remedy)` every surface prints when a version's content is not in the archive.

    **Here rather than in either caller, because two surfaces say it and they must say the same
    thing.** `pnk doctor` reports it as a `WARN` row and `pnk upgrade` as its own outcome; the two
    lived as byte-identical copies for one increment, with nothing that would notice if one were
    reworded. Two surfaces disagreeing about one KB is the defect class this release exists to
    remove, so the wording is a fact with one home like any other.

    **It is the path 100% of today's KBs take, so it is written for someone who did nothing
    wrong.** `notes@1.0` is deliberately not archived — it denotes eleven different template
    contents, and a diff computed from the wrong base is worse than no diff — and this is what they
    get instead. It promises nothing a release *cannot* keep: an unarchived version's content
    is gone, not pending.
    """
    shipped = ", ".join(f"{name}@{version}" for version in archived)
    return (
        f"cannot compare: {' and '.join(missing)} "
        f"{'is' if len(missing) == 1 else 'are'} not in this build's archive",
        f"Nothing is wrong with your KB and nothing needs changing. A manifest records a version "
        f"string, never the content that version meant, and this build ships the content of "
        f"{shipped or 'no version of this template'} — so there is no baseline to diff against, "
        f"and there will not be a later one: an unarchived version's content is gone, not pending. "
        f"To see what moved, compare it by hand: run `pnk init` on a throwaway directory and diff "
        f"its pinakes.toml against yours. A KB stamped from "
        # `archived[0]`, the **oldest** archived version, because the sentence says *or later*.
        # `[-1]` names the newest and reads as a promise that excludes every version between —
        # true while one version is archived, false and user-facing from the next bump onward.
        f"{f'{name}@{archived[0]}' if archived else 'an archived version'} or later is compared "
        f"automatically.",
    )


HISTORICAL_FILES: tuple[str, ...] = ("README.md", "eval/questions.yaml")
"""What `copy_extras` copied before a template could declare it, and what an absent `files` means.

**Absent is these two, never none.** Every template that exists today declares nothing — `notes`
included — so reading an absent key as an empty list would stop stamping a README and a starter
golden set into every new KB, and would do it silently. It also means no third-party template
written against an earlier build changes behaviour by standing still.
"""


def declared_files(name: str) -> tuple[str, ...]:
    """The files `name` says it writes into a KB, validated as a declaration rather than as a path.

    **What is checked here is what can be judged without a target**: the shape of the value, and the
    version archive. Whether an entry *lands* inside a KB depends on the KB — a symlinked directory
    in the target is a fact about the target, not about the template — so `copy_extras` checks that
    against the real one.

    **`_versions` is refused as a path component, and this is the increment where such a rule can
    first fail.** While `copy_extras` iterated a hardcoded pair, no archive path was reachable
    whatever the archive held, and a test asserting otherwise was satisfied by the hardcoding rather
    than by any rule. The moment the list is read from `template.toml`, a template can declare
    `_versions/1.0/README.md` — and containment would **pass** it, because it lands inside the
    target. Containment is the wrong instrument here: it measures escape, not provenance. An
    archived version is the frozen record of what a reference once meant, so copying it into a KB
    would stamp content from a version nobody released under the name of one they did.
    """
    raw = _root(name).joinpath("template.toml").read_text(encoding="utf-8")
    data: dict[str, Any] = tomllib.loads(raw)
    if "files" not in data:
        return HISTORICAL_FILES

    # Narrowed element by element rather than with `all(isinstance(...))`: `tomllib` returns `Any`,
    # so the comprehension's item type stays unknown under pyright strict and the list would be
    # `list[str]` only by assertion. Building the typed list is the narrowing.
    declared: object = data["files"]
    shape = TemplateError(
        f"template {name} declares a `files` that is not a list of strings.",
        remedy='`files = ["README.md", "eval/questions.yaml"]` — paths relative to the KB.',
    )
    if not isinstance(declared, list):
        raise shape

    entries: list[str] = []
    for item in cast(list[object], declared):
        if not isinstance(item, str):
            raise shape
        entries.append(item)

    for entry in entries:
        if not entry or Path(entry).is_absolute():
            raise TemplateError(
                f"template {name} declares {entry!r}, which is not a relative path.",
                remedy="Every `files` entry is relative to the KB root.",
            )
        if VERSIONS_DIR in Path(entry).parts:
            raise TemplateError(
                f"template {name} declares {entry!r}, which names the version archive.",
                remedy=(
                    f"A template cannot copy anything out of {VERSIONS_DIR}/. What is archived "
                    "there is the frozen content of a released version, kept so `pnk upgrade` can "
                    "say what a recorded reference meant — never content to stamp into a KB."
                ),
            )
    return tuple(entries)


def copy_extras(name: str, target: Path) -> tuple[list[Path], list[Path]]:
    """Copy everything a KB should own: the template's README and its starter golden set.

    Returns `(written, adopted)` — the second being files that were **already there and left
    exactly as they are**. A directory worth adopting usually has a `README.md` already, and it is
    the user's; replacing it with a template's would be destroying the thing they wrote to make
    room for boilerplate.

    **Every entry is checked before any entry is written.** A template whose second declaration
    escapes would otherwise leave the first one written into a KB that then fails to be created —
    the partial state `pnk init` has no way to describe and no user has a reason to expect.

    **A template is packaged data, which is not the same as trusted data.** `pnk init --template`
    names whatever is installed, and that can have arrived from anywhere, so the declaration is
    checked against the target it will actually be written into rather than assumed well-formed.
    """
    root = _root(name)
    anchor = target.resolve()
    entries = declared_files(name)

    for relative in entries:
        try:
            inside = lands_inside(anchor, target, relative)
        except (ValueError, OSError) as exc:
            raise TemplateError(
                f"template {name} declares {relative!r}, which cannot be written: {exc}",
                remedy="Correct the template's `files`.",
            ) from exc
        if not inside:
            raise TemplateError(
                f"template {name} declares {relative!r}, which writes outside the KB.",
                remedy=(
                    "Every `files` entry must land inside the KB being created. An entry that "
                    "walks out writes into a directory the user never pointed pinakes at."
                ),
            )
        # **The source side of the same question, and it is a second layer rather than the same one
        # twice.** The check above stops an entry *writing* outside the KB; this one stops it
        # *reading* outside the template. A symlinked directory in the template tree points wherever
        # it likes on the machine, and the file it names would be copied **into** the KB — which for
        # a KB that is then committed and published is the more expensive direction of the two.
        # Neither layer catches the other's case: an escaping destination lands inside the template,
        # and an escaping source lands inside the target.
        #
        # Guarded on `Path` because `importlib.resources` hands back a `Traversable`, which for a
        # zip-imported package has no symlinks to follow and no `resolve()` to follow them with. A
        # wheel installs unpacked, so the real path is the one users get.
        if isinstance(root, Path) and not lands_inside(root.resolve(), root, relative):
            raise TemplateError(
                f"template {name} declares {relative!r}, which reads outside the template.",
                remedy=(
                    "Every `files` entry must name a file inside the template's own directory. An "
                    "entry that walks out copies something the template does not own into the KB."
                ),
            )

    written: list[Path] = []
    adopted: list[Path] = []
    for relative in entries:
        source = root
        for part in Path(relative).parts:
            source = source.joinpath(part)
        if not source.is_file():
            continue
        destination = target / relative
        if destination.exists():
            adopted.append(destination)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(destination)
    return written, adopted
