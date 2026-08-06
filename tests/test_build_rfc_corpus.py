"""`tools/build_rfc_corpus.py` — the title curation and the chunking reserve, driven offline.

A subprocess rather than an import, for the reason `tests/test_fragments.py` gives: it exercises
**the same artifact** an operator runs by hand, argument parsing included, and needs no `sys.path`
surgery the type checkers then cannot resolve.

**Offline, and provably so.** Every RFC number here is far beyond any that will be assigned, and
every build is pointed at a `--cache` holding the text and the metadata for each. So a fetch that
escaped the cache would 404, `fetch` would skip the document, and the run would die on *"no RFCs
fetched"* — a loud failure rather than a test that quietly measures the live RFC Editor. (The one
exception is the repository-refusal test, which exits at argument parsing and so reaches no fetch
at all; it is given no cache deliberately, so that a *broken* refusal fails on an empty corpus
rather than by writing harvested RFCs into this repository's working tree.)

**What is *not* re-tested here.** That `sync` adopts a sidecar's title instead of overwriting it is
a property of `sync`, and `tests/test_sync.py::test_an_existing_sidecars_title_is_never_rewritten`
owns it. This file owns the half in front of it: that a title is *in* the sidecar before the first
sync ever runs, because a title that is not there then never arrives.

**The gap this cannot cover.** `fetch_title` treats an unparseable cache entry as a miss and
refetches, so that a truncated write cannot demote a document to its filename stem silently. Only
the network can exercise that branch, so nothing below asserts it. The two *parseable* outcomes —
a document with a title and a document without one — are covered, and they are what a run produces.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import cast

import pytest
import yaml

from pinakes.chunk import ChunkingError, assert_chunkable
from pinakes.manifest import load as load_manifest
from pinakes.sidecar import minted_title
from pinakes.sidecar import read as read_sidecar

TOOL = Path(__file__).parent.parent / "tools" / "build_rfc_corpus.py"

MEASURED_MAX_PREFIX_TOKENS = 68
"""The largest `title > heading_path` prefix over RFCs 8600-8799 — 195 documents, section numbers
stripped, tokenised with the manifest's own `BAAI/bge-small-en-v1.5` (20260806).

Restated here as a floor because the reserve's only justification *is* this measurement, and the
number it replaced — the plan's worked example of 30, taken from RFC 9110 alone — is smaller than
the median document in that band. A reserve quietly lowered back toward it would truncate half the
corpus with no warning and no error, which is precisely the failure that reads as a clean null."""

WINDOW_TOKENS = 512
"""`BAAI/bge-small-en-v1.5`'s window, from `ModelInfo` — the model the generated manifest names."""

DOCUMENT = "﻿Test RFC\n\n1.  Introduction\n\n   Some body text.\n"
"""Leading BOM deliberate: the RFC Editor serves one, and the heading predicate matches at column
0, so a BOM surviving into the document would silently disqualify its first heading."""


def cache_entry(cache: Path, number: int, *, title: str | None) -> None:
    """One RFC in the download cache: its text, and the metadata document the title comes from.

    `title=None` writes `{}` — exactly what the tool caches for a 404, so "the publisher offers no
    title" is expressed here the same way a real run expresses it.
    """
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"rfc{number}.txt").write_text(DOCUMENT, encoding="utf-8")
    metadata = {} if title is None else {"title": title, "doc_id": f"RFC{number}"}
    (cache / f"rfc{number}.json").write_text(json.dumps(metadata), encoding="utf-8")


