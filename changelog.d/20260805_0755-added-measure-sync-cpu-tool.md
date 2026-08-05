- **`tools/measure_sync_cpu.py` measures how many cores a long-running command actually keeps
  busy.** Built for item 6 of `plans/20260731_1202-open-corrections.md`, which required a real
  cores-busy measurement of `pnk sync`'s document loop, per backend, before anything about it could
  change. Not a CI gate — an operator tool, run by hand: `python3 tools/measure_sync_cpu.py
  --interval 1 -- uv run pnk sync --kb <path> --rebuild`, reporting wall-clock, peak and mean
  `%cpu` (macOS-per-core), and the same numbers converted to cores.
