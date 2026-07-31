"""Reverse-scan: what the *other* KBs say points at this one (docs/DESIGN.md §6.2).

A `links[]` entry is written in the source document's sidecar and points forward. That is the whole
authoring model, and it means a KB has no way of knowing who links *to* it without asking. This
module asks: for each `[[links.kb]]`, read that KB's committed sidecars and keep the entries whose
target is us.

**Committed sidecars, never the partner's index.** An index is disposable, machine-local, and may
not exist at all — a freshly cloned KB has sidecars and nothing else. Reading one would also mean
holding a second KB's lock, which §6.2 forbids: a cross-KB read must never be able to block a
partner's own sync.

**But the partner's `pinakes.toml` is read too, and must be.** A sidecar carries `id`, `title`,
`tags`, `created`, `links`, `provenance` — and *not* the KB it belongs to. So "sidecars alone"
cannot supply `links.src_kb_id`, cannot key `kb_refs.kb_id`, and cannot even locate the sidecars,
which live under the partner's own `[sources] roots` and need not be in `docs/`. Three rules follow:

1. `src_kb_id` comes from the partner's **`[kb] id`**, never from the local manifest's declared
   `[[links.kb]] id`. When they disagree that is a recorded failure, not a guess — attributing one
   KB's links to another is exactly the confusion permanent ULIDs exist to prevent.
2. Sidecars are enumerated from the partner's `[sources]`.
3. **Partner sidecars are read with the partner's own id as `owner`.** Both pre-existing
   `read_sidecar` call sites hard-code the *local* KB, and reusing either would expand a partner's
   `pnk://self/<doc>` to us — minting rows claiming the partner links to local documents it never
   named. That defect was found and fixed once already (docs/RETROSPECTIVES.md: *"a sidecar copied
   into another KB would silently retarget its link at the new KB"*), and `tests/partner-kb/`
   carries a hand-authored `self` link so it cannot come back unnoticed.

**Only links targeting *this* KB are kept.** A partner's link to a third KB is read and discarded.
Recording it would accumulate a foreign graph this index can never complete, and a partial view of
someone else's links is the silently-incomplete answer §6.2 refuses.

**Nothing here raises.** Every failure is a `LinkScanError` *constructed* and returned, because
`pnk sync` runs on three git hooks and a partner that is simply not on this machine must not turn
every commit red. The caller decides what to do with them; `SyncReport.ok` does not count them.
"""

import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from pinakes.errors import (
    LinkedKbIdMismatchError,
    LinkedKbUnreachableError,
    LinkedSidecarUnreadableError,
    LinkScanError,
    LinkTargetMissingError,
    PinakesError,
)
from pinakes.ids import DocId, KbId, parse_kb_id
from pinakes.manifest import LinkedKb, Manifest
from pinakes.sidecar import SIDECAR_SUFFIX
from pinakes.sidecar import read as read_sidecar

MANIFEST_NAME = "pinakes.toml"

TTL_MINUTES = 60
"""How stale an inbound-link picture may be before a plain `pnk sync` re-reads a partner.

A code constant rather than a manifest key, deliberately: "how stale may a cross-KB link be" is a
question about *this* engine's cost model, not about a KB, and a per-KB knob would be one more
thing to get wrong in a file people hand-edit. `--scan-links` forces a re-read regardless.

Sixty minutes because the walk runs on `post-commit` and `post-merge`: a partner with a thousand
sidecars costs a thousand small reads, and paying that on every commit to make an *inbound* link
appear an hour sooner is the wrong trade. `pnk doctor` reports the age.
"""


@dataclass(frozen=True, slots=True)
class ReverseRow:
    """One inbound edge: `src` is a document in the *other* KB, `dst` is one of ours."""

    src_kb_id: KbId
    src_doc_id: DocId
    dst_doc_id: DocId
    rel: str


