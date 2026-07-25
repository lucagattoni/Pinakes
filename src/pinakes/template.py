"""Templates — the blueprint a KB is stamped from (docs/DESIGN.md §6.1).

Templates version independently of the package, so upgrading `pinakes` never silently re-chunks
someone's corpus. They are packaged inside the wheel and read through `importlib.resources`, so
nothing depends on the source tree being present.
"""

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


@dataclass(frozen=True, slots=True)
class TemplateInfo:
    name: str
    version: str
    description: str

    @property
    def reference(self) -> str:
        """`notes@1.0` — what the manifest records, so a later `pnk upgrade` can diff it."""
        return f"{self.name}@{self.version}"


def _root(name: str) -> Traversable:
    try:
        root = resources.files(PACKAGE).joinpath(name)
    except ModuleNotFoundError as exc:  # pragma: no cover — packaging failure
        raise TemplateError(f"template package {PACKAGE} is missing.", remedy="Reinstall.") from exc
    if not root.is_dir():
        raise TemplateError(
            f"no template named {name!r}.",
            remedy=f"Available: {', '.join(available()) or '(none)'}.",
        )
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


def copy_extras(name: str, target: Path) -> list[Path]:
    """Copy everything a KB should own: the template's README and its starter golden set."""
    written: list[Path] = []
    root = _root(name)

    for relative in ("README.md", "eval/questions.yaml"):
        source = root
        for part in relative.split("/"):
            source = source.joinpath(part)
        if not source.is_file():
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(destination)
    return written
