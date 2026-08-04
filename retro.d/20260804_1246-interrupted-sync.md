## Interrupted sync — a TZ test that used the fixture helper would have proven nothing (20260804 12:46)

**HIGH — the first draft of the UTC-timestamp regression test called `test_sync.py`'s own `run()`
helper, which hardcodes `now="20260725 16:00"` for every other test in the file specifically to
bypass the real clock.** `sync.py:709`'s `stamp = now or datetime.now(UTC)...` only reaches the
real-clock branch when the caller passes `now=None` — and `run(kb, ...)` never does, because that
fixed string is what makes 60-odd other tests in `test_sync.py` deterministic. A TZ test built on
top of `run()` would set `TZ`, call `run(kb)`, read back `meta['built_at']`, and find it exactly
`"20260725 16:00"` regardless of which clock `sync.py` actually used — passing identically whether
the site under test read `datetime.now()` or `datetime.now(UTC)`, because neither ever ran. Caught
before committing by asking the same question the increment's own instructions insist on for the
mutation pass: does the assertion distinguish the fixed from the broken code, or only look like it
does? Fixed by calling `sync()` directly with no `now=` override in both TZ tests
(`test_a_real_sync_stamps_utc_not_local_under_a_non_utc_timezone`,
`test_estimate_only_stamps_utc_not_local_under_a_non_utc_timezone` — the second reaches its own
independent clock at `sync.py`'s `_estimate_only`, unaffected by the outer `now=` either way, so it
needed no such change but is named here for the record) — and mutation-verified afterward by
reverting each site to `datetime.now()` and confirming the corresponding test failed by roughly the
test's chosen offset (`Pacific/Kiritimati`, UTC+14), not merely failing.

**The general rule this confirms rather than discovers:** a test helper that fixes an input to make
most tests deterministic is exactly the place a new test targeting *that specific input* must not
reuse the helper — the fixture built to remove non-determinism from one property will just as
readily remove the property a new test exists to observe. `docs/RETROSPECTIVES.md`'s own advice on
claiming a test is mutation-verified — run the mutant, don't just trust the assertion reads
correctly — is what caught this one before the mutation pass would have had to.
