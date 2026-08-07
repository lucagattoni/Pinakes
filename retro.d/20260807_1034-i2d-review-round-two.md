## 2d review, round two — the argument for the key's placement was false when written (20260807 10:34)

**HIGH — the option was put in `[chunking]` rather than `[retrieval]` because `[chunking]` is
recorded in the index and therefore cannot flip silently. That reasoning was correct about the
mechanism and wrong about every KB in existence.** `chunking_drift` treats a key absent from `meta`
as *unknown, never drifted* — the rule that stops an upgrade demanding a rebuild of every index —
and `chunking_metadata` is absent from every index built before this release. Only a `--rebuild`
ever stamps the chunking identity, so the absence is self-perpetuating. Measured on a KB built by
this branch with the key then deleted, which is exactly the shape a 0.15.1 index has:

    drift ()            embedded 0          backend calls 0
    pnk doctor:  OK  chunking coherence: index matches the configured chunking

An affirmative OK over uninjected vectors, forever. For a pre-existing index the two manifest
sections behaved identically, which is the thing the placement argument was written to rule out.

**The fix turns on a distinction the original rule did not need.** `max_tokens` and `overlap` have
been settable since v0.1, so an index that fails to record them could genuinely have been built
under any value: absence there is ignorance. `chunking_metadata` is different — no release that
could have written any existing index was able to inject anything — so absence *proves* `off`.
`store.ABSENT_MEANS` says so, and because it resolves to the default, it fires only for a user who
explicitly opted in: the compatibility guarantee it looks like it threatens is untouched. Both
directions have tests, and the second one matters as much as the first — an unclearable warning on
every upgraded KB is the failure mode the heading-coverage check already had to answer for.

**MEDIUM — the fix for round one's finding shipped with the same class of hole inside it.** Round
one found that `--rebuild` carried a protected document's *vectors* forward, and the fix re-embedded
them. But the re-embed called `embedding_text` without calling `assert_prefix_fits`, so the one path
that re-embeds **without re-chunking** became the only path with no truncation guard — and it is the
path that needs one most, since its chunks were sized by whatever `max_tokens` built the previous
index and are never re-chunked. A fix for a silent-truncation defect that reintroduced silent
truncation one function away.

**MEDIUM — and it also introduced a way to publish a half-written document.** `DETACH` requires the
transaction closed, so that function commits in a `finally`; with the writes inside that block, a
document whose embedding failed was committed *active* with chunks and zero vectors, which
`_apply`'s `rollback()` could no longer undo and `--rebuild`'s unconditional index swap then
published. No later sync repairs it: the file's content hash is unchanged, so every future run says
`Skip`. Now the old rows are read under the attach and every write happens after it, in one
transaction the caller can still roll back.

**MEDIUM — the eval artifact labels a leg from the manifest, never from the index.** Every
`[chunking]` value in a header is read from `pinakes.toml` at eval time. Because flipping `metadata`
changes no chunk's text, hash or span, an eval run against an index that was never rebuilt produces
a byte-for-byte plausible artifact stamped `metadata: "prefix"` over uninjected vectors — and
`tools/two_leg_gate.py` would accept it as the injected leg, since it compares headers to headers.
The instrument that licenses an irreversible schema bump could be handed a leg that never existed.
`eval.run` now compares the index's recorded chunking against the manifest and refuses before
scoring a single question.

**The four rules this round leaves behind.**

1. **A grep for the operation is not a proof about the outcome.** Round one's defect survived a
   check for every `.embed(` call site because the offending path produces vectors with
   `INSERT … SELECT`. Round two's survived a reading of `chunking_drift` because the defect is in
   what the function does with a key that *is not there*. Both times the search was over the wrong
   set — the question is never "where is this called" but "what else can reach this state".
2. **A fix is a change, and gets the same review as one.** Two of this round's findings are in code
   written to fix round one, hours earlier and with the defect fresh in mind.
3. **State an argument in terms of the population it covers.** *"`[chunking]` is recorded, so the
   flip is reported"* was true of indexes this release builds and false of every index that existed.
   The sentence never said which it meant.
4. **A partially-failed harness must not report like a completed one.** Round one lost 15 of 17
   agents to a usage limit and returned `{"confirmed": [], "refuted": []}` — indistinguishable from
   a clean review. The findings were recovered from the agents' transcripts by hand; one was the
   HIGH above. Round two ran complete: 14 findings, 14 judged, 9 confirmed, 5 refuted.
