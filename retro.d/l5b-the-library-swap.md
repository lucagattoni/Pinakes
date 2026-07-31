### Swapping a YAML library is not a swap (L5b, the links release)

**The plan predicted three failures precisely, and all three landed as written** — which is worth
recording because it is the first increment in this project where that happened. It named the 872nd
test (`{id: x, : }`, which ruamel parses, so the case fell through to the `id` check and the
parse-error branch had been asserting nothing), the free-path gate being red on day one, and the
`ScalarBoolean` coercion being insufficient at one level.

**The free-path gate was defeated by its own harness, and I wrote the defect.** `_author_links` in
`tests/free_path_run.py` — added in L5 to close a coverage hole — wrote a sidecar through
`yaml.safe_dump`. That put `yaml` into the very module list the gate inspects, and it was also the
last PyYAML sidecar *writer* in the repo: a fixture written by one library and read by another,
which is exactly the divergence the gate exists to forbid.

**`existing[:] = keep` wipes ruamel's comment metadata outright.** Reconciling a sequence by
rebuilding a keep-list destroys `CommentedSeq.ca.items` entirely — every comment in the block, not
just the removed entry's — while `del existing[index]` shifts the survivors. Measured: `{}` against
`{0: '# first', 1: '# third'}`. Both merge functions had it.

**A comment before a sequence entry belongs to the entry above it**, exactly as it does for a
mapping key. The plan pins the deletion limitation for mapping keys; it is broader than that. After
deleting the middle of three commented links, `# first` stays correct, `# second` reattaches to the
*third* link, and `# third` disappears. The surviving links are all correct; the prose beside one of
them is not.

**"Unobservable" was the wrong conclusion; "observable only where something else is broken" was the
right one.** The plan's *"assign a known key only when its value actually changed"* looked untestable
— every known-key value is the node read out of the document and written straight back, so a write
of an unchanged document is already a no-op. Two attempts at a test passed against the mutated
source and I wrote that no mutation of it could fail. A reviewer then removed the rule and the
committed corpora stopped round-tripping: the short-circuit was **masking** the duplicate-link
defect below, not proving its own redundancy. Once that was fixed the rule really was unobservable
— but the claim was true by accident for two commits, and the difference is exactly what an
adversarial pass is for.

**`-x` makes a mutation look like it was caught by the wrong test.** Two links mutations appeared to
be killed only by an unrelated pre-existing test; without `-x` both were also killed by the test
written for them. Run the mutation pass without early exit, or the report is about test ordering.

**A merge key must be the identity the storage layer already uses.** Reconciling `links` on `to`
alone looked sufficient and is undefined the moment two links point at one document with different
relations — which `_links()` accepts and the index stores as two rows, its primary key including
`rel`. Measured on the version that had it: dropping an *unrelated* third link rewrote the first
link's `rel` to the second's and deleted the second, leaving one row carrying the wrong relation
under the other's comment. The index's own `PRIMARY KEY` was the answer, and it was already written
down in `store.py`.

**A recursive rule needs a depth bound as much as a base case.** "A key absent from the new mapping
is deleted" is required at the top of `provenance` — or `--force` leaves a false paid claim behind —
and destructive one level down, where `with_extraction_provenance` builds a plain four-key
replacement and the user's own `reviewed_by` sits beside `content_hash`. One sentence, two opposite
correct answers, distinguished only by depth.

**The exit criterion was the thing nobody ran.** The plan's one falsifiable sentence — *every
committed sidecar still round-trips* — had no test, and running it by hand found a `pnk://self/…`
entry in `partner-kb` being deleted, rebuilt without its unknown per-link keys, and moved to the end
of its block. `_links()` expands `self` on read, so the loaded entry's raw `to` never equals
anything in the reconciliation set. The docs bounded the invariant with "`pnk://self/…` expansion",
which reads as *the URI text changes* and not *the entry is rebuilt* — a documented exclusion that
quietly covered a defect.

**Quoting was applied on the path that was tested and not on the path that ships.** Decision 23's
predicate reached the merge branch and the mint, but not the branch taken when a key **first
appears** — which is the branch `pnk link` will follow on a sidecar that has no `links:` yet, i.e.
almost all of them. Three quoting mutations survived the whole suite.

**An error message is part of the interface.** Three of this increment's breaking changes surfaced
as `TaggedScalar`, `ScalarFloat` and `OctalInt` — ruamel class names, from a library the user never
chose, with no remedy. The type is not what they need; "quote it, or drop the tag" is.
