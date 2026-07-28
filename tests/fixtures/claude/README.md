# Claude-vision response fixtures

One file per branch `extract/claude.py` can take. Each is a *script*: the responses (and transport
failures) a single slice's call sequence receives, in order. `tests/test_extract_claude.py` replays
them through the `Transport` seam, so the whole extractor — every retry, every reservation, every
ledger pair — is exercised with `anthropic` not installed at all.

## Provenance, stated plainly

**These are hand-authored to the documented response shape, not captured from the live API.** No
run against a real key has happened yet; `plans/v0.2.md` I7b lists that as a human-gated exit
criterion, and it is the step that replaces these bodies with genuine recordings.

That distinction matters, so it is written here rather than implied by the word "recorded": a
fixture authored from a spec can only be as right as the spec, and the failure it cannot catch is
the API behaving differently from its documentation. What these fixtures *do* prove is the thing
they were written for — that each branch exists, is reachable, and does what the plan says when it
is reached. Two independent things, and only one of them is settled.

Every page body is synthetic. **No real knowledge-base content, and nothing from any live
document, is ever committed here** (CLAUDE.md: this repository is public).

## The scripts

| File | Branch | What it exercises |
|---|---|---|
| `happy-five-page-slice` | happy | The shape every other case departs from |
| `short-final-slice` | short-slice | A document whose page count is not a multiple of K |
| `refusal-then-success` | refusal | `stop_reason: refusal`, checked **before** `content` is read — the cheap failure, retried once |
| `refusal-twice` | refusal | The second refusal is recorded, not retried again |
| `schema-invalid-then-success` | schema-invalid | Prose where JSON was required, then recovery |
| `schema-invalid-exhausted` | schema-invalid | One attempt plus three retries, then recorded |
| `truncated-then-success` | truncated | `stop_reason: max_tokens`, re-asked once at the raised bound |
| `truncated-twice` | truncated | Truncated at both bounds — recorded, never retried a third time |
| `context-window-exceeded` | context-window | A hard failure with **no** retry: re-sending an identical oversize request only spends again |
| `short-page-array` | content-dropping | Four pages for a five-page slice. The most dangerous body in the set — mapped positionally it shifts every page's text, spans still tile, and no downstream check can see it |
| `tag-leaking` | tag-leaking | Schema-valid, but a page carries a `<thinking>` fragment: `output_config.format` constrains structure, never string content |
| `rate-limited-then-success` | 429 | Never billed → the reservation is **voided**, and the retry takes a fresh one |
| `server-error-exhausted` | 500 | The initial attempt plus both transport backoffs, all voided |
| `timeout` | timeout | Billable-unknown → the reservation is left **open**, never voided |

## Format

```json
{
  "name": "…", "branch": "…", "why": "…",
  "responses": [
    {"kind": "response", "stop_reason": "end_turn", "model": "…", "content": [ … ], "usage": { … }},
    {"kind": "error", "class": "status", "status": 429},
    {"kind": "error", "class": "timeout"}
  ]
}
```

`kind: "error"` replays a transport failure rather than a response — `class` is `status`
(with a `status` code), `timeout`, or `connection`. A script that runs out of entries is a test
bug, and the replayer says so rather than returning something plausible.
