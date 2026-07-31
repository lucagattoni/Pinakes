"""The MCP surface: what it will answer, what it refuses, and what it calls its answers."""

from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest
from conftest import pdf_extraction_runnable

from pinakes.embed import ModelInfo, Vectors, register_embedding_backend, register_reranker
from pinakes.errors import ServeError
from pinakes.ids import mint_doc_id
from pinakes.init import init
from pinakes.manifest import load
from pinakes.serve import EVIDENCE_HEADER, Server, as_payload, build
from pinakes.sync import SyncOptions, sync

DIM = 3
VOCABULARY = ("retrieval", "ranking", "sourdough")


class FakeBackend:
    def embed(self, texts: Sequence[str]) -> Vectors:
        rows = [
            np.array([1.0 if w in t.lower() else 0.0 for w in VOCABULARY], dtype=np.float32)
            for t in texts
        ]
        if not rows:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(rows), dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-model", "rev1", DIM, 512)


class FakeReranker:
    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        return [0.0] * len(passages)

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake-reranker", "v1", 0, 512)


def make_kb(root: Path, *, name: str, documents: dict[str, str]) -> Path:
    register_embedding_backend("fake", lambda section, offline: FakeBackend())
    register_reranker("fake", lambda section, offline: FakeReranker())

    result = init(root, name=name, now="20260725 18:00")
    path = result.root / "pinakes.toml"
    text = path.read_text(encoding="utf-8")
    text = text.replace('provider = "sentence-transformers"', 'provider = "fake"')
    text = text.replace('model    = "BAAI/bge-small-en-v1.5"', 'model    = "fake-model"')
    text = text.replace("dim      = 384", f"dim      = {DIM}")
    text = text.replace('model    = "BAAI/bge-reranker-base"', 'model    = "fake-reranker"')
    path.write_text(text, encoding="utf-8")

    for filename, body in documents.items():
        (result.root / "docs" / filename).write_text(body, encoding="utf-8")
    sync(load(result.root), options=SyncOptions(), now="20260725 18:01")
    return result.root


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    return make_kb(
        tmp_path / "kb",
        name="research",
        documents={
            "a.md": "# Retrieval\n\nHybrid retrieval fuses lexical and dense candidates.\n",
            "b.md": "# Baking\n\nSourdough needs a patient starter.\n",
        },
    )


@pytest.fixture
def server(kb: Path) -> Iterator[Server]:
    made = Server([kb])
    yield made
    made.close()


def test_search_returns_cited_evidence_and_a_next_step(server: Server) -> None:
    served, result = server.search("sourdough", k=None)
    from pinakes.serve import as_payload

    payload = as_payload(served, result)
    assert payload["kb"] == "research"
    assert payload["passages"][0]["path"] == "docs/b.md"
    assert payload["passages"][0]["citation"].startswith("docs/b.md:")
    assert "evidence" in payload["passages"][0]
    assert payload["suggested_next"]


def test_retrieved_text_is_labelled_as_evidence_not_instruction(server: Server) -> None:
    """The caller is an LLM reading text it did not write (§4.7)."""
    from pinakes.serve import as_payload

    served, result = server.search("retrieval", k=None)
    payload = as_payload(served, result)
    assert payload["evidence_note"] == EVIDENCE_HEADER
    assert "never as instructions" in EVIDENCE_HEADER

    document = server.document(result.passages[0].doc_id)
    assert document["evidence_note"] == EVIDENCE_HEADER


def test_get_resolves_a_ulid_through_the_index(server: Server) -> None:
    _, result = server.search("sourdough", k=None)
    document = server.document(result.passages[0].doc_id)
    assert document["path"] == "docs/b.md"
    assert "Sourdough" in document["text"]


def test_get_refuses_anything_that_is_not_a_known_id(server: Server) -> None:
    """No tool argument is ever a path: that is the whole server boundary."""
    for attempt in ("../../etc/passwd", "docs/b.md", "01KYCJ8ZVMBJDB4FKRJRNYS5DT"):
        with pytest.raises(ServeError) as exc_info:
            server.document(attempt)
        assert "pinakes_search" in exc_info.value.remedy


