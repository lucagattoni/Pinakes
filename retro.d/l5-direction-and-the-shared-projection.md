### The defect was in the field nobody thought to assert (L5, the links release)

L5's own mutation pass killed all three of the targets the plan named. An adversarial review then
mutated **eight more** payload fields and watched every one survive the full 887-test suite. Two of
those were real defects, not merely untested:

- **`direction` was keyed by node, while a row is `(node, rel)`.** Given `a --related--> b` and
  `b --cites--> a`, asking about `a` reported the citation as running *from* `a` — the opposite of
  what someone wrote. Shipped in L4, copied verbatim into L5, wrong on both surfaces. The provider's
  own docstring argued the case for the key it used: *"Keyed by node, because a node reached both
  ways is still one neighbour"* — true of the node, irrelevant to the row.
- **`DIRECTIONS` was defined and never enforced.** `edges_of` tests `in ("out", "both")` and
  `in ("in", "both")`, so `direction="outbound"` ran neither query and returned a confident empty
  answer with a "no links from here" hint. `argparse` `choices` covered the CLI; the MCP surface,
  the one an untrusted model types into, had nothing.

**The lesson that generalises: a field with no assertion is a field that can be a constant.** Ask of
each one, "which mutation would this catch?" — not "is it correct?". `scored_by_query`, the field
L3's docstring calls load-bearing, could be frozen to `True`; `unresolved`, whose contract says
"returned, never dropped", could be frozen to `[]`.

**A tidy fixture defeats a mutation test.** Three fields survived even after tests were written for
them, because the KB-backed fixtures were too clean: the fake embedding backend's vectors are
orthonormal, so every cosine is exactly 1.0 and deleting `round()` changes nothing; nothing hit a
response cap, so `truncated` could be frozen empty; no frontier entry sat past distance 1. The fix
was to build the dataclasses directly and take the fixture out of the question.

**Two copies of one payload had already drifted** — the MCP `frontier` carried a `distance` the
CLI's did not, `scored_by_query` reached only one of them, `unresolved` dropped a `kb_id` its
sibling lists carried. Neither failed, because nothing compared them. They now share
`pinakes.graph.present`, and a test asserts both surfaces project the same keys.

**Calling a tool is not the same as exercising it.** The free-path gate was strengthened to *invoke*
`pinakes_links` rather than only list it — but the fixture KB had one document and no links, so the
whole neighbour projection never executed. A `raise SystemExit` planted in that loop never fired.
The fixture now authors one intra-KB and one unreachable-KB link, and the same probe fires.

**The fix for a wrong answer produced a differently wrong answer, and the tests written with it
could not see that either.** Keying `directions` by `(node, rel)` was right; merging to `both`
across *expansions* was not. `directions` accumulates over the whole walk, so an edge discovered
while expanding an unrelated parent rewrote a row already emitted from the start — and a row's
`direction` then changed with `--depth`, to exactly the untruth the fix was written to remove. Both
new direction tests ran at `depth=1`, where the start is the only parent, so neither could reach it.
A second adversarial pass found it by varying the one parameter the tests held fixed.

The generalisation: **when a fix adds a rule, test the axis the rule is defined over.** The rule was
about *which expansion* a direction came from, and every test pinned a single expansion.
