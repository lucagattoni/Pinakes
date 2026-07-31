# The local source walk escapes the KB

**Audience: the coder. Goal: executor.** One increment, its own branch, its own PATCH release.
**Not part of L6, L7 or L8** — it touches `sync.py` and `manifest.py`, which the links plan does not,
and it should not wait behind an unmerged branch. Land it whenever the tree is free.

Written 20260731 21:25, after L6 review 10 fixed the *partner* side of this and recorded the local
side for the planner. Everything below is measured on `main` at `900aae7`, live in 0.5.0.

## The rule that is only half implemented

`manifest.py`'s `_sources` rejects an absolute or `..`-bearing entry in `[sources] roots`:

```python
if Path(entry).is_absolute() or ".." in Path(entry).parts:
    raise ManifestError(..., message=f"`roots` entry {entry!r} must stay inside the KB")
```

It validates **nothing** in `include`. `sync.walk_sources` then does
`candidate.relative_to(manifest.root)`, which is the *same purely lexical non-guard* review 10
found in `linkscan.sidecars_under`: `docs/../../outside/x.md` **is** relative to the root as a
string, so it returns that path rather than raising. Two spellings of one rule; one of them does not
implement it.

## Three measured defects

**1 — `..` in `include` walks out of the KB and writes files outside it.**

```text
include = ["**/*.md", "../../outside/*.md"]

$ pnk sync
2 indexed, 0 renamed, 0 metadata-only, 0 unchanged, 0 removed
$ ls ../outside/
secret.md   secret.md.pnk.yaml          ← a sidecar minted outside the KB
$ sqlite> select path from documents;
docs/../../outside/secret.md            ← the document key keeps the `..`
```

**2 — an absolute `include` is a raw traceback**, not a `PinakesError`:

```text
include = ["/…/outside/*.md"]

$ pnk sync ; echo $?
Traceback (most recent call last):
  ...
NotImplementedError: Non-relative patterns are unsupported
1
```

No `error:` line and no remedy — out through `cli.main` as a stack trace. That is the class L6's
review rounds have spent four passes closing on the partner side.

**3 — a symlinked directory carries the walk out, with no `..` anywhere.** This is why validating
the patterns is **not sufficient on its own**:

```text
docs/escape -> …/outside          (a symlink, inside the KB)
include = ["*/*.md"]              (no `..`, no absolute path)

$ pnk sync
1 indexed
$ sqlite> select path from documents;
docs/escape/secret.md
$ ls …/outside/
secret.md   secret.md.pnk.yaml
```

Measured too, and worth knowing: the **default** `include = ["**/*.md", "**/*.txt"]` does *not*
escape this way, because `pathlib`'s recursive `**` skips symlinked directories. That is luck about
the standard library, not a guard — a user who writes any non-recursive pattern loses it.

## Why "it is the user's own configuration" does not make this deferrable

That framing is what made it look like a foot-gun rather than a defect, and it does not hold:
`pinakes.toml` is **committed and shared**. Clone a KB from someone else, run `pnk sync`, and
*their* `include` writes sidecars into *your* tree, relative to your clone. It is the same
untrusted-input argument the partner-side fix rests on — one repository hop further away.

It also writes where CLAUDE.md says pinakes may not: a sidecar minted outside the KB is a file
created in a directory the tool was never pointed at.

## What to build

**Copy `linkscan.sidecars_under`, do not re-derive it.** Revised 20260801 00:58: this section
originally specified review 10's shape, and L6 reviews **11, 12 and 13** each found a defect in it.
Rebuilding that sequence here would be the increment's whole cost for nothing. Read
`sidecars_under` at the L6 tip and mirror it; the four attempts and what each got wrong are in
`retro.d/l6-pnk-link.md`. **Both layers, and neither covers the other.**

**Layer 1 — static, *before* `glob`.** This is what bounds the walk. Review 10 checked containment
per candidate *after* globbing, so `../../../../**/*.md` still enumerated and stat'd the whole tree
on every plain sync before refusing what it found — measured on the partner side at 0.123s over 3000
outside files against 0.0005s for the static refusal. For each `(root, pattern)`:

```python
probe = base.joinpath(*(part for part in Path(pattern).parts if part != "**"))
if not (probe.parent.resolve() / probe.name).is_relative_to(anchor):   # anchor = kb_root.resolve()
    ...refuse this pattern...
```

**`**` is dropped from the probe** (L6 review 14, 20260801). `Path.parts` counts it as one
component while `glob` lets it match *zero*, so keeping it let a following `..` cancel it and the
probe landed one level *below* where the walk actually goes: `**/../../**/*.md` probed inside the KB
and then walked the directory containing it, recursively. The drop is exact rather than merely
conservative — every component `**` expands to is one a following `..` then pops, so the
zero-expansion is the highest the walk can reach, and that is what must be inside the KB.

Three more things that spelling gets right and the two obvious alternatives do not:

- **Not "does the pattern contain `..`"** (review 12). `../notes/*.md` from `docs/` lands inside the
  KB and is legitimate; refusing it calls a valid manifest an escape. What matters is where the
  path *lands*, never whether `..` occurs in it.
- **Not "resolve the fixed prefix before the first glob component"** (review 13). A leading glob —
  `*/../../../outside/**/*.md` — has an empty prefix, passes unconditionally, and runs its `..`
  inside `glob`: review 10's unbounded walk, reachable again.
