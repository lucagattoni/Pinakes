# Cutting a release

**Audience: the agent cutting it. Goal: executor.** Follow it in order; nothing here is a judgement
call. The *rules* about when to release, and the traps that have cost this project a release before,
stay in [`CLAUDE.md`](https://github.com/lucagattoni/pinakes/blob/main/CLAUDE.md) — this file is the procedure they point at.

Extracted from `CLAUDE.md` on 20260801 02:07, when that file crossed its own size guardrail. Nothing
was dropped in the move.

## Before you start

1. **Check what has already landed.** `git fetch`, then diff `origin/main` against this work's base.
   Another agent, session or worktree may have cut a release since this branch started, so the number
   you were about to assign — or a plan's assumed target — may already be taken. Decide the number
   only after that check. *(20260728: an I6a worktree almost reasoned about "0.2.1 vs 0.3.0" from a
   stale base, when a parallel docs pass had already shipped v0.2.1.)*
2. **`python3 tools/shared_file_overlap.py --fetch --strict`**, then *read* the merged state of what
   it names.

## The procedure

1. `python3 tools/fragments.py --apply` — splices `changelog.d/` and `retro.d/` into `CHANGELOG.md`
   and `docs/RETROSPECTIVES.md`, then deletes the fragments. A release that skips this and runs it
   later splices into the wrong version.
2. Bump `__version__` in `src/pinakes/__init__.py`.
3. Move `[Unreleased]` into a dated `[x.y.z] — YYYYMMDD HH:MM` section. **Add its link definition at
   the foot and repoint `[Unreleased]`'s compare** — `fragments.py --apply` splices entries and does
   not touch the footer.
4. Commit, then **land with `python3 tools/land.py <branch>`** — never `git merge` by hand. It
   merges in the primary checkout whatever directory you ran it from, refuses if `main`'s sha did
   not move, and pushes; `--cleanup-only` removes the branch and its worktree later, once you have
   seen CI go green. Merging from inside the feature worktree merges the branch into itself and
   reports success three times over
   ([`CLAUDE.md`](https://github.com/lucagattoni/pinakes/blob/main/CLAUDE.md)).
5. (`land.py` pushed for you. If you landed by hand anyway, push now.)
6. `make release-check` — prints `__version__` and the tag to push. **Run it before the tag, never
   after**: a tag publishes to PyPI, and PyPI does not allow re-uploading a version.
7. `git tag -a vx.y.z`, push the tag. The workflow refuses a tag disagreeing with `__version__`.
8. Create the GitHub release, notes drawn from that CHANGELOG section.

## Verify it happened — never assume

`git tag -l`, `gh release list`, and `git merge-base --is-ancestor vx.y.z main`, **before** writing
release notes. A CHANGELOG entry and a `__version__` are only claims: v0.1.0 had both for two days
with no tag, no release and nothing published (`RETROSPECTIVES.md`, 20260727).

## Sweep the three documents a release stales, in five places — in the release commit, not later

| Document | What goes stale |
|---|---|
| `docs/STATUS.md` — **line 3** | `**Latest release: x.y.z**`. **Missed by four consecutive release sweeps** (0.5.0 → 0.7.1) because this table did not name it, while the same sweeps updated all three rows below. It is the first line a reader sees and it contradicted the file's own tables in a public repo. Bump it with `__version__`, in the same commit |
| `docs/STATUS.md` — *Published on PyPI* | The published-version list. It is a fact about the **index**, not about this repo |
| `docs/STATUS.md` — *Release roadmap* | Tick the row, and drop the name from the unbuilt-work table above it — **only at a release's final cut**, never at an interim one |
| `README.md` | The install lines, if the release added an extra or a capability a new user would look for |
| `docs/ROADMAP.md` | **Three places, and it was missed the first time this table was used against it.** The summary table needs a row; Part 4 needs a `## x.y.z — <title> · <stamp>` section (the table's row links to its anchor, so the two are written together or the link dies); and Part 5's *Open corrections* heading carries its own **item count in the anchor** — closing an item there changes the anchor and silently breaks every in-page link to it. Added 20260805 18:02, after 0.12.0's sweep found the list naming three items that had closed and repeating a diagnosis the plan had already withdrawn |

**Also grep the whole tree for claims the release just falsified** — the class a checklist of
*sections* cannot catch, found eight times on 20260803, in three docs contradicting a fourth:

    grep -rn "unreleased\|in no release yet\|not built yet\|Next:" docs/ plans/ README.md CLAUDE.md

Re-judge every hit against what this release shipped. Most are fine (historical records, generic
instructions); the ones that are not are exactly the ones nothing else will ever flag.

**Verify by querying the index and installing what the docs show, not by reading them**
(`curl -s https://pypi.org/pypi/pinakes/json`). **Three separate caches will tell you a successful
upload failed.** Measured on 0.9.0 and again on 0.10.0, 20260804:

| Cache | Symptom | Beat it with |
|---|---|---|
| The JSON endpoint | Returns the previous release list; still said `0.8.0` an hour after 0.9.0 uploaded | A query string, then wait — it is the slowest to settle |
| `https://pypi.org/simple/` | Lists no file for the new version, **even with a cache-buster and `Cache-Control: no-cache`** | Nothing reliable. Do not read its silence as evidence |
| `uv`'s own index cache | `uvx --refresh` reports the version *unsatisfiable* | `uvx --no-cache --refresh`. **`--refresh` alone is not enough** |
| PyPI's index itself | Even `--no-cache` cannot resolve a version that uploaded seconds ago | **Wait and retry** — measured ~90 s on 0.11.0. Poll in a loop rather than concluding from one attempt |

So **the order that actually settles it**: read the workflow's `Publish to PyPI` step log — it
prints `Uploading pinakes-x.y.z-py3-none-any.whl` per file and cannot be cached — then confirm with
`uvx --no-cache --refresh --from "pinakes[light]==x.y.z" pnk --version`. Only a failed install
after **both** of those is a failed publish (20260729 — a correct 0.4.0 upload read as missing;
20260804 — 0.10.0 read as missing from `/simple/` while its two files were already on the index).

Caught 20260729: `STATUS.md` still said "Published version: 0.2.2 **only**" three hours after 0.3.0
was on PyPI, and the roadmap still listed the paid-extraction release as unbuilt.

## Afterwards

Fast-forward the primary checkout: `git pull --ff-only`.
