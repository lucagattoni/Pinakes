"""`[kb] requires_pinakes` — turning a misleading refusal into an actionable one (G4).

The manifest is forward-**incompatible** by design: an unknown key is a hard error, because a typo
that silently left you on defaults is worse than a refusal (docs/DESIGN.md §2.1). The cost is that a
KB written by a newer pinakes fails on the first key this build has never heard of, and says:

    REFUSED: [budget]: unknown key(s): `weekly_eur`
    REMEDY : Unknown keys are rejected rather than ignored — a typo would otherwise leave you
             with default behaviour while believing you had configured something.

The refusal is correct and **the diagnosis is wrong**: the user's problem is an out-of-date
pinakes, and they have been told they cannot spell. `requires_pinakes` lets the manifest say so
first — which only works if it is read *before* strict validation, since afterwards the parse has
already died on the unknown key. That ordering is the feature, and
`test_the_pre_pass_runs_before_strict_validation` is the test that holds it.

What this cannot do, stated so nobody expects it: it never explains a key retroactively. A pinakes
built before G4 has no pre-pass and fails on `requires_pinakes` itself. It only ever helps for keys
added *after* it ships (docs/KB-UPDATES.md §7).
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pinakes import __version__
from pinakes.errors import ManifestError
from pinakes.manifest import load

#: Comfortably above anything this project will ever publish, so the test does not go stale the
#: moment a release is cut — writing `">=0.6"` here would start passing for the wrong reason.
UNREACHABLE = ">=999.0"

MANIFEST = """\
[kb]
name = "research"
id   = "01KYCPTN72ZXC1DDWS6054MGZV"
{extra}

[sources]
roots = ["docs/"]

