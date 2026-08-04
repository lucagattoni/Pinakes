- **`tools/land.py` — landing a branch is one command that verifies it landed.** Running
  `git merge <branch>` from inside that branch's own worktree merges it into itself: git reports
  *"Already up to date"*, the push reports *"Everything up-to-date"*, and a tag created there points
  off-`main` — three successful commands and nothing landed. Git cannot catch it, because a branch
  merged into itself creates no commit and `pre-merge-commit` never fires. `land.py` finds the
  primary checkout itself whatever directory it was invoked from, **refuses if `main`'s sha did not
  move**, and re-reads `origin/main` after pushing because a push reporting success is only a claim.
  `--cleanup` removes the worktree *and* both copies of the branch, since deleting one leaves the
  other behind. Contributor tooling; nothing in the package changes.
