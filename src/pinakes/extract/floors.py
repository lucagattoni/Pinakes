"""Shared floor loading: read the two v0.2 fitted numbers the way an installed copy has to.

`extract/floors.toml` ships as package data beside I6a's `prices.toml`, for the same reason: a file
that lives only in the source tree is invisible to every installed copy, and both numbers here are
consumed at runtime, not at repo-checkout time. Two numbers share one file because they were fitted
in the same corpus run (`make pdf-eval`, `plans/v0.2.md` I3b): I3a's running-head threshold *T*
(`layout.assemble`'s `running_head_threshold`) and I3b's text-yield floor. They differ in what an
absent value means to their own callers — *T* costs nothing, so `pdfium.py` treats its absence as a
startup error; the text-yield floor gates spending, so I7b/I8 treat its absence as "refuse to spend"
— but loading the file itself is one honest function, not two, since a missing or malformed
`floors.toml` is the same problem either way.
"""

import tomllib
from dataclasses import dataclass
from importlib import resources

from pinakes.errors import FloorsMissingError

FLOORS_RESOURCE = "floors.toml"


@dataclass(frozen=True, slots=True)
class Floors:
    running_head_threshold: float
    text_yield_floor: float
    fitted_on: str


def load_floors() -> Floors:
    """Read `floors.toml` through `importlib.resources` — never a repo-relative path, or a source
    checkout would silently pass what an installed wheel cannot (docs/RETROSPECTIVES.md, I2's own
    `du`-vs-measured lesson applies here just as much: read the artifact a user actually gets)."""
    try:
        raw = (
            resources.files("pinakes.extract").joinpath(FLOORS_RESOURCE).read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError) as exc:
        raise FloorsMissingError(reason=str(exc)) from exc

    try:
        data = tomllib.loads(raw)
        return Floors(
            running_head_threshold=float(data["running_head_threshold"]),
            text_yield_floor=float(data["text_yield_floor"]),
            fitted_on=str(data["fitted_on"]),
        )
    except (tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as exc:
        raise FloorsMissingError(reason=f"malformed floors.toml ({exc})") from exc
