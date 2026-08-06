## 2a — Real titles and a measured chunking reserve for the RFC corpus (20260806 06:12)

**The plan's worked reserve was wrong by more than twofold, and only measuring found it.** The
injection experiment's plan offered `480` as the corpus `max_tokens`, from "a measured max prefix of
30" — RFC 9110's largest `title > heading_path` with section numbers stripped. Measured properly,
over every heading path of RFCs 8600-8799 (195 documents, 5 of the 200 numbers unpublished),
tokenised with the corpus's own `BAAI/bge-small-en-v1.5`: the largest prefix is **68 tokens**, the
per-document largest has **median 31**, p95 51, p99 61. The median document already exceeds 30.
RFC 9110 was an unrepresentative sample for one reason nobody spotted: its title is **two tokens**
long, and titles run to 32.

Reserving 30 would have truncated roughly half the corpus's longest chunks — silently, since an
over-length embedding input raises no warning and no error. That truncation removes text from
exactly the continuation chunks the hypothesis is about, so it biases toward **no movement**: a
false negative that reads as a clean result. The reserve shipped is **96**, deliberately 41% above
the measured maximum, because 200 numbers is under a third of the modern band.

**The plan said "do not re-derive these" about a table whose own line numbers had already drifted.**
Same failure class, one level up: a number recorded as measured invites reuse, and reuse is
exactly what makes a sampling flaw permanent. The four "read this before writing a line" findings in
§2 were all correct and all load-bearing; the one worked number beside them was not.

**A defect I nearly introduced, caught in my own adversarial pass.** Preserving the KB id across a
re-run — needed once the output directory holds permanent document ULIDs — makes a re-run *look*
identity-preserving while `write_kb` still rewrote `pinakes.toml`. That would silently discard the
`[retrieval.confidence]` thresholds 2c will fit onto this corpus, with every command reporting
success: the same KB by its id, no longer the same KB by its calibration. The fix removed the
reason rather than the symptom — an existing manifest is not rewritten at all, so the id is stable
by construction and the `existing_kb_id` reader that motivated the concern was deleted. Its cost is
that a re-run does not adopt a changed `[chunking]`, so the run now names both values.

**What nothing else in the repository exercises: a title with YAML punctuation.** RFC 8713 is
*"IAB, IESG, IETF Trust, and IETF LLC Selection, Confirmation, and Recall Process: Operation of…"*.
Every committed corpus is hand-titled in plain words, so the first colon in a `title:` arrives from
the RFC Editor — into the one file holding a document's permanent ULID. `ruamel` quotes it and it
round-trips; that is now asserted through `sidecar.read` rather than assumed.

**Verified by execution, which the plan had none of.** Two RFCs built and synced with the real
`fastembed` backend: both documents indexed under their published titles, 801 chunks, largest
`token_count` exactly **414** — so the stamped cap binds on real text, as finding 1 said the default
510 does against a 512-token window.

**A bound left in place, not fixed.** `corpus.json` describes the *run*, not the directory: a
re-run over a smaller `--rfcs` set records fewer RFCs than `docs/` still holds. Pre-existing, and
now slightly more visible because `titles.kept_from_earlier_run` hints at accumulation. Worth
fixing before the run at 2f, where the corpus's composition has to be attributable.
