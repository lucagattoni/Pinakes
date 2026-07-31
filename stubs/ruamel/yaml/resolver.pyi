from typing import Any

from ruamel.yaml.nodes import Node

class VersionedResolver:
    def __init__(self, version: tuple[int, int] | None = None) -> None: ...
    def resolve(self, kind: type[Node], value: str | None, implicit: tuple[bool, bool]) -> Any: ...
