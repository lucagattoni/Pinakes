- **Five `pnk doctor` checks had no test at all** — `template`, `reranker`, `model cache`,
  `extensions` and `links`. Found by the coverage test above on the first run it did.
- **Three `⏳ pending amendment` notes in `docs/DESIGN.md` §9 still said work was unbuilt** that
  shipped in 0.3.0: the ledger fields and the price-staleness WARN (I6b), the cap arithmetic over a
  running total (I6a/I6b), and the measured free-vs-paid delta, which had been sitting in the row
  above them since the 20260729 measurement run.
- **`README.md` named neither PDF extra.** `pinakes[pdf]` and `pinakes[claude]` now appear in the
  quickstart, with the paid one's cost stated plainly and **all three** `[budget]` caps named —
  raising one and hitting the next is the discovery path those caps exist to prevent. `make budget`
  joined the Development target list.
