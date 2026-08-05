## The corpus rejected two of my fixes, and that is the result (20260805 21:00)

**The measurement §5.3 demanded was run, on real RFCs, in doubling rounds: 66 → 131 → 259 → …**
The rule was *state the predicate first, measure second, and treat a poor match as a finding rather
than a licence to loosen a clause*. It held, twice, in the direction that costs something.

**Round 1 (66 documents) found a false positive.** RFC 769 lists facsimile command codes as
`56 - SET-UP`, `57 - DATA`, `58 - END`. Consecutive integers, short labels, column 0, blank lines
around — every clause passed, and the predicate produced three headings that are not headings.

**The first fix was wrong, and the corpus said so.** "A heading's title must not begin with
punctuation" kills it. It also killed three genuine documents: `5.1.  /get`, `2.7.3.  "iprev"`, and
RFC 2010's entire outline, which numbers real sections `1 - Rationale and Scope` — *the identical
shape as the false positive*. Form cannot separate them. **What separates them is where they
start:** an outline begins at section 1, a list of opcodes begins at 56. That rule changes exactly
one verdict across the corpus, and it is the wrong one. It shipped as clause 9.

**Round 2 (131 documents) found a second false positive, and rejected a second fix.** RFC 778
numbers a *procedure* — `1.  Connect to COMSAT-GAT host…`, `2.  Send the command…` — starting at 1,
so clause 9 does not catch it. The obvious discriminator is that a heading stands alone: require a
blank line *after* the candidate. Measured, it removed the false positive and **four genuine
documents with it**, because real headings wrap:

    7.4.  The Network Information Center and
          Requests for Comments Distribution Contact

**Rejected, and RFC 778 is recorded as an accepted bound instead.** Labelling the steps of a
numbered procedure as sections is defensible; `56 - SET-UP` was not. Not every false positive is
worth a rule, and a rule that costs real structure to buy a marginal one is a bad trade even when
its net count looks fine.

**What the corpus did buy: clause 10.** A recurring convention numbers top-level sections `1.0`,
`2.0`, mixing the two freely — RFC 2006 runs `6` then `7.0`, RFC 2024 runs `1.1` then `2.0`. Read
literally those are depth changes no walk can accept, and the document is rejected whole.
Normalising a trailing zero fixes it, and is safe precisely because a real subsection never carries
`.0`.

**Clause 10's own test then caught a bug the walk could not see.** The walk normalised `2.0` to `2`
and accepted the document — while the heading stack still used the raw depth, nesting `2.0` *under*
`1.0`. The document passed and the hierarchy was wrong. Two places consume a number's depth and only
one had been taught the convention.

**Generalisable, and the reason the doubling protocol matters:** clause 9 was derived from 66
documents and looked complete; 131 documents produced a false positive it could not catch. A fix
validated at one corpus size has been validated at one corpus size. Every round both re-checks the
previous fixes and gets a vote on the next.
