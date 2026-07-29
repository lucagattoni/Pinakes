## A sidecar that would not parse was replaced by a freshly minted one (20260729 07:26)

**HIGH — the one failure the design says is unrecoverable, shipped since v0.1 and live in 0.4.0 on
PyPI.** `walk_sources` dropped a sidecar it could not read (`except PinakesError: continue`,
`sync.py:385`) so that one bad file would not stop the walk. That was right. What it did not
account for is that the *document* then matches DESIGN §6.4's "new path, no sidecar" row — and the
mint path wrote a freshly minted sidecar over the file still holding the document's permanent ULID.
Every inbound `pnk://` link points at the id that was destroyed, and there is no migration
machinery by design.

Three things made it invisible:

* **`pnk sync` reported success.** `report.ok` was true, `failures` empty, `1 indexed`.
* **`pnk doctor` afterwards reported `sidecars: N readable`, `duplicate ids: none`, `failures:
  none`** — every check green, because the unparseable file no longer existed. The skip site's own
  comment said *"reported by `pnk doctor`"*; that safety net could never fire, because syncing
  repairs the symptom by destroying the evidence.
* **The module that owns the risk had already named it.** `sidecar.write`'s atomic-rename comment
  calls ULID loss *"the one failure in this module that no later command could repair"* — and then
  handed the file to a caller that overwrote it deliberately. A guard written against a *torn*
  write says nothing about a *deliberate* one.

**How it was found, and what that says.** Not by a test — by hand-authoring L1's partner corpus
with one deliberately unresolvable link, syncing it, and noticing that `pnk doctor` reported 10
links where the density gate had just counted 13. The discrepancy was three links, all on one
document, and that document's sidecar had a new ULID and a `created` stamp from the sync. **A
second, independent count of the same population is what exposed it**; every check that read only
the post-sync state agreed with itself. L7 requires the gate's number and doctor's number to be
the same population for a different reason — so that a user and CI cannot disagree — and this is
the argument for computing both at all.

**The fix, and one guard that was removed for failing its own mutation test.** Minting goes through
a new `sidecar.create`, which refuses where a file exists; the refusal lives at the write rather
than in the caller, because "the only caller that reaches it" is a property of today's code. A
matching guard added to the `--index-only` branch of `_mint` proved **undetectable by mutation** —
deleting it changed no observable behaviour, only which of two `SidecarError`s was reported,
because the indexing path re-reads the sidecar for its metadata and *that* read refuses first. It
was removed rather than kept, and `_mint`'s docstring records why, so a later reader does not
"restore the missing check". A guard that cannot be mutated is not a guard; keeping it would have
been the kind of decoration this project's mutation step exists to catch.

**The adversarial pass found the bigger half.** The fix as first written covered only the case
where the document is *absent from the index* — a fresh KB, a fresh clone, a `--rebuild`. For a
document already indexed whose content is unchanged, pairing yields `RefreshMetadata`, and that
branch sits **outside** `_apply`'s per-document `try`, so `_refresh_metadata`'s re-read of the
sidecar raised straight through `_apply`, the action loop and `sync()`. One hand-broken file aborted
the entire corpus: no `failures` row, no `set_meta`, no commit, and every document after it
unprocessed — contradicting this module's own opening promise and `docs/CLI.md`'s "failures are
recorded, the run continues". That is the *likeliest* route in: edit a link by hand, re-sync. Three
paths existed for one cause (`Mint`, `Reembed`, `RefreshMetadata`) and each behaved differently;
they now report identically. **The lesson is about where the first fix stopped**: it was written
against the reproduction, and the reproduction was a fresh KB because that is what a corpus author
happens to have. A fix aimed at a repro covers the repro's path.

**Two smaller things the same pass caught, both about honesty rather than correctness.** The refusal
said only "already exists, so a freshly minted sidecar cannot be written over it" — which reads like
a pinakes bug (*of course* it exists) and says nothing about the character the user mistyped, while
DESIGN, the changelog and the commit message all claimed it named the parse error. The walk has to
swallow that error to keep walking, so the mint path now re-reads the one file to recover it. And
the remedy said "repair the file rather than deleting it — it holds the permanent ULID", which is
false for the second shape the tests deliberately parametrise over: `id: not-a-ulid` has no ULID to
repair *to*, and a user in a blocked pre-commit was being told not to do the only thing that
unblocks them.

**What the tests are parametrised over, and why.** Two unrelated parse failures — a malformed link
URI and a malformed `id`. The defect is *any* `PinakesError` from `read_sidecar` reaching the mint
path, and a test written only against a bad link would have gone quiet the moment link parsing
moved.
