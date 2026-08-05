- **A Markdown document is now titled by its own `# ` heading.** `sync` never read a document's
  content for its title — `skeleton()` was called without `title=` at both sites, so the filename
  stem always won. It was easy to miss because the two usually differ only in capitalisation:
  `# Access restrictions` sitting beside `title: access restrictions` reads as though the heading
  *was* used, when the value is the stem with its hyphens swapped for spaces. A file called
  `rfc9110-notes.md` opening on `# HTTP Semantics` was titled *"rfc9110 notes"*.

  **An H1 is structure, not a guess** — which is what separates this from the first-line heuristic
  that stays rejected. An RFC's first line is `Internet Engineering Task Force (IETF)`; a `# ` is an
  explicit authored marker saying what the document is called. Markdown only: a `#` in a `.txt` is a
  comment character, and reading a PDF here would be a second extraction outside the cache. Fenced
  `#` lines are ignored, and `##` does not count — a file opening on a subsection is not named after
  it. Where there is no H1 the filename fallback stands, visibly a filename.

  **No migration, and none needed.** Titles are minted only when a sidecar is created, so every KB
  already indexed keeps exactly the titles it has — and `title` is the user's field, which a sync
  must never overwrite. Pinned by a test that edits a title, then edits the document's H1, and
  asserts the user's wins.
