## G5 — a root spends a fan-out slot it is then discarded from (20260804 22:30)

**HIGH — the fourth review round, on a rule the third round had already written down.** Round three
added a filter to `_offer_chunks` dropping candidates already found this hop or already emitted by
an earlier one, with the reasoning stated in the comment: *"a slot spent on it adds nothing, and
dropping it before the cut is the same rule the membership exclusion applies one level up"*. The
rule is right. It was applied to two of the **three** categories it covers.

A **root** reaching `found` is discarded twice over. `_accept` skips it before emitting, and `run`
seeds `self._expanded` with the roots so it never joins the frontier either — so a root contributes
neither a row nor a hop. Yet it had already taken one of the `adjacent_k` slots on the way, and the
neighbours of a fused top-*k* chunk are very often *other* fused top-*k* chunks: `sibling` connects
adjacent ordinals, and adjacent ordinals of a chunk the query matched are exactly what the vector
stage also ranked highly.

Measured on `graded_neighbour` at the shipped default `adjacent_k = 8`: **4 candidates returned as
built, 10 with roots dropped before the cut** — and all six of the new ones are chunks fusion had
not found, which is the only thing the channel exists to contribute.

**Why it survived three rounds.** Every existing assertion about roots was set-level — *"neither
root may be emitted"*, *"expansion still runs"* — and a set-level assertion cannot tell a slot
spent from a slot saved. Both are satisfied by the defective walk. The test that catches it counts
instead: `adjacent_k = 1`, two candidates, one of them a root, and the single slot must reach the
non-root. With the filter removed the walk returns `[]`, which is the failure mode named in the
assertion's own message.

### What the fix is worth, and where that cannot be seen

`tests/demo-kb` moved **zero questions** across all three gate legs — off, `expand`,
`expand-no-authored` — with aggregates identical to four decimal places. That is not evidence the
fix is inert: demo-kb's documents are about two chunks each, so `adjacent_k = 8` never saturates
and a root never displaces anything. **A corpus can be incapable of exercising a change**, and
reporting "no movement" from one is reporting the corpus, not the code. The RFC realism corpus —
300 documents, 106 806 chunks — is where the fan-out cut actually binds, and it is the corpus the
gate runs on.

### The backstop that now survives mutation, on purpose

`_accept`'s `if node in self._roots: continue` is unreachable once `_offer_chunks` filters. It
stays: *"a root is never emitted"* is an invariant of the emit point, and a later caller adding a
second way into `found` should not be able to break it from a distance. The honest consequence is
recorded in the docstring and in the mutation table — **deleting that line fails no test**, while
deleting the `_offer_chunks` filter fails exactly one. A backstop whose mutant survives is fine;
a backstop silently *counted* as the enforcement is not, which is the same
assertion-satisfied-by-something-else failure in its bookkeeping form.
