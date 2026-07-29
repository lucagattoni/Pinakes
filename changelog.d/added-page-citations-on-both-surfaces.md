- **`path:page` citations, on the CLI and the MCP surface in the same increment** (I8). A PDF
  passage cites `docs/paper.pdf:p7`, or `docs/paper.pdf:p7-8` when the chunk straddles a page break.
  The `p` is deliberate: `:12-480` already meant character offsets, so a bare `:12-13` would have
  been a page range and a character range in one syntax. Non-paged sources are unchanged.
- **`pnk search --json` and `pinakes_search` carry `page_start`/`page_end`** as separate integers
  beside the rendered `citation` (both `null` for a source with no pages), so nothing has to parse a
  citation back apart.
- **`pinakes_get` is page-aware**: `page_start`/`page_end` read one range, page boundaries come back
  marked by a `[page N]` line, and the payload reports `page_count`. A PDF is served from the
  extraction cache — the same text the index was built from — never by re-extracting.
- **`pnk doctor` gains a `text yield` check**, reporting **per page, never per document**: the
  median non-whitespace characters per page, then the pages below the fitted floor by path *and*
  page (`docs/scan.pdf p4-9`). A document-level median stays silent on a 200-page report with eight
  scanned inserts, which is exactly the document worth knowing about. Its remedy names the paid
  extractor and says that it spends.
- **Three end-to-end traces** (`tests/test_pdf_trace.py`): a table-cell word across six hops from
  extraction to the agent surface, every filter dimension actually selecting PDF rows, and one paid
  slice's cost from estimate through reservation, the response's own `usage`, reconciliation and
  into what `pnk budget` prints.
