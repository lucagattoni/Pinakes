## T5 — The plan asked for a decision the file next to the code had already taken (20260808 06:28)

**HIGH — D-4 was open in the plan and settled in `manifest.py`, three lines below the tuple it was
about.** The plan spent a four-option table, a recommendation and a paragraph of D-12 cross-reference
on "what happens to `vector_tier = "sqlite-vec"` before the tier exists", and framed the choice as
turning on a judgement about `docs/MANIFEST.md`: is its row a promise or a disclosure? Meanwhile
`GRAPH_CHANNELS`' docstring, at `manifest.py:52` against `VECTOR_TIERS` at `:51`, already stated the
answer as a rule — *"a manifest that can ask for a mode the code does not implement is a manifest
whose setting silently does nothing, and `table.choice` refusing the name is how a user finds that
out at load time"* — and applied it to `"ppr"`, a value in the very next row of the same
documentation table. The plan cites neither.

**What that changes about reading a plan.** A plan's decision table is a list of questions its
author could not answer *from the plan*, which is not the same as questions the repository has not
answered. Two of the plan's four open recommendations here were about consistency with existing
behaviour, and the cheapest evidence for both was adjacent to the line being changed. The habit
worth keeping: before weighing a plan's options, look at what the sibling key does — the file is
often more decided than the document about it.

**MEDIUM — the plan's own two halves disagreed about what T5 could deliver.** It asked for
`resolve_tier` to be called by *both* `sync` and `search`, "so `meta`'s claim and the code path
cannot disagree", and then admitted two paragraphs later, correctly, that "with exactly one real
tier there is nothing else to discriminate". Both cannot hold: if there is nothing to discriminate,
`search` has no dispatch to make, and a `tier` parameter threaded into `_vector` that can hold one
value behind an unreachable branch buys a *shape* that looks like a shared decision while being
decoration. Built the resolver with one caller and said so in its docstring. This is the eighth of
the template-release plan's own measurements or specs to be wrong, and the second found by building
rather than by reading it.

**A smaller one, on honesty in a one-tier world.** The first draft of `resolve_tier` was
`return "numpy"` — correct, and a function that ignores its only argument. It became
`return "numpy" if tier == "auto" else tier`, which reads the manifest and honours an explicit
tier. Today both arms return the same string, so no test can tell them apart; what the second form
buys is that the increment restoring `"sqlite-vec"` gets it honoured by that line and owes only
`auto`'s side of the choice. Worth the branch; not worth pretending a test covers it.
