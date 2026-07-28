"""`extract/cache.py` — one JSON file per (document, backend+fingerprint), so a re-synced,
unchanged PDF never pays for extraction twice.

One entry stores exactly I1's `ExtractedText` plus its provenance and cache-keying metadata — the
same shape a miss produces by calling the extractor directly — so a hit and a miss are
indistinguishable to the caller. A draft that stored only `text` and `page_spans` would work on
every miss and fail on every hit the moment a later increment starts consuming
`per_page_provenance`, which is rule 2's failure shape in exactly the increment pair the plan cites
to justify it.

`operation_id`/`call_ids` are the future join key to the ledger (I6b/I7c): always `None` today,
since no paid backend exists yet and a free extraction costs nothing to join to. The fields are
part of the schema now so I7c never needs a cache migration to add them.

Invalidation is **by key, never by mutation**: a changed document (`content_hash`) or a changed
backend/version/threshold (`fingerprint`, `extract.fingerprint()`) simply misses and re-extracts.
Any problem reading an entry — missing file, truncated write, unreadable JSON, a schema this
version doesn't recognise, a required field of the wrong shape — is a miss, never a crash: a cache
existing only to be faster than a miss must never be a new way to fail correctly-configured sync.
Written to a sibling temp file and `os.replace`d, so a process killed mid-write leaves either the
old entry or nothing, never a half-written one that would need the "truncated" case to catch it.

Eviction (`evict_orphans`) and reporting (`survey`) share one classification: a cache entry whose
`content_hash` matches no active document is an orphan. An orphan written by a paid backend
(`operation_id` is not `None`) is never deleted automatically — only reported — because a
soft-deleted or un-sidecarred document is not an "active document", and sweeping away an extraction
that was paid for, with no prompt and no printed cost, is the one mistake this module must not
make (plans/v0.2.md, I4). An entry that cannot be parsed is left alone and reported as corrupt for
the same reason: a paid entry can't be ruled out for a file that can't be read.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pinakes.extract import ExtractedText

CACHE_SCHEMA_VERSION = 1
_CONTENT_HASH_PREFIX = "sha256:"


def entry_path(cache_dir: Path, *, content_hash: str, fingerprint: str) -> Path:
    """`<content_hash>-<fingerprint>.json`, with `content_hash`'s `sha256:` prefix stripped — a
    colon is illegal in a Windows path, and the prefix carries no information the caller doesn't
    already have (every entry in this cache is a sha256, and the JSON body restates it in full)."""
    bare_hash = content_hash.removeprefix(_CONTENT_HASH_PREFIX)
    return cache_dir / f"{bare_hash}-{fingerprint}.json"


def peek(cache_dir: Path, *, content_hash: str, fingerprint: str) -> ExtractedText | None:
    """A read-only lookup: `None` on any miss, and never calls an extractor (I5's paid-protection
    check uses this to ask "is the *recorded* backend's own cached result still here" without the
    fallback-to-extraction `get_or_extract` always performs on a miss)."""
    return _read(entry_path(cache_dir, content_hash=content_hash, fingerprint=fingerprint))


def get_or_extract(
    cache_dir: Path,
    *,
    content_hash: str,
    backend: str,
    fingerprint: str,
    extract: Callable[[], ExtractedText],
    operation_id: str | None = None,
    call_ids: Sequence[str] | None = None,
) -> ExtractedText:
    """Return the cached `ExtractedText` if the key matches; otherwise call `extract`, cache its
    result, and return that. `extract` is called lazily — never on a hit — so a cache hit never
    pays for loading the backend (importing pypdfium2, say) at all, only for reading a JSON file.
    """
    path = entry_path(cache_dir, content_hash=content_hash, fingerprint=fingerprint)
    cached = _read(path)
    if cached is not None:
        return cached
    extracted = extract()
    # The cache is an optimisation; a disk-full/permission failure writing it must not fail an
    # extraction that already succeeded.
    with contextlib.suppress(OSError):
        _write(
            path,
            content_hash=content_hash,
            backend=backend,
            fingerprint=fingerprint,
            extracted=extracted,
            operation_id=operation_id,
            call_ids=call_ids,
        )
    return extracted


def _read(path: Path) -> ExtractedText | None:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    data = cast(dict[str, Any], raw)
    if data.get("schema") != CACHE_SCHEMA_VERSION:
        return None
    text = data.get("text")
    raw_page_spans = data.get("page_spans")
    raw_provenance = data.get("per_page_provenance")
    if not isinstance(text, str) or not isinstance(raw_page_spans, list):
        return None
    if not isinstance(raw_provenance, list):
        return None
    page_spans = cast(list[Any], raw_page_spans)
    per_page_provenance = cast(list[Any], raw_provenance)
    try:
        return ExtractedText(
            text=text,
            page_spans=tuple((int(span[0]), int(span[1])) for span in page_spans),
            per_page_provenance=tuple(_string_mapping(page) for page in per_page_provenance),
        )
    except (KeyError, TypeError, IndexError, ValueError):
        return None


def _string_mapping(raw: object) -> dict[str, str]:
    """A `per_page_provenance` entry, validated key *and* value — `dict(page)` alone would accept
    `{"confidence": None}` silently, degrading `ExtractedText`'s declared `Mapping[str, str]`."""
    if not isinstance(raw, dict):
        raise TypeError("per_page_provenance entry must be a mapping")
    mapping = cast(dict[Any, Any], raw)
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()):
        raise TypeError("per_page_provenance entry must map str to str")
    return cast(dict[str, str], mapping)


