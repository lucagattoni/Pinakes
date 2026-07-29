- **0.4.0 shipped without the three-document post-release sweep** — the rule added to `CLAUDE.md`
  eight minutes before it was cut. `docs/STATUS.md` still read *"Latest release: 0.3.0"*, its
  *Published on PyPI* table still listed *"0.2.2 and 0.3.0"*, and the roadmap had no 0.4.0 row while
  the 0.3.0 row still described `path:page` citations as unreleased — they shipped in 0.4.0. Swept,
  with the upload time taken from the index (0.4.0, 20260729 03:37 UTC).

  **A caveat the rule needs, learned while checking this one:** `https://pypi.org/pypi/<pkg>/json`
  is CDN-cached, and a query moments after an upload can return the *previous* release list. The
  first check here reported 0.4.0 missing from an index that already had it — which would have
  turned a correct release into a false alarm, or worse, licensed a re-upload attempt. Query with
  cache-busting, and cross-check `https://pypi.org/simple/<pkg>/`, before concluding a publish
  failed.

  The release itself was correct end to end: tag `v0.4.0`, `__version__` agreeing, wheel smoke test
  green, GitHub release published, and the `Publish to PyPI` step succeeded with its
  *"Explain why nothing was published"* fallback skipped.
