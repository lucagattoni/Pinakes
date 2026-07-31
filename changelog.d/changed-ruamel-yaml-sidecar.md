- **`ruamel.yaml` replaces `pyyaml` for reading and writing sidecars.** A rewrite now preserves
  comments, quoting style, block scalars and blank lines, because `write()` reconciles the known
  keys *into the document that was read* rather than rendering a fresh one. `pyyaml` leaves
  `[project.dependencies]`; the dependency count is unchanged.

  This also fixes a silent corruption that had nothing to do with comments. `Sidecar.extra` is
  documented as *"round-tripped untouched"* and was not: under YAML 1.1, `country: NO` was read as
  `False` and written back as `false`, `shelf: 0755` became `493`, `confirmed: yes` became `true`
  and `duration: 1:30` became `90`. YAML 1.2 reads them as the strings they visibly are.

  **Three breaking changes**, all consequences of the library. A **duplicate key** is now a hard
  error rather than silent last-wins — which of the two values was meant is not recoverable, and
  ruamel's own message ends with a URL for switching the check off that pinakes deliberately does
  not pass on. A **string field that YAML 1.2 resolves as a number** (`1e3`, `1E3`, `0o17` in
  `title`, `created`, `tags[]`, `links[].to`, `links[].rel`) is refused. And an **`!!str`-tagged
  value** is refused — the only *working* tag that changes behaviour; `!!int`, `!!float`, `!!bool`,
  `!!seq` and `!!map` still load to the same values they always did, though the tag itself is not
  written back (`!!int 3` comes back as `3`).

  **Separately, four shapes whose unhandled `TypeError` becomes a named error** — `!!binary`,
  `!!set`, `!!timestamp` and a bare date all crashed `pnk sync` out of `json.dumps` before, and are
  now refused at `read()` with a remedy. That is a fix, not a break.

  **A documented widening:** a *custom*-tagged mapping or sequence (`!custom {a: 1}`) was a parse
  error and is now accepted, because it serialises. Not `!!map`/`!!seq`, which were never refused.

  **One regression, named rather than fixed.** A sidecar whose value contains a *self-referential*
  anchor (`mine: &x` with `b: *x` inside it) used to crash `pnk sync` with `Circular reference
  detected` when the index serialised it. It is now silently read as `null`, and the anchor and
  alias do not survive the next write. Pathological input, and the only place this change trades a
  loud failure for a quiet one — which is the direction that matters, so it is written down.

  **A non-string key at the top level of a sidecar is now refused**, with a remedy. It used to crash
  `pnk sync` from inside the index writer.

  **A reused anchor name is refused**, as it was before the swap. The new parser accepts it and
  resolves every alias to the *last* anchor of that name — so `a: &dup 1`, `b: &dup 2`, `c: *dup`
  would have made `c` equal 2 — reporting it only as a warning on stderr.

  **A `links:`, `tags:` or `provenance:` key with nothing under it no longer crashes a write.**
  `links:` alone — what a sidecar carries before its first link is added — raised an unhandled
  error out of `pnk sync`, including the write that follows a paid extraction.
