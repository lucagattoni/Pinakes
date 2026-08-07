## T1 — The version archive, and what mutation testing found in it (20260807 19:36)

**HIGH — the plan's own baseline undercounted the sites it had just corrected, and the second
count was as wrong as the first.** The template-release plan was re-verified against `main` at
`71911e2` on 20260807, and that re-run *specifically* corrected the `notes@1.0` site list: it had
said "both, in `test_init.py`", and the correction raised it to "six sites in five files", with a
box explaining that the original defect was a `grep` scoped to one file. Running the corrected
command at that same commit returns **nine sites in eight files**. The three it still missed were
`tests/test_sync_links.py:66` and the two committed KB manifests, `tests/demo-kb/pinakes.toml` and
`tests/partner-kb/pinakes.toml`. The lesson is not "grep wider" — the plan already said that. It is
that **a count in a document is a measurement, and re-running the command is the only thing that
distinguishes a corrected count from a confidently wrong one.** The correction was written and
believed; nobody re-ran it.

**HIGH — a formatter can edit a file the project has promised is frozen.** The archive's whole
value is byte-identity: `_versions.toml` records a SHA-256, and `pnk upgrade` will diff against
those exact bytes. `check.sh` runs `ruff format --check .` over the whole repository, and ruff
reformats Python inside Markdown fences. A template `README.md` that ever gains a `python` fence
would be rewritten *in its archived copies too* — the project's own formatter editing a version
that already shipped — and it would surface as a ledger mismatch one leg away from its cause.
Latent today (no template README has a fence) and closed with a `[tool.ruff] extend-exclude`.
**Generalisable: whenever a repository declares some bytes immutable, list every tool with write
access to them.** The gates were audited; the formatter was not, because it is not a gate.

**MEDIUM — mutation testing found a branch no input could distinguish, which is the same defect
class as a gate that cannot fire.** `git_history_reason` probed `--is-inside-work-tree` and then
`--is-shallow-repository`. Neutering the first changed no test result: outside a checkout the
second exits 128 anyway, so the first was dead weight wearing the clothes of defensive care. It
was removed. This increment exists because `pnk doctor` carried a check that could never fire for
eleven releases; shipping a redundant branch inside its fix would have been the same mistake at
one-tenth the scale. **A branch that no test can tell apart from its absence is a branch nobody
knows works.**

**MEDIUM — the first mutation run was invalid, and its invalidity was informative.** Three mutants
changed `content_hash` and turned the *whole suite* red rather than one test, because the committed
ledger pins the hash function: change it and leg (iii) fires everywhere. That coupling is a feature
— the hash definition cannot drift silently — but it destroys the per-assertion signal, so the
harness was corrected to regenerate the ledger under each hash mutant, which is the tree such an
implementation would really have shipped with. Separately, two tests both tampered with
`README.md`, so a mutant exempting the README failed all three. **A mutant that travels to another
test means the two tests share a vector, not that either is wrong** — but the sharing is worth
removing, because it makes every future mutation result harder to read.

**MEDIUM — leg ordering decided which remedy the user is given, and the wrong order gives the
opposite one.** Editing a frozen `_versions/<live>/` file also makes the live files differ from
it. With the live-vs-archive comparison first, the gate reported *"the live files differ from
archived 1.1"* and advised bumping the version — when what happened was that a published version
was edited and needs restoring. The ledger check now runs first, so each fault reports its own leg.
Found by running the failure paths, not by reading the code: both orderings look correct on the
page and only one is.

**LOW — "exactly one commit" was unsatisfiable in the increment that introduces it.** Leg (vii) as
specified fails on its own landing commit, because `./check.sh` runs *before* the archive is
committed and `git log` returns zero. It is *at most* one: zero means not yet committed, one means
added and never touched, two or more is the violation.
