## Mutation testing found a guard that could not fire (20260805 19:07)

**LOW as a defect, worth keeping as a method result.** The numbered-heading predicate's
document-level check was written straight from its own spec, which says the numbers must form a
valid outline walk **and** that no number repeats. Both were implemented: a `seen` set alongside the
step-validity rule.

Mutating the clauses one at a time, eight of nine mutants were killed by the test named for that
clause. **The ninth — deleting the no-repeats check entirely — broke nothing.**

The first instinct is "write the missing test". The right answer was that **no such test can
exist**: every step the walk permits raises the number tuple lexicographically — a sibling raises
its last component, a first child appends to it, an ancestor's next sibling raises a shallower one —
so an accepted sequence is strictly increasing and a repeat is unreachable. The check was dead code
wearing a guard's clothes.

It was **removed rather than kept as defence in depth**, and the reasoning put in the docstring. A
guard that cannot fire still reads as one, and the next person to touch the step rule would weaken
it believing this had their back. The spec keeps the no-repeats sentence — as a statement of intent
it is correct, and the implementation note now says why it needs no code.

**Generalisable:** a surviving mutant asks a question before it asks for a test — *is this
reachable at all?* Adding a test for unreachable code is how dead code acquires the appearance of
coverage. This is the inverse of the failure this project keeps meeting: usually an assertion is
satisfied by something other than the property it names; here a *guard* was satisfied by something
other than itself.

## Running it found what reading it could not (20260805 19:15)

**MEDIUM, and the reason it is recorded beside the note above: the two findings came from opposite
methods on the same increment.** The dead guard was found by mutating code. This one was found only
by building a KB and using the feature the way a user would.

`[chunking] headings = "numbered"` added to an already-synced KB, then a plain `pnk sync`:

| | result |
|---|---|
| plain `pnk sync` | `1 unchanged` · every `heading_path` still empty |
| `pnk sync --rebuild` | `1 indexed` · the three heading paths, and the first `parent-child` edge |

An incremental sync re-chunks a document only when *the document* changed. A manifest-only edit
changes no content hash, so the feature silently does nothing — and `pnk doctor` then reports
exactly the condition the user just tried to fix.

**Every test passed throughout, and no test could have caught it.** The unit tests call
`chunk_document` directly with the parameter set; the mechanism that drops it lives in `sync.py`'s
change detection, one layer up. The defect is not in either component — it is in the seam, and a
seam is only visible from outside both.

**It is also pre-existing**: `max_tokens` and `overlap` have always behaved this way. Three releases
did not surface it because no `[chunking]` key had ever been worth flipping on a KB already indexed.
Adding the first one that is, is what made an old defect newly reachable — and *"my change did not
cause this"* is not the same as *"my change did not make it matter"*.

**Generalisable:** for any change that adds a knob, turn the knob on a real KB before landing. Unit
tests verify a component honours a parameter; only using it verifies the parameter *arrives*.
