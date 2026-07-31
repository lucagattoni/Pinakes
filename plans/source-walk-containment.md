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

**Both layers. Neither alone is enough** — defect 2 needs the load-time check (a glob that pathlib
refuses never reaches the walk), and defect 3 needs the walk-time check (no pattern inspection can
see a symlink).

**Layer 1 — `manifest.py`, in `_sources`.** Apply the existing `roots` predicate to `include` as
well, in the same loop shape and with the same message, substituting the field name. Reject
absolute entries and any entry with `..` in its parts. `exclude` is **not** validated: an `..` there
can only fail to match, never widen the walk — say so in a comment so the asymmetry is not read as
an oversight.

**Layer 2 — `sync.walk_sources`.** Replace the lexical `candidate.relative_to(manifest.root)` with
`linkscan.sidecars_under`'s spelling, which review 10 arrived at and tested: **resolve the parent,
keep the final component unresolved**, then require `is_relative_to(manifest.root)`. A candidate
that fails is skipped, and the skip is reported once **per pattern**, not per file — a hostile or
mistaken `../**` matches thousands. The asymmetry is deliberate and must be preserved: a symlinked
*document* inside the KB is still ingested, while a symlinked *directory* cannot carry the walk out.

Apply the same predicate to the sidecar sweep ten lines below (`root.rglob(f"*{SIDECAR_SUFFIX}")`
→ `candidate.relative_to(manifest.root)` at `sync.py:425`, and `document_for(candidate)
.relative_to(manifest.root)` at `:426`, which has the identical shape).

**Do not** resolve the whole candidate path. Review 10 measured the cost of over-tightening on the
partner side: it drops legitimate documents, and a dropped document is a deleted row.

## Tests

In `tests/test_sync.py` unless a better home exists — check before writing:

| Test | Pins |
|---|---|
| `test_an_include_pattern_that_climbs_out_of_the_kb_is_refused_at_load` | defect 1, layer 1 |
| `test_an_absolute_include_pattern_is_a_manifest_error_not_a_traceback` | defect 2 — assert the message and remedy, **and** that no `NotImplementedError` escapes |
| `test_a_symlinked_directory_cannot_carry_the_walk_out_of_the_kb` | defect 3, layer 2 |
| `test_a_symlinked_document_inside_the_kb_is_still_ingested` | the asymmetry — the over-tightening regression |
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
