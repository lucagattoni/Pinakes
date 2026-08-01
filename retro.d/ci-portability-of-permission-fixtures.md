## `main` was red for four merges, and local `check.sh` could not have known (20260801 06:05)

Four tests written across L6 and L7 passed on macOS and failed on CI, so `2314dea` (L6) and
`ed01b00` merged onto a red `main` and stayed there until L8's verification step 1 looked.

**Two causes, one shape: a test that cannot build its precondition does not skip — it asserts the
wrong thing.**

- **`chmod(0o000)` is not a portable way to deny a read.** Three fixtures built an "unreadable
  directory" that CI read anyway: `pnk link` reported `no pinakes.toml there` where the test
  demanded `Permission denied`, and `'docs/locked/x.md' is not a document in this KB` where it
  demanded `cannot be read`.

  **The first fix was wrong, and its wrongness is the lesson.** It probed whether permissions are
  enforced and skipped when they are not — reasoning that CI runs as root. CI is *not* root: the
  probe reported permissions enforced, did not skip, and the run failed identically. Whatever that
  runner does with a mode-000 directory, `is_file()` neither succeeded nor raised `EACCES`.

  Skipping was the wrong shape regardless. It disables the guard **exactly where it broke** — the
  environment the test could not model is the one that most needed testing. The refusal is now
  *injected*: `Path.is_file` raises `PermissionError`, which is precisely what the guard exists to
  catch, on every platform and with no filesystem semantics in the way. A test for "an `OSError`
  becomes a `PinakesError`" should raise an `OSError`, not arrange for the operating system to.
- **Two more of the same shape, found only by pushing the fix and watching CI again.** A
  300-character filename asserted to produce `ENAMETOOLONG` — the length at which a filesystem
  says that is a property of the filesystem, and on CI the name was simply not a document. And an
  embedded NUL in an `include` pattern asserted to raise from `resolve()` — on CI it raised
  nothing, so the test asserted a problem that never occurred. Both now raise the error directly.

  **Every one of these tests asked the operating system to produce an error, and then asserted on
  the answer.** That is a test of the platform, not of the guard. The guard's contract is "an
  `OSError`/`ValueError` from this call becomes a `PinakesError`" — so the test should raise one.

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
