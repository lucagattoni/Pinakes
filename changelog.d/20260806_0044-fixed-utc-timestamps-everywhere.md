- **Every timestamp Pinakes writes is UTC — the last three naive-local sites are gone.** `pnk init`
  stamped `[kb] created` from the machine's wall clock, the paid extractor priced a document against
  a local `now`, and `pnk doctor`'s price-age check subtracted a naive local clock from a price
  table whose `as_of` is authored in UTC. Each was a different instant on a different machine, and
  none of them failed loudly: a KB minted in Europe and read in California simply disagreed about
  when it was made. `sync`, `lock`, the ledger and the accountant were already UTC, which is what
  made the remainder a **mixed** scheme rather than a consistent local one — the worse of the two,
  because two stamps in the same index no longer shared a zero point.
- **`is_stale()` compared a stamp it documented as local against a value `sync` had been writing in
  UTC.** The code was right and its docstring was wrong; the docstring now says UTC. Worth stating
  because the mismatch is invisible on a UTC machine and silent everywhere else.
- **Pinned by a test that fails on a naive clock, not merely on a wrong one**
  (`tests/test_init.py::test_created_is_utc_even_where_the_machine_clock_is_not`). It runs under
  `TZ=Pacific/Kiritimati` — UTC+14, chosen because the naive stamp lands on a *different date* for
  ten hours of every day, so the failure is loud rather than a rounding minute. Mutation-verified:
  reverting `init.py` to `datetime.now()` fails it with `created '20260806 14:41' is not the UTC
  instant (20260806 00:41..)`.
- **`[budget] timezone` is untouched and is not an exception.** It decides where a *daily* or
  *monthly* window starts for a user who wants their cap to reset at local midnight; the ledger
  still stores UTC and converts at read time, so no local time is ever written to disk.
