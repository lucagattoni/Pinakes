"""Capture `tests/fixtures/claude/` bodies from the live API.

**This script spends real money and needs a real key.** It is a developer tool, never a product
entry point: no `pnk` subcommand reaches it, no test imports it, and CI never runs it. That is why
it lives under `tools/` rather than `src/` — the paid-path allowlist (docs/INVARIANTS.md,
`.paid-path-allowlist`) enumerates what a
*user* running `pnk` can trigger, and gate 2 scans `src/` only. Run it exactly as the measurement
run is run:

    uv run --frozen --env-file .env python tools/record_claude_fixtures.py --scenario happy

**Why this exists at all.** Every fixture was authored from the API's *documented* response shape.
A fixture authored from a spec can only be as right as the spec, and the failure it cannot catch is
the API behaving differently from its documentation (`tests/fixtures/claude/README.md`). This
replaces that reading with a recording, for the branches a recording can reach.

**The branches it deliberately cannot reach.** `schema-invalid`, `content-dropping`, `tag-leaking`,
`429`, `500` and `timeout` encode the API *misbehaving* — a body that violates the schema it was
constrained to, a page array short of the slice, an internal tag leaking into a constrained string,
a transport failure. None can be ordered on demand, and forcing a 429 means hammering a live
service, which is abuse rather than measurement. Those fixtures stay authored, and the README says
so per-fixture with the reason — the honest split, rather than a blanket disclaimer over a set that
is now half evidence.

Recorded bodies are the transport's return value verbatim, extra fields included: the point is
fidelity to what the API really sends, so a field nobody reads today is still evidence tomorrow.
Every page body comes from `tests/pdf-corpus/`, which is synthetic by construction — no real
knowledge-base content can reach a fixture this way (CLAUDE.md: this repository is public).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "tests" / "pdf-corpus"
FIXTURES = REPO / "tests" / "fixtures" / "claude"

MODEL = "claude-opus-5"


def _slice_of(pdf: str, first: int, last: int) -> tuple[bytes, int]:
    """Bytes for pages [first, last] (inclusive, 0-indexed) through the extractor's own slicer.

    `slice_bytes` may split an oversized slice into several chunks; a recording that silently used
    only the first would be a fixture for a request the extractor never makes, so anything but one
    chunk is refused rather than truncated.
    """
    from pinakes.extract.claude import slice_bytes

    pages = last - first + 1
    chunks = slice_bytes(CORPUS / pdf, first, last, pages_in_slice=pages)
    if len(chunks) != 1:
        raise SystemExit(
            f"{pdf}[{first}:{last}] split into {len(chunks)} chunks — too large to record as "
            "one slice; pick a smaller page range."
        )
    return chunks[0]


class Recorder:
    """Wraps the real transport and keeps every response, in order.

    Errors are captured in the *fixture's* vocabulary — `class` plus `status` — rather than as a
    traceback, because that is what `_replay_error` in the test suite consumes. The classification
    is the extractor's own `TransportError`, so what gets recorded is what the extractor concluded,
    not what this script guessed.
    """

    def __init__(self) -> None:
        from pinakes.extract.claude import AnthropicTransport

        self.inner = AnthropicTransport()
        self.entries: list[dict[str, Any]] = []

    def create(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        from pinakes.extract.claude import Billability, TransportError

        try:
            response = self.inner.create(request)
        except TransportError as exc:
            entry: dict[str, Any] = {"kind": "error"}
            if exc.status is not None:
                entry["class"], entry["status"] = "status", exc.status
            elif exc.billability is Billability.UNKNOWN:
                entry["class"] = "timeout"
            else:
                entry["class"] = "connection"
            self.entries.append(entry)
            raise
        recorded = {"kind": "response", **dict(response)}
        self.entries.append(recorded)
        return response


def _call(rec: Recorder, pdf: str, first: int, last: int, *, max_tokens: int | None = None) -> None:
    """One billed call.

    Failures are recorded and swallowed — a refusal or a 400 IS the recording.
    """
    from pinakes.extract.claude import MAX_TOKENS, TransportError, build_request

    payload, pages = _slice_of(pdf, first, last)
    request = build_request(
        model=MODEL,
        pdf_bytes=payload,
        pages_in_slice=pages,
        max_tokens=MAX_TOKENS if max_tokens is None else max_tokens,
    )
    try:
        rec.create(request)
    except TransportError as exc:
        print(f"  transport error recorded: {exc}", file=sys.stderr)


def _happy(rec: Recorder) -> None:
    _call(rec, "baseline-12p.pdf", 0, 4)


def _short_final(rec: Recorder) -> None:
    _call(rec, "baseline-12p.pdf", 10, 11)


def _refusal_twice(rec: Recorder) -> None:
    for _ in range(2):
        _call(rec, "headers-repeating.pdf", 0, 4)


def _truncated_then_success(rec: Recorder) -> None:
    _call(rec, "baseline-12p.pdf", 0, 4, max_tokens=32)
    _call(rec, "baseline-12p.pdf", 0, 4)


@dataclass(frozen=True)
class Scenario:
    branch: str
    why: str
    #: What was sent, in the words the fixture's provenance will carry.
    source: str
    drive: Callable[[Recorder], None]


#: One entry per branch a recording can actually reach. The branches deliberately absent are listed
#: in the module docstring, with the reason each cannot be recorded.
SCENARIOS: dict[str, Scenario] = {
    "happy-five-page-slice": Scenario(
        "happy",
        "A clean five-page slice — the shape every other case departs from.",
        "tests/pdf-corpus/baseline-12p.pdf, pages 1-5",
        _happy,
    ),
    "short-final-slice": Scenario(
        "short-slice",
        "A document whose page count is not a multiple of K: the trailing two-page slice.",
        "tests/pdf-corpus/baseline-12p.pdf, pages 11-12",
        _short_final,
    ),
    "refusal-twice": Scenario(
        "refusal",
        "Two refusals: retried once, then recorded as a failure.",
        "tests/pdf-corpus/headers-repeating.pdf, pages 1-5, sent twice",
        _refusal_twice,
    ),
    "truncated-then-success": Scenario(
        "truncated",
        "`stop_reason: max_tokens` at the first bound, then the same slice at the raised one.",
        "tests/pdf-corpus/baseline-12p.pdf, pages 1-5, at max_tokens=32 then the shipped bound",
        _truncated_then_success,
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    parser.add_argument(
        "--out", type=Path, default=None, help="where to write (default: the fixture itself)"
    )
    parser.add_argument(
        "--at",
        required=True,
        help="UTC 'YYYYMMDD HH:MM' of this recording — read off the clock (`date -u`), never "
        "composed (docs/README.md § Conventions: an invented HH:MM lands in the future about "
        "half the time)",
    )
    args = parser.parse_args()

    scenario = SCENARIOS[args.scenario]
    rec = Recorder()
    print(f"recording {args.scenario} ({scenario.branch}) — this spends", file=sys.stderr)
    scenario.drive(rec)

    out = args.out or (FIXTURES / f"{args.scenario}.json")
    body = {
        "name": args.scenario,
        "branch": scenario.branch,
        "why": scenario.why,
        "provenance": {
            "kind": "recorded",
            "at": args.at,
            "model": MODEL,
            "source": scenario.source,
        },
        "responses": rec.entries,
    }
    out.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} — {len(rec.entries)} entries", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
