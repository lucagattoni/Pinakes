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

**HIGH — the first `edge_census` design counted every hub bucket, so `co-located` and
`shared-tag` could never report zero on a corpus with documents in it, which is exactly the case
the feature exists to surface.** Found by an independent adversarial-review pass (a fresh agent
given the diff and the requirement, not the implementation reasoning), not by the author: a
directory holding one document, a tag on one document — `plans/20260803_2239-corpus-probe-run.md`
itself calls this shape "most dirs connect nothing" — still contributed its member count to the
sum, because `sum(len(members) for members in hub.values())` does not care how large each bucket
is. A corpus with real documents and zero shared structure would have printed a large positive
`co-located`, the opposite of what the census exists to show. Fixed by excluding buckets of size
one (`_spoke_count`, `tools/reachable_ceiling_probe.py`) — a bucket with nothing else in it
derives no edge. **The reviewer also showed the first reconciliation test could not have caught
this**: its "independent" expectation was `sum(len(members))` over the *same* kind of total
(document count, tag-row count), which is invariant to which bucket each item lands in — a
grouping bug and a correct grouping produce the same sum. The fixed test computes its own
per-bucket sizes from the raw tables and applies the same size-two-or-more filter, so a fixture
now needs at least one real multi-member bucket **and** at least one genuine singleton bucket
(`docs/alone/solo.md`, deliberately alone) to mean anything.

**HIGH — the first reconciliation fixture could not have caught a wrong `parent-child` formula,
twice.** 900 words replaced an initial 240: at 240 words per heading section, structural chunking
produced exactly one chunk per `heading_path`, so every `groups[a] * groups[b]` term was `1 * 1`,
and a flat `+= 1` per group-pair passed unnoticed. Raising every group to 900 words moved every
group to size **2**, not different sizes — and `2*2 == 2+2`, so the *next* plausible wrong formula
(`groups[a] + groups[b]`) also passed unnoticed; the adversarial review caught this one, mutating
the multiplication to addition and finding the test still green. Fixed with three *unequal* group
sizes (2, 3, 5 chunks, from 800/1300/2000 words against `max_tokens = 510`) chosen so no pairwise
sum equals the corresponding product. The general form, twice-demonstrated: a fixture built to be
"nonzero" is not a fixture built to distinguish the correct formula from the plausible wrong ones
near it, and "I already raised the fixture size once" is not evidence the new size clears every
nearby coincidence — each candidate wrong formula has to be checked against the actual numbers
chosen, not assumed defeated by "bigger."

**MEDIUM — the first `authored` reconciliation counted `links` rows; `edge_census` counts unique
pairs.** `graph.authored` is a `set` per document, so two `rel`s between the same two documents
(both legal — `pnk link` refuses only an identical `(target, rel)` pair, not a second relation
between the same target) still count as one edge. The first test's "independent" expectation
filtered and counted rows, which happened to agree only because the original fixture had no
document pair linked twice. Fixed by comparing unique `frozenset({src, dst})` pairs instead of
rows, and the fixture now deliberately links one pair twice with different `rel`s to make the
distinction observable.

Common thread across all three: an adversarial reviewer with no stake in the implementation asked
"would this test's expectation still be right if the code grouped things differently, or if the
same edge were recorded twice?" — a question the author, having just written the grouping code
being tested, did not think to ask about their own logic.
