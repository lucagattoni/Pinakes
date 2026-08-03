- **`tools/status_header_gate.py` — `docs/STATUS.md`'s header can no longer drift from the
  released version.** Line 3 must start with exactly `**Latest release: x.y.z**` and name
  `pinakes.__version__`; a missing, moved or reformatted line fails as loudly as a wrong version.
  Wired into `check.sh` and its own CI job with a negative check proving it can still fail. The
  header had drifted for four consecutive releases (0.5.0 → 0.7.1) while the release sweeps
  updated every table below it — a checklist missed it four times, which is this project's
  threshold for turning an item into a gate. Only the version is gated, never the `last reviewed`
  date beside it: a wall-clock staleness check would fail a quiet weekend with no code change.
