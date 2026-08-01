"""`pinakes.toml` — the manifest, and how a KB root is found.

The manifest is **user-owned**, like `docs/`. Nothing in pinakes rewrites it after `pnk init`, so
this module only ever reads. Validation is strict in both directions: a missing required key fails,
and so does an unknown one (docs/DESIGN.md §2.1).

Cross-key invariants are checked here rather than at the point of use, because a manifest that
cannot produce sane behaviour should fail when it is read, not three commands later:

* `final_k <= fusion_top_k <= candidates_per_source` — the pipeline narrows at every stage (§4.1);
  a wider later stage cannot invent candidates the earlier one discarded.
* `confirm_above_eur <= per_operation_eur` — the confirmation prompt is unreachable otherwise, the
  exact defect design pass 3 split those fields to fix (§5).
* `overlap < max_tokens` — otherwise every chunk contains the previous one entire.
* `[retrieval.confidence]` requires `fitted_for`: thresholds fitted against a different reranker are
  not thresholds, and §4.2 would rather report `unknown` than a number it cannot justify.

**One check runs before all of that**: `[kb] requires_pinakes`, in a pre-pass over the raw TOML
(G4). Strictness means an unknown key is a hard error, so a manifest written by a newer pinakes
fails on the first key this build has never heard of — and tells the user they made a typo when
their actual problem is an out-of-date pinakes. Reading the compatibility floor *before* the strict
validator is the only ordering in which that field can do its job; after it, the parse has already
died and the good error is unreachable (docs/KB-UPDATES.md §7).
"""

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pinakes import __version__
from pinakes._toml import ROOT_NAME, Table
from pinakes.errors import InvalidIdError, ManifestError, NoKbFoundError
from pinakes.extract import registered_extractors
from pinakes.graph.traverse import DEFAULT_ADJACENT_K, MAX_ADJACENT_K
from pinakes.ids import KbId, parse_kb_id

MANIFEST_NAME = "pinakes.toml"
STATE_DIR = ".pinakes"
TIMESTAMP_FORMAT = "%Y%m%d %H:%M"

FUSION_STRATEGIES = ("rrf",)
RERANK_MODES = ("local", "none")
VECTOR_TIERS = ("auto", "numpy", "sqlite-vec")
CHUNK_STRATEGIES = ("structural",)
ON_EXCEED = ("abort", "partial")
EXTRACTION_BACKEND_DEFAULT = "pypdfium2"
EXTRACTION_MODEL_DEFAULT = "claude-opus-5"


@dataclass(frozen=True, slots=True)
class KbSection:
    name: str
    id: KbId
    template: str | None
    created: str | None


@dataclass(frozen=True, slots=True)
class SourcesSection:
    roots: tuple[str, ...]
    include: tuple[str, ...]
    exclude: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingSection:
    provider: str
    model: str
    dim: int
    revision: str | None


@dataclass(frozen=True, slots=True)
class ExtractionSection:
    """`backend` names a registry entry (extract/__init__.py); `model` is paid-backend-only."""

    backend: str
    model: str


@dataclass(frozen=True, slots=True)
class ChunkingSection:
    strategy: str
    max_tokens: int
    overlap: int


@dataclass(frozen=True, slots=True)
class ConfidenceSection:
    """Thresholds fitted against a golden set, and the reranker they were fitted for (§4.2)."""

    fitted_for: str
    low_below: float
    high_above: float


@dataclass(frozen=True, slots=True)
class RetrievalSection:
    candidates_per_source: int
    fusion: str
    fusion_top_k: int
    final_k: int
    rerank: str
    vector_tier: str
    adjacent_k: int
    confidence: ConfidenceSection | None


@dataclass(frozen=True, slots=True)
class RerankSection:
    provider: str
    model: str
    revision: str | None


@dataclass(frozen=True, slots=True)
class BudgetSection:
    """Parsed and validated from v0.1; the caps are consumed by `budget.reserve` from I6a, the
    ledger and `pnk ask --deep` itself still land later (I6b, then the deep release).

    All four caps are `Decimal`, not `float` (I6a): a reservation compared against a
    float-derived cap is a representation error wearing a different hat, and the boundary tests
    this increment adds assert exact equality at the cent.
    """

    confirm_above_eur: Decimal
    per_operation_eur: Decimal
    daily_eur: Decimal
    monthly_eur: Decimal
    max_price_age_days: int
    timezone: str
    on_exceed: str