@dataclass(frozen=True, slots=True)
class ScannedKb:
    """The outcome of walking one `[[links.kb]]`."""

    alias: str
    declared_id: KbId
    path: Path
    """Resolved against the local KB root — what `kb_refs.path` records.

    **Always absolute, on every row.** The one exception is the row `scan_one` returns when
    `resolve_path` answers `None`: there this is the declared text, for the message alone, and that
    row carries an issue and never `complete`, so `sync` cannot persist it. Review 7 made that the
    *general* fallback and review 8 measured the consequence — a relative path walked from the
    working directory. Keep it absolute: five call sites use it as a filesystem base.
    """

    kb_id: KbId | None = None
    """The partner's *own* `[kb] id` — except on a `skipped_fresh` row, where nothing was read and
    this is the locally declared `[[links.kb]] id`. `None` when it could not be established.

    The exception is safe only because `sync` `continue`s on `skipped_fresh` before reading it. A
    reader that does not (L7's `pnk doctor` is the obvious next one) would be taking the local
    declaration for the partner's own — the confusion rule 1 of the module docstring exists to
    prevent."""

    rows: tuple[ReverseRow, ...] = ()
    issues: tuple[LinkScanError, ...] = ()

    complete: bool = False
    """The walk finished with no failure that could have hidden rows.

    **This is what licenses the delete.** Replacing a partner's rows means deleting all of them
    first, and they only come back if every sidecar was then re-read successfully — so a vanished
    file or an unparseable sidecar mid-walk would be a mass deletion of edges that are still true.
    An incomplete walk keeps whatever was already known and records why.

    A *missing target* does not clear this: the row is still recorded, and the partner's claim is
    real whether or not we have the document it names.
    """

    skipped_fresh: bool = False
    """Skipped because `kb_refs.last_scan` is inside the TTL. Distinct from `complete`: nothing was
    read, so nothing may be deleted either."""


@dataclass(frozen=True, slots=True)
class ScanResult:
    scanned: tuple[ScannedKb, ...] = ()

    @property
    def issues(self) -> tuple[LinkScanError, ...]:
        return tuple(issue for kb in self.scanned for issue in kb.issues)


def resolve_path(root: Path, raw: str) -> Path | None:
    """`[[links.kb]] path` → an absolute path, or `None` when the text names no path at all.

    Relative to the KB root rather than the process's working directory, because a manifest is
    committed and shared: `../partner-kb` has to mean the same thing whatever directory `pnk` was
    invoked from. An absolute path is honoured as given — and warned about by `pnk doctor` (L7),
    since a committed absolute path publishes a filesystem layout.

    **It never raises, whatever the manifest says.** `raw` is user-written text from a committed
    file, and both calls below reject some of it — `expanduser()` raises `RuntimeError` for an
    unknown user (`~someone/kb`), `resolve()` raises `ValueError` for an embedded NUL, which
    `tomllib` accepts and `manifest.py` does not filter. Neither is a `PinakesError`, so both
    reached `cli.main` as a traceback.

    **Handled here rather than at the call sites, because fixing it at call sites is what produced
    six instances of it.** L6 wrapped this call in `_via_alias`, then in `scan_one`, and the seventh
    review pass still found it bare in `scan()`'s freshness branch — which plain `pnk sync` takes,
    so a `~` path that stops resolving turned every `git commit` inside the TTL into a traceback.
    A function that three call sites each had to remember to guard is a function with the wrong
    contract.

    **`None`, never the declared text as a fallback.** The seventh round returned `Path(raw)` so an
    error could name what the author wrote, and that value is *relative* — every consumer uses it
    as a filesystem base (`(path / MANIFEST_NAME).is_file()`, `why_not_a_kb`, `partner_sources`,
    `sidecars_under`, `_doc_id_of`), so the walk silently re-anchored on the **working directory**:
    the one thing the paragraph above says this function exists to prevent. Measured in review 8 —
    with a directory of that literal name in the CWD holding a `pinakes.toml`, `pnk sync` walked
    it, found nothing, stamped the scan `complete` and deleted every inbound row the real partner
    had. `None` cannot be walked, and pyright makes each caller say what it does instead. The
    declared text stays available for the *message* — it is `linked.path`, which every caller
    already holds.
    """
    try:
        return _resolve(root, raw)
    except (RuntimeError, ValueError, OSError):
        return None


