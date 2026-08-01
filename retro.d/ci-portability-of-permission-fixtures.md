## `main` was red for two merges, and local `check.sh` could not have known (20260801 05:25)

Four tests written across L6 and L7 passed on macOS and failed on CI, so `2314dea` (L6) and
`ed01b00` merged onto a red `main` and stayed there until L8's verification step 1 looked.

**Two causes, one shape: a test that cannot build its precondition does not skip — it asserts the
wrong thing.**

- **`chmod(0o000)` denies nothing to root**, and CI's container runs as root. Three fixtures built
  an "unreadable directory" that was, there, an ordinary empty one: `pnk link` then reported
  `no pinakes.toml there` where the test demanded `Permission denied`, and
  `'docs/locked/x.md' is not a document in this KB` where it demanded `cannot be read`. Guarded now
  by `conftest.permissions_are_enforced`, which **probes** — writes a file, chmods the directory,
  tries to read it back — rather than inferring from `os.geteuid()`, because capabilities, ACLs and
  mount options all decide this and the only question that matters is whether the read is refused
  *here*.
- **`pathlib`'s wording is not a contract.** A test asserted
  `Unacceptable pattern: PosixPath('.')`, which CPython renders as `Unacceptable pattern: ''` on
  other versions. The increment's promise is that the pattern *the author wrote* is named and the
  other `include` entries survive; that is what it asserts now. Third instance in two increments of
  asserting a phrase where the property was meant.

**The process failure is the larger one.** `./check.sh` was green before each merge, and green on
one developer machine is not green on the three-leg CI matrix — different OS, different Python
patch, different privileges. The project rule already says to check whether the latest run on the
default branch actually succeeded; it was not checked after either merge, and the second merge
landed on top of the first failure without noticing it.

**`gh run list --branch main` belongs in the merge sequence, after the push**, not in the next
increment's verification step. A red default branch blocks the release either way — finding it two
merges later only makes the bisect longer.
