## The eval harness: three defects under one green suite (20260729 03:23)

Found while planning the links and graph releases, whose whole gate rests on this harness. All
three were live on `main` and all three passed every test.

**HIGH — the `multi-hop` class measured nothing about hopping.** `Outcome.hops_followed` was
computed for every scripted question and read by no metric — not `recall_at_k`, not `by_kind`,
nothing `compare()` looks at. **Deleting the hop loop outright left `by_kind["multi-hop"]`
bit-identical.** A multi-hop question was a single-shot search of its last hop's query wearing a
label. The one guard was `assert any(outcome.hops_followed > 0 …)` — an `any()` over five questions,
on a field that fed nothing.

**HIGH — and that hid a defect in the golden set itself.** Three of the five questions named their
*last* hop's document in `expect`; two named their *first*. So the scorer ran a query about
brittle-paper conservation and demanded the annual report. Nothing could catch the disagreement,
because `hops` fed no metric that could notice it. The fix makes `expect` exactly the union of the
hops' documents and asserts it for the committed set.

**The numbers moved because the scorer was wrong, not because retrieval changed.** recall@5
0.8788 → 0.9091, MRR 0.7737 → 0.8116, rerank precision 0.7273 → 0.7576, `by_kind["multi-hop"]`
0.80 → 1.00. Stricter scoring, higher score — because the two inverted questions had been asked
about the wrong document all along. **A metric that improves when you make it stricter is telling
you it was measuring something else.**

**MEDIUM — `compare()` wrote `by_kind` into every baseline and never read it back.** A change
lifting one class and dropping another by the same amount moves the aggregates by almost nothing;
CI was green through it. The question count had the same shape: written, never compared, so a
golden set that silently lost its hard questions would have scored *better*.

**MEDIUM — the "cheap deterministic embedder" was not deterministic.** `HashingBackend` hashed each
word with `hash()`, which Python randomises per process for `str` unless `PYTHONHASHSEED` is set —
and nothing sets it, nor can a `conftest.py`, since the value is read before the interpreter starts.
Which words collided in the 64-dimensional space changed run to run: **one failure in 40 runs**
before, **zero in 60** after switching to `zlib.crc32`. It surfaced only because a newly written
test tripped over it once. A fake that cannot reproduce itself cannot tell a real regression from
its own noise (v0.1 rule 5).

**The transferable lesson.** All three survived because the tests asserted that the machinery *ran*,
never that it could *detect*. The mutation pass is what caught them: four mutants — `hit` ignoring
hops, the `by_kind` comparison, the question-count check, and the golden-set consistency assertion —
were introduced deliberately and all four killed a named test. Green proves the tests ran; only
breaking the code on purpose proves they can see.
