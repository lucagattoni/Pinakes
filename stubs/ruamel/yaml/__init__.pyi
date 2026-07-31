"""Minimal stub for `ruamel.yaml`, declaring only what this repository uses.

ruamel ships `py.typed`, so this stub is not about a missing marker: `load` and `dump` take an
untyped `stream`, which pyright strict will not accept at the call sites. A stub **overrides the
real package** for every path in pyright's `include` — `src/`, `tests/` and `tools/` — so any symbol
one of them touches must be declared here or that file silently stops type-checking.

A symbol declared in the wrong module is pyright-green and an `ImportError` at runtime, which is
what `test_every_symbol_the_ruamel_stub_declares_matches_inspect_signature` exists to catch.
"""

from typing import IO, Any

from ruamel.yaml.error import YAMLError as YAMLError

class YAML:
    preserve_quotes: bool
    width: int
    def __init__(self, *, typ: str | list[str] | None = None) -> None: ...
    def load(self, stream: str | bytes | IO[str] | IO[bytes]) -> Any: ...
    def dump(self, data: Any, stream: IO[str] | IO[bytes]) -> None: ...
