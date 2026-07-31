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

**Some rules cannot be tested, and saying so beats inventing a test.** The plan's *"assign a known
key only when its value actually changed"* has no observable effect: `_merge_mapping` and
`_merge_links` mutate their nodes in place, and `deepcopy` of an immutable scalar returns the same
object, so a write of an unchanged document is already a no-op without the short-circuit. Two
attempts at a test for it passed against the mutated source. The rule states intent and saves a
walk; the honest thing is a docstring saying no mutation of it can fail, not a third attempt.

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
