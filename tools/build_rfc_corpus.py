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

**Titles come from the publisher, not from the text.** Every `.txt` document falls back to its
filename stem for `title` (`sidecar.minted_title`), so an uncurated RFC corpus is titled `rfc9110`
throughout — which is the condition `pnk doctor`'s title check exists to detect, and it confounds
any measurement that reads `title` as retrieval context. So each document's sidecar is **minted
here, before the first sync**, carrying the title from `https://www.rfc-editor.org/rfc/rfc<N>.json`.
`title` is the user's field and sync never overwrites it, so a title that is not there at first
ingest never arrives. Nothing is inferred: a value is read from the RFC Editor's own metadata, and
a document whose metadata cannot be read keeps the filename stem and **is named in the output and
in `corpus.json`** — a corpus where an unknown share of titles are filenames measures something
nobody can name.

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
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import cast

RFC_URL = "https://www.rfc-editor.org/rfc/rfc{number}.txt"
RFC_METADATA_URL = "https://www.rfc-editor.org/rfc/rfc{number}.json"
"""The RFC Editor's own metadata for one document — ~1.5 KB, from the host the text comes from,
and cached exactly as the text is."""

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


def title_of(raw: str) -> str | None:
    """The `title` field of one RFC's metadata document, or `None` when it carries none.

    Deliberately total over any *parseable* JSON: a 404 is cached as `{}` below, and that absence
    must read back exactly like a published document that happens to omit the field. Only
    unparseable bytes are an error, and they are raised by the caller rather than swallowed here —
    a truncated cache entry that silently became "no title" is the one failure this whole path
    exists to prevent.
    """
    metadata: object = json.loads(raw)
    if not isinstance(metadata, dict):
        return None
    title: object = cast("dict[str, object]", metadata).get("title")
    return title.strip() if isinstance(title, str) and title.strip() else None


