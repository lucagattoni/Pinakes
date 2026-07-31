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


def test_a_malformed_kb_table_is_left_to_the_strict_validator(
    write_manifest: Callable[[str], Path],
) -> None:
    """The pre-pass reports one thing and never a second. `[kb]` missing entirely is the strict
    validator's error, in its own words — a pre-pass that started duplicating those would give two
    different messages for one mistake, and they would drift."""
    root = write_manifest('[sources]\nroots = ["docs/"]\n')
    with pytest.raises(ManifestError) as exc_info:
        load(root)
    assert "kb" in str(exc_info.value) and "missing" in str(exc_info.value)
