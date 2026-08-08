"""Where a relative path *lands* — the one predicate two callers share.

A `[sources] include` pattern and a template's declared `files` entry both name something relative
that must end up inside a known directory, and both are read from a file Pinakes does not write.
The test they need is the same one, and `manifest._check_include_containment` records four attempts
at it that each got it wrong differently — so it lives here once rather than being re-derived by
the next caller that needs it.
"""

from pathlib import Path


def lands_inside(anchor: Path, base: Path, relative: str) -> bool:
    """Does `relative`, joined onto `base`, land inside `anchor`?

    **The parent is resolved and the final component is not**, which is the whole of it. Three of
    the four recorded failed attempts are here; the fourth — resolving the fixed prefix before the
    first glob component — is about globbing rather than landing and stayed with
    `manifest._check_include_containment`. Each of these fails on a case the callers really meet:

    * **Not "does it contain `..`"** — `../notes/x.md` from `docs/` lands *inside* and is a
      legitimate thing to write. What matters is where the path lands, never whether `..` occurs in
      it. Refusing a valid input is the same defect as accepting an invalid one.
    * **Not "resolve nothing"** — that is purely lexical, and `Path("/kb/../outside/x")` *is*
      relative to `/kb` as a string.
    * **Not "resolve the whole path"** — that follows a final symlink, so a symlinked *document*
      would be refused as an escape while a glob naming the same file is accepted.

    Parent resolved, final component left alone: `..` collapses, a symlinked *ancestor* is caught,
    and a symlinked leaf stays readable.

    **A trailing `..` is the exemption to that**, and it is not a corner case — it is the hole the
    leniency above would otherwise open. `Path("/kb/..").is_relative_to("/kb")` is lexically
    **true**, so leaving that final component unresolved would let it through. It is resolved whole
    instead, which is safe because nothing a caller wants to read or write is *named* `..`.

    **Glob syntax is the caller's to strip before calling.** `**` matches zero or more components
    while `Path.parts` counts it as one, and what that means for a following `..` is a fact about
    globs rather than about landing. `manifest` drops it; a template's `files` entry is literal and
    has nothing to drop.

    `resolve()` raises `OSError` or `ValueError` on paths a TOML string can legally hold — an
    embedded NUL, for one. **That propagates deliberately**: each caller has its own error type and
    its own message, and answering `False` here would report "reaches outside the KB" for something
    that is in fact unreadable, sending the user to fix the wrong thing.
    """
    probe = base.joinpath(*Path(relative).parts)
    landing = probe.resolve() if probe.name == ".." else probe.parent.resolve() / probe.name
    return landing.is_relative_to(anchor)
