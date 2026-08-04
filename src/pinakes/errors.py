"""Error types.

Every user-facing failure derives from `PinakesError` and carries a **remedy**: the message says
what went wrong, the remedy says what to do about it. The CLI prints both, so no failure path can
leave the user knowing something broke but not what to try next — which is the difference between
a tool that stops and a tool that strands you.

Subclasses are added by the increment that first raises them; an empty hierarchy invented up front
would be a guess about failures that do not exist yet.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path


class PinakesError(Exception):
    """Base class for every failure Pinakes reports to a human."""

    def __init__(self, message: str, *, remedy: str) -> None:
        super().__init__(message)
        self.message = message
        self.remedy = remedy

    def __reduce__(self) -> tuple[object, ...]:
        """Rebuild through `PinakesError`, not `type(self)`.

        `Exception.__reduce__` replays `self.args` through the subclass constructor, and subclasses
        here take their own arguments (a command name, a path) rather than `(message, remedy)` — so
        the default would raise `TypeError` while unpickling. Anything that moves an exception
        across a process boundary (pytest-xdist, multiprocessing) hits this, and a checker that
        crashes while *reporting* a failure is worse than the failure.
        """
        return (_rebuild, (type(self), self.message, self.remedy))


class NotImplementedYetError(PinakesError):
    """A command in the CLI surface whose implementation has not landed yet.

    Exists so the surface can be complete before the behaviour is: `pnk <cmd>` must fail loudly
    rather than exit 0 and imply it did something.
    """

    def __init__(self, command: str, *, increment: str) -> None:
        super().__init__(
            f"`pnk {command}` is not implemented yet.",
            remedy=(
                f"It lands in increment {increment} — see plans/20260725_1317-v0.1.md for the "
                f"build order "
                f"and docs/DESIGN.md for the specification."
            ),
        )
        self.command = command
        self.increment = increment


class InvalidIdError(PinakesError):
    """A string that should have been a ULID is not one."""

    def __init__(self, raw: str, *, kind: str) -> None:
        super().__init__(
            f"{raw!r} is not a valid {kind} ULID.",
            remedy=(
                "IDs are 26-character uppercase Crockford base32, minted by pinakes and never "
                "edited by hand. If this came from a sidecar, restore the original ID — "
                "renumbering breaks every inbound link (docs/DESIGN.md §2.2)."
            ),
        )
        self.raw = raw
        self.kind = kind


class InvalidUriError(PinakesError):
    """A `pnk://` link is malformed."""

    def __init__(self, raw: str, *, reason: str) -> None:
        super().__init__(
            f"{raw!r} is not a valid pnk:// URI: {reason}.",
            remedy="The form is pnk://<kb-ulid>/<doc-ulid> — see docs/DESIGN.md §2.2.",
        )
        self.raw = raw
        self.reason = reason


class ManifestError(PinakesError):
    """`pinakes.toml` is missing, unreadable, or says something that cannot be honoured."""

    def __init__(
        self, path: Path, *, table: str | None, message: str, remedy: str | None = None
    ) -> None:
        location = f"{path}" if table in (None, "<root>") else f"{path} [{table}]"
        super().__init__(
            f"{location}: {message}",
            remedy=remedy or "See docs/DESIGN.md §2.1 for the manifest schema.",
        )
        self.path = path
        self.table = table


class NoKbFoundError(PinakesError):
    """No `pinakes.toml` in this directory or any parent."""

    def __init__(self, start: Path) -> None:
        super().__init__(
            f"no pinakes.toml found in {start} or any parent directory.",
            remedy=(
                "Run this inside a KB, pass --kb <path>, or create one with `pnk init <name>`."
            ),
        )
        self.start = start


class StoreError(PinakesError):
    """The index cannot be used as asked."""


class IndexSchemaError(PinakesError):
    """The index was built by a different schema version. There is no migration, by design."""

    def __init__(self, path: Path, *, found: str | None, expected: int) -> None:
        super().__init__(
            f"{path} has schema version {found or 'unknown'}, but this pinakes expects {expected}.",
            remedy=(
                "Run `pnk sync --rebuild`. The index is derived state: rebuilding is free and "
                "always safe, which is why this design carries no migration machinery "
                "(docs/DESIGN.md §3)."
            ),
        )
        self.path = path
        self.found = found
        self.expected = expected


class SidecarError(PinakesError):
    """A `.pnk.yaml` sidecar is missing something, or says something that cannot be honoured."""

    def __init__(self, path: Path, message: str, *, remedy: str | None = None) -> None:
        super().__init__(
            f"{path} {message}.",
            remedy=remedy or "See docs/DESIGN.md §2.2 for the sidecar format.",
        )
        self.path = path


class ChunkingError(PinakesError):
    """A document cannot be chunked as configured."""


class EmbeddingError(PinakesError):
    """A backend cannot do what the manifest asks."""


class BackendMissingError(PinakesError):
    """The backend a manifest names is not installed. A supported state, not a broken one (§4.5)."""

    def __init__(self, provider: str, *, extra: str) -> None:
        super().__init__(
            f"the `{provider}` backend is not installed.",
            remedy=(
                f'Install it with `uv add "pinakes[{extra}]"`. A core-only install can index and '
                f"search nothing that needs embeddings — that is expected, not a fault."
            ),
        )
        self.provider = provider
        self.extra = extra


class BackendUnknownError(PinakesError):
    """The manifest names a provider nothing has registered."""

    def __init__(self, provider: str, *, known: list[str]) -> None:
        super().__init__(
            f"no backend is registered for provider {provider!r}.",
            remedy=f"Known providers: {', '.join(known) or '(none)'}.",
        )
        self.provider = provider
        self.known = known


class DuplicateIdsError(PinakesError):
    """One document id claimed by more than one sidecar.

    Fatal by design: renumbering would break inbound links that were perfectly fine, and there is
    no way to tell which document the id was originally minted for (docs/DESIGN.md §6.4).
    """

    def __init__(self, duplicates: Mapping[str, list[str]]) -> None:
        listing = "; ".join(
            f"{doc_id} claimed by {', '.join(paths)}"
            for doc_id, paths in sorted(duplicates.items())
        )
        super().__init__(
            f"the same document id appears in more than one sidecar: {listing}.",
            remedy=(
                "Decide which document owns the id and give the other a new sidecar (delete "
                "its `id` and let sync mint one). Never edit the id of a document other KBs "
                "link to."
            ),
        )
        self.duplicates = dict(duplicates)


class LockError(PinakesError):
    """The sync lock cannot be taken safely."""


class SyncError(PinakesError):
    """A sync cannot proceed."""


class CoherenceError(PinakesError):
    """The index was built by a different model than the manifest now names (§4.4)."""

    def __init__(self, differences: Mapping[str, tuple[str, str]]) -> None:
        listing = "; ".join(
            f"{key}: index has {found!r}, manifest says {wanted!r}"
            for key, (found, wanted) in sorted(differences.items())
        )
        super().__init__(
            f"the index does not match the configured model — {listing}.",
            remedy=(
                "Run `pnk sync --rebuild`. Embeddings are meaningless across models: a KB that "
                "silently returned results here would be returning garbage."
            ),
        )
        self.differences = dict(differences)


class IncompleteIndexError(PinakesError):
    """The index carries none of the embedding identity keys yet — a first sync started and did
    not finish (`sync.py` writes them only after the document loop completes), not a model that
    changed under a completed index. Distinct from `CoherenceError` on purpose: the two share a
    symptom — the identity keys do not match what the manifest expects — but not a cause, and
    `--rebuild` on this one discards every embedding an interrupted sync already wrote.
    """

    def __init__(self) -> None:
        super().__init__(
            "the index has no embedding identity recorded yet — an earlier `pnk sync` did not "
            "finish.",
            remedy=(
                "Run `pnk sync`. It resumes incrementally and keeps every embedding already "
                "written — no rebuild is needed, unlike a genuine model mismatch."
            ),
        )


class ExtractionCoherenceError(PinakesError):
    """A *free*-backend extraction is stale (§4.4, decision 13). A paid mismatch only WARNs and
    marks affected results `stale_extraction` — extracted text does not go meaningless the way an
    embedding under the wrong model does, and a free re-extraction costs nothing to just run — so
    only the free direction refuses the whole query.
    """

    def __init__(
        self,
        backend: str,
        *,
        stored_fingerprint: str,
        current_fingerprint: str,
        paths: Sequence[str],
    ) -> None:
        sample = ", ".join(sorted(paths)[:3])
        more = len(paths) - 3
        super().__init__(
            f"{len(paths)} document(s) extracted with `{backend}` (fingerprint "
            f"{stored_fingerprint}) no longer match its current fingerprint "
            f"({current_fingerprint}): {sample}" + (f" and {more} more" if more > 0 else ""),
            remedy="Run `pnk sync --rebuild` to re-extract with the current backend.",
        )
        self.backend = backend
        self.stored_fingerprint = stored_fingerprint
        self.current_fingerprint = current_fingerprint
        self.paths = tuple(paths)


class ExtractorMissingError(PinakesError):
    """The library a registered extractor needs is not installed. A supported state (§4.5)."""

    def __init__(self, provider: str, *, extra: str) -> None:
        super().__init__(
            f"the `{provider}` extractor is not installed.",
            remedy=(
                f'Install it with `uv add "pinakes[{extra}]"`. A core-only install can index '
                f"everything except PDFs — that is expected, not a fault."
            ),
        )
        self.provider = provider
        self.extra = extra


class ApiKeyMissingError(PinakesError):
    """The paid extractor has no key, and Pinakes will not go looking for one.

    Named for `PINAKES_ANTHROPIC_API_KEY` rather than the SDK's `ANTHROPIC_API_KEY` deliberately:
    the SDK reads its own variable out of whatever environment it happens to be in, so a key
    exported for an unrelated tool would let a paid call proceed that nobody asked for. Supplying
    the key has to be an act aimed at *this* tool (DESIGN §5, `CLAUDE.md`).
    """

    def __init__(self) -> None:
        super().__init__(
            "the `claude-vision` extractor has no API key.",
            remedy=(
                "Set `PINAKES_ANTHROPIC_API_KEY` for this command only — "
                "`uv run --env-file .env pnk ...` with the key in `.env`. pinakes deliberately "
                "ignores `ANTHROPIC_API_KEY`: a tool that can spend must not pick up a credential "
                "from an environment nobody pointed at it."
            ),
        )


class ExtractionError(PinakesError):
    """A registered extractor could not produce text from this document."""


class PaidExtractionRequiredError(PinakesError):
    """A paid-extracted document's content changed under a free-effective run (I5, decision 14).

    Neither silently re-extracting with the downgraded free backend nor silently leaving the now
    stale text indexed is honest; the remedy is a deliberate, paid re-extraction. The content-hash
    comparison this raises on comes from the sidecar's own recorded `provenance.extraction.
    content_hash`, not from any cache or index lookup — so this fires the same way whether the
    cache is warm, cold, or the KB was just cloned.
    """

    def __init__(self, path: str, *, recorded_backend: str) -> None:
        super().__init__(
            f"{path} was extracted with the paid `{recorded_backend}` backend, but its content "
            "has changed since.",
            remedy=f"Run `pnk sync --extract={recorded_backend}` to pay for a fresh extraction, "
            "matching what the sidecar already records.",
        )
        self.path = path
        self.recorded_backend = recorded_backend


class PaidExtractionUnavailableError(PinakesError):
    """A paid-extracted document's content is *unchanged* (the sidecar's own recorded content_hash
    still matches), but the extracted text itself is not available anywhere on this machine: no
    cache entry, and this exact document was never indexed here before (I5) — the common case is
    a fresh clone of a KB whose paid PDFs were extracted on a different machine, or a rename
    reaching this document for the first time after `--clear-cache`.

    Distinct from `PaidExtractionRequiredError`: nothing about the file changed, so silently
    treating this as "requires paying again for a changed file" would be a false claim. This is
    an honest "cannot re-derive it for free from what's here" instead.
    """

    def __init__(self, path: str, *, recorded_backend: str) -> None:
        super().__init__(
            f"{path} was extracted with the paid `{recorded_backend}` backend, and its content is "
            "unchanged, but that extraction's text is not available on this machine (no cache "
            "entry, and it has not been indexed here before).",
            remedy=f"Run `pnk sync --extract={recorded_backend}` to pay for a fresh extraction — "
            "or sync once on a machine or clone that already has it cached or indexed, if one "
            "exists.",
        )
        self.path = path
        self.recorded_backend = recorded_backend


class FloorsMissingError(PinakesError):
    """`extract/floors.toml` is missing or unreadable. Never a single document's fault — every
    pypdfium2 extraction needs the fitted running-head threshold *T* it carries, so this is an
    environment/packaging problem, raised the same way for every document rather than isolated to
    one (`docs/RETROSPECTIVES.md`, I3b)."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(
            f"pinakes.extract's floors.toml is missing or unreadable ({reason}).",
            remedy=(
                "This ships as package data; reinstall `pinakes[pdf]` or rebuild the wheel "
                "(`uv build`). From a source checkout, `make pdf-eval` fits and writes it."
            ),
        )
        self.reason = reason


class TemplateError(PinakesError):
    """A template is missing or unusable."""


class InitError(PinakesError):
    """A KB cannot be created here."""


class HookError(PinakesError):
    """Git hooks cannot be installed here."""


class TraversalError(PinakesError):
    """A traversal was asked for something it cannot mean — an unknown `direction`, so far.

    Not a `ServeError`: both `pnk links` and `pinakes_links` reach the same provider, and the error
    belongs to the traversal rather than to whichever surface asked for it.
    """


class ServeError(PinakesError):
    """The MCP server cannot answer as asked."""


class EvalError(PinakesError):
    """The golden set or its baseline cannot be used."""


class CalibrationError(PinakesError):
    """Thresholds cannot be fitted from this golden set."""


class PricesMissingError(PinakesError):
    """`budget/prices.toml` is missing or unreadable (I6a) — ships as package data for the same
    reason `FloorsMissingError` exists: a file only present in the source tree is invisible to an
    installed wheel, and every estimate depends on it."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(
            f"pinakes.budget's prices.toml is missing or unreadable ({reason}).",
            remedy=(
                "This ships as package data; reinstall pinakes or rebuild the wheel (`uv build`)."
            ),
        )
        self.reason = reason


class UnknownModelPriceError(PinakesError):
    """`prices.toml` has no entry for this model — an estimate built on a silently absent price
    would be a `KeyError` three layers down instead of a named, actionable failure."""

    def __init__(self, model: str, *, known: Sequence[str]) -> None:
        super().__init__(
            f"no price entry for model {model!r}.",
            remedy=(
                f"Known models: {', '.join(sorted(known))}. "
                "This ships in pinakes.budget's prices.toml; a model outside that list cannot be "
                "estimated until a price for it is added there."
            ),
        )
        self.model = model
        self.known = tuple(known)


class StalePricesError(PinakesError):
    """`prices.toml`'s `as_of` is older than `[budget] max_price_age_days` (I6a, docs/DESIGN.md
    §5) — an estimate built on silently outdated prices is a liability, so estimation refuses
    rather than quietly using a number that may no longer be true."""

    def __init__(self, *, as_of: str, max_age_days: int) -> None:
        super().__init__(
            f"pinakes's bundled prices.toml is dated {as_of!r}, older than the configured "
            f"max_price_age_days ({max_age_days}).",
            remedy=(
                "Upgrade pinakes to refresh the bundled prices, or raise `[budget] "
                "max_price_age_days` once you have verified the current prices are still accurate."
            ),
        )
        self.as_of = as_of
        self.max_age_days = max_age_days


