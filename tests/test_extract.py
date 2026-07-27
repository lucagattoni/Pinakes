"""The extraction seam: registry dispatch, the two honest stubs, and the fake test double."""

import builtins
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType

import pytest

from pinakes.errors import BackendUnknownError, ExtractionError, ExtractorMissingError
from pinakes.extract import (
    CLAUDE_VISION,
    FAKE,
    PYPDFIUM2,
    ExtractedText,
    ExtractionContext,
    fingerprint,
    fingerprint_inputs,
    load_extractor,
    registered_extractors,
)


def test_all_three_backends_are_registered() -> None:
    assert registered_extractors() == sorted([CLAUDE_VISION, FAKE, PYPDFIUM2])


def test_an_unregistered_backend_lists_the_known_ones() -> None:
    with pytest.raises(BackendUnknownError) as exc_info:
        load_extractor("telepathy")
    assert PYPDFIUM2 in exc_info.value.remedy


def test_the_fake_extractor_is_a_working_double_not_a_stub() -> None:
    """Registered by I1, named here — a stand-in must be adversarial in what it stands in for."""
    extracted = load_extractor(FAKE).extract(Path("irrelevant.pdf"), ExtractionContext())
    assert isinstance(extracted, ExtractedText)
    assert "  " in extracted.text  # double spaces
    assert extracted.text.count("Running Header") >= 2  # a stray running head, repeated
    assert "hyphen-\nated" in extracted.text  # a hyphenated word split across a line break

    assert "".join(extracted.text[s:e] for s, e in extracted.page_spans) == extracted.text
    assert extracted.page_spans[0][0] == 0
    assert extracted.page_spans[-1][1] == len(extracted.text)


def _blocking(*names: str) -> Callable[..., ModuleType]:
    """`__import__` replacement that refuses only the named modules, real otherwise."""
    real_import = builtins.__import__

    def refuse(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        if any(name == blocked or name.startswith(f"{blocked}.") for blocked in names):
            raise ImportError(f"no module named {name}")
        return real_import(name, globals, locals, fromlist, level)

    return refuse


def _faking(*names: str) -> Callable[..., ModuleType]:
    """`__import__` replacement that satisfies the named modules with a stand-in, real otherwise.

    Proves a stub's own "not implemented yet" error fires even when the library imports cleanly —
    without needing it genuinely installed (no uninstall, and no install, needed for this test).
    """
    real_import = builtins.__import__
    stand_ins = {name: ModuleType(name) for name in names}

    def fake(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        if name in stand_ins:
            return stand_ins[name]
        return real_import(name, globals, locals, fromlist, level)

    return fake


@pytest.mark.parametrize(
    ("backend", "module", "extra"),
    [(PYPDFIUM2, "pypdfium2", "pdf"), (CLAUDE_VISION, "anthropic", "claude")],
)
def test_a_missing_extra_names_the_install_command(
    monkeypatch: pytest.MonkeyPatch, backend: str, module: str, extra: str
) -> None:
    monkeypatch.setattr(builtins, "__import__", _blocking(module))
    with pytest.raises(ExtractorMissingError) as exc_info:
        load_extractor(backend)
    assert exc_info.value.extra == extra
    assert f'uv add "pinakes[{extra}]"' in exc_info.value.remedy


@pytest.mark.parametrize(
    ("backend", "module", "increment"),
    [(PYPDFIUM2, "pypdfium2", "I3b"), (CLAUDE_VISION, "anthropic", "I7b")],
)
def test_a_stub_names_its_own_landing_increment(
    monkeypatch: pytest.MonkeyPatch, backend: str, module: str, increment: str
) -> None:
    monkeypatch.setattr(builtins, "__import__", _faking(module))
    with pytest.raises(ExtractionError) as exc_info:
        load_extractor(backend)
    assert increment in exc_info.value.message


def test_fingerprint_inputs_never_import_the_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """§4.4 runs this on every query; it must not import a paid client to answer one."""
    monkeypatch.setattr(builtins, "__import__", _blocking("pypdfium2", "anthropic"))
    for backend in (PYPDFIUM2, CLAUDE_VISION, FAKE):
        assert fingerprint_inputs(backend)["backend"] == backend


def test_fingerprint_is_a_pure_function_of_the_inputs() -> None:
    assert fingerprint(PYPDFIUM2) == fingerprint(PYPDFIUM2)
    assert fingerprint(PYPDFIUM2) != fingerprint(CLAUDE_VISION)
    assert fingerprint(PYPDFIUM2) != fingerprint(FAKE)


def test_extraction_context_paid_fields_default_to_none() -> None:
    ctx = ExtractionContext()
    assert ctx.model is None
    assert ctx.force is False
    assert ctx.accountant is None
    assert ctx.ledger is None
    assert ctx.staging_dir is None
    assert ctx.resume_from_page is None
