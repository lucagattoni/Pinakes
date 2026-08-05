- **`pnk doctor` reports the highest-degree structural edge hubs (G6).** Degree is read, never
  stored — G3 deliberately keeps no `degree` column — so the check reuses `hub_degree()`, the same
  indexed `count(*)` the expansion channel damps by, over every `in-section`, `co-located` and
  `shared-tag` hub node. Always `Status.OK`: a big hub is not a problem on its own, since G3's
  weight table damps it at read time, so this is report-only.

  Report-only means human-readable. A `tag` or `dir` node's key already is the value worth
  printing; a `heading` node's key is `<doc-ulid>:<heading_path>` (G3), scoped per document, and
  is resolved here against `documents.path` before it is printed — a bare `nodes.id` or a raw ULID
  pasted into an issue identifies nothing. A KB deriving no hub edges reports `none`, cleanly,
  rather than an empty table with only a header.
