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

**HIGH — the gate reproduced, inside itself, the exact defect it was built to catch.** Given
`--templates` as a *relative* path, leg (vii) built its `git log` pathspec against the process
working directory while git resolved it against the templates directory. It matched nothing, `git
log` returned empty, zero commits read as "not committed yet", and the gate printed
`history leg (vii) ran … none edited` **and `all legs green`** over a tree carrying the coordinated
three-file edit. That is the strong mode claimed while nothing was checked — the thing this
increment exists to stop `pnk doctor` doing. Every leg-(vii) test passed `--repo` explicitly, so
nothing covered it. **A flag that changes where a tool looks needs a test that runs it from
somewhere else**; resolving paths once at the argument boundary is the fix, and the general rule is
that a relative path and a `cwd` argument must never be chosen independently.

**HIGH — leg (vii)'s first design blocked the project's own procedure, and no single mechanism
fixes it.** Counting every commit that touched an archived directory fails a branch that adds one
and then corrects it during review — which is exactly what `docs/BUILDING.md` requires (green
`./check.sh` *before* review, review fixes in *their own commit*). The failure text said the archive
*"still says what the version said when it shipped"* about a version that had never shipped, and the
only escape — amend or rebase — is the operation that also defeats the leg. Two candidate fixes each
looked sufficient and each was blind: counting only commits already on `origin/main` stops catching
the coordinated edit *before* it merges; comparing content against `origin/main` stops catching an
edit that has *already* merged. **The leg needs both halves, and the way to see that was a table of
three scenarios against two candidate rules**, not a closer reading of either candidate.

**MEDIUM — a test asserting on a configuration was satisfied by the prose describing it.** The test
pinning `fetch-depth: 0` onto the gate's CI job grepped the workflow file for the string. The job's
own comment explains *why* the setting is there and contains it, so deleting the setting left the
test green. Caught only by mutating it. **Grep a config file and you assert about a document; parse
it and you assert about the configuration** — the test now loads the YAML and reads
`jobs.template-drift.steps[checkout].with.fetch-depth`.

**MEDIUM — nothing pinned that the gate was wired in at all.** Deleting the `check.sh` line and the
entire CI job left all forty-odd tests in `tests/test_template_drift.py` green, because every one of
them drives the tool directly. A test suite for a gate proves the gate *works*; it says nothing
about whether anything *runs* it, and those are different claims. Two assertions now cover the
second one.

**MEDIUM — the hash covered bytes that do not ship, and could bake them into the ledger.** It walked
the working tree, so a gitignored `.DS_Store` in the template directory turned `./check.sh` red on a
clean checkout with the remedy *"bump the version and archive the new files"*. The worse direction:
present while `--print-hash` generated a ledger row, it was folded into the committed sha — leaving
the author green and failing only on a clean CI checkout, pointing at an archive nobody had touched.
The fix is *ignored*, not *untracked*, and the distinction is load-bearing: measured against a real
hatchling build, a gitignored file does **not** reach the wheel while an untracked-but-un-ignored
`.orig` **does**. Hashing git's tracked set would have hashed away a stray file that really
publishes, and given a brand-new archive the digest of the empty string.

**Process note — two independent skeptics disagreed, and the disagreement was the useful output.**
One confirmed the stray-file finding; another refuted it, having implemented and measured a
*tracked-set* fix and shown it strictly worse. Both were right about what they tested, and neither
had tested the rule that was actually adopted. **A refutation kills a proposed fix, not necessarily
the finding** — the two have to be judged separately, and the second reviewer's evidence is what
made the third option obviously correct.
