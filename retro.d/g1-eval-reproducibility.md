## G1 — Is the eval reproducible? (20260801 00:52)

Decision 15 said measure before fixing, and the measurement paid for itself twice: once by finding a
real defect, and once by contradicting the fix that was nearly written for it.

**HIGH — the eval was reproducible by luck, and the luck was invisible.** Running the golden set,
editing a document, re-syncing, rebuilding and comparing *per-question* outcomes: the real `[light]`
models agreed everywhere. A low-dimensional fake disagreed on one question in 41 between an
incremental sync and a `--rebuild`. Both facts are the same fact — 384-dimensional cosines almost
never tie exactly, and every tiebreak underneath resolved to `chunks.id`, the rowid, which
`store.py`'s own schema comment says has no identity across rebuilds. A property that holds because
the corpus never exercises it is not a property, and G5's sign test was about to be built on it.
The fix is total ordering on `(documents.path, chunks.ordinal)` at three sites plus a stable
`argsort`; **no measured number moved**, which is the right outcome for a change that only breaks
ties, and is why this increment rewrites no baseline and needs no amendment to L8 step 5.

**HIGH — the fixture was the algorithm, in the one place that judges the algorithm.** The first
version of the tests used eight dimensions, reasoning "fewer dimensions, more ties". Swept against
the genuine pre-fix code, eight and sixteen dimensions both reported **zero** differences across all
four perturbations: collapse the space far enough and every candidate ties, so the ordering
underneath stops reaching the top-k at all. The relationship is not monotonic — 32 caught two
perturbations, 64 caught one, 128 caught two. Had the sweep not been run, G1 would have shipped a
green gate, a green test suite and a live defect, all three agreeing. The sweep is recorded in the
gate's own `DIM` docstring rather than the conclusion alone, because the next person's intuition
will be the same as this one's.

**HIGH — the mutation harness deleted the thing it was measuring.** The first mutation run restored
each mutation with `git checkout -- <file>`. The fix was uncommitted, so the first restore reverted
it; every later mutation then failed to apply to code that no longer had the target, and the suite
ran green against **original** code four times while reporting "0 failures" as though the mutations
had been survived. It read exactly like a well-tested change. Two rules fall out. *Restore from a
copy of the mutated-from state, never from `HEAD`* — `git checkout` restores to the last commit,
which is a different thing from "undo my mutation" whenever the work is uncommitted. And *a mutation
harness must assert that its mutation applied*: the rewritten one fails loudly if the target string
is not found exactly once, which is what turned three silent no-ops into an error.

**MEDIUM — a stable sort needed its own test, and the obvious one was vacuous.** `kind="stable"`
changes nothing a repeated run can observe: on a fixed input array NumPy's introsort is
deterministic. It changes what happens when the array *grows*, because partitioning depends on the
whole array — measured at 500 of 500 random tie-heavy arrays reordering their original entries. The
first test written for it used four tied chunks and passed under the mutation, because NumPy uses an
insertion sort below roughly sixteen elements and insertion sort is stable whatever `kind` says. A
fixture can be too small to contain the behaviour it is named after.

**What the increment ended up asserting, and at which level.** Three end-to-end tests state the
property G5 needs, over the committed corpus and questions; four site tests each drive one ordering
decision directly and are the mutation targets — one mutation, one failing test, verified for all
four. The two levels are not redundant: the end-to-end tests can only observe ties the corpus
happens to contain, which is precisely how the defect survived three releases.
