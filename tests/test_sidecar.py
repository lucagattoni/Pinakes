"""Sidecars: the user's file. Identity is permanent, unknown keys survive, links resolve."""

from dataclasses import replace
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
        # An unclosed flow mapping, which **both** libraries reject as a parse error. The old
        # fixture `{id: x, : }` relied on PyYAML refusing an empty key; ruamel parses it and the
        # case then fell through to the `id` check, testing nothing about the parse-error branch.
        ("{id: x", "is not valid YAML"),
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


# --- The ruamel round-trip (L5b) ---------------------------------------------------------------
#
# **Every comment test compares file bytes.** `CommentedMap.__eq__` ignores comments entirely, so a
# test asserting `read(p) == before` passes with every comment in the file destroyed. What is being
# claimed here is a property of the *file*, and only the file can witness it.

ANNOTATED = """\
# Transcribed from the 1974 accession register, box 12.
# Do not renumber `id` — every inbound link depends on it.
id: {id}
title: "Loans outward, 1974"      # as printed on the register spine
tags:
- accessions
- loans          # kept for the quarterly report
created: "20260725 18:00"

links:
# The counterpart record in the partner archive:
- to: {counterpart}
  rel: counterpart

notes: |
  Two folios are missing from this box.
  The gap is recorded in the 1975 audit.
shelf: 0755
country: NO
"""


def _annotated(tmp_path: Path, owner: KbId) -> tuple[Path, str]:
    """A sidecar with everything PyYAML used to destroy, written the way a person would write it."""
    doc = mint_doc_id()
    body = ANNOTATED.format(id=doc, counterpart=f"pnk://{mint_kb_id()}/{mint_doc_id()}")
    path = tmp_path / f"a.md{SIDECAR_SUFFIX}"
    path.write_text(body, encoding="utf-8")
    return path, body


def test_comments_survive_a_rewrite(tmp_path: Path, owner: KbId) -> None:
    path, before = _annotated(tmp_path, owner)
    write(path, read(path, owner=owner))
    after = path.read_text(encoding="utf-8")

    assert "# Transcribed from the 1974 accession register, box 12." in after
    assert "# Do not renumber `id`" in after
    assert "# as printed on the register spine" in after
    assert "# kept for the quarterly report" in after
    assert after.count("#") == before.count("#"), "no comment gained or lost"


def test_quoting_style_survives_a_rewrite(tmp_path: Path, owner: KbId) -> None:
    """PyYAML emitted `title: Loans outward, 1974` — bare. `preserve_quotes` is what stops that."""
    path, _ = _annotated(tmp_path, owner)
    write(path, read(path, owner=owner))
    assert 'title: "Loans outward, 1974"' in path.read_text(encoding="utf-8")


def test_block_scalars_and_blank_lines_survive_a_rewrite(tmp_path: Path, owner: KbId) -> None:
    """PyYAML turned `notes: |` into a single-quoted blob with blank lines spliced in."""
    path, before = _annotated(tmp_path, owner)
    write(path, read(path, owner=owner))
    after = path.read_text(encoding="utf-8")

    assert "notes: |" in after
    assert "  Two folios are missing from this box." in after
    assert after.count("\n\n") == before.count("\n\n"), "blank-line structure is part of the file"


def test_yaml_1_1_scalars_are_no_longer_corrupted(tmp_path: Path, owner: KbId) -> None:
    """The bug that is not about comments. Under YAML 1.1 these were read as `False` and `493` and
    written back that way — on keys this module documents as round-tripped untouched."""
    path, _ = _annotated(tmp_path, owner)
    parsed = read(path, owner=owner)
    assert parsed.extra["country"] == "NO", "PyYAML read this as False"
    # `0755` is not octal in YAML 1.2, so the value is 755 rather than PyYAML's 493 — and ruamel
    # remembers the written form, so the file keeps `0755` regardless of what the number is.
    assert parsed.extra["shelf"] == 755, "PyYAML read this as 493"

    write(path, parsed)
    after = path.read_text(encoding="utf-8")
    assert "country: NO" in after and "shelf: 0755" in after
    # Asserted as whole lines: a minted ULID can contain `493`, and a bare substring test would
    # then pass or fail depending on the id, which is the definition of a flaky assertion.
    lines = after.splitlines()
    assert "country: false" not in lines and "shelf: 493" not in lines


def test_an_unknown_key_round_trips_byte_identically(tmp_path: Path, owner: KbId) -> None:
    """The invariant this increment introduces, stated over the bytes rather than over a dict."""
    path, before = _annotated(tmp_path, owner)
    write(path, read(path, owner=owner))
    assert path.read_text(encoding="utf-8") == before


def test_the_users_key_order_is_preserved_on_rewrite(tmp_path: Path, owner: KbId) -> None:
    """Canonical ordering is for minting. An existing file keeps the order its author chose —
    `sorted(extra)` on this path would reorder a document nobody edited."""
    path = tmp_path / f"b.md{SIDECAR_SUFFIX}"
    path.write_text(f"zebra: last\nid: {mint_doc_id()}\nalpha: first\n", encoding="utf-8")
    write(path, read(path, owner=owner))
    assert [line.split(":")[0] for line in path.read_text(encoding="utf-8").splitlines()] == [
        "zebra",
        "id",
        "alpha",
    ]


def test_a_minted_sidecar_still_uses_canonical_order(tmp_path: Path) -> None:
    path = tmp_path / f"c.md{SIDECAR_SUFFIX}"
    write(path, skeleton(Path("docs/c.md"), created="20260725 18:00"))
    keys = [line.split(":")[0] for line in path.read_text(encoding="utf-8").splitlines()]
    assert keys[0] == "id" and "title" in keys and "created" in keys


