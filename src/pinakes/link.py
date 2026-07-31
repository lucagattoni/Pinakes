"""`pnk link` — the one command that writes a link, and the only machine writer of `links[]`.

**Forward only, into the source document's own sidecar** (plans/links-and-graph.md, decision 5).
A link is authored where it is meant; the other end learns about it by reverse-scan (§6.2), never
by having its file edited from outside.

**Never mints.** A source with no sidecar is refused rather than created: a `links[].to` needs the
target's permanent ULID, which only `pnk sync` mints, and building a sidecar here would hand
`write()` a *fresh* id to lay over a file that may already hold a permanent one — the unrecoverable
case `sidecar.create()` exists to refuse. An unreadable source sidecar is reported and left exactly
as it is, for the same reason.

**Three resolution points, easy to conflate.** This module resolves an alias or `self` in the
`<target>` *argument*, before anything is written. `sidecar.read()` resolves a `pnk://self/…`
already on disk. `sidecar.write()` matches entries on the *resolved* URI. Only the first is here.
"""

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from pinakes import sidecar as sidecar_module
from pinakes import uri as uri_module
from pinakes.errors import (
    LinkedKbIdMismatchError,
    LinkedKbUnreachableError,
    PinakesError,
    SidecarError,
)
from pinakes.ids import DocId, KbId
from pinakes.linkscan import MANIFEST_NAME, partner_sources, resolve_path
from pinakes.manifest import LinkedKb, Manifest
from pinakes.sidecar import Link
from pinakes.uri import PnkUri


@dataclass(frozen=True, slots=True)
class LinkOutcome:
    """What one `pnk link` did. `written` is false when the link was already there, byte for
    byte — an authoring command is asked the same thing twice, and rewriting the file to append a
    duplicate entry would be worse than doing nothing."""

    sidecar: Path
    target: PnkUri
    rel: str
    written: bool


def add(manifest: Manifest, *, source: str, target: str, rel: str) -> LinkOutcome:
    """Write one `links[]` entry into `source`'s sidecar. Every failure is a `PinakesError`."""
    relation = rel.strip()
    if not relation:
        # `sidecar._links` refuses an empty `rel` at *read* time, which would surface as a
        # corrupted-file error on a file this command had just written. Refused at the argument.
        raise PinakesError(
            "--rel cannot be empty.",
            remedy="Name the relation, for example `--rel cites` or `--rel supersedes`.",
        )

    path = source_sidecar(manifest, source)
    to = resolve_target(manifest, target)
    existing = sidecar_module.read(path, owner=manifest.kb.id)

    if to.kb == manifest.kb.id and to.doc == existing.id:
        # Refused rather than written. A document related to itself says nothing and would come
        # back as its own neighbour from `pnk links`.
        #
        # **Worded for both ways of arriving here**, because only the ULID is known: the target
        # really is this document (a typo — the same path twice, or a `pnk://` copied out of the
        # file being edited), or it is a *different* file carrying the same id, which is a KB fault
        # in its own right. "would link to itself" alone told someone who had named two different
        # documents that one of them was itself, and pointed at neither the duplicate nor the tool
        # that finds it.
        raise PinakesError(
            f"{source} and the target are the same document ({existing.id}).",
            remedy=(
                "A link goes between two documents. If you meant two different files, they are "
                "sharing a ULID — `pnk doctor` names duplicate ids, and one of them has to be "
                "corrected before either can be linked."
            ),
        )

    link = Link(to=to, rel=relation)
    if link in existing.links:
        return LinkOutcome(sidecar=path, target=to, rel=relation, written=False)

    try:
        sidecar_module.write(path, replace(existing, links=(*existing.links, link)))
    except OSError as exc:
        # `write()` re-raises the `OSError` after removing its temporary file, and the sidecar on
        # disk is untouched. Wrapped so a full disk reaches the user as one line rather than a
        # traceback out of `main`, which only catches `PinakesError`.
        raise SidecarError(path, f"could not be written: {exc.strerror}") from exc
    return LinkOutcome(sidecar=path, target=to, rel=relation, written=True)


def source_sidecar(manifest: Manifest, raw: str) -> Path:
    """The sidecar `pnk link` will write, given `<source>` as the user typed it."""
    document = _document_in(manifest.root, raw, kb="this KB")
    return sidecar_module.sidecar_path(document)


