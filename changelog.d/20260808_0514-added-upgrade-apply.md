- **`pnk upgrade --apply` adopts the template changes that fit, after showing you all of them.** It
  writes every hunk that applies cleanly, skips the ones already in your file, and **refuses the
  whole run if any hunk conflicts** — a half-upgraded manifest with no record of which half is worse
  than an unupgraded one. It is the only thing in Pinakes that rewrites a `pinakes.toml` after
  `pnk init`, and it is bounded by what it printed: nothing reaches the file that was not on screen
  first. Your previous manifest is copied to `pinakes.toml.orig`, whose path is printed along with
  the warning that nothing ignores it — `pnk init`'s `.gitignore` covers `.pinakes/` only. It
  re-reads what it wrote and restores the original if it does not load, refuses while a sync holds
  the KB, and refuses a manifest whose line endings are not uniform rather than leaving a mixture
  nobody chose (a uniformly CRLF file stays CRLF). It updates exactly one key outside the hunks —
  `[kb] template` — and refuses rather than guessing where it belongs. It never syncs, re-chunks or
  re-embeds; when an applied key is one your index was built under it names the key and points at
  `pnk sync --rebuild`.
- **A `[budget]` default is applied like any other change, and both commands print the cap first.**
  A spending cap that would move is printed under its own labelled heading with the old value and
  the new one, by `pnk upgrade` and `pnk upgrade --apply` alike, before anything is written — and
  the heading appears **only** when a cap really would move, so its absence is information too. A
  raised cap is permission, never spending: the free extractor stays the default.
- **`pnk upgrade --apply` never writes `[kb] requires_pinakes`.** When applied hunks introduce keys
  it names them and says you may want a floor set by hand. It suggests no version: nothing in
  Pinakes maps a manifest key to the release that introduced it, so a printed `>=x.y.z` would be a
  guess wearing a decimal point. An existing value is left byte-identical.
- **Exit codes:** a conflict still exits `0` from `pnk upgrade` — a report has nothing to fail at —
  and exits `1` from `pnk upgrade --apply`, which was asked for a write it could not make. `cannot
  compare` stays `3` under `--apply` and writes nothing, which is what **every KB that predates the
  version archive** gets. `--json --apply` emits one document carrying either `applied` or
  `refused`, and every payload now carries a `spend` array.