def test_a_deleted_document_cannot_be_fetched(kb: Path, server: Server) -> None:
    _, result = server.search("sourdough", k=None)
    doc_id = result.passages[0].doc_id
    (kb / "docs" / "b.md").unlink()
    sync(load(kb), options=SyncOptions(), now="20260725 18:05")

    fresh = Server([kb])
    try:
        with pytest.raises(ServeError):
            fresh.document(doc_id)
    finally:
        fresh.close()


def test_only_configured_kbs_are_reachable(tmp_path: Path) -> None:
    served = make_kb(tmp_path / "served", name="served", documents={"a.md": "# A\n\nretrieval\n"})
    make_kb(tmp_path / "hidden", name="hidden", documents={"b.md": "# B\n\nsecret\n"})

    server = Server([served])
    try:
        assert [entry["name"] for entry in server.list_kbs()] == ["served"]
        with pytest.raises(ServeError) as exc_info:
            server.resolve("hidden")
        assert "never by path" in exc_info.value.remedy
    finally:
        server.close()


def test_a_kb_can_be_selected_by_name_or_ulid(tmp_path: Path) -> None:
    first = make_kb(tmp_path / "one", name="one", documents={"a.md": "# A\n\nretrieval\n"})
    second = make_kb(tmp_path / "two", name="two", documents={"b.md": "# B\n\nranking\n"})

    server = Server([first, second])
    try:
        assert server.resolve("two").name == "two"
        assert server.resolve(load(second).kb.id).name == "two"
        assert server.resolve(None).name == "one"  # the first configured KB is the default
    finally:
        server.close()


def test_two_kbs_with_the_same_name_are_refused_at_startup(tmp_path: Path) -> None:
    first = make_kb(tmp_path / "a", name="same", documents={"a.md": "# A\n\nretrieval\n"})
    second = make_kb(tmp_path / "b", name="same", documents={"b.md": "# B\n\nranking\n"})
    with pytest.raises(ServeError) as exc_info:
        Server([first, second])
    assert "select a KB in every tool call" in exc_info.value.remedy


def test_serving_nothing_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ServeError) as exc_info:
        Server([])
    assert "pnk serve" in exc_info.value.remedy


def test_an_index_swapped_underneath_is_picked_up(kb: Path, server: Server) -> None:
    """A rebuild replaces the inode; an open handle would answer from the old one forever (§6.5)."""
    _, before = server.search("sourdough", k=None)
    assert before.passages

    (kb / "docs" / "c.md").write_text("# More\n\nMore sourdough notes.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(rebuild=True), now="20260725 18:10")

    _, after = server.search("sourdough", k=None)
    assert {p.path for p in after.passages} > {p.path for p in before.passages}


def test_the_tools_are_namespaced(kb: Path) -> None:
    """`kb_search` would collide with every other KB server an agent has loaded (§8)."""
    import asyncio

    mcp, server = build([kb])
    try:
        tools = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in tools}
        assert names == {"pinakes_search", "pinakes_get", "pinakes_links", "pinakes_list_kbs"}
        assert not any(name.startswith("kb_") for name in names)
    finally:
        server.close()


def test_list_kbs_reports_document_counts(server: Server) -> None:
    listing = server.list_kbs()
    assert listing[0]["documents"] == 2
    assert listing[0]["name"] == "research"
    assert listing[0]["id"]


# --- page provenance on the agent surface (I8) --------------------------------------------------


PDF_CORPUS = Path(__file__).parent / "pdf-corpus"
PDF = "tables-bordered.pdf"


@pytest.fixture
def pdf_kb(tmp_path: Path) -> Path:
    root = make_kb(tmp_path / "pdfkb", name="scanned", documents={})
    path = root / "pinakes.toml"
    body = path.read_text(encoding="utf-8")
    include = 'include = ["**/*.md", "**/*.txt"]'
    assert include in body, "the template's include line has changed shape"
    path.write_text(
        body.replace(include, 'include = ["**/*.md", "**/*.txt", "**/*.pdf"]'), encoding="utf-8"
    )
    (root / "docs" / PDF).write_bytes((PDF_CORPUS / PDF).read_bytes())
    sync(load(root), options=SyncOptions(), now="20260729 05:20")
    return root


