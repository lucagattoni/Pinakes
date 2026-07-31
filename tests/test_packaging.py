"""Packaging invariants: extras stay extras, and each library imports cleanly when installed."""

import tomllib
from collections.abc import Callable
from importlib import import_module
from importlib.machinery import ModuleSpec
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import conftest
import pytest

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _pyproject() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _spec_absent(name: str) -> ModuleSpec | None:
    return None


def _spec_present(name: str) -> ModuleSpec | None:
    return ModuleSpec(name, None)


def _spec_for(*present: str) -> Callable[[str], ModuleSpec | None]:
    """A `find_spec` stand-in reporting only the named modules as importable."""

    def find(name: str) -> ModuleSpec | None:
        return ModuleSpec(name, None) if name in present else None

    return find


def test_extractors_stay_extras() -> None:
    """`pypdfium2`/`anthropic` must never enter core — a light install stays torch-free (§4.5)."""
    dependencies = " ".join(_pyproject()["project"]["dependencies"]).lower()
    assert "pypdfium2" not in dependencies
    assert "anthropic" not in dependencies


def test_claude_extra_requires_pdf_extra() -> None:
    """The paid path slices, pre-checks and audits through pypdfium2 — it cannot run without it."""
    optional = _pyproject()["project"]["optional-dependencies"]
    assert "pinakes[pdf]" in optional["claude"]


def test_pillow_is_dev_only_never_core_and_never_an_extra() -> None:
    """Pillow builds the corpus; it must never be something an *installed* pinakes pulls in.

    Stated as a decision in I2 and relied on by `pdf_runnable()`, but until this test nothing
    enforced it — adding `pillow` to `[project.dependencies]` or to the `pdf` extra left the whole
    suite green, unlike the structurally identical pypdfium2/anthropic claim above.
    """
    project = _pyproject()["project"]
    core = " ".join(project["dependencies"]).lower()
    assert "pillow" not in core

    for name, entries in project["optional-dependencies"].items():
        joined = " ".join(entries).lower()
        assert "pillow" not in joined, f"pillow leaked into the [{name}] extra"

    dev = " ".join(_pyproject()["dependency-groups"]["dev"]).lower()
    assert "pillow" in dev  # and it does have to be *somewhere*, or the corpus cannot regenerate


@pytest.mark.skipif(find_spec("pypdfium2") is None, reason="pinakes[pdf] not installed")
def test_pypdfium2_imports_without_a_warning() -> None:
    """`filterwarnings = ["error"]` (pyproject) turns any import-time warning into this failing."""
    import_module("pypdfium2")


@pytest.mark.skipif(find_spec("anthropic") is None, reason="pinakes[claude] not installed")
def test_anthropic_imports_without_a_warning() -> None:
    import_module("anthropic")


