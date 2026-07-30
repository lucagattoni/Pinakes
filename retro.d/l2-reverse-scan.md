## L2 — Reverse-scan (20260730 16:51)

**One root cause behind all three HIGH findings: I bypassed `manifest.load` and kept none of what
it was doing.** The bypass is right — a partner may run a newer pinakes whose manifest mentions keys
this one has never heard of, and refusing to read a neighbour's inbound links over that would make
every connected KB a version dependency of every other. But `load` is not only a parser; it is also
the place that rejects an absolute `[sources] roots`, rejects `..` in one, and validates the include
patterns. Reading the TOML directly removed all of it and replaced none of it, and the partner's
manifest is **input this KB does not control**. Every one of the three failures below is that same
sentence.

**A partner renaming its own `docs/` silently deleted every inbound row it had.** A `roots` entry
that is not a directory was a quiet `continue`, so the walk yielded zero sidecars, reported
`complete=True`, and the caller did exactly what it is written to do with a complete walk: delete
and replace. Reproduced — rows 1 → 0, `link_scan` empty, `last_scan` stamped fresh, so the retry was
suppressed for a full window too. This is precisely the mass deletion the `complete` flag exists to
prevent, arriving through the one door the flag was not watching, and **no "successful walk" test
could ever have caught it** because they all leave the partner's sidecars where they are. A missing
root is now a walk failure with a reason.

**The partner's `exclude` was ignored, while a comment claimed otherwise.** `sidecars_under`'s
docstring said a document "whose document was excluded" contributes nothing; it read only `roots`
and `include`. The shipped `notes` template stamps `exclude = ["**/drafts/**"]`, so this is not an
exotic configuration — it is the shape of every KB `pnk init` creates, and the scan was recording
inbound links from documents the partner's own KB does not contain.

**A partner's manifest could crash `pnk sync` on a git hook.** The `sidecars_under` call sat
*outside* the `try`, and `Path.glob` raises on patterns `manifest.load` would have rejected —
`NotImplementedError` for a non-relative pattern, `ValueError` for an empty one. Both escaped
`sync()` entirely. The module's central promise is "nothing here raises", precisely so a partner
that is merely broken cannot block a commit; the one call that could raise was the one left outside.

**Two tests that could not fail, both of mine.** `test_the_partner_is_never_locked` asserted the
partner had no `.pinakes/` — on a fixture where the partner was never synced, so the directory had
never existed. It proved nothing was created and nothing whatever about locking; it now holds the
partner's real `SyncLock` while the local sync runs. And a test asserting no SQLite connection was
left open re-asserted pre-existing `sync()` behaviour (`_run`'s `finally: close()` always releases
it), so no L2-shaped defect could have made it fail. Deleted rather than kept: a test that cannot
fail is worse than no test, because it is counted.

**A failed local run blamed the partner.** `known_documents` is read from the index, so a document
that failed to index *this run* is absent from it — and a genuine inbound link was then reported as
pointing at a document this KB does not have. It does have it; it failed to index it. The local
picture is now passed as `None` on a failed or budget-stopped run, which suppresses that check
without touching the rows, since the rows come from the partner and owe nothing to our state.
`_run` already guards `active_content_hashes` on `report.ok` for the same class of reason — the
precedent was there.

**Dead code that credited itself with someone else's work.** `ScanResult.delisted` and the
`known_kb_ids` parameter were computed every sync, complete with a docstring explaining that the
rows "are removed" — by a function that never read either. The sweep is `store.forget_reverse_links`,
which takes the manifest's ids directly. Removed, along with the `SELECT DISTINCT` that fed it.

**Mutation: 11 targets before the review, 5 more after, all detected.** The one apparent survivor
was equivalent code rather than a gap — taking `src_kb_id` from the declared id instead of the
partner's own is indistinguishable wherever a row is written, *because* the mismatch guard refuses
first. The guard is what carries the weight, so the test asserts what makes the assignment moot: a
mismatched id writes no rows and no `kb_refs` entry.

**And a test premise of mine was wrong, which the failure said plainly.** `_replace_links` only runs
for a document that gets an action, so the reverse-then-authored ordering needs the document to
actually change — a second sync skips everything and rewrites nothing. Worth keeping because it is a
fact about when authored links are re-asserted at all, not just about this test.
