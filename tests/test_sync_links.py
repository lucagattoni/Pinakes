"""Reverse-scan: inbound links, `kb_refs`, and the deletes that keep them true (§6.2).

Every fixture here builds **two real KBs on disk** that name each other. A single-KB fixture cannot
exercise any of this: the whole increment is about what one KB learns by reading another's
committed sidecars, and the interesting failures — a partner's `self` link, an id mismatch, a
half-read walk — only exist when there is a second manifest to disagree with.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from pinakes import linkscan, store
from pinakes.embed import EmbeddingBackend, ModelInfo, Vectors
from pinakes.errors import SyncError
from pinakes.ids import DocId, KbId, mint_doc_id, mint_kb_id
from pinakes.linkscan import (
    TTL_MINUTES,
    is_stale,
    resolve_path,
    sidecars_under,
    why_unresolvable,
)
from pinakes.manifest import load
from pinakes.sidecar import SIDECAR_SUFFIX
from pinakes.sync import SyncOptions, SyncReport, sync

DIM = 8


class FakeBackend:
    """Deterministic and instant — what is under test is the scan, not a model."""

    def embed(self, texts: Sequence[str]) -> Vectors:
        listed = list(texts)
        if not listed:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.ascontiguousarray(
            np.vstack([np.full(DIM, (len(text) % 7) / 7.0, dtype=np.float32) for text in listed]),
            dtype=np.float32,
        )

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", "rev1", DIM, 512)


def fake_factory(_manifest: Any, _offline: bool) -> EmbeddingBackend:
    return FakeBackend()


MANIFEST = """\
[kb]
name     = "{name}"
id       = "{kb_id}"
template = "notes@1.0"
created  = "20260730 09:00"

[sources]
roots   = ["{docs}/"]
include = ["**/*.md"]

[embedding]
provider = "fastembed"
model    = "fake-model"
dim      = {dim}

[chunking]
strategy   = "structural"
max_tokens = 120
overlap    = 16

[retrieval]
candidates_per_source = 30
fusion                = "rrf"
fusion_top_k          = 12
final_k               = 5
rerank                = "none"
vector_tier           = "numpy"

[rerank]
provider = "none"
model    = "none"
"""


@dataclass
class Kb:
    root: Path
    kb_id: KbId
    docs: dict[str, DocId]
    docs_dir: str = "docs"

    def sidecar(self, name: str) -> Path:
        return self.root / self.docs_dir / f"{name}.md{SIDECAR_SUFFIX}"

    def uri(self, name: str) -> str:
        return f"pnk://{self.kb_id}/{self.docs[name]}"

    def set_links(self, name: str, entries: Sequence[tuple[str, str]]) -> None:
        """Rewrite one sidecar's `links[]` as `(uri, rel)` pairs — the authoring model, by hand."""
        path = self.sidecar(name)
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
        if entries:
            body["links"] = [{"to": uri, "rel": rel} for uri, rel in entries]
        else:
            body.pop("links", None)
        path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")

    def connect(self, other: Kb, alias: str, *, path: str | None = None, kb_id: str | None = None):
        """Add a `[[links.kb]]` naming `other`. `kb_id`/`path` override to build the bad cases."""
        manifest = self.root / "pinakes.toml"
        text = manifest.read_text(encoding="utf-8")
        target = path if path is not None else _relative(self.root, other.root)
        text += (
            f'\n[[links.kb]]\nname = "{alias}"\n'
            f'id   = "{kb_id or other.kb_id}"\npath = "{target}"\n'
        )
        manifest.write_text(text, encoding="utf-8")

    def disconnect_all(self) -> None:
        manifest = self.root / "pinakes.toml"
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(text.split("\n[[links.kb]]")[0] + "\n", encoding="utf-8")


def _relative(here: Path, there: Path) -> str:
    import os

    return os.path.relpath(there, here)


def make_kb(
    root: Path,
    name: str,
    doc_names: Sequence[str],
    *,
    docs_dir: str = "docs",
    kb_id: str | None = None,
) -> Kb:
    (root / docs_dir).mkdir(parents=True)
    identifier = KbId(kb_id) if kb_id else mint_kb_id()
    (root / "pinakes.toml").write_text(
        MANIFEST.format(name=name, kb_id=identifier, dim=DIM, docs=docs_dir), encoding="utf-8"
    )
    docs: dict[str, DocId] = {}
    for doc in doc_names:
        (root / docs_dir / f"{doc}.md").write_text(f"# {doc}\n\nText about {doc}.\n", "utf-8")
        doc_id = mint_doc_id()
        docs[doc] = doc_id
        (root / docs_dir / f"{doc}.md{SIDECAR_SUFFIX}").write_text(
            yaml.safe_dump({"id": str(doc_id), "title": doc}, sort_keys=False), encoding="utf-8"
        )
    return Kb(root=root, kb_id=identifier, docs=docs, docs_dir=docs_dir)


def run(kb: Kb, *, now: str = "20260730 12:00", **options: Any) -> SyncReport:
    return sync(
        load(kb.root),
        options=SyncOptions(**options),
        backend_factory=fake_factory,
        now=now,
    )


def links_in(kb: Kb, *, origin: str | None = None) -> list[tuple[str, str, str, str, str]]:
    connection = store.connect_ro(kb.root / ".pinakes" / "index.db")
    try:
        sql = "SELECT src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel, origin FROM links"
        rows = [tuple(str(value) for value in row) for row in connection.execute(sql)]
    finally:
        connection.close()
    return sorted((a, b, c, d, e) for a, b, c, d, e, o in rows if origin is None or o == origin)


def kb_refs(kb: Kb) -> dict[str, tuple[str, str, str]]:
    connection = store.connect_ro(kb.root / ".pinakes" / "index.db")
    try:
        return {
            str(row[0]): (str(row[1]), str(row[2]), str(row[3]))
            for row in connection.execute("SELECT kb_id, alias, path, last_scan FROM kb_refs")
        }
    finally:
        connection.close()


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Kb, Kb]:
    """A local KB and a partner that links into it. The shape every test here needs."""
    local = make_kb(tmp_path / "local", "local", ["alpha", "beta"])
    partner = make_kb(tmp_path / "partner", "partner", ["one", "two"])
    local.connect(partner, "partner")
    partner.connect(local, "local")
    partner.set_links("one", [(local.uri("alpha"), "counterpart")])
    return local, partner


# --- What the scan records ----------------------------------------------------------------------


def test_inbound_rows_carry_the_other_kbs_id_as_source(pair: tuple[Kb, Kb]) -> None:
    local, partner = pair
    run(local)

    rows = links_in(local, origin="reverse-scan")
    assert rows == [
        (
            str(partner.kb_id),
            str(partner.docs["one"]),
            str(local.kb_id),
            str(local.docs["alpha"]),
            "counterpart",
        )
    ]


def test_a_self_link_in_a_partner_sidecar_resolves_to_the_partner_not_the_local_kb(
    pair: tuple[Kb, Kb],
) -> None:
    """The trap. `read_sidecar`'s `owner` expands `pnk://self/<doc>`, and both pre-existing call
    sites hard-code the *local* KB — so reusing either would resolve a partner's `self` link to us
    and mint an inbound edge from a document the partner never pointed here.

    The same defect was found and fixed once already (a sidecar copied into another KB silently
    retargeting its link), which is why `tests/partner-kb/` carries a hand-authored `self` link.
    """
    local, partner = pair
    partner.set_links("two", [(f"pnk://self/{partner.docs['one']}", "related")])

    run(local)

    inbound = links_in(local, origin="reverse-scan")
    assert all(dst != str(partner.docs["one"]) for _, _, _, dst, _ in inbound), (
        "a partner's `self` link was resolved against the local KB"
    )
    assert len(inbound) == 1  # only the genuine cross-KB one


