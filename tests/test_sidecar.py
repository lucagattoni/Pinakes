"""Sidecars: the user's file. Identity is permanent, unknown keys survive, links resolve."""

from pathlib import Path

import pytest
import yaml

from pinakes.errors import SidecarError
from pinakes.ids import KbId, mint_doc_id, mint_kb_id
from pinakes.sidecar import (
    SIDECAR_SUFFIX,
    Link,
    Sidecar,
    create,
    document_for,
    extraction_provenance,
    find_duplicate_ids,
    is_sidecar,
    read,
    sidecar_path,
    skeleton,
    with_extraction_provenance,
    without_extraction_provenance,
    write,
)
from pinakes.uri import PnkUri


@pytest.fixture
def owner() -> KbId:
    return mint_kb_id()


def test_paths_append_rather_than_substitute() -> None:
    assert sidecar_path(Path("docs/paper.pdf")).name == f"paper.pdf{SIDECAR_SUFFIX}"
    assert sidecar_path(Path("docs/notes.md")).name == f"notes.md{SIDECAR_SUFFIX}"
    assert document_for(Path(f"docs/paper.pdf{SIDECAR_SUFFIX}")) == Path("docs/paper.pdf")
    assert is_sidecar(Path(f"a{SIDECAR_SUFFIX}"))
    assert not is_sidecar(Path("a.yaml"))


def test_document_for_rejects_a_non_sidecar() -> None:
    with pytest.raises(SidecarError):
        document_for(Path("docs/notes.md"))


def test_round_trip_preserves_everything_including_unknown_keys(
    tmp_path: Path, owner: KbId
) -> None:
    """A sidecar is a file a person may extend; a rewrite that drops their fields is data loss."""
    doc_id, other_kb, other_doc = mint_doc_id(), mint_kb_id(), mint_doc_id()
    path = tmp_path / f"notes.md{SIDECAR_SUFFIX}"
    path.write_text(
        yaml.safe_dump(
            {
                "id": doc_id,
                "title": "Attention",
                "tags": ["transformers", "architecture"],
                "created": "20260725 09:14",
                "links": [{"to": f"pnk://{other_kb}/{other_doc}", "rel": "cites"}],
                "provenance": {"source": "https://arxiv.org/abs/1706.03762"},
                "reading_status": "done",
                "my_own_field": {"nested": [1, 2]},
            }
        ),
        encoding="utf-8",
    )

    loaded = read(path, owner=owner)
    assert loaded.id == doc_id
    assert loaded.tags == ("transformers", "architecture")
    assert loaded.links[0].to == PnkUri(kb=other_kb, doc=other_doc)
    assert loaded.extra == {"reading_status": "done", "my_own_field": {"nested": [1, 2]}}

    write(path, loaded)
    reloaded = read(path, owner=owner)
    assert reloaded == loaded
    assert "reading_status" in path.read_text(encoding="utf-8")


def test_self_links_are_expanded_on_read(tmp_path: Path, owner: KbId) -> None:
    """A sidecar copied into another KB must keep pointing where it always pointed (§2.2)."""
    target = mint_doc_id()
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text(
        yaml.safe_dump(
            {"id": mint_doc_id(), "links": [{"to": f"pnk://self/{target}", "rel": "supersedes"}]}
        ),
        encoding="utf-8",
    )

    loaded = read(path, owner=owner)
    assert loaded.links[0].to == PnkUri(kb=owner, doc=target)

    write(path, loaded)
    assert "self" not in path.read_text(encoding="utf-8")


def test_written_files_carry_no_content_hash(tmp_path: Path, owner: KbId) -> None:
    """§2.2: change detection is the index's job; a hash here would churn and go stale."""
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    write(path, skeleton(Path("docs/a.md"), created="20260725 09:14"))
    assert "content_hash" not in path.read_text(encoding="utf-8")


def test_skeleton_mints_an_id_and_a_readable_title() -> None:
    made = skeleton(Path("docs/my-research-notes.md"))
    assert made.id
    assert made.title == "my research notes"
    assert made.links == ()


def test_missing_id_is_an_error_that_explains_why(tmp_path: Path, owner: KbId) -> None:
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text("title: no id here\n", encoding="utf-8")
    with pytest.raises(SidecarError) as exc_info:
        read(path, owner=owner)
    assert "has no `id`" in exc_info.value.message


