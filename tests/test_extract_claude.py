"""The paid extractor, driven entirely by `tests/fixtures/claude/` — with `anthropic` absent.

**Unmarked on purpose.** The whole point of the registry seam is that the paid path's behaviour is
testable without the paid client installed; a suite that needed `[claude]` would prove the opposite
of what it claims. The `paid` marker is reserved for tests that make a *real* API call, and there
is exactly one of those here.

Most cases drive `extract_slice` directly with a few bytes standing in for a sliced PDF, so they
need no extras at all and run on every CI leg. The document-level cases genuinely slice a PDF and
carry the `pdf` marker for it.
"""

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import paid_runnable, pdf_extraction_runnable

from pinakes.budget.accountant import Accountant
from pinakes.budget.ledger import CallState, ledger_path, quantise, read, resolve
from pinakes.budget.prices import Prices, load_prices
from pinakes.errors import ExtractionError
from pinakes.extract import CLAUDE_VISION, fingerprint_inputs
from pinakes.extract import fingerprint as extraction_fingerprint
from pinakes.extract.cache import stage_page, staged_pages
from pinakes.extract.claude import (
    LEAKED_TAG_PATTERN,
    MAX_REQUEST_BYTES,
    MAX_TOKENS_RETRY,
    SCHEMA_RETRIES,
    SEMANTIC_CALL_BUDGET,
    TRANSPORT_ATTEMPTS,
    Billability,
    BudgetRefusedError,
    CallTally,
    SchemaFailureError,
    TransportError,
    assemble_pages,
    build_client_kwargs,
    build_request,
    extract_slice,
    parse_pages,
)
from pinakes.manifest import load
from pinakes.sync import hash_file

FIXTURES = Path(__file__).parent / "fixtures" / "claude"
CORPUS = Path(__file__).parent / "pdf-corpus"
MODEL = "claude-opus-5"
SLICE_BYTES = b"%PDF-1.4\n% a stand-in for a sliced sub-document\n"

#: Every branch the plan cites the fixture set for. Hard-coded rather than derived from the
#: directory: a test that reads the same thing it checks passes on any content at all.
REQUIRED_BRANCHES = frozenset(
    {
        "happy",
        "short-slice",
        "refusal",
        "schema-invalid",
        "truncated",
        "context-window",
        "content-dropping",
        "tag-leaking",
        "429",
        "500",
        "timeout",
    }
)


def load_fixture(name: str) -> dict[str, Any]:
    raw: object = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, Any], raw)


