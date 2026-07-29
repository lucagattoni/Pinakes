- **Two agents can no longer quietly overwrite each other's shared-document edits.** Several agents
  work in this repo at once, and the collision has two shapes — only one of which anybody notices.
  `git merge` conflicting is the loud one. The quiet one is `git merge` **succeeding** because the
  two edits landed on different lines: git merges edits that do not overlap textually, never edits
  that agree, so two agents can state contradictory things in one file with every command reporting
  success. Both shapes were hit on 20260729, when three parallel branches edited `CHANGELOG.md`,
  `docs/STATUS.md` and `docs/DESIGN.md` inside one hour.

  Two complementary answers:

  - **`tools/fragments.py` removes the cause** for the two documents every change must write to. A
    change now adds `changelog.d/<category>-<slug>.md` or `retro.d/<slug>.md` instead of editing
    `CHANGELOG.md` or `docs/RETROSPECTIVES.md`, and the fragments are spliced in at release time by
    one actor with nothing else running. Two agents cannot conflict in separate files, so for these
    documents the conflict class stops existing rather than being managed. The category lives in the
    **filename**, where it cannot drift from the content. Existing `[Unreleased]` prose is left
    exactly where it is — adoption needs no migration commit, which would itself have collided.
  - **`tools/shared_file_overlap.py` reports what remains.** It names the files this branch touches
    that the default branch has touched too since they diverged, marking the high-contention ones.
    Generic, so it covers `docs/STATUS.md` and `docs/DESIGN.md`, which are living documents that
    fragments do not suit. Offline and advisory in `check.sh`; `--fetch --strict` is a gate before
    merging.

  Both are stdlib-only and import nothing from this project, so CI's `build` job runs them before
  the package builds.
