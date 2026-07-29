## Shared-file contention tooling (20260729 04:06)

**HIGH — `git status --porcelain`'s leading space is significant, and a helper doing `.strip()` on
the whole output silently ate it.** The overlap gate's `git()` wrapper returned
`proc.stdout.strip()`, which is correct for `merge-base` and `symbolic-ref` and wrong for
`status --porcelain`: a modified file is reported as `` M CHANGELOG.md`` with the status in columns
0–1, so stripping the output removed the first line's leading space and the path parsed one
character short — `HANGELOG.md`. It matched nothing, and the gate reported **"no overlap" with total
confidence**. Exactly the one failure a contention gate cannot have.

Two things about how it was caught, both worth keeping:

- **The tests drive real `git` against real temp repositories, not a mocked `subprocess`.** The gate
  is almost entirely a set of claims *about git's behaviour* — what `diff A...B` means, which commit
  `merge-base` picks, how `status --porcelain` spells a rename — and a mock asserts the author's
  belief about each of those rather than the behaviour. A mocked test would have returned
  `" M CHANGELOG.md"` from a fake and passed with the bug present.
- **The mutation pass re-introduced this exact bug deliberately** and confirmed the right test
  fails. `git()` is now documented as trailing-newlines-only, with the reason, because the next
  person to "tidy" it back to `.strip()` will find nothing obviously wrong.

**MEDIUM — a clean auto-merge is not a correct merge, and only the loud half of that was being
managed.** Three parallel branches edited `CHANGELOG.md`, `docs/STATUS.md` and `docs/DESIGN.md`
inside one hour on 20260729. `CHANGELOG.md` conflicted and was resolved by hand; the other two
merged **silently**, because the edits landed on different lines. Git merges edits that do not
overlap textually, never edits that agree — so two agents can leave one document contradicting
itself with every command reporting success, and no conflict resolution however careful would
surface it.

The response is deliberately in two layers, because one does not cover the other's cases:

- `changelog.d/` and `retro.d/` **remove the cause** for the two documents every change must write
  to — separate files cannot conflict, so for those the class stops existing.
- `tools/shared_file_overlap.py` **reports what remains**, which is the living documents
  (`docs/STATUS.md`, `docs/DESIGN.md`) that fragments do not suit, because they are edited in place
  rather than appended to.

**LOW — the fragment tool takes `--repo` so its tests can drive the real artifact.** Importing a
`tools/` script from a test needs `sys.path` surgery that `pyright` and `ty` then cannot resolve —
`ty` failed the build on exactly that. Running it as a subprocess follows the precedent
`tests/test_paid_path.py` set for `tools/paid_path_gate.py`, and tests the same artifact `check.sh`
runs, argument parsing included.
