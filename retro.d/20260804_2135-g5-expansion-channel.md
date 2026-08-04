## G5 — the expansion channel (20260804 21:35)

**HIGH — a ranking rule that would have made depth 2 unreachable, and it read as the careful
choice.** The channel's output is ordered and then cut at `candidates_per_source`. The first
implementation ranked `(distance, -cosine, …)`, on the reasoning that a two-hop chunk should not
outrank a one-hop one on similarity alone — which sounds like the conservative reading of APPROACH
§4A's *"score expanded chunks by edge weight and link distance"*. It is not conservative, it is
**silently disabling half the feature**: with distance as the primary key, every one-hop chunk
precedes every two-hop one, so on any corpus where one hop already fills the cut, depth 2
contributes nothing to the output at all. The channel would have been depth-1 wearing a depth-2
budget — and the reachability ceiling that unblocked this increment was measured at **two** logical
hops, so the gate would have been measuring something the precondition never covered. Now
`(-cosine, distance, …)`: cosine ranks, distance breaks the ties cosine cannot, and
`test_a_two_hop_chunk_outranks_a_one_hop_one_when_the_query_says_so` fails if the order comes back.

**HIGH — every tiebreak resolved to a surrogate id, and it looked stable because of another
module's `ORDER BY`.** Fan-out, frontier order and the final ranking all broke ties on
`nodes.id`. Those ids are deterministic today — but only because `edges.derive` enumerates
documents `ORDER BY path` — so the channel's answers depended on an invariant of a different
module, unstated in both. That is G1's defect in a new place: `_hydrate`'s unordered
`WHERE c.id IN (…)` was stable in practice too, until a rebuild moved one golden-set question.
Every tiebreak here now resolves to `(documents.path, chunks.ordinal)`, the total order G1 gave the
rest of the pipeline. **The lesson is not "avoid surrogate ids"** — it is that *"this is
deterministic"* is a claim about the code that computes it, and if that code is somewhere else, the
determinism is an assumption rather than a property.

**HIGH — a fixture that was not the shape its own docstring described, in the tests written to
catch exactly that.** The membership-exclusion fixture built one document of six flat sections, so
that ordinal 0 and ordinal 4 would be reachable *only* through their document's membership edge.
Its body was `f"## Section {i}\n\nword{i} " * 30` — which repeats the **heading** thirty times, and
produced 180 chunks nested under `Section 0 > Section 5`. A `parent-child` hierarchy, inside a
fixture whose entire purpose was to have none, in a file whose docstring names "an assertion
satisfied by something other than the property it names" as the failure it is written against. It
was invisible until an unrelated ordering change made the walk reach one chunk more. Two things
followed: dropping the `# Title` was **not** enough either — the chunker then reads the first `##`
as the root and derives `Section 0 > Section n`, the same defect one heading level down — and a
fixture that a test's meaning depends on now asserts its own shape (`_assert_flat_sections`: six
chunks, every heading path depth 1, zero `parent-child` edges). **A fixture is an assertion.**

**MEDIUM — a mutant that survived eighteen others, in the half of a rule the other half hides.**
The membership exclusion is two filters: a document never passes through to itself, and a root's
own document never contributes member chunks at any depth. Deleting the *second* left the whole
suite green, because at hop 1 the source **is** the root's document, so the first already covers
it — and no fixture ever reached a root document from somewhere else. The shape that does is
`A —authored→ B —authored→ {A, C}` at `adjacent_k=1`: at hop 2 the source is B, the first filter
does not apply, and without the second, A takes the only slot to re-contribute chunks the query
already had. **Two rules that agree on every case you have built are one rule until you build the
case that separates them.**

**LOW — a throwaway mutation harness produced two runs of contradictory results.** Mutating a
source file, running pytest and restoring in a loop reported extra failures in tests unrelated to
the mutated file, twice, while the machine was also running a two-hour re-index and an eval matrix.
Clearing `__pycache__` between mutants and running each mutant on a quiet machine gave seven clean,
reproducible results. The mechanism was not pinned down — a stale bytecode cache after a
same-second restore and a subprocess that failed to spawn under load are both consistent with what
was seen. Recorded because the *reaction* is the reusable part: a mutation result that implicates a
file the mutant did not touch is a result about the harness, and re-running it on a quiet machine
costs a minute.
