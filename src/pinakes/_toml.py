"""A strict reader over parsed TOML.

Every accessor consumes the key it reads; `done()` then fails on whatever is left. That is how
unknown keys become hard errors: a manifest saying `finall_k = 20` must not be silently ignored,
because the user would get default behaviour while believing they had configured something.

Errors name the file, the table and the key, in that order — a validation error the user cannot
locate is barely better than no validation.
"""

from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from pinakes.errors import ManifestError

ROOT_NAME = "<root>"


class Table:
    """One TOML table, read destructively so leftovers can be reported."""

    def __init__(self, data: dict[str, Any], *, name: str, source: Path) -> None:
        self._data = dict(data)
        self._name = name
        self._source = source

    @property
    def name(self) -> str:
        return self._name

    def _child_name(self, key: str) -> str:
        """`[retrieval]`, not `[<root>.retrieval]`: the name must match what the user typed."""
        return key if self._name == ROOT_NAME else f"{self._name}.{key}"

    def _fail(self, message: str, *, remedy: str | None = None) -> ManifestError:
        return ManifestError(self._source, table=self._name, message=message, remedy=remedy)

    def _take(self, key: str, *, required: bool) -> object | None:
        """Read and consume a key. Returns `object`, not `Any`, so every caller must narrow it."""
        if key in self._data:
            return self._data.pop(key)
        if required:
            raise self._fail(f"missing required key `{key}`")
        return None

    def _string(self, key: str, *, required: bool) -> str | None:
        value = self._take(key, required=required)
        if value is None:
            return None
        if not isinstance(value, str):
            raise self._fail(f"`{key}` must be a string, found {type(value).__name__}")
        if not value.strip():
            # An explicit empty string is a mistake, never a request for the default: silently
            # substituting one would hide it until something far downstream failed obscurely.
            raise self._fail(f"`{key}` must not be empty")
        return value

    def string(self, key: str) -> str:
        """A required string. The return type is `str`, so callers need no assertion."""
        value = self._string(key, required=True)
        assert value is not None  # `required=True` raised already; this is for the type checker
        return value

    def optional_string(self, key: str) -> str | None:
        return self._string(key, required=False)

    def string_or(self, key: str, default: str) -> str:
        return self._string(key, required=False) or default

    def choice(self, key: str, allowed: Sequence[str], *, default: str | None = None) -> str:
        value = self.string(key) if default is None else self.string_or(key, default)
        if value not in allowed:
            raise self._fail(
                f"`{key}` must be one of {', '.join(repr(option) for option in allowed)}, "
                f"found {value!r}"
            )
        return value

    def integer(self, key: str, *, default: int | None = None, minimum: int | None = None) -> int:
        value = self._take(key, required=default is None)
        if value is None:
            value = default
        # bool is an int subclass; `max_tokens = true` must not read as 1.
        if not isinstance(value, int) or isinstance(value, bool):
            raise self._fail(f"`{key}` must be an integer, found {type(value).__name__}")
        if minimum is not None and value < minimum:
            raise self._fail(f"`{key}` must be >= {minimum}, found {value}")
        return value

    def number(
        self, key: str, *, default: float | None = None, minimum: float | None = None
    ) -> float:
        value = self._take(key, required=default is None)
        if value is None:
            value = default
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise self._fail(f"`{key}` must be a number, found {type(value).__name__}")
        value = float(value)
        if minimum is not None and value < minimum:
            raise self._fail(f"`{key}` must be >= {minimum}, found {value}")
        return value

    def decimal(
        self, key: str, *, default: Decimal | None = None, minimum: Decimal | None = None
    ) -> Decimal:
        """A TOML number read as an exact `Decimal`, for a value that is ever compared or summed
        as money — where `float`'s binary representation error would make a hard cap not actually
        hard (I6a).

        TOML has no native decimal type, so `tomllib` hands back a `float` regardless; this goes
        through `Decimal(str(value))`, never `Decimal(value)` directly. The former recovers the
        clean literal a user typed (`0.05` -> `Decimal("0.05")`); the latter reproduces the exact
        binary value that literal only approximates (`0.05` ->
        `Decimal("0.05000000000000000277555756156289135105907917022705078125")`) — verified
        directly against every value this project's own `[budget]` defaults use.
        """
        value = self._take(key, required=default is None)
        if value is None:
            assert default is not None  # `required=True` above already raised otherwise
            decimal_value = default
        else:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise self._fail(f"`{key}` must be a number, found {type(value).__name__}")
            decimal_value = Decimal(str(value))
        # Checked on both paths, not only the TOML-sourced one — `integer()`/`number()` above
        # validate their own defaults for free, since they share one type with the parsed value;
        # `decimal()`'s default is already a `Decimal` rather than a parsed float, so an early
        # return here would let a below-`minimum` default slip past unminded.
        if minimum is not None and decimal_value < minimum:
            raise self._fail(f"`{key}` must be >= {minimum}, found {decimal_value}")
        return decimal_value

    def strings(self, key: str, *, default: Sequence[str] | None = None) -> tuple[str, ...]:
        value = self._take(key, required=default is None)
        if value is None:
            return tuple(default or ())
        if not isinstance(value, list):
            raise self._fail(f"`{key}` must be a list of strings")
        items: list[str] = []
        for item in cast(list[object], value):
            if not isinstance(item, str):
                raise self._fail(
                    f"`{key}` must be a list of strings, found a {type(item).__name__}"
                )
            items.append(item)
        return tuple(items)

    def table(self, key: str) -> "Table | None":
        value = self._take(key, required=False)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise self._fail(f"`{key}` must be a table")
        return Table(cast(dict[str, Any], value), name=self._child_name(key), source=self._source)

    def tables(self, key: str) -> list["Table"]:
        value = self._take(key, required=False)
        if value is None:
            return []
        if not isinstance(value, list):
            raise self._fail(f"`{key}` must be an array of tables")
        tables: list[Table] = []
        for index, item in enumerate(cast(list[object], value)):
            if not isinstance(item, dict):
                raise self._fail(f"`{key}` must be an array of tables")
            tables.append(
                Table(
                    cast(dict[str, Any], item),
                    name=f"{self._child_name(key)}[{index}]",
                    source=self._source,
                )
            )
        return tables

    def reject(self, key: str, *, because: str) -> None:
        """Fail loudly on a key that moved, so an old manifest is corrected rather than ignored."""
        if key in self._data:
            raise self._fail(f"`{key}` is not valid here: {because}")

    def done(self) -> None:
        if self._data:
            unknown = ", ".join(f"`{key}`" for key in sorted(self._data))
            raise self._fail(
                f"unknown key(s): {unknown}",
                remedy=(
                    "Unknown keys are rejected rather than ignored — a typo would otherwise leave "
                    "you with default behaviour while believing you had configured something. "
                    "Check the spelling against docs/DESIGN.md §2.1."
                ),
            )