def test_a_value_with_spaces_past_eighty_columns_is_not_folded(tmp_path: Path, owner: KbId) -> None:
    """ruamel's default `width` is 80 and folds a long value across lines — changing a file nobody
    edited. `width = 4096` is what keeps it on one line."""
    long_value = " ".join(["preservation"] * 20)
    path = tmp_path / f"d.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\nnote: {long_value}\n", encoding="utf-8")
    write(path, read(path, owner=owner))
    assert f"note: {long_value}" in path.read_text(encoding="utf-8")


def test_a_duplicate_key_is_refused_without_ruamels_suppression_url(
    tmp_path: Path, owner: KbId
) -> None:
    """PyYAML took the last silently. Which value was meant is exactly what nobody can recover —
    and ruamel's own message ends with a URL for switching the check off, which must not travel."""
    path = tmp_path / f"e.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\ntitle: First\ntitle: Second\n", encoding="utf-8")
    with pytest.raises(SidecarError) as caught:
        read(path, owner=owner)
    assert "repeats a key" in caught.value.message
    assert "http" not in caught.value.message and "suppress" not in caught.value.message.lower()
    assert caught.value.remedy


def test_a_minted_title_that_looks_like_a_boolean_is_quoted(tmp_path: Path) -> None:
    """`skeleton()` derives the title from the filename stem, so `NO.md` mints `title: NO` — which
    a YAML 1.1 reader takes as `False`. Read back **through PyYAML**, deliberately: after this
    increment nothing else in the repo reads 1.1, so nothing else keeps the claim honest."""
    path = tmp_path / f"NO.md{SIDECAR_SUFFIX}"
    write(path, skeleton(Path("docs/NO.md"), created="20260725 18:00"))
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["title"] == "NO"


def test_a_two_space_indented_sequence_is_reindented(tmp_path: Path, owner: KbId) -> None:
    """A **documented exclusion** from the byte-identity invariant, pinned so it stays documented.

    ruamel emits block sequences at the dumper's indentation, not the source's, so a file written
    with `  - item` comes back as `- item`. Nothing is lost — comments, values and order all
    survive — but the bytes differ, and the invariant CLAUDE.md gains says so explicitly.
    `docs/GUIDE.md`'s `links:` example is written in the indented style and is the counter-example,
    not a typo.
    """
    path = tmp_path / f"f.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\ntags:\n  - one   # kept\n  - two\n", encoding="utf-8")
    write(path, read(path, owner=owner))
    after = path.read_text(encoding="utf-8")

    assert "\n- one" in after and "\n- two" in after, "reindented to the dumper's style"
    assert "# kept" in after, "and the comment rides along with it"


def _provenanced(tmp_path: Path, name: str = "g") -> Path:
    """A sidecar already carrying `provenance.extraction`, commented at the nested map's **last
    key** — the only position that reproduces the loss, because ruamel stores a comment as the
    *preceding* key's trailer, so a comment describing a sibling of `extraction` lives inside it."""
    path = tmp_path / f"{name}.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\n"
        "provenance:\n"
        "  extraction:\n"
        "    backend: claude-vision\n"
        "    fingerprint: fp-1\n"
        "    extracted: '20260725 18:00'\n"
        "    content_hash: abc   # the file's hash when this extraction ran\n"
        "  note: hand-checked against the register\n",
        encoding="utf-8",
    )
    return path


def test_a_comment_inside_provenance_extraction_survives_a_re_extraction(
    tmp_path: Path, owner: KbId
) -> None:
    """A one-level merge assigns a plain `dict` over the loaded `extraction` node and takes the
    comment with it — this is the nested case that catches it."""
    path = _provenanced(tmp_path)
    write(
        path,
        with_extraction_provenance(
            read(path, owner=owner),
            backend="claude-vision",
            fingerprint="fp-2",
            extracted="20260726 09:00",
            content_hash="def",
        ),
    )
    after = path.read_text(encoding="utf-8")

    assert "# the file's hash when this extraction ran" in after
    assert "note: hand-checked against the register" in after
    assert "fingerprint: fp-2" in after and "fp-1" not in after


def test_with_extraction_provenance_preserves_comments(tmp_path: Path, owner: KbId) -> None:
    path = _provenanced(tmp_path, "h")
    before = path.read_text(encoding="utf-8").count("#")
    write(
        path,
        with_extraction_provenance(
            read(path, owner=owner),
            backend="claude-vision",
            fingerprint="fp-2",
            extracted="20260726 09:00",
            content_hash="def",
        ),
    )
    assert path.read_text(encoding="utf-8").count("#") == before


def test_without_extraction_provenance_preserves_comments(tmp_path: Path, owner: KbId) -> None:
    """The `--force` reversal. `extraction` must actually go — a merge that only assigns would
    leave the stale paid claim in place, silently failing the invariant DESIGN §2.2 states."""
    path = _provenanced(tmp_path, "i")
    write(path, without_extraction_provenance(read(path, owner=owner)))
    after = path.read_text(encoding="utf-8")

    assert "extraction:" not in after, "the stale paid claim must be gone"
    assert "note: hand-checked against the register" in after, "its sibling stays"