@dataclass(frozen=True, slots=True)
class LinkedKb:
    name: str
    id: KbId
    path: str


@dataclass(frozen=True, slots=True)
class Manifest:
    root: Path
    kb: KbSection
    sources: SourcesSection
    embedding: EmbeddingSection
    extraction: ExtractionSection
    chunking: ChunkingSection
    retrieval: RetrievalSection
    rerank: RerankSection
    budget: BudgetSection
    links: tuple[LinkedKb, ...]

    @property
    def path(self) -> Path:
        return self.root / MANIFEST_NAME

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIR

    @property
    def index_path(self) -> Path:
        return self.state_dir / "index.db"

    @property
    def extract_cache_dir(self) -> Path:
        return self.state_dir / "cache" / "extract"

    def linked_kb(self, alias: str) -> LinkedKb | None:
        return next((linked for linked in self.links if linked.name == alias), None)


def find_kb_root(start: Path | None = None) -> Path:
    """Walk up from `start` to the nearest directory holding a `pinakes.toml`.

    Git-style discovery: a command run three directories deep inside a KB still means that KB.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    raise NoKbFoundError(current)


def load(root: Path) -> Manifest:
    """Read and validate `<root>/pinakes.toml`."""
    path = root / MANIFEST_NAME
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ManifestError(path, table=None, message=f"cannot be read: {exc.strerror}") from exc

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ManifestError(path, table=None, message="is not valid UTF-8") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(path, table=None, message=f"is not valid TOML: {exc}") from exc

    # The pre-pass, and its position in this function is the whole feature (G4). Every line below
    # this one can fail on a key a newer pinakes introduced; this one runs first so the failure can
    # say *why* instead of blaming a typo.
    _check_required_version(data, path)

    root_table = Table(data, name=ROOT_NAME, source=path)
    manifest = Manifest(
        root=root.resolve(),
        kb=_kb(root_table, path),
        sources=_sources(root_table, path),
        embedding=_embedding(root_table, path),
        extraction=_extraction(root_table, path),
        chunking=_chunking(root_table, path),
        retrieval=_retrieval(root_table, path),
        rerank=_rerank(root_table, path),
        budget=_budget(root_table, path),
        links=_links(root_table, path),
    )
    root_table.done()
    return manifest


def discover(start: Path | None = None) -> Manifest:
    return load(find_kb_root(start))


REQUIRES_PINAKES = "requires_pinakes"
REQUIRES_PREFIX = ">="


def _check_required_version(data: dict[str, Any], path: Path) -> None:
    """`[kb] requires_pinakes` — refuse a KB this build is too old to read (G4).

    Runs over the **raw** parsed TOML, before `Table` validates anything, because the field only
    earns its keep in the case where a later key is one this build has never heard of. Read
    afterwards it would be unreachable exactly when it is needed.

    **Its absence means compatible, never an error.** Every KB in existence lacks the field; a
    missing floor is "no floor declared", not a refusal — and this must stay true, or shipping the
    check would break every KB on the planet at once.

    A **floor only**, which is what the compatibility posture actually is: a KB may be opened by the
    pinakes that wrote it or a newer one, never an older one (docs/KB-UPDATES.md §4). There is no
    ceiling to express, so there is no specifier grammar to support and no dependency to take on for
    parsing one.

    This deliberately does not touch anything else in `data`: `[kb]` being absent or malformed is
    the strict validator's to report, in its own words, a few lines later. A pre-pass that started
    duplicating those errors would give two different messages for one mistake.
    """
    kb = data.get("kb")
    if not isinstance(kb, dict):
        return
    raw = cast(dict[str, Any], kb).get(REQUIRES_PINAKES)
    if raw is None:
        return

    if not isinstance(raw, str) or not raw.startswith(REQUIRES_PREFIX):
        raise ManifestError(
            path,
            table="kb",
            # The TOML type, never `repr`: a manifest saying `requires_pinakes = 2026-01-01` is
            # handed to us as a `datetime.date`, and telling its author they wrote
            # `datetime.date(2026, 1, 1)` describes Python rather than their file.
            message=(
                f'`{REQUIRES_PINAKES}` must be a string like `">={__version__}"`, '
                f"found {_toml_kind(raw)}"
            ),
            remedy=(
                "It states the oldest pinakes that can read this KB, and only a floor is "
                "supported — a KB is readable by the version that wrote it or any newer one. If "
                "this KB came from a newer pinakes that writes something richer here, upgrade "
                "pinakes rather than editing the file."
            ),
        )

    # No `.strip()`. It would accept `">= 0.9"`, a trailing newline, and — since `str.strip()`
    # is Unicode-aware — a non-breaking space, while this same function refuses non-ASCII *digits*
    # on the grounds that leniency there is a silently wrong comparison. One rule, not two.
    required = _version_tuple(raw.removeprefix(REQUIRES_PREFIX))
    if required is None:
        raise ManifestError(
            path,
            table="kb",
            message=(
                f"`{REQUIRES_PINAKES}` names a version this build cannot read: {raw!r} "
                f"(this build is {__version__})"
            ),
            remedy=(
                "A version is digits separated by dots, like `0.5` or `0.5.0`. A newer pinakes may "
                "write a form this one does not understand, in which case upgrading is the fix."
            ),
        )

    # **Not an `assert`.** `python -O` strips those, and this one guarded a `None` that reaches
    # `len()` two lines later — so under `-O` a `__version__` carrying a release-candidate or
    # `.dev` suffix turned every KB with this field into a `TypeError`, including ones whose floor
    # the build plainly meets. `tests/test_cli.py::test_version_is_set` pins the release format,
    # but this module must not fail catastrophically if that pin is ever relaxed.
    running = _version_tuple(__version__) or _version_tuple(_numeric_prefix(__version__))
    if running is None:
        # Nothing to compare against. A build whose own version is unparseable cannot honestly
        # refuse anyone else's KB, and refusing every KB is a far worse failure than skipping an
        # advisory check — so the floor goes unenforced rather than unopenable.
        return
    if _pad(required, len(running)) > _pad(running, len(required)):
        raise ManifestError(
            path,
            table="kb",
            message=(f"this KB requires pinakes {raw} (this build is {__version__})"),
            remedy=(
                "Upgrade pinakes — `uv add --upgrade pinakes` — or open the KB with the version "
                "that wrote it. Downgrading a KB is not supported: nothing rewrites a manifest a "
                "user owns (docs/KB-UPDATES.md §4)."
            ),
        )


#: Python refuses `int()` on a decimal string longer than `sys.int_info.default_max_str_digits`
#: (4300 since 3.11) and raises `ValueError`. A version component is never remotely this long, so
#: the bound costs nothing — and without it `">=" + "9" * 5000` passed the digit check below and
#: crashed `pnk doctor` with a traceback, on the code path this whole increment exists to make
#: diagnostic rather than baffling.
MAX_VERSION_DIGITS = 32


def _version_tuple(text: str) -> tuple[int, ...] | None:
    """`"1.2.3"` -> `(1, 2, 3)`; `None` for anything that is not a short dotted ASCII number.

    Total by construction: every rejection is a `None`, never an exception. Two guards, each for a
    case where Python is more permissive than a version format should be — `"٣".isdigit()` is
    `True` and `int("٣")` is `3`, so Eastern Arabic numerals would otherwise *compare* rather than
    be refused; and `int()` raises above 4300 digits rather than returning a large number.
    """
    parts = text.split(".")
    return (
        tuple(int(part) for part in parts)
        if parts
        and all(
            part.isascii() and part.isdigit() and len(part) <= MAX_VERSION_DIGITS for part in parts
        )
        else None
    )


def _numeric_prefix(version: str) -> str:
    """`"1.2.3rc1"` -> `"1.2.3"` — the dotted-numeric head of a PEP 440 version.

    Only ever applied to `pinakes.__version__`, never to a manifest's floor: a user writing
    `">=0.6.0rc1"` is told their version is unreadable, which is honest, while a *release candidate
    of pinakes itself* should still be able to compare against a floor rather than skip the check.
    """
    head: list[str] = []
    for part in version.split("."):
        digits = ""
        for character in part:
            if not (character.isascii() and character.isdigit()):
                break
            digits += character
        if not digits:
            break
        head.append(digits)
        if digits != part:  # `0rc1` — the numeric run ended inside this component
            break
    return ".".join(head)


#: TOML's own vocabulary for the types `tomllib` produces. `bool` before `int`, because it is a
#: subclass of it and `isinstance(True, int)` is `True`.
_TOML_KINDS: tuple[tuple[type, str], ...] = (
    (bool, "a boolean"),
    (int, "an integer"),
    (float, "a float"),
    (str, "a string"),
    (list, "an array"),
    (dict, "a table"),
)


def _toml_kind(value: object) -> str:
    """What a TOML author would call this, so an error names their file rather than our runtime."""
    for kind, name in _TOML_KINDS:
        if isinstance(value, kind):
            return name
    # Dates and times, which `tomllib` returns as `datetime` objects. Naming the TOML concept beats
    # `datetime.date(2026, 1, 1)`, which describes our runtime rather than the line they wrote.
    return "a date or time"


def _pad(version: tuple[int, ...], length: int) -> tuple[int, ...]:
    """`0.5` and `0.5.0` are the same version, and tuple comparison does not know that."""
    return version + (0,) * (length - len(version))


def _required_table(root_table: Table, name: str, path: Path) -> Table:
    table = root_table.table(name)
    if table is None:
        raise ManifestError(path, table=name, message="is missing")
    return table


def _optional_table(root_table: Table, name: str) -> Table | None:
    return root_table.table(name)


def _kb(root_table: Table, path: Path) -> KbSection:
    table = _required_table(root_table, "kb", path)
    name = table.string("name")
    raw_id = table.string("id")
    try:
        kb_id = parse_kb_id(raw_id)
    except InvalidIdError as exc:
        raise ManifestError(
            path,
            table="kb",
            message=f"`id` is not a ULID: {raw_id!r}",
            remedy=(
                "A KB's id is permanent and is the authority in every pnk:// URI — never edit or "
                "regenerate it (docs/DESIGN.md §2.2)."
            ),
        ) from exc

    created = table.optional_string("created")
    if created is not None:
        try:
            # A wall-clock stamp by design: the manifest records when the KB was created
            # in local time, so no timezone is attached or wanted here.
            datetime.strptime(created, TIMESTAMP_FORMAT)
        except ValueError as exc:
            raise ManifestError(
                path,
                table="kb",
                message=f"`created` must look like `20260725 09:14`, found {created!r}",
            ) from exc

    # Consumed, not read: `_check_required_version` has already acted on it, over the raw TOML,
    # before this function ran. Taking it here is what stops `done()` below rejecting it as an
    # unknown key — the field would otherwise be refused by the very strictness it exists to
    # explain, which is a self-defeating shape a test pins directly.
    table.optional_string(REQUIRES_PINAKES)

    section = KbSection(
        name=name, id=kb_id, template=table.optional_string("template"), created=created
    )
    table.done()
    return section


def _sources(root_table: Table, path: Path) -> SourcesSection:
    table = _required_table(root_table, "sources", path)
    section = SourcesSection(
        roots=table.strings("roots", default=("docs/",)),
        include=table.strings("include", default=("**/*.md", "**/*.txt")),
        exclude=table.strings("exclude", default=()),
    )
    table.done()
    if not section.roots:
        raise ManifestError(
            path, table="sources", message="`roots` must name at least one directory"
        )
    for entry in section.roots:
        if Path(entry).is_absolute() or ".." in Path(entry).parts:
            raise ManifestError(
                path,
                table="sources",
                message=f"`roots` entry {entry!r} must stay inside the KB",
                remedy="Roots are always relative to the KB root (docs/DESIGN.md §2.1).",
            )
    _check_include_containment(section, path)
    return section


def _check_include_containment(section: SourcesSection, path: Path) -> None:
    """`include` carries the same containment rule as `roots`, refused here rather than at the walk.

    **The rule was written in prose beside one of its two inputs and implemented for that one.** The
    `roots` loop above states that a source root must stay inside the KB; `include` was validated
    nowhere, and `sync.walk_sources` then relied on `candidate.relative_to(manifest.root)` — purely
    lexical, so `docs/../../outside/x.md` *is* relative to the root as a string. Measured on 0.7.0:
    `include = ["../../outside/*.md"]` indexed a file outside the KB, minted a **sidecar** beside
    it, and stored the document under a key that still contained the `..`.

    Writing outside the KB is the part that makes this a defect rather than a foot-gun, and
    "it is the user's own configuration" does not survive contact with the fact that `pinakes.toml`
    is **committed and shared**: clone someone's KB, run `pnk sync`, and *their* `include` writes
    into *your* tree. So this is a hard error at load, matching the `roots` precedent — the manifest
    is the user's own, unlike the partner manifests `linkscan.sidecars_under` merely reports on.

    **The predicate is `linkscan`'s, copied rather than re-derived.** Four attempts there each got
    it wrong differently, and mirroring the survivor is cheaper than repeating that sequence:

    * **Not "does the pattern contain `..`"** — `../notes/*.md` from `docs/` lands *inside* the KB
      and is a legitimate thing to write. What matters is where the path lands, never whether `..`
      occurs in it. Refusing a valid manifest is the same defect as accepting an invalid one.
    * **Not "resolve the fixed prefix before the first glob component"** — `*/../../../outside/**`
      has an empty prefix, so it passes unconditionally and runs its `..` inside `glob`.
    * **Not "resolve the whole path"** — with no glob component the probe *is* the file, and
      resolving it whole follows a final symlink, so `include = ["alpha.md"]` would be refused as an
      escape while `include = ["*.md"]`, naming the same file, is accepted. Parent resolved, final
      component left alone: `..` collapses and a symlinked *ancestor* is caught, while a symlinked
      *document* stays readable.
    * **`**` is dropped from the probe**, because it matches *zero* or more components while
      `Path.parts` counts it as one. Keeping it let a following `..` cancel it, so the probe landed
      one level below where the walk actually goes. Dropping it is exact, not merely conservative:
      every component `**` expands to is one a following `..` then pops, so the zero-expansion is
      the highest the walk can reach, and that is what must be inside the KB.

    **This is the bound, and it is not the whole guard.** A symlinked *directory* inside the KB is
    invisible to any static check — no `..`, no absolute path, and the escape only exists on disk —
    so `sync.walk_sources` keeps a per-candidate test as well. Neither layer covers the other.

    **`exclude` is deliberately not validated.** A pattern there can only fail to match, never widen
    the walk, so a `..` in it is harmless. The asymmetry is intentional rather than an oversight.
    """
    root = path.parent
    anchor = root.resolve()
    for pattern in section.include:
        if Path(pattern).is_absolute():
            # Its own message, because "reaches outside the KB" is false for an absolute path
            # naming this KB's own `docs/` — and `glob` refuses to walk one wherever it points,
            # which on 0.7.0 surfaced as a bare `NotImplementedError` traceback out of `cli.main`.
            raise ManifestError(
                path,
                table="sources",
                message=f"`include` pattern {pattern!r} is an absolute path",
                remedy=(
                    "Patterns are relative to each `roots` entry. Python's `glob` cannot walk an "
                    "absolute pattern at all, wherever it points."
                ),
            )
        for name in section.roots:
            base = (root / name).resolve()
            try:
                probe = base.joinpath(*(part for part in Path(pattern).parts if part != "**"))
                # The final component is resolved too when it is `..`, which leaving the last one
                # alone otherwise lets through: `Path("/kb/..").is_relative_to("/kb")` is *true*
                # lexically. The exemption exists so a symlinked document stays readable, and `..`
                # is never one.
                landing = (
                    probe.resolve() if probe.name == ".." else probe.parent.resolve() / probe.name
                )
            except (ValueError, OSError) as exc:
                # `resolve()` raises on an embedded NUL, which `tomllib` accepts.
                raise ManifestError(
                    path,
                    table="sources",
                    message=f"`include` pattern {pattern!r} cannot be walked: {exc}",
                    remedy="Remove or correct the pattern.",
                ) from exc
            if not landing.is_relative_to(anchor):
                raise ManifestError(
                    path,
                    table="sources",
                    message=(
                        f"`include` pattern {pattern!r} reaches outside the KB "
                        f"(under root {name!r})"
                    ),
                    remedy=(
                        "Patterns must stay inside the KB, like `roots`. A pattern that walks out "
                        "indexes files pinakes was never pointed at and writes sidecars beside "
                        "them."
                    ),
                ) from None
    return None


def _embedding(root_table: Table, path: Path) -> EmbeddingSection:
    table = _required_table(root_table, "embedding", path)
    section = EmbeddingSection(
        provider=table.string("provider"),
        model=table.string("model"),
        dim=table.integer("dim", minimum=1),
        revision=table.optional_string("revision"),
    )
    table.done()
    return section


def _extraction(root_table: Table, path: Path) -> ExtractionSection:
    table = _optional_table(root_table, "extraction")
    if table is None:
        return ExtractionSection(backend=EXTRACTION_BACKEND_DEFAULT, model=EXTRACTION_MODEL_DEFAULT)
    section = ExtractionSection(
        backend=table.choice(
            "backend", registered_extractors(), default=EXTRACTION_BACKEND_DEFAULT
        ),
        model=table.string_or("model", EXTRACTION_MODEL_DEFAULT),
    )
    table.done()
    return section


def _chunking(root_table: Table, path: Path) -> ChunkingSection:
    table = _optional_table(root_table, "chunking")
    if table is None:
        return ChunkingSection(strategy="structural", max_tokens=510, overlap=64)
    section = ChunkingSection(
        strategy=table.choice("strategy", CHUNK_STRATEGIES, default="structural"),
        max_tokens=table.integer("max_tokens", default=510, minimum=1),
        overlap=table.integer("overlap", default=64, minimum=0),
    )
    table.done()
    if section.overlap >= section.max_tokens:
        raise ManifestError(
            path,
            table="chunking",
            message=f"`overlap` ({section.overlap}) must be smaller than `max_tokens` "
            f"({section.max_tokens})",
            remedy="Otherwise every chunk contains the whole of the one before it.",
        )
    return section


def _retrieval(root_table: Table, path: Path) -> RetrievalSection:
    table = _optional_table(root_table, "retrieval")
    if table is None:
        return RetrievalSection(
            candidates_per_source=50,
            fusion="rrf",
            fusion_top_k=20,
            final_k=8,
            rerank="local",
            vector_tier="auto",
            adjacent_k=DEFAULT_ADJACENT_K,
            confidence=None,
        )
    confidence = _confidence(table, path)
    table.reject(
        "top_k", because="the pipeline has three separate widths — see docs/DESIGN.md §4.1"
    )
    section = RetrievalSection(
        candidates_per_source=table.integer("candidates_per_source", default=50, minimum=1),
        fusion=table.choice("fusion", FUSION_STRATEGIES, default="rrf"),
        fusion_top_k=table.integer("fusion_top_k", default=20, minimum=1),
        final_k=table.integer("final_k", default=8, minimum=1),
        rerank=table.choice("rerank", RERANK_MODES, default="local"),
        vector_tier=table.choice("vector_tier", VECTOR_TIERS, default="auto"),
        # Deliberately **not** stamped into the `notes` template, in this release or the next:
        # `_toml.py` hard-errors on an unknown key, so a manifest carrying `adjacent_k` cannot be
        # read by any pinakes built before it existed. `[kb] requires_pinakes` cannot help
        # retroactively either — an older build has no pre-pass and fails on that key itself — so
        # the key stays settable-but-unstamped until a release deliberately accepts the break.
        adjacent_k=table.integer(
            "adjacent_k", default=DEFAULT_ADJACENT_K, minimum=1, maximum=MAX_ADJACENT_K
        ),
        confidence=confidence,
    )
    table.done()
    if not section.final_k <= section.fusion_top_k <= section.candidates_per_source:
        raise ManifestError(
            path,
            table="retrieval",
            message=(
                f"widths must narrow: final_k ({section.final_k}) <= fusion_top_k "
                f"({section.fusion_top_k}) <= candidates_per_source "
                f"({section.candidates_per_source})"
            ),
            remedy="A later stage cannot return candidates an earlier stage discarded (§4.1).",
        )
    return section


def _confidence(retrieval: Table, path: Path) -> ConfidenceSection | None:
    table = retrieval.table("confidence")
    if table is None:
        return None
    fitted_for = table.optional_string("fitted_for")
    if fitted_for is None:
        raise ManifestError(
            path,
            table="retrieval.confidence",
            message="`fitted_for` is required whenever thresholds are present",
            remedy=(
                "Thresholds are only meaningful for the reranker they were fitted against; without "
                "`fitted_for` pinakes cannot tell whether they still apply, and §4.2 reports "
                "`unknown` rather than guessing."
            ),
        )
    section = ConfidenceSection(
        fitted_for=fitted_for,
        low_below=table.number("low_below"),
        high_above=table.number("high_above"),
    )
    table.done()
    if section.low_below > section.high_above:
        raise ManifestError(
            path,
            table="retrieval.confidence",
            message=(
                f"`low_below` ({section.low_below}) must not exceed `high_above` "
                f"({section.high_above})"
            ),
        )
    return section


def _rerank(root_table: Table, path: Path) -> RerankSection:
    table = _optional_table(root_table, "rerank")
    if table is None:
        return RerankSection(
            provider="sentence-transformers", model="BAAI/bge-reranker-base", revision=None
        )
    section = RerankSection(
        provider=table.string_or("provider", "sentence-transformers"),
        model=table.string_or("model", "BAAI/bge-reranker-base"),
        revision=table.optional_string("revision"),
    )
    table.done()
    return section


def _budget(root_table: Table, path: Path) -> BudgetSection:
    table = _optional_table(root_table, "budget")
    if table is None:
        return BudgetSection(
            confirm_above_eur=Decimal("0.01"),
            per_operation_eur=Decimal("0.05"),
            daily_eur=Decimal("1.00"),
            monthly_eur=Decimal("5.00"),
            max_price_age_days=30,
            timezone="UTC",
            on_exceed="abort",
        )
    section = BudgetSection(
        confirm_above_eur=table.decimal(
            "confirm_above_eur", default=Decimal("0.01"), minimum=Decimal("0")
        ),
        per_operation_eur=table.decimal(
            "per_operation_eur", default=Decimal("0.05"), minimum=Decimal("0")
        ),
        daily_eur=table.decimal("daily_eur", default=Decimal("1.00"), minimum=Decimal("0")),
        monthly_eur=table.decimal("monthly_eur", default=Decimal("5.00"), minimum=Decimal("0")),
        max_price_age_days=table.integer("max_price_age_days", default=30, minimum=1),
        timezone=table.string_or("timezone", "UTC"),
        on_exceed=table.choice("on_exceed", ON_EXCEED, default="abort"),
    )
    table.done()
    if section.confirm_above_eur > section.per_operation_eur:
        raise ManifestError(
            path,
            table="budget",
            message=(
                f"`confirm_above_eur` ({section.confirm_above_eur}) must not exceed "
                f"`per_operation_eur` ({section.per_operation_eur})"
            ),
            remedy=(
                "The confirmation prompt would be unreachable: the hard cap would abort before the "
                "prompt could ever fire (docs/DESIGN.md §5)."
            ),
        )
    try:
        ZoneInfo(section.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ManifestError(
            path,
            table="budget",
            message=f"`timezone` {section.timezone!r} is not a known IANA zone",
            remedy="Daily and monthly budget windows are computed in it, so it must be resolvable.",
        ) from exc
    return section


def _links(root_table: Table, path: Path) -> tuple[LinkedKb, ...]:
    links_table = _optional_table(root_table, "links")
    if links_table is None:
        return ()
    entries: list[LinkedKb] = []
    for table in links_table.tables("kb"):
        raw_id = table.string("id")
        try:
            kb_id = parse_kb_id(raw_id)
        except InvalidIdError as exc:
            raise ManifestError(
                path, table=table.name, message=f"`id` is not a ULID: {raw_id!r}"
            ) from exc
        entry = LinkedKb(
            name=table.string("name"),
            id=kb_id,
            path=table.string("path"),
        )
        table.done()
        entries.append(entry)
    links_table.done()
    _reject_duplicates(entries, path)
    return tuple(entries)


def _reject_duplicates(entries: Sequence[LinkedKb], path: Path) -> None:
    for field, values in (
        ("name", [entry.name for entry in entries]),
        ("id", [str(entry.id) for entry in entries]),
    ):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ManifestError(
                path,
                table="links.kb",
                message=f"duplicate {field}: {', '.join(duplicates)}",
                remedy="Each connected KB is listed once; an alias must resolve to one KB.",
            )