def _resolve(root: Path, raw: str) -> Path:
    expanded = Path(raw).expanduser()
    # `.resolve()` on both branches: `kb_refs.path` is shown to a person and compared by later
    # increments, and `/a/b/../c` is the same place as `/a/c` written two ways.
    return (expanded if expanded.is_absolute() else root / expanded).resolve()


def why_unresolvable(root: Path, raw: str) -> str:
    """Why `resolve_path` returned `None`, naming the actual fault rather than the category.

    **The reason alone, no path** — the same register as `why_not_a_kb`, because
    `LinkedKbUnreachableError` interpolates the path itself. A first version included it and read
    `cannot be read at ~nosuchuser/kb: '~nosuchuser/kb' cannot be resolved to a path: …`.

    Shares `_resolve` with `resolve_path` rather than repeating its two lines, so the reason cannot
    drift from the rule it explains. Called only once the answer is already known to be `None`.
    """
    try:
        _resolve(root, raw)
    except RuntimeError as exc:
        return f"the `~` cannot be expanded: {exc}"
    except (ValueError, OSError) as exc:
        return f"not a usable path: {exc}"
    return "not a usable path"


def why_not_a_kb(path: Path) -> str:
    """Why `path` holds no readable `pinakes.toml`, in words that name the actual situation.

    Five cases, not two. A two-way `is_dir()` split reported a `[[links.kb]] path` that points at
    an existing *regular file* as "no such directory", which is the one answer a person would check
    and find false — the path is right there.

    **The last two are the same defect, one level down**, and the three-way split had it too: the
    caller's probe is `is_file()`, so a `pinakes.toml` that exists but is a directory, or is a
    symlink to nothing, was reported as "no pinakes.toml there" — with the file visible in `ls`.
    Found in review 9 by reading this docstring's own justification against its code.

    **Unlike `resolve_path`, this one may raise, and the callers guard it.** `exists()`,
    `is_symlink()` and `is_dir()` raise on an unreadable parent (`~root` on macOS is mode 0700) and
    on `ENAMETOOLONG`. Both call sites place it inside their `except OSError`, verified. Stated
    rather than fixed: the totality argument that applies to `resolve_path` does not, because there
    is no answer this function could return for "I could not tell" that a caller would not have to
    branch on anyway — and every caller is already branching. L7's `pnk doctor` will be the third
    caller; it needs the same `try`.
    """
    if not path.exists():
        return "no such directory"
    if not path.is_dir():
        return "not a directory"
    manifest = path / MANIFEST_NAME
    if manifest.is_symlink() and not manifest.exists():
        return "the pinakes.toml there is a broken symlink"
    if manifest.exists():
        return "the pinakes.toml there is not a regular file"
    return "no pinakes.toml there"


def partner_sources(root: Path) -> tuple[KbId, list[str], list[str], list[str]]:
    """`([kb] id, roots, include, exclude)` from a partner's manifest.

    **`exclude` is not optional to read.** The shipped `notes` template stamps
    `exclude = ["**/drafts/**"]`, so it is present in every KB `pnk init` creates — ignoring it
    meant recording inbound links from documents the partner's own KB does not contain.

    Read with `tomllib` directly rather than through `manifest.load`, which validates the *whole*
    file against this pinakes' schema. A partner may legitimately be running a newer version with
    keys we do not know — `[kb] requires_pinakes` (G4) exists precisely for that — and refusing to
    read a neighbour's inbound links because its manifest mentions a key we have not shipped yet
    would make every connected KB a version dependency of every other.
    """
    with (root / MANIFEST_NAME).open("rb") as handle:
        data = tomllib.load(handle)

    def table(name: str) -> dict[str, object]:
        raw: object = data.get(name)
        if not isinstance(raw, dict):
            raise ValueError(f"no [{name}] table")
        return cast(dict[str, object], raw)

    identifier = table("kb").get("id")
    if not isinstance(identifier, str):
        raise ValueError("no [kb] id")

    sources = table("sources")

    def strings(key: str, default: list[str]) -> list[str]:
        raw = sources.get(key)
        if not isinstance(raw, list):
            return default
        values = [value for value in cast(list[object], raw) if isinstance(value, str)]
        return values or default

    return (
        parse_kb_id(identifier),
        strings("roots", ["docs/"]),
        strings("include", ["**/*.md"]),
        strings("exclude", []),
    )