def test_a_hand_broken_id_says_not_to_renumber(tmp_path: Path, owner: KbId) -> None:
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text("id: not-a-ulid\n", encoding="utf-8")
    with pytest.raises(SidecarError) as exc_info:
        read(path, owner=owner)
    assert "Restore the original id" in exc_info.value.remedy


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("", "is empty"),
        ("- a\n- b\n", "must be a mapping"),
        ("id: [1]\n", "`id` must be a string"),
        ("{id: x, : }", "is not valid YAML"),
    ],
)
def test_malformed_sidecars_are_rejected(
    tmp_path: Path, owner: KbId, body: str, expected: str
) -> None:
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(SidecarError) as exc_info:
        read(path, owner=owner)
    assert expected in exc_info.value.message


@pytest.mark.parametrize(
    ("links", "expected"),
    [
        ("links: notalist", "`links` must be a list"),
        ("links:\n  - to: pnk://x/y\n    rel: cites", "not a valid pnk:// URI"),
        ("links:\n  - rel: cites", "needs a `to` URI"),
        ("links:\n  - to: pnk://self/01KYCJ8ZVMBJDB4FKRJRNYS5DT\n    rel: ''", "non-empty `rel`"),
        ("links:\n  - just a string", "must be a mapping"),
    ],
)
def test_malformed_links_name_their_position(
    tmp_path: Path, owner: KbId, links: str, expected: str
) -> None:
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\n{links}\n", encoding="utf-8")
    with pytest.raises(SidecarError) as exc_info:
        read(path, owner=owner)
    assert expected in exc_info.value.message


def test_an_alias_in_a_link_is_rejected(tmp_path: Path, owner: KbId) -> None:
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nlinks:\n  - to: pnk://archive/{mint_doc_id()}\n    rel: cites\n",
        encoding="utf-8",
    )
    with pytest.raises(SidecarError) as exc_info:
        read(path, owner=owner)
    assert "[[links.kb]]" in exc_info.value.message


def test_tags_must_be_strings(tmp_path: Path, owner: KbId) -> None:
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\ntags: [ok, 3]\n", encoding="utf-8")
    with pytest.raises(SidecarError) as exc_info:
        read(path, owner=owner)
    assert "`tags` must be strings" in exc_info.value.message


def test_duplicate_ids_are_found_and_reported_with_every_path() -> None:
    """§6.4 makes this a hard error: renumbering would break links that were fine."""
    shared, unique = mint_doc_id(), mint_doc_id()
    found = find_duplicate_ids(
        {
            Path("docs/a.md.pnk.yaml"): Sidecar(id=shared),
            Path("docs/b.md.pnk.yaml"): Sidecar(id=shared),
            Path("docs/c.md.pnk.yaml"): Sidecar(id=unique),
        }
    )
    assert list(found) == [shared]
    assert found[shared] == [Path("docs/a.md.pnk.yaml"), Path("docs/b.md.pnk.yaml")]


def test_no_duplicates_is_an_empty_result() -> None:
    assert find_duplicate_ids({Path("a"): Sidecar(id=mint_doc_id())}) == {}


def test_an_explicit_empty_value_survives_a_round_trip(tmp_path: Path, owner: KbId) -> None:
    """`tags: []` is something the user wrote; writing back must not quietly delete it."""
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\ntags: []\nprovenance: {{}}\n", encoding="utf-8")

    write(path, read(path, owner=owner))
    written = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert written["tags"] == []
    assert written["provenance"] == {}


def test_a_skeleton_writes_no_empty_keys(tmp_path: Path) -> None:
    """The other half of the rule: absent stays absent."""
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    write(path, skeleton(Path("docs/a.md")))
    written = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert set(written) == {"id", "title"}


def test_writing_is_atomic_and_leaves_no_debris(tmp_path: Path, owner: KbId) -> None:
    """A truncated sidecar loses the permanent id, and every inbound link with it."""
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    write(path, skeleton(Path("docs/a.md")))
    original = read(path, owner=owner)

    write(path, original)
    assert list(tmp_path.iterdir()) == [path]
    assert read(path, owner=owner).id == original.id


