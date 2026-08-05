- **The numbered-heading predicate gained two clauses, both derived from measuring it against real
  RFCs rather than from reasoning about them.** Clauses 1–8 were written before any corpus was
  consulted, as `plans/20260805_1721-metadata-as-retrieval-context.md` § 5.3 requires; these two
  were not, and are recorded as post-hoc in the code that implements them.

  - **Clause 9 — an outline starts at section 1.** RFC 769 lists facsimile command codes as
    `56 - SET-UP`, `57 - DATA`, `58 - END`: consecutive integers, short labels, column 0, blank
    lines around, every clause satisfied, three headings produced that are not headings. Form
    cannot separate it from a real outline — RFC 2010 numbers genuine sections `1 - Rationale and
    Scope`, the identical shape — but its starting number can.
  - **Clause 10 — a trailing `.0` is a numbering style, not a depth.** A recurring convention
    numbers top-level sections `1.0`, `2.0` and mixes the two freely (RFC 2006 runs `6` then `7.0`;
    RFC 2024 runs `1.1` then `2.0`). Read literally those are depth changes no outline walk can
    accept, so the whole document was rejected. Safe because a real subsection never carries `.0`.

  **Two other candidate rules were tried and rejected on the evidence, which is the part worth
  keeping.** "A title must not begin with punctuation" removed the false positive and three genuine
  documents with it (`5.1.  /get`, `2.7.3.  "iprev"`, RFC 2010's whole outline). "A heading must be
  followed by a blank line" removed a second false positive and four genuine documents, because real
  headings wrap onto a second line. Neither shipped.
