"""`paths.lands_inside` — the predicate two callers share, tested where it lives.

The extraction that created this module is asserted to be behaviour-preserving by the *existing*
`[sources] include` containment tests, which pass unchanged (`tests/test_sync.py`,
`tests/test_manifest.py`). This file is the other half: the predicate's own cases, stated once
rather than inferred from a manifest error message, so the next caller that needs it can read what
it promises without reconstructing it from `include` semantics.
"""

from pathlib import Path

import pytest

from pinakes.paths import lands_inside


def test_a_dot_dot_that_stays_inside_is_accepted(tmp_path: Path) -> None:
    """Refusing a valid input is the same defect as accepting an invalid one.

    `../notes/x.md` from `docs/` lands inside the KB and is a legitimate thing to write, which is
    why the predicate measures where a path lands and never whether `..` occurs in it.
    """
    anchor = tmp_path.resolve()
    (tmp_path / "docs").mkdir()
    (tmp_path / "notes").mkdir()

    assert lands_inside(anchor, tmp_path / "docs", "../notes/x.md")


def test_a_dot_dot_that_walks_out_is_refused(tmp_path: Path) -> None:
    anchor = (tmp_path / "kb").resolve()
    (tmp_path / "kb").mkdir()

    assert not lands_inside(anchor, tmp_path / "kb", "../../evil.md")


def test_a_symlinked_leaf_stays_readable(tmp_path: Path) -> None:
    """Resolving the *whole* path would refuse this, and it is a file the caller must be able to
    reach: a document inside the KB that happens to be a symlink is still a document inside the KB.
    """
    anchor = (tmp_path / "kb").resolve()
    (tmp_path / "kb").mkdir()
    (tmp_path / "elsewhere.md").write_text("target\n", encoding="utf-8")
    (tmp_path / "kb" / "alpha.md").symlink_to(tmp_path / "elsewhere.md")

    assert lands_inside(anchor, tmp_path / "kb", "alpha.md")


def test_a_symlinked_ancestor_is_caught(tmp_path: Path) -> None:
    """The counterpart to the case above, and why the *parent* is resolved even though the leaf is
    not. The escape here exists only on disk — no `..`, no absolute path, nothing lexical to see.
    """
    anchor = (tmp_path / "kb").resolve()
    (tmp_path / "kb").mkdir()
    (tmp_path / "outside").mkdir()
    (tmp_path / "kb" / "escape").symlink_to(tmp_path / "outside", target_is_directory=True)

    assert not lands_inside(anchor, tmp_path / "kb", "escape/evil.md")


def test_a_trailing_dot_dot_is_refused(tmp_path: Path) -> None:
    """The exemption, and the hole it closes.

    `Path("/kb/..").is_relative_to("/kb")` is lexically **true**, so leaving the final component
    unresolved — which is what keeps a symlinked leaf readable — would let a trailing `..` escape
    through that same leniency. Nothing a caller wants is *named* `..`, so it is resolved whole.
    """
    anchor = (tmp_path / "kb").resolve()
    (tmp_path / "kb").mkdir()

    assert not lands_inside(anchor, tmp_path / "kb", "..")


def test_an_embedded_nul_raises_rather_than_answering_false(tmp_path: Path) -> None:
    """`resolve()` raises on paths a TOML string can legally hold, and that propagates.

    Answering `False` would report "reaches outside the KB" for something that is in fact
    unreadable, sending the user to fix the wrong thing. Each caller wraps it in its own error.
    """
    anchor = tmp_path.resolve()

    with pytest.raises((ValueError, OSError)):
        lands_inside(anchor, tmp_path, "a\x00b/x.md")