def test_a_partner_link_to_a_third_kb_is_not_recorded(pair: tuple[Kb, Kb]) -> None:
    """Recording it would accumulate a foreign graph this index can never complete, and a partial
    view of someone else's links is exactly the silently-incomplete answer §6.2 refuses."""
    local, partner = pair
    third = mint_kb_id()
    partner.set_links(
        "two", [(f"pnk://{third}/{mint_doc_id()}", "related"), (local.uri("beta"), "related")]
    )

    run(local)

    inbound = links_in(local, origin="reverse-scan")
    assert all(src_kb == str(partner.kb_id) for src_kb, _, _, _, _ in inbound)
    assert len(inbound) == 2


def test_kb_refs_records_alias_path_and_scan_time(pair: tuple[Kb, Kb]) -> None:
    """Four columns that DESIGN §3 defined and nothing had ever written."""
    local, partner = pair
    run(local, now="20260730 12:00")

    refs = kb_refs(local)
    alias, path, last_scan = refs[str(partner.kb_id)]
    assert alias == "partner"
    assert Path(path).resolve() == partner.root.resolve()
    assert last_scan == "20260730 12:00"


def test_the_scan_reads_sidecars_not_the_partners_index(pair: tuple[Kb, Kb]) -> None:
    """The fixture holds a partner index that *contradicts* its sidecars: an inbound row the
    sidecars do not justify. If the scan read the index, that row would appear here.

    Built with `store.create` plus direct inserts rather than by syncing the partner for real —
    syncing it would drag an embedding backend into a test that needs none, and would also make
    the index agree with the sidecars, which is the one thing this fixture must not do.
    """
    local, partner = pair
    partner_index = partner.root / ".pinakes" / "index.db"
    partner_index.parent.mkdir(parents=True, exist_ok=True)
    connection = store.create(partner_index)
    try:
        connection.execute(
            "INSERT INTO links VALUES (?, ?, ?, ?, ?, 'sidecar')",
            (
                str(partner.kb_id),
                str(partner.docs["two"]),
                str(local.kb_id),
                str(local.docs["beta"]),
                "invented-by-the-index",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    run(local)

    rels = {rel for _, _, _, _, rel in links_in(local, origin="reverse-scan")}
    assert "invented-by-the-index" not in rels
    assert rels == {"counterpart"}


def test_a_target_this_kb_does_not_have_is_reported_but_still_recorded(
    pair: tuple[Kb, Kb],
) -> None:
    """Dropping it would hide a real claim the other KB is making — usually it just means the
    partner is ahead of us."""
    local, partner = pair
    absent = mint_doc_id()
    partner.set_links("two", [(f"pnk://{local.kb_id}/{absent}", "related")])

    report = run(local)

    assert any(str(absent) in message for _, message, _ in report.link_scan)
    assert any(dst == str(absent) for _, _, _, dst, _ in links_in(local, origin="reverse-scan"))


# --- Never overwriting an authored row -----------------------------------------------------------


def test_a_reverse_row_never_overwrites_an_authored_row(tmp_path: Path) -> None:
    """A manifest listing *itself* is the only way an authored tuple and a reverse tuple can
    collide: an authored row's `src_kb_id` is always the local KB, and duplicate `[[links.kb]]`
    ids are already refused at parse time. `INSERT OR REPLACE` would flip `origin` to
    `reverse-scan` and drop the row out of the authored-only population the density gate and
    `pnk doctor` both count."""
    kb = make_kb(tmp_path / "solo", "solo", ["alpha", "beta"])
    kb.connect(kb, "myself")  # the self-listing fixture
    kb.set_links("alpha", [(kb.uri("beta"), "related")])

    run(kb)

    rows = [
        (src_doc, dst_doc, rel)
        for src_kb, src_doc, _dst_kb, dst_doc, rel in links_in(kb, origin="sidecar")
        if src_kb == str(kb.kb_id)
    ]
    assert (str(kb.docs["alpha"]), str(kb.docs["beta"]), "related") in rows, (
        "the authored row was downgraded to origin=reverse-scan"
    )


def test_an_authored_row_reclaims_a_tuple_a_reverse_scan_already_wrote(tmp_path: Path) -> None:
    """The other order, which is safe for a different reason: `_replace_links` uses
    `INSERT OR REPLACE`, so it reclaims the tuple and rewrites `origin` to `sidecar`. Making that
    writer a `DO NOTHING` too — the symmetric-looking "fix" — would silently undercount authored
    links forever."""
    kb = make_kb(tmp_path / "solo", "solo", ["alpha", "beta"])
    kb.connect(kb, "myself")
    kb.set_links("alpha", [(kb.uri("beta"), "related")])
    run(kb)

    connection = store.connect_rw(kb.root / ".pinakes" / "index.db")
    try:
        connection.execute("UPDATE links SET origin = 'reverse-scan'")
        connection.commit()
    finally:
        connection.close()

    # The document has to actually be *re-indexed* for `_replace_links` to run: a Skip rewrites
    # nothing, which is itself worth knowing — the reclaim happens when the authored side changes,
    # not on every sync.
    (kb.root / "docs" / "alpha.md").write_text("# alpha\n\nEdited.\n", encoding="utf-8")
    run(kb, now="20260730 13:00", scan_links=True)

    authored = links_in(kb, origin="sidecar")
    assert (
        str(kb.kb_id),
        str(kb.docs["alpha"]),
        str(kb.kb_id),
        str(kb.docs["beta"]),
        "related",
    ) in authored


# --- The deletes ---------------------------------------------------------------------------------


def test_a_removed_link_removes_its_reverse_row(pair: tuple[Kb, Kb]) -> None:
    local, partner = pair
    run(local)
    assert len(links_in(local, origin="reverse-scan")) == 1

    partner.set_links("one", [])
    run(local, now="20260730 14:00", scan_links=True)

    assert links_in(local, origin="reverse-scan") == []


def test_the_delete_is_scoped_to_the_scanned_kb(tmp_path: Path) -> None:
    """Two partners. Re-scanning one must not touch the other's rows."""
    local = make_kb(tmp_path / "local", "local", ["alpha"])
    first = make_kb(tmp_path / "first", "first", ["one"])
    second = make_kb(tmp_path / "second", "second", ["two"])
    local.connect(first, "first")
    local.connect(second, "second")
    first.connect(local, "local")
    second.connect(local, "local")
    first.set_links("one", [(local.uri("alpha"), "from-first")])
    second.set_links("two", [(local.uri("alpha"), "from-second")])
    run(local)
    assert len(links_in(local, origin="reverse-scan")) == 2

    first.set_links("one", [])
    run(local, now="20260730 14:00", scan_links=True)

    rels = {rel for _, _, _, _, rel in links_in(local, origin="reverse-scan")}
    assert rels == {"from-second"}


def test_delisting_a_linked_kb_removes_its_reverse_rows_and_kb_ref(pair: tuple[Kb, Kb]) -> None:
    """The per-scanned-KB delete never fires for a KB that is no longer scanned, and nothing else
    in `src/` removes a reverse row — so before this, disconnecting a partner left
    `pnk links --direction in` serving its edges until someone happened to rebuild."""
    local, partner = pair
    run(local)
    assert len(links_in(local, origin="reverse-scan")) == 1
    assert str(partner.kb_id) in kb_refs(local)

    local.disconnect_all()
    report = run(local, now="20260730 14:00")

    assert links_in(local, origin="reverse-scan") == []
    assert kb_refs(local) == {}
    assert report.links_forgotten == 1


def test_a_failed_scan_leaves_the_previous_reverse_rows_in_place(pair: tuple[Kb, Kb]) -> None:
    """The delete is unconditional within its scope, so a half-read partner would lose edges that
    are still true. Two of the four failure modes reach here."""
    local, partner = pair
    run(local)
    before = links_in(local, origin="reverse-scan")
    assert len(before) == 1

    # A second partner document whose sidecar will not parse: the walk is now incomplete, and the
    # rows it *did* read must not be written as if they were the whole picture.
    partner.sidecar("two").write_text("id: not-a-ulid\n", encoding="utf-8")

    report = run(local, now="20260730 14:00", scan_links=True)

    assert links_in(local, origin="reverse-scan") == before
    assert any("will not parse" in message for _, message, _ in report.link_scan)


def test_a_failed_scan_does_not_stamp_last_scan(pair: tuple[Kb, Kb]) -> None:
    """Recording the timestamp would suppress the retry for a full TTL on the strength of a walk
    that failed — the one outcome that must not be sticky."""
    local, partner = pair
    run(local, now="20260730 12:00")
    partner.sidecar("two").write_text("id: not-a-ulid\n", encoding="utf-8")

    run(local, now="20260730 14:00", scan_links=True)

    _alias, _path, last_scan = kb_refs(local)[str(partner.kb_id)]
    assert last_scan == "20260730 12:00"


# --- The failure taxonomy -------------------------------------------------------------------------


def test_each_failure_mode_is_recorded_with_its_reason(tmp_path: Path) -> None:
    """Four shapes, four distinguishable messages, and every one of them constructed rather than
    raised — the scan carries on to the next KB."""
    local = make_kb(tmp_path / "local", "local", ["alpha"])

    absent = make_kb(tmp_path / "absent", "absent", ["x"])
    local.connect(absent, "gone", path="../nowhere-at-all")

    wrong = make_kb(tmp_path / "wrong", "wrong", ["y"])
    local.connect(wrong, "mismatched", kb_id=str(mint_kb_id()))

    broken = make_kb(tmp_path / "broken", "broken", ["z"])
    broken.connect(local, "local")
    broken.sidecar("z").write_text("id: not-a-ulid\n", encoding="utf-8")
    local.connect(broken, "unparseable")

    ahead = make_kb(tmp_path / "ahead", "ahead", ["w"])
    ahead.connect(local, "local")
    ahead.set_links("w", [(f"pnk://{local.kb_id}/{mint_doc_id()}", "related")])
    local.connect(ahead, "ahead")

    report = run(local)

    by_alias = {alias: message for alias, message, _ in report.link_scan}
    assert "no such directory" in by_alias["gone"]
    assert "but the KB at that path is" in by_alias["mismatched"]
    assert "will not parse" in by_alias["unparseable"]
    assert "does not have" in by_alias["ahead"]
    assert all(remedy for _, _, remedy in report.link_scan), "every failure owes a remedy"


def test_an_unreachable_linked_kb_does_not_fail_the_sync(tmp_path: Path) -> None:
    """`SyncReport.ok` is `not self.failures`, and `pnk sync` runs on three git hooks. Recording a
    missing partner as a failure would block every commit over a KB that is simply not on this
    machine — contradicting both `[[links.kb]]`'s "non-existence is not an error" and `pnk doctor`
    reporting it as a warning."""
    local = make_kb(tmp_path / "local", "local", ["alpha"])
    other = make_kb(tmp_path / "other", "other", ["one"])
    local.connect(other, "gone", path="../not-here")

    report = run(local)

    assert report.ok
    assert report.failures == []
    assert len(report.link_scan) == 1


def test_a_linked_kb_that_raises_before_the_handling_is_still_only_an_issue(
    pair: tuple[Kb, Kb],
) -> None:
    """*"Nothing here raises"* was false of the three lines that ran before any handling did.

    `resolve_path` calls `expanduser()`, which raises `RuntimeError` on an unknown user; `is_file`
    and `is_dir` swallow a missing path and nothing else, so an unreadable partner directory raises
    `PermissionError`. Both escaped `scan_one` entirely and turned `pnk sync` on a `post-commit`
    hook into a traceback — the precise failure the promise exists to prevent. Found by grepping
    the module for calls that touch the filesystem, after L6 had fixed the same class in
    `link.py` four times, one instance at a time.
    """
    local, partner = pair

    partner.root.chmod(0o000)
    try:
        report = run(local, now="20260730 12:00")
    finally:
        partner.root.chmod(0o755)
    assert report.ok  # an unreadable partner is a fact about this machine, never a sync failure
    assert len(report.link_scan) == 1

    manifest = local.root / "pinakes.toml"
    text = manifest.read_text(encoding="utf-8")
    path_line = next(line for line in text.splitlines() if line.startswith("path = "))
    manifest.write_text(text.replace(path_line, 'path = "~nosuchuser12345/kb"'), encoding="utf-8")

    report = run(local, now="20260730 14:00", scan_links=True)
    assert report.ok
    assert len(report.link_scan) == 1
    # The path reported is the one declared, not the local KB root — which is a readable directory
    # with nothing to do with the failure, and was what an earlier version named.
    _alias, message, _remedy = report.link_scan[0]
    assert "~nosuchuser12345/kb" in message
    assert str(local.root) not in message


def test_resolve_path_never_raises_whatever_the_manifest_says() -> None:
    """`[[links.kb]] path` is user-written text in a committed file, and two of the calls that
    consume it reject some of it: `expanduser()` raises `RuntimeError` for an unknown user,
    `resolve()` raises `ValueError` for an embedded NUL — which `tomllib` accepts and the manifest
    parser does not filter. Neither is a `PinakesError`.

    Pinned on the function rather than on its callers **because fixing it at call sites is what
    produced six instances of it**: L6 wrapped this call in `_via_alias`, then in `scan_one`, and a
    review pass still found it bare in `scan()`'s freshness branch.

    **The answer is an *absolute* path or `None` — never a relative one.** An earlier version of
    this test asserted only `isinstance(…, Path)`, which the declared-text fallback satisfied while
    handing five filesystem call sites a path anchored on the working directory. The type was never
    the property worth pinning; where the path points is.
    """
    root = Path("/tmp/somewhere")
    unresolvable = ("~nosuchuser12345/kb", "a\x00b", "~zzzznosuchuser/x", "kb\x00/x")
    for raw in unresolvable:
        assert resolve_path(root, raw) is None, raw
        reason = why_unresolvable(root, raw)
        # **The reason alone, never the path** — `LinkedKbUnreachableError` interpolates that
        # itself, and a first version stuttered it: `cannot be read at ~x/kb: '~x/kb' cannot be
        # resolved to a path: …`. Same register as `why_not_a_kb`, which this sits beside.
        assert reason and raw not in reason, raw

    for raw in ("../partner", "/abs/kb", "sub/kb", "~"):
        answer = resolve_path(root, raw)
        assert answer is not None and answer.is_absolute(), raw


def test_an_unresolvable_path_is_reported_rather_than_fresh_skipped(
    pair: tuple[Kb, Kb],
) -> None:
    """The freshness branch of `scan()` — which **plain `pnk sync` takes**, since `force` is only
    set by `--scan-links`, and which every git hook therefore reaches.

    The scenario is ordinary: a partner scans once (writing `last_scan`), then `[[links.kb]] path`
    is edited to something that will not resolve — a typo, or a path valid on the machine the
    manifest was committed from. Every commit inside the hour-long TTL was then a traceback. No
    test touched this branch at all: `grep skipped_fresh tests/` returned nothing.

    **The assertion that discriminates is `link_scan`, not `report.ok`.** A first version asserted
    only `ok`, which holds whether the branch runs or not — the increment's own recurring class,
    inside the fix for a finding that said the branch had no test. A skipped-fresh row carries no
    issue, so a non-empty `link_scan` is the proof this path was *not* silently skipped. The
    freshness branch proper is pinned by `test_a_fresh_kb_refs_entry_skips_the_walk`; both
    directions are mutation-verified.
    """
    local, _partner = pair
    run(local, now="20260730 12:00")  # writes kb_refs.last_scan

    manifest = local.root / "pinakes.toml"
    text = manifest.read_text(encoding="utf-8")
    path_line = next(line for line in text.splitlines() if line.startswith("path = "))
    manifest.write_text(text.replace(path_line, 'path = "~nosuchuser12345/kb"'), encoding="utf-8")

    report = run(local, now="20260730 12:30")  # inside the TTL: the fresh branch, no force
    assert report.ok
    # And it is **not** silently fresh-skipped: a path naming nothing is a broken manifest, and the
    # TTL exists to skip re-reading a partner that was fine an hour ago — not to withhold the reason
    # for the rest of the hour.
    assert len(report.link_scan) == 1
    _alias, message, _remedy = report.link_scan[0]
    assert "~nosuchuser12345/kb" in message


def test_an_unresolvable_path_is_never_walked_from_the_working_directory(
    pair: tuple[Kb, Kb], tmp_path: Path
) -> None:
    """The declared-text fallback review 7 added was a **relative** path, and five call sites use
    `ScannedKb.path` as a filesystem base — so the walk re-anchored on the process's working
    directory, the one thing `resolve_path`'s first paragraph says it exists to prevent.

    The consequence is not a crash but silent data loss, which is why it survived a round: with a
    directory of that literal name in the CWD holding a readable `pinakes.toml`, the walk succeeds,
    finds no sidecars, stamps itself `complete` — and `replace_reverse_links` then deletes every
    inbound row the real partner had, with `report.ok` true and no issue raised.

    The decoy carries the *partner's own* `[kb] id`, because the id-mismatch refusal would
    otherwise catch it first and hide the defect behind the wrong guard.
    """
    local, partner = pair
    run(local, now="20260730 12:00")
    assert len(links_in(local, origin="reverse-scan")) == 1

    manifest = local.root / "pinakes.toml"
    text = manifest.read_text(encoding="utf-8")
    path_line = next(line for line in text.splitlines() if line.startswith("path = "))
    manifest.write_text(text.replace(path_line, 'path = "~nosuchuser12345/kb"'), encoding="utf-8")

    workdir = tmp_path / "workdir"
    decoy = workdir / "~nosuchuser12345" / "kb"
    (decoy / "docs").mkdir(parents=True)
    (decoy / "pinakes.toml").write_text(
        (partner.root / "pinakes.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )

    here = os.getcwd()
    os.chdir(workdir)
    try:
        report = run(local, now="20260730 14:00", scan_links=True)
    finally:
        os.chdir(here)

    assert len(links_in(local, origin="reverse-scan")) == 1, "the decoy's empty walk deleted rows"
    assert len(report.link_scan) == 1
    _alias, message, _remedy = report.link_scan[0]
    assert "cannot be expanded" in message  # the fault, not just "unreachable"
    assert "~nosuchuser12345/kb" in message  # ...and the text the author wrote
    assert str(local.root) not in message  # ...never the local KB root
    # `last_scan` is not stamped either: an unreachable partner must not suppress the retry.
    assert "partner" not in {alias for alias, *_ in report.links_scanned}


# --- The TTL --------------------------------------------------------------------------------------


def test_a_fresh_kb_refs_entry_skips_the_walk(pair: tuple[Kb, Kb]) -> None:
    local, partner = pair
    run(local, now="20260730 12:00")

    partner.set_links("one", [])  # would remove the row, if anyone looked
    report = run(local, now="20260730 12:30")  # inside the TTL

    assert len(links_in(local, origin="reverse-scan")) == 1
    assert report.links_scanned == ()


def test_an_expired_ttl_forces_a_rescan(pair: tuple[Kb, Kb]) -> None:
    local, partner = pair
    run(local, now="20260730 12:00")
    partner.set_links("one", [])

    run(local, now="20260730 14:00")  # well past the TTL

    assert links_in(local, origin="reverse-scan") == []


def test_scan_links_forces_a_rescan(pair: tuple[Kb, Kb]) -> None:
    local, partner = pair
    run(local, now="20260730 12:00")
    partner.set_links("one", [])

    run(local, now="20260730 12:01", scan_links=True)  # far inside the TTL

    assert links_in(local, origin="reverse-scan") == []


@pytest.mark.parametrize(
    ("last_scan", "expected", "why"),
    [
        (None, True, "nothing is known yet"),
        ("20260730 11:59", True, "exactly at the TTL"),
        ("20260730 12:00", False, "inside the TTL"),
        (
            "20260730 23:00",
            True,
            "in the future — the clock moved, or the file came from elsewhere",
        ),
        ("not a timestamp", True, "unparseable must never read as recent"),
    ],
)
def test_the_ttl_never_reads_uncertainty_as_fresh(
    last_scan: str | None, expected: bool, why: str
) -> None:
    """A future `last_scan` treated as fresh would suppress every scan until real time caught up —
    the one failure mode with no symptom."""
    assert is_stale(last_scan, "20260730 12:59", ttl_minutes=TTL_MINUTES) is expected, why


# --- Flags ----------------------------------------------------------------------------------------


def test_sidecars_only_does_not_scan(pair: tuple[Kb, Kb]) -> None:
    """Reverse rows are index rows, and `--sidecars-only` returns before the index is opened."""
    local, _partner = pair
    run(local, sidecars_only=True)

    assert not (local.root / ".pinakes" / "index.db").exists()


def test_sidecars_only_with_scan_links_is_refused(pair: tuple[Kb, Kb]) -> None:
    """Refused rather than silently resolved: honouring both would mean one flag doing nothing and
    the user unable to tell which."""
    local, _partner = pair
    with pytest.raises(SyncError) as caught:
        run(local, sidecars_only=True, scan_links=True)
    assert "nothing to write" in caught.value.message
    assert "on its own" in caught.value.remedy


def test_rebuild_reconstructs_reverse_rows_from_sidecars_alone(pair: tuple[Kb, Kb]) -> None:
    """A rebuild starts from `store.create` on a fresh file, so `kb_refs` is empty and there is
    nothing for the TTL to skip on — the inbound picture has to come back from the partner's
    committed sidecars or not at all."""
    local, _partner = pair
    run(local)
    before = links_in(local, origin="reverse-scan")
    assert before

    run(local, now="20260730 12:05", rebuild=True)

    assert links_in(local, origin="reverse-scan") == before
    assert str(_partner.kb_id) in kb_refs(local)


def test_a_kb_with_no_linked_kbs_still_sweeps(pair: tuple[Kb, Kb]) -> None:
    """A manifest can drop its *last* `[[links.kb]]`, which is exactly the case where nothing
    would ever come back to clean up after it."""
    local, _partner = pair
    run(local)
    assert links_in(local, origin="reverse-scan")

    local.disconnect_all()
    run(local, now="20260730 14:00")

    assert links_in(local, origin="reverse-scan") == []


def test_the_partner_is_never_locked(pair: tuple[Kb, Kb]) -> None:
    """§6.2: a cross-KB read must never block, or be blocked by, a partner's own sync.

    The partner holds its **own sync lock** for the duration — the state a partner mid-sync is
    actually in. An earlier version of this test asserted the partner had no `.pinakes/`, on a
    fixture where it never had one: it proved nothing was created and nothing at all about locking.
    """
    from pinakes.lock import SyncLock

    local, partner = pair
    (partner.root / ".pinakes").mkdir(parents=True, exist_ok=True)

    with SyncLock(partner.root / ".pinakes") as held:
        assert held.acquired, "the fixture failed to take the partner's lock"
        report = run(local)

    assert report.ok
    assert len(links_in(local, origin="reverse-scan")) == 1


def test_a_vanished_partner_root_deletes_nothing(pair: tuple[Kb, Kb]) -> None:
    """A partner renaming its own `docs/` yielded zero sidecars — which reads as "no inbound
    links" — so every row was deleted and `last_scan` stamped fresh, with nothing reported.

    Reproduced before the fix: rows 1 → 0, `link_scan` empty, `last_scan` advanced. It is the same
    mass deletion the `complete` flag exists to prevent, arriving through the one door the flag was
    not watching, and no "successful walk" test could see it because they all leave the sidecars
    where they are.
    """
    local, partner = pair
    run(local, now="20260730 12:00")
    assert len(links_in(local, origin="reverse-scan")) == 1

    (partner.root / partner.docs_dir).rename(partner.root / "renamed")
    report = run(local, now="20260730 14:00", scan_links=True)

    assert len(links_in(local, origin="reverse-scan")) == 1, "the inbound rows were deleted"
    assert any("not a directory" in message for _, message, _ in report.link_scan)
    _alias, _path, last_scan = kb_refs(local)[str(partner.kb_id)]
    assert last_scan == "20260730 12:00", "a failed walk stamped itself as fresh"


def test_a_partners_exclude_is_honoured(pair: tuple[Kb, Kb]) -> None:
    """The shipped `notes` template stamps `exclude = ["**/drafts/**"]`, so this is the shape of
    every KB `pnk init` creates — and ignoring it recorded inbound links from documents the
    partner's own KB does not contain."""
    local, partner = pair
    drafts = partner.root / partner.docs_dir / "drafts"
    drafts.mkdir()
    (drafts / "wip.md").write_text("# wip\n\nDraft.\n", encoding="utf-8")
    (drafts / f"wip.md{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump(
            {
                "id": str(mint_doc_id()),
                "links": [{"to": local.uri("beta"), "rel": "from-a-draft"}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', 'include = ["**/*.md"]\nexclude = ["**/drafts/**"]'
        ),
        encoding="utf-8",
    )

    run(local, now="20260730 14:00", scan_links=True)

    rels = {rel for _, _, _, _, rel in links_in(local, origin="reverse-scan")}
    assert "from-a-draft" not in rels
    assert rels == {"counterpart"}


def test_a_partners_bad_include_pattern_does_not_crash_the_sync(pair: tuple[Kb, Kb]) -> None:
    """`glob` raises on patterns `manifest.load` would have rejected, and every one of these
    inputs comes from a *partner's* manifest. Bypassing `load` to tolerate unknown keys removed the
    only validation and added none, so these escaped `sync()` and crashed `pnk sync` on a git hook
    — the opposite of what "nothing here raises" is for."""
    local, partner = pair
    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', 'include = ["/etc/**/*.md"]'
        ),
        encoding="utf-8",
    )

    report = run(local, now="20260730 14:00", scan_links=True)

    assert report.ok
    assert any("[sources]" in message for _, message, _ in report.link_scan)


def test_a_partner_root_outside_its_own_kb_is_refused(pair: tuple[Kb, Kb], tmp_path: Path) -> None:
    """`manifest._sources` refuses absolute roots and `..`; nothing re-applied that to a partner's
    manifest, so it could point this walk anywhere on the machine — and `roots = ["/"]` would be an
    unbounded walk on a `post-commit` hook."""
    local, partner = pair
    outside = tmp_path / "outside" / "docs"
    outside.mkdir(parents=True)
    (outside / "smuggled.md").write_text("# s\n\nText.\n", encoding="utf-8")
    (outside / f"smuggled.md{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump(
            {"id": str(mint_doc_id()), "links": [{"to": local.uri("beta"), "rel": "smuggled"}]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'roots   = ["docs/"]', f'roots   = ["docs/", "{outside}"]'
        ),
        encoding="utf-8",
    )

    report = run(local, now="20260730 14:00", scan_links=True)

    rels = {rel for _, _, _, _, rel in links_in(local, origin="reverse-scan")}
    assert "smuggled" not in rels
    # **`roots entry`, not just "outside the KB".** Deleting this guard entirely left all 101
    # tests green: the outside root was globbed and the *per-candidate* check then emitted
    # "include pattern … reaches outside the KB", which satisfied a bare substring assertion.
    # That check is not a substitute — it fires only once `glob` is already walking, which is
    # exactly what this rule exists to prevent (`roots = ["/"]` on a `post-commit` hook).
    assert any("roots entry" in message for _, message, _ in report.link_scan)


@pytest.mark.parametrize(
    ("pattern", "via_symlink"),
    [
        ("../../outside/docs/*.md", False),
        ("../../**/*.md", False),
        # A symlinked *directory* under the partner's own root, which plain `**/*.md` does not
        # reach — `Path.glob` does not recurse one — so it needs a pattern that names it.
        ("sneak/*.md", True),
    ],
)
def test_a_partner_include_pattern_outside_its_own_kb_is_refused(
    pair: tuple[Kb, Kb], tmp_path: Path, pattern: str, via_symlink: bool
) -> None:
    """The same containment rule as the test above, for the input it was never applied to.

    `include` is exactly as partner-controlled as `roots`, and the check existed for `roots` alone
    — so a pattern reaching out of the KB walked wherever it pointed and this KB recorded inbound
    links from files the partner does not own, with `complete` true so they were persisted.

    **`candidate.relative_to(root)` did not catch it.** `relative_to` is purely lexical, so
    `docs/../../outside/smuggled.md` *is* relative to the root as a string — measured, it returns
    `docs/../../outside/smuggled.md` rather than raising. Containment has to resolve.
    """
    local, partner = pair
    outside = partner.root.parent / "outside" / "docs"
    outside.mkdir(parents=True)
    (outside / "smuggled.md").write_text("# s\n\nText.\n", encoding="utf-8")
    (outside / f"smuggled.md{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump(
            {"id": str(mint_doc_id()), "links": [{"to": local.uri("beta"), "rel": "smuggled"}]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    if via_symlink:
        (partner.root / partner.docs_dir / "sneak").symlink_to(outside)
    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', f'include = ["**/*.md", "{pattern}"]'
        ),
        encoding="utf-8",
    )

    report = run(local, now="20260730 14:00", scan_links=True)

    rels = {rel for _, _, _, _, rel in links_in(local, origin="reverse-scan")}
    assert "smuggled" not in rels
    assert any("outside the KB" in message for _, message, _ in report.link_scan)


def test_an_escaping_include_pattern_is_refused_without_walking(pair: tuple[Kb, Kb]) -> None:
    """**The refusal has to happen before the glob, or it does not bound anything.**

    Checking each candidate refuses the *results* while still paying for the enumeration — so
    `include = ["../../../../**/*.md"]` walked the machine on every `post-commit`, collected
    nothing, and (because the escape sets `complete` false) never stamped `last_scan`, so the TTL
    could not suppress the retry either. The `roots` rule gets this right by refusing before it
    walks; presenting `include` as the same rule while checking it a step later delivered the
    refusal without the bound.

    **The discriminator is a path that does not exist.** A per-candidate check sees no candidates
    and reports nothing; a static one refuses the pattern on its text. That is deterministic, where
    asserting on elapsed time is not.
    """
    local, partner = pair
    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', 'include = ["**/*.md", "../../no-such-directory/*.md"]'
        ),
        encoding="utf-8",
    )

    report = run(local, now="20260730 14:00", scan_links=True)

    assert any("reaches outside the KB" in message for _, message, _ in report.link_scan)


def test_a_dot_dot_pattern_that_stays_inside_the_kb_is_not_refused(pair: tuple[Kb, Kb]) -> None:
    """The static refusal tests **where the pattern's fixed prefix lands**, not whether it contains
    `..`.

    A first version refused any `..`, which refuses `../notes/*.md` — a pattern that stays inside
    the KB and that the partner's own `walk_sources` ingests. This KB then called a legitimate
    manifest an escape; and because an escape sets `complete` false, it never wrote `last_scan`, so
    the partner was re-read, re-refused and never refreshed on every sync, permanently. Refusing a
    partner's valid configuration is the same defect as accepting an invalid one — both are this KB
    disagreeing with the partner about the partner's own KB.
    """
    local, partner = pair
    notes = partner.root / "notes"
    notes.mkdir()
    (notes / "n.md").write_text("# n\n\nText.\n", encoding="utf-8")
    (notes / f"n.md{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump(
            {"id": str(mint_doc_id()), "links": [{"to": local.uri("beta"), "rel": "from-notes"}]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', 'include = ["**/*.md", "../notes/*.md"]'
        ),
        encoding="utf-8",
    )

    report = run(local, now="20260730 14:00", scan_links=True)

    assert not [m for _, m, _ in report.link_scan if "outside the KB" in m]
    rels = {rel for _, _, _, _, rel in links_in(local, origin="reverse-scan")}
    assert "from-notes" in rels


def test_a_leading_glob_does_not_defeat_the_static_refusal(
    pair: tuple[Kb, Kb], tmp_path: Path
) -> None:
    """`*/../../outside/*.md` — the escape sits behind a glob component.

    A version that tested only the prefix *before the first glob component* had an empty prefix
    here, so it passed unconditionally and the `..` ran inside `glob`: unbounded again, and
    reporting nothing when the outside tree held no match. The whole pattern is joined instead, and
    a glob component is simply a name that does not exist, which `resolve()` collapses lexically.
    """
    local, partner = pair
    outside = partner.root.parent / "outside"
    outside.mkdir()
    (outside / "smuggled.md").write_text("# s\n\nText.\n", encoding="utf-8")
    (outside / f"smuggled.md{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump(
            {"id": str(mint_doc_id()), "links": [{"to": local.uri("beta"), "rel": "smuggled"}]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', 'include = ["**/*.md", "*/../../../outside/*.md"]'
        ),
        encoding="utf-8",
    )

    report = run(local, now="20260730 14:00", scan_links=True)

    assert "smuggled" not in {rel for _, _, _, _, rel in links_in(local, origin="reverse-scan")}
    assert any("outside the KB" in message for _, message, _ in report.link_scan)


def test_a_fixed_include_naming_a_symlinked_document_agrees_with_the_glob_spelling(
    pair: tuple[Kb, Kb], tmp_path: Path
) -> None:
    """One file, two spellings of the include that names it, and they must answer the same.

    Joining the pattern and resolving it *whole* follows the final symlink, so
    `include = ["linked.md"]` was refused as an escape while `include = ["*.md"]` — reaching the
    same document — was accepted. The containment rule is `parent.resolve() / name` in all three
    places that implement it (`link._document_in`, the candidate loop, and here); writing it a
    fourth way is what produced three wrong versions in three rounds.
    """
    _local, partner = pair
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / "linked.md").write_text("# linked\n\nText.\n", encoding="utf-8")
    (real / f"linked.md{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump({"id": str(mint_doc_id())}, sort_keys=False), encoding="utf-8"
    )
    docs = partner.root / partner.docs_dir
    (docs / "linked.md").symlink_to(real / "linked.md")
    (docs / f"linked.md{SIDECAR_SUFFIX}").symlink_to(real / f"linked.md{SIDECAR_SUFFIX}")

    # Not a count — `*.md` legitimately reaches the fixture's other documents too. What has to
    # agree is whether *this* document is reached, and whether either spelling is refused.
    for spelling in ("linked.md", "*.md"):
        found, problems = sidecars_under(partner.root, ["docs/"], [spelling], [])
        assert problems == [], f"{spelling!r} was refused: {problems}"
        assert {path.name for path in found} >= {f"linked.md{SIDECAR_SUFFIX}"}, (
            f"{spelling!r} did not reach the symlinked document"
        )


