- **`pnk init` adopts a directory that already has content, instead of refusing it.** Creating a
  repository, cloning it, then running `pnk init` inside is the normal way to start a KB — and a
  `.git`, a `README.md` and a `pyproject.toml` made that directory "not empty", so `init` refused
  with *"clear this one first"*, which is an alarming thing to read about a directory holding the
  documents you meant to index. Hit three times independently before it was changed.

  **The blanket emptiness test is gone, and what replaces it is narrower and stronger: `init` never
  overwrites a file that is already there.** Any file it would have written and found present is
  left **byte-identical** and named in the output (`left as they were: .gitignore, README.md`), so
  there is nothing left for an emptiness test to protect. The accepted cost, stated when the
  decision was taken: a typo in the path now creates a KB among unrelated files rather than
  refusing — recoverable by deleting `pinakes.toml`, where overwriting a README is not.

  **Two things are called out rather than silently handled.** An adopted `.gitignore` that does not
  mention `.pinakes/` is reported with the line to add — `init` will not edit a file it does not
  own, and that directory holds the index and the spend ledger. And `--ci` is **refused** rather
  than adopted when a workflow already exists, now *before anything is created*: it is an explicit
  request, so honouring it by doing nothing would be worse than refusing.
