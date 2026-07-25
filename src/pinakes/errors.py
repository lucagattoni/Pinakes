"""Error types.

Every user-facing failure derives from `PinakesError` and carries a **remedy**: the message says
what went wrong, the remedy says what to do about it. The CLI prints both, so no failure path can
leave the user knowing something broke but not what to try next — which is the difference between
a tool that stops and a tool that strands you.

Subclasses are added by the increment that first raises them; an empty hierarchy invented up front
would be a guess about failures that do not exist yet.
"""

from collections.abc import Mapping
from pathlib import Path


class PinakesError(Exception):
    """Base class for every failure pinakes reports to a human."""

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
                f"It lands in increment {increment} — see plans/v0.1.md for the build order "
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


class TemplateError(PinakesError):
    """A template is missing or unusable."""


class InitError(PinakesError):
    """A KB cannot be created here."""


class HookError(PinakesError):
    """Git hooks cannot be installed here."""


class ServeError(PinakesError):
    """The MCP server cannot answer as asked."""


class EvalError(PinakesError):
    """The golden set or its baseline cannot be used."""


class CalibrationError(PinakesError):
    """Thresholds cannot be fitted from this golden set."""


def _rebuild(cls: type[PinakesError], message: str, remedy: str) -> PinakesError:
    """Unpickling helper for `PinakesError.__reduce__` — must stay module-level to be importable.

    Rebuilds the *original* subclass without calling its constructor, whose signature differs per
    subclass. Message and remedy survive; subclass-specific attributes do not, which is the right
    trade for an object whose job on the far side of a process boundary is to be reported.
    """
    error = cls.__new__(cls)
    PinakesError.__init__(error, message, remedy=remedy)
    return error
