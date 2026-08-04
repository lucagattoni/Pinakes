## The edge census — a `.get` default that would have hidden its own defect (20260804 11:25)

**MEDIUM — the first draft of the text renderer used `report.edges.get(kind, 0)`, which is exactly
the failure class this feature exists to prevent.** The whole point of `edge_census` is that a kind
missing from the dict must never read the same as a kind genuinely at zero. `_render`'s first draft
indexed the dict defensively, so if `edge_census` ever regressed to drop a kind — a renamed key, a
kind skipped by mistake — the printed table would still show `kind 0`, silently correct-looking,
while the JSON output (built with `dict(self.edges)`, no default) would be missing the key outright.
Same bug, two output formats disagreeing about whether it happened. Caught before committing, by
asking what a reviewer would ask: "would this line notice its own input being wrong?" Fixed to
`report.edges[kind]` — direct indexing, so a dropped kind crashes loudly in text output too, matching
JSON. **The instinct to make a formatter defensive is usually right and was wrong here**: this
formatter's job is to report a fact `edge_census` promises to supply completely, and a default that
papers over the promise being broken is worse than a crash — the same lesson
`docs/RETROSPECTIVES.md`'s *reachable-ceiling probe* retro already drew about the probe's inputs,
recurring one layer up, in the probe's own output code.

**LOW — the first reconciliation fixture could not have caught a wrong `parent-child` formula.**
900 words replaced an initial 240: at 240 words per heading section, structural chunking produced
exactly one chunk per `heading_path`, so every `groups[a] * groups[b]` term was `1 * 1`. A mutation
that replaced the multiplication with a flat `+= 1` per group-pair passed every test unchanged,
because the two formulas agree whenever every group has size one. Only mutation-testing the
reconciliation test itself — not just running it green — surfaced this: a fixture built to be
"nonzero" is not the same as a fixture built to distinguish the formula from a simpler wrong one.
The general form: when a test's fixture data happens to sit at a value where two implementations
agree (here, group size 1, where `a*b` and `a+b-1` and a flat count all coincide), a reconciliation
test only proves agreement at that value, not correctness of the formula. Worth checking, for any
future fixture built to "exercise a nonzero code path": whether the nonzero value chosen is large
enough to separate the correct formula from the plausible wrong ones nearby.
