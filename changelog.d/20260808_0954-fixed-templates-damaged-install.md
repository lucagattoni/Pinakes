- **A damaged template no longer hides the healthy ones.** `pnk templates` lists what it can read
  and names what it cannot, on both the human and `--json` surfaces, exiting non-zero when anything
  is unreadable. Previously — and still, for `pnk init --template` — a template directory missing
  its `template.toml` escaped as a traceback; a listing that aborted on the first bad one would have
  reported nothing about the rest.
