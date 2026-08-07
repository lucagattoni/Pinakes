## 2d review — the grep that was necessary and not sufficient (20260807 09:54)

**HIGH — a rebuild could leave a half-injected index, and the check that should have caught it was
looking for the wrong thing.** Before landing the injection, this increment verified that
`sync.py` has exactly **one** `.embed(` call on the indexing path — `grep -rn '\.embed(' src/`
returns that one, plus two query-side calls. The conclusion drawn was "every vector on the indexing
path goes through the switch". It does not follow, and the counter-example was already in the file:
`_copy_forward_protected_document` writes rows into `embeddings` with an `INSERT … SELECT` from the
index being replaced. It produces vectors **without embedding anything**, so no grep for `.embed(`
could ever have found it.

The consequence was the failure class this project exists to prevent. A KB with a paid-extracted
PDF, `[chunking] metadata` flipped to `"prefix"`, and `pnk sync --rebuild`: the protected document
keeps its uninjected vectors, `set_meta` stamps `chunking_metadata = "prefix"` over the whole
index, and the next `pnk sync` and `pnk doctor` both report **no drift**. Every command succeeds,
and half the index is injected.

**The fix separates the two costs that had been treated as one.** The docstring said the document
is "never re-extracted, never re-embedded", as though those were the same protection. Extraction is
what spends money; embedding is local and free, and the chunk texts are carried forward anyway. So
the chunks are still copied and the extraction still never re-run, and the vectors are recomputed
under this run's settings — which fixes both directions, since turning injection *off* again had
the mirror-image defect.

**One guard is deliberately louder than it needs to be today.** `unnumbered_heading_path` is not
persisted (`chunk.Chunk` says why: the stored form is the citation form, and a second column is a
second thing to keep in step). A carried-forward chunk therefore cannot say what its path looks
like with the section numbers removed, so injecting the stored form would quietly prepend the
citation form this experiment measured at 44% numbers and rejected. Unreachable now — only PDFs are
ever protected and the PDF path records no heading path — but **step 5 of this plan is PDF layout
heuristics**, which is exactly what would make it reachable. It refuses with a named remedy instead.

**What the review round found beyond that, all of it in code this increment wrote:**

| | |
|---|---|
| `--sign-test` printed `FAIL at 0.05` and exited **0** | the flag names the 2f gate, which licenses the irreversible schema bump; a driver branching on `$?` would have taken it |
| A miss was written to the artifact as `Infinity` | invalid JSON: `JSON.parse` rejects it, `jq` silently coerces it to 1.8e308 — the one outcome the rank ordering exists to make visible became a very good rank |
| A truncated artifact exited **1**, same as a genuine no-go | `read_outcomes` only refuses a file that *parses*; a `JSONDecodeError` is a `ValueError`, which the first version of the handler did not catch |
| Nothing recorded which leg was which | transposing `--before`/`--after` inverts the verdict, and the identity check cannot catch it — it is never told which value is the baseline, only that the two must differ |
| `pnk doctor`'s half of the drift promise was untested | a mutant reading a constant there passed the entire suite |
| Two more vacuous assertions | `backend.embedded == [rows]` is `[] == []` when a run indexes nothing; `all(…)` over an empty list again |

**Three of those six are the same defect in three costumes, and it is worth naming once.** An
assertion of the form *"everything we produced looks like X"* is silently satisfied by producing
nothing. It has now been found three times in this increment alone — once during development, twice
in review — so the rule is: **any assertion over a collection the code under test produced needs a
companion assertion that the collection is non-empty**, and preferably one that names the expected
count.

**The review that found this was itself a measurement, and it half failed.** Five adversarial
lenses were run as independent agents; a usage limit killed 15 of the 17 agents mid-flight,
including every verifier. The workflow returned `{"confirmed": [], "refuted": []}` — which reads
exactly like a clean review and was nothing of the sort. The findings were recovered from the
agents' own transcripts and verified by hand. **An empty result from a harness that partially
failed is not evidence of absence**, and a report that does not distinguish the two is worse than
no report: `confirmed: []` was one careless sentence away from becoming "the review found nothing".
