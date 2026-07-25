"""§6.4, row by row. This is the logic that silently corrupts a KB when it is wrong."""

import pytest

from pinakes.errors import DuplicateIdsError
from pinakes.ids import DocId, mint_doc_id
from pinakes.pairing import (
    ACTIVE,
    DELETED,
    Adopt,
    IndexedDocument,
    IndexSnapshot,
    Mint,
    Reembed,
    RefreshMetadata,
    Rename,
    Skip,
    SoftDelete,
    WalkedFile,
    WalkedSidecar,
    WalkSnapshot,
    actions_of,
    describe,
    pair,
)


def indexed(
    doc_id: DocId,
    path: str,
    content_hash: str = "h1",
    sidecar_hash: str | None = None,
    state: str = ACTIVE,
) -> IndexedDocument:
    return IndexedDocument(
        id=doc_id, path=path, content_hash=content_hash, sidecar_hash=sidecar_hash, state=state
    )


def walked(path: str, content_hash: str = "h1") -> WalkedFile:
    return WalkedFile(path=path, content_hash=content_hash)


def sidecar(document_path: str, doc_id: DocId, file_hash: str = "s1") -> WalkedSidecar:
    return WalkedSidecar(
        path=f"{document_path}.pnk.yaml",
        document_path=document_path,
        id=doc_id,
        file_hash=file_hash,
    )


# --- Row: path and content unchanged --------------------------------------------------------


def test_unchanged_document_is_skipped() -> None:
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/a.md", "h1", "s1"),)),
        WalkSnapshot((walked("docs/a.md", "h1"),), (sidecar("docs/a.md", doc, "s1"),)),
    )
    assert describe(result) == {"Skip": 1}
    assert actions_of(result, Skip)[0].doc_id == doc


# --- Row: sidecar-only edit (design pass 7) -------------------------------------------------


def test_a_sidecar_only_edit_refreshes_metadata_without_re_embedding() -> None:
    """Tags changed, document untouched: re-embedding would be waste, skipping would be a freeze."""
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/a.md", "h1", "s1"),)),
        WalkSnapshot((walked("docs/a.md", "h1"),), (sidecar("docs/a.md", doc, "s2"),)),
    )
    assert describe(result) == {"RefreshMetadata": 1}
    assert actions_of(result, RefreshMetadata)[0].sidecar_hash == "s2"


# --- Row: path unchanged, content changed ---------------------------------------------------


def test_edited_document_is_re_embedded_and_keeps_its_id() -> None:
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/a.md", "h1"),)),
        WalkSnapshot((walked("docs/a.md", "h2"),), (sidecar("docs/a.md", doc),)),
    )
    assert describe(result) == {"Reembed": 1}
    action = actions_of(result, Reembed)[0]
    assert action.doc_id == doc
    assert action.content_hash == "h2"


# --- Row: rename (one new path, same content) -----------------------------------------------


def test_a_rename_keeps_the_id() -> None:
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/old.md", "h1"),)),
        WalkSnapshot((walked("docs/new.md", "h1"),), (sidecar("docs/new.md", doc),)),
    )
    assert describe(result) == {"Adopt": 1}
    assert actions_of(result, Adopt)[0].doc_id == doc
    assert actions_of(result, Adopt)[0].old_path == "docs/old.md"


def test_a_rename_without_a_sidecar_is_detected_by_content() -> None:
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/old.md", "h1"),)),
        WalkSnapshot((walked("docs/new.md", "h1"),), ()),
    )
    assert describe(result) == {"Rename": 1}
    renamed = actions_of(result, Rename)[0]
    assert (renamed.doc_id, renamed.old_path, renamed.path) == (doc, "docs/old.md", "docs/new.md")


# --- Row: duplicate content, ambiguous --------------------------------------------------------


def test_duplicate_content_is_reported_rather_than_guessed() -> None:
    """Attaching the id to the wrong duplicate would silently redirect every inbound link."""
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/old.md", "h1"),)),
        WalkSnapshot((walked("docs/one.md", "h1"), walked("docs/two.md", "h1")), ()),
    )
    assert len(result.ambiguities) == 1
    assert result.ambiguities[0].candidates == ("docs/one.md", "docs/two.md")
    assert describe(result) == {"SoftDelete": 1, "Mint": 2}


def test_a_sidecar_breaks_the_duplicate_tie() -> None:
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/old.md", "h1"),)),
        WalkSnapshot(
            (walked("docs/one.md", "h1"), walked("docs/two.md", "h1")),
            (sidecar("docs/two.md", doc),),
        ),
    )
    assert result.ambiguities == ()
    assert actions_of(result, Adopt)[0].path == "docs/two.md"
    assert actions_of(result, Mint)[0].path == "docs/one.md"


# --- Row: new file -----------------------------------------------------------------------------


def test_a_new_file_without_a_sidecar_is_minted() -> None:
    result = pair(IndexSnapshot(), WalkSnapshot((walked("docs/new.md", "h9"),), ()))
    assert describe(result) == {"Mint": 1}
    assert actions_of(result, Mint)[0].path == "docs/new.md"


