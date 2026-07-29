- **A docs change now audits its neighbourhood, not its diff.** Before landing any documentation
  edit, the surrounding claims are re-read against four questions: is this **consistent** with the
  other docs, does its **logic** still hold, has it been **superseded** by a decision taken since,
  and is it **outdated** against the code, the package index or the clock.

  The rule exists because whatever made the line you came to fix go stale almost certainly reached
  its neighbours too, and reading the diff cannot show that. Measured on 20260729: a one-line PyPI
  correction was requested, and sweeping around it found five more stale claims — a shipped release
  still listed as unbuilt in two separate tables, an install block missing the headline capability
  of the last two releases, a README sentence implying a feature that is not built, a runbook still
  described as producing numbers the project "admits it lacks" after the run had happened, and a
  design note reading "no increment assigned" for work a plan had since assigned. Every one was a
  single-line edit; none was visible from the change that prompted the sweep.

  Full rule in [`docs/README.md` § Conventions](docs/README.md#conventions), with a one-line pointer
  from `CLAUDE.md`'s Docs section.