def test_a_double_star_before_a_dot_dot_does_not_defeat_the_refusal(
    pair: tuple[Kb, Kb],
) -> None:
    """`**` matches **zero** or more components, while `Path.parts` counts it as one.

    So a probe that kept `**` let a following `..` cancel it and landed one level *below* where the
    walk actually goes: `**/../../**/*.md` probed inside the KB and walked the directory containing
    it, recursively — measured linear in the outside tree, and reporting nothing, because an escape
    is only noticed once a candidate is yielded and this pattern matched none.

    Dropping `**` from the probe is exact rather than merely conservative: every component `**`
    expands to is one a following `..` then pops, so the zero-expansion is the highest the walk can
    reach, and that is what has to be inside the KB.
    """
    _local, partner = pair
    outside = partner.root.parent / "outside"
    outside.mkdir()
    for index in range(40):
        (outside / f"dir{index}").mkdir()

    for pattern in ("**/../../outside/*.md", "**/../../**/*.md"):
        _found, problems = sidecars_under(partner.root, ["docs/"], [pattern], [])
        assert problems, f"{pattern!r} was not refused"
        assert "reaches outside the KB" in problems[0]

    found, problems = sidecars_under(partner.root, ["docs/"], ["**/*.md"], [])
    assert problems == [], "an ordinary `**` was caught by the escape rule"
    assert len(found) == 2


