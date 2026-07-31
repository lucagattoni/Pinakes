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
  `!!seq` and `!!map` all worked before and still do.

  **Separately, four shapes whose unhandled `TypeError` becomes a named error** — `!!binary`,
  `!!set`, `!!timestamp` and a bare date all crashed `pnk sync` out of `json.dumps` before, and are
  now refused at `read()` with a remedy. That is a fix, not a break.

  **A documented widening:** a *custom*-tagged mapping or sequence (`!custom {a: 1}`) was a parse
  error and is now accepted, because it serialises. Not `!!map`/`!!seq`, which were never refused.
