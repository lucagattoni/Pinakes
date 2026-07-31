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

### The adversarial pass over G1's own diff (20260801 01:25)

Six findings, four of them real defects in work that was already green.

**HIGH — a gate advertised a field it had retired.** `_plant` rewrote the reranker's *model* name
and left `[retrieval.confidence] fitted_for` naming the real one, so `_confidence` short-circuited
and all 41 questions scored `unknown`. Both the gate's docstring and the tests claimed to compare
the confidence label. Naming the reranker was not enough either: the committed thresholds were
fitted on a real cross-encoder's logits and sit below every score the fake can emit, so the label
became a constant `high` — still unable to move. Thresholds inside the fake's range give
35 medium / 5 high / 1 low, and the field is finally live. **The class of defect matters more than
the instance:** a fixture that rewires half of a calibrated pair silently disables the thing it was
calibrated for, and nothing fails.

**HIGH — the plan still asserted what the measurement disproved.** Decision 15 says a final tiebreak
would be *"a provable no-op"* because cross-document ties are totalised by `documents.path` and
rowid order is ordinal order. Both premises are true about **writes** and irrelevant to the
**output**: `documents.path` cannot separate two chunks of the same document, and an incremental
sync by definition does not rewrite the files it did not touch, so rowid order stops matching corpus
order at the first re-chunked file. The plan is an executor doc; leaving that cell intact would have
licensed a G2–G5 executor to skip a tiebreak for a reason this increment measured to be false.

**MEDIUM — half the gate's sweep has never observed anything.** Of its four perturbations, *added*
and *removed* report zero differences against the genuine pre-fix code at every width swept
(8/16/32/64/128), while *edited* and *renamed* bite. `--inject-difference` cannot reveal this: it
corrupts all four alike. The gate now states it. **A gate's own justification is a claim like any
other** — this one said "it sweeps four ways where the tests exercise one", and two of the four were
along for the ride.

**MEDIUM — the contract's file table was checked against the wrong question.** It compared the two
tracks' *owned* files and never asked what a new gate touches. Every gate edits `check.sh`,
`ci.yml` and `tests/test_check_script.py`, which both tracks append to at the end of the same
regions; and G1 necessarily edits `search.py` and `store.py`, which the table lists under neither
track, because reproducibility is a property of core retrieval. Widened, with the reason.

**LOW, and recorded rather than fixed —** making the BM25 cut total costs a join: +11.5 ms on a
50k-chunk corpus where every chunk matches every term. That is the worst case a planner can be
given, the correctness is not optional, and the number now sits in `docs/STATUS.md` so a later
change can argue with it.

**What the pass confirmed, having tried to break it:** `bm25()` still resolves with the alias
present and returns byte-identical rows; the join multiplies nothing (both sides unique); the
`load_vectors` reordering costs nothing measurable; `graph/provider.py`, the other caller, reduces
to a per-document max and is order-independent; the four site tests each fail against pre-fix code;
and the artifact paths, cache keys and macOS wheels in the cross-machine job all resolve.