def sidecars_under(
    root: Path, roots: list[str], include: list[str], exclude: list[str]
) -> tuple[list[Path], list[str]]:
    """Every sidecar beside a document the partner's own `[sources]` would ingest, and what went
    wrong — `(sidecars, problems)`.

    Driven from the *documents* rather than by globbing `**/*.pnk.yaml`, so a stray sidecar outside
    the partner's roots, or one whose document its `exclude` removes, contributes nothing. What the
    partner does not consider part of its KB is not something this KB may record links from.

    **Every input here is partner-controlled, and none of it went through `manifest.load`.** That
    bypass is deliberate — a partner may run a newer pinakes with keys this one does not know — but
    it also skipped the validation `load` performs, so this function has to do it:

    * a `roots` entry that resolves outside the partner KB is refused. `manifest._sources` already
      rejects absolute roots and `..`; without the same check here, a partner manifest could point
      the walk at any directory on this machine, and `roots = ["/"]` would be an unbounded walk on
      a `post-commit` hook.
    * a `roots` entry that is **not a directory** is a *problem*, never a quiet skip. Skipping it
      yielded zero sidecars, which reads as "this partner has no inbound links" — and the caller
      then deletes every row it had. A partner renaming its own `docs/` silently destroyed the
      whole inbound picture and stamped the scan as fresh.
    * **an `include` pattern that escapes the KB is refused too, in two halves.** `include` is
      exactly as partner-controlled as `roots`, and the check above was implemented for `roots`
      alone — so `include = ["../../outside/*.md"]` walked out of the partner KB and this one
      recorded inbound links from files the partner does not own. `candidate.relative_to(root)` did
      not catch it: `relative_to` is purely lexical, so `docs/../../outside/planted.md` *is*
      relative to the root as a string. Containment has to resolve.

      A `..` or absolute pattern is refused **before** globbing, because that is what bounds the
      walk — checking each candidate afterwards refuses the results while still paying for the
      enumeration, which was the whole point of the `roots` rule. What no static check can see is a
      **symlinked directory**, so the per-candidate test remains, spelled as `link._document_in`
      spells it (parent resolved, final component not) so a symlinked *document* inside the KB
      stays readable — and it `break`s, which bounds that half.

      Found in review 10 by testing this docstring's own argument against the code below it, and
      completed in review 11 by testing the *fix's* argument the same way.
    """
    found: set[Path] = set()
    problems: list[str] = []
    anchor = root.resolve()
    # One entry per *pattern*, collected across every root and reported once at the end: a partner
    # with two roots reported the same escape twice. Not "per match" — the `break` below already
    # yields at most one per (root, pattern), and a `..` pattern never reaches it at all.
    escaping: set[str] = set()
    # `parent.resolve()` is a syscall chain per candidate, and a large KB globs thousands of files
    # out of a handful of directories.
    resolved: dict[Path, Path] = {}
    for name in roots:
        base = (root / name).resolve()
        if not base.is_relative_to(anchor):
            problems.append(f"[sources] roots entry {name!r} points outside the KB")
            continue
        if not base.is_dir():
            problems.append(f"[sources] roots entry {name!r} is not a directory")
            continue
        for pattern in include:
            if pattern in escaping:
                continue  # an optimisation only — `escaping` is a set, which is what dedupes
            # **Refused before globbing, which is what bounds the walk.** The per-candidate check
            # below cannot: `glob` has already enumerated and stat'd the whole tree by the time the
            # first match is inspected, so `include = ["../../../../**/*.md"]` walked the machine
            # on every `post-commit` even though nothing was collected. The `roots` branch above
            # gets this right by `continue`ing before it walks.
            #
            # **What is tested is where the pattern's fixed prefix lands, not whether it contains
            # `..`.** A first version refused any `..`, which refuses `../notes/*.md` — a pattern
            # that stays *inside* the KB and that the partner's own `walk_sources` ingests. This KB
            # then called a legitimate manifest an escape, and because that sets `complete` false
            # it never wrote `last_scan`, so the partner was re-read, re-refused and never
            # refreshed on every sync forever. Disagreeing with the partner about its own KB is
            # wrong in this direction too — the rule review 11 stated for `exclude` and broke one
            # branch above it.
            #
            # Resolving the prefix costs one `resolve()` and no enumeration, so the bound survives.
            if Path(pattern).is_absolute():
                # `glob` raises `NotImplementedError` on this anyway, and `scan_one` catches it —
                # named here only so the report says which pattern rather than which exception.
                escaping.add(pattern)
                continue
            fixed: list[str] = []
            for part in Path(pattern).parts:
                if any(char in part for char in "*?["):
                    break
                fixed.append(part)
            if not base.joinpath(*fixed).resolve().is_relative_to(anchor):
                escaping.add(pattern)
                continue
            for candidate in base.glob(pattern):
                parent = resolved.get(candidate.parent)
                if parent is None:
                    parent = candidate.parent.resolve()
                    resolved[candidate.parent] = parent
                # **Containment before the `is_file` skip**, not after: a pattern reaching outside
                # that matched only sidecars or only directories was skipped by that `continue` and
                # never recorded as an escape, so the walk left the KB and reported nothing.
                if not (parent / candidate.name).is_relative_to(anchor):
                    escaping.add(pattern)
                    break  # bounds a symlinked-directory escape, which no static check can see
                if not candidate.is_file() or candidate.name.endswith(SIDECAR_SUFFIX):
                    continue
                # **`exclude` matches the *unresolved* path**, as it did before the containment
                # check existed and as the partner's own `walk_sources` does. Matching the resolved
                # one silently changed which rules fire — with `docs/alias -> docs/real` inside the
                # KB, `exclude = ["docs/real/*"]` began excluding documents reached as
                # `docs/alias/…`, and an excluded document is a dropped sidecar, which with
                # `complete` true is a deleted inbound row. This KB must exclude exactly what the
                # partner excludes; disagreeing in either direction is a wrong answer about someone
                # else's KB.
                relative = candidate.relative_to(anchor).as_posix()
                if any(candidate.match(rule) or Path(relative).match(rule) for rule in exclude):
                    continue
                sidecar = candidate.with_name(candidate.name + SIDECAR_SUFFIX)
                if sidecar.is_file():
                    found.add(sidecar)
    problems.extend(
        f"[sources] include pattern {pattern!r} reaches outside the KB"
        for pattern in sorted(escaping)
    )
    return sorted(found), problems


