- **`pnk doctor` reports what share of chunks carry a heading path, and warns when a whole source
  type carries none.** The RFC realism corpus indexed **106 806 chunks with not one heading path**
  and nothing said so — which matters because `heading_path` is what G3's `in-section`, `parent`
  and `child` edges derive from, so three of the seven edge kinds derived **zero** edges on the
  corpus G5's gate was measured against. A graph result on such a corpus reads as *"structure does
  not help"* when what it measured is *"the structure was never extracted"*.

  **Total absence across a source type is the predicate, not a fitted share.** A document's chunks
  before its first heading legitimately have none, so an "any chunk missing one" rule would warn on
  an ordinary corpus and become noise. Measured before the check was written, the distribution is
  bimodal and needs no threshold between its modes: `tests/demo-kb` 60/60 and `tests/partner-kb`
  55/55 at **100%**, the RFC corpus at **0%**.

  **The remedy distinguishes the two causes**, because they need different actions. Heading
  detection runs for `markdown` only — every other kind goes through `_plain_blocks`, which sets
  `heading_path=None` unconditionally — so a `.txt` or `.pdf` source **cannot** carry one whatever
  the file contains, and the remedy says so rather than sending someone to edit documents that are
  not the problem. A `markdown` corpus at 0% is the opposite case: the chunker reads ATX headings
  and those files use another convention.

  Counted over chunks in the index, never by re-chunking a sample: a check that re-derives its own
  input reports what today's chunker *would* do, not what the index every query runs against holds.
