- **`pnk sync`'s own timestamps are UTC, matching `sync.lock`'s.** `sync.py` stamped
  `datetime.now()` (local) while `lock.py` already stamped `datetime.now(UTC)` — identical
  `YYYYMMDD HH:MM` format, no marker, different clocks. In a zone ahead of UTC a lock taken seconds
  ago could read hours old next to a `sync.py`-written timestamp from the same moment, which is the
  evidence a user weighs before `pnk sync --force-unlock` — the risk being a force-unlock against a
  sync that is still running. Both `sync()`'s own stamp (written into `meta['built_at']`, every
  sidecar's `created`, and every failure's `happened`) and `--estimate-only`'s price-staleness clock
  are now `datetime.now(UTC)`.
