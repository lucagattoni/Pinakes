- **`pinakes_get` on a PDF crashed with an unhandled traceback.** It read the source file with
  `read_text(encoding="utf-8")`, which raises `UnicodeDecodeError` — a `ValueError`, so the
  surrounding `except OSError` never caught it. PDFs are now served as their extracted text, and the
  decode failure has an explicit branch for the case a binary source is somehow recorded with no
  extraction backend.
- **The `stale_extraction` marker reached neither surface.** It was computed in `search.py` and
  dropped by both the CLI and the MCP renderer. The plan's own amendment row said I8 would take it
  "to the agent surface and not only the CLI", which understated the gap by half. Both surfaces now
  carry it — marked, never withheld.
- **The shipped `notes` template told every new KB that "no shipped code path spends money"**, which
  stopped being true when 0.3.0 shipped the paid extractor. The `[budget]` comment now says what the
  caps are for and that they bind only once you opt in.
- **`docs/GUIDE.md` said the paid extractor was "built but in no release yet"** — also untrue since
  0.3.0 — and still listed `path:page` citations as missing.