class ContextWindowExceededError(PinakesError):
    """A single request's input (`K` page-slice tokens plus the prompt) would exceed the model's
    documented maximum input — the pre-check exists so this is discovered at estimate time, not at
    a 400 response from a paid call already in flight (I6a, docs/DESIGN.md §5)."""

    def __init__(self, *, request_tokens: int, max_input_tokens: int, model: str) -> None:
        super().__init__(
            f"a single request's input ({request_tokens:,} tokens) would exceed {model}'s "
            f"documented maximum input ({max_input_tokens:,} tokens).",
            remedy=(
                "This should not fire under the shipped constants — K is a fixed request-shape "
                "constant (I6a decision 8), not a configurable knob. If it does, either the "
                "model's documented context window shrank or the page-token ceiling grew past "
                "what any model here accepts; report this as a pinakes defect."
            ),
        )
        self.request_tokens = request_tokens
        self.max_input_tokens = max_input_tokens
        self.model = model


class LedgerError(PinakesError):
    """`.pinakes/ledger.jsonl` cannot be written or read (I6b). Never a per-call failure to shrug
    off: the ledger is the one part of `.pinakes/` a rebuild cannot recreate, so a call whose
    reservation cannot be written must not be made."""


class BudgetConfirmationError(PinakesError):
    """A run owes a `confirm_above_eur` confirmation and has no way to obtain one — no terminal and
    no `--yes` (I6b, docs/DESIGN.md §5). Deliberately narrow: it fires only when a confirmation is
    *actually* owed, never on every non-interactive sync."""

    def __init__(self, *, amount_eur: str, threshold_eur: str) -> None:
        super().__init__(
            f"this run is estimated at €{amount_eur}, above the €{threshold_eur} "
            "`confirm_above_eur` threshold, and there is no terminal to confirm from.",
            remedy=(
                "Re-run interactively, or pass `--yes` to authorise the estimate. `--yes` answers "
                "this prompt only — it raises no cap and authorises no cache deletion."
            ),
        )
        self.amount_eur = amount_eur
        self.threshold_eur = threshold_eur


