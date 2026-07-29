- **`docs/VERIFICATION.md`** — every promise this project makes, and the test that holds it, with
  `tests/test_verification.py` asserting each named test exists. It replaces `plans/v0.2.md`'s
  verification table as the *lookup*: that table wrote its test paths before the tests existed, and
  implementation renamed most of them, so **61 of its 98 references did not resolve**. The
  properties were almost all tested — under better names — but a table whose paths cannot be
  resolved verifies nothing, which is the failure its own preamble warns about. The plan keeps its
  predictions as the record of what was intended.
- **`pnk doctor` now proves its own checks are tested** —
  `tests/test_doctor.py::test_every_doctor_check_is_exercised_by_a_test`. Adding a check is one
  line, and nothing about that line requires a test to exist.
- **`pnk sync --help` is asserted to state each dangerous flag's *limit*, not only its capability**
  — `--force` widens no cap, `--yes` raises none, `--clear-cache` never touches the ledger,
  `--estimate-only` generates nothing.
- **CI's wheel smoke asserts the two files the spending guards read** (`prices.toml`, `floors.toml`)
  are present in the built wheel, and that a core-only install names the extra it needs rather than
  producing a traceback.
