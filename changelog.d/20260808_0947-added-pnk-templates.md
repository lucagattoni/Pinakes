- **`pnk templates` — what this build can stamp a KB from.** Name, version and description for
  every installed template, with `--json`. It takes no `--kb`: the answer is a property of the
  install, not of a KB. Until now `template.available()` was reachable only through the error raised
  by `pnk init --template` naming something that does not exist, so the way to discover what was
  installed was to get something wrong first. **CLI-only, decided 20260808** — there is no
  `pinakes_*` tool for it: the MCP server answers about the KBs it was pointed at, and creation has
  no MCP surface, so such a tool would list templates its caller has no way to use.