class UnknownCallError(PinakesError):
    """`pnk budget --resolve` names a `call_id` the ledger has no open reservation for."""

    def __init__(self, call_id: str, *, reason: str) -> None:
        super().__init__(
            f"cannot resolve call {call_id}: {reason}.",
            remedy="`pnk budget` lists every call still reported as `unknown outcome`.",
        )
        self.call_id = call_id


class LinkScanError(PinakesError):
    """A linked KB could not be scanned for inbound links (§6.2).

    Four shapes, one base. Every one is **constructed and never raised**: the scan reports each and
    carries on to the next KB, because `pnk sync` runs on three git hooks and a partner that is
    merely absent on this machine must not turn every commit red. `SyncReport.ok` does not count
    them for the same reason — an unreachable partner is a fact about *this machine*, and §6.2
    already calls incomplete link coverage an honest limitation rather than a failure.

    They carry a message and a remedy so the scan can print one line a person can act on, and so
    `pnk doctor` (L7) can re-derive severity from the manifest without inventing new prose.
    """

    def __init__(self, alias: str, message: str, *, remedy: str) -> None:
        # `rstrip(".")` before appending one: the reasons these carry are increasingly borrowed
        # from other exceptions — `RuntimeError`'s "Could not determine home directory.", another
        # `PinakesError`'s own already-punctuated message — and those arrive with a full stop, so a
        # fixed `.` produced `…home directory..`. Every reason written by hand here has none.
        super().__init__(f"linked KB `{alias}` {message.rstrip('.')}.", remedy=remedy)
        self.alias = alias


