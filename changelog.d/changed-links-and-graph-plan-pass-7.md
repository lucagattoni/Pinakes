- `plans/links-and-graph.md` revised after adversarial pass 7 (6 HIGH across two reviewers), and
  the `pnk link` YAML question settled. L1–L8 are now implementable; G1–G6 are not — G5's gate
  clauses are re-reviewed before G5 is built. L2 was rewritten around four defects: a per-KB delete
  that turned any mid-walk failure into the mass deletion the same section forbids, a delisted
  partner whose rows no delete could reach, a scan that could not compute `src_kb_id` from sidecars
  at all (a sidecar does not carry its KB's ULID) and whose natural workaround would re-target a
  partner's `self` links at the local KB, and a failure taxonomy whose only recording channel makes
  `pnk sync` exit non-zero on a git hook. G5 was rewritten around two: the gate made the
  *without*-authored run binding while shipping the *with*-authored configuration, and G2's headroom
  threshold never said which of its two reachability numbers licensed an irreversible
  `schema_version` bump.