def build(out: Path, cache: Path, numbers: list[int]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--out",
            str(out),
            "--cache",
            str(cache),
            "--rfcs",
            ",".join(str(number) for number in numbers),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc


def sidecar_of(out: Path, number: int) -> dict[str, object]:
    text = (out / "docs" / f"rfc{number}.txt.pnk.yaml").read_text(encoding="utf-8")
    return dict(yaml.safe_load(text))


def provenance(out: Path) -> dict[str, object]:
    return dict(json.loads((out / "corpus.json").read_text(encoding="utf-8")))


def section(data: dict[str, object], key: str) -> dict[str, object]:
    """One nested mapping, typed. `isinstance` alone narrows to `dict[Unknown, Unknown]`, which
    neither checker will index."""
    value = data[key]
    assert isinstance(value, dict), f"{key!r} is {type(value).__name__}, not a mapping"
    return cast("dict[str, object]", value)


def integer(data: dict[str, object], key: str) -> int:
    value = data[key]
    assert isinstance(value, int) and not isinstance(value, bool), f"{key!r} is not an integer"
    return value


def test_the_published_title_reaches_the_sidecar(tmp_path: Path) -> None:
    """The whole reason this increment exists.

    Asserted against `minted_title` rather than against a literal, because the failure being
    guarded is not "the title is wrong" — it is "the title is the filename", which is what every
    `.txt` document gets when nothing writes one, and what an uncurated RFC corpus is titled
    throughout.
    """
    cache = tmp_path / "cache"
    cache_entry(cache, 99991, title="HTTP Semantics")
    out = tmp_path / "kb"

    build(out, cache, [99991])

    assert sidecar_of(out, 99991)["title"] == "HTTP Semantics"
    assert sidecar_of(out, 99991)["title"] != minted_title(out / "docs" / "rfc99991.txt")
    assert provenance(out)["titles"] == {
        "source": "https://www.rfc-editor.org/rfc/rfc{number}.json",
        "published": 1,
        "filename_fallback": [],
        "kept_from_earlier_run": [],
    }


def test_a_document_with_no_published_title_falls_back_and_is_named(tmp_path: Path) -> None:
    """A corpus in which an unknown share of titles are filenames measures something nobody can
    name — so the fallback is kept (a visibly-a-filename title is honest) and the document is
    **named**, in the run's output *and* in `corpus.json`, which is the copy that survives the
    scrollback."""
    cache = tmp_path / "cache"
    cache_entry(cache, 99991, title="HTTP Semantics")
    cache_entry(cache, 99992, title=None)
    out = tmp_path / "kb"

    proc = build(out, cache, [99991, 99992])

    assert sidecar_of(out, 99992)["title"] == minted_title(out / "docs" / "rfc99992.txt")
    assert sidecar_of(out, 99992)["title"] == "rfc99992"
    assert "99992" in proc.stdout
    assert "no published title" in proc.stdout
    titles = section(provenance(out), "titles")
    assert titles["filename_fallback"] == [99992]
    assert titles["published"] == 1  # the fallback is not counted as published


def test_an_empty_title_is_a_fallback_not_a_title(tmp_path: Path) -> None:
    """`""` and `"   "` are absences wearing a string's clothes. A sidecar carrying `title: ""`
    would pass any "did we write a title" check while telling the reader nothing, and — unlike the
    filename stem — would not be visible to `pnk doctor`'s minted-title check either."""
    cache = tmp_path / "cache"
    cache_entry(cache, 99991, title="   ")
    out = tmp_path / "kb"

    build(out, cache, [99991])

    assert sidecar_of(out, 99991)["title"] == minted_title(out / "docs" / "rfc99991.txt")
    assert section(provenance(out), "titles")["filename_fallback"] == [99991]


def test_a_title_with_yaml_punctuation_round_trips(tmp_path: Path) -> None:
    """Real RFC titles carry colons and `#` — RFC 8713 is *"IAB, IESG, IETF Trust, and IETF LLC
    Selection, Confirmation, and Recall Process: Operation of…"*.

    Written unquoted, `title: A: B` is either a YAML error or a different value, and the sidecar
    that holds the document's permanent ULID would be the file that no longer parses. Nothing else
    in this repository exercises it: every committed corpus is hand-titled in plain words, so the
    first punctuated title anyone writes arrives from the RFC Editor. Asserted through
    `sidecar.read` rather than a raw string compare, because it is the product's own reader that
    has to get it back.
    """
    cache = tmp_path / "cache"
    nasty = "IAB, IESG: Selection, Confirmation, and Recall Process #1"
    cache_entry(cache, 99991, title=nasty)
    out = tmp_path / "kb"

    build(out, cache, [99991])

    owner = load_manifest(out).kb.id
    written = read_sidecar(out / "docs" / "rfc99991.txt.pnk.yaml", owner=owner)
    assert written.title == nasty


def test_the_manifest_stamps_a_reduced_max_tokens_that_leaves_room_for_the_prefix(
    tmp_path: Path,
) -> None:
    """The reserve is a *corpus* setting so that both legs of the injection experiment chunk
    identically; the number itself has to leave room for the longest prefix the corpus can produce.

    Both directions are asserted. `max_tokens + reserve` must be chunkable — otherwise the injected
    prefix is truncated away, silently, from exactly the long chunks the experiment is about. And
    one token more must **not** be, which is what pins the reserve to the whole of the remaining
    budget rather than to some smaller number that merely happens to fit.

    The embedding model is asserted first, because everything below is arithmetic about *its*
    window: swapped for a model with a different one, every assertion here would still pass while
    the corpus it describes was wrong — an assertion satisfied by something other than the property
    it names.
    """
    cache = tmp_path / "cache"
    cache_entry(cache, 99991, title="HTTP Semantics")
    out = tmp_path / "kb"

    build(out, cache, [99991])

    manifest = dict(tomllib.loads((out / "pinakes.toml").read_text(encoding="utf-8")))
    recorded = section(provenance(out), "chunking")
    max_tokens = integer(section(manifest, "chunking"), "max_tokens")
    reserve = integer(recorded, "prefix_reserve_tokens")

    assert section(manifest, "embedding")["model"] == "BAAI/bge-small-en-v1.5"
    assert max_tokens == integer(recorded, "max_tokens")
    assert reserve >= MEASURED_MAX_PREFIX_TOKENS
    assert_chunkable(max_tokens + reserve, model_max_tokens=WINDOW_TOKENS)
    with pytest.raises(ChunkingError):
        assert_chunkable(max_tokens + reserve + 1, model_max_tokens=WINDOW_TOKENS)


def test_the_generated_manifest_still_loads(tmp_path: Path) -> None:
    """The `max_tokens` stamp is spliced into a `str.format` template carrying a TOML comment, and
    a manifest that will not parse fails at the *next* command rather than at the one that wrote
    it. `load` rather than `tomllib` on purpose: it is strict about unknown keys and values, so it
    is what would reject a stamp this tool wrote in the wrong section."""
    cache = tmp_path / "cache"
    cache_entry(cache, 99991, title="HTTP Semantics")
    out = tmp_path / "kb"

    build(out, cache, [99991])

    manifest = load_manifest(out)
    assert manifest.chunking.headings == "numbered"
    assert manifest.chunking.max_tokens < 510  # reduced from the default, which is the whole point
    assert manifest.chunking.overlap < manifest.chunking.max_tokens


def test_the_bom_is_stripped_from_the_written_document(tmp_path: Path) -> None:
    """The heading predicate matches at column 0, so a surviving BOM disqualifies the document's
    first heading — and a corpus quietly missing one heading per document is exactly the kind of
    difference a retrieval measurement cannot see."""
    cache = tmp_path / "cache"
    cache_entry(cache, 99991, title="HTTP Semantics")
    out = tmp_path / "kb"

    build(out, cache, [99991])

    written = (out / "docs" / "rfc99991.txt").read_text(encoding="utf-8")
    assert not written.startswith("﻿")
    assert written.startswith("Test RFC")


def test_a_rerun_keeps_the_document_ulid_and_the_kb_id(tmp_path: Path) -> None:
    """Both ids are permanent (`docs/DESIGN.md` §2.2) and this script re-runs by design — its
    download cache exists so a partial run resumes.

    Before sidecars were minted here, re-minting the KB id produced a new-but-equivalent KB. Now
    that the directory holds permanent document ULIDs it would orphan them — so neither file that
    holds an id is rewritten: not the manifest, and not the sidecar, which *is* the only copy of
    the document's ULID and the thing every inbound `pnk://` link resolves through.
    """
    cache = tmp_path / "cache"
    cache_entry(cache, 99991, title="HTTP Semantics")
    out = tmp_path / "kb"

    build(out, cache, [99991])
    first_doc_id = sidecar_of(out, 99991)["id"]
    first_kb_id = tomllib.loads((out / "pinakes.toml").read_text(encoding="utf-8"))["kb"]["id"]

    proc = build(out, cache, [99991])

    assert sidecar_of(out, 99991)["id"] == first_doc_id
    assert tomllib.loads((out / "pinakes.toml").read_text(encoding="utf-8"))["kb"]["id"] == (
        first_kb_id
    )
    assert "already had a sidecar" in proc.stdout
    assert section(provenance(out), "titles")["kept_from_earlier_run"] == [99991]


def test_a_rerun_does_not_overwrite_an_existing_manifest(tmp_path: Path) -> None:
    """The manifest carries the KB's permanent id and, once the corpus is calibrated, the fitted
    `[retrieval.confidence]` thresholds — a measurement, not a setting.

    This is the defect that appears the moment a re-run *preserves* identity: the KB would look
    like the same KB, with its calibration replaced, and every command would report success. The
    document beside it is still refreshed, so a re-run still resumes a partial fetch.
    """
    cache = tmp_path / "cache"
    cache_entry(cache, 99991, title="HTTP Semantics")
    out = tmp_path / "kb"

    build(out, cache, [99991])
    manifest = out / "pinakes.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + '\n[retrieval.confidence]\nfitted_for = "fake@rev1"\nlow_below = 0.31\n'
        "high_above = 0.62\n",
        encoding="utf-8",
    )
    calibrated = manifest.read_text(encoding="utf-8")

    proc = build(out, cache, [99991])

    assert manifest.read_text(encoding="utf-8") == calibrated
    assert "left alone" in proc.stdout


