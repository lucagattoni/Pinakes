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
"""

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pinakes._toml import ROOT_NAME, Table
from pinakes.errors import InvalidIdError, ManifestError, NoKbFoundError
from pinakes.extract import registered_extractors
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
    return section


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
