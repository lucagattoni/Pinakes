## Source-walk containment — one rule, three sites, enforced at one (20260801 13:28)

**The durable lesson: a containment rule argued in prose beside one of its two inputs is a rule for
one input.** `manifest._sources` states that a source root must stay inside the KB and enforces it
for `roots`. `include` sat two lines away, validated nowhere. The same lexical
`candidate.relative_to(root)` non-guard then appeared at three sites — `linkscan.sidecars_under`
(fixed in L6 review 10), `sync.walk_sources`, and the sidecar sweep beside it — and the one whose
docstring carried the argument was the one that did not implement it.

**All three defects were re-measured on 0.7.0 before anything was changed**, against a plan that had
measured them on 0.5.0 at `900aae7`. All three still reproduced, unchanged:

| | Before | After |
|---|---|---|
| `include = ["../../outside/*.md"]` | `2 indexed`, **a sidecar minted outside the KB**, document keyed `docs/../../outside/secret.md` | `ManifestError` at load, naming the pattern and the root |
| `include = ["/abs/path/*.md"]` | bare `NotImplementedError` traceback out of `cli.main` | `ManifestError`: *"is an absolute path"*, with its own remedy |
| `docs/escape -> /outside`, `include = ["*/*.md"]` | `1 indexed`, **a sidecar minted outside the KB** | `0 indexed`, the pattern reported, nothing written outside |

**HIGH — a fourth defect, found by a test that was meant to pin correct behaviour.** Layer 1
deliberately *accepts* a `..` pattern that lands inside the KB (`include = ["../notes/*.md"]` from
`docs/`), because what matters is where a path lands rather than whether `..` occurs in it. The test
asserting that then failed on the document's key: `relative_to` is lexical, so it returned
`docs/../notes/n.md`. Measured with `roots = ["docs/", "notes/"]` and
`include = ["../notes/*.md", "*.md"]`, one file on disk produced **one indexed document and two
failures** — *"appeared after the walk had already read this directory"* — because the sidecar found
under one key was invisible under the other, and the unmatched sweep reported an indexed document as
unmatched. Nothing in the plan predicted this; it exists only because the legal `..` case had never
been exercised.

The fix is **lexical** collapse (`posixpath.normpath`), not `resolve()`. Resolving would follow a
symlinked *directory* and re-key every document under it — `docs/alias/x.md` becoming
`docs/real/x.md` — which on an existing KB is a path change against a permanent identity. Lexical
collapse touches only paths containing `..`, and every one of those is already broken today.
Containment does not rely on it: the per-candidate check resolves.

**The predicate was copied from `linkscan.sidecars_under`, not re-derived, and that was the whole
point.** Reviews 11, 12, 13 and 14 each found a different defect in a different spelling of this one
rule: refusing any `..` (rejects a valid manifest); resolving only the prefix before the first glob
component (defeated by a leading `*`); resolving the whole path (refuses a symlinked *document*
while accepting the same file via `*.md`); and keeping `**` in the probe (it matches *zero*
components while `Path.parts` counts it as one, so a following `..` cancels it). Re-deriving would
have cost that sequence again for nothing.

**MEDIUM — the static layer is the bound, and the dynamic layer is the guard; neither covers the
other.** Checking candidates after globbing refuses the results while still paying for the
enumeration, which is what the `roots` rule exists to prevent —
`test_an_escaping_pattern_is_refused_without_enumerating_the_tree` counts entries pulled from the
generator, not `resolve()` calls, because the cost being avoided is the walk itself. And a symlinked
directory has no `..` and no absolute path, so it is invisible to any load-time check. The
per-candidate test `break`s rather than `continue`s, and runs **before** the `is_file()`/sidecar
skip: a pattern reaching outside that matched only directories or only sidecars hit one of those
`continue`s first, so the walk left the KB and reported nothing.

