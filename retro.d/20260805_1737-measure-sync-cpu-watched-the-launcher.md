## `measure_sync_cpu.py` measured the launcher, not the work (20260805 17:37)

**HIGH — the tool answered its one question with a number that was precisely, confidently wrong,
and every test passed.** `sample_percent` ran `ps -o %cpu= -p <pid>` against the pid it launched.
The invocation the tool was written for — and prints in its own `--help` and changelog fragment —
is `-- uv run pnk sync ...`, which makes `uv` the measured process and `pnk` its *child*. `uv` waits
and burns nothing.

Measured on this repo before the fix, one identical one-core busy loop:

| launched as | reported |
|---|---|
| the busy loop directly | **1.0 cores** |
| the same loop behind `uv run` | **0.0 cores** |

The failure mode is the expensive one: `0.0 cores` for a sync saturating a core does not read as a
broken tool. It reads as *the finding item 6 went looking for* — "the loop is not CPU-bound, so
multiprocessing buys nothing" — and it would have been quoted into a design decision.

**Why the tests could not catch it.** All seven ran `sys.executable -c <busy loop>`: a direct child
that does the work itself. The suite covered the sampler, the units, exit-code propagation, empty
and non-positive arguments, and the trailing-interval bug — everything except *the one process
shape the tool exists to be pointed at*. Coverage of the code was complete; coverage of the
**invocation** was zero. This is the recurring class named in `docs/RETROSPECTIVES.md` — an
assertion satisfied by something other than the property it names — reached from a new direction:
not a weak assertion, but a fixture that was never the real subject.

**Fixed** by summing `%cpu` across the root pid and every descendant from a single `ps -A` snapshot
(one snapshot, so a child starting or exiting mid-walk cannot be double-counted or missed), plus a
test whose command is a launcher that burns nothing itself.

**The new test's upper bound is load-bearing, and mutation proved it.** With the tree walk
neutered, the launcher still reported **0.1 cores** of its own interpreter startup — so
`assert peak > 0` would have passed the mutant. Asserting `> 0.5` fails it. A threshold above
"anything a waiting process can produce" and below one core is what makes the assertion name the
property; "non-zero" would not have.

**Also corrected: `%cpu` is a decaying average over up to a minute** (`man ps`), not the
instantaneous reading the docstring claimed. Right for the steady-state multi-minute loop this
measures, but it means `peak` is the peak of a *smoothed* series — a low peak is much weaker
evidence of an idle machine than a high peak is of a busy one, and the docstring now says so.

**Generalisable:** when a tool's purpose is to be run one particular way, one test must run it
*that* way. A synthetic fixture chosen for speed silently replaced the subject here, and no amount
of assertion strength on the wrong subject would have helped.
