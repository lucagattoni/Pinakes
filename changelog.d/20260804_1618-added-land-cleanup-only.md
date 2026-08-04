- **`tools/land.py --cleanup-only` removes a branch that landed earlier.** The normal flow is to
  land, watch CI, then clean up — but by then re-running `--cleanup` correctly refuses, because the
  default branch cannot move a second time, so the only way to finish was by hand. That is the class
  of mistake the script exists to remove. It verifies the branch is an ancestor of `origin/main`
  before destroying anything: *"looks merged"* is not *"landed"*.
