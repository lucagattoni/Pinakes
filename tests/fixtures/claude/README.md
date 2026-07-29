# Claude-vision response fixtures

One file per branch `extract/claude.py` can take. Each is a *script*: the responses (and transport
failures) a single slice's call sequence receives, in order. `tests/test_extract_claude.py` replays
them through the `Transport` seam, so the whole extractor — every retry, every reservation, every
ledger pair — is exercised with `anthropic` not installed at all.

## Provenance, stated per fixture

**This set is half evidence and half construction, and every file says which it is.** Each carries
a `provenance` block: `recorded` names when, which model, and what was sent; `authored` names why a
recording is not obtainable. A blanket disclaimer used to stand here instead, and it was replaced
the moment four branches were recorded live — a single claim over a mixed set is wrong about every
fixture it does not describe.

That distinction decides what a fixture can prove. A recorded body is evidence about the API. An
authored body proves only that the branch exists, is reachable, and does what the plan says when it
is reached — which is worth having, and is not the same thing.

Recorded bodies are the transport's return value **verbatim**, extra fields included. The extractor
reads a handful of keys; the rest are kept because a field nobody reads today is still evidence
tomorrow.

Every page body comes from `tests/pdf-corpus/`, which is synthetic by construction. **No real
knowledge-base content, and nothing from any live document, is ever committed here** (CLAUDE.md:
this repository is public).

### Recorded — 20260729 03:36, `claude-opus-5`

Captured by [`tools/record_claude_fixtures.py`](../../../tools/record_claude_fixtures.py), which
spends real money and is never run by `pnk`, by a test, or by CI.

| File | Branch | What it exercises |
|---|---|---|
| `happy-five-page-slice` | happy | The shape every other case departs from |
| `short-final-slice` | short-slice | A document whose page count is not a multiple of K |
| `refusal-twice` | refusal | The second refusal is recorded, not retried again |
| `truncated-then-success` | truncated | `stop_reason: max_tokens`, re-asked once at the raised bound |

**What recording changed.** The authored bodies were right about every branch's *control flow* and
wrong about the response shape in five ways, none of which a passing test could have revealed:

- the API returns `model: "claude-opus-5"` — the alias, not the dated snapshot the fixtures assumed;
- a text block carries a `citations` field;
- a response carries `id`, `role`, `type`, `container`, `stop_sequence` and `stop_details`;
- `usage` carries seven more fields than `input_tokens`/`output_tokens`, including
  `output_tokens_details.thinking_tokens: 0` — which is the request's `thinking: disabled` being
  confirmed by the server rather than assumed;
- a refusal bills **1** output token, not 0.

The sixth finding had a defect behind it: a refusal arrives with a structured `stop_details` giving
a `category` and an `explanation`, and the extractor discarded both, leaving an operator with a
bare "the model refused the request". `_refusal_reason` now surfaces them.

### Authored — and why a recording is not obtainable

These encode the API *misbehaving*, or a failure that cannot be induced without abusing a live
service. Each file's `provenance.why_not_recorded` carries the full reason; the short form:

| File | Branch | Why it cannot be recorded |
|---|---|---|
| `refusal-then-success` | refusal | A refusal followed by a success **has never been observed** — the same bytes refused twice, identically |
| `schema-invalid-then-success` | schema-invalid | The API cannot be asked to violate the schema it was constrained to |
| `schema-invalid-exhausted` | schema-invalid | As above, four times running |
| `truncated-twice` | truncated | Needs an output over 16,000 tokens; no corpus page produces one |
| `context-window-exceeded` | context-window | `MAX_REQUEST_BYTES` refuses the request first — the branch guards a pinakes defect, not an API behaviour |
| `short-page-array` | content-dropping | Requires the model to drop a page. The most dangerous body in the set, and nothing can provoke it |
| `tag-leaking` | tag-leaking | `output_config.format` constrains structure, never string content — the leak cannot be requested |
| `rate-limited-then-success` | 429 | Forcing a 429 means hammering a live service: abuse, not measurement |
| `server-error-exhausted` | 500 | A fault in someone else's service |
| `timeout` | timeout | The classification it drives is asserted directly against the SDK hierarchy in `stubs/anthropic.pyi` |

`refusal-then-success` deserves its line read twice. The live evidence is that a refusal is a
deterministic decision on fixed input, so the retry this fixture models may well never succeed in
practice. That is n=1 on one document — enough to record, not enough to change what the code spends.

## Format

```json
{
  "name": "…", "branch": "…", "why": "…",
  "provenance": {"kind": "recorded", "at": "YYYYMMDD HH:MM", "model": "…", "source": "…"},
  "responses": [
    {"kind": "response", "stop_reason": "end_turn", "model": "…", "content": [ … ], "usage": { … }},
    {"kind": "error", "class": "status", "status": 429},
    {"kind": "error", "class": "timeout"}
  ]
}
```

An authored fixture carries `{"kind": "authored", "why_not_recorded": "…"}` instead.

`kind: "error"` replays a transport failure rather than a response — `class` is `status`
(with a `status` code), `timeout`, or `connection`. A script that runs out of entries is a test
bug, and the replayer says so rather than returning something plausible.

## Re-recording

```bash
uv run --frozen --env-file .env python tools/record_claude_fixtures.py \
    --scenario happy-five-page-slice --at "$(date '+%Y%m%d %H:%M')"
```

`--at` is required and has no default: the timestamp is read off the clock, never composed
(CLAUDE.md — an invented `HH:MM` lands in the future about half the time).