class LinkedKbUnreachableError(LinkScanError):
    """`[[links.kb]] path` does not exist on this machine, or holds no readable `pinakes.toml`."""

    def __init__(self, alias: str, path: Path, *, reason: str) -> None:
        super().__init__(
            alias,
            f"cannot be read at {path}: {reason}",
            remedy=(
                "Not an error in itself — a KB is routinely shared without its partners, and "
                "inbound links from it are simply not known here. If it should resolve, fix "
                "`[[links.kb]] path`, or check that you can read the directory it names."
            ),
        )
        self.path = path


class LinkedKbIdMismatchError(LinkScanError):
    """The partner's own `[kb] id` is not the ULID this manifest declared for it."""

    def __init__(self, alias: str, *, declared: str, found: str) -> None:
        super().__init__(
            alias,
            f"is declared as {declared} but the KB at that path is {found}",
            remedy=(
                "A KB ULID is permanent, so one of the two points at the wrong KB. Correct the "
                "`[[links.kb]] id` or its `path`. Nothing is scanned until they agree — guessing "
                "which is right would attribute one KB's links to another."
            ),
        )
        self.declared = declared
        self.found = found


class LinkedSidecarUnreadableError(LinkScanError):
    """One of the partner's sidecars will not parse."""

    def __init__(self, alias: str, path: Path, *, reason: str) -> None:
        super().__init__(
            alias,
            f"has a sidecar that will not parse ({path}): {reason}",
            remedy=(
                "Its inbound links are not recorded, and the ones already known here are kept "
                "untouched. Repair the file in the other KB, then `pnk sync --scan-links`."
            ),
        )
        self.path = path


class LinkTargetMissingError(LinkScanError):
    """The partner links to a document ULID this KB does not have."""

    def __init__(self, alias: str, *, doc_id: str, count: int = 1) -> None:
        subject = "a document" if count == 1 else f"{count} documents"
        super().__init__(
            alias,
            f"links to {subject} this KB does not have (first: {doc_id})",
            remedy=(
                "Usually the other KB is ahead of this one, or a document was deleted here. The "
                "inbound edge is recorded anyway — dropping it would hide a real claim the other "
                "KB is making."
            ),
        )
        self.doc_id = doc_id
        self.count = count


def _rebuild(cls: type[PinakesError], message: str, remedy: str) -> PinakesError:
    """Unpickling helper for `PinakesError.__reduce__` — must stay module-level to be importable.

    Rebuilds the *original* subclass without calling its constructor, whose signature differs per
    subclass. Message and remedy survive; subclass-specific attributes do not, which is the right
    trade for an object whose job on the far side of a process boundary is to be reported.
    """
    error = cls.__new__(cls)
    PinakesError.__init__(error, message, remedy=remedy)
    return error
