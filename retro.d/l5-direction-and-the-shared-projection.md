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

**A third pass found no new defect in the traversal itself, and four in what surrounded it.** The
`(node, rel)` scheme was probed against a reciprocal pair, a mutual same-rel pair, each `direction`,
a self-loop, a 3-cycle, a node reached at two different hops by different relations, a node reached
by two parents in one hop with opposite directions, and a node dropped by fan-out then re-reached —
all correct. What was still wrong sat one layer out: an assignment nobody asserted, a message worded
from the wrong end, a branch ordered ahead of a better one, and an assertion satisfied by a
substring.

Two of those are worth naming as patterns:

- **`assert "-> related: b" in output` passed on `<-> related: b`.** A substring assertion over
  rendered text will match a *longer* glyph containing the shorter one, so dropping the outbound
  arrow entirely left the test green. Match whole lines when asserting on human output.
- **Splitting `f(x, scores=s)` into `f(x); f.scores = s` moved a value out of the type checker's
  reach.** The construction was covered by the tests that built providers directly; the assignment
  was covered by nothing, and deleting it disabled query ranking with every gate green. When a
  refactor turns an argument into a mutation, the mutation needs its own assertion at its own call
  site — and there were two call sites.

**Left for the graph release** (L3 core, predating this increment, found while probing): a node
dropped by fan-out at hop 1 and re-reached at hop 2 is emitted with `distance: 2` although it is one
authored hop from the start; and a self-loop (`a --sameas--> a`) is dropped entirely — not a
neighbour, not unresolved, not on the frontier.

**A fix applied to one surface is half a fix.** Round 3 gave `pinakes_links` the rule that a
narrowed walk reports the narrowing before it reports dangling links — and left `pnk links` branching
on `unresolved` alone, in the same commit, so the CLI told a user their links "resolve to nothing"
about a document with a live neighbour one dropped `--rel` away. Both the docs and the changelog
described the MCP behaviour as though it were both. The two surfaces now share
`present.is_filtered` and `present.arrow`, which is the only way this stops recurring: the rule has
to live in one place, not be applied twice.

**A remedy in an error message is a claim, and it was false.** The dangling-links hint sent the
caller to `pnk doctor` — but `doctor._links` inspects only the *destination* side of local sidecar
rows, so when the missing endpoint is the link's **source** (a deleted document whose outbound rows
survive the soft delete) doctor reports `links: OK` and contradicts the message that sent you there.
Dropped the clause; extending that check belongs to L7, which owns doctor's link coverage.

Four review rounds, each finding real defects in the previous round's fix, then converging: 11
findings, then 11 with one HIGH, then 7 with none, then 5 with none. What the last two rounds found
was never the traversal — it was the layer around it: an assignment nobody asserted, an assertion
satisfied by a substring, a message worded from the wrong end, a branch ordered ahead of a better
one, and a rule applied to one of two surfaces.

**The rule two rounds were spent getting right had no test that could detect its inversion.** Round
5 found the shipped behaviour correct on both surfaces and the precedence — *filter before dangling
before "no links"* — freely reversible with the suite green. The cause was a fixture that could not
make both conditions true at once: `--rel` narrows `provider.unresolved` as well as the neighbours
(`edges_of` receives the same `rel`), so a rel-filtered call leaves `unresolved` empty and the
branch being out-ranked never competes. `--direction` is the lever that does it — an outbound link
that dangles and an inbound one that is live. The assertion that named the defect in its own message
(*"one dropped argument away from a live neighbour"*) was the vacuous one.

**Test the discriminating case, not the two sides separately.** A precedence rule is only observable
where both branches are eligible; a fixture that satisfies one at a time asserts the wording of each
and the order of neither.