- **Not "resolve the whole path"** (review 13). With no glob component the probe *is* the file, and
  resolving it whole follows a final symlink — so `include = ["alpha.md"]` is refused as an escape
  while `include = ["*.md"]`, the same file, is accepted. Parent resolved, final component left
  alone: the directory chain is followed so `..` collapses and a symlinked ancestor is caught, while
  a symlinked document stays readable. A glob component is a name that does not exist, which
  `resolve()` collapses lexically — so this stays one `resolve()` and no enumeration.

**An absolute pattern gets its own message**, not "reaches outside the KB": that is false for an
absolute path naming this KB's own `docs/`, and `glob` refuses to walk one wherever it points
(defect 2 above is exactly that `NotImplementedError`).

**Layer 2 — dynamic, per candidate.** A symlinked *directory* is invisible to any static check
(defect 3), so the same `probe.parent.resolve() / probe.name` test runs on each candidate — and on
escape it **`break`s**, not `continue`s. Review 12 measured the difference at 360× on a symlinked
escape and found the `break` had no test at all. It must run **before** the `is_file()`/sidecar
skip: a pattern reaching outside that matched only sidecars or only directories hit that `continue`
first, so the walk left the KB and reported nothing.

**One problem per pattern, not per file and not per `(root, pattern)`** — a hostile `../**` matches
thousands, and two roots reported the same escape twice. Collect into a `set` keyed on the pattern.

**`exclude` keeps matching the path it matches today.** Review 10 switched the partner side to the
*resolved* path and review 11 reverted it: with `docs/alias -> docs/real` inside the KB,
`exclude = ["docs/real/*"]` began excluding documents reached as `docs/alias/…`. Here the stake is
higher than on the partner side — a locally dropped document is a deleted index row *and* an
orphaned sidecar, not just a missing inbound edge.

Apply the same predicate to the sidecar sweep below (`root.rglob(f"*{SIDECAR_SUFFIX}")` →
`candidate.relative_to(manifest.root)`, and `document_for(candidate).relative_to(manifest.root)`,
which has the identical shape).

**Where the refusal lives.** Unlike the partner side, this manifest is the user's own, so an
escaping or absolute pattern is a **hard `ManifestError` at load**, matching the `roots` precedent —
layer 1's predicate moves into `manifest._sources`, which already has `root` in hand. Layer 2 cannot
be a load-time error (nothing is resolvable until the walk runs), so it stays a skip plus a reported
problem. `exclude` is **not** validated: an `..` there can only fail to match, never widen the walk
— say so in a comment so the asymmetry is not read as an oversight.

## Tests

In `tests/test_sync.py` unless a better home exists — check before writing:

| Test | Pins |
|---|---|
| `test_an_include_pattern_that_climbs_out_of_the_kb_is_refused_at_load` | defect 1, layer 1 |
| `test_an_absolute_include_pattern_is_a_manifest_error_not_a_traceback` | defect 2 — assert the message and remedy, **and** that no `NotImplementedError` escapes |
| `test_a_symlinked_directory_cannot_carry_the_walk_out_of_the_kb` | defect 3, layer 2 |
| `test_a_symlinked_document_inside_the_kb_is_still_ingested` | the asymmetry — the over-tightening regression |
| `test_the_same_document_is_ingested_by_a_fixed_and_a_globbed_pattern_alike` | review 13's second defect — two spellings of one include must not give opposite answers |
| `test_a_dot_dot_pattern_that_stays_inside_the_kb_is_accepted` | review 12 — refusing a valid manifest is the same defect as accepting an invalid one |
| `test_a_leading_glob_does_not_defeat_the_static_refusal` | review 13's first defect |
| `test_a_double_star_before_a_dot_dot_does_not_defeat_the_refusal` | review 14 — `**` matches *zero* components while `Path.parts` counts it as one, so a following `..` cancels it. **Review 13's ten measured patterns were all correct and none combined `**` with `..`**: a table of cases proves the cases in it and reads like proof of the rule |
| `test_an_escaping_pattern_is_refused_without_enumerating_the_tree` | layer 1's whole purpose — count entries pulled from the generator, not `resolve()` calls |
| `test_the_escape_is_reported_once_per_pattern_not_once_per_file` | the report shape |
| `test_an_excluded_pattern_may_contain_dot_dot` | the stated asymmetry, so a later pass does not "fix" it |

**Mutation, per assertion, not per commit** — round 9b's rule, earned here twice. For each test,
break the guard it names and confirm the failure is on the assertion that **encodes the claim**, not
on an earlier one. A test that fails proves the mutation is caught, never that it is caught for the
stated reason.

## Docs and release

- `docs/MANIFEST.md` — the `[sources]` table: `include` now carries the same constraint as `roots`,
  and `exclude` does not. State why.
- `docs/DESIGN.md` §2.1 only if the *reasoning* changes; a new constraint on an existing field does
  not qualify.
- A `changelog.d/` fragment under `### Fixed`, and a `retro.d/` fragment: the durable lesson is
  **a containment rule written in prose beside one of its two inputs is a rule for one input** —
  three sites carried the same lexical `relative_to` non-guard, and the one with the argument in its
  docstring was the one that did not implement it.
- **PATCH.** It is a bug fix. It *is* a behaviour change for a manifest that already carries `..` in
  `include` — which is a manifest that is writing files outside its own KB, so the `roots` precedent
  (hard error) is the right one. Say so in the CHANGELOG entry rather than softening the check.