def test_provenance_first_appearing_is_appended_and_moves_no_comment(
    tmp_path: Path, owner: KbId
) -> None:
    """Appended at the end, never inserted at its canonical position: ruamel binds a comment to its
    *preceding* key, so inserting `provenance` above an unknown key would leave that key's own
    comment reading as though it introduced `provenance`."""
    path = tmp_path / f"j.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\n# describes the shelf below, and nothing else\nshelf: A12\n",
        encoding="utf-8",
    )
    write(
        path,
        with_extraction_provenance(
            read(path, owner=owner),
            backend="claude-vision",
            fingerprint="fp-1",
            extracted="20260726 09:00",
            content_hash="abc",
        ),
    )
    lines = path.read_text(encoding="utf-8").splitlines()

    comment = lines.index("# describes the shelf below, and nothing else")
    assert lines[comment + 1].startswith("shelf:"), "the comment still introduces `shelf`"
    assert lines.index("provenance:") > comment, "appended after the user's keys"


def test_reordering_links_does_not_move_their_comments(tmp_path: Path, owner: KbId) -> None:
    """Reconciled by `to`, never by position. Positional matching silently reattaches the user's
    prose to a different link the moment the list is reordered — worse than losing it, because the
    comment then describes the wrong thing."""
    kb, first, second = mint_kb_id(), mint_doc_id(), mint_doc_id()
    path = tmp_path / f"k.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\n"
        "links:\n"
        "# the counterpart in the partner archive\n"
        f"- to: pnk://{kb}/{first}\n"
        "  rel: counterpart\n"
        "# superseded by the 1975 revision\n"
        f"- to: pnk://{kb}/{second}\n"
        "  rel: supersedes\n",
        encoding="utf-8",
    )
    parsed = read(path, owner=owner)
    reordered = replace(parsed, links=tuple(reversed(parsed.links)))
    write(path, reordered)
    lines = path.read_text(encoding="utf-8").splitlines()

    # Both assertions matter and neither implies the other: a rebuild that wipes ruamel's comment
    # metadata outright leaves *no* comment misattributed, so the "stayed with its own link" check
    # passes vacuously unless presence is asserted first.
    assert path.read_text(encoding="utf-8").count("#") == 2, "both comments are still there"
    counterpart = lines.index("# the counterpart in the partner archive")
    assert str(first) in lines[counterpart + 1], "the comment stayed with its own link"
    superseded = lines.index("# superseded by the 1975 revision")
    assert str(second) in lines[superseded + 1]


def test_unknown_keys_inside_a_link_entry_survive_a_rewrite(tmp_path: Path, owner: KbId) -> None:
    """Nothing is deleted from inside a matched entry: `_links()` surfaces `to` and `rel` alone, so
    a delete-what-is-missing merge there would destroy what DESIGN §2.2 requires to round-trip."""
    kb, target = mint_kb_id(), mint_doc_id()
    path = tmp_path / f"l.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nlinks:\n- to: pnk://{kb}/{target}\n  rel: related\n"
        "  confidence: high\n  noted: '20260725'\n",
        encoding="utf-8",
    )
    write(path, read(path, owner=owner))
    after = path.read_text(encoding="utf-8")

    assert "confidence: high" in after and "noted: '20260725'" in after


def test_the_original_document_is_excluded_from_equality(tmp_path: Path, owner: KbId) -> None:
    """Same fields, same sidecar — whether or not one of them still remembers a file."""
    path, _ = _annotated(tmp_path, owner)
    parsed = read(path, owner=owner)
    assert parsed.original is not None
    assert replace(parsed, original=None) == parsed


def test_deleting_a_commented_key_loses_one_comment_and_misattributes_another(
    tmp_path: Path, owner: KbId
) -> None:
    """**A known limitation, pinned rather than fixed.** ruamel binds a comment to its preceding
    key, so deleting a key drops that key's own comment and leaves the one above it attached to
    whatever follows. Reachable through `without_extraction_provenance`."""
    path = tmp_path / f"m.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\n"
        "provenance:\n"
        "  # introduces extraction\n"
        "  extraction:\n"
        "    backend: claude-vision\n"
        "    fingerprint: fp-1\n"
        "    extracted: '20260725 18:00'\n"
        "    content_hash: abc\n"
        "  # introduces note\n"
        "  note: kept\n",
        encoding="utf-8",
    )
    write(path, without_extraction_provenance(read(path, owner=owner)))
    after = path.read_text(encoding="utf-8")

    assert "note: kept" in after, "the surviving key is intact"
    # Measured, and this is the shape of the loss: the comment that *preceded* the deleted key
    # survives and reattaches to whatever follows — so it now introduces the wrong thing — while
    # the surviving key's own comment is the one that disappears.
    assert "# introduces extraction" in after, "misattributed, not deleted"
    lines = after.splitlines()
    assert lines[lines.index("  # introduces extraction") + 1].strip() == "note: kept"
    assert "# introduces note" not in after, "this is the one that is silently lost"


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ("blob: !!binary aGk=", "bytes"),
        ("members: !!set\n  ? a", "a set"),
        ("when: !!timestamp 2026-07-31", "a timestamp"),
        ("when: 2026-07-31", "a bare date"),
        ("thing: !whatever v", "an unknown tag"),
        ("!whatever k: v", "a tagged key"),
        ("m:\n  1: a\n  b: c", "a mapping mixing string and non-string keys"),
    ],
)
def test_a_json_unencodable_extra_value_is_refused_with_a_remedy(
    tmp_path: Path, owner: KbId, body: str, why: str
) -> None:
    """The index stores metadata as JSON, so `read()` refuses what `json.dumps` would not take.

    **Equivalence, not a new refusal.** PyYAML rejects an unknown tag today as a clean
    `SidecarError`; ruamel returns a `TaggedScalar`, so without this the swap alone would turn that
    clean error into a traceback out of `pnk sync`.

    The mixed-key case is why the check encodes the **assembled mapping** rather than each value:
    both values there are perfectly encodable on their own, and the failure is a comparison
    *between* the keys.
    """
    path = tmp_path / f"n.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\n{body}\n", encoding="utf-8")
    with pytest.raises(SidecarError) as caught:
        read(path, owner=owner)
    assert "cannot store" in caught.value.message, why
    assert "JSON" in caught.value.remedy


