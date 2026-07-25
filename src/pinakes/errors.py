"""Error types.

Every user-facing failure derives from `PinakesError` and carries a **remedy**: the message says
what went wrong, the remedy says what to do about it. The CLI prints both, so no failure path can
leave the user knowing something broke but not what to try next — which is the difference between
a tool that stops and a tool that strands you.

Subclasses are added by the increment that first raises them; an empty hierarchy invented up front
would be a guess about failures that do not exist yet.
"""


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
        return (_rebuild, (self.message, self.remedy))


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


def _rebuild(message: str, remedy: str) -> PinakesError:
    """Unpickling helper for `PinakesError.__reduce__` — must stay module-level to be importable."""
    return PinakesError(message, remedy=remedy)
