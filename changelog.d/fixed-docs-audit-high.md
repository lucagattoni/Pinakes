- **Nine wrong public claims corrected, found by a full documentation audit against the code.** The
  README told readers `pnk link` was "still to come" — it shipped in 0.6.0. `docs/GUIDE.md` said
  twice that *"nothing here spends money, and nothing can"*, three lines below the row instructing
  `--extract=claude-vision`; `docs/MANIFEST.md` said the budget was inert. Both have been false
  since 0.3.0. `docs/CLI.md` published an exit-code contract giving `2` for an unknown backend name,
  which exits `1`. `docs/MANIFEST.md` gave the wrong base for `[sources] include` — patterns are
  relative to each `roots` entry, so the documented `docs/**/*.md` under `roots = ["docs/"]` indexes
  nothing — and said an alias in a sidecar link resolves on write when it is a hard error at read.
  `docs/graph/README.md` said "nothing here is built" of research whose links release shipped.