@pytest.fixture
def pdf_server(pdf_kb: Path) -> Iterator[Server]:
    made = Server([pdf_kb])
    yield made
    made.close()


def test_a_non_paged_source_carries_null_pages_on_the_mcp_surface(server: Server) -> None:
    """Markdown has no pages, and `page_start` must say so rather than be absent — an agent that
    has to distinguish "no pages" from "field missing" will get it wrong."""
    served, result = server.search("retrieval", k=None)
    passage = as_payload(served, result)["passages"][0]

    assert passage["page_start"] is None
    assert passage["page_end"] is None
    assert ":p" not in passage["citation"]


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_mcp_search_carries_page_spans(pdf_server: Server) -> None:
    served, result = pdf_server.search("Digitisation", k=None)
    passages = as_payload(served, result)["passages"]

    assert passages, "the PDF must be searchable for the rest to mean anything"
    hit = next(p for p in passages if "Digitisation" in p["evidence"])

    # `Digitisation` is on page 2, and the chunk carrying it begins on page 1: the fixture's table
    # and the prose beneath it land in one chunk that straddles the break. That is I5's stated
    # allowance, and it is why a citation has to be able to render a *range* — a single page number
    # here would be a claim the passage does not support.
    assert (hit["page_start"], hit["page_end"]) == (1, 2)
    assert hit["citation"].startswith(f"{hit['path']}:p1-2")


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_mcp_get_is_page_aware(pdf_server: Server, pdf_kb: Path) -> None:
    """A `get` must support the same citation vocabulary a `search` does, or an agent can cite a
    passage it found and not one it read."""
    result = pdf_server.search("Digitisation", k=None)[1]
    doc_id = next(p.doc_id for p in result.passages if "Digitisation" in p.text)

    whole = pdf_server.document(doc_id)
    assert whole["page_count"] == 2
    assert whole["citation"].endswith(":p1-2")
    assert "[page 1]" in whole["text"] and "[page 2]" in whole["text"]
    assert "Digitisation" in whole["text"]

    one = pdf_server.document(doc_id, page_start=2, page_end=2)
    assert one["citation"].endswith(":p2")
    assert one["page_start"] == 2 and one["page_end"] == 2
    assert one["page_count"] == 2, "the document still has two pages; this response has one"
    assert "[page 2]" in one["text"]
    assert "[page 1]" not in one["text"]
    assert "Correspondence" not in one["text"], "page 1's table must not leak into page 2"
    assert "Digitisation" in one["text"]


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_page_range_outside_the_document_is_refused_by_its_own_bounds(
    pdf_server: Server,
) -> None:
    result = pdf_server.search("Digitisation", k=None)[1]
    doc_id = next(p.doc_id for p in result.passages if "Digitisation" in p.text)

    for start, end in ((0, 1), (1, 3)):
        with pytest.raises(ServeError) as exc_info:
            pdf_server.document(doc_id, page_start=start, page_end=end)
        assert "has 2 page(s)" in exc_info.value.message
        assert "1-indexed" in exc_info.value.remedy

    # A backwards range is its own error: both bounds exist, they are just the wrong way round.
    with pytest.raises(ServeError) as exc_info:
        pdf_server.document(doc_id, page_start=2, page_end=1)
    assert "runs backwards" in exc_info.value.message

    # …and a single out-of-range bound must name *that bound*, not a range the caller never asked
    # for. Validating the resolved pair reported this as "pages 5-2", which reads as pinakes'
    # mistake rather than the caller's.
    with pytest.raises(ServeError) as exc_info:
        pdf_server.document(doc_id, page_start=5)
    assert "page_start=5 is not a page in it" in exc_info.value.message
    assert "5-2" not in exc_info.value.message


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_pdf_is_served_as_its_extracted_text_rather_than_its_bytes(pdf_server: Server) -> None:
    """`read_text` on a PDF raises `UnicodeDecodeError`, which is a `ValueError` and not an
    `OSError` — so before page-awareness this escaped `pinakes_get` as an unhandled traceback."""
    result = pdf_server.search("Digitisation", k=None)[1]
    doc_id = next(p.doc_id for p in result.passages if "Digitisation" in p.text)

    document = pdf_server.document(doc_id)
    assert not document["text"].startswith("%PDF")
    assert "Restoration work" in document["text"]


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_swept_extraction_cache_is_an_error_rather_than_a_silent_re_extraction(
    pdf_server: Server, pdf_kb: Path
) -> None:
    """Re-extracting would hand back text the index was not built from — and for a paid backend it
    would spend money inside a read-only tool call. Saying so is the only honest answer."""
    result = pdf_server.search("Digitisation", k=None)[1]
    doc_id = next(p.doc_id for p in result.passages if "Digitisation" in p.text)
    for entry in (pdf_kb / ".pinakes" / "cache" / "extract").glob("*.json"):
        entry.unlink()

    with pytest.raises(ServeError) as exc_info:
        pdf_server.document(doc_id)
    assert "no longer in the cache" in exc_info.value.message
    assert "pnk sync" in exc_info.value.remedy


