"""One datum, traced end to end — the shape of miss these traces exist to catch.

v0.1's two most expensive plannable misses were both producer/consumer *name* agreement with
*column* disagreement: every layer used the right word for the wrong number, and five consistency
passes could not see it, because each layer was internally coherent. A trace is the only test that
can: every hop asserts against the value carried from the hop before it, so a slip anywhere between
extraction and the agent surface has nowhere to hide.

Three data are traced: a word from a table cell (page provenance), a filter dimension (selection),
and one slice's cost (money).
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import pdf_extraction_runnable

from pinakes import store
from pinakes.cli import main
from pinakes.embed import EmbeddingBackend, load_backend
from pinakes.extract import ExtractionContext
from pinakes.extract import cache as extract_cache
from pinakes.extract import fingerprint as extraction_fingerprint
from pinakes.manifest import load
from pinakes.search import Filters, escape_fts, search
from pinakes.serve import Server, as_payload
from pinakes.sync import SyncOptions, sync

pytestmark = [
    pytest.mark.pdf,
    pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed"),
]

CORPUS = Path(__file__).parent / "pdf-corpus"
FIXTURE = "tables-bordered.pdf"

#: (word, the page it is on) — read off the fixture's own `expected.txt` and verified against a
#: real pypdfium2 extraction, never derived from `page_spans` inside the test. A page number the
#: test computes the same way the code does would agree with any bug they share.
#:
#: **Both pages are traced on purpose.** The table sits entirely on page 1, so a `page_start` that
#: were hardcoded, defaulted or off by the page-span's own base would still satisfy a page-1-only
#: trace. `Digitisation` is on page 2 and appears nowhere else in the document.
TRACED = [("Correspondence", 1), ("Digitisation", 2)]


@pytest.fixture
def pdf_kb(make_fake_kb: Callable[..., Path]) -> Path:
    root = make_fake_kb()
    manifest_path = root / "pinakes.toml"
    body = manifest_path.read_text(encoding="utf-8")
    # The template deliberately leaves PDFs out of `include`. Assert the rewrite landed rather than
    # trusting `str.replace`, which reports a miss to nobody — a KB with no PDF in it would make
    # every trace below pass vacuously.
    include = 'include = ["**/*.md", "**/*.txt"]'
    assert include in body, "the template's include line has changed shape"
    body = body.replace(include, 'include = ["**/*.md", "**/*.txt", "**/*.pdf"]')
    # `make_fake_kb` rewrites the *embedding* provider only (its `_rewrite` substitutes once), so
    # `[rerank]` still names sentence-transformers and `pnk search` would refuse before reaching a
    # single assertion below.
    rerank = '[rerank]\nprovider = "sentence-transformers"'
    assert rerank in body, "the template's [rerank] block has changed shape"
    body = body.replace(rerank, '[rerank]\nprovider = "fake"')
    manifest_path.write_text(body, encoding="utf-8")
    (root / "docs" / FIXTURE).write_bytes((CORPUS / FIXTURE).read_bytes())
    sync(load(root), options=SyncOptions(), now="20260729 05:00")
    return root


def _document_row(root: Path) -> tuple[str, str, str, str]:
    connection = store.connect_ro(load(root).index_path)
    try:
        row = connection.execute(
            "SELECT id, path, content_hash, extraction_backend FROM documents "
            "WHERE path = ? AND state = 'active'",
            (f"docs/{FIXTURE}",),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None, "the PDF must have been indexed for anything below to mean something"
    return (
        str(row["id"]),
        str(row["path"]),
        str(row["content_hash"]),
        str(row["extraction_backend"]),
    )


@pytest.mark.parametrize(("word", "expected_page"), TRACED)
def test_a_table_cell_word_survives_every_hop(
    pdf_kb: Path, word: str, expected_page: int, capsys: pytest.CaptureFixture[str]
) -> None:
    from pinakes.extract.pdfium import Pypdfium2Extractor

    manifest = load(pdf_kb)
    doc_id, path, content_hash, backend = _document_row(pdf_kb)

    # hop 1 — extraction: the word is at offset `o`, on page `p`.
    extracted = Pypdfium2Extractor().extract(CORPUS / FIXTURE, ExtractionContext())
    assert extracted.text.count(word) == 1, "a word appearing twice traces two data, not one"
    offset = extracted.text.index(word)
    page = next(
        n for n, (start, end) in enumerate(extracted.page_spans, start=1) if start <= offset < end
    )
    assert page == expected_page, "the extraction disagrees with the fixture's own expected text"

    # hop 2 — cache: the entry the index was built from yields the same offset and page.
    cached = extract_cache.peek(
        manifest.extract_cache_dir,
        content_hash=content_hash,
        fingerprint=extraction_fingerprint(backend, manifest.extraction.model),
    )
    assert cached is not None, "sync must have written a cache entry keyed by what it recorded"
    assert cached.text.index(word) == offset
    assert cached.page_spans == extracted.page_spans

    # hop 3 — chunks: at least one covers the offset, and every one that does carries the word and
    # a page range containing `p`.
    connection = store.connect_ro(manifest.index_path)
    try:
        covering = connection.execute(
            "SELECT id, text, char_start, char_end, page_start, page_end FROM chunks "
            "WHERE doc_id = ? AND char_start <= ? AND char_end > ?",
            (doc_id, offset, offset),
        ).fetchall()
        assert covering, "the never-drop guarantee means some chunk contains every offset"
        for row in covering:
            assert word in str(row["text"])
            # **Not `page_start == p`.** A chunk that straddles a page break starts on the earlier
            # page, so a word on the later one legitimately sits inside a chunk whose `page_start`
            # is smaller — I5 allows exactly that, and the citation renders `p1-2` for it. Asserting
            # equality would fail on a correct chunker (plans/v0.2.md's I8 draft said `==`).
            assert int(row["page_start"]) <= page <= int(row["page_end"])

        # hop 4 — FTS: the lexical index returns those same rowids for the word.
        matched = {
            int(r["rowid"])
            for r in connection.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", (escape_fts(word),)
            )
        }
        assert {int(r["id"]) for r in covering} <= matched
        starts = {int(r["char_start"]) for r in covering}
        pages = {(int(r["page_start"]), int(r["page_end"])) for r in covering}
    finally:
        connection.close()

    # hop 5 — CLI: the rendered citation names the page, in the `p` form that cannot be misread
    # as the character offsets a non-paged source still renders.
    assert main(["search", word, "--kb", str(pdf_kb), "--json"]) == 0
    from_cli = [
        p
        for p in json.loads(capsys.readouterr().out)["passages"]
        if p["doc_id"] == doc_id and p["char_start"] in starts
    ]
    assert from_cli, f"{word} must come back from `pnk search`"
    cli_passage = from_cli[0]
    assert (cli_passage["page_start"], cli_passage["page_end"]) in pages
    assert cli_passage["page_start"] <= page <= cli_passage["page_end"]
    expected_locator = (
        f"p{cli_passage['page_start']}"
        if cli_passage["page_start"] == cli_passage["page_end"]
        else f"p{cli_passage['page_start']}-{cli_passage['page_end']}"
    )
    assert cli_passage["citation"].startswith(f"{path}:{expected_locator}")

    # hop 6 — MCP: the same passage, the same page numbers. Asserting the *same* number on both
    # surfaces is the only way a CLI/MCP divergence is visible at all.
    server = Server([pdf_kb])
    try:
        served, result = server.search(word, k=None, filters=Filters())
        payload = as_payload(served, result)
    finally:
        server.close()
    from_mcp = [p for p in payload["passages"] if p["doc_id"] == doc_id and word in p["evidence"]]
    assert from_mcp
    assert (from_mcp[0]["page_start"], from_mcp[0]["page_end"]) == (
        cli_passage["page_start"],
        cli_passage["page_end"],
    )
    assert from_mcp[0]["citation"] == cli_passage["citation"]


def test_every_filter_dimension_resolves_for_pdfs(pdf_kb: Path) -> None:
    """Every dimension a PDF can be selected by must actually *select* it.

    The plan's draft asserted each dimension resolves to a column "non-null for every PDF row",
    which is vacuous: `tags` is not a column at all but `json_each(d.metadata, '$.tags')` over a
    field declared `NOT NULL DEFAULT '{}'`, so the non-null assertion holds by schema for every row
    — PDF or not — on a corpus where no PDF carries a single tag. Exercising the filter is the only
    version of this test that can fail.
    """
    manifest = load(pdf_kb)
    doc_id, path, _, _ = _document_row(pdf_kb)

    sidecar = pdf_kb / "docs" / f"{FIXTURE}.pnk.yaml"
    body = sidecar.read_text(encoding="utf-8")
    assert "tags:" not in body, "the fixture's own tags would make the tag filter untested"
    sidecar.write_text(body.rstrip("\n") + "\ntags:\n  - archive\n", encoding="utf-8")
    sync(manifest, options=SyncOptions(), now="20260729 05:01")

    mtime = (pdf_kb / "docs" / FIXTURE).stat().st_mtime
    dimensions = {
        "source_type": Filters(source_type="pdf"),
        "path_prefix": Filters(path_prefix="docs/tables"),
        "tags": Filters(tags=("archive",)),
        "modified_after": Filters(modified_after=mtime - 1),
        "modified_before": Filters(modified_before=mtime + 1),
    }
    connection = store.connect_ro(load(pdf_kb).index_path)
    try:
        for name, filters in dimensions.items():
            result = search(
                connection,
                load(pdf_kb),
                "correspondence",
                backend=_backend(pdf_kb),
                filters=filters,
            )
            assert any(p.doc_id == doc_id for p in result.passages), (
                f"filtering on {name} must still return {path}"
            )

        # …and a value that excludes it must exclude it, or the assertions above would pass on a
        # filter that is never applied at all.
        for name, filters in {
            "source_type": Filters(source_type="markdown"),
            "path_prefix": Filters(path_prefix="docs/nothing"),
            "tags": Filters(tags=("absent",)),
            "modified_after": Filters(modified_after=mtime + 3600),
            "modified_before": Filters(modified_before=mtime - 3600),
        }.items():
            result = search(
                connection,
                load(pdf_kb),
                "correspondence",
                backend=_backend(pdf_kb),
                filters=filters,
            )
            assert not any(p.doc_id == doc_id for p in result.passages), (
                f"an excluding {name} filter must exclude {path}"
            )
    finally:
        connection.close()


def _backend(root: Path) -> EmbeddingBackend:
    return load_backend(load(root).embedding, offline=True)


# --- the money trace ---------------------------------------------------------------------------


def test_a_paid_slice_traces_from_estimate_to_the_budget_report(
    make_fake_kb: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One slice's cost, hop by hop: estimate → reservation → the response's own `usage` →
    reconciliation → the total `pnk budget` prints.

    **The unit is the slice, not the page.** After decision 8 no per-page number exists anywhere in
    the money machinery, and a trace whose unit nothing produces cannot assert against the layer
    below it. Each hop asserts against the previous one's number, so a unit slip — tokens vs MTok,
    USD vs EUR — cannot hide in an intermediate layer while every layer stays internally coherent.
    """
    import shutil
    from decimal import Decimal

    from test_extract_claude import MODEL, RecordedTransport, load_fixture

    from pinakes.budget.estimate import estimate_document
    from pinakes.budget.ledger import RecordKind, ledger_path
    from pinakes.budget.ledger import read as read_ledger
    from pinakes.budget.prices import load_prices
    from pinakes.budget.summary import euros
    from pinakes.cli import EXIT_OK
    from pinakes.extract import CLAUDE_VISION, ExtractorEntry, register_extractor, registered_entry
    from pinakes.extract import claude as claude_module
    from pinakes.extract.claude import ClaudeVisionExtractor

    now = "20260729 05:00"
    root = make_fake_kb(
        extraction_backend=CLAUDE_VISION,
        budget={"per_operation_eur": "50.00", "daily_eur": "50.00", "monthly_eur": "50.00"},
    )
    manifest_path = root / "pinakes.toml"
    body = manifest_path.read_text(encoding="utf-8")
    assert 'include = ["**/*.md", "**/*.txt"]' in body
    manifest_path.write_text(
        body.replace('include = ["**/*.md", "**/*.txt"]', 'include = ["**/*.pdf"]'),
        encoding="utf-8",
    )
    shutil.copyfile(CORPUS / "baseline-1p.pdf", root / "docs" / "scan.pdf")

    # hop 1 — the estimate: one page is one slice, and a slice is what a reservation covers.
    prices = load_prices()
    loaded = load(root)
    estimate = estimate_document(
        pages=1,
        model=MODEL,
        prices=prices,
        now=now,
        max_price_age_days=loaded.budget.max_price_age_days,
    )
    assert estimate.requests == 1, "this trace's unit is one slice; the fixture must be one call"

    transport = RecordedTransport("short-final-slice")
    transport.entries[0]["content"] = [
        {"type": "text", "text": json.dumps({"pages": [{"page": 1, "text": "paid text"}]})}
    ]
    original_entry = registered_entry(CLAUDE_VISION)
    register_extractor(
        CLAUDE_VISION,
        ExtractorEntry(
            lambda: ClaudeVisionExtractor(transport),
            claude_module.fingerprint_inputs,
            paid=True,
            requires=("anthropic", "claude"),
        ),
    )
    monkeypatch.setattr(claude_module, "default_transport", lambda: transport)
    try:
        assert main(["sync", "--kb", str(root), "--force", "--yes"]) == EXIT_OK
    finally:
        register_extractor(CLAUDE_VISION, original_entry)
    capsys.readouterr()

    records = read_ledger(ledger_path(root / ".pinakes")).records
    reservations = [r for r in records if r.kind is RecordKind.RESERVATION]
    reconciliations = [r for r in records if r.kind is RecordKind.RECONCILIATION]
    assert len(reservations) == 1 and len(reconciliations) == 1

    # hop 2 — the reservation carries the estimate, in euros, for this one slice.
    assert reservations[0].cost_eur == estimate.per_request_eur

    # hop 3 — the response's own `usage`, straight from the recorded fixture.
    usage = load_fixture("short-final-slice")["responses"][0]["usage"]
    input_tokens, output_tokens = usage["input_tokens"], usage["output_tokens"]

    # hop 4 — the reconciliation reads that usage, never the estimate.
    assert reconciliations[0].input_tokens == input_tokens
    assert reconciliations[0].output_tokens == output_tokens
    assert reconciliations[0].input_tokens != estimate.input_tokens_per_request, (
        "if the estimate and the response agreed by accident, this trace could not tell a "
        "reconciliation that read the response from one that re-reported its own guess"
    )

    price = prices.for_model(MODEL)
    expected_usd = (
        Decimal(input_tokens) * price.input_per_mtok_usd
        + Decimal(output_tokens) * price.output_per_mtok_usd
    ) / Decimal(1_000_000)
    assert reconciliations[0].cost_usd == expected_usd.quantize(reconciliations[0].cost_usd)

    # hop 5 — and that is the number `pnk budget` reports, formatted by the report's own
    # formatter rather than by this test's idea of one.
    spent = euros(reconciliations[0].cost_eur)
    assert Decimal(spent) > 0, (
        "a total that rounds to zero would make the assertion below pass on any output"
    )
    assert main(["budget", "--kb", str(root)]) == EXIT_OK
    assert spent in capsys.readouterr().out
