"""The extraction seam: one protocol, one result type, and an open registry of backends.

A backend turns a document into text; nothing downstream cares how. `Extractor.extract(path, ctx)`
is the whole contract, and `ExtractedText(text, page_spans, per_page_provenance)` is the only type
that crosses it - `RawPages` / `Block` / `CharSpan` (I3a) are the free backend's internal geometry,
not the seam, because the paid backend has no coordinates to put in them.

`ExtractionContext` carries what a call needs that a bare path cannot: the configured model, the
`--force` flag, and the accountant/ledger/staging-directory/page-resume machinery I6a-I7c add. It
is defined now, frozen, with every paid field defaulting to `None`, so the signature never has to
change again - only what a later increment threads through it does.

The registry is open and keyed on backend name, exactly like `embed.py`'s (the one structural call
of v0.1 worth repeating): a name maps to a factory function, imports happen lazily *inside* that
function, and a missing extra fails with the exact `uv add` line rather than an ImportError. Both
real backends are registered here as **stubs** - `pypdfium2` still checks its own import (so a
missing `[pdf]` extra is reported precisely) and then raises `ExtractionError` naming the increment
that implements it, and `claude-vision` does the same for `[claude]`/`anthropic`. Manifest
validation and `--extract` both check membership in this registry's key set and never import
anything (§4.4's per-document coherence check depends on that holding for the whole lifetime of the
project, not just today): an unknown backend is rejected before either extra could matter.

Fingerprint **inputs** - not a fingerprint method on the backend - live beside each registry entry,
as a client-free dict of version strings and constants. `fingerprint()` hashes that dict with one
shared pure function, so a per-document coherence check can ask "does this backend still match?"
without importing a paid client to answer it. What each backend's inputs actually contain is filled
in by the increment that can state them honestly: I3a/I3b add `LAYOUT_VERSION` and the fitted
running-head threshold to pypdfium2's; I7b states claude-vision's. Here, each is just its own name
plus whatever `importlib.metadata` can read about the installed library, so the mechanism is real
before either input list is complete.

The `fake` backend is a genuine `Extractor`, not a stub: it returns fixed, deliberately ugly text
(a repeated running head, double spaces, a hyphenated word split across a line) so later increments
can exercise chunking end to end without pypdfium2, `anthropic`, or a real document.
"""

import hashlib
import importlib.metadata
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pinakes.errors import BackendUnknownError, ExtractionError, ExtractorMissingError

PYPDFIUM2 = "pypdfium2"
CLAUDE_VISION = "claude-vision"
FAKE = "fake"


@dataclass(frozen=True, slots=True)
class ExtractionContext:
    """What an `Extractor` call needs beyond the path. Paid fields are `None` on the free path."""

    model: str | None = None
    force: bool = False
    accountant: object | None = None
    ledger: object | None = None
    staging_dir: Path | None = None
    resume_from_page: int | None = None


@dataclass(frozen=True, slots=True)
class ExtractedText:
    """The one type crossing the seam: text, its per-page spans, and per-page provenance."""

    text: str
    page_spans: tuple[tuple[int, int], ...]
    per_page_provenance: tuple[Mapping[str, str], ...] = ()


class Extractor(Protocol):
    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractedText: ...


type ExtractorFactory = Callable[[], Extractor]
type FingerprintInputs = Callable[[], Mapping[str, str]]


@dataclass(frozen=True, slots=True)
class ExtractorEntry:
    load: ExtractorFactory
    fingerprint_inputs: FingerprintInputs


_REGISTRY: dict[str, ExtractorEntry] = {}


def register_extractor(name: str, entry: ExtractorEntry) -> None:
    _REGISTRY[name] = entry


def registered_extractors() -> list[str]:
    return sorted(_REGISTRY)


def _entry(name: str) -> ExtractorEntry:
    found = _REGISTRY.get(name)
    if found is None:
        raise BackendUnknownError(name, known=registered_extractors())
    return found


def load_extractor(name: str) -> Extractor:
    """Build the registered extractor. Imports, if any, happen inside the factory, lazily."""
    return _entry(name).load()


def fingerprint_inputs(name: str) -> Mapping[str, str]:
    """The backend's declared inputs — never imports, so §4.4 can call this on every query."""
    return _entry(name).fingerprint_inputs()


def fingerprint(name: str) -> str:
    """Hash a backend's inputs with one shared pure function, never a per-backend formula."""
    canonical = json.dumps(dict(fingerprint_inputs(name)), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _installed_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _import(module: str, extra: str, name: str) -> Any:
    try:
        return __import__(module, fromlist=["_"])
    except ImportError as exc:
        raise ExtractorMissingError(name, extra=extra) from exc


def _load_pypdfium2() -> Extractor:
    _import("pypdfium2", "pdf", PYPDFIUM2)
    from pinakes.extract.pdfium import Pypdfium2Extractor

    return Pypdfium2Extractor()


def _pypdfium2_fingerprint_inputs() -> Mapping[str, str]:
    """Deliberately omits pypdfium2's bundled PDFium *build* number — see `pdfium.py`'s own
    docstring for why: it exists only as an attribute of the imported module, and this function
    must never import the backend it describes (`test_fingerprint_inputs_never_import_the_backend`,
    I1), since §4.4 calls it on every query, not only at sync."""
    from pinakes.extract.floors import load_floors
    from pinakes.extract.layout import LAYOUT_VERSION

    floors = load_floors()
    return {
        "backend": PYPDFIUM2,
        "pypdfium2_version": _installed_version("pypdfium2"),
        "layout_version": str(LAYOUT_VERSION),
        "running_head_threshold": str(floors.running_head_threshold),
    }


def _load_claude_vision() -> Extractor:
    _import("anthropic", "claude", CLAUDE_VISION)
    raise ExtractionError(
        "the claude-vision extractor lands in I7b.",
        remedy="See plans/v0.2.md for the build order.",
    )


def _claude_vision_fingerprint_inputs() -> Mapping[str, str]:
    return {"backend": CLAUDE_VISION, "anthropic_version": _installed_version("anthropic")}


_FAKE_PAGE_1 = (
    "Running Header\n\nThis  is a test page with  double spaces and a hyphen-\n"
    "ated word that continues on the next line.\n"
)
_FAKE_PAGE_2 = "Running Header\n\nA second page carries the same running head as the first.\n"


class _FakeExtractor:
    """Deterministic and deliberately ugly — a stand-in, not a mock (ground rules, rule 5)."""

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractedText:
        text = _FAKE_PAGE_1 + _FAKE_PAGE_2
        return ExtractedText(
            text=text,
            page_spans=((0, len(_FAKE_PAGE_1)), (len(_FAKE_PAGE_1), len(text))),
        )


def _load_fake() -> Extractor:
    return _FakeExtractor()


def _fake_fingerprint_inputs() -> Mapping[str, str]:
    return {"backend": FAKE}


register_extractor(PYPDFIUM2, ExtractorEntry(_load_pypdfium2, _pypdfium2_fingerprint_inputs))
register_extractor(
    CLAUDE_VISION, ExtractorEntry(_load_claude_vision, _claude_vision_fingerprint_inputs)
)
register_extractor(FAKE, ExtractorEntry(_load_fake, _fake_fingerprint_inputs))