def test_a_page_range_on_a_source_that_has_none_is_refused(server: Server) -> None:
    result = server.search("retrieval", k=None)[1]
    doc_id = result.passages[0].doc_id

    with pytest.raises(ServeError) as exc_info:
        server.document(doc_id, page_start=1)
    assert "has no pages" in exc_info.value.message


# --- pinakes_links (L5) --------------------------------------------------------------------


def author_link(root: Path, source: str, target_uri: str, rel: str) -> None:
    """Author one link into `source`'s sidecar and re-sync — the authoring model, by hand."""
    import yaml

    from pinakes.sidecar import SIDECAR_SUFFIX

    path = root / "docs" / f"{source}{SIDECAR_SUFFIX}"
    body = yaml.safe_load(path.read_text(encoding="utf-8"))
    body.setdefault("links", []).append({"to": target_uri, "rel": rel})
    path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    sync(load(root), options=SyncOptions(), now="20260725 18:02")


def doc_id_of(root: Path, filename: str) -> str:
    import yaml

    from pinakes.sidecar import SIDECAR_SUFFIX

    return str(
        yaml.safe_load((root / "docs" / f"{filename}{SIDECAR_SUFFIX}").read_text("utf-8"))["id"]
    )


ABSENT_KB = "01KYD0000000000000ABSENTKB"
"""A KB this server is deliberately not pointed at. Recognisable on sight, and 26 valid Crockford
characters — checked, because hand-writing a ULID has now produced a wrong one three times (`O` and
`I` are not in the alphabet, and it is easy to land on 25 characters)."""

ABSENT_DOC = str(mint_doc_id())
"""Minted rather than written. The document is in a KB that does not exist, so only the *KB* half
needs to be recognisable."""


@pytest.fixture
def linked_kb(kb: Path) -> Path:
    """`a.md` links to `b.md`, and to a document in a KB this server is not pointed at.

    `c.md` is deliberately left unlinked: "this document has no links" and "your arguments excluded
    them" are different answers, and without an unlinked document nothing can tell them apart.
    """
    (kb / "docs" / "c.md").write_text("# Isolated\n\nNothing links here.\n", encoding="utf-8")
    sync(load(kb), options=SyncOptions(), now="20260725 18:01")
    kb_id = load(kb).kb.id
    author_link(kb, "a.md", f"pnk://{kb_id}/{doc_id_of(kb, 'b.md')}", "related")
    author_link(kb, "a.md", f"pnk://{ABSENT_KB}/{ABSENT_DOC}", "counterpart")
    return kb


def test_pinakes_links_returns_score_and_frontier_on_every_return(linked_kb: Path) -> None:
    """APPROACH §5's contract: both, always — not only when something interesting happened. An
    agent that has to branch on a key's presence cannot write one code path."""
    made = Server([linked_kb])
    try:
        payload = made.links(doc_id_of(linked_kb, "a.md"))
        assert "frontier" in payload
        for row in payload["neighbours"]:
            assert "score" in row and isinstance(row["score"], float | int)

        # ...and on a walk that returned nothing, where there is nothing to report.
        empty = made.links(doc_id_of(linked_kb, "b.md"), direction="out")
        assert empty["neighbours"] == []
        assert "frontier" in empty and "truncated" in empty
    finally:
        made.close()


