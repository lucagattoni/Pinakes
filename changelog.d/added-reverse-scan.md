- **`pnk sync` now records what other knowledge bases link *into* this one** (L2 of the links
  release). For each `[[links.kb]]`, it reads that KB's **committed sidecars** — never its index,
  which is gitignored, absent in a fresh clone, and unreadable without holding a second KB's lock —
  and writes the entries targeting this KB as inbound rows, filling `kb_refs` for the first time
  since the column existed. Only links targeting *this* KB are kept: a partner's link to a third KB
  is discarded rather than recorded as a graph this index could never complete. A partner's own
  `[kb] id` is what identifies it, and a mismatch with the `[[links.kb]] id` declared here scans
  nothing rather than guessing which is right. Replacing a partner's rows is all-or-nothing and
  happens only after a complete walk, so a sidecar that will not parse mid-scan leaves the
  previously known edges alone instead of deleting them; a KB dropped from `[[links.kb]]` has its
  rows and `kb_refs` entry removed, which nothing else would ever have done. The scan is bounded by
  a one-hour freshness window because `pnk sync` runs on `post-commit` and `post-merge`, and
  **`--scan-links`** ignores it. Every failure — unreachable path, id mismatch, unparseable
  sidecar, a target this KB does not have — is reported with a remedy and **does not fail the
  sync**: a partner that is simply not on this machine must not block every commit. The partner's
  own `[sources]` is honoured in full — `exclude` included, which matters because the shipped
  template stamps one — and a `roots` entry that has vanished, points outside the partner KB, or
  uses a pattern the walker rejects is a reported failure rather than a walk that quietly finds
  nothing and deletes what it had.