def test_a_new_file_with_a_sidecar_adopts_its_id() -> None:
    """A KB cloned from a colleague arrives with sidecars and no index; the ids must survive."""
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot(), WalkSnapshot((walked("docs/a.md", "h1"),), (sidecar("docs/a.md", doc),))
    )
    assert describe(result) == {"Adopt": 1}
    adopted = actions_of(result, Adopt)[0]
    assert adopted.doc_id == doc
    assert adopted.old_path is None


# --- Row: deletion -----------------------------------------------------------------------------


def test_a_vanished_document_is_soft_deleted() -> None:
    doc = mint_doc_id()
    result = pair(IndexSnapshot((indexed(doc, "docs/gone.md", "h1"),)), WalkSnapshot())
    assert describe(result) == {"SoftDelete": 1}
    assert actions_of(result, SoftDelete)[0].doc_id == doc


def test_an_already_deleted_document_is_left_alone() -> None:
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/gone.md", "h1", state=DELETED),)), WalkSnapshot()
    )
    assert describe(result) == {}


def test_a_returning_file_revives_its_row() -> None:
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/a.md", "h1", state=DELETED),)),
        WalkSnapshot((walked("docs/a.md", "h1"),), ()),
    )
    assert describe(result) == {"Reembed": 1}


# --- Row: duplicate ids (fatal) ----------------------------------------------------------------


def test_one_id_in_two_sidecars_is_fatal_and_names_both() -> None:
    doc = mint_doc_id()
    with pytest.raises(DuplicateIdsError) as exc_info:
        pair(
            IndexSnapshot(),
            WalkSnapshot(
                (walked("docs/a.md"), walked("docs/b.md")),
                (sidecar("docs/a.md", doc), sidecar("docs/b.md", doc)),
            ),
        )
    assert "docs/a.md.pnk.yaml" in exc_info.value.message
    assert "docs/b.md.pnk.yaml" in exc_info.value.message
    assert "Never edit the id" in exc_info.value.remedy


# --- Compound cases ----------------------------------------------------------------------------


def test_rename_plus_edit_keeps_the_id_and_emits_no_delete() -> None:
    """The hash tie is gone, but the sidecar travelled — inbound links must survive (§6.4)."""
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/old.md", "h1"),)),
        WalkSnapshot((walked("docs/new.md", "h2"),), (sidecar("docs/new.md", doc),)),
    )
    assert describe(result) == {"Adopt": 1}
    assert not actions_of(result, SoftDelete)
    assert actions_of(result, Adopt)[0].old_path == "docs/old.md"


def test_rename_plus_edit_without_the_sidecar_is_reported_as_such() -> None:
    """§9's most likely real-world corruption, surfaced at the moment it happens."""
    doc = mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(doc, "docs/old.md", "h1"),)),
        WalkSnapshot((walked("docs/new.md", "h2"),), ()),
    )
    assert describe(result) == {"SoftDelete": 1, "Mint": 1}
    assert result.moved_without_sidecar == ("docs/old.md",)


def test_a_sidecar_whose_document_is_gone_is_reported_as_orphaned() -> None:
    doc = mint_doc_id()
    result = pair(IndexSnapshot(), WalkSnapshot((), (sidecar("docs/gone.md", doc),)))
    assert result.orphaned_sidecars == ("docs/gone.md.pnk.yaml",)


def test_a_sidecar_disagreeing_with_the_index_wins() -> None:
    """`docs/` is the truth; the index is derived. The stale row is retired, not silently kept."""
    old, new = mint_doc_id(), mint_doc_id()
    result = pair(
        IndexSnapshot((indexed(old, "docs/a.md", "h1"),)),
        WalkSnapshot((walked("docs/a.md", "h1"),), (sidecar("docs/a.md", new),)),
    )
    assert describe(result) == {"SoftDelete": 1, "Adopt": 1}
    assert actions_of(result, SoftDelete)[0].doc_id == old
    assert actions_of(result, Adopt)[0].doc_id == new


def test_a_whole_mixed_sync() -> None:
    kept, edited, renamed, gone = (mint_doc_id() for _ in range(4))
    result = pair(
        IndexSnapshot(
            (
                indexed(kept, "docs/kept.md", "h1", "s1"),
                indexed(edited, "docs/edited.md", "h2"),
                indexed(renamed, "docs/old.md", "h3"),
                indexed(gone, "docs/gone.md", "h4"),
            )
        ),
        WalkSnapshot(
            (
                walked("docs/kept.md", "h1"),
                walked("docs/edited.md", "h2-changed"),
                walked("docs/new.md", "h3"),
                walked("docs/brand-new.md", "h5"),
            ),
            (sidecar("docs/kept.md", kept, "s1"),),
        ),
    )
    assert describe(result) == {"Skip": 1, "Reembed": 1, "Rename": 1, "SoftDelete": 1, "Mint": 1}


def test_pairing_is_pure_and_order_independent() -> None:
    """Same picture, different walk order, same decisions — pairing is set-wise (§6.4)."""
    first, second = mint_doc_id(), mint_doc_id()
    before = IndexSnapshot((indexed(first, "docs/a.md", "h1"), indexed(second, "docs/b.md", "h2")))
    forward = WalkSnapshot((walked("docs/a.md", "h1"), walked("docs/b.md", "h2-new")), ())
    backward = WalkSnapshot((walked("docs/b.md", "h2-new"), walked("docs/a.md", "h1")), ())
    assert describe(pair(before, forward)) == describe(pair(before, backward))