def test_every_known_key_is_written_back(tmp_path: Path, owner: KbId) -> None:
    """A key this module claims to understand but never writes would be silent data loss."""
    from pinakes.sidecar import KNOWN_KEYS

    kb, doc = mint_kb_id(), mint_doc_id()
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text(
        yaml.safe_dump(
            {
                "id": mint_doc_id(),
                "title": "t",
                "tags": ["x"],
                "created": "20260725 09:14",
                "links": [{"to": f"pnk://{kb}/{doc}", "rel": "cites"}],
                "provenance": {"source": "s"},
            }
        ),
        encoding="utf-8",
    )
    write(path, read(path, owner=owner))
    assert set(yaml.safe_load(path.read_text(encoding="utf-8"))) == set(KNOWN_KEYS)


def test_unreadable_file_reports_the_path(tmp_path: Path, owner: KbId) -> None:
    with pytest.raises(SidecarError) as exc_info:
        read(tmp_path / "missing.pnk.yaml", owner=owner)
    assert "cannot be read" in exc_info.value.message


def test_links_are_written_as_strings_not_objects(tmp_path: Path, owner: KbId) -> None:
    kb, doc = mint_kb_id(), mint_doc_id()
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    write(path, Sidecar(id=mint_doc_id(), links=(Link(to=PnkUri(kb=kb, doc=doc), rel="cites"),)))
    written = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert written["links"] == [{"to": f"pnk://{kb}/{doc}", "rel": "cites"}]


def test_extraction_provenance_is_none_on_a_fresh_skeleton(tmp_path: Path) -> None:
    assert extraction_provenance(skeleton(tmp_path / "a.pdf")) is None


def test_with_extraction_provenance_merges_additively(tmp_path: Path, owner: KbId) -> None:
    """The one existing `provenance` key (e.g. a hand-written `source`) must survive — I5's
    read-merge-write is additive, never a replacement of the whole block (plan text)."""
    original = Sidecar(id=mint_doc_id(), provenance={"source": "scanned by hand"})

    stamped = with_extraction_provenance(
        original,
        backend="claude-vision",
        fingerprint="fp1",
        extracted="20260728 12:00",
        content_hash="sha256:abc",
    )

    assert stamped.provenance["source"] == "scanned by hand"
    assert extraction_provenance(stamped) == ("claude-vision", "fp1", "sha256:abc")

    path = tmp_path / f"a.pdf{SIDECAR_SUFFIX}"
    write(path, stamped)
    reread = read(path, owner=owner)
    assert reread.provenance["source"] == "scanned by hand"
    assert extraction_provenance(reread) == ("claude-vision", "fp1", "sha256:abc")


def test_extraction_provenance_tolerates_a_hand_edited_block(tmp_path: Path, owner: KbId) -> None:
    """A sidecar is user-owned (module docstring): a malformed `provenance.extraction` is treated
    as never-extracted, not a reason to fail the whole sync over a decoration field."""
    path = tmp_path / f"a.pdf{SIDECAR_SUFFIX}"
    write(
        path,
        Sidecar(id=mint_doc_id(), provenance={"extraction": {"backend": "claude-vision"}}),
    )  # no `fingerprint`, no `content_hash`
    assert extraction_provenance(read(path, owner=owner)) is None


def test_extraction_provenance_requires_content_hash_too(tmp_path: Path, owner: KbId) -> None:
    """A sidecar written before this field existed (or hand-edited to drop it) must not be
    misread as "has provenance but with a blank content_hash" — it is simply unreadable, same as
    a missing `fingerprint`, per this function's own tolerance rule."""
    path = tmp_path / f"a.pdf{SIDECAR_SUFFIX}"
    write(
        path,
        Sidecar(
            id=mint_doc_id(),
            provenance={"extraction": {"backend": "claude-vision", "fingerprint": "fp1"}},
        ),  # no `content_hash`
    )
    assert extraction_provenance(read(path, owner=owner)) is None


