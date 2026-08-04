## G3 — the node model and the edge set (20260804 16:30)

**HIGH — a hierarchy derivation that was quadratic in a *document's* chunk count.** `parent-child`
was derived by testing `child.heading_path.startswith(parent.heading_path + " > ")` over every
chunk pair within a document. Measured on one document: 2 000 chunks 0.23 s, 4 000 chunks 0.85 s,
8 000 chunks 3.32 s — so a single 32 000-chunk document (one long PDF) would have spent ~50 s
deriving, on a path `pnk sync` runs from three git hooks. Replaced by grouping chunks by heading
path and having each path look up its own ancestors (`" > ".join(segments[:d])`), which is the same
relation and is linear in chunks: 32 000 chunks now 0.59 s. **The corpus that would have exposed
this is the one that cannot**: the RFC realism corpus has an empty `heading_path` on every chunk, so
its 106 806 chunks derived zero hierarchy edges and cost nothing. A performance defect invisible on
the only corpus at scale.

**HIGH — a mutant that nothing caught, in a filter that looked redundant.** `authored_pairs`
filters `links` on `src_kb_id = ? AND dst_kb_id = ?` and then joins both ends to `doc` nodes.
Changing the `AND` to an `OR` failed no test, because the join already drops a foreign document
ULID — a foreign document has no local `doc` node. That reasoning is wrong in exactly one case, and
it is a case that happens: **fork a KB** — copy the directory, mint a new `[kb] id`, and every
document keeps its permanent ULID. A reverse scan of the fork then writes
`(fork_kb, D, local_kb, E)` where `D` is *also* one of our documents, and the `OR` reads it as "our
D cites E" — an edge nobody authored here. The lesson generalises: **a filter that a second filter
appears to make redundant is only redundant under an assumption, and the assumption is the thing to
test.** Pinned by `test_a_forked_kb_sharing_a_document_ulid_does_not_forge_a_local_authored_edge`,
which builds two real KBs rather than inserting the row.

**MEDIUM — the deriver was cross-checked against the instrument the go decision was measured on,
and this was worth more than any single test.** `tools/reachable_ceiling_probe.py` derives the same
relations in memory, written independently. Comparing the two censuses on `tests/demo-kb`
(`test_the_stored_edge_set_agrees_with_the_probe_the_decision_was_taken_on`) caught two mutants no
targeted test did, and the RFC corpus reproduced the go decision's drop table exactly — `sibling`
106 506, `shared-tag` 643, `co-located` 262. A second implementation of the same spec is a cheaper
oracle than a third round of hand-written assertions, and it answers a question no assertion can:
*did G3 build the graph G2 measured, or a different plausible one.*

**MEDIUM — the plan's orientation rule, read literally, makes every hub unreachable.** G3's spec
says the provider queries "`src = ? OR dst = ?` for those kinds and `src = ?` for hub kinds". A hub
spoke is stored hub-first, so `src = ?` answers "who is in me" — and a member asking "what am I in"
needs `dst = ?`. Read literally, no member could ever enter a hub, and `co-located`/`shared-tag`
are the two kinds the go decision measured carrying all nine liftable questions. The sentence's real
content is the *symmetric* half: a `src`-only read of a symmetric kind silently drops half of every
relation. Built as three explicit functions — `peers()`, `members()`, `hubs()` — so the two halves
of a hub kind cannot be confused for one query, and pinned by
`test_a_hub_is_entered_from_a_member_and_expanded_from_the_hub`.

**HIGH — a kind selection that could be silently dropped, in the function that preaches against
it.** `peers()`/`neighbours()` took `local_kb: str | None = None` and skipped `authored` when it was
absent — the same "confident, wrong, smaller answer" its own docstring warns about for a `src`-only
read, from the other side. G5's gate runs *with* and *without* authored edges; a caller who forgot
the keyword would have got the "without" arm believing it ran the "with" one, and lost the
highest-trust edge class with nothing printed. Now a `TraversalError` naming
`select_kinds(drop=["authored"])` as the way to mean it. **`select_kinds()` refusing an unknown name
was designed against exactly this and did not cover it** — the refusal guarded the *name* and left
the *ingredient*.

**MEDIUM — every corpus that certifies this increment has two of the six kinds at zero.**
`parent-child` has derived zero edges in every measurement ever taken here — one-level headings in
both committed corpora, an empty `heading_path` throughout the RFC corpus — and no committed sidecar
carries a `tags:` key, so `shared-tag` is exercised only by synthetic fixtures. The cross-check
against the probe therefore *passed with `_hierarchy_edges` deleted*, because its non-vacuity guard
was a total over all kinds. Fixed by asserting each compared kind is non-zero and naming the two
this corpus cannot exercise, so a kind that silently stops deriving fails rather than reads as
agreement. **A "total > 0" guard on a per-item comparison is not a non-vacuity guard** — it is one
item's evidence spread over all of them.

**MEDIUM — `parent-child` is materialised pairwise, and its row count is the product of two
sections.** APPROACH §3 keeps hierarchy direct — *"the one relation that stays direct"* — so an
ancestor heading of *a* chunks and a descendant of *d* chunks is a·d rows. Measured at
`max_tokens=400` on plausible document shapes: 5.8×, 16.3× and 53.5× the chunk count. Extrapolated
to 300 documents of the worst shape that is ~10 M rows. Not changed here — hubbing it contradicts
APPROACH §3 and restricting it to the immediate parent narrows the relation the go decision's probe
measured — but pinned by a test that asserts the arity, and reported to the planner as a spec
question rather than absorbed as an implementation choice.

**LOW — a duplicated tag inflated a hub's member count where nothing could see it.** `derive`
collects edges into a `set`, so `tags: [t, t]` produced one spoke — but `_tag_buckets` appended the
document twice, and the `< 2` minting rule counts the *bucket*. A single document repeating one tag
therefore minted a hub with one spoke and a divisor of 2. The test named
`test_a_duplicate_tag_in_one_sidecar_is_one_spoke` passed with the deduplication removed, because
the set downstream hid the mechanism it named. Deduplicated where the length is decided, and pinned
by the single-document case that has no set to hide behind.

**LOW — a hub with one member is derived state that connects nothing.** A directory holding one
document, a tag on one document, a heading with one chunk: expanding it returns only the node that
reached it. The spec only says degree-zero hubs are reaped, which full re-derivation gives for free.
Degree-one hubs are minted at zero benefit — a node, a spoke, and an entry in G6's hub report — so
they are skipped, which also makes the census directly comparable to the probe's (`_spoke_count`
counts buckets of two or more). Reachability is unchanged **for the channel as APPROACH §4A defines
it today**; §4B's all-chunk seeding is itself flagged for re-evaluation on the `sqlite-vec` tier, so
the claim is scoped rather than unconditional. The alternative reading is recorded here because it
was a choice, not a deduction.