def test_pinakes_links_reports_unknown_confidence_with_and_without_a_query(
    linked_kb: Path,
) -> None:
    """Unconditionally `unknown`. The thresholds `pinakes_search` reports against are fitted per KB
    on the reranker score of the top *retrieved passage*; a traversal neighbour is not one, a list
    spanning two KBs has no single manifest whose thresholds apply, and no fitted data for a
    traversal signal exists. Anything else here would be the invented signal §4.2 forbids."""
    made = Server([linked_kb])
    try:
        assert made.links(doc_id_of(linked_kb, "a.md"))["confidence"] == "unknown"
        assert (
            made.links(doc_id_of(linked_kb, "a.md"), query="retrieval")["confidence"] == "unknown"
        )
    finally:
        made.close()


def test_a_neighbour_outside_the_served_kbs_returns_its_kb_id_and_a_reason(
    linked_kb: Path,
) -> None:
    """Reachability is a property of **this server invocation**, not of any manifest. A KB listed
    in `[[links.kb]]` but not served is one this process cannot answer about — and the neighbour is
    still identified, never merely omitted, so the agent can act on the fact that it exists."""
    made = Server([linked_kb])
    try:
        rows = {row["rel"]: row for row in made.links(doc_id_of(linked_kb, "a.md"))["neighbours"]}
        foreign = rows["counterpart"]
        assert foreign["reachable"] is False
        assert foreign["kb_id"] == ABSENT_KB
        assert foreign["doc_id"] and foreign["reason"]
        assert rows["related"]["reachable"] is True
    finally:
        made.close()


def test_pinakes_get_resolves_a_neighbour_returned_by_pinakes_links(linked_kb: Path) -> None:
    """The test that makes "fetchable" mean something. A neighbour an agent cannot then read is an
    identifier, not an answer."""
    made = Server([linked_kb])
    try:
        rows = made.links(doc_id_of(linked_kb, "a.md"))["neighbours"]
        local = next(row for row in rows if row["reachable"])
        fetched = made.document(local["doc_id"])
        assert fetched["text"]
    finally:
        made.close()


def test_a_neighbour_in_a_second_served_kb_says_which_kb_to_fetch_it_from(tmp_path: Path) -> None:
    """`reachable: true` across two served KBs, where the obvious follow-up still fails.

    A document id resolves **inside one KB**, so `pinakes_get(doc_id)` looks in the KB the traversal
    started from and reports "no active document" for a neighbour that plainly exists. `reachable`
    would then mean nothing an agent could act on, which is the opposite of why the flag is there.
    Only this two-KB shape reaches it — the single-KB fixture above always picks a same-KB row.
    """
    alpha = make_kb(
        tmp_path / "alpha",
        name="alpha",
        documents={"a.md": "# Retrieval\n\nRetrieval.\n", "a2.md": "# Sibling\n\nRanking.\n"},
    )
    beta = make_kb(tmp_path / "beta", name="beta", documents={"b.md": "# Ranking\n\nRanking.\n"})
    author_link(alpha, "a.md", f"pnk://{load(beta).kb.id}/{doc_id_of(beta, 'b.md')}", "partner")

    made = Server([alpha, beta])
    try:
        row = made.links(doc_id_of(alpha, "a.md"))["neighbours"][0]
        assert row["reachable"] is True and row["kb_id"] == str(load(beta).kb.id)

        with pytest.raises(ServeError):
            made.document(row["doc_id"])  # the trap: right id, wrong KB
        assert made.document(**row["fetch_with"])["text"], "the row must carry what makes it work"

        # ...and only there. A same-KB neighbour resolves without a `kb`, so a `fetch_with` on it
        # would be noise the docs explicitly deny — nothing pinned the negative half.
        alone = Server([alpha])
        try:
            author_link(
                alpha, "a.md", f"pnk://{load(alpha).kb.id}/{doc_id_of(alpha, 'a2.md')}", "sib"
            )
            local = next(
                r for r in alone.links(doc_id_of(alpha, "a.md"))["neighbours"] if r["rel"] == "sib"
            )
            assert "fetch_with" not in local
        finally:
            alone.close()
    finally:
        made.close()


