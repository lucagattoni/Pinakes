## The progress printer's closing newline assumed the loop always reaches its own end (20260804 13:07)

**MEDIUM — an independent adversarial review found that `cli._progress_printer`'s "finished" branch
(`done >= total`) is the only place the printer ever emits its closing newline, and `_run`'s loop
(`sync.py`) does not always reach `done == total`.** A `[budget]` cap or any early exit stops the
loop partway through, so the last `progress(done, total)` call for that run has `done < total`, and
the printer's `\r`-prefixed line is left open — no trailing newline — for whatever prints next
(`print_sync_report`, or an error message on an unhandled exception) to land on. Confirmed live: a
progress line followed immediately by report text on the same terminal row. No test in the original
commit exercised `done < total` as a run's *last* call — `test_progress_printer_throttles_...`
always ended at `done == total`, and the progress-callback sync test never triggered an early stop.

Fixed by splitting `_progress_printer()` into `(progress, finish)`: `progress` behaves as before,
but also tracks whether a line is open (`dirty`); `finish` closes it with one newline if so, and is
a no-op otherwise. `run_sync` calls `finish` unconditionally in a `finally` around the `sync()`
call, so it closes the line whether the run finished normally, stopped on a budget cap, or `sync()`
raised. Mutation-verified: made `finish()` unconditionally clear `dirty` without printing;
`test_progress_printer_finish_closes_a_line_an_early_stop_left_open` caught it (expected `"\n"`,
got `""`).

**The general shape of the miss:** a "does this print the right thing" test that only drives the
happy path (the loop's *last* call always being its *final* call) cannot see a defect that only
exists on an early-exit path, because the assertion and the code under test share the same
unstated assumption — "the loop reaches `done == total`" was never itself questioned, only how the
printer behaves once it does.
