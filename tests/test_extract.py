"""The extraction seam: registry dispatch, the two honest stubs, and the fake test double."""

import builtins
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
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
    ExtractorEntry,
    backend_requirement,
    fingerprint,
    fingerprint_inputs,
    is_backend_installed,
    is_paid_backend,
    load_extractor,
    paid_backend_names,
    register_extractor,
    registered_extractors,
    unregister_extractor,
)


def test_all_three_backends_are_registered() -> None:
    assert registered_extractors() == sorted([CLAUDE_VISION, FAKE, PYPDFIUM2])


def test_only_claude_vision_is_registered_as_paid() -> None:
    assert paid_backend_names() == frozenset({CLAUDE_VISION})
    assert is_paid_backend(CLAUDE_VISION)
    assert not is_paid_backend(PYPDFIUM2)
    assert not is_paid_backend(FAKE)


def test_is_paid_backend_never_imports_the_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry metadata only (`ExtractorEntry.paid`'s own docstring) — §4.4's per-document
    coherence check calls this on every query and must never import a paid client to answer it."""
    monkeypatch.setattr(builtins, "__import__", _blocking("pypdfium2", "anthropic"))
    assert is_paid_backend(CLAUDE_VISION)
    assert paid_backend_names() == frozenset({CLAUDE_VISION})


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


def test_claude_vision_stub_names_its_own_landing_increment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one remaining stub — pypdfium2 stopped being one in I3b (below)."""
    monkeypatch.setattr(builtins, "__import__", _faking("anthropic"))
    with pytest.raises(ExtractionError) as exc_info:
        load_extractor(CLAUDE_VISION)
    assert "I7b" in exc_info.value.message


def test_pypdfium2_is_a_real_extractor_not_a_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """I3b's own landing: `load_extractor(PYPDFIUM2)` used to raise, naming this increment, the
    moment `pypdfium2` imported cleanly — now it must return a working `Extractor` instead."""
    monkeypatch.setattr(builtins, "__import__", _faking("pypdfium2"))
    extractor = load_extractor(PYPDFIUM2)
    assert hasattr(extractor, "extract")


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


@pytest.fixture
def probe_backend() -> Iterator[Callable[[tuple[str, str] | None], str]]:
    """Register a throwaway backend with a chosen `requires`, unregistered on teardown.

    `is_backend_installed` is otherwise only ever exercised against the real `pypdfium2` and
    `anthropic`, whose presence varies per CI leg — so every assertion about it would agree with
    whatever the environment happened to be. A synthetic requirement is the only way to pin both
    answers at once.
    """
    registered: list[str] = []

    def _register(requires: tuple[str, str] | None) -> str:
        name = f"probe-{len(registered)}"
        register_extractor(
            name,
            ExtractorEntry(
                load=lambda: load_extractor(FAKE),
                fingerprint_inputs=lambda: {"backend": name},
                requires=requires,
            ),
        )
        registered.append(name)
        return name

    yield _register

    for name in registered:
        unregister_extractor(name)


def test_is_backend_installed_reports_a_missing_module(
    probe_backend: Callable[[tuple[str, str] | None], str],
) -> None:
    """The direction that matters for a user: a backend whose library is absent must say so.

    Caught by mutation, 20260728 19:31 — `is_backend_installed` returning a constant `True` passed
    the entire suite, because its only consumers (`doctor._extraction`, `sync._missing_pdf_extra`)
    are tested with it monkeypatched. A function nothing tests directly is a function whose callers
    all agree with each other.
    """
    absent = probe_backend(("pinakes_definitely_not_an_installed_module", "nope"))
    present = probe_backend(("json", "stdlib"))
    needs_nothing = probe_backend(None)

    assert is_backend_installed(absent) is False
    assert is_backend_installed(present) is True
    assert is_backend_installed(needs_nothing) is True


def test_is_backend_installed_locates_without_executing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    probe_backend: Callable[[tuple[str, str] | None], str],
) -> None:
    """The whole claim of the `find_spec` approach: it answers "installed?" without running the
    module. Proved with a module that *raises on import* — if the implementation ever went back to
    importing, this test would error rather than fail politely.

    This is what keeps `pnk doctor` off I7a's gate 4: loading a paid backend to report whether it
    is available is exactly the leak this increment fixed, in both doctor and sync.
    """
    module_name = "pinakes_i7a_import_tripwire"
    (tmp_path / f"{module_name}.py").write_text(
        "raise RuntimeError('is_backend_installed executed the module')\n", encoding="utf-8"
    )
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    name = probe_backend((module_name, "tripwire"))

    assert is_backend_installed(name) is True
    assert module_name not in sys.modules


def test_backend_requirement_names_the_extra_a_user_is_told_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `(module, extra)` pair is what `sync`'s skipped-`.pdf` hint turns into `pinakes[pdf]`.
    Registry metadata, so it answers without importing either client."""
    monkeypatch.setattr(builtins, "__import__", _blocking("pypdfium2", "anthropic"))
    assert backend_requirement(PYPDFIUM2) == ("pypdfium2", "pdf")
    assert backend_requirement(CLAUDE_VISION) == ("anthropic", "claude")
    assert backend_requirement(FAKE) is None
