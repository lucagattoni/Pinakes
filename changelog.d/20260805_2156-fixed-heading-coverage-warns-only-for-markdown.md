- **`pnk doctor`'s heading-coverage check no longer warns about something you cannot fix.** It
  WARNed whenever *any* source type sat at 0%, so a KB holding one `.py` file or one PDF warned on
  **every run, forever**, with a remedy that amounted to *"this is a limit of the tool"*. An
  un-actionable warning that cannot be cleared is how doctor output stops being read at all — which
  costs the actionable warnings too, a larger loss than the one signal it gave up.

  **WARN is now reserved for `markdown` at 0%**, the one case a user can act on: the chunker reads
  ATX headings, so a Markdown corpus with none is being silently chunked by size. Everything else is
  reported **OK with a note**, and the note separates three facts that previously wore the same 0%:
  `text` *can* carry a heading path (set [`[chunking] headings`](../docs/MANIFEST.md#chunking));
  `text` with that key **already set** means the grammar was offered those documents and **refused**
  them rather than inventing an outline; `code` and `pdf` cannot carry one today whatever they
  contain.

  It also corrects a claim 0.13.0 falsified: the old remedy still said non-Markdown types cannot
  carry a heading path *whatever the document contains*, which stopped being true when the numbered
  grammar shipped.
