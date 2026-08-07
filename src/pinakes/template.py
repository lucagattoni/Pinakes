"""Templates — the blueprint a KB is stamped from (docs/DESIGN.md §6.1).

Templates version independently of the package, so upgrading `pinakes` never silently re-chunks
someone's corpus. They are packaged inside the wheel and read through `importlib.resources`, so
nothing depends on the source tree being present.
"""

import re
import tomllib
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from jinja2 import StrictUndefined, Template

from pinakes.errors import TemplateError

PACKAGE = "pinakes.templates"
MANIFEST_TEMPLATE = "pinakes.toml.j2"
DEFAULT_TEMPLATE = "notes"
VERSIONS_DIR = "_versions"

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


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


def render_manifest(name: str, context: dict[str, Any]) -> str:
    """Render `pinakes.toml`. `StrictUndefined`: a missing variable fails here, not at read time."""
    source = _root(name).joinpath(MANIFEST_TEMPLATE).read_text(encoding="utf-8")
    return Template(source, undefined=StrictUndefined, keep_trailing_newline=True).render(**context)


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
    return Template(source, undefined=StrictUndefined, keep_trailing_newline=True).render(**context)


def copy_extras(name: str, target: Path) -> tuple[list[Path], list[Path]]:
    """Copy everything a KB should own: the template's README and its starter golden set.

    Returns `(written, adopted)` — the second being files that were **already there and left
    exactly as they are**. A directory worth adopting usually has a `README.md` already, and it is
    the user's; replacing it with a template's would be destroying the thing they wrote to make
    room for boilerplate.
    """
    written: list[Path] = []
    adopted: list[Path] = []
    root = _root(name)

    for relative in ("README.md", "eval/questions.yaml"):
        source = root
        for part in relative.split("/"):
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
