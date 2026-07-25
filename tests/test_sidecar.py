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
    document_for,
    find_duplicate_ids,
    is_sidecar,
    read,
    sidecar_path,
    skeleton,
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
    assert made.title == "my research notes.md" or made.title == "my research notes"
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
