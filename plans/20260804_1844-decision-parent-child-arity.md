# Decision — `parent-child` stays transitive, and its cost is measured before G5

**Audience: the coder and the planner. Goal: executor.** DECIDED by the planner, 20260804 18:44,
raised by G3's implementer as a spec defect rather than worked around — which is what the go
decision asked for.

## The question

`parent-child` derives from a `heading_path` prefix relation within one document. Its **arity was
never specified.** G3 built it transitively: every ancestor path joined to every descendant path, so
a section with *a* chunks above a subsection with *d* chunks yields *a·d* rows. Measured on
plausible document shapes, that is **5.8×–53.5× the chunk count**.

It did not bite on the RFC realism corpus — but only because every chunk there has an empty
`heading_path`, so `parent-child` derived **zero edges**. The cost is real and unmeasured.

## The decision

**Keep it transitive, as built.** Three additions, none of them code today:

1. **A measured ceiling is required before G5's gate runs.** Derive against a corpus whose chunker
   actually populates `heading_path` and record `parent-child` edges per chunk, wall-clock, and
   index growth. **The only corpus this has run against derived zero of them**, so every number
   above is a projection.
2. **`parent-child` becomes a second G5 arm**, beside `--drop sibling`. `select_kinds(drop=[...])`
   already makes it a flag.
3. **If the ceiling is alarming, the immediate-parent variant is the arm to measure** — not a
   change to make first and measure afterwards.

## Why transitive

**It is what was measured.** `tools/reachable_ceiling_probe.py`'s predicate is

    def _is_prefix(a: str, b: str) -> bool:
        return a != b and (b.startswith(a + " > ") or a.startswith(b + " > "))

— **any** ancestor, in **both** directions, not the immediate parent. The 12-failing/9-liftable
figure that unblocked the graph release
([`20260804_1442-decision-g3-go.md`](20260804_1442-decision-g3-go.md)) was produced under that
relation. Narrowing the shipped edge set to immediate-parent-only would mean **the measurement no
longer describes what ships**, and it narrows it in the direction that costs reach: at depth 2 a
grandparent is one hop away transitively and two hops away immediately, and 2 hops is the whole
budget the precondition was measured against.

**And arity is a retrieval-quality question, in the same class as `sibling`.** The go decision
refused to let a reachability ceiling choose the kind set, and sent that question to G5's gate. The
same reasoning applies here, for the same reason: a ceiling gauge cannot rank, and an argument
cannot measure.

## Why not the alternatives

| Option | Why not |
|---|---|
| **Immediate parent only** | Cheap and tempting, but it changes the relation the probe measured and shortens reach at exactly the depth the precondition tested. It would be deciding a retrieval question on a cost argument. It is the right thing to *measure* if the ceiling proves alarming — as an arm, not as a default |
| **Hub the hierarchy** | Contradicts APPROACH §3, which keeps hierarchy unhubbed on purpose. `in-section` is already the per-document heading hub; adding a second hub over the same structure changes the node model to solve a row-count problem |
| **Cap the arity** | An arbitrary truncation, silent by construction, in the one kind whose whole content is structure. A cap that fires is indistinguishable from a corpus that has no deep nesting |

## What is already true, and needs no work

* **The arity is visible, not implicit.** `tests/test_edges.py::test_the_hierarchy_row_count_is_pinned_because_it_is_the_product_of_two_sections`
  pins the row count as a product, so a change to the relation fails a test that names why.
  `test_hierarchy_matches_the_naive_prefix_predicate` pins equivalence with the naive form.
* **Derivation is linear in chunks**, quadratic only in a document's *distinct heading paths* — the
  implementation looks ancestors up rather than testing every chunk pair. The row *count* is the
  concern here, never the derivation time.
* **The per-kind census reports it**, so an explosion is a number in the report rather than a
  surprise in the index size.

## The standing risk this leaves

**A corpus with deep heading nesting and large sections could make `parent-child` the dominant
kind**, on a `pnk sync` that already runs from three git hooks. That is stated rather than mitigated,
because mitigating it now means choosing a shape for the relation before anyone has measured one.
Requirement 1 is what converts it from a guess into a number.