def fetch_title(number: int, cache: Path, *, timeout: float) -> str | None:
    """The RFC's published title, from `cache` when present. `None` when the publisher offers none.

    **A 404 is cached as `{}`** — a valid metadata document with no `title` — so the absence is
    recorded in the same format as a presence and a 300-document re-run does not re-ask for it.
    That is also the only reason this whole path is exercisable offline. The cost is that a
    *transient* 404 is cached permanently: the run names the document as a fallback once, and every
    later run reports it as `kept`. Deleting the cached `.json` is the remedy.

    **An unparseable cache entry is a miss, never a fallback title.** A truncated write would
    otherwise demote a document to its filename stem quietly, and quiet is the failure mode: the
    caller reports fallbacks precisely because a corpus of unknown title provenance measures
    nothing. Anything other than a 404 is raised, matching `fetch`: a network that is down should
    stop the run, not silently produce a corpus titled `rfc8600`.
    """
    cached = cache / f"rfc{number}.json"
    if cached.exists():
        try:
            return title_of(cached.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    try:
        with urllib.request.urlopen(
            RFC_METADATA_URL.format(number=number), timeout=timeout
        ) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        body = "{}"
    else:
        time.sleep(POLITE_DELAY_SECONDS)
    title = title_of(body)  # raises on a malformed *response*, which is not a cacheable answer
    cache.mkdir(parents=True, exist_ok=True)
    cached.write_text(body, encoding="utf-8")
    return title


EMBEDDING_WINDOW_TOKENS = 512
"""`BAAI/bge-small-en-v1.5`'s window, the model this corpus's manifest names."""

SPECIAL_TOKENS = 2
"""`assert_chunkable`'s own default, restated here because the arithmetic below has to agree with
it exactly — `chunk.assert_chunkable` is what refuses the pair, and `tests/` checks it does."""

PREFIX_RESERVE_TOKENS = 96
"""Headroom for the `title > heading_path` prefix the injection experiment prepends to the text
that is embedded and indexed (`plans/20260805_1721-metadata-as-retrieval-context.md` §2).

**Measured 20260806 06:1x, not chosen.** Every heading path of RFCs 8600-8799 — 195 documents, 5 of
the 200 numbers unpublished — prefixed with the document's published title, section numbers
stripped, tokenised with this manifest's own `BAAI/bge-small-en-v1.5`:

    largest prefix   68 tokens   ("The China Mobile, Huawei, and ZTE Broadband Network Gateway
                                  (BNG) Simple Control and User Plane Separation Protocol
                                  (S-CUSP) > S-CUSP TLVs and Sub-TLVs > Sub-TLV Format and
                                  Sub-TLVs > Egress-CAR Sub-TLV")
    per-document largest: median 31, p95 51, p99 61
    longest title alone   32 tokens

**The plan's worked example of 30 is falsified by this and must not be used.** It was RFC 9110's
maximum, and RFC 9110's title is two tokens long; the median document in a 195-document band
already exceeds it. Reserving 30 would have truncated roughly half the corpus silently.

**The 41% between 68 and 96 is deliberate.** The measurement covers 200 of the modern band's ~700
numbers, so a longer prefix elsewhere in the band is likely rather than merely possible; and the
injected form adds a separator between prefix and text, which tokenises with the text rather than
independently of it.

**Why the reserve is a corpus setting and not a per-document computation.** Both legs of the
experiment must chunk identically or they are different corpora, and a reserve buried in code is a
reserve the two legs can disagree about. Stamping one `max_tokens` makes the chunk boundaries
byte-identical by construction, leaving the injected text as the only difference — which is the
entire requirement.

**What catches a corpus that exceeds it even so: `assert_chunkable`, loudly.** This is measured
over a band, not proven over every band. Exceeding it must be a refusal naming the value to lower
`max_tokens` to, never the silent truncation an over-length embedding input gets today."""

CHUNK_MAX_TOKENS = EMBEDDING_WINDOW_TOKENS - SPECIAL_TOKENS - PREFIX_RESERVE_TOKENS
"""What the manifest stamps. The default 510 leaves *zero* headroom against this model, so an
injected prefix would push every full chunk past the window and be truncated — removing text from
exactly the long chunks the experiment is about, with no warning and no error."""


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
headings   = "numbered"
max_tokens = {max_tokens}
# Not the default 510: the model's window is {window} tokens, {special} of them
# special, and {reserve} of what remains is reserved for the `title > heading_path`
# prefix the injection experiment prepends to the embedded and indexed text. Both
# legs chunk at this value, so their chunk boundaries are identical and the injected
# text is the only difference between them.

[retrieval.confidence]
fitted_for = "Xenova/ms-marco-MiniLM-L-6-v2"
low_below  = {low_below}
high_above = {high_above}
"""


CONFIDENCE_LOW_BELOW = -4.3841
CONFIDENCE_HIGH_ABOVE = -0.5586
"""Fitted 20260806 by `python -m pinakes.calibrate` against this corpus and its frozen golden set
(96 answerable, 14 unanswerable questions), and stamped here rather than left for a human to paste.

**Without them every confidence is `unknown`.** `manifest.load` leaves `confidence` `None` when the
section is absent, `_confidence` returns `UNKNOWN` on its first check, and the eval then reports
`false_abstain` and `false_confidence` as a vacuous **0.0** with `confidence_coverage` at 0.0 —
metrics that read as perfect and measure nothing. Two of the three numbers the injection
experiment's §2 requires are those two.

**Stamped, so that both legs of a comparison are fitted identically by construction.** Thresholds
refitted after a change would differ between legs, and every confidence comparison would then be
measuring the refit rather than the change. A generated corpus whose thresholds lived only in an
uncommitted `pinakes.toml` would also lose them on any machine but the one that fitted them.

**Carry `calibrate.py`'s own caveat wherever these numbers are reported**: they are fitted on the
same golden set the eval scores against, so the false-confidence rate is partly a measurement of
the fit. Treat calibration as a floor on quality, not a measurement of it."""


def write_documents(out: Path, documents: dict[int, str]) -> None:
    (out / "docs").mkdir(parents=True, exist_ok=True)
    for number, body in documents.items():
        # The BOM the RFC editor serves would otherwise land at the head of the first chunk, and
        # column-0 matching is a clause of the heading predicate.
        (out / "docs" / f"rfc{number}.txt").write_text(body.lstrip("﻿"), encoding="utf-8")


def write_manifest(out: Path, *, kb_id: str) -> bool:
    """Write `pinakes.toml`, unless one is already there. `True` when it wrote.

    **An existing manifest is never overwritten**, for the same reason an existing sidecar is not.
    It carries the KB's permanent id (`docs/DESIGN.md` §2.2), and — once the corpus has been
    calibrated — the fitted `[retrieval.confidence]` thresholds, which are a measurement and not a
    setting. Rewriting it would replace both while every command still reported success: the KB
    would look like the same KB and no longer be one.

    This script re-runs by design (its download cache exists so a partial run resumes), so that is
    not a hypothetical. The cost is that a re-run does **not** pick up a changed `[chunking]`, which
    is why the caller compares the two and says so.
    """
    path = out / "pinakes.toml"
    if path.exists():
        return False
    path.write_text(
        MANIFEST.format(
            kb_id=kb_id,
            max_tokens=CHUNK_MAX_TOKENS,
            window=EMBEDDING_WINDOW_TOKENS,
            special=SPECIAL_TOKENS,
            reserve=PREFIX_RESERVE_TOKENS,
            low_below=CONFIDENCE_LOW_BELOW,
            high_above=CONFIDENCE_HIGH_ABOVE,
        ),
        encoding="utf-8",
    )
    return True


def stamped_max_tokens(out: Path) -> int | None:
    """`[chunking] max_tokens` in the manifest already there, or `None` if it cannot be read.

    Read with `tomllib` rather than `manifest.load`, deliberately: this runs against whatever an
    earlier *release* wrote, and `load` is strict about unknown keys by design. An unreadable
    manifest returns `None` and the caller warns — this is a diagnostic, never a gate.
    """
    path = out / "pinakes.toml"
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None
    chunking: object = parsed.get("chunking")
    if not isinstance(chunking, dict):
        return None
    found: object = cast("dict[str, object]", chunking).get("max_tokens")
    return found if isinstance(found, int) and not isinstance(found, bool) else None


def mint_sidecars(out: Path, titles: Mapping[int, str | None]) -> tuple[list[int], list[int]]:
    """Write each document's sidecar **before the first sync**, carrying its published title.

    Returns `(fallback, kept)`: the documents that got the filename stem because no title could be
    read, and the documents an earlier run already minted a sidecar for.

    **An existing sidecar is left exactly as it is.** It holds the document's permanent ULID, which
    nothing can recompute, so `sidecar.create` refuses to write over one — and that refusal is
    right. But it means a re-run cannot repair a title an earlier run could not fetch, which is why
    `kept` is returned rather than skipped silently: the titles in a corpus with a non-empty `kept`
    are the titles of whichever run first minted them. To re-fetch one, delete its `.json` from the
    cache *and* its sidecar — accepting that the document is issued a new ULID.

    **No `created`, unlike `sync`'s own mint.** Nothing in the product reads the field — only
    `[kb] created` in the manifest is validated — and a wall-clock stamp would differ between two
    builds of the same corpus, against a script whose whole point is that a later run can be
    *compared* with an earlier one. Stated because it is a divergence, not an oversight.
    """
    # Imported here rather than at module scope, following `main`'s `mint_kb_id`: this script is
    # run as `python3 tools/...` and its `--help` should not depend on an installed `pinakes`.
    from pinakes.sidecar import create as create_sidecar
    from pinakes.sidecar import sidecar_path, skeleton

    fallback: list[int] = []
    kept: list[int] = []
    for number, title in sorted(titles.items()):
        document = out / "docs" / f"rfc{number}.txt"
        target = sidecar_path(document)
        if target.exists() or target.is_symlink():
            kept.append(number)
            continue
        if title is None:
            fallback.append(number)
        create_sidecar(target, skeleton(document, title=title))
    return fallback, kept


def write_provenance(
    out: Path, numbers: Iterable[int], *, era: str, fallback: Sequence[int], kept: Sequence[int]
) -> None:
    """What was fetched, so a later run can be *compared* with this one rather than merely repeated.

    A corpus whose contents are unrecorded produces numbers nobody can attribute — the failure this
    whole script exists to stop.

    **`titles` is here and not only on stdout for exactly that reason.** A corpus in which some
    unknown share of `title` fields are filename stems measures something nobody can name, and the
    run that would have said so scrolled past weeks ago.
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
                "titles": {
                    "source": RFC_METADATA_URL,
                    "published": len(fetched) - len(fallback) - len(kept),
                    "filename_fallback": sorted(fallback),
                    "kept_from_earlier_run": sorted(kept),
                },
                "chunking": {
                    "max_tokens": CHUNK_MAX_TOKENS,
                    "prefix_reserve_tokens": PREFIX_RESERVE_TOKENS,
                },
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


GOLDEN_SET = Path(__file__).resolve().parent / "rfc_corpus" / "questions.yaml"
"""The frozen golden set, committed because it is authored rather than harvested.

The corpus is regenerated and never committed; the questions are the instrument that reads it, and
an instrument living on one machine cannot be re-run — which is the whole reason this script
exists. Its own header records how it was authored and why it must not be edited."""


def write_golden_set(out: Path) -> bool:
    """Copy the committed golden set into `<out>/eval/questions.yaml`.

    Overwritten on every build, unlike `pinakes.toml`: the repository copy is the source of truth,
    so a corpus carrying an older one would be evaluated against questions nobody could find. The
    manifest is the opposite case — it holds the KB's permanent id and its fitted confidence
    thresholds, which a rebuild must not discard.

    `pinakes.eval` defaults to `<kb>/eval/questions.yaml`, so putting it here is what lets the
    documented run be `python -m pinakes.eval <out>` with no path flag.
    """
    if not GOLDEN_SET.exists():  # pragma: no cover — only in a truncated checkout
        return False
    (out / "eval").mkdir(parents=True, exist_ok=True)
    (out / "eval" / "questions.yaml").write_text(
        GOLDEN_SET.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return True


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
    titles: dict[int, str | None] = {}
    missing: list[int] = []
    for number in numbers:
        body = fetch(number, cache, timeout=args.timeout)
        if body is None:
            missing.append(number)
            continue
        documents[number] = body
        titles[number] = fetch_title(number, cache, timeout=args.timeout)
        print(
            f"  rfc{number}: {len(body.splitlines())} lines — {titles[number] or '(no title)'}",
            flush=True,
        )

    if not documents:
        raise SystemExit("no RFCs fetched — nothing to build")

    from pinakes.ids import mint_kb_id

    write_documents(out, documents)
    wrote_manifest = write_manifest(out, kb_id=str(mint_kb_id()))
    fallback, kept = mint_sidecars(out, titles)
    write_provenance(out, documents, era=args.era, fallback=fallback, kept=kept)
    wrote_questions = write_golden_set(out)

    print(f"\n{len(documents)} documents -> {out}")
    if not wrote_manifest:
        # Named against the value this build would have stamped, not merely "kept": the two legs of
        # the injection experiment must chunk identically, and a corpus grown by a re-run onto a
        # manifest from before the reserve existed would chunk at 510 and truncate the prefix away
        # — silently, from exactly the long chunks the experiment is about.
        stamped = stamped_max_tokens(out)
        reads = "could not be read" if stamped is None else f"is {stamped}"
        note = "" if stamped == CHUNK_MAX_TOKENS else f" — its [chunking] max_tokens {reads}"
        print(f"pinakes.toml already existed and was left alone{note}")
        if stamped != CHUNK_MAX_TOKENS:
            print(
                f"  this build stamps {CHUNK_MAX_TOKENS}. To adopt it, build into a fresh --out: "
                "editing max_tokens in place rechunks the KB and invalidates any captured baseline."
            )
    if missing:
        # Named, not just counted: a silent gap is how a corpus quietly becomes something other
        # than what its provenance file claims.
        print(f"{len(missing)} not published (skipped): {', '.join(str(n) for n in missing)}")
    # Both named rather than counted, for the reason above and one more: these are the documents
    # whose `title` is a filename stem, and a measurement that reads `title` as retrieval context
    # is measuring `rfc8600` on every one of them.
    if fallback:
        print(
            f"{len(fallback)} with no published title — filename stem kept: "
            f"{', '.join(str(n) for n in fallback)}"
        )
    if kept:
        print(
            f"{len(kept)} already had a sidecar from an earlier run and were left untouched: "
            f"{', '.join(str(n) for n in kept)}"
        )
    if not wrote_questions:  # pragma: no cover — only in a truncated checkout
        print(f"no golden set at {GOLDEN_SET} — `pinakes.eval` will skip this corpus")
    print(f"next: uv run pnk sync --kb {out} --rebuild")
    print(f"then: uv run python -m pinakes.eval {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
