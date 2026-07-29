## L1 — The partner corpus and the density gate (20260729 08:47)

**HIGH — the gate did not gate the one shape it was built for.** `degrees` was keyed by *basename*
(`path.name`), so two documents sharing a filename in different folders collapsed to one key and the
later-sorted one **overwrote** the earlier. Demonstrated against the shipped gate: a degree-6
hub — 50% above the cap of 4 — behind `docs/aaa/policy.md` exited 0 and was reported as *"worst
degree 1 (policy.md)"*. Density alone permits one hub wired to everything; the degree cap exists
separately *precisely* to catch that, and a basename key is the single way it cannot. Now keyed by
path relative to the KB root. The committed corpora are flat, so nothing in this repo would ever
have exercised it — the fixture had to be built to find it.

**HIGH — the gate counted sidecars where it meant documents**, and was wrong in both directions.
An orphaned sidecar (which `pnk sync` deliberately keeps) inflated the denominator: 8 of 10 real
documents linked read as 27% and passed a 35% cap. A document whose sidecar had not been minted was
invisible, so the gate reported nonsense on any KB where sync had not run. Documents now come from
`[sources] include`, which is what the word means.

**HIGH — two documents kept a privacy claim the increment made false.** `README.md` still said
*"The sole KB here is a small synthetic corpus"* and `CLAUDE.md` *"The only KB here is the synthetic
demo corpus"*, while `DESIGN.md` was updated in the same commit to "the two synthetic corpora". The
repo contradicted itself about what had been committed, in the section a reader consults **because**
they are worried about exactly that. The *audit-the-neighbourhood* rule exists for this and I applied
it to DESIGN alone — the file I was already editing — which is the failure mode the rule describes.

**A claim that was true by coincidence, stated as if by construction.** The gate's docstring,
`check.sh` and the changelog all said it "counts the same population `pnk doctor` reports". The
*link* counts are the same population, by construction. The *document* counts are not: doctor counts
indexed documents, the gate counts files matching `include`. They agree on the committed corpora and
nothing makes them. The wording now says which half is guaranteed.

**Two gates and no test that either still exists.** L1 added a `check.sh` gate and a CI job and
asserted neither, so deleting either left the suite green — in a repo that already has
`test_check_sh_declares_the_pdf_quality_guard`, written for that exact failure. The convention was
there; I did not apply it. Both are pinned now, and CI's negative step additionally greps for the
message rather than accepting any non-zero exit, since a crash, a missing corpus, or `uv` itself
falling over all satisfy the weaker check.

**What the corpus taught about relations.** `counterpart` was used both as a reciprocated 1:1
pairing (inward loan ↔ outward loan) and as a loose association (courier requirements → outward
loan). A later increment reading `counterpart` as a pairing would be misinformed by its own fixture.
Now `governs`.

**The `self`-form fixture is not a fixed point of the product's own writer.** `sidecar.write`
resolves `self` to a ULID on write, so anything that reads and rewrites that file destroys the trap
L2 needs — and `pnk link` (L6) writes exactly that key. The test catches it, but a long way from the
cause, so the hazard is named in the test rather than left to be rediscovered.

**Mutation, twice.** Seven targets before the review, seven after the gate was rewritten. Two
mutations *appeared* to survive and were worth more than the ones that failed: the first had not
applied at all — a `str.replace` searching for `'self'` where the source says `"self"`, the exact
no-op `conftest._rewrite` refuses, met in my own mutation harness, which now asserts the
substitution happened. The second was real: nothing asserted that the report prints the cap **in
force** rather than the module default, so `--max-density 0.1` printed "27% of the 35% cap" and then
failed the corpus in the next line.

**And the verification gate caught its own author.** Renaming
`test_the_committed_split_is_what_pnk_doctor_counts` (misnamed — it never consulted `pnk doctor`)
turned `tests/test_verification.py` red until `docs/VERIFICATION.md` was updated with it. That is
I9 working on the first increment after it shipped.
