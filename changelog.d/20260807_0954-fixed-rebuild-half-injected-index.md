- **`--rebuild` no longer leaves a paid-extracted document holding vectors from the old settings.**
  A document whose paid extraction `--rebuild` protects is carried forward from the index being
  replaced instead of being re-extracted — and its **embeddings** were carried forward with it,
  while the run stamped the *current* `[chunking]` over the whole index. Turning
  `[chunking] metadata` on and rebuilding therefore produced a KB whose paid documents held
  uninjected vectors, whose recorded identity said `prefix`, and whose next `pnk sync` and
  `pnk doctor` both reported no drift: every command succeeded over a half-injected index. Turning
  injection back off had the mirror-image defect.
  The vectors are now recomputed from the carried-forward chunks. **The paid extraction is still
  never re-run** — that is the part that costs money; embedding is local and free, and the chunk
  texts are already in hand. A carried-forward chunk that has a `heading_path` is refused with a
  named remedy rather than injected with the citation form of its path, since the numbers-stripped
  form is built during chunking and deliberately not stored; no source type reaching this path
  produces one today.
  **Not closed, and larger than this key:** those chunks are still copied verbatim, so `headings`,
  `max_tokens` and `overlap` changes do not reach a protected document on a rebuild. Re-chunking
  needs the extracted text, which is exactly what may not be obtainable again without paying.
