- **`tools/build_rfc_corpus.py` fetches RFCs and builds a KB from them — the realism corpus as a
  script rather than a directory on one machine.** This repository commits no harvested content, so
  the 300-document corpus that produced this project's most useful findings lived locally and died
  with the machine; that is why its measurement cannot be re-run and its verdict is correspondingly
  hard to revisit. Nothing harvested is committed here — only the script, and a `corpus.json`
  recording exactly which RFCs a run fetched, so a later run can be *compared* with an earlier one
  rather than merely repeated.

  It refuses to build inside this repository, caches downloads so a re-run costs nothing and a
  partial run resumes, and takes an `--era` band because RFC rendering changed between the nroff
  and xml2rfc generations: **a measurement over this corpus is a measurement over that era**, and
  saying which is the difference between a result and an anecdote.
