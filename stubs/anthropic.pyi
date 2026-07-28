"""Hand-authored stub for the `anthropic` surface this project actually calls.

Needed for the same reason `pypdfium2.pyi` is, and for one more: `anthropic` is an **optional
extra**, so the type gate runs on the `[light]` leg with the package absent — and CI's `check` job
is a three-leg matrix, so a stub-less strict run is red on two of the three legs regardless of
which one a developer happens to have installed locally.

Deliberately minimal: only `extract/claude.py`'s surface. The exception hierarchy is the part that
matters, because `claude.py` classifies failures by it, and one relationship in it is easy to get
wrong from memory — **`APIConnectionError` is a sibling of `APIStatusError`, not a subclass** (both
descend from `APIError`), and `APITimeoutError` is a subclass of `APIConnectionError`. Ordering the
`isinstance` checks the other way round would silently classify every timeout as a plain connection
failure, which is exactly the difference between a `void` and an `unknown outcome` — between
recording €0 and admitting a possible charge.

`status_code` is deliberately **not** declared here: `claude.py` reads it through `getattr` with an
`isinstance` check, because a stub is a claim about a library and this project would rather narrow
a real value than trust one it wrote down itself.
"""

from typing import Any

class APIError(Exception): ...
class APIStatusError(APIError): ...
class APIConnectionError(APIError): ...
class APITimeoutError(APIConnectionError): ...

class Usage:
    input_tokens: int
    output_tokens: int

class Message:
    def model_dump(self) -> dict[str, Any]: ...

class TokenCount:
    input_tokens: int

class Messages:
    def create(self, **kwargs: Any) -> Message: ...
    def count_tokens(self, **kwargs: Any) -> TokenCount: ...

class Anthropic:
    messages: Messages
    def __init__(
        self,
        *,
        api_key: str | None = ...,
        timeout: float | None = ...,
        max_retries: int = ...,
        **kwargs: Any,
    ) -> None: ...
