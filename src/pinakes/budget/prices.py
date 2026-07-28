"""`prices.toml` loading — the money-side twin of `extract/floors.py`.

Ships as package data beside `extract/floors.toml`, read through `importlib.resources` for the
same reason: a file that lives only in the source tree is invisible to an installed wheel, and
prices are consumed at runtime, not at repo-checkout time.

Every value in the file is a TOML *string*, not a bare number — parsed via `Decimal(the_string)`
directly, never `Decimal(float(the_string))`. TOML has no native decimal type, so a bare `5.00`
would come back from `tomllib` as a `float`, and `Decimal(5.00)` reproduces the exact binary value
that literal only approximates, not the clean decimal a human wrote (verified directly,
docs/RETROSPECTIVES.md). Because this file is entirely project-controlled — never user-authored,
unlike `pinakes.toml` — writing prices as strings costs nothing and removes the float
intermediary altogether, rather than reconstructing it from `str(float(...))` the way
`manifest.py`'s `Table.decimal()` has to for a user-authored TOML number.
"""

import tomllib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib import resources
from typing import Any, cast

from pinakes.errors import PricesMissingError, UnknownModelPriceError

PRICES_RESOURCE = "prices.toml"


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_mtok_usd: Decimal
    output_per_mtok_usd: Decimal


@dataclass(frozen=True, slots=True)
class Prices:
    as_of: str
    usd_per_eur: Decimal
    models: dict[str, ModelPrice]

    def for_model(self, model: str) -> ModelPrice:
        found = self.models.get(model)
        if found is None:
            raise UnknownModelPriceError(model, known=tuple(self.models))
        return found


def load_prices() -> Prices:
    """Read `prices.toml` through `importlib.resources` — never a repo-relative path, or a source
    checkout would silently pass what an installed wheel cannot (the same lesson `floors.py`
    already states)."""
    try:
        raw = (
            resources.files("pinakes.budget").joinpath(PRICES_RESOURCE).read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError) as exc:
        raise PricesMissingError(reason=str(exc)) from exc

    try:
        data = tomllib.loads(raw)
        raw_models = cast(dict[str, Any], data["models"])
        models = {
            name: ModelPrice(
                input_per_mtok_usd=Decimal(str(entry["input_per_mtok_usd"])),
                output_per_mtok_usd=Decimal(str(entry["output_per_mtok_usd"])),
            )
            for name, entry in raw_models.items()
        }
        return Prices(
            as_of=str(data["as_of"]),
            usd_per_eur=Decimal(str(data["usd_per_eur"])),
            models=models,
        )
    except (
        tomllib.TOMLDecodeError,  # syntax
        KeyError,  # a required key absent
        TypeError,  # a value the wrong shape (e.g. `models` not a table)
        ValueError,
        InvalidOperation,  # `Decimal(str(x))` on an unparsable value, e.g. "5,00" or "TBD"
        AttributeError,  # `models` present but not a table (`raw_models.items()` on a str/int)
    ) as exc:
        raise PricesMissingError(reason=f"malformed prices.toml ({exc})") from exc