[embedding]
provider = "fastembed"
model    = "BAAI/bge-small-en-v1.5"
dim      = 384
"""


@pytest.fixture
def kb(write_manifest: Callable[[str], Path]) -> Callable[..., Path]:
    """A minimal valid KB, with whatever `[kb]` and trailing lines the test needs."""

    def _make(*, extra: str = "", tail: str = "") -> Path:
        return write_manifest(MANIFEST.format(extra=extra) + tail)

    return _make


def test_an_absent_requires_pinakes_is_not_an_error(kb: Callable[..., Path]) -> None:
    """Every KB in existence lacks the field. A missing floor is "none declared", not a refusal —
    and if this ever fails, shipping the check broke every KB on the planet at once."""
    manifest = load(kb())
    assert manifest.kb.name == "research"


def test_a_manifest_requiring_a_newer_pinakes_names_the_version(kb: Callable[..., Path]) -> None:
    """Both numbers, because either alone leaves the user guessing: what is needed, and what they
    have. The remedy has to be an upgrade, never an edit to a file pinakes does not own."""
    with pytest.raises(ManifestError) as exc_info:
        load(kb(extra=f'requires_pinakes = "{UNREACHABLE}"'))

    message = str(exc_info.value)
    assert UNREACHABLE in message
    assert __version__ in message
    assert "upgrade pinakes" in exc_info.value.remedy.lower()


def test_the_pre_pass_runs_before_strict_validation(kb: Callable[..., Path]) -> None:
    """The whole increment, in one test.

    This manifest carries *both* a floor this build cannot meet and a key from the future that
    strict validation would reject. Read in the other order, the parse dies on `weekly_eur` and
    tells the user about a typo — the exact misdiagnosis `requires_pinakes` exists to prevent, and
    the failure mode is invisible unless a test carries both faults at once.
    """
    root = kb(
        extra=f'requires_pinakes = "{UNREACHABLE}"',
        tail="\n[budget]\nweekly_eur = 1.00\n",
    )

    with pytest.raises(ManifestError) as exc_info:
        load(root)

    message = str(exc_info.value)
    assert UNREACHABLE in message, (
        "the version floor did not win the race against strict validation"
    )
    assert "weekly_eur" not in message, (
        "the unknown key was reported instead of the version floor — the pre-pass is running after "
        "strict validation, which makes the field unreachable in the only case it exists for"
    )


def test_a_floor_this_build_meets_exactly_is_accepted(kb: Callable[..., Path]) -> None:
    """`>=` includes the boundary. Off-by-one here would refuse the KB pinakes just wrote."""
    assert load(kb(extra=f'requires_pinakes = ">={__version__}"')).kb.name == "research"


def test_an_older_floor_is_accepted(kb: Callable[..., Path]) -> None:
    assert load(kb(extra='requires_pinakes = ">=0.0.1"')).kb.name == "research"


def test_a_shorter_floor_compares_as_the_same_version(kb: Callable[..., Path]) -> None:
    """`0.5` and `0.5.0` are one version, and tuple comparison does not know that."""
    major, minor, *_ = __version__.split(".")
    assert load(kb(extra=f'requires_pinakes = ">={major}.{minor}"')).kb.name == "research"


def test_a_longer_floor_of_trailing_zeros_is_the_same_version(kb: Callable[..., Path]) -> None:
    """The direction that actually needs the padding, and the one the obvious test misses.

    A *shorter* floor compares correctly by accident: `(0, 5) > (0, 5, 0)` is already `False`. It is
    the *longer* one that goes wrong — `(0, 5, 0, 0) > (0, 5, 0)` is `True`, so an unpadded
    comparison refuses a floor this build exactly meets. Found by mutation: deleting `_pad` left
    every other test in this module green.
    """
    assert load(kb(extra=f'requires_pinakes = ">={__version__}.0"')).kb.name == "research"


def test_the_field_does_not_trip_the_unknown_key_check(kb: Callable[..., Path]) -> None:
    """The self-defeating shape: a field that explains strictness, refused by that same strictness.

    `_check_required_version` reads the raw TOML and leaves the key in place, so `[kb]`'s own
    validator has to consume it too. Miss that and every manifest carrying the field is rejected —
    including, eventually, every manifest.
    """
    manifest = load(kb(extra='requires_pinakes = ">=0.1"'))
    assert manifest.kb.id is not None


@pytest.mark.parametrize(
    "value",
    [
        '"0.6"',  # a bare version: no operator, so what it means is a guess
        '"<=0.6"',  # a ceiling, which the compatibility posture does not have
        '"==0.6"',
        "0.6",  # a TOML float, not a string
        "true",
    ],
)
def test_a_floor_that_is_not_a_lower_bound_is_refused(kb: Callable[..., Path], value: str) -> None:
    """Only `>=` is accepted, and the refusal says so.

    A KB is readable by the pinakes that wrote it or any newer one, so a floor is the only bound
    there is to express. Accepting a second spelling for it — or silently ignoring an operator this
    build does not implement — would be the strictness this module exists to provide, waived at the
    one place it guards a compatibility decision.
    """
    with pytest.raises(ManifestError) as exc_info:
        load(kb(extra=f"requires_pinakes = {value}"))
    assert "only a floor is supported" in exc_info.value.remedy


@pytest.mark.parametrize("value", [">=0.6.x", ">=nine", ">=0..6", ">=", ">= ", ">=٣.٤"])
def test_a_floor_that_is_not_a_dotted_number_is_refused(
    kb: Callable[..., Path], value: str
) -> None:
    """Including Eastern Arabic numerals, which are the interesting case: `"٣".isdigit()` is `True`
    and `int("٣")` is `3`, so a check written with `isdigit()` alone would compare them as a version
    rather than refuse them. That is a silently wrong comparison where this is a refusal."""
    with pytest.raises(ManifestError) as exc_info:
        load(kb(extra=f'requires_pinakes = "{value}"'))
    assert "cannot read" in str(exc_info.value) or "only a floor" in exc_info.value.remedy


@pytest.mark.parametrize("body", ['[sources]\nroots = ["docs/"]\n', 'kb = "not a table"\n'])
def test_a_missing_or_non_table_kb_is_left_to_the_strict_validator(
    write_manifest: Callable[[str], Path], body: str
) -> None:
    """The pre-pass reports one thing and never a second.

    Asserted as **exact equality** against the strict validator's own wording, not as a keyword
    match. The weaker version passed against a deliberately duplicated pre-pass error as long as the
    duplicate happened to contain the same two words — verified by mutation, which is how it was
    caught. Both branches of `isinstance(kb, dict)` are exercised: absent, and present-but-not-a-
    table.
    """
    root = write_manifest(body)
    with pytest.raises(ManifestError) as exc_info:
        load(root)
    expected = (
        f"{root / 'pinakes.toml'} [kb]: is missing"
        if body.startswith("[sources]")
        else f"{root / 'pinakes.toml'}: `kb` must be a table"
    )
    assert str(exc_info.value) == expected


def test_a_version_component_of_absurd_length_is_refused_not_a_traceback(
    kb: Callable[..., Path],
) -> None:
    """`int()` raises above 4300 digits rather than returning a large number (Python 3.11+).

    `"9" * 5000` satisfies `isascii()` and `isdigit()`, so without a length bound it reached `int()`
    and crashed every command with a `ValueError` traceback — on the one code path this increment
    exists to make diagnostic. A refusal is the whole product here; a traceback is the failure it
    was written to remove.
    """
    with pytest.raises(ManifestError) as exc_info:
        load(kb(extra=f'requires_pinakes = ">={"9" * 5000}.0"'))
    assert "cannot read" in str(exc_info.value)


@pytest.mark.parametrize(
    "literal",
    [
        pytest.param('">= 0.9.0"', id="space-after-op"),
        pytest.param('">=0.9.0 "', id="trailing-space"),
        # A TOML escape, not a raw newline: a literal one inside a basic string is a TOML syntax
        # error, so writing it that way would test the TOML parser instead of this check.
        pytest.param(r'">=0.5.0\n"', id="trailing-newline"),
        pytest.param(r'">=\u00a00.9.0"', id="nbsp"),
        pytest.param(r'">=0.9.0\t"', id="tab"),
    ],
)
def test_whitespace_around_the_version_is_refused(kb: Callable[..., Path], literal: str) -> None:
    """One rule, not two.

    An earlier version called `.strip()` on the remainder, which accepted all of these — including
    the non-breaking space, since `str.strip()` is Unicode-aware — while the same function refused
    non-ASCII *digits* on the grounds that leniency there is a silently wrong comparison. The
    documented grammar is `>=` followed by the version, and that is now what is accepted.
    """
    with pytest.raises(ManifestError) as exc_info:
        load(kb(extra=f"requires_pinakes = {literal}"))
    assert "cannot read" in str(exc_info.value)


def test_a_leading_zero_compares_as_the_number_it_is(kb: Callable[..., Path]) -> None:
    """`00.5.0` is `0.5.0`, which is what PEP 440 normalisation does too. Pinned because it is
    accepted silently, and silent acceptance should be deliberate rather than incidental."""
    major, minor, patch = __version__.split(".")
    assert load(kb(extra=f'requires_pinakes = ">=0{major}.{minor}.{patch}"')).kb.name == "research"


def test_a_non_string_value_names_the_toml_type_not_a_python_repr(
    kb: Callable[..., Path],
) -> None:
    """A TOML author sees `2026-01-01` in their file; `datetime.date(2026, 1, 1)` describes our
    runtime, not their mistake."""
    with pytest.raises(ManifestError) as exc_info:
        load(kb(extra="requires_pinakes = 2026-01-01"))
    message = str(exc_info.value)
    assert "datetime" not in message and "date(" not in message
    assert "must be a string" in message


def test_an_unparseable_own_version_skips_the_check_rather_than_crashing(
    kb: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `assert` this replaced was stripped by `python -O`, leaving a `None` to reach `len()`.

    A build whose own version string is unparseable cannot honestly refuse anyone's KB — and
    refusing *every* KB, including ones whose floor it plainly meets, is far worse than leaving an
    advisory check unenforced. A pre-release version still compares, on its numeric head.
    """
    from pinakes import manifest as manifest_module

    monkeypatch.setattr(manifest_module, "__version__", "0.9.0rc1")
    assert load(kb(extra='requires_pinakes = ">=0.5"')).kb.name == "research"
    with pytest.raises(ManifestError):
        load(kb(extra='requires_pinakes = ">=999.0"'))

    monkeypatch.setattr(manifest_module, "__version__", "not-a-version")
    assert load(kb(extra='requires_pinakes = ">=999.0"')).kb.name == "research"


def test_the_template_does_not_stamp_a_floor(tmp_path: Path) -> None:
    """A decision in three documents and, until now, in no test.

    A fresh KB carries no key an older pinakes would choke on, so stamping a floor would lock out
    readers for nothing. Nothing else fails if a future template edit adds it, and what it would
    cause is exactly the lockout the decision exists to prevent.
    """
    from pinakes.init import init

    root = init(tmp_path / "fresh", now="20260801 01:30").root
    assert "requires_pinakes" not in (root / "pinakes.toml").read_text(encoding="utf-8")