def scan_one(
    linked: LinkedKb,
    *,
    local_root: Path,
    local_kb: KbId,
    known_documents: frozenset[DocId] | None,
) -> ScannedKb:
    """Walk one linked KB. Never raises: every failure comes back in `issues`.

    `known_documents=None` means *this run does not know which documents exist* — a sync whose own
    document loop failed has an incomplete picture, and reporting a partner's link as pointing at a
    missing document would be blaming the partner for our failure. The rows are still recorded;
    they come from the partner's sidecars and owe nothing to our local state.
    """
    # **The probe goes inside the `try`, because "never raises" was not true of it.** `is_file` and
    # `is_dir` swallow a missing path and nothing else, so an unreadable partner directory raises
    # `PermissionError` — which turned `pnk sync` on a `post-commit` hook into a traceback, the
    # exact failure this module's promise exists to prevent, from the lines that ran before any of
    # the handling did. Found by grepping the module for calls that touch the filesystem, after the
    # same class had been fixed four times one instance at a time in `link.py` (L6).
    # `resolve_path` sits *outside* the `try` because it does not raise (see its docstring): the
    # earlier fix wrapped it here, which the class's sixth instance showed to be the wrong shape —
    # the guarantee belongs to the function, not to each caller. It answers `None` for text that
    # names no path, and that is returned here rather than walked: review 8 measured the previous
    # declared-text fallback re-anchoring the whole walk on the working directory.
    resolved = resolve_path(local_root, linked.path)
    if resolved is None:
        declared = Path(linked.path)
        return _with(
            ScannedKb(alias=linked.name, declared_id=linked.id, path=declared),
            issues=(
                LinkedKbUnreachableError(
                    linked.name, declared, reason=why_unresolvable(local_root, linked.path)
                ),
            ),
        )

    path = resolved
    base = ScannedKb(alias=linked.name, declared_id=linked.id, path=path)
    try:
        if not (path / MANIFEST_NAME).is_file():
            return _with(
                base,
                issues=(LinkedKbUnreachableError(linked.name, path, reason=why_not_a_kb(path)),),
            )
    except OSError as exc:
        return _with(
            base,
            issues=(LinkedKbUnreachableError(linked.name, path, reason=exc.strerror or str(exc)),),
        )

    try:
        partner_id, roots, include, exclude = partner_sources(path)
    except (OSError, ValueError, tomllib.TOMLDecodeError, PinakesError) as exc:
        return _with(base, issues=(LinkedKbUnreachableError(linked.name, path, reason=str(exc)),))

    if partner_id != linked.id:
        # Refused rather than resolved. Trusting the manifest's declaration would file another
        # KB's links under this alias; trusting the partner would silently redirect a link the
        # local author wrote deliberately. Both are wrong, and a permanent ULID means one of the
        # two is simply a mistake to fix.
        return _with(
            base,
            kb_id=partner_id,
            issues=(
                LinkedKbIdMismatchError(
                    linked.name, declared=str(linked.id), found=str(partner_id)
                ),
            ),
        )

    rows: list[ReverseRow] = []
    issues: list[LinkScanError] = []
    complete = True
    missing: list[DocId] = []

    try:
        # Inside the try, not outside it. `glob` raises on patterns `manifest.load` would have
        # rejected — `NotImplementedError` for a non-relative pattern, `ValueError` for an empty
        # one — and every one of those inputs comes from a *partner's* manifest. Outside the try
        # they escaped `sync()` entirely and crashed `pnk sync` on a git hook, which is exactly the
        # "nothing here raises" promise this module is built on.
        found, problems = sidecars_under(path, roots, include, exclude)
    except (OSError, ValueError, NotImplementedError, PinakesError) as exc:
        return _with(
            base,
            kb_id=partner_id,
            issues=(LinkedKbUnreachableError(linked.name, path, reason=f"[sources] {exc}"),),
        )

    for problem in problems:
        # A walk failure, never a quiet skip: zero sidecars reads as "no inbound links", and the
        # caller then deletes every row this partner had.
        issues.append(LinkedKbUnreachableError(linked.name, path, reason=problem))
        complete = False

    for sidecar in found:
        try:
            # `owner=partner_id`, never the local KB — see the module docstring.
            parsed = read_sidecar(sidecar, owner=partner_id)
        except PinakesError as exc:
            issues.append(LinkedSidecarUnreadableError(linked.name, sidecar, reason=exc.message))
            complete = False
            continue
        for link in parsed.links:
            if link.to.kb != local_kb:
                continue  # a third KB's business, and a partial view of it would be a lie
            if known_documents is not None and link.to.doc not in known_documents:
                missing.append(link.to.doc)
            rows.append(
                ReverseRow(
                    src_kb_id=partner_id,
                    src_doc_id=parsed.id,
                    dst_doc_id=link.to.doc,
                    rel=link.rel,
                )
            )

    if missing:
        issues.append(
            LinkTargetMissingError(linked.name, doc_id=str(missing[0]), count=len(missing))
        )

    return _with(
        base,
        kb_id=partner_id,
        rows=tuple(rows),
        issues=tuple(issues),
        complete=complete,
    )


