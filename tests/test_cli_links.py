"""`pnk links` and the SQLite provider, against two real KBs on disk.

Reuses `test_sync_links`'s two-KB builder, because the properties that matter here — a cross-KB
neighbour is terminal, carries a ULID, and has no title — do not exist in a single-KB fixture at
all.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from test_sync_links import Kb, make_kb, run

from pinakes import store
from pinakes.graph.provider import DocumentProvider, document_key, edges_of, resolve_document
from pinakes.graph.traverse import MAX_DEPTH, traverse
from pinakes.ids import mint_doc_id


@pytest.fixture
def linked(tmp_path: Path) -> tuple[Kb, Kb]:
    """A local KB with an internal link and a partner that links into it, synced."""
    local = make_kb(tmp_path / "local", "local", ["alpha", "beta", "gamma"])
    partner = make_kb(tmp_path / "partner", "partner", ["one"])
    local.connect(partner, "partner")
    partner.connect(local, "local")
    local.set_links("alpha", [(local.uri("beta"), "related")])
    partner.set_links("one", [(local.uri("alpha"), "counterpart")])
    run(local)
    return local, partner


def links_of(kb: Kb, document: str, **options: object) -> dict[str, Any]:
    """`pnk links --json` for one document, as a parsed payload.

    `Any`, not `object`: this is decoded JSON whose shape the tests below assert directly, and
    typing it as `object` only means every one of those assertions needs a suppression saying "yes,
    it really is a list" — which is noise standing where a real type error would show.
    """
    import contextlib
    import io

    from pinakes.cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(
            [
                "links",
                document,
                "--kb",
                str(kb.root),
                "--json",
                *[
                    part
                    for name, value in options.items()
                    for part in (f"--{name.replace('_', '-')}", str(value))
                ],
            ]
        )
    assert code == 0, buffer.getvalue()
    return json.loads(buffer.getvalue())


# --- The neighbour contract ---------------------------------------------------------------


def test_every_neighbour_is_a_document(linked: tuple[Kb, Kb]) -> None:
    """Tag, directory and heading nodes have no `doc_id` and never reach this surface — which is
    what lets a later release add a whole structural graph without touching this contract."""
    local, _partner = linked
    payload = links_of(local, "docs/alpha.md", depth=MAX_DEPTH)

    neighbours: list[dict[str, Any]] = payload["neighbours"]
    assert neighbours
    for row in neighbours:
        assert set(row) <= {
            "kb_id",
            "doc_id",
            "rel",
            "direction",
            "distance",
            "score",
            "scored_by_query",
            "terminal",
            "title",
        }
        assert row["doc_id"], "a node with no doc_id reached the traversal surface"


def test_a_cross_kb_neighbour_is_marked_terminal(linked: tuple[Kb, Kb]) -> None:
    local, partner = linked
    payload = links_of(local, "docs/alpha.md", depth=MAX_DEPTH)
    rows = {row["doc_id"]: row for row in payload["neighbours"]}

    foreign = rows[str(partner.docs["one"])]
    assert foreign["terminal"] is True
    assert rows[str(local.docs["beta"])]["terminal"] is False


def test_a_cross_kb_neighbour_carries_its_kb_ulid_and_no_title(linked: tuple[Kb, Kb]) -> None:
    """No title, and not guessed at: this index holds the partner's *links*, never its documents,
    so any title it offered would be invented from an id."""
    local, partner = linked
    rows = {
        row["doc_id"]: row
        for row in links_of(local, "docs/alpha.md", depth=MAX_DEPTH)["neighbours"]
    }

    foreign = rows[str(partner.docs["one"])]
    assert foreign["kb_id"] == str(partner.kb_id)
    assert "title" not in foreign


def test_a_same_kb_neighbour_carries_its_title(linked: tuple[Kb, Kb]) -> None:
    local, _partner = linked
    rows = {row["doc_id"]: row for row in links_of(local, "docs/alpha.md")["neighbours"]}
    assert rows[str(local.docs["beta"])]["title"] == "beta"


def test_kb_id_is_a_ulid_not_a_name(linked: tuple[Kb, Kb]) -> None:
    """Three namespaces exist and only one is portable. `[kb] name` is documented as free to
    rename and `[[links.kb]] name` is machine-local; a payload carrying either would break the
    moment it crossed a machine."""
    local, partner = linked
    payload = links_of(local, "docs/alpha.md", depth=MAX_DEPTH)

    ids = {row["kb_id"] for row in payload["neighbours"]}
    assert ids <= {str(local.kb_id), str(partner.kb_id)}
    assert "partner" not in ids and "local" not in ids


def test_json_output_shape_is_pinned(linked: tuple[Kb, Kb]) -> None:
    """An agent parses this. Adding a key is a feature; renaming or dropping one is a break."""
    local, _partner = linked
    payload = links_of(local, "docs/alpha.md")

    assert set(payload) == {"document", "neighbours", "frontier", "unresolved", "truncated"}
    row = payload["neighbours"][0]
    assert {
        "kb_id",
        "doc_id",
        "rel",
        "direction",
        "distance",
        "score",
        "scored_by_query",
        "terminal",
    } <= set(row)
    assert {"kb_id", "doc_id", "rel", "reason", "distance"} == set(payload["frontier"][0])


# --- Bounds ---------------------------------------------------------------------------------


def test_depth_beyond_the_cap_is_served_at_the_cap(linked: tuple[Kb, Kb]) -> None:
    local, _partner = linked
    payload = links_of(local, "docs/alpha.md", depth=99)

    assert max(row["distance"] for row in payload["neighbours"]) <= MAX_DEPTH


def test_direction_selects_which_half_is_returned(linked: tuple[Kb, Kb]) -> None:
    local, partner = linked

    outward = links_of(local, "docs/alpha.md", direction="out")
    inward = links_of(local, "docs/alpha.md", direction="in")

    assert {row["doc_id"] for row in outward["neighbours"]} == {str(local.docs["beta"])}
    assert {row["doc_id"] for row in inward["neighbours"]} == {str(partner.docs["one"])}


def test_rel_filters_to_one_relation(linked: tuple[Kb, Kb]) -> None:
    local, _partner = linked
    payload = links_of(local, "docs/alpha.md", rel="related")

    assert {row["rel"] for row in payload["neighbours"]} == {"related"}


def test_a_document_with_no_links_is_empty_not_an_error(linked: tuple[Kb, Kb]) -> None:
    local, _partner = linked
    payload = links_of(local, "docs/gamma.md")
    assert payload["neighbours"] == []


def test_a_document_can_be_named_by_ulid_or_by_path(linked: tuple[Kb, Kb]) -> None:
    """`pnk search` prints paths; requiring a ULID would mean copying one out of `--json` to ask
    about a result already on screen."""
    local, _partner = linked
    by_path = links_of(local, "docs/alpha.md")
    by_ulid = links_of(local, str(local.docs["alpha"]))
    assert by_path == by_ulid


def test_an_unknown_document_is_refused_with_a_remedy(linked: tuple[Kb, Kb]) -> None:
    from pinakes.cli import main

    local, _partner = linked
    assert main(["links", "docs/nope.md", "--kb", str(local.root)]) != 0


# --- The provider ----------------------------------------------------------------------------


def test_one_query_per_hop_not_a_recursive_cte(linked: tuple[Kb, Kb]) -> None:
    """A recursive CTE would have to re-implement depth, fan-out and dedup in SQL to honour the
    caps that already live in the core — three rules in two places, which is how they drift.

    Counted at the sqlite3 layer with a trace callback, not by trusting the provider's own tally:
    the provider could count one thing and issue another.
    """
    local, _partner = linked
    statements: list[str] = []
    connection = sqlite3.connect(local.root / ".pinakes" / "index.db")
    connection.row_factory = sqlite3.Row
    connection.set_trace_callback(statements.append)
    try:
        provider = DocumentProvider(connection, local_kb=local.kb_id)
        statements.clear()  # the constructor's title lookup is not part of the walk
        traverse(provider, document_key(str(local.kb_id), str(local.docs["alpha"])), depth=3)
    finally:
        connection.close()

    assert not any("WITH RECURSIVE" in statement.upper() for statement in statements)
    # Two per expansion — outbound and inbound are separate statements by design — plus the
    # `unresolved` probe's own pair. What matters is that it is a function of hops, not of the
    # graph's size.
    assert len(statements) <= 4 * MAX_DEPTH + 4, statements


def test_the_provider_never_offers_a_node_without_a_doc_id(linked: tuple[Kb, Kb]) -> None:
    local, _partner = linked
    connection = store.connect_ro(local.root / ".pinakes" / "index.db")
    try:
        provider = DocumentProvider(connection, local_kb=local.kb_id)
        candidates = provider.neighbours(
            document_key(str(local.kb_id), str(local.docs["alpha"])), query=None
        )
    finally:
        connection.close()

    assert candidates
    for candidate in candidates:
        assert len(candidate.node_key) == 2 and all(candidate.node_key)


def test_a_local_link_to_a_missing_document_is_unresolved_not_dropped(
    linked: tuple[Kb, Kb],
) -> None:
    local, _partner = linked
    ghost = mint_doc_id()
    local.set_links(
        "alpha", [(local.uri("beta"), "related"), (f"pnk://{local.kb_id}/{ghost}", "related")]
    )
    run(local, now="20260730 14:00", scan_links=True)

    payload = links_of(local, "docs/alpha.md")

    assert [entry["doc_id"] for entry in payload["unresolved"]] == [str(ghost)]
    # Disjoint, deliberately: it appeared in *both* lists before this was fixed, leaving a caller
    # to guess which one was lying about the same id.
    assert str(ghost) not in {row["doc_id"] for row in payload["neighbours"]}


def test_a_cross_kb_target_is_never_called_unresolved(linked: tuple[Kb, Kb]) -> None:
    """This index cannot know whether a partner's document exists — asserting it does not would be
    claiming something it has no standing to know."""
    local, _partner = linked
    connection = store.connect_ro(local.root / ".pinakes" / "index.db")
    try:
        provider = DocumentProvider(connection, local_kb=local.kb_id)
        missing = provider.unresolved(document_key(str(local.kb_id), str(local.docs["alpha"])))
    finally:
        connection.close()

    assert missing == []


def test_resolve_document_ignores_a_soft_deleted_document(linked: tuple[Kb, Kb]) -> None:
    local, _partner = linked
    connection = store.connect_rw(local.root / ".pinakes" / "index.db")
    try:
        connection.execute(
            "UPDATE documents SET state = 'deleted' WHERE id = ?", (str(local.docs["gamma"]),)
        )
        connection.commit()
        assert resolve_document(connection, "docs/gamma.md") is None
    finally:
        connection.close()


def test_edges_of_projects_the_direction_it_came_from(linked: tuple[Kb, Kb]) -> None:
    local, _partner = linked
    connection = store.connect_ro(local.root / ".pinakes" / "index.db")
    try:
        found = edges_of(connection, document_key(str(local.kb_id), str(local.docs["alpha"])))
    finally:
        connection.close()

    by_direction = {edge.direction for edge in found}
    assert by_direction == {"out", "in"}


def test_depth_is_honoured_not_merely_capped(linked: tuple[Kb, Kb]) -> None:
    """`--depth 2` must actually reach hop 2.

    Asserting only that distances stay under the cap is satisfied by a CLI that ignores the flag
    entirely and always walks one hop — verified by mutation, where exactly that change passed
    every other test here.
    """
    local, _partner = linked
    local.set_links("beta", [(local.uri("gamma"), "related")])
    run(local, now="20260730 15:00", scan_links=True)

    one = links_of(local, "docs/alpha.md", depth=1)
    two = links_of(local, "docs/alpha.md", depth=2)

    assert {row["distance"] for row in one["neighbours"]} == {1}
    assert 2 in {row["distance"] for row in two["neighbours"]}
    assert str(local.docs["gamma"]) in {row["doc_id"] for row in two["neighbours"]}
    assert str(local.docs["gamma"]) not in {row["doc_id"] for row in one["neighbours"]}


def human_output(kb: Kb, document: str, **options: object) -> str:
    """`pnk links` as a person reads it — stdout only, no `--json`."""
    import contextlib
    import io

    from pinakes.cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(
            [
                "links",
                document,
                "--kb",
                str(kb.root),
                *[
                    part
                    for name, value in options.items()
                    for part in (f"--{name.replace('_', '-')}", str(value))
                ],
            ]
        )
    assert code == 0, buffer.getvalue()
    return buffer.getvalue()


def test_the_human_output_names_each_direction_with_its_own_arrow(tmp_path: Path) -> None:
    """`->` written here, `<-` pointing here, `<->` the same relation written from both ends.

    `run_links`' human output had no assertion at all until this: mutating the arrow's fallback to
    `<-` survived the whole suite, and so did deleting the `no links` line, which would leave an
    unlinked document printing nothing and exiting 0.
    """
    kb = make_kb(tmp_path / "arrows", "arrows", ["alpha", "beta", "gamma", "orphan"])
    kb.set_links("alpha", [(kb.uri("beta"), "related"), (kb.uri("gamma"), "mutual")])
    kb.set_links("gamma", [(kb.uri("alpha"), "mutual")])
    kb.set_links("beta", [(kb.uri("alpha"), "cites")])
    run(kb)

    # Matched against whole lines, never as substrings: `-> related: beta` is *inside*
    # `<-> related: beta`, so dropping the `out` mapping rendered every outbound link as
    # reciprocal and this test still passed.
    lines = {line.split("  [hop")[0] for line in human_output(kb, "docs/alpha.md").splitlines()}
    assert "-> related: beta" in lines, "written here"
    assert "<- cites: beta" in lines, "pointing here"
    assert "<-> mutual: gamma" in lines, "the same relation from both ends"

    assert "no links" in human_output(kb, "docs/orphan.md"), "silence would read as success"


def test_the_cli_says_so_when_every_link_dangles(tmp_path: Path) -> None:
    """stdout said `no links` for a document whose links exist and resolve to nothing, while
    stderr listed them. A user piping stdout reads only the contradiction."""
    kb = make_kb(tmp_path / "cli", "cli", ["alpha", "stale"])
    absent = f"pnk://{kb.kb_id}/{mint_doc_id()}"  # minted, never hand-written
    kb.set_links("stale", [(absent, "related")])
    run(kb)

    dangling = human_output(kb, "docs/stale.md")
    assert "no links" not in dangling, "its links exist — they resolve to nothing"
    assert "resolve to nothing" in dangling

    # ...but not when the caller's own filter is what emptied it. `alpha` has a live link; asking
    # for a relation it does not carry must not report that its links resolve to nothing.
    kb.set_links("alpha", [(kb.uri("stale"), "related")])
    run(kb)
    filtered = human_output(kb, "docs/alpha.md", rel="nosuchrel")
    assert "resolve to nothing" not in filtered, "one dropped argument away from a live neighbour"
    assert "no links match these arguments" in filtered