def resolve_target(manifest: Manifest, raw: str) -> PnkUri:
    """`<target>` → a fully resolved `pnk://<kb-ulid>/<doc-ulid>`.

    Three grammars, **in this precedence order**, because they overlap:

    1. a `pnk://` URI — tried first, since it would otherwise split as the alias `pnk`;
    2. `<alias>:<path>`, but **only when the prefix is a declared `[[links.kb]]` name** — a POSIX
       path may legitimately contain a colon, and a stricter rule would refuse to link to
       `docs/2026: a review.md`;
    3. otherwise the whole string, as a path relative to this KB's root.

    A well-formed `pnk://` whose target is not on this machine **is written**: the URI carries both
    ULIDs, nothing here needs the file, and refusing would make an authoring command depend on
    which KBs happen to be checked out. Unresolvable means something narrower — an alias or `self`
    that cannot be turned into a ULID pair at all.
    """
    if raw.startswith(uri_module.SCHEME):
        # `InvalidUriError` is already a `PinakesError` carrying its own remedy. `self` expands to
        # the local KB here, before the entry is written — never on the way back out.
        return uri_module.parse(raw).resolve(owner=manifest.kb.id)

    alias, separator, rest = raw.partition(":")
    linked = manifest.linked_kb(alias) if separator else None
    if linked is not None:
        return _via_alias(linked, rest, local_root=manifest.root)

    try:
        doc = _doc_id_of(manifest.root, raw, manifest.kb.id, "this KB")
    except PinakesError as exc:
        if not separator:
            raise
        # It looked like `<alias>:<path>` and was tried as a path, because that prefix names no
        # `[[links.kb]]`. Saying only "not a document in this KB" answers a question the user did
        # not ask: they think `nope` is a KB. Name what is actually declared.
        raise PinakesError(
            exc.message,
            remedy=f"`{alias}` is not a linked KB either — {_declared(manifest)}. {exc.remedy}",
        ) from exc
    return PnkUri(kb=manifest.kb.id, doc=doc)


def _declared(manifest: Manifest) -> str:
    if not manifest.links:
        return "this manifest declares no `[[links.kb]]` at all"
    names = ", ".join(f"`{linked.name}`" for linked in manifest.links)
    return f"this manifest declares {names}"


def _via_alias(linked: LinkedKb, relative: str, *, local_root: Path) -> PnkUri:
    """`<alias>:<path>` → the partner's own KB ULID and that document's ULID.

    **The partner's `[kb] id`, never the local manifest's declaration of it**, and a disagreement
    is refused rather than resolved — the same rule, for the same reason, as `linkscan`'s rule 1.
    Here it is sharper still: a link written from a stale `[[links.kb]] id` is *permanent* and
    points at a KB that does not exist, and there is no migration machinery to repair it.

    **The refusal is what enforces that, not the choice of variable.** Past it the two ids are
    equal by construction, so substituting `linked.id` at the return changes nothing observable —
    measured: that mutation is caught by no test, while deleting the refusal is caught at once.
    `partner_id` stays because it remains the correct source if the refusal is ever narrowed.
    """
    if not relative.strip():
        raise PinakesError(
            f"`{linked.name}:` names no document.",
            remedy=f"Give the path within that KB, for example `{linked.name}:docs/notes.md`.",
        )

    # Against the *local KB root*, never the working directory: a manifest is committed and
    # shared, so `../partner-kb` has to mean the same place whatever directory `pnk` ran from.
    root = resolve_path(local_root, linked.path)
    if not (root / MANIFEST_NAME).is_file():
        reason = "no pinakes.toml there" if root.is_dir() else "no such directory"
        raise LinkedKbUnreachableError(linked.name, root, reason=reason)

    try:
        partner_id, *_ = partner_sources(root)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise LinkedKbUnreachableError(linked.name, root, reason=str(exc)) from exc

    if partner_id != linked.id:
        raise LinkedKbIdMismatchError(linked.name, declared=str(linked.id), found=str(partner_id))

    return PnkUri(kb=partner_id, doc=_doc_id_of(root, relative, partner_id, f"`{linked.name}`"))


