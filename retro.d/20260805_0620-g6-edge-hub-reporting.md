## G6 — Edge-hub reporting (20260805 06:20)

**MEDIUM — the enumeration order this check's own sort relied on was implicit.** The first cut
enumerated hub node ids with `SELECT DISTINCT src FROM edges WHERE kind = ?`, no `ORDER BY` — the
only query touching `edges` in this codebase without one; every read in `graph/edges.py` orders
explicitly, and that file's own docstring argues for it. It happened to come back in ascending
`src` order today (a covering-index scan on `edges_src(src, kind)`), which is exactly the "mint
order" the first test's fixture needed to differ from degree order to prove the `.sort()` was doing
real work. That property held by accident of a query plan, not by anything this function asserted.
Fixed with an explicit `ORDER BY src`. Found by an adversarial review agent, not by any test — no
test could have caught it, since the property under test (the sort) still worked; only reading the
query against the file's own convention surfaced it.

**MEDIUM — one of the three hub kinds shipped with zero assertions on its printed text.** `_hub_label`
has three branches — `tag`, `dir`, `heading` — and the landing commit tested `tag` (the sort-order
fixture) and `heading` (the human-actionable-label fixture) but never `dir`. `co-located` appeared
in a docstring only, explaining why the *other* fixtures were built to avoid triggering it — which
reads, on a second look, exactly like the tests were routed around covering it rather than covering
it. `test_a_directory_hub_is_named_by_its_kb_root_relative_path` closes it.

**LOW, folded into the fix above — a degree tie had no assertion in either direction.** `top.sort(key=
lambda item: item[1], reverse=True)` is a stable sort, so two hubs at equal degree kept whatever
order they arrived in — which is to say, the same implicit query-plan order the first finding
flags, one layer further in. Given a real tie the printed order was accidental twice over. Fixed by
sorting on `(-degree, kind, key)` explicitly, and `test_a_degree_tie_breaks_deterministically_and_
the_rest_are_counted` builds four hubs tied at degree 2 whose mint order is the *reverse* of their
correct printed order — reverting the tiebreak makes the mutant print `d, c, b` instead of
`a, b, c`, which is the sharpest test in this increment: it fails on a `reverse=True`-only sort
that every other test here would still pass.

**LOW, self-inflicted — a vacuous assertion, written by the implementer, in this same increment.**
While extending an existing test's block with a new line, an assertion checking for a string that
appears nowhere in `src/` — `"unchecked until the links release" not in detail` — was added twice
(once by the edit that introduced the increment's other tests, once copied into a third test written
later in the same session). It always passed, proved nothing, and is exactly the failure class this
project's own `CLAUDE.md` names: *"an assertion satisfied by something other than the property it
names."* Caught by cross-referencing the diff against `src/` during this same retrospective pass
(`grep -rn "unchecked until the links release" src/` returns nothing), not by any tool — nothing
in `check.sh` can distinguish a true-but-empty assertion from a load-bearing one. Removed.

**Read together:** three of these four findings trace to the same root — an *implicit* order (query
plan, sort stability) standing in for an *explicit* one, discovered because it happened to agree
with what a fixture needed. G3's own docstrings warn about exactly this shape for a `src`-only read
of a symmetric edge kind ("a confident, wrong, smaller answer"); this increment reproduced a milder
version of it one level up, in the read that reports G3's own structure back to a human.
