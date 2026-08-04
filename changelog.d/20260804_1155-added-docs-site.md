- **A published documentation site — [lucagattoni.github.io/pinakes](https://lucagattoni.github.io/pinakes/).**
  MkDocs Material over the existing `docs/`, deployed to GitHub Pages on every push to `main` and
  built with `--strict` on every PR, so a broken internal link or anchor fails the check. Nothing in
  `docs/` moved: the filenames are load-bearing in `tools/fragments.py`, `tools/status_header_gate.py`
  and `tests/test_verification.py`, so the chapter numbering lives in `mkdocs.yml`'s `nav` and is
  applied by JavaScript rather than written into the Markdown. `make docs` and `make docs-serve`
  build and preview it; `mkdocs_hooks.py` gives the site GitHub's heading-anchor algorithm so one
  anchor works on both surfaces.
