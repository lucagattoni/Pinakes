"""`extract/cache.py` — hit/miss keying, atomic writes, corrupt-file handling, and eviction.

No pypdfium2 anywhere here: `ExtractedText` is a plain dataclass and `get_or_extract`'s `extract`
callable is whatever the caller supplies, so this whole module is testable with a counting stand-in
— exactly the point of deferring the real extractor behind a lazy callable (I4).
"""

import json
from pathlib import Path

from pinakes.extract import ExtractedText
from pinakes.extract import cache as extract_cache

SAMPLE = ExtractedText(
    text="Hello, world.",
    page_spans=((0, 13),),
    per_page_provenance=({"source": "pypdfium2"},),
)


class Spy:
    """Counts calls; returns a fixed `ExtractedText` each time (deterministic, not a mock)."""

    def __init__(self, result: ExtractedText = SAMPLE) -> None:
        self.calls = 0
        self.result = result

    def __call__(self) -> ExtractedText:
        self.calls += 1
        return self.result


def test_a_second_lookup_with_the_same_key_never_calls_extract(tmp_path: Path) -> None:
    spy = Spy()
    first = extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=spy
    )
    second = extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=spy
    )
    assert spy.calls == 1
    assert first == SAMPLE
    assert second == SAMPLE


def test_a_changed_content_hash_misses(tmp_path: Path) -> None:
    spy = Spy()
    extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=spy
    )
    extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:def", backend="pypdfium2", fingerprint="fp1", extract=spy
    )
    assert spy.calls == 2


def test_a_changed_fingerprint_misses(tmp_path: Path) -> None:
    """A version bump, a fitted-threshold change — anything `extract.fingerprint()` reflects."""
    spy = Spy()
    extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=spy
    )
    extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp2", extract=spy
    )
    assert spy.calls == 2


def test_a_truncated_cache_file_misses_rather_than_crashes(tmp_path: Path) -> None:
    path = extract_cache.entry_path(tmp_path, content_hash="sha256:abc", fingerprint="fp1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema": 1, "content_hash": "sha256:abc", "text": "Hel', encoding="utf-8")

    spy = Spy()
    result = extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=spy
    )
    assert spy.calls == 1  # the truncated file was a miss, not a crash
    assert result == SAMPLE
    # And the miss re-wrote a good entry: a third lookup is now a hit.
    extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=spy
    )
    assert spy.calls == 1


def test_a_wrong_schema_version_misses(tmp_path: Path) -> None:
    path = extract_cache.entry_path(tmp_path, content_hash="sha256:abc", fingerprint="fp1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": 999,
                "content_hash": "sha256:abc",
                "backend": "pypdfium2",
                "fingerprint": "fp1",
                "page_count": 1,
                "page_spans": [[0, 13]],
                "text": "stale shape",
                "per_page_provenance": [{}],
                "operation_id": None,
                "call_ids": None,
            }
        ),
        encoding="utf-8",
    )
    spy = Spy()
    result = extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=spy
    )
    assert spy.calls == 1
    assert result == SAMPLE


def test_a_missing_required_field_misses(tmp_path: Path) -> None:
    path = extract_cache.entry_path(tmp_path, content_hash="sha256:abc", fingerprint="fp1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": 1, "content_hash": "sha256:abc"}), encoding="utf-8")
    spy = Spy()
    result = extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=spy
    )
    assert spy.calls == 1
    assert result == SAMPLE


def test_a_hit_never_calls_extract_at_all_not_even_lazily(tmp_path: Path) -> None:
    """`extract` is only ever called on a miss — a hit must not pay for loading a backend."""
    extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=Spy()
    )

    def _boom() -> ExtractedText:
        raise AssertionError("extract() must not be called on a hit")

    result = extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=_boom
    )
    assert result == SAMPLE