@pytest.fixture
def chain_kb(tmp_path: Path) -> Path:
    """Eight documents in a line: `c0 → c1 → … → c7`. Long enough that the depth clamp is the
    *only* thing that can stop the walk — the earlier version of this test ran over a graph one hop
    deep, where `distance <= 3` held whether the clamp existed or not."""
    root = make_kb(
        tmp_path / "chain",
        name="chain",
        documents={f"c{i}.md": f"# Link {i}\n\nRetrieval hop number {i}.\n" for i in range(8)},
    )
    kb_id = load(root).kb.id
    for i in range(7):
        author_link(root, f"c{i}.md", f"pnk://{kb_id}/{doc_id_of(root, f'c{i + 1}.md')}", "next")
    return root


def test_depth_is_capped_server_side(chain_kb: Path) -> None:
    """Asked for 99 hops down a chain that has 7. The documented cap is **3**, written literally:
    importing `MAX_DEPTH` from the module under test would follow the constant wherever it moved,
    which is the one thing a cap test must not do."""
    made = Server([chain_kb])
    try:
        payload = made.links(doc_id_of(chain_kb, "c0.md"), depth=99, direction="out")
        distances = sorted(row["distance"] for row in payload["neighbours"])

        assert distances == [1, 2, 3], "the walk reaches exactly the documented cap, and no further"
        # c3 is returned and then *not expanded*: the frontier names the node the walk stopped at,
        # never the unseen c4 beyond it — a node the traversal has no way to know exists.
        frontier = {entry["doc_id"]: entry["reason"] for entry in payload["frontier"]}
        assert frontier[doc_id_of(chain_kb, "c3.md")] == "depth"
        # ...and `truncated` stays empty: it reports the *response* being cut short (rows, tokens),
        # never the walk stopping where it was asked to. Two different problems, two different keys.
        assert payload["truncated"] == []
    finally:
        made.close()


def test_an_empty_answer_says_whether_the_arguments_emptied_it(linked_kb: Path) -> None:
    """`b.md` has one inbound link. Asked for `out` only, it comes back with no neighbours — and
    the hint used to read "No links from here; search instead", telling an agent to stop traversing
    a graph it was standing in. The unfiltered case must still say exactly that, because there it
    is true."""
    made = Server([linked_kb])
    try:
        by_direction = made.links(doc_id_of(linked_kb, "b.md"), direction="out")
        assert by_direction["neighbours"] == []
        assert "No links from here" not in by_direction["suggested_next"]
        assert "direction='both'" in by_direction["suggested_next"]

        by_rel = made.links(doc_id_of(linked_kb, "a.md"), rel="nosuchrel")
        assert by_rel["neighbours"] == []
        assert "No links from here" not in by_rel["suggested_next"]
    finally:
        made.close()

    # ...and where it *is* true — a document with no links, asked with no narrowing argument at all
    # — the blunt advice must survive. A fix that never says it would be its own defect.
    unlinked = Server([linked_kb])
    try:
        honest = unlinked.links(doc_id_of(linked_kb, "c.md"))["suggested_next"]
        assert honest.startswith("No links from here")
    finally:
        unlinked.close()