def test_a_rerun_onto_an_older_manifest_names_the_chunking_it_did_not_change(
    tmp_path: Path,
) -> None:
    """Keeping the manifest has a cost, and this is it: a corpus grown by a re-run onto a manifest
    written before the reserve existed chunks at the old `max_tokens` and truncates the injected
    prefix away — silently, from exactly the long chunks the experiment is about. So the run says
    which value is in the file and which value it would have stamped."""
    cache = tmp_path / "cache"
    cache_entry(cache, 99991, title="HTTP Semantics")
    out = tmp_path / "kb"

    build(out, cache, [99991])
    manifest = out / "pinakes.toml"
    edited, count = re.subn(
        r"^max_tokens = \d+$",
        "max_tokens = 510",
        manifest.read_text(encoding="utf-8"),
        count=1,
        flags=re.MULTILINE,
    )
    assert count == 1, "the manifest no longer stamps max_tokens where this test expects it"
    manifest.write_text(edited, encoding="utf-8")

    proc = build(out, cache, [99991])

    assert "max_tokens is 510" in proc.stdout
    assert "fresh --out" in proc.stdout


def test_it_refuses_to_build_inside_this_repository(tmp_path: Path) -> None:
    """This repository is public and commits no harvested content (`CLAUDE.md`). The refusal is
    older than this file; it is tested here because a corpus builder whose one safety rule is
    untested is a corpus builder that will land harvested RFCs in a public repo the day the check
    is refactored."""
    repo = TOOL.parent.parent
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--out", "tests/rfc-kb", "--rfcs", "99991"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "refusing to build a KB inside this repository" in proc.stderr
    assert not (repo / "tests" / "rfc-kb").exists()