def test_without_extraction_provenance_clears_only_that_key(tmp_path: Path, owner: KbId) -> None:
    """`--force` overwriting a paid extraction with a free one must not also erase an unrelated,
    hand-written provenance key sitting beside it."""
    stamped = with_extraction_provenance(
        Sidecar(id=mint_doc_id(), provenance={"source": "scanned by hand"}),
        backend="claude-vision",
        fingerprint="fp1",
        extracted="20260728 12:00",
        content_hash="sha256:abc",
    )

    cleared = without_extraction_provenance(stamped)

    assert extraction_provenance(cleared) is None
    assert cleared.provenance["source"] == "scanned by hand"
    assert "provenance" in cleared.present

    path = tmp_path / f"a.pdf{SIDECAR_SUFFIX}"
    write(path, cleared)
    reread = read(path, owner=owner)
    assert extraction_provenance(reread) is None
    assert reread.provenance["source"] == "scanned by hand"


def test_without_extraction_provenance_drops_an_empty_block_entirely(
    tmp_path: Path, owner: KbId
) -> None:
    """When `extraction` was the only provenance key, clearing it should leave the sidecar looking
    exactly as it would if the paid extraction had never happened — no stray `provenance: {}`."""
    stamped = with_extraction_provenance(
        Sidecar(id=mint_doc_id()),
        backend="claude-vision",
        fingerprint="fp1",
        extracted="20260728",
        content_hash="sha256:abc",
    )

    cleared = without_extraction_provenance(stamped)

    assert cleared.provenance == {}
    assert "provenance" not in cleared.present

    path = tmp_path / f"a.pdf{SIDECAR_SUFFIX}"
    write(path, cleared)
    assert "provenance" not in yaml.safe_load(path.read_text(encoding="utf-8"))


# --- Minting never writes over a file that is already there ------------------------------------


def test_create_writes_a_sidecar_where_there_is_none(tmp_path: Path) -> None:
    target = tmp_path / f"note.md{SIDECAR_SUFFIX}"
    made = skeleton(tmp_path / "note.md", created="20260729 07:00")

    create(target, made)

    assert yaml.safe_load(target.read_text(encoding="utf-8"))["id"] == str(made.id)


def test_create_refuses_to_overwrite_an_existing_sidecar(tmp_path: Path) -> None:
    """The invariant lives at the write, not in the caller that happens to reach it today: a
    freshly minted id written over an existing sidecar replaces a *permanent* ULID with a different
    one, and every inbound pnk:// link points at the old one with no migration by design."""
    target = tmp_path / f"note.md{SIDECAR_SUFFIX}"
    original = "id: 01KYCPXAJWWAK83Z0KBK6Y3NHR\ntitle: mine\n"
    target.write_text(original, encoding="utf-8")

    with pytest.raises(SidecarError) as caught:
        create(target, skeleton(tmp_path / "note.md", created="20260729 07:00"))

    assert "already exists" in str(caught.value)
    assert "permanent ULID" in (caught.value.remedy or "")
    assert target.read_text(encoding="utf-8") == original


def test_write_still_overwrites_because_a_merge_needs_it(tmp_path: Path) -> None:
    """`create` is the new refusal; `write` must keep overwriting, or I5's read-merge-write of
    `provenance.extraction` into an existing sidecar has nowhere to land."""
    target = tmp_path / f"note.md{SIDECAR_SUFFIX}"
    target.write_text("id: 01KYCPXAJWWAK83Z0KBK6Y3NHR\ntitle: before\n", encoding="utf-8")
    kept = read(target, owner=mint_kb_id())

    write(target, Sidecar(id=kept.id, title="after", present=kept.present))

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {
        "id": "01KYCPXAJWWAK83Z0KBK6Y3NHR",
        "title": "after",
    }


def test_create_refuses_a_dangling_symlink_too(tmp_path: Path) -> None:
    """`Path.exists()` follows symlinks and reports False for a dangling one, so `os.replace` would
    quietly turn the link into a regular file. Nothing holding a ULID is lost, but the guard means
    "refuse where something is already there" and a narrower predicate drifts from its own rule."""
    target = tmp_path / f"note.md{SIDECAR_SUFFIX}"
    target.symlink_to(tmp_path / "nowhere.yaml")

    with pytest.raises(SidecarError):
        create(target, skeleton(tmp_path / "note.md", created="20260729 07:00"))

    assert target.is_symlink()
