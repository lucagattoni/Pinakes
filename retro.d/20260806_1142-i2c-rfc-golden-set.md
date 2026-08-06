## 2c — A golden set authored by agents that did not know what it was for (20260806 11:42)

**The anti-circularity rule was implemented rather than promised.** The plan requires the questions
frozen before any injection code exists, "so that no number can influence them" — and the deeper
risk it names is fitting the question set to the mechanism, which "is undetectable afterwards". An
author who knows the hypothesis cannot prove they ignored it, and no reviewer can check it from
outside. So the set was authored by six agents over disjoint document slices, each told only that
it was writing an evaluation set for a retrieval system and forbidden from reading this repository,
where the plan would have told it. Blind authorship is the only version of that guarantee that
survives review.

**The exit criterion failed the first time, and how it failed was the useful part.** 70 questions
produced an improvable pool of **9** against a criterion of 10. The shape mattered more than the
number: 51 of 60 answerable questions were already at rank 1, `lexical` and `simple-lookup` both
scored **1.00**, and 8 of the 9 pool members were `paraphrase`. On a corpus of distinctive
technical vocabulary — protocol acronyms, registered code points, field names — BM25 with a
reranker essentially solves the classes that share words with their document.

**The obvious fix was the wrong one, and it would have passed.** Authoring more paraphrase
questions reaches a pool of 10 quickly. It also enriches the set with exactly the class a change to
the *embedded* text is most likely to move, which is fitting the instrument to the hypothesis one
step removed: the criterion would pass and the result would mean nothing, with nothing in the
artifact to show it. The two new slices carried the **same proportional mix** as the first four,
over 135 documents no question had touched. The pool went to **15**, and it changed shape — 11
paraphrase, 2 lexical, 2 simple-lookup, where before it was one class. A pool spread across classes
is what makes `compare()`'s per-class guard able to catch a change buying one class out of another.

**The expensive error in a question set is self-concealing, so the set carries its own evidence.**
A question pointing at the wrong document looks exactly like a retrieval miss. It would have
inflated the pool and made the power criterion pass for the wrong reason — the measurement then
resting on questions nobody could answer either. Every answerable question therefore records the
sentence from its document that answers it, verbatim, and `tools/verify_rfc_golden_set.py` refuses
the set if a sentence is not there. All 96 verified. Whitespace is normalised because RFC bodies
are hard-wrapped at ~72 columns, which also means the recorded evidence is often the fragment on
one line rather than a whole sentence.

**A slice can only check its own slice.** Each author confirmed its `no-answer` topics absent from
its own 50 documents. Checked across all 195, three had mentions elsewhere — "camel case" in
rfc8618 against a question about the CAMEL protocol, one mention of blockchain databases in
rfc8673, Bluetooth as a transport example in rfc8628 and rfc8793 — and later, SCADA as a category
label and NFC as both a URI transport and Unicode Normalization Form C. None answers its question,
and all were kept deliberately: a calibration set wants plausible near-misses, and a lexical
collision that answers nothing is exactly that. Two topics were duplicated across slices and
dropped.

**`filter` and `multi-hop` are absent by decision.** `filter` needs metadata worth filtering on and
these sidecars carry a title and nothing else. `multi-hop` is the graph channel's class and
`graph_channel` is off here, so such a question would score as an ordinary lookup while being
reported under a name claiming otherwise.

**The corpus is not committed, so everything that reads it had to be.** The questions, the fitted
confidence thresholds and the `before` leg all live in the repository; the 195 documents do not.
That is the same lesson `build_rfc_corpus.py` was written for — a 300-RFC corpus once produced this
project's most useful finding and died with the machine that held it. The thresholds are stamped
into the builder's manifest template rather than pasted into a generated `pinakes.toml`, which also
makes both legs of the comparison fitted identically by construction: refitting after a change
would measure the refit.
