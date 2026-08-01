# Open corrections

**Audience: an implementing agent. Goal: executor.** Every live item names the file, the current
text and the required text. Nothing here is a judgement call — if an item reads as a question, that
is a defect in this file; say so rather than choosing.

Restructured 20260801 11:30, after the 0.6.0 release: **nine of the original twelve items were
already closed**, most of them as a side effect of the work that closed something else. A list where
two thirds of the entries are done is one nobody reads to the bottom, so the live items are first and
the closed ones are a table.

**Documentation items are no longer here.** Since the ownership decision (20260801 01:24,
`CLAUDE.md`) every `docs/**`, `plans/**`, `README.md`, `CLAUDE.md` and `CHANGELOG.md` correction is
the planner's, and this file held six. They were closed as part of that ownership, not by an
implementer. What remains below is code and tooling.

**Since 20260801 12:14 these are the only buildable pinakes increments.** The links release is
complete and the graph release is blocked at G2's measurement, so
[`links-and-graph.md`](links-and-graph.md) has nothing an agent can pick up. The work that unblocks
it is a corpus rather than code ([`realism-corpus.md`](realism-corpus.md)), and these three are what
there is to build in the meantime.

---

## Live

### 1 · `tools/link_density_gate.py` — an uncaught `ValueError` on a non-canonical root

**Current:** `census` calls `document.relative_to(root)` on the **raw** root while `documents_of`
resolves its bases (`(root / name).resolve()`). On macOS, where `/tmp` symlinks to `/private/tmp`,
the two disagree and the tool dies with a traceback. Still reproduces on `main`, 20260801 11:30:

```text
$ cp -R tests/demo-kb /tmp/dgt && uv run python tools/link_density_gate.py /tmp/dgt
ValueError: '/private/tmp/dgt/docs/access-restrictions.md' is not in the subpath of '/tmp/dgt'
```

**Required:** resolve the root once at the top of `census` (`root = root.resolve()`), so the
denominator and the `relative_to` share one base. A test passing a root through a symlinked parent
pins it.

**Why it matters:** it only bites on an explicit non-canonical root, so the committed corpora are
fine and CI is green — but this is the tool an executor is told to run *against a copy* when
comparing the gate's number with `pnk doctor`'s, and on this platform that is a `/tmp` path.

---

### 2 · `tools/fragments.py` — duplicate `###` headings on splice

**Current:** applying the 7 changelog fragments at the 0.6.0 cut produced a section with **two
`### Fixed` headings**, and one entry beginning `- **Fixed: …**` filed under `### Added` — the
fragment's own prefix, in the wrong section. The tool concatenates fragments in order and does not
merge same-named headings. Repaired by hand for 0.6.0; the tool is unchanged.

**Required:** group by heading and emit one block per category in Keep-a-Changelog order (`Added`,
`Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`). A test that applies two fragments sharing
a category and asserts one heading in the output.

**Why it matters:** it is silent, it lands in the artifact that is published and cannot be
re-uploaded, and it scales with fragment count — 11 at this release, and the graph release will have
more.

---

### 3 · The local source walk escapes the KB — its own increment

Three measured defects in `sync.walk_sources` and `manifest._sources`, live since before 0.5.0: a
`..` in `[sources] include` walks out of the KB and mints sidecars outside it; an absolute `include`
is an unhandled `NotImplementedError` traceback; and a symlinked directory carries the walk out with
no `..` anywhere. Too large for this file — the build order, the two layers, the ten tests and the
PATCH release are in [`source-walk-containment.md`](source-walk-containment.md).

**Take this one if you built L6**, and read its first instruction: *copy `linkscan.sidecars_under`,
do not re-derive it.* Reviews 10–14 each killed a different plausible-looking spelling of that rule.

---

## Closed — recorded so nobody reopens them

| # | Was | Closed by |
|---|---|---|
| 1 | `sidecar.py`'s docstring overstated the 1.1 → 1.2 fix | Now says *"three of the four"*, and that `0755` becomes int **755** |
| 2 | `CHANGELOG.md` `[0.5.0]` stated one break twice, once over-broadly | One statement, carrying the *uniformly-keyed nested mapping* precision |
| 3 | `docs/MANIFEST.md`'s `rel` row credited the user, not `pnk link` | Fixed on the L6 branch |
| 4 | `docs/STATUS.md`'s verified-install claim omitted the manifest edit | Rewritten and re-verified against **0.6.0** from the index, 20260801 11:10 |
| 5 | Both 🚫 rows listed link-coverage reporting, which shipped in v0.1 | Moot: the links-release row left both tables at the final cut |
| 6b | The plan's baseline said 0.4.0 and a stale `main` | Re-baselined at `6421cb1`, 20260801 |
| 6c | The verification table named two tests that do not exist | Repointed; `tests/test_verification.py` green |
| 6d | L6 named two tests L5b already owned | L6 shipped with distinct names |
| 7 | The iteration log was out of chronological order | Sorted, and now in `links-and-graph-log.md` — 25 rows, verified sorted |
| 9 | L6 review 7's freshness test never entered the freshness branch | Review 8b closed it the other way; the prescribed fix would now pin behaviour review 8 replaced |
| 12 | L7 shipped without two of its four Docs items | Both fixed before the 0.6.0 tag. **The rule it earned:** the last step before declaring an increment done is to re-read its own Docs list and grep for each sentence the plan quotes |

---

## Not to be fixed — recorded so nobody tries

- **A sidecar carrying its own `%YAML 1.1` directive** is parsed at 1.1, so `country: NO` becomes
  `False`. Frozen in 0.5.0; a `changelog.d/` fragment already recorded it.
- **An integral `!!float`** keeps its tag and gains quotes on rewrite. Same fragment.
- **A uniformly non-string-keyed nested mapping** is accepted and coerced. A stated residual in
  `docs/MANIFEST.md`'s bounds table, not a defect.
- **The `v0.5.0` tag annotation** says "Three breaking changes". Tag annotations are not cleanly
  rewritable and the tag is published; the release body and CHANGELOG are the corrected records.
- **A raw NUL byte reaches user-facing output** from a hand-written `[[links.kb]] path` using the
  `\u0000` escape — unreachable from `argv`, which cannot carry one. Sanitising the path into the
  message would cost the *name what the author wrote* property L6 review 9 exists to protect.
