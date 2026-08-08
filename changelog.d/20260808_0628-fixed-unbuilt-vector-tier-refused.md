- **Breaking, and deliberately in a patch: `vector_tier = "sqlite-vec"` is now refused, and a KB
  whose `pinakes.toml` sets it stops loading entirely — every command, not only search.** The fix is
  one line, `vector_tier = "auto"`, and it changes nothing about how that KB behaves: the value was
  accepted and then ignored, so such a KB was already getting the NumPy tier. `sync` stamped `numpy`
  into the index's `meta` whatever the manifest said and `search` never read the field, so the
  setting was silent on all four surfaces — `sync`, `search`, the index's own record, and
  `pnk doctor`. The error names the tiers that are built and points at `docs/STATUS.md`. The value
  returns when the tier it names is built, in the template release; its removal is a fix, not a
  decision against it. The precedent for hard-erroring a manifest that previously loaded is this
  project's own 0.7.1, on the same reasoning: the previous behaviour *was* the defect.
- **The index's `vector_tier` is written from the resolver that decides it, not from a literal.**
  `sync.py` hardcoded `"numpy"` while `[retrieval] vector_tier` was a parsed field nothing consumed,
  so `meta`'s claim and the code path had no reason to agree beyond there being one tier.
  `search.resolve_tier()` is now the single answer to which tier ran.