def _with(
    base: ScannedKb,
    *,
    kb_id: KbId | None = None,
    rows: tuple[ReverseRow, ...] = (),
    issues: tuple[LinkScanError, ...] = (),
    complete: bool = False,
) -> ScannedKb:
    """Explicit keywords, not `**changes: object`.

    `KbId` is a `NewType`, so the obvious `isinstance`-based unpacking of a `**kwargs` bag does not
    type-check at all — and a helper that has to lie to the checker about what it received is a
    helper that will eventually be handed the wrong thing.
    """
    return ScannedKb(
        alias=base.alias,
        declared_id=base.declared_id,
        path=base.path,
        kb_id=kb_id,
        rows=rows,
        issues=issues,
        complete=complete,
    )


def is_stale(last_scan: str | None, now: str, *, ttl_minutes: int = TTL_MINUTES) -> bool:
    """Whether a partner is due a re-read.

    Both stamps are `%Y%m%d %H:%M` — minute resolution, local time, no zone — because that is what
    `sync()` already writes everywhere else and a second time format in one index would be worse
    than the coarseness. So the TTL is whole minutes, and a scan is never *not* due when the answer
    is uncertain:

    * no `last_scan` at all → stale (nothing is known yet);
    * a stamp that will not parse → stale (a hand-edited or future-format value must not be read
      as "recent", which would suppress the scan silently and forever);
    * a stamp **in the future** → stale. The clock moved backwards, or the file came from another
      machine. Treating it as fresh would suppress every scan until real time caught up, which is
      the one failure mode with no symptom.
    """
    if last_scan is None:
        return True
    fmt = "%Y%m%d %H:%M"
    try:
        then = datetime.strptime(last_scan, fmt)
        current = datetime.strptime(now, fmt)
    except ValueError:
        return True
    if then > current:
        return True
    return (current - then).total_seconds() >= ttl_minutes * 60


