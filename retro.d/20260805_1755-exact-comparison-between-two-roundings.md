## An exact assertion between two *different* roundings — green locally, red on one CI leg (20260805 17:55)

**MEDIUM — a coin-flip assertion that passed for the wrong reason, and whose failure was earned by
an unrelated correct change.** `test_reports_cores_the_way_macos_percent_converts_to_them` read the
two numbers off the `peak:` line and asserted `cores == pytest.approx(percent / 100.0)` — at
`approx`'s *default relative* tolerance, i.e. effectively exact. But `report()` renders percent at
0 dp and cores at 1 dp: they are two roundings of one value, not one value printed twice. Exact
agreement is a coincidence of the input, never a property of the code.

It held only while a single-process sample sat at exactly `100.0`. The tree-sum fix
([the launcher retro](20260805_1737-measure-sync-cpu-watched-the-launcher.md)) made a one-core loop
read `101.4` — parent plus child — and `"101"/100 != 1.0` turned CI red.

**The tell is which legs failed.** `check (light pdf)` failed; `check (light)` and
`check (light pdf claude)` passed on the same commit, same code, same test. Three legs disagreeing
about one assertion is not a flaky *environment* — it is an assertion whose truth depends on a
measured value nobody controls.

**And it failed on merged `main`, not on the branch.** The branch's own `./check.sh` was green,
twice, because this machine's readings rounded agreeably. A local gate cannot rule out an assertion
that is only *usually* true.

**Fixed** with `abs=0.06` and the arithmetic written down: 0.5 of display error in the percent is
0.005 of a core, plus 0.05 from the cores field's own rounding, so 0.055 is the largest honest
disagreement between the two fields.

**The loosened bound still bites** — verified, not assumed. Dropping the `/100` from
`CpuTrace.cores` fails exactly this test (1.0 against 101). A tolerance that admits *formatting*
disagreement while still rejecting *arithmetic* disagreement is the assertion the test always meant
to make.

**Generalisable:** comparing two rendered numbers is comparing two roundings. Either compare the
values before formatting, or state a tolerance derived from the display precisions — never an exact
comparison "because they should be equal". This is the repo's recurring class once more: the
assertion named "the conversion is right" was actually testing "the two roundings happen to agree".
