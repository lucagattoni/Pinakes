- **Three docstrings corrected where the code had moved under them.**
  `tools/build_rfc_corpus.py` said `assert_chunkable` was what catches a corpus exceeding the
  prefix reserve — it cannot and never could, since it validates `max_tokens` before anything is
  chunked and so never sees a prefix; `chunk.assert_prefix_fits` is the one, which is why it
  exists. The same module's header said the 300-RFC corpus "lived on one machine and died with
  it": it is public at `lucagattoni/pinakes-corpus-rfc` with documents, sidecars and manifest
  committed, so its figures are re-derivable — what is gone is the index and the unpinned backend
  revision, and its manifest carries no `[chunking] headings` key, so rebuilding it today still
  yields zero heading paths. (`CHANGELOG.md` keeps the superseded sentence in its released entry:
  a dated record keeps its words.)
  `doctor.py`'s heading-coverage check said detection is "for `markdown` only — every other kind
  goes through `_plain_blocks`", which 0.13.0 falsified and which the same docstring contradicted
  twenty lines later, where it tells a `text` corpus at 0% to set `[chunking] headings`. The same
  stale sentence in `tests/test_doctor.py` promised a `.txt` file "cannot carry one whatever it
  contains", while that test's own assertions turn on the opposite.
