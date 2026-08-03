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

**One live item, raised 20260803 22:23.** The three that were here closed in 0.7.1 and the list was
briefly empty; the item below replaced it within the hour, which is the ordinary state of this file
rather than a setback. Beyond it there is no pinakes code work: the links release is complete, the
graph release is **blocked** at G2's measurement ([`links-and-graph.md`](links-and-graph.md)), and
what unblocks it is a corpus ([`realism-corpus.md`](realism-corpus.md)).

---

## Live

### 1 · `docs/STATUS.md`'s header is not gated, and drifted four releases

**Current:** line 3 read `**Latest release: 0.4.1**` on 20260803, with the roadmap ticked through
**0.7.1**, the PyPI table listing 0.7.1, and `__version__` at 0.7.1. The line alone was wrong, in
the file whose own preamble says *"This file is the only place in the repo that says what is
built"* — and this repo is public. Corrected 20260803 22:23; `docs/RELEASING.md`'s sweep table now
names it. **Neither of those stops it recurring**, which is the actual item here.

**Required:** a `check.sh` gate — `tools/status_header_gate.py`, appended at the same place every
new gate is, with its `.github/workflows/ci.yml` and `tests/test_check_script.py` entries.

* Parse `**Latest release: x.y.z**` out of `docs/STATUS.md`. **Not found, or not that exact shape →
  fail**, so deleting or reformatting the line cannot silence the gate.
* Compare against `pinakes.__version__`. Unequal → fail, naming both values and the file.
* **The invariant holds with no exception window.** On `main`, `__version__` *is* the latest
  release: the release commit bumps it, and `docs/RELEASING.md` step 2 puts that in the same commit
  as the sweep. Between releases neither moves. So the gate never goes red on a correct tree — check
  that claim against the procedure before writing it, not after.

**Gate only the version, never the `last reviewed` date.** A wall-clock staleness check fails on a
quiet weekend with no code change — decided already, and recorded in `check.sh` beside
`prices-toml-parses`. Copy that reasoning rather than re-deciding it.

**Tests.** `tests/test_check_script.py` — the gate is invoked; and a unit test per branch: agreeing
versions pass, disagreeing versions fail naming both, a missing line fails, a reformatted line
fails. **Mutation-verify the comparison specifically** — a gate that reads the file and never
compares is this project's recurring defect, and it would pass every test that only checks exit 0.

**Why it matters:** a written checklist missed this four times running. That is the project's own
threshold for turning a checklist item into a gate — the same reason `changelog.d/`, `retro.d/` and
`nul-scan` exist.

---

## Closed — recorded so nobody reopens them

| Was | Closed by |
|---|---|
| `tools/link_density_gate.py` died with a `ValueError` on a non-canonical root — every `/tmp` path on macOS, and running it against a copy is exactly what an executor is told to do | 0.7.1. `census` resolves the root once, so the denominator and the `relative_to` share one base |
| `tools/fragments.py` spliced **two `### Added` headings** into one section, and filed a `Fixed:` entry under `Added` — silent, and it lands in an artifact that cannot be re-uploaded | Fixed with a test (`tests/test_fragments.py`). `_merge_into_section` reuses an existing `### Category` heading, bounded to the anchor's own section so an older release's heading is never written into |
| The local source walk escaped the KB: a `..` in `[sources] include` minted sidecars outside it, an absolute pattern was a bare `NotImplementedError`, and a symlinked directory carried the walk out with no `..` anywhere. Live since before 0.5.0 | 0.7.1, as its own increment. **A fourth defect was found by a test written to pin *correct* behaviour** — a legal `..` landing inside the KB kept the `..` in the document key, so one file reachable two ways indexed once and failed twice |
| `sidecar.py`'s docstring overstated the 1.1 → 1.2 fix | Now says *"three of the four"*, and that `0755` becomes int **755** |
| `CHANGELOG.md` `[0.5.0]` stated one break twice, once over-broadly | One statement, carrying the *uniformly-keyed nested mapping* precision |
| `docs/MANIFEST.md`'s `rel` row credited the user, not `pnk link` | Fixed on the L6 branch |
| `docs/STATUS.md`'s verified-install claim omitted the manifest edit | Rewritten and re-verified against **0.6.0** from the index, 20260801 11:10 |
| Both 🚫 rows listed link-coverage reporting, which shipped in v0.1 | Moot: the links-release row left both tables at the final cut |
| The plan's baseline said 0.4.0 and a stale `main` | Re-baselined at `6421cb1`, 20260801 |
| The verification table named two tests that do not exist | Repointed; `tests/test_verification.py` green |
| L6 named two tests L5b already owned | L6 shipped with distinct names |
| The iteration log was out of chronological order | Sorted, and now in `links-and-graph-log.md` — 25 rows, verified sorted |
| L6 review 7's freshness test never entered the freshness branch | Review 8b closed it the other way; the prescribed fix would now pin behaviour review 8 replaced |
| L7 shipped without two of its four Docs items | Both fixed before the 0.6.0 tag. **The rule it earned:** the last step before declaring an increment done is to re-read its own Docs list and grep for each sentence the plan quotes |

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
