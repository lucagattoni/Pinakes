## A warning that cleared itself without the fix being applied (20260805 20:20)

**HIGH — the first draft turned a silent defect into a *lying* one, and every test passed.** The
chunking-drift warning was correct. What was wrong sat 300 lines away: `sync.py` wrote the current
chunking identity into `meta` at the end of **every** sync, including the incremental one that had
just refused to re-chunk anything.

So the sequence was:

| step | what the user saw | what was true |
|---|---|---|
| edit manifest, `pnk sync` | `1 unchanged` + the new warning | index still built the old way |
| `pnk sync` again | `1 unchanged`, **no warning** | index still built the old way |
| `pnk doctor` | **`OK chunking coherence`** | index still built the old way |

A warning that clears itself without the fix being applied is worse than no warning: it converts
"the tool said nothing" into "the tool said it was fine". The index actively claimed a coherence it
did not have.

**Found by running it a second time, not by testing it.** The unit tests asserted the warning
appears — it did. Nothing asserted it *persists*, because persistence only fails on the second
invocation, and a test that runs an operation once cannot see a defect that needs it twice. The
fix's own test is now `..._persists_until_the_rebuild_actually_happens`, which syncs three times.

**The correct rule turned out to be narrow:** record the identity only when *every* chunk in the
index was produced by this run — a rebuild, or a first build into an empty index. An incremental
sync re-chunks only what changed, so after one the index is a *mixture*, and there is no single
honest value to record. Leaving the old value is right: it keeps warning, which is exactly what a
mixed index deserves.

**Generalisable, and it is the second time today:** a state-writing side effect belongs with the
work it describes, not with the command that happened to run. `set_meta` is called once per sync and
was treated as "the place identity goes" — but identity is a claim about the *chunks*, and only one
of those code paths actually produced them all.
