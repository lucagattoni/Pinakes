"""Fetch RFCs and build a Pinakes KB from them — the realism corpus, as a script rather than a
directory nobody else has.

**Why this exists as a script and not as committed fixtures.** This repository is public and its
rule is that the only KBs in it are synthetic and written for the purpose, never harvested
(`CLAUDE.md`). So the corpus that produced this project's most useful findings — 300 RFCs, 106 806
chunks, every `heading_path` empty — lived on one machine and died with it, which is why that
measurement cannot be re-run today and its verdict is correspondingly hard to revisit. A script is
the version of it that survives: nothing harvested is committed, and anyone can regenerate the
corpus from a recorded list.

**It writes outside the repository by default** (`--out`), and never into `tests/`. A KB built here
must not become a fixture by accident.

**Reproducibility is bounded, and the bound is worth stating.** RFCs are immutable once published,
so the *documents* are stable. Their rendering is not: the pre-2019 corpus was produced by nroff and
the current one by xml2rfc, and the two differ in ways a heading grammar notices. `--era` picks a
band deliberately rather than leaving it to whichever numbers happen to get chosen, and the manifest
of what was fetched is written into the output directory so a later run can be compared with an
earlier one rather than merely repeated.

Usage:

    python3 tools/build_rfc_corpus.py --out ~/rfc-kb --count 60 --era modern
    python3 tools/build_rfc_corpus.py --out ~/rfc-kb --rfcs 791,793,2616

Downloads are cached under `<out>/.cache` and reused, so re-running costs nothing and a partial run
resumes rather than refetching.

Then, from the KB:

    uv run pnk sync --kb ~/rfc-kb --rebuild
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Sequence
from pathlib import Path

RFC_URL = "https://www.rfc-editor.org/rfc/rfc{number}.txt"

ERAS: dict[str, tuple[int, int]] = {
    # Bands, not samples: a contiguous range is reproducible from two numbers, where "40 RFCs I
    # liked" is not. Both ends are inclusive.
    "early": (760, 1400),  # nroff era, 1980s to early 90s
    "classic": (2000, 3000),  # the RFC 2616 generation
    "modern": (8600, 9300),  # xml2rfc output, the format most current documents use
}
"""Rendering changed under these documents over four decades. A grammar measured against one band
has been measured against one band, and saying which is the difference between a result and an
anecdote."""

POLITE_DELAY_SECONDS = 0.5
"""A courtesy to rfc-editor.org, which owes this project nothing. Not a rate limit anyone published
— just enough that a 300-document run is not a burst."""


def rfc_numbers(*, era: str, count: int, start: int | None) -> list[int]:
    """A contiguous block, so the selection is reproducible from its arguments alone.

    Not random and not "interesting" ones: a corpus chosen for interest is a corpus fitted to
    whatever it was chosen to show.
    """
    low, high = ERAS[era]
    first = low if start is None else start
    numbers = list(range(first, min(first + count, high + 1)))
    if not numbers:
        raise SystemExit(f"no RFCs in range: era={era} start={start} count={count}")
    return numbers


def fetch(number: int, cache: Path, *, timeout: float) -> str | None:
    """The RFC's plain text, from `cache` when present. `None` when it does not exist upstream.

    A gap is normal — RFC numbers are not dense, and several are withdrawn — so a 404 is a skip
    rather than a failure. Anything else is raised: a network that is down should stop the run, not
    quietly produce a smaller corpus than the caller asked for.
    """
    cached = cache / f"rfc{number}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    try:
        with urllib.request.urlopen(RFC_URL.format(number=number), timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    time.sleep(POLITE_DELAY_SECONDS)
    cache.mkdir(parents=True, exist_ok=True)
    cached.write_text(body, encoding="utf-8")
    return body


MANIFEST = """\
[kb]
name = "rfc-realism-corpus"
id   = "{kb_id}"

[sources]
roots   = ["docs/"]
include = ["**/*.txt"]

[embedding]
provider = "fastembed"
model    = "BAAI/bge-small-en-v1.5"
dim      = 384

[rerank]
provider = "fastembed"
model    = "Xenova/ms-marco-MiniLM-L-6-v2"

[chunking]
headings = "numbered"
"""


def write_kb(out: Path, documents: dict[int, str], *, kb_id: str) -> None:
    (out / "docs").mkdir(parents=True, exist_ok=True)
    for number, body in documents.items():
        # The BOM the RFC editor serves would otherwise land at the head of the first chunk, and
        # column-0 matching is a clause of the heading predicate.
        (out / "docs" / f"rfc{number}.txt").write_text(body.lstrip("﻿"), encoding="utf-8")
    (out / "pinakes.toml").write_text(MANIFEST.format(kb_id=kb_id), encoding="utf-8")


def write_provenance(out: Path, numbers: Iterable[int], *, era: str) -> None:
    """What was fetched, so a later run can be *compared* with this one rather than merely repeated.

    A corpus whose contents are unrecorded produces numbers nobody can attribute — the failure this
    whole script exists to stop.
    """
    fetched = sorted(numbers)
    (out / "corpus.json").write_text(
        json.dumps(
            {
                "source": "https://www.rfc-editor.org/rfc/",
                "era": era,
                "era_range": ERAS[era],
                "count": len(fetched),
                "rfcs": fetched,
                "note": (
                    "Fetched, never committed. RFC rendering changed between the nroff and xml2rfc "
                    "eras, so a measurement over this corpus is a measurement over this era."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_rfc_corpus", description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="KB directory to create")
    parser.add_argument("--era", choices=sorted(ERAS), default="modern")
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--start", type=int, default=None, help="first RFC number (default: era's)")
    parser.add_argument("--rfcs", default=None, help="explicit comma-separated numbers")
    parser.add_argument(
        "--cache", type=Path, default=None, help="download cache (default: out/.cache)"
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    out: Path = args.out.expanduser()
    if (Path.cwd() / "pyproject.toml").exists() and out.resolve().is_relative_to(Path.cwd()):
        parser.error(
            f"refusing to build a KB inside this repository ({out}). This repo commits no "
            "harvested content — pass an --out outside it."
        )

    numbers = (
        [int(part) for part in args.rfcs.split(",")]
        if args.rfcs
        else rfc_numbers(era=args.era, count=args.count, start=args.start)
    )
    cache: Path = args.cache or (out / ".cache")

    documents: dict[int, str] = {}
    missing: list[int] = []
    for number in numbers:
        body = fetch(number, cache, timeout=args.timeout)
        if body is None:
            missing.append(number)
            continue
        documents[number] = body
        print(f"  rfc{number}: {len(body.splitlines())} lines", flush=True)

    if not documents:
        raise SystemExit("no RFCs fetched — nothing to build")

    from pinakes.ids import mint_kb_id

    write_kb(out, documents, kb_id=str(mint_kb_id()))
    write_provenance(out, documents, era=args.era)

    print(f"\n{len(documents)} documents -> {out}")
    if missing:
        # Named, not just counted: a silent gap is how a corpus quietly becomes something other
        # than what its provenance file claims.
        print(f"{len(missing)} not published (skipped): {', '.join(str(n) for n in missing)}")
    print(f"next: uv run pnk sync --kb {out} --rebuild")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