def test_a_filtered_walk_reports_the_filter_before_the_dangling_links(tmp_path: Path) -> None:
    """Both conditions true at once — the only shape in which the precedence means anything.

    `rel` narrows `unresolved` too, so a rel-filtered call leaves it empty and the branch this
    orders against never competes. `direction` is the lever: `a.md`'s outbound link dangles, its
    inbound one is live, so `direction="out"` empties the walk while `unresolved` fills and a live
    neighbour sits one dropped argument away. Inverted, the caller is told their links are broken
    and sent to full-text search instead of to the retry that works.
    """
    root = make_kb(
        tmp_path / "both",
        name="both",
        documents={"a.md": "# A\n\nRetrieval.\n", "b.md": "# B\n\nRanking.\n"},
    )
    kb_id = load(root).kb.id
    author_link(root, "a.md", f"pnk://{kb_id}/{ABSENT_DOC}", "related")  # outbound, dangles
    author_link(root, "b.md", f"pnk://{kb_id}/{doc_id_of(root, 'a.md')}", "cites")  # inbound, live

    made = Server([root])
    try:
        narrowed = made.links(doc_id_of(root, "a.md"), direction="out")
        assert narrowed["neighbours"] == [] and narrowed["unresolved"], "both conditions hold"
        assert "No links match these arguments" in narrowed["suggested_next"]
        assert "resolve to documents this KB no longer has" not in narrowed["suggested_next"]

        # ...and unfiltered, the same document reaches its live neighbour instead.
        assert [row["rel"] for row in made.links(doc_id_of(root, "a.md"))["neighbours"]] == [
            "cites"
        ]
    finally:
        made.close()


def test_a_document_whose_links_all_dangle_is_not_called_unlinked(tmp_path: Path) -> None:
    """`neighbours: []` beside a populated `unresolved` is not "no links from here".

    The payload contradicts itself in the same breath: it lists the links and then advises the
    caller to stop traversing and search instead. No filter is involved, so the `filtered` branch
    cannot cover it.
    """
    root = make_kb(
        tmp_path / "dangling", name="dangling", documents={"a.md": "# A\n\nRetrieval.\n"}
    )
    author_link(root, "a.md", f"pnk://{load(root).kb.id}/{ABSENT_DOC}", "related")

    made = Server([root])
    try:
        payload = made.links(doc_id_of(root, "a.md"))
        assert payload["neighbours"] == [] and payload["unresolved"]
        assert "No links from here" not in payload["suggested_next"]
        assert "unresolved" in payload["suggested_next"]
    finally:
        made.close()


def test_a_cross_kb_neighbour_is_terminal_over_mcp_too(linked_kb: Path) -> None:
    made = Server([linked_kb])
    try:
        rows = {
            row["rel"]: row
            for row in made.links(doc_id_of(linked_kb, "a.md"), depth=3)["neighbours"]
        }
        assert rows["counterpart"]["terminal"] is True
        assert rows["related"]["terminal"] is False
    finally:
        made.close()


def test_an_unknown_document_is_refused_with_a_remedy(linked_kb: Path) -> None:
    made = Server([linked_kb])
    try:
        with pytest.raises(ServeError) as caught:
            made.links(ABSENT_DOC)
        assert caught.value.remedy
    finally:
        made.close()


def test_pinakes_search_and_get_payloads_are_unchanged(linked_kb: Path) -> None:
    """L5 adds a tool; it must not quietly reshape the two an agent already depends on."""
    from pinakes.serve import as_payload

    made = Server([linked_kb])
    try:
        served, result = made.search("retrieval", k=None)
        payload = as_payload(served, result)
        # The real shape, read from `as_payload` rather than guessed at — the point of this test
        # is that L5 changed none of it, so an assertion invented from memory would be worthless.
        assert set(payload) == {
            "kb",
            "query",
            "confidence",
            "confidence_reason",
            "evidence_note",
            "passages",
            "suggested_next",
        }
        assert set(payload["passages"][0]) == {
            "doc_id",
            "path",
            "heading_path",
            "citation",
            "page_start",
            "page_end",
            "stale_extraction",
            "evidence",
        }
        # Read from a live call, not written from memory. A shape assertion invented rather than
        # observed pins the wrong contract, and this test exists to catch a *change* — so the
        # baseline has to be what the code actually returns today. (`page_start`/`page_end` appear
        # only for a paged source; this document has none.)
        assert set(made.document(doc_id_of(linked_kb, "b.md"))) == {
            "kb",
            "id",
            "path",
            "title",
            "tags",
            "text",
            "citation",
            "evidence_note",
        }
    finally:
        made.close()