def test_a_double_bang_str_value_is_refused(tmp_path: Path, owner: KbId) -> None:
    """`!!str` is the only *working* tag that breaks — `!!int`, `!!float`, `!!bool`, `!!seq` and
    `!!map` all worked before the swap and still do. It is a documented breaking change."""
    path = tmp_path / f"o.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\nlabel: !!str hello\n", encoding="utf-8")
    with pytest.raises(SidecarError):
        read(path, owner=owner)


def test_the_standard_tags_that_worked_before_the_swap_still_work(
    tmp_path: Path, owner: KbId
) -> None:
    """The other half of that claim, asserted rather than implied."""
    path = tmp_path / f"p.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\ni: !!int 5\nf: !!float 1.5\nb: !!bool true\n"
        "s: !!seq [a]\nm: !!map {a: b}\n",
        encoding="utf-8",
    )
    extra = read(path, owner=owner).extra
    assert extra["i"] == 5 and extra["f"] == 1.5 and extra["b"] is True
    assert extra["s"] == ["a"] and extra["m"] == {"a": "b"}


def test_a_tagged_mapping_is_accepted_because_it_serialises(tmp_path: Path, owner: KbId) -> None:
    """The **documented widening**: a *custom*-tagged mapping or sequence is `ConstructorError`
    under PyYAML and a `CommentedMap` after — so it is now accepted. Not `!!map`/`!!seq`, which
    were never refused."""
    path = tmp_path / f"q.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\nblock: !custom\n  a: 1\n", encoding="utf-8")
    assert read(path, owner=owner).extra["block"] == {"a": 1}


def test_a_non_string_key_at_the_top_level_is_refused(tmp_path: Path, owner: KbId) -> None:
    """The union escape. `{1: a}` is uniformly int-keyed, so `extra` alone sorts and encodes —
    and `_metadata()` then merges it with the string keys `tags` and `provenance`, making the
    union mixed and `json.dumps(sort_keys=True)` raise out of `pnk sync`.

    Checking the parts is not checking the whole: the comparison that fails is between keys that
    meet nowhere but in the assembled metadata.
    """
    path = tmp_path / f"jj.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\n1: a\n", encoding="utf-8")
    with pytest.raises(SidecarError) as caught:
        read(path, owner=owner)
    assert "cannot store" in caught.value.message
    assert "keys must all be strings" in caught.value.remedy


def test_a_uniformly_non_string_keyed_mapping_is_a_stated_residual(
    tmp_path: Path, owner: KbId
) -> None:
    """`sort_keys=True` catches **mixed**-type keys only. A uniformly int-keyed mapping is accepted
    and silently coerced to string keys by `json.dumps`, at any depth — identical under PyYAML
    today, so not a regression, but the invariant is not absolute and this pins that."""
    path = tmp_path / f"r.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\nm:\n  1: a\n  2: b\n", encoding="utf-8")
    assert read(path, owner=owner).extra["m"] == {1: "a", 2: "b"}
    # *Nested* is the residual. At the **top level** the same shape is refused, because the
    # assembled metadata puts it beside `tags` and `provenance` — see the test above.


def test_a_comment_on_a_tags_entry_survives_a_rewrite(tmp_path: Path, owner: KbId) -> None:
    """`tags` was specified as "a list of plain strings with no per-entry comments" and replaced
    wholesale. Measured, ruamel stores a comment on a `tags` entry exactly as on a `links` entry —
    so the increment whose purpose is to stop destroying comments was specified to destroy these."""
    path = tmp_path / f"s.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\ntags:\n- accessions   # the department that owns this\n- loans\n",
        encoding="utf-8",
    )
    write(path, read(path, owner=owner))
    assert "# the department that owns this" in path.read_text(encoding="utf-8")


def test_an_unchanged_known_key_is_not_reassigned(tmp_path: Path, owner: KbId) -> None:
    """The property, on **node identity** rather than on bytes — bytes can match by luck.

    It does **not** guard the unchanged-key short-circuit: `_merge_tags` mutates the sequence in
    place and never reassigns `document["tags"]`, so this identity holds with the rule removed.
    Nothing here can distinguish them, and the reason is worth knowing rather than papering over.
    """
    path = tmp_path / f"t.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\ntags:\n- one   # kept\n- two\nlinks: []\n", encoding="utf-8"
    )
    parsed = read(path, owner=owner)
    assert parsed.original is not None
    before = parsed.original["tags"]

    write(path, parsed)
    assert parsed.original["tags"] is before, "the node itself must not be replaced"
    assert "# kept" in path.read_text(encoding="utf-8")


def test_changed_tags_keep_the_comments_of_the_entries_that_remain(
    tmp_path: Path, owner: KbId
) -> None:
    """When they *do* change, reconciliation is by value — so a surviving entry keeps its comment
    and only a genuinely removed one loses it."""
    path = tmp_path / f"u.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\ntags:\n- accessions   # the department\n- loans   # quarterly\n",
        encoding="utf-8",
    )
    parsed = read(path, owner=owner)
    write(path, replace(parsed, tags=("accessions", "audit")))
    after = path.read_text(encoding="utf-8")

    assert "# the department" in after, "a surviving entry keeps its own comment"
    assert "- audit" in after and "- loans" not in after


