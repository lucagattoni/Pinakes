- **`docs/VERIFICATION.md` now has rows for 0.7.1, and one row stops overstating what its test
  checks.** 0.7.1 shipped seventeen tests holding the source-walk containment guarantees — including
  that no sidecar is minted outside the KB — and touched the verification table not at all, while
  `README.md` tells readers that table maps *every* promise to the test that holds it. Twelve rows
  added. The gate could not have caught this: it walks from the table to the tests, proving no row
  is fiction, and structurally cannot prove no guarantee is un-rowed — so the landing checklist in
  `docs/README.md` gains the step that is the only thing standing between the table and this class
  of omission. Separately, *"every non-OK check carries a remedy"* is now stated as what it is —
  spot-checked on five of the ≥29 checks `pnk doctor` produces, in one unsynced fixture — with a
  pointer to the sibling row that does enumerate.