def _write(
    path: Path,
    *,
    content_hash: str,
    backend: str,
    fingerprint: str,
    extracted: ExtractedText,
    operation_id: str | None,
    call_ids: Sequence[str] | None,
) -> None:
    body = {
        "schema": CACHE_SCHEMA_VERSION,
        "content_hash": content_hash,
        "backend": backend,
        "fingerprint": fingerprint,
        "page_count": len(extracted.page_spans),
        "page_spans": [list(span) for span in extracted.page_spans],
        "text": extracted.text,
        "per_page_provenance": [dict(page) for page in extracted.per_page_provenance],
        "operation_id": operation_id,
        "call_ids": list(call_ids) if call_ids is not None else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # `.tmp` on purpose, never `.json`: `Path.glob("*.json")` matches dot-files too (verified —
    # unlike shell globbing), so a `*.json`-suffixed temp name left behind by an uncatchable kill
    # (SIGKILL, OOM, power loss — `except BaseException` below already cleans up anything else)
    # would be scanned by `survey`/`total_stats`/`clear_all` as if it were a real entry.
    descriptor, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(body, handle)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


@dataclass(frozen=True, slots=True)
class CacheSurvey:
    """A read-only classification of every entry in the cache. Never deletes anything itself —
    `evict_orphans` is the only function in this module that does, and it deletes exactly
    `.orphans`, nothing in `.paid_orphans` or `.corrupt`."""

    entries: int
    bytes_used: int
    orphans: tuple[Path, ...]
    paid_orphans: tuple[Path, ...]
    corrupt: tuple[Path, ...]


def survey(cache_dir: Path, *, active_content_hashes: set[str]) -> CacheSurvey:
    if not cache_dir.is_dir():
        return CacheSurvey(0, 0, (), (), ())
    entries = 0
    bytes_used = 0
    orphans: list[Path] = []
    paid_orphans: list[Path] = []
    corrupt: list[Path] = []
    for candidate in sorted(cache_dir.glob("*.json")):
        entries += 1
        bytes_used += candidate.stat().st_size
        classified = _classify(candidate, active_content_hashes=active_content_hashes)
        if classified == "corrupt":
            corrupt.append(candidate)
        elif classified == "paid_orphan":
            paid_orphans.append(candidate)
        elif classified == "orphan":
            orphans.append(candidate)
    return CacheSurvey(entries, bytes_used, tuple(orphans), tuple(paid_orphans), tuple(corrupt))


def _classify(path: Path, *, active_content_hashes: set[str]) -> str:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "corrupt"
    if not isinstance(raw, dict):
        return "corrupt"
    data = cast(dict[str, Any], raw)
    if data.get("schema") != CACHE_SCHEMA_VERSION:
        return "corrupt"
    content_hash = data.get("content_hash")
    if not isinstance(content_hash, str):
        return "corrupt"
    operation_id = data.get("operation_id")
    if content_hash in active_content_hashes:
        return "active"
    return "paid_orphan" if operation_id is not None else "orphan"


def evict_orphans(cache_dir: Path, *, active_content_hashes: set[str]) -> CacheSurvey:
    """After a fully successful sync: remove free-backend orphans; report (never remove) paid
    orphans and corrupt entries. Returns the survey taken before deletion."""
    found = survey(cache_dir, active_content_hashes=active_content_hashes)
    for path in found.orphans:
        path.unlink(missing_ok=True)
    return found


def total_stats(cache_dir: Path) -> tuple[int, int]:
    """Entry count and total bytes, with no active/orphan classification — `--clear-cache`
    empties everything unconditionally, so its confirmation prompt needs the unfiltered total."""
    if not cache_dir.is_dir():
        return 0, 0
    paths = list(cache_dir.glob("*.json"))
    return len(paths), sum(path.stat().st_size for path in paths)


def clear_all(cache_dir: Path) -> tuple[int, int]:
    """`--clear-cache`: empties `cache/extract/` unconditionally — paid or free, active or
    orphaned. This is the one operation in this module that does not distinguish paid entries,
    because it is the explicit, confirmed, whole-directory nuke the manual flag names it as."""
    if not cache_dir.is_dir():
        return 0, 0
    paths = sorted(cache_dir.glob("*.json"))
    total_bytes = sum(path.stat().st_size for path in paths)
    for path in paths:
        path.unlink()
    return len(paths), total_bytes