def test_a_removed_link_takes_only_its_own_comment(tmp_path: Path, owner: KbId) -> None:
    """Deletion by index, not slice assignment.

    `existing[:] = keep` wipes `CommentedSeq.ca.items` outright — every comment in the sequence,
    not just the removed entry's — while `del` shifts what it can. Measured on trailing comments:
    `{}` versus `{0: '# first', 1: '# third'}`.

    Leading comments are a different case, and this test pins it rather than claiming it is fixed.
    """
    kb, first, second, third = mint_kb_id(), mint_doc_id(), mint_doc_id(), mint_doc_id()
    path = tmp_path / f"v.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nlinks:\n"
        f"# first\n- to: pnk://{kb}/{first}\n  rel: a\n"
        f"# second\n- to: pnk://{kb}/{second}\n  rel: b\n"
        f"# third\n- to: pnk://{kb}/{third}\n  rel: c\n",
        encoding="utf-8",
    )
    parsed = read(path, owner=owner)
    write(path, replace(parsed, links=(parsed.links[0], parsed.links[2])))
    after = path.read_text(encoding="utf-8")

    assert str(second) not in after, "the entry itself is gone"
    # **The pinned limitation, and it is broader than mapping keys.** A comment written on its own
    # line before a sequence entry is stored as the *preceding* entry's trailer, exactly as it is
    # for a mapping key — so deleting an entry leaves its leading comment attached to whatever
    # takes its place, and the last comment in the block is the one that disappears. Nothing is
    # silently *wrong* about the surviving links; the prose beside one of them is.
    assert "# first" in after, "the first entry's own comment is untouched"
    assert "# second" in after, "misattributed to the entry that took its place, not deleted"
    lines = after.splitlines()
    assert str(third) in lines[lines.index("# second") + 1]
    assert "# third" not in after, "this is the one that is silently lost"


def test_an_unchanged_links_block_is_not_rewritten(tmp_path: Path, owner: KbId) -> None:
    """The same property for `links`, and blind in the same way.

    `_links()` hands back the very `SingleQuotedScalarString` node it read, so even the merge path
    reassigns the same object and identity survives. What this pins is that a plain read-write does
    not disturb the block; the short-circuit that skips the walk is not observable here either.
    """
    kb, target = mint_kb_id(), mint_doc_id()
    path = tmp_path / f"w.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nlinks:\n- to: pnk://{kb}/{target}\n  rel: 'related'\n",
        encoding="utf-8",
    )
    parsed = read(path, owner=owner)
    assert parsed.original is not None
    before = parsed.original["links"][0]["rel"]

    write(path, parsed)
    assert parsed.original["links"][0]["rel"] is before, "an unchanged rel must not be reassigned"
    assert "rel: 'related'" in path.read_text(encoding="utf-8"), "...so its quoting survives"


def test_an_unchanged_provenance_node_survives_a_rewrite_intact(
    tmp_path: Path, owner: KbId
) -> None:
    """The property, asserted — but **not** a guard on the unchanged-key rule, which nothing can
    guard.

    Removing `_unchanged` changes no observable behaviour, and it is worth writing down why rather
    than pretending a test covers it: `_merge_mapping` and `_merge_links` mutate their nodes **in
    place**, and `deepcopy` of an immutable scalar returns the same object — so a write of an
    unchanged document is already a no-op without the short-circuit. The rule states the intent and
    saves the walk; it does not change the result, and no mutation of it can fail a test.
    """
    path = _provenanced(tmp_path, "x")
    parsed = read(path, owner=owner)
    assert parsed.original is not None
    before = parsed.original["provenance"]["extraction"]["backend"]

    write(path, parsed)
    assert parsed.original["provenance"]["extraction"]["backend"] is before
    assert "# the file's hash when this extraction ran" in path.read_text(encoding="utf-8")


def test_two_links_sharing_a_to_keep_their_own_rel_and_comment(tmp_path: Path, owner: KbId) -> None:
    """Reconciled on the **(to, rel) pair**, which is the index's own identity — its `links` primary
    key includes `rel`, and `_links()` accepts two entries pointing at one document with different
    relations.

    Keyed on `to` alone the pair collapses. Measured on the version that did: dropping an
    *unrelated* third link rewrote the first link's `rel` to the second's and deleted the second
    outright, leaving one row carrying the wrong relation under the other's comment.
    """
    kb, shared, other = mint_kb_id(), mint_doc_id(), mint_doc_id()
    path = tmp_path / f"y.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nlinks:\n"
        f"# why it is a counterpart\n- to: pnk://{kb}/{shared}\n  rel: counterpart\n"
        f"# why it supersedes\n- to: pnk://{kb}/{shared}\n  rel: supersedes\n"
        f"- to: pnk://{kb}/{other}\n  rel: related\n",
        encoding="utf-8",
    )
    parsed = read(path, owner=owner)
    assert len(parsed.links) == 3, "both relations to the same document are real links"

    write(path, replace(parsed, links=parsed.links[:2]))  # drop the unrelated third
    after = path.read_text(encoding="utf-8")
    lines = after.splitlines()

    assert after.count("rel:") == 2, "both surviving links are still there"
    assert lines[lines.index("# why it is a counterpart") + 2] == "  rel: counterpart"
    assert lines[lines.index("# why it supersedes") + 2] == "  rel: supersedes"
    assert str(other) not in after


