- **`docs/ROADMAP.md` — the whole development story on one page, written for a human.** A table of
  every release with its date, title and a short bullet summary, then one expanded section per row,
  then the unbuilt work with what blocks each piece. Unbuilt rows carry no number and no date, per
  the naming rule. It is published as chapter 4.1 of the site, ahead of `STATUS.md`.

  **It owns no fact, deliberately.** `STATUS.md` stays the only place that says what is built,
  `CHANGELOG.md` the exact record, `plans/` the build orders — this is a narrative view over the
  three, and `docs/README.md`'s routing table now says so in both directions: correct STATUS first,
  then sweep ROADMAP, never the reverse. The alternative — rewriting `STATUS.md` for readability —
  was rejected because it is machine-load-bearing (`tools/status_header_gate.py` parses its third
  line, CI reads its tables) and agent-facing reference, and a document cannot be both that and a
  narrative without serving neither.
