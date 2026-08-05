## Fixture copies carried the developer's own `.pinakes/` into the test workspace (20260805 17:49)

**MEDIUM — three tests failed on `main` immediately after two clean merges, on a machine where
nothing was wrong with the code, and the failure impersonated the exact defect this repo watches
for.** `CLAUDE.md` says a clean auto-merge is not a correct merge; both branches had been green
individually; `main` then failed. Every signal pointed at a bad merge. The cause was a
`tests/demo-kb/.pinakes/index.db` dated 1 Aug — a leftover from a manual `pnk sync` predating the
graph release's `schema_version` 3 bump — which five `shutil.copytree` calls copied into the test
workspace along with the documents.

**The tests were coupled to whether the developer had ever run the tool by hand.** CI clones fresh,
so `.pinakes/` never exists there and the suite is permanently green; a dev box that has exercised
the fixture once fails until the directory is removed. `.pinakes/` is gitignored, so nothing in the
diff, the merge or the branch could have shown it.

**The idiom was already in the codebase and applied to four of nine call sites.**
`ignore=shutil.ignore_patterns(".pinakes")` was used in `test_eval.py`, `test_search_reproducibility.py`
and twice in `test_partner_kb.py`. The other five simply omitted it. A guard applied at *some* call
sites is not a guard — it is a coin flip weighted by which test the copy happens to be in, and no
gate could notice the omission because the states it protects against are gitignored and absent in
CI.

**Verified in both directions, planting a poisoned fixture rather than reasoning about it.** With a
deliberately corrupt `tests/*/.pinakes/index.db` in place, all 105 tests across the four affected
files pass. Removing the guard from one call site fails exactly that site's test
(`test_edges.py::test_the_stored_edge_set_agrees_with_the_probe_the_decision_was_taken_on`,
`StoreError`), which is what makes the guard's presence the property under test rather than an
incidental line.

**Generalisable:** when a test copies a directory the tool also writes into, the copy must name what
it excludes. And a *loud* environment-coupled failure is not a cheap one — this one cost real time
precisely because it arrived wearing the costume of a merge defect, right after a merge.