def test_a_user_key_inside_provenance_extraction_survives_a_re_extraction(
    tmp_path: Path, owner: KbId
) -> None:
    """Deletion of missing keys is bounded to the **top level** of `provenance`.

    It is required there — `without_extraction_provenance` must actually remove `extraction`, or
    the `--force` reversal silently leaves a false paid claim behind. Recursing with it strips the
    user's own keys from *inside* `extraction`, because `with_extraction_provenance` builds a plain
    four-key replacement; CLAUDE.md says that write is additive, "never any other key".
    """
    path = tmp_path / f"z.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nprovenance:\n  extraction:\n    backend: claude-vision\n"
        "    fingerprint: fp-1\n    extracted: '20260725 18:00'\n    content_hash: abc\n"
        "    reviewed_by: me   # checked against the register\n",
        encoding="utf-8",
    )
    write(
        path,
        with_extraction_provenance(
            read(path, owner=owner),
            backend="claude-vision",
            fingerprint="fp-2",
            extracted="20260726 09:00",
            content_hash="def",
        ),
    )
    after = path.read_text(encoding="utf-8")

    assert "reviewed_by: me" in after, "a paid extraction rewrites additively, never any other key"
    assert "# checked against the register" in after
    assert "fingerprint: fp-2" in after and "fp-1" not in after


def test_a_document_trailing_comment_is_captured_by_an_appended_key(
    tmp_path: Path, owner: KbId
) -> None:
    """**A second pinned limitation.** A comment at the end of the document belongs to nothing in
    particular, and appending `provenance` after it makes it read as that block's introduction.

    Inserting at the canonical position instead would misplace a *different* comment — the one
    introducing the first unknown key — so this is a choice between two misplacements, not a bug
    with a fix. Pinned so the choice stays visible.
    """
    path = tmp_path / f"aa.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nshelf: A12\n# a note about the whole document\n", encoding="utf-8"
    )
    write(
        path,
        with_extraction_provenance(
            read(path, owner=owner),
            backend="claude-vision",
            fingerprint="fp-1",
            extracted="20260726 09:00",
            content_hash="abc",
        ),
    )
    lines = path.read_text(encoding="utf-8").splitlines()

    assert lines[lines.index("# a note about the whole document") + 1] == "provenance:"


def test_a_self_referential_anchor_is_nulled_rather_than_refused(
    tmp_path: Path, owner: KbId
) -> None:
    """**A pinned exclusion, and the one place this increment is not behaviour-equivalent.**

    `mine: &x\\n  b: *x` is a mapping containing itself. PyYAML built the cycle and `json.dumps`
    then raised `Circular reference detected` out of `pnk sync` — loud, and at the right moment.
    ruamel resolves the alias to `None` instead, so the value silently changes, the anchor and
    alias are dropped from the file, and nothing raises: `json.dumps({'b': None})` is perfectly
    valid, so the JSON check cannot see it either.

    Pathological input, and pinned rather than fixed — but recorded as a real regression from a
    crash to a silent change, which is the direction that matters.
    """
    path = tmp_path / f"bb.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\nmine: &x\n  b: *x\n", encoding="utf-8")

    parsed = read(path, owner=owner)
    assert parsed.extra["mine"] == {"b": None}, "the self-reference becomes null"

    write(path, parsed)
    after = path.read_text(encoding="utf-8")
    assert "&x" not in after and "*x" not in after, "the anchor and alias do not survive"


@pytest.mark.parametrize(
    ("field", "body"),
    [
        ("title", "title: 1e3"),
        ("title", "title: 0o17"),
        ("created", "created: 1E3"),
        ("tags", "tags:\n- 1e3"),
    ],
)
def test_a_string_field_that_yaml_1_2_resolves_as_a_number_is_refused(
    tmp_path: Path, owner: KbId, field: str, body: str
) -> None:
    """One of the increment's three breaking changes. Under YAML 1.1 these were strings; 1.2 reads
    them as numbers and the field checks refuse them."""
    path = tmp_path / f"cc.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\n{body}\n", encoding="utf-8")
    with pytest.raises(SidecarError) as caught:
        read(path, owner=owner)
    assert field in caught.value.message and "number" in caught.value.message


@pytest.mark.parametrize(
    "body",
    ["title: !whatever v", "title: !!str hello", "created: !whatever v", "tags:\n- !whatever v"],
)
def test_a_tagged_scalar_in_a_known_field_is_refused_with_a_remedy(
    tmp_path: Path, owner: KbId, body: str
) -> None:
    """And it must not say `TaggedScalar`. Three of this increment's breaking changes reach a user
    through these messages, and naming a ruamel internal class tells them nothing they can act on —
    what they need is "quote it, or drop the tag"."""
    path = tmp_path / f"dd.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\n{body}\n", encoding="utf-8")
    with pytest.raises(SidecarError) as caught:
        read(path, owner=owner)
    assert "tagged value" in caught.value.message
    assert "Scalar" not in caught.value.message and "Tagged" not in caught.value.message
    assert "Quote it" in caught.value.remedy


def test_a_rel_or_tag_that_looks_like_a_boolean_is_quoted_when_written(
    tmp_path: Path, owner: KbId
) -> None:
    """Decision 23 on every path pinakes writes a scalar, not just the minted `title`.

    Three quoting mutations survived the whole suite before this: dropping `_authored` from the
    links merge, from the links append, and from the tags append. `pnk link --rel no` is the real
    case — read back **through PyYAML**, because after this increment nothing else in the repo
    reads YAML 1.1 and nothing else would notice.
    """
    kb, target = mint_kb_id(), mint_doc_id()
    path = tmp_path / f"ee.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\ntags: []\nlinks: []\n", encoding="utf-8")

    parsed = read(path, owner=owner)
    write(
        path,
        replace(
            parsed,
            tags=("no", "accessions"),
            links=(Link(to=PnkUri(kb=kb, doc=target), rel="no"),),
        ),
    )
    reread = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert reread["tags"] == ["no", "accessions"], "a YAML 1.1 reader must not see False"
    assert reread["links"][0]["rel"] == "no"


