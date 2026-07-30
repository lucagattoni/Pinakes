## L3–L4 — The traversal core and `pnk links` (20260730 18:06)

**Four HIGH findings, all in the properties the increment's own prose claimed loudest.** That is
the pattern worth keeping: the module docstring argued at length for double-capping, precedence and
server-side clamping, and each of those three was where the defect was. Writing the argument down
appears to have substituted for checking it.

**The response was half-capped.** `max_rows` and `token_budget` gated `neighbours`; the `frontier`
was appended to unconditionally. Measured: a caller asking for **one** row received **1,000**
frontier entries — and the frontier is the part an agent parses to decide what to ask next. Now
capped, and ordered so that entries about nodes you did *not* get come first: capping without that
ordering let the `depth` notes of accepted nodes fill the whole budget and crowd out every `rows`
note, so a caller asking for 2 of 5 was told nothing about the 3 it missed.

**"Every bound is clamped server-side" was true of two of the four.** `max_rows=10**9` returned
3,660 rows with an empty `truncated`. Three documents said otherwise. Once this is reachable over
MCP the caller supplying `max_rows` is the untrusted party, so the sentence was not merely
inaccurate.

**A frontier entry contradicted the answer beside it.** A node dropped by fan-out at one hop and
reached at another kept its `fanout` entry — while sitting in `neighbours` and having been
expanded. `FrontierEntry`'s own docstring says "discovered and **not** expanded". Stale drops are
now retracted at return; `terminal` and `depth` are kept, because those describe accepted nodes
deliberately not expanded, which is the contract rather than a contradiction of it.

**Half the stated precedence was inverted.** The row and token checks ran before terminality was
consulted, so a terminal neighbour dropped by the row cap reported `rows` — inviting a retry with a
*smaller* request, which cannot help. Of the ten pairs the declared order implies, five were
backwards and exactly one was tested: the one the code happened to honour.

**The gate had three separate ways of being vacuous, and its docstring was an essay about gates
that cannot fail.**

* It passed against a `traverse()` that returned an empty `Result` — every check was one-sided, so
  zero neighbours satisfied all of them. Now equalities.
* It imported `MAX_DEPTH` and `MAX_ADJACENT_K` from the code it gates and compared them with
  themselves. Raising the caps to 10 and 150 moved the walk and the gate still passed, while
  `docs/MANIFEST.md` went on promising 64. The documented numbers are now literals in the gate — a
  second copy, which is the only thing that makes a silent change show up.
* It had no negative check, in a repo where the *immediately preceding* increment added one to its
  sibling job and a test that guards it. Added, with a `--expect-depth` override so CI can drive
  the gate into failure on purpose and assert the stated reason.

**Two more the same pass found.** The row cap truncated by parent-expansion order while ranking was
per-parent, so a top-ranked neighbour behind a low-ranked parent lost to a worthless one in front of
it — the same mistake as truncate-then-rank, one level up. And node-level row dedup silently dropped
a second distinct relation to the same target, in a module whose contract is that a fact about the
graph is returned rather than dropped; rows are now deduped per **edge** while expansion stays per
**node**.

**A dead sort term with a docstring defending it.** `_rank` sorted by `(-weight, distance,
node_key)` and explained that a nearer neighbour of equal weight ranks higher. `_rank` is called
with one hop's candidates, so `distance` was constant in every sort. Removing it changed nothing —
which is how it was found, and is the argument for deleting rather than believing prose.

**A test that could not hold its name.** `test_depth_counts_logical_hops_not_physical_edges` had no
hub in its fixture and its own docstring conceded the core never sees one; it was a second copy of
the clamp test wearing a larger claim, and `docs/VERIFICATION.md` cited it for a promise it could
not carry. Renamed to what it actually checks. The logical-hop promise belongs to the provider that
composes hubs.

**And new behaviour shipped without tests.** `[retrieval] adjacent_k` and `_toml.integer(maximum=)`
had none — the commit message's claim that a value above the cap is *refused* rather than clamped
was asserted and never executed, against this project's own rule that tests ship in the increment
that introduces the behaviour.

**A process failure worth recording separately.** L4 was built in L3's worktree while L3's
adversarial review was still reading it, so the reviewer found the tree dirty with a parallel
increment's work and had to run every probe against a copy. It cost the review nothing this time
because L4 added files rather than editing `traverse.py`, but that was luck. One increment, one
worktree, and the review finishes before the next one starts.

**Four silent `str.replace` no-ops this session**, one of which spliced a new import into the middle
of an existing one and produced a nonsense symbol. It is the same failure `conftest._rewrite` exists
to refuse, met in editing rather than in a fixture. Non-trivial edits now go through a tool that
errors when its anchor does not match.