def scan(
    manifest: Manifest,
    *,
    local_documents: frozenset[DocId] | None,
    last_scans: dict[str, str],
    now: str,
    force: bool = False,
) -> ScanResult:
    """Walk every `[[links.kb]]`, skipping the ones still inside the TTL.

    Sweeping a *delisted* KB's rows is the caller's job, through `store.forget_reverse_links` —
    it needs the index, and this module deliberately does not have one.
    """
    scanned: list[ScannedKb] = []
    for linked in manifest.links:
        resolved = None if force else resolve_path(manifest.root, linked.path)
        # `resolve_path(...) is None` **falls through to the walk** rather than being fresh-skipped.
        # A path that names nothing is a broken manifest, and the TTL exists to skip re-reading a
        # partner that was fine an hour ago — not to withhold the reason a partner is unreachable
        # for the rest of the hour. `scan_one` reports it and returns immediately, so the
        # fall-through costs nothing. It also keeps `ScannedKb.path` a real `Path`: the alternative
        # was a nullable field on a row `sync` stringifies.
        if resolved is not None and not is_stale(last_scans.get(str(linked.id)), now):
            scanned.append(
                ScannedKb(
                    alias=linked.name,
                    declared_id=linked.id,
                    path=resolved,
                    kb_id=linked.id,
                    skipped_fresh=True,
                )
            )
            continue
        scanned.append(
            scan_one(
                linked,
                local_root=manifest.root,
                local_kb=manifest.kb.id,
                known_documents=local_documents,
            )
        )

    return ScanResult(scanned=tuple(scanned))