def test_one_unusable_include_pattern_does_not_discard_the_others(pair: tuple[Kb, Kb]) -> None:
    """`Path.glob("")` raises `ValueError`, and that reached `scan_one`, which reported the whole
    partner unreachable: every other `include` entry was discarded, `complete` stayed false
    forever, and the message named `'.'` for a pattern the author wrote as `""`.

    One pattern is one problem — the precedent the absolute case sets one branch above. Both the
    `glob()` call and each `next()` are guarded, because `""` raises at the call while a pattern
    that turns unacceptable partway raises from the step; the first version of this fix guarded
    only the step, and `""` still escaped.
    """
    _local, partner = pair
    for bad in ("", "."):
        found, problems = sidecars_under(partner.root, ["docs/"], ["**/*.md", bad], [])
        assert len(found) == 2, f"{bad!r} discarded the valid include entries"
        assert problems == [
            f"[sources] include pattern {bad!r} cannot be walked: "
            "Unacceptable pattern: PosixPath('.')"
        ]


def test_the_walk_raising_is_an_issue_not_a_traceback(
    pair: tuple[Kb, Kb], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`scan_one` promises *"Never raises: every failure comes back in `issues`"*, and its guard
    around `sidecars_under` had stopped being exercised by anything.

    The input that used to reach it — `include = ["/etc/**/*.md"]` — is now answered by the
    absolute branch and never reaches `glob`, so the test written for it passes on the new message
    while the guard it was written for is dead. That is the third time in this increment a later
    fix has quietly disarmed an older test, so the promise is pinned directly here instead of
    through an input that a future fix can intercept.
    """
    local, _partner = pair

    def exploding(
        _root: Path, _roots: list[str], _include: list[str], _exclude: list[str]
    ) -> tuple[list[Path], list[str]]:
        raise OSError(5, "io")

    monkeypatch.setattr(linkscan, "sidecars_under", exploding)

    report = run(local, now="20260730 14:00", scan_links=True)

    assert report.ok
    assert len(report.link_scan) == 1
    _alias, message, _remedy = report.link_scan[0]
    assert "[sources]" in message


@pytest.mark.parametrize(
    ("include", "exclude", "expected"),
    [
        # A NUL in a non-final component reaches `probe.parent.resolve()`, which was outside any
        # handler — one line above the `glob` guard written to stop exactly this outcome.
        (["**/*.md", "a\x00b/x.md"], [], "include pattern 'a\\x00b/x.md' cannot be walked"),
        # ...and in the final component it reaches `next()`, whose guard no test exercised: the
        # `""`/`"."` fixtures written for it raise at the `glob()` *call*, not at the step.
        (["**/*.md", "sub/\x00"], [], "include pattern 'sub/\\x00' cannot be walked"),
        # `Path.match("")` raises too. The comment on the `next` guard cited this very case as its
        # reason for scoping tightly, and then left it unhandled.
        (["**/*.md"], [""], "exclude rule '' cannot be used"),
    ],
)
def test_one_bad_sources_entry_is_one_problem_not_the_end_of_the_partner(
    pair: tuple[Kb, Kb], include: list[str], exclude: list[str], expected: str
) -> None:
    """Each of these raised out of `sidecars_under` into `scan_one`'s coarse handler, which reports
    the **whole** partner unreachable: every other `include` entry discarded, `complete` false
    forever, and a message naming neither the key nor the value.

    An unusable `exclude` is a *problem*, never a quiet drop — dropping it would make this KB record
    links from documents the partner's own KB excludes, which is the one thing this function must
    not do.
    """
    _local, partner = pair
    found, problems = sidecars_under(partner.root, ["docs/"], include, exclude)
    assert len(found) == 2, "the valid entries stopped being walked"
    assert len(problems) == 1, problems
    assert problems[0].startswith(f"[sources] {expected}: "), problems[0]


def test_a_pattern_that_escapes_under_one_root_collects_under_none(pair: tuple[Kb, Kb]) -> None:
    """A pattern can escape under one root and be legal under another — `roots = ["docs/",
    "docs/sub/"]` with `include = ["../../x/*.md"]`, where `x/` is inside the KB.

    The `pattern in escaping` skip is what stops the second root collecting from a pattern the
    first reported as an escape, and its comment called it "an optimisation". Removing it collects
    the document *and* reports the escape, in one report. A partner's `[sources]` is one statement
    about one KB, not a per-root negotiation.
    """
    _local, partner = pair
    (partner.root / partner.docs_dir / "sub").mkdir()
    inside = partner.root / "x"
    inside.mkdir()
    (inside / "in.md").write_text("# in\n\nText.\n", encoding="utf-8")
    (inside / f"in.md{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump({"id": str(mint_doc_id())}, sort_keys=False), encoding="utf-8"
    )

    found, problems = sidecars_under(partner.root, ["docs/", "docs/sub/"], ["../../x/*.md"], [])

    assert found == [], "a pattern refused under one root was collected under another"
    assert problems == ["[sources] include pattern '../../x/*.md' reaches outside the KB"]


def test_a_trailing_dot_dot_include_is_refused(pair: tuple[Kb, Kb]) -> None:
    """`Path("/kb/..").is_relative_to("/kb")` is **true** lexically, so leaving the final component
    unresolved let `include = ["../.."]` name the KB's parent unreported. That exemption exists so a
    symlinked *document* stays readable, and `..` is never a document."""
    _local, partner = pair
    _found, problems = sidecars_under(partner.root, ["docs/"], ["../.."], [])
    assert problems == ["[sources] include pattern '../..' reaches outside the KB"]


def test_only_double_star_is_dropped_from_the_probe(pair: tuple[Kb, Kb]) -> None:
    """`*` matches exactly **one** component, so a following `..` cancels it and the probe is right
    to keep it. Dropping `*` as well would refuse `*/../../docs/*.md`, which stays inside the KB —
    and a wrongly refused pattern sets `complete` false, freezing that partner's inbound rows
    permanently. Nothing pinned the boundary until this test."""
    _local, partner = pair
    (partner.root / partner.docs_dir / "sub").mkdir()
    _found, problems = sidecars_under(partner.root, ["docs/"], ["*/../../docs/*.md"], [])
    assert problems == []


def test_a_partner_document_without_a_sidecar_contributes_nothing(pair: tuple[Kb, Kb]) -> None:
    """The common case in a real KB, and `if sidecar.is_file()` was pinned by nothing: mutating it
    to `if True` left every test green. A regression would mint a phantom sidecar path per bare
    document, one `LinkedSidecarUnreadableError` each, and `complete=False` permanently."""
    _local, partner = pair
    (partner.root / partner.docs_dir / "bare.md").write_text("# bare\n", encoding="utf-8")

    found, problems = sidecars_under(partner.root, ["docs/"], ["**/*.md"], [])

    assert problems == []
    assert {path.name for path in found} == {
        f"one.md{SIDECAR_SUFFIX}",
        f"two.md{SIDECAR_SUFFIX}",
    }


def test_an_absolute_include_says_it_is_absolute_not_that_it_escapes(pair: tuple[Kb, Kb]) -> None:
    """An absolute pattern cannot be walked at all — `glob` raises `NotImplementedError` on one
    even when it names this KB's own `docs/`. It gets its own message, because the escape wording
    is simply false for that case, and that is what the branch used to say."""
    _local, partner = pair
    inside = partner.root / partner.docs_dir
    _found, problems = sidecars_under(partner.root, ["docs/"], [f"{inside}/*.md"], [])
    assert problems == [
        f"[sources] include pattern '{inside}/*.md' is absolute; patterns are relative to a root"
    ]


def test_a_symlinked_escape_stops_at_the_first_match(
    pair: tuple[Kb, Kb], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The **dynamic** half has to bound the walk too, and its `break` had no test.

    A symlinked directory named under a *glob* component is invisible to the static check — the
    fixed prefix of `*/*.md` is empty, so it lands on the root and passes — and that pattern still
    reaches `glob`. If the escape only `continue`d, the whole outside tree was enumerated before
    anything was refused, which is the defect the commit exists to close, in the half it kept.
    Mutating `break` to `continue` left all 96 tests green.

    The pattern must not name the symlink in its fixed part (`sneak/*.md`), or the static check
    refuses it first and the dynamic half is never reached — a fixture that does not arrive at the
    guard it was written for, which this increment has now shipped three times.

    **Counting `resolve()` cannot see this** — the parent cache collapses it to one call either
    way. What differs is how many entries are pulled from the generator, so that is what is
    counted.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    for index in range(40):
        (outside / f"f{index}.md").write_text("x\n", encoding="utf-8")
    _local, partner = pair
    (partner.root / partner.docs_dir / "sneak").symlink_to(outside)

    consumed = 0
    real_glob = Path.glob

    def counting_glob(self: Path, pattern: str, **kwargs: Any) -> Any:
        nonlocal consumed
        for item in real_glob(self, pattern, **kwargs):
            consumed += 1
            yield item

    monkeypatch.setattr(Path, "glob", counting_glob)
    _found, problems = sidecars_under(partner.root, ["docs/"], ["*/*.md"], [])
    monkeypatch.undo()

    assert problems, "the symlinked escape was not detected at all"
    assert consumed == 1, f"the walk consumed {consumed} of 40 matches before refusing"


def test_an_escape_matching_only_sidecars_is_still_reported(
    pair: tuple[Kb, Kb], tmp_path: Path
) -> None:
    """Containment is checked **before** the `is_file`/sidecar skip, not after.

    A pattern that reaches outside but matches only sidecars — or only directories — hit that
    `continue` first and was never recorded as an escape: the walk left the KB and reported nothing.

    **The pattern has to reach the dynamic half**, which means a symlinked directory named under a
    *glob* component: a `..` is refused on the pattern text, and so is a symlink named in the fixed
    prefix. This fixture has been retargeted twice for exactly that reason — first when the static
    refusal was added, then again when it learned to resolve the prefix — and each time the
    mutation, not the reading, is what showed the test had stopped reaching its guard.
    """
    local, partner = pair
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / f"orphan.md{SIDECAR_SUFFIX}").write_text("id: whatever\n", encoding="utf-8")
    (partner.root / partner.docs_dir / "sneak").symlink_to(outside)

    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]', f'include = ["**/*.md", "*/*{SIDECAR_SUFFIX}"]'
        ),
        encoding="utf-8",
    )

    report = run(local, now="20260730 14:00", scan_links=True)

    assert any("outside the KB" in message for _, message, _ in report.link_scan)


def test_one_escaping_pattern_is_one_problem_however_many_roots(pair: tuple[Kb, Kb]) -> None:
    """The flag was per `(root, pattern)` while its comment argued per *pattern*, so a partner with
    two roots reported the same escape twice — and the reason the comment gives for collapsing it
    (not burying every other issue in the report) applies to the duplicate just as much."""
    local, partner = pair
    (partner.root / "notes").mkdir()
    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        .replace('roots   = ["docs/"]', 'roots   = ["docs/", "notes/"]')
        .replace('include = ["**/*.md"]', 'include = ["**/*.md", "../../elsewhere/*.md"]'),
        encoding="utf-8",
    )

    report = run(local, now="20260730 14:00", scan_links=True)

    escapes = [m for _, m, _ in report.link_scan if "reaches outside the KB" in m]
    assert len(escapes) == 1, escapes


def test_an_exclude_rule_matches_the_path_the_partner_wrote_not_the_resolved_one(
    pair: tuple[Kb, Kb],
) -> None:
    """The containment fix changed `relative` from the unresolved path to the resolved one, which
    silently changed which `exclude` rules fire.

    With `docs/alias -> docs/real` *inside* the KB, `exclude = ["docs/real/*"]` began excluding a
    document reached as `docs/alias/…`. An excluded document is a dropped sidecar, and a dropped
    sidecar with `complete` true is a **deleted inbound row** — the failure the whole `complete`
    machinery exists to prevent, reintroduced by a fix for a different problem.

    The rule is not "resolved or unresolved" but *"whatever the partner's own `walk_sources` does"*:
    this KB must exclude exactly what the partner excludes, and disagreeing in either direction is
    a wrong answer about someone else's KB.
    """
    local, partner = pair
    docs = partner.root / partner.docs_dir
    (docs / "real").mkdir()
    (docs / "real" / "kept.md").write_text("# kept\n\nText.\n", encoding="utf-8")
    (docs / "real" / f"kept.md{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump(
            {"id": str(mint_doc_id()), "links": [{"to": local.uri("beta"), "rel": "via-alias"}]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (docs / "alias").symlink_to(docs / "real")

    manifest = partner.root / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'include = ["**/*.md"]',
            'include = ["**/*.md", "alias/*.md"]\nexclude = ["docs/real/*"]',
        ),
        encoding="utf-8",
    )

    report = run(local, now="20260730 14:00", scan_links=True)

    assert report.ok
    rels = {rel for _, _, _, _, rel in links_in(local, origin="reverse-scan")}
    assert "via-alias" in rels, "an exclude rule fired on the resolved path, dropping the document"


def test_a_symlinked_document_inside_a_partner_kb_is_still_read(
    pair: tuple[Kb, Kb], tmp_path: Path
) -> None:
    """The other direction of the containment fix, so it cannot be tightened into a refusal.

    The check resolves the *parent* and leaves the final component alone — `link._document_in`'s
    spelling — because `Path.glob` does yield a symlinked file, and the partner's own `pnk sync`
    indexes one. Resolving the whole path would drop a legitimate document from the walk, and a
    dropped document is a deleted inbound row.
    """
    local, partner = pair
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / "linked.md").write_text("# linked\n\nText.\n", encoding="utf-8")
    (real / f"linked.md{SIDECAR_SUFFIX}").write_text(
        yaml.safe_dump(
            {"id": str(mint_doc_id()), "links": [{"to": local.uri("beta"), "rel": "via-symlink"}]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    docs = partner.root / partner.docs_dir
    (docs / "linked.md").symlink_to(real / "linked.md")
    (docs / f"linked.md{SIDECAR_SUFFIX}").symlink_to(real / f"linked.md{SIDECAR_SUFFIX}")

    report = run(local, now="20260730 14:00", scan_links=True)

    rels = {rel for _, _, _, _, rel in links_in(local, origin="reverse-scan")}
    assert "via-symlink" in rels, "a symlinked document inside the KB was dropped from the walk"
    assert not any("outside the KB" in message for _, message, _ in report.link_scan)


def test_a_failed_local_run_does_not_blame_the_partner(pair: tuple[Kb, Kb]) -> None:
    """`known_documents` comes from the index, so a document that failed *this run* is absent from
    it — and a true inbound link would be reported as pointing at a document we do not have. We do
    have it; we failed to index it."""
    local, partner = pair
    (local.root / local.docs_dir / f"beta.md{SIDECAR_SUFFIX}").write_text(
        "id: not-a-ulid\n", encoding="utf-8"
    )
    partner.set_links("one", [(local.uri("alpha"), "counterpart"), (local.uri("beta"), "related")])

    report = run(local, now="20260730 14:00", scan_links=True)

    assert not report.ok, "the fixture failed to break the local document"
    assert not any("does not have" in message for _, message, _ in report.link_scan)
    assert len(links_in(local, origin="reverse-scan")) == 2, "the rows are still recorded"


def test_a_mismatched_kb_id_writes_nothing_at_all(tmp_path: Path) -> None:
    """The refusal, not the assignment, is what makes `src_kb_id` safe.

    `src_kb_id` is taken from the partner's own `[kb] id` rather than the manifest's declared one —
    but wherever a row is actually written those two are equal, *because* a mismatch refuses first.
    Mutating the assignment is therefore equivalent code; mutating this guard is not. Trusting the
    declaration would file another KB's links under this alias, and trusting the partner would
    silently redirect a link the local author wrote deliberately: with a permanent ULID, one of the
    two is simply a mistake to fix.
    """
    local = make_kb(tmp_path / "local", "local", ["alpha"])
    partner = make_kb(tmp_path / "partner", "partner", ["one"])
    partner.connect(local, "local")
    partner.set_links("one", [(local.uri("alpha"), "counterpart")])
    local.connect(partner, "partner", kb_id=str(mint_kb_id()))  # declares the wrong ULID

    report = run(local)

    assert links_in(local, origin="reverse-scan") == []
    assert kb_refs(local) == {}, "a KB that was refused must not be stamped as scanned"
    assert any("but the KB at that path is" in message for _, message, _ in report.link_scan)


def test_reverse_rows_never_enter_the_authored_count(pair: tuple[Kb, Kb]) -> None:
    """`pnk doctor` and the density gate both count *authored* links, and the reverse scan must not
    inflate that number — the two populations are the same one by construction, and L7 depends on
    it staying that way. Asserted here rather than in L7 because this is the increment that could
    break it.
    """
    local, _partner = pair
    run(local)

    connection = store.connect_ro(local.root / ".pinakes" / "index.db")
    try:
        authored = connection.execute(
            "SELECT count(*) FROM links WHERE src_kb_id = ? AND origin = 'sidecar'",
            (str(local.kb_id),),
        ).fetchone()[0]
    finally:
        connection.close()

    assert authored == 0, "the local KB authored no links in this fixture"
    assert links_in(local, origin="reverse-scan"), "...but it did learn an inbound one"