class RecordedTransport:
    """Replays one fixture's script. Counts its own calls, so "every retry took its own
    reservation" is an observation rather than an inference."""

    def __init__(self, *scripts: str, on_call: Callable[[int], None] | None = None) -> None:
        self.on_call = on_call
        """Runs just before each reply — the seam for "something else spent while we were
        backing off", which is not a hypothetical on a KB two processes share."""
        self.entries: list[dict[str, Any]] = []
        for name in scripts:
            responses: object = load_fixture(name)["responses"]
            assert isinstance(responses, list)
            for entry in cast(list[object], responses):
                assert isinstance(entry, dict)
                self.entries.append(cast(dict[str, Any], entry))
        self.calls = 0
        self.requests: list[Mapping[str, Any]] = []
        self.token_counts = 0

    def create(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.calls >= len(self.entries):
            raise AssertionError(
                f"the extractor made call {self.calls + 1} but the script has "
                f"{len(self.entries)} entries — the test's expectation, not the code, is wrong"
            )
        entry = self.entries[self.calls]
        self.calls += 1
        self.requests.append(request)
        if self.on_call is not None:
            self.on_call(self.calls)
        if entry.get("kind") == "error":
            raise _replay_error(entry)
        return entry

    def count_tokens(self, request: Mapping[str, Any]) -> int:
        self.token_counts += 1
        return 30_300


def _replay_error(entry: dict[str, Any]) -> TransportError:
    kind = entry.get("class")
    if kind == "timeout":
        return TransportError(
            "the request timed out", billability=Billability.UNKNOWN, retryable=False
        )
    if kind == "connection":
        return TransportError(
            "the connection failed before any response",
            billability=Billability.NOT_BILLED,
            retryable=True,
        )
    status = entry.get("status")
    assert isinstance(status, int)
    return TransportError(
        f"the API returned {status}",
        billability=Billability.NOT_BILLED,
        retryable=status == 429 or status >= 500,
        status=status,
    )


def prices() -> Prices:
    return Prices(
        as_of=datetime.now().strftime("%Y%m%d %H:%M"),
        usd_per_eur=Decimal("1.08"),
        models=load_prices().models,
    )


@pytest.fixture
def accountant(make_fake_kb: Callable[..., Path]) -> Accountant:
    root = make_fake_kb(
        extraction_backend=CLAUDE_VISION,
        budget={"per_operation_eur": "50.00", "daily_eur": "50.00", "monthly_eur": "50.00"},
    )
    # `yes=True`: a whole-document run is well above `confirm_above_eur`, and it should be — the
    # confirmation has its own tests, and every other test here is about something else.
    return Accountant(load(root), prices=prices(), now=datetime.now(UTC), yes=True)


def never_sleeps(_seconds: float) -> None:
    """Backoff is real in production and pointless in a test — asserted separately."""


def run_slice(
    accountant: Accountant,
    transport: RecordedTransport,
    *,
    pages: int = 5,
    tally: CallTally | None = None,
) -> Any:
    return extract_slice(
        transport=transport,
        accountant=accountant,
        pdf_bytes=SLICE_BYTES,
        pages_in_slice=pages,
        model=MODEL,
        reserved_eur=Decimal("0.04"),
        price=load_prices().for_model(MODEL),
        tally=tally or CallTally(),
        sleep=never_sleeps,
    )


def ledger_calls(accountant: Accountant) -> list[Any]:
    return list(resolve(read(ledger_path(accountant.manifest.state_dir)).records).calls)


# --- the fixture set is the artifact ---------------------------------------------------------


def test_the_recorded_fixture_set_covers_every_branch() -> None:
    """A fixture set described in a ground-rules section with no owner is how v0.1's paid-API gate
    came not to exist. This is the assertion that gives it one."""
    branches = {load_fixture(path.stem)["branch"] for path in FIXTURES.glob("*.json")}
    assert branches >= REQUIRED_BRANCHES, REQUIRED_BRANCHES - branches


def test_every_fixture_says_why_it_exists() -> None:
    for path in sorted(FIXTURES.glob("*.json")):
        fixture = load_fixture(path.stem)
        assert fixture["why"], f"{path.name} has no `why`"
        assert fixture["name"] == path.stem


def test_the_fixtures_do_not_claim_to_be_real_recordings() -> None:
    """They are authored from the documented shape, and the README says so. A fixture set that
    reads as captured-from-production is a claim about evidence nobody has."""
    readme = (FIXTURES / "README.md").read_text(encoding="utf-8")
    assert (
        "hand-authored to the documented response shape, not captured from the live API" in readme
    )


# --- the request ------------------------------------------------------------------------------


def test_the_client_disables_sdk_retries() -> None:
    """A pure function, real values, no client — so this runs with `anthropic` absent and is not
    a stand-in asserting a property of itself. The SDK's default of 2 turns one `messages.create`
    into up to three billed HTTP requests, and a request retried after a timeout can be billed
    twice for generation the server already completed."""
    assert build_client_kwargs() == {"max_retries": 0}


def test_the_request_puts_the_document_before_the_text_and_sends_no_sampling_knobs() -> None:
    request = build_request(model=MODEL, pdf_bytes=SLICE_BYTES, pages_in_slice=5)
    blocks = request["messages"][0]["content"]
    assert [block["type"] for block in blocks] == ["document", "text"]
    assert blocks[0]["source"]["media_type"] == "application/pdf"
    assert "\n" not in blocks[0]["source"]["data"]
    for forbidden in ("temperature", "top_p", "top_k"):
        assert forbidden not in request, f"{forbidden} 400s on this model"


def test_thinking_is_disabled_explicitly_and_pinned_to_its_effort() -> None:
    request = build_request(model=MODEL, pdf_bytes=SLICE_BYTES, pages_in_slice=5)
    assert request["thinking"] == {"type": "disabled"}
    assert request["output_config"]["effort"] in ("low", "medium", "high")
    assert request["output_config"]["format"]["type"] == "json_schema"


def test_a_slice_that_encodes_past_the_limit_is_refused_before_it_is_sent() -> None:
    from pinakes.extract.claude import RequestTooLargeError

    with pytest.raises(RequestTooLargeError):
        build_request(model=MODEL, pdf_bytes=b"x" * MAX_REQUEST_BYTES, pages_in_slice=5)


# --- the branch order -------------------------------------------------------------------------


def test_a_clean_slice_comes_back_whole(accountant: Accountant) -> None:
    transport = RecordedTransport("happy-five-page-slice")
    result = run_slice(accountant, transport)
    assert len(result.pages) == 5
    assert transport.calls == 1
    assert [call.state for call in ledger_calls(accountant)] == [CallState.RECONCILED]


def test_a_refusal_is_handled_before_content_is_read(accountant: Accountant) -> None:
    """The fixture's refusal carries an empty `content` list. Reading it first would raise a
    schema failure and mis-classify the cheapest failure in the set as the most expensive."""
    transport = RecordedTransport("refusal-then-success")
    assert transport.entries[0]["content"] == []
    result = run_slice(accountant, transport)
    assert len(result.pages) == 5
    assert transport.calls == 2


def test_a_second_refusal_is_recorded_rather_than_retried_forever(accountant: Accountant) -> None:
    transport = RecordedTransport("refusal-twice")
    with pytest.raises(ExtractionError) as exc_info:
        run_slice(accountant, transport)
    assert "refused" in exc_info.value.message
    assert transport.calls == 2


def test_a_context_window_failure_is_hard_with_no_retry(accountant: Accountant) -> None:
    """At K = 5 this should be unreachable, so reaching it means a page constant is wrong —
    retrying an identical oversize request would only spend again."""
    transport = RecordedTransport("context-window-exceeded")
    with pytest.raises(ExtractionError) as exc_info:
        run_slice(accountant, transport)
    assert "context window" in exc_info.value.message
    assert transport.calls == 1


def test_a_truncated_response_is_reasked_once_at_the_raised_bound(accountant: Accountant) -> None:
    """Checked *before* schema validation: a truncated body is invalid JSON, and without this
    branch it would be retried identically three times, all paid, all truncating identically."""
    transport = RecordedTransport("truncated-then-success")
    result = run_slice(accountant, transport)
    assert len(result.pages) == 5
    assert transport.calls == 2
    assert transport.requests[0]["max_tokens"] < transport.requests[1]["max_tokens"]
    assert transport.requests[1]["max_tokens"] == MAX_TOKENS_RETRY


def test_a_second_truncation_is_a_failure(accountant: Accountant) -> None:
    transport = RecordedTransport("truncated-twice")
    with pytest.raises(ExtractionError) as exc_info:
        run_slice(accountant, transport)
    assert "truncated" in exc_info.value.message
    assert transport.calls == 2


def test_a_schema_failure_is_retried_and_recovers(accountant: Accountant) -> None:
    transport = RecordedTransport("schema-invalid-then-success")
    result = run_slice(accountant, transport)
    assert len(result.pages) == 5
    assert transport.calls == 2


def test_schema_retries_are_bounded(accountant: Accountant) -> None:
    transport = RecordedTransport("schema-invalid-exhausted")
    with pytest.raises(ExtractionError):
        run_slice(accountant, transport)
    assert transport.calls == SCHEMA_RETRIES + 1


def test_a_short_page_array_is_a_schema_failure(accountant: Accountant) -> None:
    """The failure no downstream check in this plan can detect. Four pages mapped positionally
    onto a five-page slice stores pages 2-5 under numbers 1-4: the spans still tile, the cache
    entry is still written, the order-free completeness audit cannot see a page shift — and every
    citation for that document is silently off by one, for good."""
    transport = RecordedTransport("short-page-array")
    result = run_slice(accountant, transport)
    assert transport.calls == 2, "the short array must be retried, never mapped"
    assert len(result.pages) == 5


def test_a_leaked_internal_tag_is_retried_never_stripped(accountant: Accountant) -> None:
    """Stripping would change the extracted text, which would then have to enter the fingerprint.
    `output_config.format` constrains structure, not what a string contains."""
    transport = RecordedTransport("tag-leaking")
    result = run_slice(accountant, transport)
    assert transport.calls == 2
    assert not any(LEAKED_TAG_PATTERN.search(page) for page in result.pages)


# --- the two retry budgets, which are not one --------------------------------------------------


def test_a_rate_limit_is_voided_and_retried_under_a_fresh_reservation(
    accountant: Accountant,
) -> None:
    """Never billed, so the reservation is released at zero. Without the void, a handful of 429s
    would permanently consume a monthly budget in an append-only file."""
    transport = RecordedTransport("rate-limited-then-success")
    result = run_slice(accountant, transport)
    assert len(result.pages) == 5

    states = [call.state for call in ledger_calls(accountant)]
    assert states == [CallState.VOIDED, CallState.RECONCILED]

    voided, reconciled = ledger_calls(accountant)
    assert voided.effective_eur == Decimal("0"), "the void consumed nothing"
    assert accountant.spent().day == reconciled.effective_eur


def test_transport_attempts_are_bounded_without_consuming_a_schema_retry(
    accountant: Accountant,
) -> None:
    """One shared counter is exactly what conflated these: two early 429s must not silently eat
    the schema-retry budget and refuse a legitimate retry, an outcome no test could tell from a
    genuine exhaustion."""
    transport = RecordedTransport("server-error-exhausted")
    with pytest.raises(TransportError):
        run_slice(accountant, transport)
    assert transport.calls == TRANSPORT_ATTEMPTS + 1
    assert all(call.state is CallState.VOIDED for call in ledger_calls(accountant))


def test_the_semantic_budget_refuses_a_seventh_call(accountant: Accountant) -> None:
    """Six token-billed calls per slice: one attempt, three schema retries, one refusal retry, one
    truncation retry. A seventh is refused rather than negotiated."""
    transport = RecordedTransport(
        "schema-invalid-exhausted", "schema-invalid-exhausted", "schema-invalid-exhausted"
    )
    with pytest.raises(ExtractionError):
        run_slice(accountant, transport)
    assert transport.calls <= SEMANTIC_CALL_BUDGET


def test_a_backoff_actually_waits_between_transport_attempts(accountant: Accountant) -> None:
    slept: list[float] = []
    transport = RecordedTransport("rate-limited-then-success")
    extract_slice(
        transport=transport,
        accountant=accountant,
        pdf_bytes=SLICE_BYTES,
        pages_in_slice=5,
        model=MODEL,
        reserved_eur=Decimal("0.04"),
        price=load_prices().for_model(MODEL),
        tally=CallTally(),
        sleep=slept.append,
    )
    assert slept and all(delay > 0 for delay in slept)


# --- billing, which is what the void rule is about ---------------------------------------------


def test_a_timeout_leaves_an_unknown_outcome_rather_than_a_void(accountant: Accountant) -> None:
    """The one failure that must NOT void. A timeout may or may not have billed — the server may
    have generated the response nobody saw — and recording €0 for it would under-count, the one
    direction a budget may never be wrong in."""
    transport = RecordedTransport("timeout")
    with pytest.raises(TransportError):
        run_slice(accountant, transport)

    calls = ledger_calls(accountant)
    assert [call.state for call in calls] == [CallState.UNKNOWN]
    assert accountant.spent().day == Decimal("0.04"), "it still consumes headroom"


def test_every_call_takes_its_own_reservation_and_ledger_pair(accountant: Accountant) -> None:
    """§5 requires reserving before *each* call, and a single reservation covering a retry loop is
    not a cap. Counted from the ledger against the transport's own call count."""
    transport = RecordedTransport("schema-invalid-exhausted")
    with pytest.raises(ExtractionError):
        run_slice(accountant, transport)
    assert len(ledger_calls(accountant)) == transport.calls


def test_a_call_that_would_breach_a_cap_is_never_made(
    make_fake_kb: Callable[..., Path],
) -> None:
    """The strongest assertion in the file: the spy sees zero calls. A budget that refuses *after*
    the request leaves is not a budget."""
    root = make_fake_kb(
        extraction_backend=CLAUDE_VISION,
        budget={"per_operation_eur": "0.01", "daily_eur": "0.01", "monthly_eur": "0.01"},
    )
    accountant = Accountant(load(root), prices=prices(), now=datetime.now(UTC))
    transport = RecordedTransport("happy-five-page-slice")

    with pytest.raises(BudgetRefusedError):
        run_slice(accountant, transport)
    assert transport.calls == 0
    assert ledger_calls(accountant) == []


def test_reservation_bounds_every_recorded_usage(accountant: Accountant) -> None:
    """The reservation is a *worst case*, so no fixture's actual usage may exceed it. Lives here
    rather than in I6a because it needs this increment's fixtures — and an exit criterion that
    depends on a later increment's artifacts is not an exit criterion."""
    from pinakes.budget.estimate import MAX_TOKENS, PROMPT_TOKENS

    for path in sorted(FIXTURES.glob("*.json")):
        for entry in load_fixture(path.stem)["responses"]:
            if entry.get("kind") != "response":
                continue
            usage = entry["usage"]
            assert usage["output_tokens"] <= MAX_TOKENS, path.name
            assert usage["input_tokens"] <= 5 * 6_000 + PROMPT_TOKENS, path.name


# --- parsing and assembly ----------------------------------------------------------------------


def test_parse_refuses_to_map_a_short_array_positionally() -> None:
    response = {"content": [{"type": "text", "text": '{"pages": [{"page": 1, "text": "a"}]}'}]}
    with pytest.raises(SchemaFailureError) as exc_info:
        parse_pages(response, expected=5)
    assert "refusing to map positionally" in str(exc_info.value)


def test_parse_selects_the_text_block_by_its_discriminator() -> None:
    response = {
        "content": [
            {"type": "thinking", "thinking": "ignored"},
            {"type": "text", "text": '{"pages": [{"page": 1, "text": "kept"}]}'},
        ]
    }
    assert parse_pages(response, expected=1) == ("kept",)


def test_normalise_runs_before_offsets() -> None:
    """Ligature expansion turns one codepoint into two, so offsets taken first would be out from
    the first ligature onward — while the spans still tiled perfectly and no property assertion
    could see it (I3a's own rule, asserted here against a second implementation of it)."""
    extracted = assemble_pages(["ﬁrst page", "second page"])
    assert extracted.text.startswith("first page")
    start, end = extracted.page_spans[0]
    assert extracted.text[start:end] == "first page"


def test_page_spans_tile_the_whole_text() -> None:
    extracted = assemble_pages(["one", "two", "three"])
    assert extracted.page_spans[0][0] == 0
    assert extracted.page_spans[-1][1] == len(extracted.text)
    # Deliberately uneven: each span is compared with the one after it, so the last has no pair.
    for (_, end), (next_start, _) in zip(
        extracted.page_spans, extracted.page_spans[1:], strict=False
    ):
        assert end == next_start


def test_every_pages_own_text_lands_inside_its_own_span() -> None:
    """The content-anchored property, against this backend's independent offset emission. A wrong
    paid page span produces a citation pointing at the wrong page with nothing revealing it."""
    pages = ["alpha content", "beta content", "gamma content"]
    extracted = assemble_pages(pages)
    for page, (start, end) in zip(pages, extracted.page_spans, strict=True):
        assert page in extracted.text[start:end]


def test_an_empty_page_gets_a_real_zero_width_span_in_place() -> None:
    extracted = assemble_pages(["first", "", "third"])
    start, end = extracted.page_spans[1]
    assert start == end
    assert extracted.page_spans[0][1] == start


# --- the fingerprint ----------------------------------------------------------------------------


def test_the_fingerprint_names_what_shapes_the_output_and_nothing_else() -> None:
    inputs = fingerprint_inputs(CLAUDE_VISION)
    assert inputs["slice_pages"] == "5"
    assert "text_policy_version" in inputs, "this backend runs normalise(), which changes the text"
    assert "pypdfium2_version" in inputs, "it slices with pdfium, so that version shapes the input"
    assert "layout_version" not in inputs, "it genuinely never runs layout.py (decision 15)"
    assert "max_tokens" not in inputs, "a budget knob; hashing it would change mid-run at a retry"


def test_changing_the_model_misses_the_cache() -> None:
    """The cache key is `<content_hash>-<fingerprint>`, so this *is* the cache-miss test: if the
    model does not enter the fingerprint, editing `[extraction] model` silently reuses text a
    different model produced, and nothing anywhere says so."""
    from pinakes.extract import fingerprint

    opus = fingerprint(CLAUDE_VISION, "claude-opus-5")
    other = fingerprint(CLAUDE_VISION, "some-other-model")
    assert opus != other
    assert fingerprint(CLAUDE_VISION, "claude-opus-5") == opus, "and it is stable"


def test_changing_k_misses_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """K is a semantic constant, not a tuning knob: a page transcribed with different neighbours
    is a different extraction, so the slice size has to be part of the key."""
    from pinakes.extract import claude as claude_module
    from pinakes.extract import fingerprint

    before = fingerprint(CLAUDE_VISION, MODEL)
    monkeypatch.setattr(claude_module, "K", 3)
    assert fingerprint(CLAUDE_VISION, MODEL) != before


def test_the_free_backends_fingerprint_ignores_the_model() -> None:
    """`pypdfium2` has no model, so threading one through must not perturb its key — otherwise
    every free KB's index would go stale the day this parameter was added."""
    from pinakes.extract import PYPDFIUM2, fingerprint

    assert fingerprint(PYPDFIUM2, "claude-opus-5") == fingerprint(PYPDFIUM2, None)


# --- the one test that needs a real key ----------------------------------------------------------


@pytest.mark.paid
@pytest.mark.skipif(
    not paid_runnable(),
    reason="needs anthropic, a key and PINAKES_ALLOW_SPEND=1 — it constructs a real client",
)
def test_the_real_client_disables_sdk_retries() -> None:
    """The other half of the split. The unmarked test above asserts the *value*; this asserts the
    client actually carries it — which the unmarked one cannot, since with `anthropic` absent the
    only thing it could inspect is a stand-in asserting a property of itself."""
    from pinakes.extract.claude import AnthropicTransport

    assert AnthropicTransport().max_retries == 0


# --- document level, which needs a real PDF -------------------------------------------------------


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_the_free_path_refuses_to_pay_for_a_healthy_pdf() -> None:
    """Paying to re-extract a PDF that already has a good text layer is the most likely way a user
    loses money by accident."""
    from pinakes.extract.claude import check_worth_paying_for

    with pytest.raises(ExtractionError) as exc_info:
        check_worth_paying_for(CORPUS / "baseline-12p.pdf", force=False)
    assert "already reads" in exc_info.value.message
    assert "--force" in exc_info.value.remedy


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_force_is_what_overrides_the_healthy_pdf_refusal() -> None:
    from pinakes.extract.claude import check_worth_paying_for

    survey = check_worth_paying_for(CORPUS / "baseline-12p.pdf", force=True)
    assert survey.pages_total == 12
    assert not survey.needs_the_paid_path


# --- `--estimate-only`, which must never generate ----------------------------------------------


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_estimate_only_makes_no_generation_call(
    make_fake_kb: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`count_tokens` measures; `messages.create` generates and bills. The whole value of the flag
    is that it does the first and never the second, so the spy counts both."""
    import shutil

    from pinakes.cli import EXIT_OK, main
    from pinakes.extract import claude as claude_module

    root = make_fake_kb(extraction_backend=CLAUDE_VISION)
    manifest_path = root / "pinakes.toml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            'include = ["**/*.md", "**/*.txt"]', 'include = ["**/*.pdf"]'
        ),
        encoding="utf-8",
    )
    shutil.copyfile(CORPUS / "baseline-12p.pdf", root / "docs" / "scan.pdf")

    transport = RecordedTransport("happy-five-page-slice")
    monkeypatch.setattr(claude_module, "default_transport", lambda: transport)

    assert main(["sync", "--kb", str(root), "--estimate-only"]) == EXIT_OK

    assert transport.calls == 0, "a generation call would have billed for output"
    assert transport.token_counts == 1
    out = capsys.readouterr().out
    assert "nothing was extracted" in out
    assert "12 page(s), 3 request(s)" in out


def test_estimate_only_refuses_a_free_backend(make_fake_kb: Callable[..., Path]) -> None:
    """ "Nothing to estimate" and "this run would cost nothing" are different answers, and only
    the first one is true on a free backend."""
    from pinakes.errors import SyncError
    from pinakes.sync import SyncOptions, sync

    root = make_fake_kb()
    with pytest.raises(SyncError) as exc_info:
        sync(load(root), options=SyncOptions(estimate_only=True))
    assert "nothing to estimate" in exc_info.value.message


# --- the confirmation, evaluated once against the whole document -------------------------------


def test_a_confirmation_is_owed_once_for_a_document_not_once_per_call(
    make_fake_kb: Callable[..., Path],
) -> None:
    """A per-call reading against a several-cent slice would prompt dozens of times for one
    multi-page document, which is how a confirmation becomes something a user holds `y` through."""
    from pinakes.budget.estimate import estimate_document

    root = make_fake_kb(
        extraction_backend=CLAUDE_VISION,
        budget={
            "confirm_above_eur": "0.01",
            "per_operation_eur": "50.00",
            "daily_eur": "50.00",
            "monthly_eur": "50.00",
        },
    )
    asked: list[str] = []
    accountant = Accountant(
        load(root),
        prices=prices(),
        now=datetime.now(UTC),
        interactive=True,
        ask=lambda prompt: (asked.append(prompt), "y")[1],
    )
    estimate = estimate_document(
        pages=12,
        model=MODEL,
        prices=prices(),
        now=datetime.now().strftime("%Y%m%d %H:%M"),
        max_price_age_days=30,
    )
    decision = accountant.check_document(estimate)
    assert decision.needs_confirmation
    assert accountant.confirm_document(decision, estimate.total_eur)
    assert len(asked) == 1, "one question for the whole document"


def test_yes_answers_the_documents_confirmation(make_fake_kb: Callable[..., Path]) -> None:
    from pinakes.budget.reserve import DocumentDecision

    root = make_fake_kb(extraction_backend=CLAUDE_VISION)
    accountant = Accountant(
        load(root), prices=prices(), now=datetime.now(UTC), interactive=False, yes=True
    )
    decision = DocumentDecision(allowed=True, needs_confirmation=True)
    assert accountant.confirm_document(decision, Decimal("0.40"))


def test_the_cap_is_rechecked_before_every_transport_attempt(
    make_fake_kb: Callable[..., Path],
) -> None:
    """§5 says reserve before *each* call, and this is why it is not merely tidy: between a 429
    and its backoff, another process syncing the same KB can spend the remaining headroom. A check
    hoisted out of the retry loop would let the retry go out anyway — the loop's own attempts all
    void at zero, so nothing *inside* it moves the total and the omission looks harmless."""
    root = make_fake_kb(
        extraction_backend=CLAUDE_VISION,
        budget={"per_operation_eur": "50.00", "daily_eur": "0.05", "monthly_eur": "50.00"},
    )
    accountant = Accountant(load(root), prices=prices(), now=datetime.now(UTC))

    def somebody_else_spends(call_number: int) -> None:
        if call_number != 1:
            return
        other = Accountant(load(root), prices=prices(), now=datetime.now(UTC))
        with other.paid_call(model=MODEL, reserved_eur=Decimal("0.04")) as call:
            call.response_received()
            call.reconcile(cost_usd=Decimal("0.0432"))

    transport = RecordedTransport("rate-limited-then-success", on_call=somebody_else_spends)
    with pytest.raises(BudgetRefusedError):
        run_slice(accountant, transport)
    assert transport.calls == 1, "the retry must never leave, because the day cap is gone"


def test_the_semantic_budget_is_per_slice_not_per_document(accountant: Accountant) -> None:
    """A document-wide counter would let slice 1's retries refuse slice 2 its *first* attempt —
    silently, as an extraction failure indistinguishable from a genuine exhaustion. The tally is
    pre-loaded here with an earlier slice's calls, which is exactly what slice 2 sees."""
    already_spent = CallTally(calls=SEMANTIC_CALL_BUDGET - 1)
    transport = RecordedTransport("schema-invalid-exhausted")

    with pytest.raises(ExtractionError):
        run_slice(accountant, transport, tally=already_spent)

    assert transport.calls == SCHEMA_RETRIES + 1, (
        "this slice gets its own full budget regardless of what earlier slices used"
    )


def test_the_reconciliation_supersedes_with_the_real_cost_not_the_reservation(
    accountant: Accountant,
) -> None:
    """The reservation is a worst case; the reconciliation is what corrects it. Recording the
    reserved amount again would leave the protocol looking complete while charging every window
    worst-case forever — `pnk budget` reporting an estimate as if it were spend, with a
    reconciliation record present to make it look settled."""
    from pinakes.extract.claude import actual_cost_usd

    transport = RecordedTransport("happy-five-page-slice")
    run_slice(accountant, transport)

    (call,) = ledger_calls(accountant)
    assert call.state is CallState.RECONCILED
    assert call.outcome is not None

    expected = actual_cost_usd(transport.entries[0], price=load_prices().for_model(MODEL))
    assert call.outcome.cost_usd == quantise(expected)
    assert call.outcome.cost_usd != call.reservation.cost_usd, (
        "an outcome identical to its reservation means nothing was reconciled"
    )
    # Derived from the response's own usage, not from anything the caller reserved. (The
    # reservation here is an arbitrary test constant, so comparing the two magnitudes would assert
    # a property of the fixture rather than of the code.)
    assert call.outcome.input_tokens == 30_300
    assert call.effective_eur == call.outcome.cost_eur


def test_a_transport_failure_is_a_document_failure_not_a_crashed_run() -> None:
    """`sync` isolates each document behind `except (PinakesError, OSError, ValueError)`. A
    transport error outside that hierarchy would take a 1,000-document corpus down over one PDF,
    which is precisely the isolation §6.4 promises."""
    from pinakes.errors import PinakesError
    from pinakes.extract.claude import RequestTooLargeError

    transport_error = TransportError(
        "boom", billability=Billability.NOT_BILLED, retryable=False, status=500
    )
    assert isinstance(transport_error, PinakesError)
    assert transport_error.remedy

    too_large = RequestTooLargeError(encoded_bytes=MAX_REQUEST_BYTES + 1, pages=5)
    assert isinstance(too_large, PinakesError)
    assert too_large.remedy


def test_estimate_only_needs_no_key_when_there_is_nothing_to_estimate(
    make_fake_kb: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A KB with no PDFs has nothing to price, so it has no business demanding an API key —
    building the transport up front would make `--estimate-only` fail on a KB it should simply
    report nothing about."""
    from pinakes.extract import claude as claude_module
    from pinakes.sync import SyncOptions, sync

    def refuse() -> Any:
        raise AssertionError("no transport should be built when no PDF would be extracted")

    monkeypatch.setattr(claude_module, "default_transport", refuse)
    root = make_fake_kb(extraction_backend=CLAUDE_VISION)

    report = sync(load(root), options=SyncOptions(estimate_only=True))
    assert report.estimates == ()


# --- the document loop, where the slice windows actually meet a real PDF ------------------------


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_document_whose_page_count_is_not_a_multiple_of_k(accountant: Accountant) -> None:
    """12 pages at K = 5 is 5 + 5 + 2. The short final slice is where an off-by-one in the window
    arithmetic would either drop pages or — the expensive one — send the whole document."""
    from pinakes.extract.claude import extract_document, slice_windows

    assert slice_windows(12) == [(0, 4), (5, 9), (10, 11)]

    transport = RecordedTransport(
        "happy-five-page-slice", "happy-five-page-slice", "short-final-slice"
    )
    extracted, tally = extract_document(
        CORPUS / "baseline-12p.pdf",
        transport=transport,
        accountant=accountant,
        model=MODEL,
        pages_total=12,
        force=True,  # the corpus PDF is healthy by design
        sleep=never_sleeps,
    )

    assert transport.calls == 3
    assert len(extracted.page_spans) == 12
    assert extracted.page_spans[-1][1] == len(extracted.text)
    assert len(tally.call_ids) == 3
    assert len(ledger_calls(accountant)) == 3
    # Each request really did carry its own slice, not the whole document over and over.
    assert (
        len(
            {
                request["messages"][0]["content"][0]["source"]["data"]
                for request in transport.requests
            }
        )
        == 3
    )


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_an_oversize_slice_is_halved_rather_than_shrinking_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reducing K is deliberately not an option — K is hashed into the fingerprint, so a smaller
    slice would silently be a *different* extraction. The slice is halved instead."""
    import base64

    from pinakes.extract import claude as claude_module
    from pinakes.extract.pdfium import slice_pages

    # Sized from the document itself: a hard-coded threshold either never splits or recurses
    # straight to the single-page failure, and which one it does would be a property of this
    # fixture rather than of the code.
    def encoded(first: int, last: int) -> int:
        return len(base64.standard_b64encode(slice_pages(CORPUS / "baseline-12p.pdf", first, last)))

    two_pages, five_pages = encoded(0, 1), encoded(0, 4)
    assert two_pages < five_pages, "the corpus fixture must grow with its page count"
    monkeypatch.setattr(claude_module, "MAX_REQUEST_BYTES", (two_pages + five_pages) // 2)

    pieces = claude_module.slice_bytes(CORPUS / "baseline-12p.pdf", 0, 4, pages_in_slice=5)
    assert len(pieces) > 1, "it must split rather than send an oversize request"
    assert sum(pages for _bytes, pages in pieces) == 5, "and no page may be lost in the split"


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_single_page_that_is_still_too_large_fails_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pinakes.extract import claude as claude_module

    monkeypatch.setattr(claude_module, "MAX_REQUEST_BYTES", 10)
    with pytest.raises(ExtractionError) as exc_info:
        claude_module.slice_bytes(CORPUS / "baseline-12p.pdf", 0, 0, pages_in_slice=1)
    assert "page 1" in exc_info.value.message
    assert "baseline-12p.pdf" in exc_info.value.message


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_with_no_fitted_floor_the_paid_path_refuses_to_spend_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A paid path running with its own cost-control check disabled is worse than one that does
    not run: the check exists to stop the most likely accidental spend, so its absence is a
    refusal, never a shrug."""
    from pinakes.errors import FloorsMissingError
    from pinakes.extract import claude as claude_module

    def no_floors() -> Any:
        raise FloorsMissingError(reason="floors.toml is missing")

    monkeypatch.setattr(claude_module, "load_floors", no_floors)
    with pytest.raises(FloorsMissingError):
        claude_module.check_worth_paying_for(CORPUS / "baseline-12p.pdf", force=False)
    # `--force` must not buy a way past a *missing guard*, only past a healthy-PDF refusal.
    with pytest.raises(FloorsMissingError):
        claude_module.check_worth_paying_for(CORPUS / "baseline-12p.pdf", force=True)


# --- the whole wiring, in one test ---------------------------------------------------------------


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_real_sync_extracts_indexes_records_and_caches(
    make_fake_kb: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everything above tests a piece. This drives `pnk sync` itself, because the pieces were
    wired together across four modules and "each part works" is not the same claim as "the parts
    are connected" — which is exactly the seam an increment is most likely to get wrong."""
    import json as json_module
    import shutil

    from pinakes import store
    from pinakes.cli import EXIT_OK, main
    from pinakes.extract import (
        CLAUDE_VISION,
        ExtractorEntry,
        register_extractor,
        registered_entry,
    )
    from pinakes.extract import claude as claude_module
    from pinakes.extract.claude import ClaudeVisionExtractor

    root = make_fake_kb(
        extraction_backend=CLAUDE_VISION,
        budget={"per_operation_eur": "50.00", "daily_eur": "50.00", "monthly_eur": "50.00"},
    )
    manifest_path = root / "pinakes.toml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            'include = ["**/*.md", "**/*.txt"]', 'include = ["**/*.pdf"]'
        ),
        encoding="utf-8",
    )
    shutil.copyfile(CORPUS / "baseline-1p.pdf", root / "docs" / "scan.pdf")

    transport = RecordedTransport("short-final-slice")  # one slice, and this PDF has one page
    transport.entries[0]["content"] = [
        {"type": "text", "text": json_module.dumps({"pages": [{"page": 1, "text": "paid text"}]})}
    ]
    original = claude_module.default_transport
    # Captured and re-registered, never unregistered: `unregister_extractor` deletes, and deleting
    # a name the package registers at import leaves every later test in the session without it.
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
        # `--force`: the corpus PDF is healthy by design, so the free-yield guard would refuse it.
        assert main(["sync", "--kb", str(root), "--force", "--yes"]) == EXIT_OK
    finally:
        register_extractor(CLAUDE_VISION, original_entry)
        claude_module.default_transport = original

    assert transport.calls == 1

    connection = store.connect_ro(root / ".pinakes" / "index.db")
    try:
        rows = connection.execute(
            "SELECT path, extraction_backend FROM documents WHERE state = 'active'"
        ).fetchall()
    finally:
        connection.close()
    assert [(str(r["path"]), str(r["extraction_backend"])) for r in rows] == [
        ("docs/scan.pdf", CLAUDE_VISION)
    ]

    # The ledger recorded the call, reconciled.
    ledger = resolve(read(ledger_path(root / ".pinakes")).records).calls
    assert [call.state for call in ledger] == [CallState.RECONCILED]

    # And the cache entry carries the join key back to it — the `null` §6.3 left open until now.
    entries = list((root / ".pinakes" / "cache" / "extract").glob("*.json"))
    assert len(entries) == 1
    cached: Any = json_module.loads(entries[0].read_text(encoding="utf-8"))
    assert cached["operation_id"]
    assert cached["call_ids"] == [ledger[0].call_id]


# --- staging: what an interrupted run must not pay for twice ------------------------------------


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_resumed_run_re_asks_nothing_that_was_staged(
    accountant: Accountant, tmp_path: Path
) -> None:
    """The whole reason staging exists. A 12-page document is three slices; if the first two
    survived an earlier run, a resume must pay for the third and only the third — counted from
    the transport, not inferred from the absence of an error."""
    from pinakes.extract.claude import extract_document

    staging = tmp_path / "partial"
    # Two slices land, the third times out — a real interruption rather than a contrived one, and
    # one the caller isolates as a document failure.
    first_run = RecordedTransport("happy-five-page-slice", "happy-five-page-slice", "timeout")
    with pytest.raises(TransportError):
        extract_document(
            CORPUS / "baseline-12p.pdf",
            transport=first_run,
            accountant=accountant,
            model=MODEL,
            pages_total=12,
            force=True,
            staging=staging,
            sleep=never_sleeps,
        )
    assert first_run.calls == 3
    assert sorted(staged_pages(staging)) == list(range(10)), "two slices staged, ten pages"

    resumed = RecordedTransport("short-final-slice")
    extracted, tally = extract_document(
        CORPUS / "baseline-12p.pdf",
        transport=resumed,
        accountant=accountant,
        model=MODEL,
        pages_total=12,
        force=True,
        staging=staging,
        sleep=never_sleeps,
    )
    assert resumed.calls == 1, "the ten staged pages must cost nothing at all"
    assert tally.calls == 1
    assert len(extracted.page_spans) == 12


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_slice_interrupted_mid_flight_is_re_asked_whole(
    accountant: Accountant, tmp_path: Path
) -> None:
    """Resume granularity is the slice, never the page: its pages were transcribed together, and
    a page transcribed with different neighbours is a different extraction."""
    from pinakes.extract.claude import extract_document

    staging = tmp_path / "partial"
    # Three of slice 1's five pages staged — as if it had been killed part-way through writing.
    for page in range(3):
        stage_page(staging, page=page, text=f"partial page {page}")

    transport = RecordedTransport(
        "happy-five-page-slice", "happy-five-page-slice", "short-final-slice"
    )
    extract_document(
        CORPUS / "baseline-12p.pdf",
        transport=transport,
        accountant=accountant,
        model=MODEL,
        pages_total=12,
        force=True,
        staging=staging,
        sleep=never_sleeps,
    )
    assert transport.calls == 3, "the partially staged slice is re-asked whole, not topped up"


@pytest.mark.pdf
@pytest.mark.skipif(not pdf_extraction_runnable(), reason="pinakes[pdf] not installed")
def test_a_partially_extracted_document_writes_no_complete_entry(
    make_fake_kb: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A half-extracted document in the index is the silent truncation the design exists to
    prevent, so it writes nothing and goes to `failures` — while its staged pages survive, which
    is what makes the next run cheap rather than merely correct."""
    import shutil

    from pinakes.extract import (
        CLAUDE_VISION,
        ExtractorEntry,
        register_extractor,
        registered_entry,
    )
    from pinakes.extract import claude as claude_module
    from pinakes.extract.cache import staging_dir
    from pinakes.extract.claude import ClaudeVisionExtractor
    from pinakes.manifest import load as load_manifest
    from pinakes.sync import SyncOptions, sync

    root = make_fake_kb(
        extraction_backend=CLAUDE_VISION,
        budget={"per_operation_eur": "50.00", "daily_eur": "50.00", "monthly_eur": "50.00"},
    )
    path = root / "pinakes.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'include = ["**/*.md", "**/*.txt"]', 'include = ["**/*.pdf"]'
        ),
        encoding="utf-8",
    )
    shutil.copyfile(CORPUS / "baseline-12p.pdf", root / "docs" / "scan.pdf")

    # Two slices succeed, the third times out: the run dies part-way through the document.
    transport = RecordedTransport("happy-five-page-slice", "happy-five-page-slice", "timeout")
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
    try:
        report = sync(load_manifest(root), options=SyncOptions(force=True, yes=True))
    finally:
        register_extractor(CLAUDE_VISION, original_entry)

    assert not report.ok
    assert [failure[0] for failure in report.failures] == ["docs/scan.pdf"]

    cache_dir = root / ".pinakes" / "cache" / "extract"
    assert list(cache_dir.glob("*.json")) == [], "no complete entry for a partial document"

    manifest = load_manifest(root)
    surviving = staging_dir(
        cache_dir,
        content_hash=hash_file(root / "docs" / "scan.pdf"),
        fingerprint=extraction_fingerprint(CLAUDE_VISION, manifest.extraction.model),
    )
    assert len(staged_pages(surviving)) == 10, "the staged pages survive for the next run"