def test_a_link_written_where_none_existed_is_quoted_too(tmp_path: Path, owner: KbId) -> None:
    """The other half: the branch taken when a key **first appears**, which is what `pnk link` will
    follow on a sidecar that has no `links:` yet — the common case, and it wrote bare. `tags` goes
    through the same branch and had the same hole."""
    kb, target = mint_kb_id(), mint_doc_id()
    path = tmp_path / f"ff.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\ntitle: A document\n", encoding="utf-8")

    parsed = read(path, owner=owner)
    write(
        path,
        replace(parsed, tags=("no",), links=(Link(to=PnkUri(kb=kb, doc=target), rel="no"),)),
    )
    reread = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert reread["links"][0]["rel"] == "no"
    assert reread["tags"] == ["no"], "the same branch writes tags, and it was bare too"


def test_a_self_link_keeps_its_place_its_comment_and_its_unknown_keys(
    tmp_path: Path, owner: KbId
) -> None:
    """`_links()` expands `self`, so a `pnk://self/…` entry never equalled anything in the wanted
    set: it was deleted and a bare replacement appended at the end. Reproduced on a **committed
    corpus sidecar**, where it silently reordered the block.

    The expansion itself is a documented exclusion. Rebuilding the entry around it is not.
    """
    other, target, sibling = mint_kb_id(), mint_doc_id(), mint_doc_id()
    path = tmp_path / f"gg.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nlinks:\n"
        f"# the sibling in this same KB\n- to: pnk://self/{sibling}\n  rel: related\n"
        "  confidence: high\n"
        f"- to: pnk://{other}/{target}\n  rel: counterpart\n",
        encoding="utf-8",
    )
    write(path, read(path, owner=owner))
    lines = path.read_text(encoding="utf-8").splitlines()

    assert (
        lines[lines.index("# the sibling in this same KB") + 1] == f"- to: pnk://{owner}/{sibling}"
    )
    assert "  confidence: high" in lines, "its unknown per-link keys survive"
    assert lines.index(f"- to: pnk://{other}/{target}") > lines.index(
        "# the sibling in this same KB"
    )


def test_two_identical_link_entries_both_survive(tmp_path: Path, owner: KbId) -> None:
    """Multiplicity, never a set. `_links()` does not deduplicate — only the index's primary key
    does — so a sidecar carrying the same `(to, rel)` twice has two links, and a `set` of pairs
    silently deletes the second: three in, one out."""
    kb, target, other = mint_kb_id(), mint_doc_id(), mint_doc_id()
    path = tmp_path / f"hh.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nlinks:\n"
        f"- to: pnk://{kb}/{target}\n  rel: related\n"
        f"- to: pnk://{kb}/{target}\n  rel: related\n"
        f"- to: pnk://{kb}/{other}\n  rel: counterpart\n",
        encoding="utf-8",
    )
    parsed = read(path, owner=owner)
    assert len(parsed.links) == 3, "the duplicate is a real link, not a parse artefact"

    # The write must **change** something, or the unchanged-key short-circuit skips the merge
    # entirely and the test cannot see how it reconciles. The first version of this test did a
    # plain read-write and a `wanted` that deduplicates survived it.
    write(path, replace(parsed, links=parsed.links[:2]))
    after = path.read_text(encoding="utf-8")

    assert after.count("rel: related") == 2, "both identical entries survive"
    assert str(other) not in after


def test_editing_a_rel_updates_the_entry_rather_than_replacing_it(
    tmp_path: Path, owner: KbId
) -> None:
    """A `rel` edit is an assignment into the existing node.

    Keying on the whole `(to, rel)` pair makes the pair the entire content of an entry, so no
    matched entry is ever updated and every edit becomes a delete plus an append — which by the
    pinned deletion limitation misattributes one comment and destroys another. This is what `pnk
    link` will do when it changes a relation, so the common case must keep the prose beside it.
    """
    kb, target = mint_kb_id(), mint_doc_id()
    path = tmp_path / f"ii.md{SIDECAR_SUFFIX}"
    path.write_text(
        f"id: {mint_doc_id()}\nlinks:\n# why these two are connected\n"
        f"- to: pnk://{kb}/{target}\n  rel: related\n  confidence: high\n",
        encoding="utf-8",
    )
    parsed = read(path, owner=owner)
    write(path, replace(parsed, links=(Link(to=parsed.links[0].to, rel="supersedes"),)))
    lines = path.read_text(encoding="utf-8").splitlines()

    assert lines[lines.index("# why these two are connected") + 1] == f"- to: pnk://{kb}/{target}"
    assert "  rel: supersedes" in lines, "the relation changed"
    assert "  confidence: high" in lines, "and the entry's own keys are still there"


def test_a_reused_anchor_name_is_refused_rather_than_silently_resolved(
    tmp_path: Path, owner: KbId
) -> None:
    """It was a clean `SidecarError` before the swap and is a silent value change after.

    PyYAML raises `ComposerError`, a `YAMLError`. ruamel accepts the document, resolves every alias
    to the **last** anchor of that name — `a: &dup 1`, `b: &dup 2`, `c: *dup` makes `c` equal 2 —
    and reports it only as a `ReusedAnchorWarning` on stderr. That is not a `YAMLError`, so
    `read()`'s handlers never saw it; and under this project's `filterwarnings = ["error"]` it
    escaped as a bare warning traceback instead of a named error.

    Promoted explicitly at the load, so the outcome does not depend on the caller's filters.
    """
    path = tmp_path / f"kk.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\na: &dup 1\nb: &dup 2\nc: *dup\n", encoding="utf-8")

    with pytest.raises(SidecarError) as caught:
        read(path, owner=owner)
    assert "anchor" in caught.value.message
    assert caught.value.remedy


