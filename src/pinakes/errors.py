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