def test_pdf_runnable_requires_all_three_conditions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pypdfium2, Pillow, and the corpus — checking fewer than all three passes on a KB missing one.

    Pillow joined this predicate in I2 (dev-group-only, never core, never an extra): a pypdfium2 +
    corpus check that forgot it would report runnable in an environment where `pdf`-marked tests
    would still crash constructing a `PIL.Image`, not skip.
    """
    corpus = tmp_path / "pdf-corpus"
    monkeypatch.setattr(conftest, "PDF_CORPUS", corpus)

    monkeypatch.setattr(conftest, "find_spec", _spec_absent)
    assert conftest.pdf_runnable() is False  # nothing holds

    corpus.mkdir()
    assert conftest.pdf_runnable() is False  # corpus present, neither library is

    monkeypatch.setattr(conftest, "find_spec", _spec_for("pypdfium2"))
    assert conftest.pdf_runnable() is False  # pypdfium2 only, Pillow still missing

    monkeypatch.setattr(conftest, "find_spec", _spec_for("PIL"))
    assert conftest.pdf_runnable() is False  # Pillow only, pypdfium2 still missing

    monkeypatch.setattr(conftest, "find_spec", _spec_present)
    assert conftest.pdf_runnable() is True  # all three hold

    # Every clause must be *individually* load-bearing, so each is turned off on its own from the
    # all-true state. Without this last case the corpus clause could be deleted outright and the
    # walk above would still pass — the corpus was created early and never removed again.
    corpus.rmdir()
    assert conftest.pdf_runnable() is False  # both libraries, corpus gone


def test_paid_runnable_requires_all_three_conditions(monkeypatch: pytest.MonkeyPatch) -> None:
    """`anthropic` importable, a key present, and the pytest-only opt-in — all three, not two."""
    monkeypatch.setattr(conftest, "find_spec", _spec_present)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("PINAKES_ALLOW_SPEND", "1")
    assert conftest.paid_runnable() is True

    monkeypatch.setattr(conftest, "find_spec", _spec_absent)
    assert conftest.paid_runnable() is False  # anthropic not importable
    monkeypatch.setattr(conftest, "find_spec", _spec_present)

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert conftest.paid_runnable() is False  # no key present
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    monkeypatch.setenv("PINAKES_ALLOW_SPEND", "0")
    assert conftest.paid_runnable() is False  # opt-in set, but not to exactly "1"


def test_ruamel_yaml_is_a_core_dependency() -> None:
    """It reads and writes every sidecar; a KB cannot be opened without it."""
    core = " ".join(_pyproject()["project"]["dependencies"]).lower()
    assert "ruamel.yaml" in core or "ruamel-yaml" in core


def test_pyyaml_is_dev_only_never_core_and_never_an_extra() -> None:
    """PyYAML left the runtime with L5b and must not come back — the `pillow` precedent.

    It stays in `dev` because the tests still need it: the one thing nothing else in this repo can
    do any more is read a file the way a **YAML 1.1** reader would, which is what
    `test_a_minted_title_that_looks_like_a_boolean_is_quoted` exists to check.
    """
    project = _pyproject()["project"]
    assert "pyyaml" not in " ".join(project["dependencies"]).lower()

    for name, entries in project["optional-dependencies"].items():
        assert "pyyaml" not in " ".join(entries).lower(), f"pyyaml leaked into the [{name}] extra"

    assert "pyyaml" in " ".join(_pyproject()["dependency-groups"]["dev"]).lower()


def test_no_module_under_src_imports_pyyaml() -> None:
    """An AST scan, not an import walk. Two reasons the walk is wrong: it loads `pypdfium2`, which
    is absent on the `[light]` leg and which the paid-path rules forbid probing by import; and it
    executes module scope only, so a lazy function-scoped import — the exact thing this guards
    against — is invisible to it.

    The **root** module name is compared, never a substring: `ruamel.yaml`, `from ruamel import
    yaml`, `ruamel.yaml.comments` and `from ruamel.yaml import YAML` all contain "yaml" and are all
    legal. `ImportFrom` additionally requires `level == 0`, or a relative `from .yaml import x`
    would trip it.

    Paired with `test_the_free_path_never_imports_the_paid_client`'s sibling runtime check, because
    neither is sufficient alone: this one cannot see a dynamic import with a computed name, and the
    runtime one only sees what a run executes — `pinakes.eval` is not in the free path's graph.
    """
    import ast

    source_root = PYPROJECT.parent / "src" / "pinakes"
    offenders: list[str] = []
    for module in sorted(source_root.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name.split(".")[0] == "yaml" for alias in node.names):
                    offenders.append(f"{module}:{node.lineno} import")
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and (node.module or "").split(".")[0] == "yaml":
                    offenders.append(f"{module}:{node.lineno} from-import")
            elif isinstance(node, ast.Call):
                target = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if target in {"import_module", "__import__"} and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and first.value == "yaml":
                        offenders.append(f"{module}:{node.lineno} dynamic")

    assert not offenders, "PyYAML is back in the runtime:\n  " + "\n  ".join(offenders)


def test_every_symbol_the_ruamel_stub_declares_matches_inspect_signature() -> None:
    """A stub that **declares a parameter ruamel does not have** is pyright-green and a `TypeError`
    at runtime — an import-only check would not catch it, which is decision 20's whole point.

    A stub that *omits* a real parameter is not a mismatch: no minimal stub could pass otherwise.
    `preserve_quotes` and `width` are *instance* attributes, so `inspect.signature` does not apply
    and `getattr(YAML, "width")` raises — they are asserted by setting them on an instance instead.
    """
    import inspect

    declared = {
        "ruamel.yaml": ["YAML"],
        "ruamel.yaml.comments": ["CommentedMap", "CommentedSeq", "TaggedScalar"],
        "ruamel.yaml.error": ["YAMLError", "ReusedAnchorWarning"],
        "ruamel.yaml.constructor": ["DuplicateKeyError", "ScalarBoolean"],
        "ruamel.yaml.scalarstring": ["SingleQuotedScalarString"],
        "ruamel.yaml.scalarbool": ["ScalarBoolean"],
        "ruamel.yaml.nodes": ["ScalarNode"],
        "ruamel.yaml.resolver": ["VersionedResolver"],
    }
    for module_name, symbols in declared.items():
        module = import_module(module_name)
        for symbol in symbols:
            assert hasattr(module, symbol), f"{module_name}.{symbol} does not exist"

    from ruamel.yaml import YAML
    from ruamel.yaml.resolver import VersionedResolver

    assert set(inspect.signature(YAML.__init__).parameters) >= {"self", "typ"}
    assert set(inspect.signature(VersionedResolver.resolve).parameters) >= {
        "kind",
        "value",
        "implicit",
    }
    instance = YAML()
    instance.preserve_quotes = True
    instance.width = 4096
    assert instance.preserve_quotes is True and instance.width == 4096


def test_the_two_resolver_union_covers_pyyaml_1_1() -> None:
    """Decision 23 says to prove this rather than assume it.

    The quoting predicate uses two `VersionedResolver`s, at 1.1 and 1.2, and deliberately **not**
    `yaml.resolver.Resolver`: L5b removes `pyyaml` from the runtime dependencies, so importing it
    in `write()` would `ImportError` on a user's install — and the AST gate is built to fail on
    exactly that import, so the increment could not be green and correct at once.

    The claim that makes that safe is that the ruamel pair is not weaker: there is no value PyYAML
    1.1 resolves as non-`str` while both ruamel versions resolve as `str`. Proved here, in `tests/`,
    where `pyyaml` *is* installed.
    """
    import yaml

    from pinakes.sidecar import needs_quoting

    probes = [
        "NO",
        "no",
        "No",
        "yes",
        "Yes",
        "YES",
        "on",
        "off",
        "ON",
        "OFF",
        "true",
        "false",
        "True",
        "False",
        "TRUE",
        "y",
        "n",
        "Y",
        "N",
        "~",
        "null",
        "Null",
        "NULL",
        "",
        "0755",
        "0o17",
        "0x1F",
        "1e3",
        "1E3",
        "1.5",
        "-3",
        "+7",
        "1_000",
        "1:30",
        "1:30:00",
        ".inf",
        "-.inf",
        ".nan",
        "2026-07-31",
        "2026-07-31 18:00:00",
        "hello",
        "a b",
    ]
    weaker: list[str] = []
    for probe in probes:
        pyyaml_is_str = isinstance(yaml.safe_load(f"v: {probe}\n").get("v"), str)
        if not pyyaml_is_str and not needs_quoting(probe):
            weaker.append(probe)

    assert not weaker, (
        "these resolve as non-strings under PyYAML 1.1 and would be written bare: " + str(weaker)
    )
