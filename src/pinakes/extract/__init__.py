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
import importlib.util
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pinakes.errors import BackendUnknownError, ExtractorMissingError

PYPDFIUM2 = "pypdfium2"
CLAUDE_VISION = "claude-vision"
FAKE = "fake"

# `(module, extra)` per backend, named once and read by both the lazy factory and the registry
# entry. Two literals would be two places for the extra to drift from the one a user is told to
# install.
_PYPDFIUM2_REQUIRES = ("pypdfium2", "pdf")
_CLAUDE_VISION_REQUIRES = ("anthropic", "claude")


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
type FingerprintInputs = Callable[[str | None], Mapping[str, str]]
"""Takes `[extraction] model`, because for a paid backend the model **is** part of what produced
the text: without it, changing `model` would silently reuse a cache entry a different model wrote
(plans/20260727_1543-v0.2.md, I7b). Free backends ignore it — `pypdfium2` has no model — and it
stays a plain
string so this is still client-free."""


@dataclass(frozen=True, slots=True)
class ExtractorEntry:
    load: ExtractorFactory
    fingerprint_inputs: FingerprintInputs
    paid: bool = False
    """Whether this backend can spend money (§5's boundary) — declared at registration, never
    derived from importing the client, so I5's per-document coherence check can tell a free
    mismatch (refuse) from a paid one (warn and mark) without ever loading `anthropic`."""
    requires: tuple[str, str] | None = None
    """`(module, extra)` this backend needs, or `None` when it needs nothing (`fake`). Declared
    here so `is_backend_installed` can answer "is it available?" through `importlib.util.find_spec`
    — which, for a top-level module, adds nothing to `sys.modules`. `pnk doctor` reports a paid
    backend's availability on every run, and doing that by *loading* the backend would import
    `anthropic` on the free path (I7a gate 4). The factory below reads the same tuple, so the
    module name a missing-extra error reports cannot drift from the one probed here."""


_REGISTRY: dict[str, ExtractorEntry] = {}


def register_extractor(name: str, entry: ExtractorEntry) -> None:
    _REGISTRY[name] = entry


def unregister_extractor(name: str) -> None:
    """`register_extractor`'s counterpart — for tests that register a temporary backend and must
    remove it again, without reaching into `_REGISTRY` directly from outside this module."""
    del _REGISTRY[name]


def registered_entry(name: str) -> ExtractorEntry:
    """The registered entry itself — for a test that swaps one out and must put it *back*.

    `unregister_extractor` deletes; there is no undo for a name the package registered at import,
    and a test that deletes one poisons every later test in the session (I7b review, pass 6).
    """
    return _entry(name)


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


def is_paid_backend(name: str) -> bool:
    """Registry metadata only — never imports the backend it describes."""
    return _entry(name).paid


def backend_requirement(name: str) -> tuple[str, str] | None:
    """The `(module, extra)` this backend needs, or `None` if it needs nothing."""
    return _entry(name).requires


def is_backend_installed(name: str) -> bool:
    """Whether the backend's library is importable — **without importing it**.

    `importlib.util.find_spec` locates a top-level module through the path finders and returns its
    spec; it does not execute the module and adds nothing to `sys.modules`. That is what lets
    `pnk doctor` report `claude-vision`'s availability on a KB configured for it while still
    satisfying I7a's gate 4 ("after a full free-path run, `anthropic` is not in `sys.modules`").
    Loading the extractor to find out — which is what doctor did before I7a — imported the paid
    client on a command that can never spend.

    A backend needing nothing is always installed. `find_spec` raises `ModuleNotFoundError` when a
    *parent* package is missing and `ValueError` for a module with no spec; both mean "not usable
    here", so both answer `False` rather than escaping as a traceback from a health check.
    """
    requires = _entry(name).requires
    if requires is None:
        return True
    module, _extra = requires
    try:
        return importlib.util.find_spec(module) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def paid_backend_names() -> frozenset[str]:
    return frozenset(name for name in _REGISTRY if _REGISTRY[name].paid)


def fingerprint_inputs(name: str, model: str | None = None) -> Mapping[str, str]:
    """The backend's declared inputs — never imports, so §4.4 can call this on every query."""
    return _entry(name).fingerprint_inputs(model)


def fingerprint(name: str, model: str | None = None) -> str:
    """Hash a backend's inputs with one shared pure function, never a per-backend formula."""
    canonical = json.dumps(
        dict(fingerprint_inputs(name, model)), sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def installed_version(distribution: str) -> str:
    """A distribution's version, or `"not installed"`. Public because `extract/claude.py` builds
    its own fingerprint inputs and needs the same answer, spelled the same way."""
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
    _import(*_PYPDFIUM2_REQUIRES, PYPDFIUM2)
    from pinakes.extract.pdfium import Pypdfium2Extractor

    return Pypdfium2Extractor()


def _pypdfium2_fingerprint_inputs(_model: str | None = None) -> Mapping[str, str]:
    """Deliberately omits pypdfium2's bundled PDFium *build* number — see `pdfium.py`'s own
    docstring for why: it exists only as an attribute of the imported module, and this function
    must never import the backend it describes (`test_fingerprint_inputs_never_import_the_backend`,
    I1), since §4.4 calls it on every query, not only at sync."""
    from pinakes.extract.floors import load_floors
    from pinakes.extract.layout import LAYOUT_VERSION

    floors = load_floors()
    return {
        "backend": PYPDFIUM2,
        "pypdfium2_version": installed_version("pypdfium2"),
        "layout_version": str(LAYOUT_VERSION),
        "running_head_threshold": str(floors.running_head_threshold),
    }


def _load_claude_vision() -> Extractor:
    """Build the paid backend. The `anthropic` probe stays here — the adapter itself imports the
    client lazily, so without this check a missing `[claude]` extra would surface as an
    `ImportError` from deep inside a transport rather than as the exact `uv add` line."""
    _import(*_CLAUDE_VISION_REQUIRES, CLAUDE_VISION)
    from pinakes.extract.claude import ClaudeVisionExtractor

    return ClaudeVisionExtractor()


def _claude_vision_fingerprint_inputs(model: str | None = None) -> Mapping[str, str]:
    """Deferred to the adapter, which owns the versions that actually shape its output — and
    imported lazily *here* rather than at module scope, because `claude.py` imports this module
    (for `ExtractedText`) and a top-level import would close the cycle.

    Still client-free: nothing on this path touches `anthropic`, which is what lets §4.4 hash a
    paid backend's fingerprint on every query without importing a paid client (I7a, gate 4).
    """
    from pinakes.extract.claude import fingerprint_inputs as claude_fingerprint_inputs

    return claude_fingerprint_inputs(model)


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


def _fake_fingerprint_inputs(_model: str | None = None) -> Mapping[str, str]:
    return {"backend": FAKE}


register_extractor(
    PYPDFIUM2,
    ExtractorEntry(_load_pypdfium2, _pypdfium2_fingerprint_inputs, requires=_PYPDFIUM2_REQUIRES),
)
register_extractor(
    CLAUDE_VISION,
    ExtractorEntry(
        _load_claude_vision,
        _claude_vision_fingerprint_inputs,
        paid=True,
        requires=_CLAUDE_VISION_REQUIRES,
    ),
)
register_extractor(FAKE, ExtractorEntry(_load_fake, _fake_fingerprint_inputs))