def test_a_reused_anchor_is_refused_whatever_the_ambient_warning_filter_says(
    tmp_path: Path, owner: KbId
) -> None:
    """`ignore` must not turn the refusal back into silent acceptance — the filter belongs to
    whoever imported pinakes, and this is a property of the sidecar format, not of their config."""
    import warnings as warnings_module

    path = tmp_path / f"ll.md{SIDECAR_SUFFIX}"
    path.write_text(f"id: {mint_doc_id()}\na: &dup 1\nb: &dup 2\n", encoding="utf-8")

    with warnings_module.catch_warnings():
        warnings_module.simplefilter("ignore")
        with pytest.raises(SidecarError):
            read(path, owner=owner)


# --- The documented exclusions, pinned ----------------------------------------------------------
#
# Every bound on the byte-identity invariant was prose until this block. A claim in a docs table is
# not a test: it cannot notice when the library's behaviour moves, and it cannot be wrong out loud.
# Two of these were measured *while writing them* and were missing from the list entirely.


def _round_trip(path: Path, owner: KbId, raw: bytes) -> bytes:
    path.write_bytes(raw)
    write(path, read(path, owner=owner))
    return path.read_bytes()


def test_an_explicit_double_bang_tag_is_stripped(tmp_path: Path, owner: KbId) -> None:
    """`!!int 3` becomes `3` and `!!seq [a]` becomes `[a]`. The value is unchanged and the *tag* is
    not preserved — so "these tags keep working" is true of loading and false of byte-identity, and
    the changelog said the former while the invariant promises the latter."""
    after = _round_trip(
        tmp_path / f"mm.md{SIDECAR_SUFFIX}",
        owner,
        f"id: {mint_doc_id()}\ni: !!int 3\ns: !!seq [a]\n".encode(),
    )
    assert b"!!int" not in after and b"!!seq" not in after
    assert b"i: 3" in after and b"s: [a]" in after


def test_an_anchor_on_an_empty_value_is_destroyed(tmp_path: Path, owner: KbId) -> None:
    """**Not in any exclusion list until this test.** The list named the *self-referential* case;
    this anchor is ordinary, it simply has nothing after it, and `&x` does not survive. An anchor on
    a non-empty value does — asserted below, so the two cases stay distinguishable."""
    after = _round_trip(
        tmp_path / f"nn.md{SIDECAR_SUFFIX}",
        owner,
        f"id: {mint_doc_id()}\nmine: &x\nother: 1\n".encode(),
    )
    assert b"&x" not in after
    assert b"mine:" in after and b"other: 1" in after


def test_an_anchor_on_a_real_value_survives(tmp_path: Path, owner: KbId) -> None:
    """The counterpart, so the exclusion above stays narrow. An ordinary anchor and its alias
    round-trip byte-identically — this is not a general "anchors are lost" caveat."""
    raw = f"id: {mint_doc_id()}\na: &x 1\nb: *x\n".encode()
    assert _round_trip(tmp_path / f"oo.md{SIDECAR_SUFFIX}", owner, raw) == raw


@pytest.mark.parametrize(
    ("name", "raw", "gone"),
    [
        ("crlf", b"id: %s\r\nk: v\r\n", b"\r\n"),
        ("bom", "﻿id: %s\nk: v\n".encode(), b"\xef\xbb\xbf"),
        ("markers", b"---\nid: %s\nk: v\n...\n", b"---"),
    ],
)
def test_what_yaml_does_not_carry_is_not_carried(
    tmp_path: Path, owner: KbId, name: str, raw: bytes, gone: bytes
) -> None:
    """CRLF, a byte-order mark and `---`/`...` markers are all lost. They are documented as lost;
    documented is not the same as tested, and a library that started preserving one of them would
    change the file without anything noticing."""
    path = tmp_path / f"{name}.md{SIDECAR_SUFFIX}"
    body = raw.replace(b"%s", str(mint_doc_id()).encode())
    after = _round_trip(path, owner, body)

    assert gone not in after
    assert b"k: v" in after, "the content survives; only the framing does not"

    if name == "crlf":
        # **Bytes, never text.** `Path.read_text` normalises line endings on the way in, so a
        # text-level comparison here compares normalised against normalised and reports
        # "identical" for a file whose bytes plainly changed. A probe that cannot observe the
        # property it tests still reads as evidence — the same failure mode as a fixture that
        # passes on broken code. Recorded here so nobody simplifies `_round_trip` to `read_text`.
        assert path.read_text(encoding="utf-8") == body.decode().replace("\r\n", "\n")


def test_a_missing_trailing_newline_is_added(tmp_path: Path, owner: KbId) -> None:
    """**Also missing from the exclusion list.** A sidecar whose last line has no newline gains
    one. Harmless, and a byte difference on a file nobody edited — which is exactly what the
    invariant claims does not happen, so it belongs in the list rather than in a surprise."""
    after = _round_trip(
        tmp_path / f"pp.md{SIDECAR_SUFFIX}", owner, f"id: {mint_doc_id()}\nk: v".encode()
    )
    assert after.endswith(b"k: v\n")