**LOW — the default `include` is safe by luck, not by design.** `["**/*.md", "**/*.txt"]` does not
escape through a symlinked directory, because `pathlib`'s recursive `**` skips them. Any user who
writes a non-recursive pattern loses that, which is exactly the shape of a guarantee nobody knows
they are relying on. Stated in `walk_sources`' docstring rather than left as folklore.

### Mutation round — three survivors, two of them defects (20260801 13:38)

Eleven guards broken on purpose. Eight were caught immediately. The three that survived were worth
more than the eight:

**HIGH — the per-root skip copied from `linkscan` was data loss here.** `sidecars_under` does
`if pattern in escaping: continue`, so a pattern known to escape contributes nothing under any later
root — correct there, where a dropped candidate costs one inbound link and a partner's `[sources]`
is one statement about one KB. Copied into `walk_sources` it means something else entirely: the
escapes *this* loop can see are **symlinks**, which are a property of one directory rather than of
the pattern, and a dropped candidate here is a **deleted index row and an orphaned sidecar**. So
`docs/escape -> /outside` silently stopped `*/*.md` collecting anything under an unrelated second
root. Removed, with a test. "Copy the predicate, do not re-derive it" was the right instruction and
this was still the wrong thing to copy — the predicate and the policy around it are different
decisions.

**MEDIUM — the containment check ran before `is_file()`, and no test could tell.** Every symlink
test matched a *file*, so moving the check after the skip changed nothing observable. The case the
ordering exists for is a pattern that matches only a **directory** (or only sidecars): it hits that
`continue` first, and the walk leaves the KB reporting nothing. `*/*` against a symlinked directory
containing a subdirectory is that case, and it now has a test.

**MEDIUM — the `break` bounded nothing, because `sorted()` had already drained the generator.** The
plan carried `break`, not `continue`, on a 360× measurement from `linkscan` review 12 — where the
loop is lazy. Written here as `for candidate in sorted(root.glob(pattern))` the enumeration a
symlinked escape triggers has *already happened* by the time the first candidate is inspected, so
the `break` saved only the loop body, and the `resolved` cache made even that one dict lookup. This
is the shape of a guard inherited with its justification and without the property the justification
rested on. The loop is now lazy; output order does not depend on it, because `walk_sources` sorts
what it returns and the per-root sort only decided which of two candidates sharing one key won —
and they describe the same file with the same hash. Measured: **301 entries enumerated before, 1
after**, and both the `break` and a reversion to `sorted()` are caught by that number.

### Two tooling corrections swept in the same PATCH (20260801 13:52)

**`tools/link_density_gate.py`** resolved one of its two bases and not the other, so any
non-canonical root — every `/tmp` path on macOS — exited with a traceback. One `root.resolve()` at
the top of `census`, and a test driving the tool through a symlinked parent.

**`tools/fragments.py`'s duplicate-heading defect was already closed**, and the open-corrections
entry saying "the tool is unchanged" is stale. Measured rather than assumed: three fragments
(two `fixed-*`, one `added-*` whose body begins `- **Fixed: …**`) spliced into a section that
already had a `### Fixed` produce exactly one `### Fixed`, one `### Added`, and the
category-prefixed entry filed by its **filename**, which is where the category belongs. Both halves
have regression tests already —
`test_fragments_merge_into_a_category_heading_that_already_exists` asserts `count("### Added") == 1`.
Closed by the 0.6.0 release-prep commit, not by this one.

**LOW, and the reason to write this down: `fragments.py --apply` is anchored to the repo it lives
in, not the working directory.** Testing it by `cd`-ing to a temp tree spliced *this* worktree's
`CHANGELOG.md` and deleted its `changelog.d/` fragment, reporting success. `--repo` exists exactly
for that and the tool's own test suite uses it. The damage was recoverable only because the
fragment had already been committed — which is the same rule the G1 mutation harness earned:
**commit before running anything that rewrites the tree.** A `git checkout --` to undo a mutation
in the same session then reverted an *uncommitted* fix in `tools/`, for the second time in this
project, and was caught only by re-reading `git diff --stat` afterwards.
