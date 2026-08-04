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

**One live item, raised 20260804 05:00** — the first defect the RFC realism corpus surfaced, and it
destroys user work.

**Earlier state, for the record: no live items as of 20260804 04:20.** The one item raised on 20260803 was built and merged the
same evening. Beyond it there is no pinakes code work: the links release is complete, the graph
release is **blocked** at G2's measurement ([`20260729_0256-links-and-graph.md`](20260729_0256-links-and-graph.md)), and what
unblocks it is a corpus ([`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md)).

---

## Live

### 1 · `pnk doctor`'s model-coherence remedy destroys an interrupted sync's work

**Found by using pinakes, not by reading it** — the RFC realism corpus, 20260804, on a first sync
of 300 documents killed at ~106 by an unrelated process death.

**Current.** `sync.py:964` writes the embedding identity keys with `set_meta` **after** the document
loop and `_scan_linked_kbs`, then commits. An interrupted first sync therefore leaves `meta`
carrying `schema_version` and nothing else, and `pnk doctor` reports:

```text
FAIL model coherence: the index does not match the configured model — embedding_dim: index
     has '(absent)', manifest says '384'; embedding_model: index has '(absent)', manifest
     says 'BAAI/bge-small-en-v1.5'; embedding_provider: index has '(absent)', manifest says
     'fastembed'.
     → Run `pnk sync --rebuild`. Embeddings are meaningless across models: a KB that silently
       returned results here would be returning garbage.
```

**Why it is a defect and not a warning.** The check cannot distinguish two states it treats
identically: *the model changed under the index* — genuinely fatal, `--rebuild` correct — and *the
first sync never finished* — benign, and `--rebuild` is **the worst available action**, discarding
every embedding that survived. On this corpus that was about an hour of CPU. A first-time user who
follows the printed remedy loses all of it, and the remedy is stated imperatively with a rationale
that makes it sound unavoidable.

**Required.** Split the two states on **absent vs different**, because they are distinguishable:

* Identity keys **absent** → the index was never completed. This is not a coherence failure; report
  it as its own check (WARN, not FAIL) whose remedy is `pnk sync` — incremental, and it keeps the
  work already done. Say that it keeps it.
* Identity keys **present and different from the manifest** → the existing FAIL, unchanged, remedy
  `pnk sync --rebuild`.
* A partial `meta` — some identity keys present, some absent — is neither, and must not silently
  fall into the benign branch. Treat it as the FAIL.

**Tests.** One per branch, and a test asserting the absent-key path's remedy does **not** contain
`--rebuild` — that string is the whole defect, and a test that only checks the check's *name* would
pass with the destructive remedy still printed.

**Do not "fix" this by writing the identity keys earlier.** They are written after the loop
deliberately; moving them would make a half-built index claim coherence with a model it was only
partly embedded under, which is the failure this check exists to catch. The defect is in the
diagnosis, not the write order.


---

## Closed — recorded so nobody reopens them

| Was | Closed by |
|---|---|
| `docs/STATUS.md`'s header was not gated and drifted four releases — it read `0.4.1` while the roadmap, the PyPI table and `__version__` all said `0.7.1` | `tools/status_header_gate.py`, 20260803 22:43. Parses line 3 for the exact `**Latest release: x.y.z**` shape and compares it against `pinakes.__version__`; a missing, moved or reformatted line fails as loudly as a wrong version. Wired into `check.sh` with its own CI job carrying a negative check |
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
| The iteration log was out of chronological order | Sorted, and now in `20260801_0102-links-and-graph-log.md` — 25 rows, verified sorted |
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
