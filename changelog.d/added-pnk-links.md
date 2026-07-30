- **`pnk links` — what a document connects to, and what connects to it** (L4 of the links release),
  over a SQLite provider for L3's traversal core. One query per hop in a Python loop, never a
  recursive CTE: the caps live in the core, and a recursive query would have to re-implement depth,
  fan-out and dedup in SQL to honour them. Takes a ULID or the path `pnk search` prints; filters by
  `--rel` and `--direction`; `--depth` is server-capped at 3; `--query` ranks neighbours by
  similarity instead of by edge, and is the only mode that loads a model at all. Every neighbour is
  a document, and `kb_id` is always a ULID — never `[kb] name`, which is free to rename, and never a
  `[[links.kb]]` alias, which means nothing elsewhere. A neighbour in another KB is **terminal**:
  returned, never expanded, at any depth, and carrying no `title`, because this index holds that
  KB's links and not its documents. Links whose target is missing come back under `unresolved` and
  never as neighbours — the two lists are disjoint.
