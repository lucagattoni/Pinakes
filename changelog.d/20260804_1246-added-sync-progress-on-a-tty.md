- **`pnk sync` shows live progress on a terminal.** A CPU-only embedding run measured at ~2.4
  documents/minute — 300 documents ran over two hours with nothing printed, making a slow sync and a
  hung one look identical. `pnk sync` now prints `documents done/total` and a rate on one
  self-overwriting line, throttled to about once a second, whenever stdout is a real terminal and
  `-q`/`--quiet` was not passed; silent otherwise, so `--ci`, git hooks and piped output are
  unaffected. `sync()` itself does no terminal I/O — it drives an injected `SyncOptions.progress`
  callback, the same shape as the existing `ask` callback, so it stays testable without a tty.