def _doc_id_of(root: Path, raw: str, owner: KbId, kb: str) -> DocId:
    """The permanent ULID of the document at `raw`, read from its sidecar.

    `owner` is that KB's own id, because that is what the sidecar's `self` links mean and `read()`
    requires one. **It is not a safety property here, and an earlier version of this docstring
    claimed it was.** Nothing in this function consumes the resolved links: only `.id` is returned,
    so passing the local id to a partner's file is measurably unobservable — that mutation is caught
    by no test, and the output is byte-identical against a partner sidecar carrying the exact
    retargeting shape. The protection against retargeting lives where the links are *kept*
    (`linkscan.scan_one`, which does read them), not here.
    """
    return sidecar_module.read(
        sidecar_module.sidecar_path(_document_in(root, raw, kb=kb)), owner=owner
    ).id


def _document_in(root: Path, raw: str, *, kb: str) -> Path:
    """`raw` as a path inside `root`, with its document and its sidecar both present.

    Relative to the **KB root**, not the working directory, matching `[[links.kb]] path` and the
    paths `pnk search` prints — a command run three directories deep inside a KB still names the
    same document. An absolute path is accepted when it lands inside that KB, and refused when it
    does not: a link is a fact about a KB's own documents, and `../../elsewhere/notes.md` has no
    ULID this KB may write down.

    **Everything above the final component is resolved; the component itself never is.** The two
    obvious spellings are each wrong in one direction, and this increment shipped both before
    arriving here:

    * `joined.resolve()` follows the final symlink too, so a *symlinked document* — which
      `pnk sync` indexes, `pnk doctor` calls a readable sidecar, and `pnk links` traverses — was
      refused as "outside this KB", with a remedy repeating the path the user had just typed
      correctly. Nothing could link it, in either direction.
    * a purely lexical `os.path.normpath` follows nothing, so a symlinked **directory** under
      `docs/` passed containment and the write went out of the KB through it — and, in the other
      direction, wrote a *permanent* `pnk://` to a ULID this KB will never index, because
      `Path.glob` does not recurse a symlinked directory. It also refused a legitimate absolute
      path whose *ancestor* is a symlink, which is the ordinary shape on macOS (`/tmp` →
      `/private/tmp`) and for any checkout behind one — `manifest.load` resolves the root, so a
      verbatim comparison could never match.

    Resolving the parent alone gets both: the directory chain is followed, so an escape through it
    is caught and a symlinked ancestor lands inside; the final component is left alone, so the
    document's own symlink is irrelevant — which is right, because what decides membership is the
    path under `[sources]`, and `Path.glob` does yield a symlinked *file*.

    **`normpath` is not applied first, deliberately.** It would collapse
    `docs/link-to-elsewhere/../x.md` to `docs/x.md` textually, turning an escaping path into one
    that looks contained — the opposite of what the check is for. `resolve()` on the parent
    collapses `..` correctly, after following the links it sits behind.

    No `expanduser()` either: this argument is documented as KB-root-relative, so a successfully
    expanded `~` lands in `$HOME` and is refused by the very next line — it bought nothing and
    raised `RuntimeError`, which is not a `PinakesError`, straight out through `cli.main` as a
    traceback.
    """
    given = Path(raw)
    joined = given if given.is_absolute() else root / given
    document = joined.parent.resolve() / joined.name
    if not document.is_relative_to(root):
        raise PinakesError(
            f"{raw!r} is outside {kb}.",
            remedy="Give a path relative to that KB's root, for example `docs/notes.md`.",
        )
    if sidecar_module.is_sidecar(document):
        # Tab completion offers the sidecar as readily as the document, and `write()` would
        # otherwise be handed `notes.md.pnk.yaml.pnk.yaml` — a second sidecar for a file that is
        # itself one.
        raise PinakesError(
            f"{raw!r} is a sidecar, not a document.",
            remedy=f"Name the document itself: `{sidecar_module.document_for(document).name}`.",
        )

    path = sidecar_module.sidecar_path(document)
    if not document.is_file():
        raise PinakesError(
            f"{raw!r} is not a document in {kb}.",
            remedy="Give a path relative to that KB's root, as `pnk search` prints it.",
        )
    if not path.is_file():
        raise PinakesError(
            f"{raw!r} has no sidecar, so it has no ULID to link.",
            remedy=(
                "Run `pnk sync` in that KB first — it mints the sidecar carrying the document's "
                "permanent ULID. `pnk link` never mints one: a fresh id written over a file that "
                "already holds a permanent one breaks every inbound link, and nothing can undo it."
            ),
        )
    return document
