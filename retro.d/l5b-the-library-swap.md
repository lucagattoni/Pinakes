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

**A fix instruction can carry its own defects, and two of pass 6's did.** Keying `links` on the
`(to, rel)` pair made the pair the *entire content* of an entry, so no matched entry was ever
updated and every `rel` edit became a delete plus an append — landing straight in the comment
misattribution the rule was written to avoid. And "positional fallback among equal pairs" was too
vague to implement; what I wrote from it used a `set`, which collapses two identical entries: three
links in, one out. The final rule needed three explicit clauses — resolve before comparing,
multiplicity never a set, assign `rel` in place — each naming the shipped version that got it wrong.

**"Exactly the call being protected" was true of the call and false of the argument.** The
JSON-encodability check ran `json.dumps(extra, sort_keys=True, ensure_ascii=False)` — the same
function `store.dumps_metadata` calls — over `extra` alone. `_metadata()` hands that function
`{"tags": …, "provenance": …, **extra}`. A uniformly int-keyed `{1: a}` sorts perfectly on its own
and becomes mixed the moment the string keys join it, so `pnk sync` still crashed. Checking the
parts is not checking the whole, and the docstring asserting otherwise is what made it look done.

**Two tests could not observe what they claimed, for the same reason.** A plain read-write of an
unchanged document short-circuits before the merge runs, so a `wanted` that deduplicates survived
`test_two_identical_link_entries_both_survive` and a `set`-based collapse was invisible. Any test of
reconciliation has to *change* something first, or it is testing the short-circuit.

**A warning is not an error, and a library that downgrades one is changing behaviour.** A reused
anchor name raised `ComposerError` — a `YAMLError` — before the swap, and after it the document
loads, every alias resolves to the **last** anchor of that name, and the only signal is a
`ReusedAnchorWarning` on stderr. Three consequences, none visible in a passing suite: the value
silently changes; `read()`'s `except YAMLError` never sees it, because a `Warning` is not one; and
under this project's `filterwarnings = ["error"]` it escapes as a bare warning traceback rather than
a named error. Promoting it at the load makes the outcome independent of whatever warning filters
the calling program happens to have set — which is the right place for a property of the file
format to live.

**An exclusion list is a set of claims, and claims rot.** Every bound on the byte-identity
invariant — indentation, `!!` tags, anchors, CRLF, BOM, document markers — was prose in a table
until it was pinned by a test. Writing those tests measured two behaviours that were *not on the
list at all*: a plain (non-recursive) anchor on an **empty** value is destroyed, where the list
named only the self-referential case; and a file with **no trailing newline** gains one. Both are
byte changes to a file nobody edited, which is exactly what the invariant claims does not happen.
A bound stated only in prose cannot notice the library moving under it, and cannot be wrong out loud.

It also falsified a changelog line I had written: *"`!!int`, `!!float`, `!!bool`, `!!seq` and
`!!map` keep working — verified"*. Verified of **loading**; the tag itself is dropped on write, so
`!!int 3` comes back as `3`. True of the value, false of the invariant, and the word "verified" is
what made it read as covering both.

**A gate that has never been shown to fail is a claim too.** The AST scan now proves it sees all
four shapes of a planted import — including the function-scoped one an import walk cannot reach —
and does not fire on any of the four legal `ruamel` forms, every one of which contains "yaml". The
stub signature test proves it can fail: writing `transform` into the expected set failed it,
because `transform` belongs to `dump` rather than `__init__`.