def test_two_kbs_holding_the_same_pdf_get_two_cache_files(tmp_path: Path) -> None:
    kb_a = tmp_path / "kb-a" / "cache" / "extract"
    kb_b = tmp_path / "kb-b" / "cache" / "extract"
    extract_cache.get_or_extract(
        kb_a, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=Spy()
    )
    extract_cache.get_or_extract(
        kb_b, content_hash="sha256:abc", backend="pypdfium2", fingerprint="fp1", extract=Spy()
    )
    assert list(kb_a.glob("*.json")) != []
    assert list(kb_b.glob("*.json")) != []
    assert kb_a != kb_b


def test_the_sweep_spares_paid_entries_and_reports_them(tmp_path: Path) -> None:
    """A paid extraction's entry has no matching active document (its source was soft-deleted, or
    never got a sidecar back) — the sweep must remove its free twin but never this one."""
    extract_cache.get_or_extract(
        tmp_path,
        content_hash="sha256:free-orphan",
        backend="pypdfium2",
        fingerprint="fp1",
        extract=Spy(),
    )
    extract_cache.get_or_extract(
        tmp_path,
        content_hash="sha256:paid-orphan",
        backend="claude-vision",
        fingerprint="fp2",
        extract=Spy(),
        operation_id="op-123",
        call_ids=["call-1", "call-2"],
    )
    extract_cache.get_or_extract(
        tmp_path,
        content_hash="sha256:still-active",
        backend="pypdfium2",
        fingerprint="fp1",
        extract=Spy(),
    )

    survey_before = extract_cache.survey(tmp_path, active_content_hashes={"sha256:still-active"})
    assert survey_before.entries == 3
    assert len(survey_before.orphans) == 1
    assert len(survey_before.paid_orphans) == 1

    found = extract_cache.evict_orphans(tmp_path, active_content_hashes={"sha256:still-active"})
    assert len(found.orphans) == 1
    assert len(found.paid_orphans) == 1

    remaining = extract_cache.survey(tmp_path, active_content_hashes={"sha256:still-active"})
    assert remaining.entries == 2  # the free orphan is gone; the paid one and the active one remain
    assert len(remaining.paid_orphans) == 1  # still there, still reported, never deleted


def test_a_corrupt_entry_is_left_alone_and_reported_not_removed(tmp_path: Path) -> None:
    """A paid entry can't be ruled out for a file that can't be read — so it is never swept."""
    junk = tmp_path / "not-json-at-all.json"
    tmp_path.mkdir(parents=True, exist_ok=True)
    junk.write_text("{not valid json", encoding="utf-8")

    found = extract_cache.evict_orphans(tmp_path, active_content_hashes=set())
    assert found.corrupt == (junk,)
    assert found.orphans == ()
    assert junk.exists()  # left alone, not swept


def test_clear_all_empties_everything_paid_or_free_active_or_orphaned(tmp_path: Path) -> None:
    extract_cache.get_or_extract(
        tmp_path, content_hash="sha256:a", backend="pypdfium2", fingerprint="fp1", extract=Spy()
    )
    extract_cache.get_or_extract(
        tmp_path,
        content_hash="sha256:b",
        backend="claude-vision",
        fingerprint="fp2",
        extract=Spy(),
        operation_id="op-1",
    )
    entries, total_bytes = extract_cache.total_stats(tmp_path)
    assert entries == 2
    assert total_bytes > 0

    removed, removed_bytes = extract_cache.clear_all(tmp_path)
    assert removed == 2
    assert removed_bytes == total_bytes
    assert list(tmp_path.glob("*.json")) == []


def test_total_stats_and_clear_all_on_a_directory_that_does_not_exist_yet(tmp_path: Path) -> None:
    missing = tmp_path / "never-synced" / "cache" / "extract"
    assert extract_cache.total_stats(missing) == (0, 0)
    assert extract_cache.clear_all(missing) == (0, 0)
    assert extract_cache.survey(missing, active_content_hashes=set()) == extract_cache.CacheSurvey(
        0, 0, (), (), ()
    )
