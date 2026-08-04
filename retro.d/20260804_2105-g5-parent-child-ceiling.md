## G5 — the `parent-child` ceiling, measured before the gate ran (20260804 21:05)

**The measurement the arity decision required, and the corpus that could supply it was neither of
the two anyone would have reached for.** `plans/20260804_1844-decision-parent-child-arity.md`
keeps `parent-child` transitive and asks for a ceiling *"against a corpus whose chunker actually
populates `heading_path`"* — because the projection of 5.8×–53.5× the chunk count had never been
run against one. Both obvious candidates fail for **different** reasons, and only the second was
known:

| corpus | documents | chunks | carry a `heading_path` | heading depth | `parent-child` |
|---|---|---|---|---|---|
| RFC realism | 300 | 106 806 | **0** | — | **0** — structural chunking degraded silently |
| `tests/demo-kb` | 30 | 60 | 60 | **always 1** | **0** — every document is flat |
| this repo's `docs/` + `plans/` | 43 | 2 671 | 2 671 | median 2, max 4 | **13 232** |

`tests/demo-kb` populates `heading_path` on every chunk and still derives zero hierarchy edges,
because a depth-1 path has no ancestor. **A corpus can satisfy "the chunker works" and still
exercise nothing**, which is a second way to get a zero that looks like a measurement — and it is
the shape the go decision's own bound warns about, one layer in.

### The numbers

Real Markdown, written by hand, with real nesting — 43 of this repository's own documents, indexed
into a scratch KB (never committed; `docs/` and `plans/` are the corpus):

* **4.95 `parent-child` rows per chunk** — 13 232 over 2 671 chunks. Against `sibling`'s 2 628 and
  `in-section`'s 2 509, hierarchy is **71% of every stored edge**, on a corpus where `sibling` is
  one row per adjacent chunk. It lands *below* the 5.8× floor the decision projected, so the
  projection was pessimistic rather than optimistic.
* **Derivation costs nothing.** The whole edge set derives in 0.158 s; the hierarchy alone is
  **0.004 s** for those 13 232 rows. G3's ancestor-lookup form is linear in chunks and quadratic
  only in a document's *distinct heading paths* (median 11 here, max 76), exactly as it claims.
  **The cost is row count, never wall clock**, which is what the decision predicted and is worth
  stating because it changes which mitigation would ever be needed.
* **Index growth is 12.9%** — 11.17 MB with the hierarchy against 9.89 MB without, both `VACUUM`ed.
  On a corpus of this shape the absolute number is 1.2 MB, and it scales with rows, not bytes of
  text: an index dominated by 384-dimensional embeddings (the RFC corpus is 265 MB for 106 806
  chunks) would grow proportionally far less.

### The ceiling is not alarming, and the standing risk is unchanged

Extrapolating 4.95 rows/chunk to the RFC corpus's 106 806 chunks gives **~529 000** hierarchy rows
against its 107 802 total today — a five-fold graph, derived in well under a second. That is a
number, not a problem, and it does **not** license switching to the immediate-parent variant: the
decision is explicit that the variant is the arm to *measure* if the ceiling proves alarming, never
the default to switch to first.

**What is still unmeasured is the tail.** 4.95 is a mean over documents whose median depth is 2.
The decision's standing risk — *"a corpus with deep heading nesting and large sections could make
`parent-child` the dominant kind"* — is about a shape none of these three corpora has: deep
nesting **and** many chunks per section, where the row count is the product. This corpus's worst
document carries 76 distinct heading paths and its arity stays modest because its sections are
short. Nothing here refutes that risk; it bounds the ordinary case and leaves the tail where the
decision left it.

### The tail, measured (20260804 22:39) — and it is alarming

The paragraph above left the standing risk as prose. It is now a number. A **purpose-built
worst-shape corpus** — six documents, heading depth 4, every heading path carrying ~26 chunks,
which is the *a·d* product the risk names — was generated, synced with the same real backend, and
measured the same way:

| | this repo's `docs/` + `plans/` | worst-shape corpus |
|---|---|---|
| chunks | 2 671 | 2 483 |
| heading depth, median / max | 2 / 4 | 3 / 4 |
| chunks per heading path, median | short sections | **26** |
| `parent-child` rows | 13 232 | **132 630** |
| **rows per chunk** | **4.95** | **53.42** |
| share of every stored edge | 71% | **94.7%** |
| **index growth** | **+12.9%** (1.2 MB) | **+113.4%** (13.3 MB) |
| derivation | 0.004 s (hierarchy) | 0.84 s (140 079 edges, every kind) |

**53.42 lands at the very top of the decision's projected 5.8×–53.5× band**, so the projection was
accurate at both ends rather than pessimistic: 4.95 sits below its floor for ordinary prose, 53.4
reaches its ceiling for the shape it warned about. **The index more than doubles.** Derivation
stays cheap — 140 079 edges in 0.84 s — which confirms the decision's own prediction that *the cost
is row count, never wall clock*, and therefore that no mitigation aimed at derivation time would
help.

**What this corpus is, and is not.** Synthetic and deliberately adversarial: generated Markdown
with uniform nesting and uniform section length, built to make the product as large as plausible
rather than to resemble anyone's notes. It is **not** evidence that real corpora do this — neither
real corpus measured above comes close. It is evidence that the shape is reachable without anything
exotic, because depth 4 with long sections is an ordinary specification or manual.

**No variant is switched to here, on purpose.**
[`plans/20260804_1844-decision-parent-child-arity.md`](../plans/20260804_1844-decision-parent-child-arity.md)
is explicit that if the ceiling proves alarming the immediate-parent form is *the arm to measure*,
never the default to change first — and `--drop parent-child` is already a reported leg of G5's
matrix. This is the input to that decision; the decision is the planner's.
