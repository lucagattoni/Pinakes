- **The GUIDE's install line works where a KB user actually stands.** `uv add "pinakes[light]"`
  needs a `pyproject.toml` and a knowledge-base directory has none, so the documented first command
  exited `No pyproject.toml found`. The guide now leads with the two forms that work in a bare
  directory — `uv init` first, or `uvx` with no install at all.
- **The GUIDE names the safe lock remedy before the destructive one.** A lock left by a dead process
  *on this host* is reclaimed automatically by re-running `pnk sync`, which continues incrementally
  and re-embeds nothing; `--force-unlock` is for a lock held by another host. Troubleshooting
  previously offered only `--force-unlock`. It also says to check the process rather than the age,
  since the lock's clock is UTC while an older KB's manifest is local.
