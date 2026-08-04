# The template release — implementation plan

**Audience: the coder. Goal: executor.** Every increment below names exact files, symbols and
predicates. Rationale that belongs in `docs/DESIGN.md` is marked as a DESIGN amendment rather than
argued here; what is argued here is only what an executor needs in order not to build the wrong
thing.

**Written 20260803 22:53 against `main` at `aae76fc`; revised 20260804 after an adversarial review,
re-verified against `main` at `d001175` and then at `55a87ae`; four decisions folded in 20260804
08:51, verified against `main` at `68084d3` and re-checked at `d06ef7e`.** `main` moved twice more
during that session alone — **re-run the Baseline block before trusting any `file:line` below.**
`55a87ae` renamed every file under
`plans/` to a `YYYYMMDD_HHMM-` prefix; the paths below are the post-rename ones, and **`ls plans/`
is the first thing to re-run** if `main` has moved again. Every claim about current behaviour below was read out of the source
or measured with a command, and the command is given so it can be re-run. Do not trust a line of it
once `main` has moved — re-run the *Baseline* section first.

**The revision's own lesson, kept because it recurs.** The draft written against `aae76fc` asserted
*"zero keys added, zero values changed"* over the template's whole history. Two commits later
(`97309d8`, `e3685e1`) that was false, and it was the sentence three increments were built on. A
measurement in a plan is a measurement **as of a commit**, never a property — M1–M6 below carry the
commit they were run at for that reason.

**Four decisions were taken by the user on 20260804 and are folded in below — D-2b (option D),
D-10 (option B), D-11 (option A), D-12 (option A).** Their entries in *Decisions* are marked
**TAKEN**, the rejected options are kept with their cons so nobody re-opens them, and every
increment, exit criterion and table that assumed a different answer has been rewritten. **T1–T4 are
no longer blocked.** What is still open is listed in *Still open — for the planner* below the
decisions.

**Scope.** The template release as `docs/STATUS.md`'s roadmap and `CLAUDE.md`'s unbuilt-work table
define it: *template ecosystem, `pnk upgrade`, the `sqlite-vec` tier*. It does **not** cover
`pnk ask --deep` (the deep release), and it does not cover the graph release's remainder
(see `20260804_1016-graph-remainder-reentry.md` beside this file).

---

## Baseline — re-verify before starting anything

```bash
git fetch && git log --oneline -1 && git status --short --branch
gh run list --branch main --limit 1
python3 tools/shared_file_overlap.py --fetch --strict
ls plans/          # every file here carries a YYYYMMDD_HHMM- prefix since 55a87ae; re-resolve any
                   # `plans/…` path this document cites before quoting it
```

Then re-run every measurement this plan rests on. They are commands, not assertions:

| # | Run this | What it said **at `d001175`, 20260804** |
|---|---|---|
| M1 | `git log --oneline --follow -- src/pinakes/templates/notes/template.toml` | one commit, `873d2e2` (20260725) — `version = "1.0"` has never changed |
| M2 | `git log --oneline --follow -- src/pinakes/templates/notes/pinakes.toml.j2` | **six** commits: `873d2e2`, `01c60db`, `232e14e`, `49ede26`, `97309d8`, `e3685e1` |
| M3 | `git diff 873d2e2 HEAD -- src/pinakes/templates/notes/pinakes.toml.j2` | two hunks. `[sources]`: **+4 comment lines**, nothing removed. `[budget]`: **−3/+4**, comments rewritten **and two defaults changed** — `per_operation_eur 0.05 → 0.30` (`97309d8`) and `monthly_eur 5.00 → 30.00` (`e3685e1`). **No key was added or removed; two values changed.** |
| M4 | `git log --oneline --follow -- src/pinakes/templates/notes/eval/questions.yaml` | two commits: `873d2e2`, `9595370` (G2) |
| M5 | `grep -n '"\*\*/\*.pdf"' src/pinakes/templates/notes/pinakes.toml.j2` | **one match, `pinakes.toml.j2:11` — inside a comment.** The glob is *not* in `include`; the comment block at `pinakes.toml.j2:11-14` explains why it is left out |
| M6 | `grep -n 'vector_tier' src/pinakes/sync.py src/pinakes/search.py` | `sync.py:971` writes the literal `"numpy"` into `meta`; `search.py` never reads `vector_tier` at all |
| M7 | `grep -n '"--kb"' src/pinakes/cli.py` | one hit, `cli.py:74`, inside `_kb_argument` (`cli.py:72-79`, `metavar="PATH"`). The shared KB flag is **`--kb`**; **there is no `--path` flag on any command** — `pnk doctor --path X` dies at argparse with `unrecognized arguments`. `metavar="PATH"` is the trap: `--help` shows `--kb PATH`, which reads as a flag called `--path` at a glance. Run this before writing any snippet in this plan |

**M3's exact text, so a later reader does not have to re-derive it.** This is the entire drift
history of the only shipped template, and three increments below rest on it:

```diff
@@ [sources] @@
 exclude = ["**/drafts/**"]
+# Add "**/*.pdf" to `include` above to index PDFs. Left out rather than commented into place
+# because `init` cannot see whether the extractor is installed: PDF ingest needs
+# `uv add "pinakes[pdf]"`, and a glob stamped without it turns every PDF into a failed document.
+# `pnk sync` names any file it skipped for want of a pattern; `pnk doctor` checks the extractor.
@@ [budget] @@
-confirm_above_eur = 0.01          # nothing spends money before v0.4; validated so a KB written
-per_operation_eur = 0.05          # today keeps working when `pnk ask --deep` arrives
-monthly_eur       = 5.00
+confirm_above_eur = 0.01          # caps on the one thing that can spend: the paid PDF extractor.
+per_operation_eur = 0.30          # The free backend is the default, so these bind only once you
+                                  # ask for it (`--extract=claude-vision`, docs/DESIGN.md §5).
+monthly_eur       = 30.00
```

**Never write a literal line count into a test or an exit criterion.** An earlier draft of this plan
asserted "the six comment lines of M3" in three places; two commits made it wrong on the count, on
the composition, and on the claim that they were comments. Assert on *content* — a named comment
line, a named key's value — never on how many lines a diff has.

## What is true on `main` today — with citations

**Read these before writing code. Never describe current behaviour from a document.**

| Fact | Where |
|---|---|
| A template is `name`, `version`, `description` in `template.toml`, plus `pinakes.toml.j2`, `README.md`, `eval/questions.yaml` | `src/pinakes/template.py:24-64`, `src/pinakes/templates/notes/` |
| `copy_extras` copies a **hardcoded** two-entry list — `README.md`, `eval/questions.yaml` | `src/pinakes/template.py:73-88` |
| `available()` skips any **top-level** entry of `pinakes.templates` whose name starts with `_`. It never descends into a template directory, so nothing under `templates/notes/` is a candidate either way | `src/pinakes/template.py:49-54` |
| **`_root()` does no name validation at all**, so a template name may contain path separators and `..`. Measured at `d001175`: `template.describe("notes/../notes")` and `template.describe("../templates/notes")` both **succeed**, and `template.describe("notes/eval")` raises a bare `FileNotFoundError` rather than a `PinakesError`. This is live today and T1's archive makes it reachable — see T1's containment rule | `src/pinakes/template.py:36-46` |
| The KB records only the *reference* `notes@1.0`, never the content | `src/pinakes/template.py:30-33`, `src/pinakes/init.py:57-70` |
| `pnk doctor` compares the recorded version string against the installed one and warns on mismatch | `src/pinakes/doctor.py:163-184` |
| The manifest is read-only to Pinakes after `init`, stated as a property | `src/pinakes/manifest.py:3-5` |
| Unknown manifest keys are a hard error; an empty string is an error too | `src/pinakes/_toml.py`, `docs/DESIGN.md:124-127` |
| `[kb] requires_pinakes` is read in a pre-pass before strict validation. It shipped in **0.6.0**, so a manifest carrying the key is unreadable by any earlier build | `src/pinakes/manifest.py:207-210,237-331`, `docs/STATUS.md:258` |
| `[retrieval] adjacent_k` is settable but deliberately **not stamped** into the template, because an older Pinakes cannot read it | `src/pinakes/manifest.py:644-651` |
| `vector_tier` accepts `auto` / `numpy` / `sqlite-vec`, and `docs/MANIFEST.md:135` documents all three as settable | `src/pinakes/manifest.py:48,643`, `docs/MANIFEST.md:135` |
| Index `SCHEMA_VERSION` is `2`; a mismatch refuses to open and names `pnk sync --rebuild`; **there are no migrations, by design** | `src/pinakes/store.py:4,28,197-206` |
| **Two** tests hardcode `notes@1.0`: `tests/test_init.py:20` asserts `manifest.kb.template`, `tests/test_init.py:99` asserts `TemplateInfo.reference`. Both move together or the branch lands red | `tests/test_init.py:20,99` |
| Core dependencies today: `jinja2`, `mcp`, `numpy`, `python-ulid`, `ruamel.yaml` (`pyproject.toml:21-27`). Extras: `st`, `light`, `pdf`, `claude` (`pyproject.toml:29-33`) | `pyproject.toml:21-27,29-33` |
| `pnk doctor` **exits 1 on a default `uv sync` of this repo**, because `[st]` is not installed and the template stamps `sentence-transformers` (`init.py:25-26`). Measured at `d001175` on a fresh `pnk init` KB: two `FAIL` lines, exit `1`. **No exit criterion in this plan may assert on `pnk doctor`'s exit code** — assert on the specific line | measured; `.github/workflows/ci.yml:99-102` runs it under the `[light]` matrix leg |

---

## Five findings that change the shape of this release

These are the reason this plan is not `docs/KB-UPDATES.md` §9 turned into increments.

### F1 — The shipped drift check has never been able to fire

`doctor._template` (`doctor.py:163-184`) warns when a KB's recorded template version differs from the
installed one. `notes`' version has been `"1.0"` since `873d2e2` while its content changed in **six**
later commits — five to `pinakes.toml.j2` and one to `eval/questions.yaml` (M1, M2, M4). Every KB
ever created records `notes@1.0`, every installed template *is*
`notes@1.0`, and the check has returned `Status.OK` on every KB in existence for every version of
Pinakes. `docs/KB-UPDATES.md` §3 case 3 predicted this before it shipped ("a rule with no gate; it
already lapsed before shipping") and nothing has closed it since.

### F2 — No template drift has ever added or removed a key; the drift that matters is a comment

M3 is the whole drift history of the only shipped template. It has exactly two components:

1. **Four comment lines added under `[sources]`** — the PDF-glob explanation. No key, no value.
2. **Two default values changed under `[budget]`**, with their comments rewritten:
   `per_operation_eur 0.05 → 0.30` (`97309d8`), `monthly_eur 5.00 → 30.00` (`e3685e1`).

**The key set has never changed.** So `docs/KB-UPDATES.md` §9's step 3 —
*"`doctor` reports manifest keys the installed template sets that this KB lacks"* — reports
**nothing** when run against the entire history of `notes`, and always would have. §9 claims that
step "Closes the PDF-glob gap"; it does not, and could not: the PDF-glob gap is component 1, which
is a comment, and a key-set difference cannot see a comment. That claim must be withdrawn from §9
rather than cited.

§5's *"write the additive changes into `pinakes.toml`"* is a value-level instrument, so it *would*
fire — on component 2 only. Which is the second finding here.

**Component 2 is a money change, and it is the one hunk class where a wrong write costs real
money.** Applying the `[budget]` hunk to an existing KB raises that KB's per-operation cap sixfold
and its monthly cap sixfold. **D-10 (taken 20260804) applies it like any other hunk**, so the thing
that keeps the user the decider is not a special case in the applier — it is the **consent path**:
`pnk upgrade` prints the whole diff and writes nothing, and `--apply` is a separate, explicit act
taken after that. That path is therefore load-bearing rather than cosmetic, and T4 specifies it as a
build requirement with its own exit criteria: **a `[budget]` change must be unmissable in the
printed diff, and the print must provably precede the first byte written.**

**The live case, so nobody has to derive it.** Today the template's `[budget]` differs from *every*
existing KB by exactly two values — `per_operation_eur` `0.05 → 0.30` and `monthly_eur`
`5.00 → 30.00`, both shipped in **0.8.0** — and both are pure value replacements that apply cleanly
to any unedited manifest. This is not a hypothetical hunk class; it is the only value-level drift
the template has.

The surviving structural conclusion, and the one every increment below rests on: **the unit of
template drift is the rendered manifest's text, not its key set.** A key-set instrument sees 0% of
the history. A value-level instrument sees only the half the user must be shown before it lands,
and misses the half that is the live gap.

### F3 — `docs/KB-UPDATES.md` §3 case 1 describes something that never happened

It says *"I9 adds `**/*.pdf` to the template, which only affects `pnk init`, so every KB created
before I9 stays PDF-blind permanently."* I9 did not do that, and the current template deliberately
omits the glob, explaining why in the comment block at `pinakes.toml.j2:11-14` (M5).
`docs/STATUS.md:69-74` records the reversed decision. So the live gap is real but its content is a
**comment**, which is the one thing a key-level mechanism cannot see. This is the same finding as F2
arriving from the other direction, and it is why §3 case 1 must be rewritten rather than cited.

Other stale references in that document, to fix in the same pass: `doctor.py:135` is now
`doctor.py:163`; `sidecar.py:35,106` predates L5b's move to `ruamel.yaml`, so the "preserved verbatim
under `extra`" claim in §4's table needs re-verification against `src/pinakes/sidecar.py` as it is
now; `_toml.py:184` and `store.py:205` were still correct on 20260803.

### F4 — `pnk upgrade` cannot do what its name says, because the old template is not shipped

`docs/DESIGN.md:625-627`, `docs/CLI.md:406` and `docs/KB-UPDATES.md` §5 all describe `pnk upgrade` as
diffing *"the KB's recorded template version against the installed one."* The wheel ships exactly one
copy of each template — the current one (`pyproject.toml:65`, `template.py:36-46`). At runtime,
`notes@1.0`'s content does not exist. The recorded reference is a string.

What is implementable without new machinery is a different operation: diff the KB's **current
manifest** against a **freshly rendered current template**. That operation cannot distinguish *"the
template changed"* from *"the user changed it"*, and reporting the second as the first is the failure
this project refuses everywhere else. **Decision D-2** resolves it.

### F5 — `vector_tier = "sqlite-vec"` is accepted today and silently does nothing

`manifest.py:643` validates it against `VECTOR_TIERS`; `sync.py:971` then writes the literal
`"numpy"` into `meta` regardless; `search.py` never reads the field (M6). A user who sets
`sqlite-vec` gets the NumPy tier, an index whose `meta` says `numpy`, and no message.
`docs/MANIFEST.md:135` documents that only the NumPy tier is built, so this is disclosed rather than
hidden — but a manifest whose validator accepts a value that changes nothing sits badly beside
`docs/DESIGN.md:124-127`, where an unknown key is a hard error and an empty string is an error rather
than a request for the default. **Decision D-4.**

---

## The tension `CLAUDE.md` and `docs/CLI.md` appear to have — resolved

Two sentences look like they contradict. They do not, and one of them is about something else
entirely.

**`CLAUDE.md`:** *"Index schema changes bump `schema_version` and require a rebuild. Never write a
migration."*
**`docs/CLI.md:406`:** *"`pnk upgrade` … diffs a KB's template version against the installed one and
**prints** a migration — never applies one."*

| | `CLAUDE.md`'s invariant | `pnk upgrade` |
|---|---|---|
| Subject | `.pinakes/index.db` | `pinakes.toml` |
| Ownership | derived state, disposable | committed, hand-edited, the user's |
| Remedy on drift | `pnk sync --rebuild` — free, lossless, deterministic | none exists; that is the whole problem (`docs/KB-UPDATES.md` §1–§2, axis 4) |
| Why no migration code | it would be pure liability against a free rebuild | not applicable — there is nothing to rebuild from |
| Enforced by | `store.py:197-206` | nothing yet |

**They are different subjects and neither constrains the other.** `pnk upgrade` may never touch
`.pinakes/`, and this plan's increments do not; the index invariant is untouched by all of it.
Conversely, `pnk upgrade` writing to `pinakes.toml` is not "a migration" in `CLAUDE.md`'s sense.

**The real contradiction is internal to the docs, and it is `docs/CLI.md` against the other two:**

* `docs/CLI.md:406` — "**never applies one**" (absolute).
* `docs/DESIGN.md:625-627` — "It never applies changes **automatically**" (permits an explicit opt-in).
* `docs/KB-UPDATES.md` §5 — "**with `--apply`**, write the additive changes into `pinakes.toml`".

Two of three permit an opt-in write; `docs/CLI.md`'s one-line planned-surface row is the outlier.
**Decision D-1** puts the choice to the user rather than resolving it here.

**Independent of D-1, one thing should change: stop calling it a migration.** The word names two
different operations in the same repository — index-schema migration (forbidden) and manifest/template
drift adoption (proposed) — and every reader who has to be told they are different has already paid
the cost. Call `pnk upgrade`'s output a **template diff** and its write a **proposed manifest
change**. That removes the collision at source instead of explaining it away, and it costs one line
in `docs/CLI.md` and one in `docs/DESIGN.md` §6.1.

---

## Decisions

**Four were taken by the user on 20260804; they blocked T1–T4 and no longer do.** The rest are
recommendations the planner may still overrule. ✅ marks a taken decision, ⭐ a recommendation.

| | Decision | Status |
|---|---|---|
| **D-2b** | What content does `notes@1.0` denote, and what seeds the archive? | ✅ **TAKEN 20260804 — D.** Do not archive `1.0`; bump, archive the bump, route `1.0` to *cannot compare*; build the *already applied* third outcome unconditionally |
| **D-10** | What does `--apply` do with a `[budget]` hunk? | ✅ **TAKEN 20260804 — B.** It applies like any other hunk. The consent path (printed diff, separate `--apply`) is what makes it defensible, and T4 must build and prove it |
| **D-11** | Does `--apply` write `[kb] requires_pinakes`? | ✅ **TAKEN 20260804 — A.** It prints a recommendation and writes nothing |
| **D-12** | What release type is T5? | ✅ **TAKEN 20260804 — A.** PATCH, with the break stated plainly, on this project's own 0.7.1 precedent |
| D-1 | Does `pnk upgrade` ever write? | **Settled as B by implication** of D-10 and D-11 (both are rules for `--apply`, which exists only under B). Recorded rather than assumed — see the entry |
| D-2 | How does it know the old template? | **Settled as A by implication** of D-2b — "archive the bump" *is* A's machinery. See the entry |
| D-3 | What does a template version denote? | ⭐ A — open |
| D-4 | What happens to `sqlite-vec` now? | ⭐ A — open. **D-12 fixes the release *type* of whichever increment refuses the value, not whether A or D is taken** |
| D-5 | Where does the pre-`--apply` manifest go? | ⭐ A + C — open |
| D-6 | Does `init` stamp `requires_pinakes`? | ⭐ A — open (it is today's behaviour) |
| D-7 | A second template this release? | ⭐ A — open |
| D-8 | Is `pnk adopt` in this release? | not scheduled; two documents disagree — open |
| D-9 | One cut or more? | ⭐ more than one — open |

### D-1 — Does `pnk upgrade` ever write to `pinakes.toml`?

| Option | Pros | Cons |
|---|---|---|
| **A. Print only, forever** (`docs/CLI.md`'s reading) | The manifest stays a file Pinakes only reads (`manifest.py:3-5`) — an invariant with no exceptions is cheaper to hold than one with three. No backup semantics, no partial-write recovery, no "it edited my config" class of bug. Smallest increment. **The user decides every `[budget]` change themselves, which F2 shows is half the actual drift.** | Does not close the live gap: adopting a change stays a manual edit against a printed diff. `docs/KB-UPDATES.md` §9's own cost/benefit puts "existing KBs actually adopt new defaults" only behind `--apply`. (An earlier draft asserted here that "nobody will do it"; that had no evidence behind it and is withdrawn.) |
| **B. `--apply` writes non-conflicting hunks, opt-in, after printing** ⭐ **— settled as the operative answer by implication of D-10 and D-11 (20260804)** | Closes the gap. Matches `docs/DESIGN.md` §6.1 and `docs/KB-UPDATES.md` §5. The precedent exists and is named in §5: `pnk doctor --prune` prints every path then acts only on request. Conflicts are refused rather than merged, so the tool never guesses. | **The whole drift history it would apply is four comment lines and two raised spending caps** (M3). For that, B buys: a new exception to `manifest.py:3-5`'s stated property, backup semantics (D-5), a re-parse-or-restore path, tests for every partial-failure mode, an amendment to `docs/DESIGN.md` §2.1, and a proposed `CLAUDE.md` amendment. **D-10 removed one item from this list and added a larger one**: there is no `[budget]` rule to write, but there *is* a consent path to build and prove — a labelled money heading in both outputs, its absence when no money moves, and print-before-write ordering asserted by position. That is the honest trade, and it is on this side of the table. |
| **C. `--apply` writes everything, resolving conflicts** | Fully automatic. | Rejected on sight: it overwrites a user's deliberate edit with a template default and cannot tell the two apart. Named only so it is visibly excluded. |

**Recommendation: B**, with T3 (print) and T4 (`--apply`) as separate increments so A remains the
outcome if T4 is never built. The plan is written so that stopping after T3 leaves a coherent
release.

**Settled as B by implication, 20260804, and recorded rather than assumed.** The user took **D-10**
and **D-11**, both of which are rules for what `--apply` does when it writes. Neither has a subject
under option A, where `--apply` does not exist. So B is the operative answer and T4 is in scope.
**If the planner disagrees and stops at T3, D-10 and D-11 become moot rather than wrong** — nothing
in T1–T3 depends on either. What B costs is unchanged and still stated in its cons column above;
D-10's answer removes one item from that list (a special rule for `[budget]` hunks) and adds
another (the consent path T4 must build and prove).

### D-2 — How does `pnk upgrade` know what the old template looked like? (F4)

| Option | Pros | Cons |
|---|---|---|
| **A. Ship a version archive in the wheel** — `templates/notes/_versions/<version>/…`, one frozen copy per released template version ⭐ **— settled as the operative answer by implication of D-2b (20260804)** | The only option under which the diff means what its name says: base = the recorded version, ours = the installed version, **theirs = the KB's manifest**, so a three-way comparison separates *template changed* from *user changed* exactly. Makes the drift gate (T1) trivial and git-free. Cheap: a template is ~4 files / ~4 KB. Works for every KB whose recorded version this build archives. | Wheel grows by one template-sized directory per released version, forever. An archive is a promise: an archived version may never be edited, and that is enforced by review plus a hash ledger, not by the filesystem. **Helps no KB whose recorded version predates the archive** — which today is every KB in existence (D-2b). `_versions` needs a containment rule of its own: it is *not* excluded by `available()`'s underscore rule, which only screens top-level entries of `pinakes.templates` (T1, and `template.py:36-46` accepts a name containing `/` and `..`). |
| **B. Diff the KB's manifest against a freshly rendered current template** | No new files, no archive discipline. Works for every KB, including pre-archive ones. | Cannot distinguish a template change from a user's deliberate edit. Reports `candidates_per_source = 30` (a user's tuning) identically to a template default that moved. This is the project's recurring defect shape: a report that names one property and is satisfied by another. |
| **C. Record the rendered manifest's *hash* at `init`** into `[kb]` | Detects *that* it drifted, cheaply. | Cannot show *what* drifted, so `pnk upgrade` still has nothing to print. Adds a manifest key no Pinakes before it can read. Cannot help any KB in existence. `.pinakes/` is not an option — it is disposable by invariant. |
| **D. Record the rendered manifest *itself* at `init`** — a committed `pinakes.toml.birth` beside the manifest | A true **per-KB** three-way base: base = this KB's own birth manifest, and it is exact rather than reconstructed. Needs no archive discipline, no ledger and no gate. Works for **third-party templates** and for versions this build does not ship — both of which A cannot serve. Nothing to keep in sync: the file is written once and never again. | Helps no KB in existence either — it starts at the first `init` after it ships, exactly like A and C. Puts a second file in the user's KB that they must not delete, in a tool whose whole posture is that a KB is `docs/` plus one manifest. A user who edits `pinakes.toml.birth` (or drops it from git) silently changes what `pnk upgrade` believes, with no gate able to notice — A's archive at least has a ledger. Does not make `pnk doctor`'s **template-to-template** report (T2) possible: that needs the *template's* history, not this KB's. |

**Recommendation: A**, because T2's report is template-against-template and only A can produce it,
and because D's per-KB file is unguarded state in a directory the user owns. **A and D are not
exclusive** — if the planner wants `pnk upgrade` to work for third-party templates later, D is the
extension, and nothing in T1–T4 forecloses it.

**Settled as A by implication, 20260804.** D-2b's taken answer is *"bump the template version and
archive the bump"*, which is option A's machinery and nothing else's. T1 therefore builds the
in-wheel archive, its ledger and its gate. A's cons stand as written — in particular *"helps no KB
whose recorded version predates the archive"*, which under D-2b is **every KB in existence** and is
the accepted cost, not an oversight.

**None of A, C or D helps a KB that exists today.** That is not a defect of the option; it is D-2b.

### D-2b — What content does `notes@1.0` denote, and what does T1 seed the archive with? ✅ TAKEN

> ### ✅ **TAKEN 20260804 — option D.**
>
> **`notes@1.0` is not archived.** T1 bumps the live template to a new version and archives *that*
> as the archive's first and only entry. Every KB recording `notes@1.0` — which is every KB in
> existence — is routed to T2's **cannot compare** path, which names a remedy rather than shrugging.
> **The *already applied* third outcome is built unconditionally**, in T3 and T4, and is tested
> against a **synthetic** two-version template because this decision makes it unreachable from
> `notes`.
>
> **Why.** `1.0` denotes six different template contents (M1, M2, M4); any seed is a guess for five
> of them, and the wrong guess for every KB created since `01c60db` — where `--apply` would
> re-insert lines already present and duplicate `per_operation_eur` and `monthly_eur`, a TOML
> duplicate-key error landing every such run in the rollback path. The accepted cost is stated and
> not softened: **`pnk upgrade` is permanently useless for 100% of KBs that exist today**, and the
> machinery's first real use is the next template change after T1's bump.

**This is the finding that most changes T1, and the draft had it backwards.** `template.toml`'s
`version = "1.0"` has never changed (M1) while `pinakes.toml.j2` changed in five later commits (M2)
and `eval/questions.yaml` in one (M4). **`notes@1.0` therefore denotes six different template
contents**, and every one of them shipped *as* `1.0`. A KB created today records `notes@1.0` with
today's content — verified at `d001175`:

```
$ pnk init /tmp/xkb && pnk doctor --kb /tmp/xkb
OK   template: notes@1.0
```

An earlier draft instructed seeding `_versions/1.0/` from `873d2e2` *"not by copying today's files"*.
That is wrong, and the failure is not cosmetic: for every KB created since `01c60db`, the hunks
computed from that base are **already present in the KB's manifest**. Under T3 their context lines
are found unmodified, so they report as "applies cleanly"; under T4 `--apply` re-inserts them —
duplicating the comment block and duplicating `per_operation_eur` and `monthly_eur`, which is a TOML
duplicate-key error, so the write fails its re-parse and every such run lands in the rollback path.
`pnk upgrade --apply` would be broken for the majority of KBs in existence.

| Option | Pros | Cons |
|---|---|---|
| **A. Seed `_versions/1.0/` from `873d2e2`** (the draft as written) | Preserves a demonstrable drift: T2/T3/T4 have something real to report on day one. | **Refuted above.** The base is a guess for five of the six contents that shipped as `1.0`, and it is the wrong guess for every KB created since 20260726. A report whose base was never this KB's content is the defect class this plan exists to remove. |
| **B. Do not archive `1.0` at all.** Bump the live template to a new version, archive *that*, and route every KB recording `1.0` to T2's **"cannot compare"** path — *subsumed by the taken D* | The only honest position: the content behind `1.0` is genuinely ambiguous, and the tool says so instead of guessing. No wrong-base hunks can be computed, so T4's duplicate-key catastrophe cannot occur. Closes F1 — the shipped check finally fires, and what it says is true. The archive keeps its promise from the first entry. | `pnk upgrade` is useless for **100% of KBs in existence**, permanently — it can only say "I cannot reconstruct what you were stamped from." Every existing KB gets a `WARN` from `pnk doctor` with no action but a manual diff. The release ships machinery whose first real use is the *next* template change. |
| **C. Seed `_versions/1.0/` from today's live files**, and do not bump | Correct for every KB created since `01c60db` — the large majority — and those KBs correctly report "up to date". | Silently wrong for pre-`01c60db` KBs (same defect as A, smaller blast radius, and undetectable). **Contradicts T1's own gate**: with `1.0` archived as the live content and no bump, the version-bump-with-no-content-change leg has nothing to check and the release ships with zero observable behaviour change — no drift to report, F1 still not demonstrated. If a bump *is* then made, `1.0` and the new version are byte-identical and the gate fails by construction. |
| **D. B, plus an already-applied outcome** ✅ **TAKEN** — B's routing, and the hunk applier additionally reports *already applied* as a third outcome (neither clean nor conflict) | B's honesty, and it also handles the case that arises regardless of the seed: a user who adopted a template change by hand and then runs `pnk upgrade`. | The third outcome must be built and tested even though B makes it unreachable from the archive itself — so its test needs a synthetic template, not `notes`. Inherits B's whole cost column, including *`pnk upgrade` is useless for every KB in existence*. |

**Taken: D**, 20260804 — B's routing plus the already-applied outcome. A and C are rejected on the
cons above and must not be re-opened by a later reader who notices the release ships no observable
diff against `notes`: that is C's failure mode, not an argument for it.

**The already-applied outcome is unconditional.** It is not a consequence of this decision and does
not depend on it — a user who read `pnk doctor`'s report and hand-adopted the change is a real case
that no seeding choice removes. It is written into T3's placement predicate and T4's write rules
below as a first-class outcome, and **its tests use a synthetic two-version template** because D
makes it unreachable from `notes`.

### D-3 — What does a template version number denote?

| Option | Pros | Cons |
|---|---|---|
| **A. Any byte under the hashed set** ⭐ | Unambiguous, mechanically checkable, and correct for this template: the comments *are* the product — `pinakes.toml.j2:11-14` is how a user learns PDFs need a glob, and it is the entire content of the live gap F3 names. A rule that ignored comments would ignore the half of M3 that matters. | Bumps on a typo fix. Users see version churn that changes no behaviour. |
| **B. Consumed content only (keys and values)** | A version number tracks behaviour, and under B `notes` *would* need a bump today — M3's two `[budget]` value changes are exactly what B tracks. | It cannot see the PDF-glob comment block, which is 100% of the live gap in F3 and the thing `docs/KB-UPDATES.md` §9 claims to close. So B leaves the drift the user is actually harmed by invisible, while bumping for the drift they can already read in the CHANGELOG. (An earlier draft said B leaves `notes` at 1.0 forever; M3's re-measurement makes that false, and B is stronger than the draft claimed — just still blind where it counts.) |
| **C. Semantic — the author decides** | Flexible. | Unenforceable; it is the rule-without-a-gate that F1 already is. |

**Recommendation: A**, and say so in `template.toml`'s own comment so the next author does not
re-litigate it.

### D-4 — What happens to `vector_tier = "sqlite-vec"` before the tier exists? (F5)

| Option | Pros | Cons |
|---|---|---|
| **A. Refuse at parse time, naming `numpy`/`auto`** ⭐ | Matches the manifest's own posture — an unknown key and an empty string are both hard errors precisely so a user is never left believing they configured something. Costs one entry in `VECTOR_TIERS` and its restoration in T6. | A behaviour change for anyone who set it: **their KB stops loading entirely** — every command, including `pnk search`, not just the one that would have used the tier. `docs/MANIFEST.md:135` currently documents `sqlite-vec` as a settable value, so this breaks a *documented* config contract, not only an accidental one. Its release type is settled — **D-12, taken 20260804: a PATCH with the break stated** — so choosing A commits to shipping a config-contract break in a PATCH, deliberately and in the CHANGELOG's own words. |
| **B. Accept and warn on every command** | Nothing breaks. | A warning on a value that cannot be honoured is noise until it is honoured, and there is no mechanism to remove it on time. |
| **C. Leave it** | Zero work. | A validator that accepts a value it ignores is the defect class this project spends review passes hunting. |
| **D. WARN in one release, refuse in the next** — accept `sqlite-vec` with a deprecation warning, then apply A | Nobody's KB stops loading without having first been told, in the tool, that it would. Turns a config-contract break into a deprecation, which is the shape a documented value deserves. | Two releases instead of one, and the second is easy to forget — the same rule-without-a-gate shape as F1 unless the removal is written into a plan at the moment the warning ships. B's objection applies to the interim release: a warning on a value that changes nothing is noise. **The warning may not name the release that will refuse it** — `CLAUDE.md`'s unbuilt-work rule forbids a version number for unbuilt work *in an error message* by name — so it points at `docs/STATUS.md` instead, which is a weaker signal than the option's pro implies. |

**Recommendation: A**, shipped as T5, standalone, before or independently of everything else here —
on the grounds that nobody can be harmed without having set a value that never did anything, and
that `plans/20260731_2128-source-walk-containment.md` set the precedent for hard-erroring a manifest that
previously loaded. **D is the defensible alternative** and the planner should take it if the
`docs/MANIFEST.md:135` documentation is judged to be a real promise rather than a disclosure.

**D-12 (taken 20260804) does not decide this.** It fixes the *type* of whichever increment refuses
the value — a PATCH with the break stated — and that is true under A (T5 refuses) and under D (the
second increment refuses; the warning increment is also a PATCH, being a fix). **Choosing D means
T5 splits into two increments, and the refusing one must be written into a plan when the warning
ships** or it is F1's shape again. Nothing else in this plan depends on which is chosen.

### D-5 — Where does the pre-`--apply` manifest go? (D-1 = B, settled by implication — so this is live)

| Option | Pros | Cons |
|---|---|---|
| **A. Write `pinakes.toml.orig` beside it and print the path** ⭐ | Recoverable without git. One file, named, printed, never deleted by Pinakes. | Creates a file in the user's KB that they did not ask for — mitigated by printing it, and by refusing to overwrite an existing `.orig`. |
| **B. Require a clean git tree** | No new files; the user's own VCS is the backup. | Not every KB is a git repository, and the KB is a directory by design. Refusing to run outside git makes a portable tool non-portable. |
| **C. No backup — rename-atomic write and re-parse-or-restore in memory** | Nothing left behind. | Recovers from a *parse* failure only. A semantically-unwanted-but-valid change is unrecoverable. |

**Recommendation: A**, with C's re-parse-or-restore *also* implemented — they guard different
failures. **D-10 raises the stakes on A specifically:** with `[budget]` hunks applying, `.orig` is
the only way a user who did not want a raised cap gets the old numbers back without an editor and a
memory. T4's exit criteria assert the `.orig` contains the **old** cap, not merely that a file
exists — a backup written after the change would satisfy the weaker check and be worthless.

### D-6 — Does `pnk init` stamp `[kb] requires_pinakes`?

| Option | Pros | Cons |
|---|---|---|
| **A. No — leave it absent** (today's behaviour) ⭐ | A new KB stays readable by any Pinakes that can read its keys. `requires_pinakes` is precisely the key an older build cannot read, so stamping it makes the *diagnosis field itself* the thing that breaks the diagnosis on builds before 0.6.0 (`manifest.py:237-331`). | The floor stays a lower bound that nothing ever raises — **and D-11 (taken 20260804) confirms it: `pnk upgrade --apply` recommends the key and never writes it**, so nothing in this plan raises a floor (`docs/KB-UPDATES.md` §8, which assumes otherwise, is one of the corrections T4 proposes). |
| **B. Stamp `">=<current>"`** | Every new KB carries an honest floor from birth. | On any Pinakes < 0.6.0 the KB fails with "unknown key `requires_pinakes`" — a *worse* error than the one the field exists to prevent, and one that fires for KBs whose floor that build would actually meet. |

**Recommendation: A.** Note that this reasoning does not stop at `init`: **whatever writes
`requires_pinakes` inherits B's cost**, which is why T4 writing it was its own decision — **D-11,
taken 20260804 as option A: it writes nothing.** The two answers now agree, and the consequence is
worth stating once: **no code path in this plan ever writes `[kb] requires_pinakes`.** A later agent
who finds the key written by Pinakes has found a defect, not a feature.

### D-7 — Does a second template ship in this release?

`docs/DESIGN.md:1080` places the template release at *"Generalisation, once real usage has shaped one
template well."* No real usage exists yet: the dogfooding KB is `pinakes-kb` in
`plans/20260801_0749-realism-corpus.md` and is not built.

| Option | Pros | Cons |
|---|---|---|
| **A. No — the machinery ships; a second template waits for evidence** ⭐ | Honours DESIGN's own sequencing. A template authored without a corpus that needed it is a guess with a version number attached, and once released it can never be un-versioned. | The release's headline is machinery, not a visible new capability. |
| **B. Ship `research-papers` from `docs/DESIGN.md` §6.1's sketch** | Concrete, demonstrable, exercises the multi-template path with a real second case. | §6.1's sketch includes `prompts/` for `--deep`, which is the deep release's; the rest is chunking and retrieval tuning nobody has measured on papers. It would set defaults by intuition, which `CLAUDE.md`'s retrieval rule forbids for retrieval and which is no better here. |

**Recommendation: A**, with the gate for a second template written down (T8) rather than left to
judgement.

### D-8 — Is `pnk adopt` in this release?

`docs/graph/PINAKES_APPROACH.md:420` assigns *"`pnk adopt` (automated ClaudeKB fleet onboarding)"* to
the template release. `docs/STATUS.md:261` and `CLAUDE.md`'s unbuilt-work table do not mention it.
**This plan does not schedule it**, on the grounds that it depends on ClaudeKB (APPROACH §8), which
is outside this repository. Flagged so the planner can either drop the APPROACH row or add the work;
leaving two documents disagreeing is the condition this note exists to end.

### D-9 — Does the template release cut once or more than once?

T1–T4 and T7 are one coherent MINOR. **T5 is a PATCH — D-12, taken 20260804** — which is a fact this
row now records rather than defers, and it must not be restated as anything else anywhere. T6 bumps `schema_version` and forces every KB in existence to rebuild — a MINOR of
its own, and one that should not be tied to a release about templates. T8 is gated and may never
happen.

**Recommendation: expect more than one cut**, which `CLAUDE.md` already handles — *"a release that
cuts more than once keeps its name in this table until the final cut."* The alternative the planner
may prefer is splitting the roadmap row into **the template release** (T1–T4, T7) and a separately
named **vector-tier release** (T5–T6), which would let the template name leave the table at its own
final cut. That is a naming decision, not a build-order one, and it is the user's.

### D-10 — What does `--apply` do with a `[budget]` hunk? ✅ TAKEN

> ### ✅ **TAKEN 20260804 — option B: a `[budget]` hunk applies like any other hunk.**
>
> **Taken against this document's recommendation, with the risk accepted as stated:** a tool that
> raises a user's spending caps because a template default moved. The risk is not softened here and
> the applier gets **no `[budget]` special case** — one rule, no exception.
>
> **What makes it defensible is the consent path, and that is now a build requirement rather than a
> mitigating remark.** `pnk upgrade` prints the diff and writes nothing; `--apply` is a separate,
> explicit act the user takes afterwards. A raised cap is therefore something the user **sees and
> consents to**, not something that happens to them. Two obligations follow, both specified in T4
> and both carrying exit criteria that discriminate:
>
> 1. **The printed diff shows a `[budget]` change unmissably** — its own labelled heading, naming
>    every changed key with **both** values, old → new, in both the report and the `--apply` run.
>    It is not left to the user to spot two numbers inside a unified diff.
> 2. **The print provably precedes the first byte written.** T4 already decides everything before it
>    writes anything; this makes the ordering observable in the output stream and asserts it by line
>    position, not by inspection.
>
> **The live case is not hypothetical.** The template's `[budget]` differs from every existing KB by
> exactly two values today — `per_operation_eur` `0.05 → 0.30` and `monthly_eur` `5.00 → 30.00`,
> both shipped in **0.8.0** (`97309d8`, `e3685e1`; `git tag --contains` puts both under `v0.8.0`).
> They are the *only* value-level drift the template has, so the first `[budget]` hunk anyone ever
> sees is a sixfold rise in two caps.
>
> **One thing this decision does not do:** it does not change the accountant. Nothing in T4 spends,
> and a raised cap is a *permission* to spend that still requires a paid entry point from
> `CLAUDE.md`'s allowlist to be invoked deliberately. `confirm_above_eur` is itself a template value
> and is subject to the same rule — a hunk that raised it would also apply, and would also be
> printed under the heading.

Raised by M3's re-measurement: two of the template's changed values are **spending caps**, and both
moved *upward* (`per_operation_eur 0.05 → 0.30`, `monthly_eur 5.00 → 30.00`). Under a naive T4 those
hunks apply cleanly to every unedited KB, and the user's caps are raised sixfold by a command whose
name is "upgrade".

| Option | Pros | Cons |
|---|---|---|
| **A. Refuse to apply any hunk touching `[budget]`; print it and say to edit by hand** — *rejected* | The one class of value where a wrong write costs real money is the one class the tool never writes. Costs one predicate (does the hunk's header or any changed line fall inside `[budget]`?) and one test. Matches the project's posture that spending is always an explicit act. | An exception that is not derivable from the hunk applier's own rules, so it must be stated in `--help`, in `docs/CLI.md`, and in the printed output — an undocumented exception is worse than none. A user who *wants* the new caps must copy two lines. |
| **B. Apply it like any other hunk** ✅ **TAKEN** | One rule, no exception. `pinakes.toml` is the user's file and the diff was printed before anything was written. | A tool that silently sextuples a spending cap because a template default moved. The printed diff is exactly what a user runs `--apply` in order not to have to read. **This con is real and is answered by obligation (1) above — a labelled heading with both values — not by denying it.** |
| **C. Apply it only under a second explicit flag** (`--apply --including-budget`) — *rejected* | Nothing is refused outright; the money change needs its own act of consent. | A second flag on a command that already has a conditional write path. Flag proliferation to serve one table, and the table it serves is only special because of what it happens to contain today. |

**Taken: B**, 20260804. A and C are rejected; their cons above are kept so the trade stays visible.
**Do not re-open this as "the applier should skip `[budget]`"** — the answer is the consent path, and
the place to strengthen it is the printed output and its exit criteria, never a special case in the
hunk applier.

### D-11 — Does `--apply` write `[kb] requires_pinakes` at all? ✅ TAKEN

> ### ✅ **TAKEN 20260804 — option A: `--apply` prints a `requires_pinakes` recommendation and writes nothing.**
>
> **Why.** Writing the key inherits exactly the cost D-6 rejects for `init`: `requires_pinakes` is
> itself unreadable by any build before 0.6.0, so writing it to record that a KB adopted a template
> change makes the KB unreadable by 0.5.x as a side effect. It also fires on **zero real cases
> today** — no template change has ever added a key (F2) — so the machinery removed has never had an
> input.
>
> **What survives is the computation**, because it is what the printed recommendation is made of,
> and its operands are the easy thing to get wrong: the adopted key set is
> `parse(base + applied hunks) − parse(base)`, **not** `parse(ours) − parse(base)`. A key carried
> only by a hunk that conflicted is not in the file and must not appear in the recommendation.
>
> **Accepted cost, stated:** the floor stays a lower bound nothing ever raises, so a KB that has
> adopted a newer key still fails on an older build with "unknown key" — the error
> `requires_pinakes` exists to improve.

D-6 rejects stamping `requires_pinakes` at `init` because *the key itself* is unreadable by any
build before 0.6.0. `--apply` writing it inherits that cost exactly. The draft's original rule also
wrote `">=<the running build's version>"`, which over-constrains: if the adopted key landed in
0.6.0, a floor of `>=0.7.2` refuses builds that could read the KB perfectly well.

| Option | Pros | Cons |
|---|---|---|
| **A. Do not write it. Print a recommendation instead** ✅ **TAKEN** | Removes an entire class of wrong write from T4. Nothing makes the KB unreadable by 0.5.x behind the user's back. **Fires on zero real cases today**: no template change has ever added a key (F2), so the machinery it removes has never had an input. The set-difference reasoning survives — it is what computes the printed recommendation. | The floor stays a lower bound nothing ever raises, so a KB that *has* adopted a newer key still fails on an older build with "unknown key", which is the error `requires_pinakes` exists to improve. |
| **B. Write `">=<the running build's version>"`** | Sound: never understates the requirement, which is the only direction that matters for a floor. Simple, and computable — the build knows its own version. | Over-constrains, sometimes by several releases, and there is no way for the command to know better (see C). Makes the KB unreadable by every pre-0.6.0 build as a side effect of adopting a comment. |
| **C. Write `max(0.6.0, <the version that introduced the adopted key>)`** | The correct floor, exactly. | **Not implementable as stated.** Nothing in the repository maps a manifest key to the release that introduced it; building and maintaining that table is a new gate-less rule of the kind F1 already is. Reject unless someone commits to the table *and* a gate over it. |

**Recommendation: A.** If the planner prefers a written floor, take **B** and state the
over-constraint in `docs/MANIFEST.md`; do not take C without the table and its gate.

### D-12 — What release type is T5? ✅ TAKEN

> ### ✅ **TAKEN 20260804 — option A: T5 is a PATCH, with the break stated plainly.**
>
> **Why.** This project's own precedent, and it is exact rather than analogous:
> `plans/20260731_2128-source-walk-containment.md` shipped as **0.7.1** — a PATCH — a change that
> hard-errors on a manifest which previously loaded, on the reasoning that *the previous behaviour
> was the defect*. A manifest saying `vector_tier = "sqlite-vec"` was never getting `sqlite-vec`
> (F5, M6), so the same reasoning holds without stretching.
>
> **The accepted cost, stated rather than softened:** a user who reads the SemVer table instead of
> the CHANGELOG upgrades a PATCH without reading, and their KB stops loading. The obligation this
> puts on T5 is that **the CHANGELOG entry states the break in its own words** — the value that is
> refused, what happens to a KB that sets it, and the one-line fix — and that the refusal message
> itself names the accepted tiers. Softening the check to avoid the version conversation is the one
> response this decision forecloses.
>
> **Settles the wobble, everywhere.** The number is stated in exactly two places from now on: this
> entry and T5's header. **D-9 no longer defers on it** and no other section may assert a different
> type. `CLAUDE.md`'s unbuilt-work rule is not breached: a *release type* is not a version number,
> and no `v0.x` is written for anything unbuilt.
>
> **What it does not settle: D-4 remains open.** D-12 fixes the type of whichever increment refuses
> the value. Under D-4 option A that is T5 itself. Under D-4 option D (warn first, refuse next) it
> is the *second* release that carries the PATCH-with-the-break-stated, and the warning release is a
> PATCH too — a warning is a fix, not a feature. Either way there is no MINOR here.

| Option | Pros | Cons |
|---|---|---|
| **A. PATCH, with the break stated plainly in the CHANGELOG** ✅ **TAKEN** | The direct precedent is this project's own: `plans/20260731_2128-source-walk-containment.md` shipped as **0.7.1** a change that hard-errors on a manifest which previously loaded, on the reasoning that the previous behaviour *was* the defect. The same reasoning holds exactly — a manifest saying `sqlite-vec` was never getting `sqlite-vec`. | A user who reads the SemVer table rather than the CHANGELOG upgrades a PATCH without reading, and their KB stops loading. |
| **B. MINOR** | Honest signalling under the global table, at a cost of one version number. Cheap: nothing else in this release depends on T5's number. | Overstates against the 0.7.1 precedent, and invites the next agent to renumber it back. |
| **C. MAJOR** | Literal reading of *"breaking change to public API, install flow, or CLI contract"* — a documented manifest value is arguably a config contract. | 1.0.0 would then be announced by a validator tightening, which is not what a MAJOR is for in a pre-1.0 project. |

**Taken: A**, 20260804, on the 0.7.1 precedent. B and C are rejected; their pros stay above so the
trade is legible. **D-4 option D (warn first, refuse next) remains available and does not conflict**
— it changes *which* release carries the break, never its type.

---

## Still open — for the planner

Nothing below blocks T1–T4. Each is named so it is not mistaken for settled by a reader who sees
four ✅ above.

| # | Open question | Where it bites | State |
|---|---|---|---|
| **O-1** ✅ | **ACCEPTED 20260804 10:30.** `pnk templates` is a decided surface: `docs/CLI.md`'s *Planned — not built yet* table carries its row as of this decision, **before** T7 lands, so the repository never holds a command with no decision record. The rejected alternatives and why: dropping it leaves discovery reachable only by triggering an error, which is the defect; folding it into `pnk init --list-templates` puts a non-initialising flag on `init` and splits the answer to *"which template is my KB on?"* across two commands. **T7 additionally owes an MCP answer** — whether the listing needs a `pinakes_*` tool or is CLI-only — which nothing has decided and T7 must not invent. Original wording: **`pnk templates` (T7) has no prior decision record anywhere in the repository.** `grep -rn 'pnk templates' docs/ plans/ README.md src/` returned nothing; `docs/CLI.md`'s *Planned — not built yet* table lists only `pnk ask --deep` and `pnk upgrade` | T7's existence | **Not decided, and this document does not decide it.** T7 invents a CLI surface. If it is accepted, `docs/CLI.md`'s planned table gains the row **before** the increment lands, so the repository never contains a command with no prior decision record. If it is rejected, T7's second half (`files = [...]` in `template.toml`) still stands on its own and can be re-homed |
| **O-2** ✅ | **DECIDED 20260804 10:30 — a distinct exit code `3`**, against both the draft's recommendation (non-zero `1`) and the planner's (`0`). What this obliges T3 to do, because the cost is real and chosen: **`docs/CLI.md`'s exit-code table becomes four codes, and gains its row when T3 lands — not before**, since documenting a code nothing returns is the defect this project fixed in that same table on 20260804. `3` must mean exactly *"no baseline exists to compare against"* and nothing else, or it becomes a second `1`. Every consumer learns a new code for one path; that is the accepted price of not overloading `1` (published as *operational failure*, which this is not) and not returning `0` (which a script may read as *up to date*). **T3 owes a test that `3` is returned only on that path**, and that a genuine operational failure during `pnk upgrade` still returns `1`. Original question: **What exit code does `pnk upgrade` return on the *cannot compare* path?** | T3's exit-code contract | Raised **by** D-2b: under the taken answer this is not an edge case, it is **every KB in existence**. T3 recommends non-zero (the command could not do what was asked; `pnk doctor`'s WARN is the scriptable signal) and says so in `docs/CLI.md` § Exit codes. **The planner should confirm**, because "`pnk upgrade` exits non-zero on 100% of today's KBs" is a support surface, not a detail |
| **O-3** | **Does T4's demonstrable end-to-end wait for the next template change?** | T4's exit criteria | A consequence of D-2b, not a defect of it: with one archived version, no diff is reachable from `notes`, so T4's positive paths are exercised against a synthetic two-version template. The alternative — landing a *real* `notes` content change plus a second bump inside this release, purely to make the machinery demonstrable — is available and is **not** taken here, because inventing a template change to exercise a tool is the tail wagging the dog. Flagged so the planner chooses deliberately |
| **O-4** | D-1, D-2 | recorded above as settled *by implication* | They are consequences of D-10/D-11 and D-2b rather than answers the user gave in their own right. If the planner disagrees with either, say so before T1 starts — T1 builds D-2 = A's archive on day one |
| **O-5** | D-3, D-4, D-5, D-6, D-7, D-8, D-9 | as tabled above | Recommendations only. D-4 and D-9 are the two that touch a release cut |

---

## Ground rules

Identical in force to `plans/20260729_0256-links-and-graph.md` § *Ground rules*; restated because an executor
should not have to cross-reference to know what binds them.

- **Worktree + branch per increment**, `YYYYMMDD_HHMM-t<N>-<slug>`, timestamp from `date`.
- **Tests ship in the increment that introduces the behaviour.** Never deferred.
- **`./check.sh` green before review**, then **break the code on purpose** for the mutation targets
  each increment names, per assertion and not per commit.
- **Retrospective review** — a fresh adversarial pass over the increment's own diff, its findings and
  fixes committed separately.
- **A `changelog.d/` fragment in the same commit as the code.** Never an edit to `CHANGELOG.md`.
  A `retro.d/` fragment for anything worth keeping. Never an edit to `docs/RETROSPECTIVES.md`.
- **Every new gate also gets its own CI job** — `ci.yml` never invokes `check.sh`.
- **A gate that cannot run says so and is still a gate**, with a test asserting the printed reason.
- **Docs land in the same commit as the behaviour**; every increment names its homes.
- **Before merging, `python3 tools/shared_file_overlap.py --fetch --strict`**, then read the merged
  state of everything it names.
- **Nothing in this plan may spend money.** `.paid-path-allowlist` is unchanged in every increment.
  **"Extending the free-path gate's coverage" names two exact edits**, and an increment that adds a
  CLI surface without both has not done it:
  1. `tests/free_path_run.py` — add a `main([...])` call for the new command inside
     `_run_free_surfaces` (`tests/free_path_run.py:182-202`), so the fresh-subprocess run actually
     reaches it;
  2. `tests/test_paid_path.py` — add the new module to the surface list the run asserts it reached
     (`tests/test_paid_path.py:299-314`), which is what stops a run that quietly did nothing from
     satisfying every "no paid import" assertion below it.

  **T3, T4 and T7 each name these two files in their deliverable lists.** `tools/paid_path_gate.py`
  and `.paid-path-allowlist` are *not* edited — gates 1 and 2 scan `src/` wholesale and need no
  entry for a new module that imports nothing paid.
- **No new core dependency** without a row in `pyproject.toml`'s comment and a stated reason. This
  plan proposes **none**, and `docs/KB-UPDATES.md` §5's `tomlkit` is not needed *for the hunks* —
  they are applied as text (F2). **T4 still makes one key-level write** (`[kb] template`), so the
  claim is not free: T4 specifies that edit as a bounded textual operation with its own test, and
  names the tomlkit alternative so the planner can overrule.
- **Every test name in this plan is a prediction, and predictions are not binding.**
  `docs/VERIFICATION.md:3-8` records the measurement: `plans/20260727_1543-v0.2.md` named 98 test paths and **61
  did not resolve**, because the names were written before the tests. `tests/test_verification.py`
  hard-fails on an unresolvable name, so a predicted-then-renamed test turns the branch red. **The
  names below describe what must be pinned, not what the function must be called.** Each increment
  adds `docs/VERIFICATION.md` rows for the tests it *actually wrote*, and the Verification table at
  the end of this plan is a shape, never a contract.

---

## Increments

Three tracks. **A** (T1–T4) and **B** (T5–T6) are independent of each other and may run in parallel
by different agents; **C** (T7–T8) depends on A. T5 depends on nothing.

### T1 — The version archive and the template-drift gate

**Why first.** Nothing else in track A can be correct without it: T2, T3 and T4 all need the recorded
version's content to exist at runtime (F4), and all three are meaningless while no version ever bumps
(F1).

**What lands.**

1. **The archive.** `src/pinakes/templates/notes/_versions/<version>/` holds a frozen byte-for-byte
   copy of that version's **consumed** files: `pinakes.toml.j2`, `README.md`, `eval/questions.yaml`,
   and `template.toml`.

   > ✅ **What seeds it is decided — D-2b, taken 20260804, option D. `_versions/1.0/` is never
   > created.** The archive's first and only entry is the version step 2 bumps to, copied from the
   > live files at that moment. **When T1 lands, `archived_versions("notes")` returns exactly one
   > version**, and three consequences follow that the rest of this increment is written around:
   > gate leg (ii) is vacuously true and must say so; T2's *cannot compare* path is the only
   > outcome reachable from `notes`; and every positive test in T2–T4 needs a synthetic
   > two-version template.
   >
   > **Never seed `_versions/1.0/` from anything** — not `873d2e2`, not today's files. `notes@1.0`
   > denotes **six** different template contents (M1, M2, M4), all of which shipped as `1.0`; a
   > seed is a guess for five of them. For every KB created since `01c60db` the hunks computed
   > from a `873d2e2` base are already present in `theirs`, so `--apply` re-inserts them and
   > duplicates `per_operation_eur` and `monthly_eur` — a TOML duplicate-key error landing every
   > such run in the rollback path. D-2b holds the full refutation; this is the executable form.
2. **The bump.** `notes`' `template.toml` gains a new `version` and `_versions/<new>/` is added as a
   byte-for-byte copy of the live files. **`1.1` is used illustratively throughout this plan; the
   actual number is chosen when T1 lands** — a version belongs to the thing when it is cut. Per D-3
   the version denotes any byte under the hashed set. (`notes@1.1` is a *template* version, not a
   release version — naming it is not a breach of `CLAUDE.md`'s unbuilt-work rule, and T1 is the
   increment that cuts it.)

   **The bump is not cosmetic and the increment must not be shipped as if it were.** It is what
   closes F1: `pnk doctor` has returned `Status.OK` on every KB in existence for every version of
   Pinakes, and after T1 it warns on all of them. That is the increment's one user-visible effect,
   it is intended, and it should be the CHANGELOG fragment's headline rather than the archive.
2b. **Two functions, because everything after T1 needs them and inventing them later scatters the
   archive's path layout across three modules.** `template.archived_versions(name) -> list[str]`,
   and `template.render_archived(name, version, context) -> str` — the archived counterpart of
   `render_manifest`, reading `_versions/<version>/pinakes.toml.j2`. T1's gate leg (vi) is their
   first caller; T2 and T3 are the rest. They raise `TemplateError` naming the version when it is
   not archived, which is the *cannot compare* path's source of truth.
3. **`templates/_versions.toml`** — a committed ledger, one row per `(template, version)`, carrying
   the SHA-256 of that version's archived directory (files sorted by relative POSIX path; each entry
   hashed as `path\0bytes`). It exists so that editing an archived version requires editing two files
   in one commit, which a reviewer can see.

   **Fix the schema in this increment and write it down**, because T2–T4's fixtures generate rows
   and a fixture that guesses the shape fails in a later increment against a gate it cannot see:

   ```toml
   [[template]]
   name    = "notes"
   version = "1.1"
   sha256  = "…"     # content_hash(templates/notes/_versions/1.1/)
   ```

   An array of tables rather than a nested key, so a row is appendable by a fixture and readable by
   `tomllib` without a schema-shaped dict walk.
4. **`tools/template_drift_gate.py`**, added to `check.sh` **and** its own CI job.

   **Its content hash is an importable function** — `content_hash(directory: Path) -> str` at module
   level, with the module importable without running the gate (`if __name__ == "__main__":`). This
   is not tidiness: T4's exit criteria and the T2–T4 test fixtures build synthetic archived versions
   and must write `_versions.toml` rows the gate will accept. **A fixture that re-implements the
   hash drifts from the gate, and the gate wins** — the failure surfaces as an unrelated red test in
   an unrelated increment. One function, one caller-visible name.

   It asserts, for every template:
   - **(i)** the live **content hash** equals `_versions/<live template.toml version>/`'s content
     hash;
   - **(ii) no two archived versions of a template share a content hash** — the converse half, which
     `docs/KB-UPDATES.md` §6 also asks for ("a version bumped with no content change"). Stated over
     the *set of archived versions* rather than "the previous release", which nothing in the
     repository defines: the archive is the record, and it is the thing the gate can read. It is
     checkable only because **`template.toml` is excluded from the content hash** — hashing the file
     that declares the version would make every bump change the hash by construction, and this half
     could then never fire. Excluding it is what makes the check able to fail. **With one archived
     version this leg is vacuously true**, and the gate must say so in its output rather than
     reporting a pass that checked nothing;
   - **(iii)** every archived version's content hash equals its `_versions.toml` row;
   - **(iv)** `_versions.toml` has a row for every archived directory and an archived directory for
     every row;
   - **(v)** the live version is present in the archive;
   - **(vi) every archived version renders** under `template.render_context` built from a stock
     manifest. See T2 for why: the contexts of two versions are not the same object, and an archive
     that no longer renders is an archive `pnk upgrade` cannot read. Without this clause the archive
     rots silently and the failure surfaces years later inside a user's `pnk upgrade`;
   - **(vii) an archived directory has been touched by exactly one commit** —
     `git log --format=%H -- src/pinakes/templates/<name>/_versions/<version>/` returns one hash.
     **This leg exists because (i)–(iv) cannot see a three-file edit**: an author who edits
     `pinakes.toml.j2`, copies it over `_versions/1.1/`, and updates the `_versions.toml` row passes
     every content check with the version unchanged. Three files, one commit, gate green, property
     violated. (vii) fails on that, and on the one-file and two-file cases as well.

   **(vii) is the gate's only git-dependent leg, and it is the reason the gate has a cannot-run
   path.** `git log` returns nothing in a shallow clone, and `.github/workflows/ci.yml` uses
   `actions/checkout@v4` with **no `fetch-depth`**, i.e. depth 1 — so **the gate's own CI job must
   set `fetch-depth: 0`**, and the gate must detect the absence of history (`git rev-parse
   --is-shallow-repository`, or no `.git` at all), **skip leg (vii) only**, and print
   `leg (vii) skipped: no git history here (shallow clone or not a checkout)`. A skip is not a pass:
   the printed reason is the ground rule's "a gate that cannot run says so", and it is what
   `test_the_gate_names_its_reason_when_it_cannot_run` pins.

   The content hash's scope is **everything under `templates/<name>/` except `_versions/` and
   `template.toml`** — an *exclude*-list, so a template gaining a new consumed file is covered by
   default. **`README.md` is in scope**, correcting `docs/KB-UPDATES.md` §6, which exempts it:
   `copy_extras` (`template.py:78`) copies it into every KB, so it is consumed, and exempting it
   would let the KB's copy drift without a bump — the exact failure the gate exists to prevent.
5. **Both hardcoded `notes@1.0` assertions move**, not one:
   `tests/test_init.py:20` (`manifest.kb.template`) and `tests/test_init.py:99`
   (`TemplateInfo.reference`). Measured at `d001175`:
   `grep -n 'notes@1.0' tests/test_init.py` → `20:` and `99:`. Bumping one and leaving the other
   lands the increment red. **Leave both exact.** A version-agnostic assertion
   (`startswith("notes@")`) would pass under every future bump and is the defect class this project
   hunts: it names "the KB records the template it was stamped from" and is satisfied by "the KB
   records something beginning with `notes@`".
6. **A template name may not contain a path separator or `..`.** This is not archive hygiene — it is
   a live hole that the archive makes reachable. `_root()` (`template.py:36-46`) joins the name onto
   the package root with no validation; measured at `d001175`:

   ```
   template.describe("notes/../notes")     -> TemplateInfo(name='notes', …)   # succeeds
   template.describe("../templates/notes") -> TemplateInfo(name='notes', …)   # succeeds
   template.describe("notes/eval")         -> FileNotFoundError               # bare, not a PinakesError
   ```

   With `_versions/` present, `pnk init --template notes/_versions/1.0` stamps a KB from an archived
   version — a "template" nobody released. `_root` gains a name check (a single path component, no
   separator, no `..`, matching `[A-Za-z0-9][A-Za-z0-9_-]*`) raising `TemplateError` with the
   available list, **before** the `joinpath`. This is the assertion that replaces the vacuous
   archive-visibility test below.

**What does not land.** No behaviour change for any user *except* an invalid `--template` name now
failing with a message instead of a traceback (step 6). `pnk init` stamps the bumped reference;
`pnk doctor` begins to WARN on every KB created before this increment, which is F1's gap becoming
visible and is the point.

**Three honest limits, to be stated in the gate's own docstring.**
(a) With git history present, leg (vii) catches a coordinated multi-file edit; **without it — a
shallow CI clone, an sdist, a vendored copy — the gate degrades to (i)–(vi)**, which a three-file
edit passes. The gate says which mode it ran in; it never claims the stronger one silently.
(b) An archived `template.toml` is outside the content hash, so its declared version can be edited
without (i)–(iv) noticing; only its presence and its directory name are checked. Leg (vii) covers
this when history is available.
(c) Leg (vii) has a false-positive mode: a tree-wide move, a licence-header sweep or a
`git filter-repo` adds a second commit to an untouched archive directory. The remedy is to name the
directory and the commits in the failure message so a human can see it is not a content edit — not
to weaken the leg.

**Tests** — `tests/test_template_drift.py`:

| Test | Pins |
|---|---|
| `test_the_live_template_matches_its_own_archived_version` | the gate's primary predicate |
| `test_editing_a_consumed_file_without_bumping_the_version_fails_the_gate` | F1 — drive the gate over a temporary template tree, mutate one byte of `pinakes.toml.j2`, assert non-zero exit and that the message names the file |
| `test_editing_only_a_comment_fails_the_gate` | **D-3 and F2 together.** A gate that passed here would be blind to the PDF-glob comment block, which is the entire content of the live gap (F3). Mutate a comment line only |
| `test_editing_the_template_readme_fails_the_gate` | the `docs/KB-UPDATES.md` §6 correction — the README is consumed by `copy_extras` |
| `test_a_new_consumed_file_is_covered_without_editing_the_gate` | the exclude-list choice. Add a file to the temporary template, assert the gate now fails until the version bumps |
| `test_a_bumped_version_with_no_archived_directory_fails` | the archive cannot fall behind the version |
| `test_a_version_bump_with_no_content_change_fails_the_gate` | leg (ii) — **and it is only reachable because `template.toml` is outside the content hash.** Re-include it and this test cannot fail. Needs a temporary template with **two** archived versions; against `notes` alone the leg is vacuous |
| `test_a_modified_archived_version_fails_against_the_ledger` | leg (iii) — the archive cannot be edited silently in one file |
| `test_a_three_file_edit_is_caught_by_the_history_leg` | **leg (vii), and the reason it exists.** In a temporary git repository: edit the live `.j2`, copy it over the archived copy, update the `_versions.toml` row, commit. Assert legs (i)–(iv) all pass and the gate still fails, naming the archived directory and the two commits that touched it. A test that only asserted "the gate fails" would be satisfied by any of the other six legs — assert **which leg** reported |
| `test_the_gate_names_its_reason_when_it_cannot_run` | **the skip path, which now has a cause.** Run the gate over a tree with no `.git` (and over a shallow clone): assert it exits 0, prints `leg (vii) skipped`, and that a three-file edit which `test_a_three_file_edit_is_caught_by_the_history_leg` catches is **not** caught here — so the skip is visible as a real loss of coverage, not a formality |
| `test_an_archived_version_that_no_longer_renders_fails_the_gate` | leg (vi) — archive rot. Add a temporary archived version whose `.j2` references an undefined variable; assert the gate names the version and the variable |
| ~~`test_the_version_archive_is_not_offered_as_a_template`~~ | **Deleted. It could not fail.** `available()` (`template.py:49-54`) iterates the *top level* of `pinakes.templates`; `_versions` lives one level deeper, under `templates/notes/`, so it is never a candidate and `"_versions" not in available()` is true however the underscore rule is written. `describe("_versions")` raises because `resources.files(PACKAGE)/"_versions"` is not a directory — again, not the underscore rule. Both assertions stay true if the rule is deleted |
| `test_a_template_name_with_a_path_separator_or_dotdot_is_refused` | **its replacement, and it fails on `main` today** (step 6): `describe("notes/_versions/1.0")`, `describe("notes/../notes")` and `describe("../templates/notes")` must each raise `TemplateError` naming the available templates. This is the property the deleted test claimed |
| ~~`test_copy_extras_never_copies_the_version_archive`~~ | **Deleted from T1. It could not fail here** — `copy_extras` (`template.py:73-88`) iterates a hardcoded two-entry tuple, so no archive path is reachable whatever the archive contains. The property becomes real only in **T7**, where a template declares `files = [...]`, and it is asserted there |

**Exit criteria — run these, do not reason about them.**

**Four rules every snippet in this plan obeys, each because breaking it produced a criterion that
passed for the wrong reason:**

1. `pnk init` refuses a non-empty directory (`init.py:97-101`), so every snippet starts with
   `rm -rf` on its scratch KB, or it fails on the second run.
2. **Never assert on `pnk doctor`'s exit code.** It is `1` on this repo's default `uv sync` because
   `[st]` is absent (measured; `tests/free_path_run.py:182-190` makes the same point in its own
   docstring). Assert on the specific line: `| grep '^OK   template'`, `| grep '^WARN template'`.
3. **Never use `grep -c … # 0`** — `grep -c` exits **1** when the count is zero, which aborts the
   block under any `set -e` reading. Use `! grep -q …`.
4. **`sed -i ''` is BSD/macOS; use `sed -i` on GNU. `shasum` is macOS; `sha256sum` on GNU.** Say
   which you ran.
5. **A command whose non-zero exit is *expected* is written `rc=0; cmd … || rc=$?`** — never
   `cmd … ; echo $?`. Measured: under `set -e`, `false ; echo $?` exits the script **before** the
   echo, so a block written to observe a refusal stops at the very command it was written to
   observe, and the assertions after it never run. Every block below that expects a refusal — T3's
   *cannot compare*, T4's conflict, T4's `notes` path, every `pytest` call whose count is then
   asserted — uses the `|| rc=$?` form for that reason. (This is rule 3's failure one level up: rule
   3 is about `grep -c`, this is about every command.)

```bash
rc=0; uv run --frozen python3 tools/template_drift_gate.py >/tmp/t1gate.out 2>&1 || rc=$?
[ "$rc" -eq 0 ] || { cat /tmp/t1gate.out; exit 1; }
grep -q 'history leg' /tmp/t1gate.out    # it always says which mode it ran in — assert that, or
                                         # "the gate passed" and "the gate skipped its only
                                         # history-dependent leg" are the same observation
# D-2b leaves exactly one archived version, so leg (ii) checks nothing. The gate must SAY that
# rather than report a pass — otherwise the release ships a green gate with a leg that has never
# run against the shipped template. (The pattern below is the *spec* of the gate's output; when the
# wording is written, put THAT string here.)
grep -qi 'leg (ii).*vacuous' /tmp/t1gate.out
# and assert the archive's shape rather than printing it for a human to judge:
uv run --frozen python3 - <<'PY'
from pinakes import template
v = template.archived_versions("notes")
assert len(v) == 1, f"D-2b: exactly one archived version at T1, got {v}"
assert "1.0" not in v, "D-2b: 1.0 is never archived"
print("archive holds exactly:", v)
PY
rm -rf /tmp/t1kb && uv run --frozen pnk init /tmp/t1kb
# `pnk init` stamps the BUMPED reference. `grep '^template'` alone is satisfied by `notes@1.0` —
# the one string that proves the bump did NOT happen — so assert both halves, and compare against
# the installed reference rather than a number written into this plan:
ref=$(uv run --frozen python3 -c 'from pinakes import template; print(template.describe("notes").reference)')
grep -qF "template = \"$ref\"" /tmp/t1kb/pinakes.toml
[ "$ref" != "notes@1.0" ] || { echo "the version was not bumped — T1 step 2 did not land"; exit 1; }
# (verified at d06ef7e that this shape resolves: on `main` today `$ref` is `notes@1.0` and the
#  manifest line is `template = "notes@1.0"`, so the grep matches and the guard above is the only
#  thing that fails — which is exactly what it is for.)
# A KB that records the old version now warns, which is F1 closing. At T1 this is doctor's EXISTING
# version-string comparison (doctor.py:163-184); the *cannot compare* wording is T2's and must not
# be asserted here:
sed -i '' 's/^template = .*/template = "notes@1.0"/' /tmp/t1kb/pinakes.toml
uv run --frozen pnk doctor --kb /tmp/t1kb | grep '^WARN template' | grep -qF 'notes@1.0'
uv run --frozen pnk doctor --kb /tmp/t1kb | grep '^WARN template' | grep -qF "$ref"  # names both
# an invalid template name is a message, not a traceback (step 6). `init` calls `template.describe`
# before `_check_target` and before any mkdir (init.py:48-50), so nothing is created either way:
rm -rf /tmp/t1evil
uv run --frozen pnk init /tmp/t1evil --template 'notes/../notes' 2>&1 | grep -q 'no template named'
! test -e /tmp/t1evil
# the archive travels in the wheel — otherwise `pnk upgrade` works from a checkout and not from PyPI.
# Two halves: it is *in* the wheel, and it is *reachable* through importlib.resources when installed.
make build && unzip -l dist/*.whl | grep '_versions/'                   # non-empty
uv run --isolated --no-project --with dist/*.whl python3 - <<'PY'
from importlib import resources
root = resources.files("pinakes.templates").joinpath("notes").joinpath("_versions")
assert root.is_dir(), "the archive did not survive packaging"
versions = sorted(e.name for e in root.iterdir() if e.is_dir())
assert versions, "the archive is present but empty"
print("archive reachable from the installed wheel:", versions)
PY
uv run --frozen python3 - <<'PY'                                        # the gate can fail
import pathlib, subprocess, sys
p = pathlib.Path("src/pinakes/templates/notes/README.md"); b = p.read_bytes()
p.write_bytes(b + b"\n<!-- mutant -->\n")
r = subprocess.run([sys.executable, "tools/template_drift_gate.py"], capture_output=True, text=True)
p.write_bytes(b)
assert r.returncode != 0 and "README.md" in (r.stdout + r.stderr), r
print("gate rejects an unversioned README edit")
PY
./check.sh
```

**One thing this block cannot check, stated rather than faked:** leg (vii) needs a repository with
history, and the three-file edit that only it catches cannot be rehearsed with a `sed` one-liner.
It is covered by `test_a_three_file_edit_is_caught_by_the_history_leg`, which builds a throwaway git
repository — run `uv run --frozen pytest -q tests/test_template_drift.py -k history` and read the
output rather than treating `./check.sh` green as evidence for it.

**Docs:** `docs/MANIFEST.md` (`[kb] template` — what a version denotes, per D-3);
`docs/STATUS.md` (the increment row, and § *Caveat: PDFs are off by default*, whose “nothing today detects or reports that divergence” sentence this partly closes);
`docs/CLI.md` § `pnk init --template` (a template name is one path component);
`docs/VERIFICATION.md` (**only** the rows this increment's own tests require);
`.github/workflows/ci.yml` — the gate's own job, **with `fetch-depth: 0`** on its checkout;
`docs/KB-UPDATES.md` §3 case 1, §3 case 3, §6 and §9 — F1, F2, F3, the README-exemption correction
and the withdrawal of §9's "Closes the PDF-glob gap" claim
(**propose to the planner; do not edit**); a `changelog.d/added-*.md` fragment.

**Mutation targets.** Delete the `README.md`-in-scope line and confirm
`test_editing_the_template_readme_fails_the_gate` fails and not another test. Replace the comment-
sensitive hash input with a TOML key-set comparison and confirm
`test_editing_only_a_comment_fails_the_gate` fails. Flip the exclude-list to an include-list and
confirm `test_a_new_consumed_file_is_covered_without_editing_the_gate` fails. Delete leg (vii) and
confirm **only** `test_a_three_file_edit_is_caught_by_the_history_leg` fails — if another test goes
red too, one of them is asserting the wrong thing. Make the shallow-clone detection return "history
available" and confirm `test_the_gate_names_its_reason_when_it_cannot_run` fails on the *printed
reason*, not on an exit code. Remove the name check from `_root` and confirm
`test_a_template_name_with_a_path_separator_or_dotdot_is_refused` fails.

**Mutation honesty.** Each line above is a claim about **one assertion**, not about the increment.
"Mutation-verified" means "this mutant made that assertion fail" — never that the assertion fails
*for the stated reason*, which is why each target above names the test that must fail **and** says
what must not.

---

### T2 — `pnk doctor` reports template drift as a diff, not a version string

**Depends on T1** (the archive).

**What lands.** `doctor._template` keeps its version comparison and gains a second half: when the
recorded version and the installed version differ, it renders **both archived versions** through one
shared context and reports the size of the difference between them.

**The comparison is template-against-template, never template-against-manifest.** That is the whole
design point and it is what makes the report unambiguous: the two sides are both generated, so
nothing the user wrote is in either. A report that included the user's manifest could not tell a
template change from a user's tuning (F4, D-2 option B), and `pnk doctor` must not present the second
as the first.

**One shared context, and it must be a superset.** A single `template.render_context(manifest)`
builds the variable mapping used for *both* renders, from the KB's own manifest with `init`'s
defaults (`init.py:25-26`) for anything the manifest cannot supply.

**Every identity field comes from the manifest, and `{{ template }}` is the one that matters.**
`init.py:62` passes `template=info.reference` — the *installed* reference — because at `init` time
the two are the same thing. They are not the same thing here, and the obvious third choice is a
guaranteed defect: rendering `base` with the recorded reference and `ours` with the installed one
puts a `[kb] template` hunk in **every** report on **every** KB, which under T4's all-or-nothing
conflict rule makes `--apply` refuse for every user who has touched their `[kb]` block. **So
`render_context` takes `name`, `kb_id`, `template` and `created` from `manifest.kb`** — both sides
render the KB's *recorded* reference, the `[kb]` block is identical on both, and it never produces a
hunk. T4's separate claim that it updates `[kb] template` "outside the applied hunks" is coherent
only under this choice.

A user's own edit to a **rendered variable** (`provider = "fastembed"`) is therefore identical on
both sides and cannot appear in the diff. A user's edit to a **literal** line (`final_k = 4`) never
enters either side, because neither side is their file. Both properties come from the same choice and
both are tested.

**The trap, and it is not the one the previous sentence closes.** `render_manifest` uses
`StrictUndefined` (`template.py:67-70`), so a *missing* variable raises rather than rendering empty.
If a later template version renames or drops a variable, a context built for the current version
fails to render an older archived one — on **one** side only, which is the worst outcome available:
`pnk doctor` raises on a KB whose only fault is being old. So `render_context` returns the **union of
every variable any archived version of that template needs**, never just the current one, and T1's
gate asserts every archived version renders under it. A variable that is dropped from the template is
not dropped from the context.

**And the union is not enough on its own, because it cannot cover a template this build did not
ship.** A third-party template, or an archived version that reached a user's machine some other way,
can need a variable no union contains. `jinja2.UndefinedError` is **not** a `PinakesError`, so
`cli.main` emits a traceback rather than a message. So: `render_manifest` catches `UndefinedError`
and re-raises it as a `TemplateError` naming the template, the version and the variable, with the
remedy that this build cannot render that version. Pinned by
`::test_a_template_version_needing_an_unknown_variable_refuses_with_a_message` — which must assert
the **message**, not merely that something was raised, or it is satisfied by any error at all.

**Report shape.** `Status.WARN`, detail `KB says notes@1.0, installed is notes@1.1 — <n> lines
differ`, remedy `Run `pnk upgrade` to see them. Nothing is applied automatically.` **`<n>` is
computed, never a constant** — no test and no exit criterion in this plan asserts a literal line
count (see M3's note on why). Three cases that are not that one, each with its own message and its
own test:

| Case | Status | Message |
|---|---|---|
| recorded version absent from the archive. **Under D-2b (taken) this is `notes@1.0` — every KB in existence — plus the exotic cases (a newer Pinakes wrote the KB; a third-party template)** | `WARN` | `cannot compare: notes@1.0 is not in this build's archive` — never a diff, never a silent OK. **This is the ordinary path, not an edge case, so its remedy is written for a user who did nothing wrong**: it says the recorded version's content cannot be reconstructed, names the manual comparison as the action available now, and says `pnk upgrade` becomes useful from the next template bump onward. A one-word shrug here is the single most-read string this increment ships |
| template name not installed at all | `WARN` | unchanged from today (`doctor.py:170-176`), with the remedy's "(the template release)" parenthesis removed |
| versions equal | `OK` | unchanged |

**Tests** — `tests/test_doctor.py`:

`::test_a_kb_recording_an_older_template_version_reports_the_line_count`;
`::test_a_user_edited_manifest_value_never_appears_in_the_template_drift_report` — set
`provider = "fastembed"` and `candidates_per_source = 30` in the KB, assert the reported line count is
unchanged from an unedited KB (**this is the test that would catch D-2 option B being implemented by
accident**);
`::test_a_comment_only_template_change_is_reported` — the PDF-glob comment block is the entire
content of the live gap (F3), and a report that missed it would be reporting nothing on the case
that motivated the release;
`::test_the_kb_identity_block_never_produces_a_hunk` — the `{{ template }}` choice above. Two
archived versions and a KB recording the older one: assert **no hunk touches `[kb]`**. Without this
the natural implementation puts a `[kb]` hunk in every report and T4 refuses for everyone;
`::test_an_unarchived_recorded_version_says_it_cannot_compare_rather_than_ok` — **run this one
against the shipped `notes`, not a synthetic template**, because under D-2b it is the path 100% of
real KBs take and it is the only one `notes` can reach. Assert the remedy names the manual
comparison, not merely that the status is `WARN`: a `WARN` is also what the version-mismatch line
already produced on `main` before this increment, so status alone does not discriminate;
`::test_a_template_version_needing_an_unknown_variable_refuses_with_a_message` — assert the message
names the version and the variable, not merely that it raised;
`::test_a_template_with_no_drift_reports_ok_and_renders_nothing` — assert the renderer is not called,
so `doctor` on a current KB pays nothing;
`::test_an_archived_version_needing_a_variable_the_current_one_dropped_still_renders` — the union
context. Build a temporary template with two archived versions whose variable sets differ, and assert
`doctor` reports a line count rather than raising.

**Every positive test above needs a synthetic two-version template, not `notes`.** D-2b (taken)
leaves the shipped template with exactly one archived version when T2 lands, so the only outcome
reachable against `notes` is *cannot compare*. **Say this in the test module's docstring.** A test
suite that quietly exercised only the one reachable path would report green over a feature nobody
had run.

**Exit criteria.**

**Split in two, and the split is forced by D-2b rather than chosen.** `notes` can reach exactly one
outcome, so the shell block asserts that one and nothing more; every positive path is a pytest
invocation whose output is read.

```bash
# (1) the one path reachable from the shipped template.
rm -rf /tmp/t2kb && uv run --frozen pnk init /tmp/t2kb
sed -i '' 's/^template = .*/template = "notes@1.0"/' /tmp/t2kb/pinakes.toml
uv run --frozen pnk doctor --kb /tmp/t2kb >/tmp/t2.out 2>&1   # never assert doctor's exit code
grep '^WARN template' /tmp/t2.out | grep -qiF 'cannot compare'
# Verified at d001175 and re-checked at d06ef7e that the anchor resolves: forcing
# `template = "notes@0.9"` on a fresh KB prints
#   WARN template: KB says notes@0.9, installed is notes@1.0
# so `^WARN template` and the two spaces after WARN are real, not a guess at the format.
#
# The remedy is the part a user acts on, and `cannot compare` alone does not prove one was printed.
# Assert the remedy names the manual comparison — pick the exact string when the message is written
# and put THAT here, not this placeholder:
grep -qiF 'compare it by hand' /tmp/t2.out
./check.sh
```

```bash
# (2) every positive path, which `notes` cannot reach. These run against the synthetic two-version
# template in the test module. `-k` can select nothing and still exit green under a casual reading —
# measured at d001175: `pytest -k containment` printed "no tests collected (1288 deselected)" and
# exited 5 — so the collected count is asserted, not assumed.
rc=0; uv run --frozen pytest -q tests/test_doctor.py \
  -k 'template_drift or archived or identity_block' >/tmp/t2pytest.out 2>&1 || rc=$?
cat /tmp/t2pytest.out
grep -qE '^[1-9][0-9]* passed' /tmp/t2pytest.out   # verified at d06ef7e: an empty selection prints
                                                    # "12 deselected in 0.01s" with no "passed"
                                                    # and exits 5, so this fails on zero collection
[ "$rc" -eq 0 ]
```

**The two invariance checks — a rendered variable (`provider`) and a literal (`final_k`) — live in
the test module and nowhere else.** An earlier draft ran them as a shell block against `notes`:
capture the `WARN template` line, edit the manifest, capture again, assert the line is unchanged.
**Under D-2b that block is void** — the line is `cannot compare` before and after *because the
comparison never happened*, so it is invariant under every edit, including one that broke the
feature. It is the exact defect class this plan exists to remove and it is deleted rather than
weakened. In the test module, against a synthetic two-version template, both checks are real:
assert the reported line count is **non-zero** first, then that it is unchanged by the edit.

**Docs:** `docs/CLI.md` § `pnk doctor` (the check's row); `docs/STATUS.md`; `docs/VERIFICATION.md`
rows for the tests above; a `changelog.d/` fragment.

**Mutation targets.** Change the render source from the *archived* recorded version to the KB's own
manifest and confirm `test_a_user_edited_manifest_value_never_appears…` fails. Build the two renders
from two different contexts and confirm the same test fails. Make the unarchived case return `OK`
and confirm `test_an_unarchived_recorded_version_says_it_cannot_compare_rather_than_ok` fails.
Feed `ours` the *installed* reference for `{{ template }}` while `base` keeps the recorded one, and
confirm `test_the_kb_identity_block_never_produces_a_hunk` fails — this is the mutant that matters,
because that implementation is the one a reader of `init.py:62` would write. Remove the
`UndefinedError` mapping and confirm the refusal test fails on the *message*, not on a traceback.

---

### T3 — `pnk upgrade`, print only

**Depends on T1, T2.**

**What lands.** A new command. It reads three inputs and writes nothing:

| Name | What it is |
|---|---|
| **base** | `_versions/<recorded version>/pinakes.toml.j2` rendered through `render_context(manifest)` |
| **ours** | `_versions/<installed version>/pinakes.toml.j2` rendered through the same context |
| **theirs** | the KB's `pinakes.toml`, read as bytes |

It prints, in this order:

1. **What the template changed** — the unified diff `base → ours`. This is the template's own history
   and contains nothing of the user's.
2. **Which of those hunks apply cleanly to `theirs`**, which are **already applied**, and which
   **conflict** because the user edited the same region.
3. **Nothing else.** No user-vs-template diff is ever printed; a line the user changed and the
   template did not is not drift and is not this command's business.

**The placement predicate, stated once and completely — because the loose version of it is where
this command goes wrong.** A hunk has a context (its unchanged lines), a removed set and an added
set. Given `theirs`:

**Evaluated in this order, and the order is part of the predicate:**

| # | Outcome | Predicate |
|---|---|---|
| 1 | **already applied** | the hunk's context **and** *added* lines occur in `theirs`, contiguously, in order, byte-for-byte, at **exactly one** position, and its removed lines do not — the user (or a newer `init`) already has this change |
| 2 | **clean** | the hunk's context **and** removed lines occur in `theirs` that way |
| 3 | **conflict** | anything else: no match, **more than one** match, a partial match, or a match whose lines are in a different order |

**Test 1 before test 2, or a pure-addition hunk is classified wrong.** A hunk that only adds lines
has an empty removed set, so predicate 2 reduces to "the context is present" — which is *also* true
after the change has been applied. Both predicates then match and whichever is evaluated first wins.
Every hunk in M3's `[sources]` component is a pure addition, so this is the ordinary case, not a
corner. `::test_a_pure_addition_already_present_is_already_applied_not_clean` pins the order.

**"Found, unmodified, in `theirs`" is not the predicate**, and an earlier draft said it was. It is
satisfied by a manifest whose `[budget]` block the user moved above `[retrieval]` — every context
line is present, so the loose rule says *clean* while the hunk's offsets are meaningless. It is also
satisfied twice over by `pinakes.toml`'s repeated blank lines and repeated comment shapes. **Uniqueness
and order are part of the predicate, not a refinement of it.**

**Why "already applied" is a first-class outcome and not a curiosity.** A user who read `pnk doctor`'s
report and hand-adopted the change is the ordinary case this command is *for*. Reporting it as
"clean" makes `--apply` re-insert the lines — duplicating a comment block, and duplicating a key,
which is a TOML duplicate-key error. Reporting it as "conflict" tells a user who did the right thing
that they have a problem. It is its own outcome, its own message, and its own test. (It is also the
outcome D-2b's rejected option A would have produced on the *majority* of KBs.)

Three further cases where a user's manifest is *legal* and the applier still cannot place a hunk,
each of which must report a **conflict**:

* the user reordered tables, so a hunk's context lines exist but not in that order;
* the user rewrote the region's whitespace or comments — the manifest is comment-dense by design
  (`pinakes.toml.j2`), so this is not exotic;
* the KB has `[[links.kb]]` entries (`manifest.py:769-803`) appended after `[budget]`, or an
  uncommented `[retrieval.confidence]` table — which lives *inside* the template's own comment region
  (`pinakes.toml.j2:35-41`), so **any hunk touching those lines conflicts for every calibrated KB**.
  Both are near-universal in a real KB and both are fixtures, not thought experiments.

**Scope: `pinakes.toml` only.** `copy_extras` also writes `README.md` and `eval/questions.yaml`
(`template.py:78`), and M4 shows the template's `questions.yaml` has drifted. `pnk upgrade` does
**not** touch either, in this increment or T4, and the reason is not oversight: the KB's
`eval/questions.yaml` is the user's golden set, and the template's is an empty stub with a header
(`templates/notes/eval/questions.yaml`). Adopting the template's version would destroy a user's
questions to deliver a comment. Say so in `docs/CLI.md`, so the omission is a stated boundary rather
than a gap a later agent "fixes".

`--json` emits the same three parts. Exit code `EXIT_OK` (0, `cli.py:32`) when there is nothing to
adopt and `0` when there is — this is a report, not a check, and a non-zero exit would make
`pnk upgrade` unusable in a script that also runs `pnk doctor`. `EXIT_FAILURE` (1) on a refusal.
**State the choice in `docs/CLI.md` § Exit codes**, because "prints a difference" and "fails" are
exactly the two readings a caller will guess between.

**Refusals, each with its own message and test:** the recorded version is not archived; the template
is not installed; `[kb] template` is absent; the recorded and installed versions are equal (print
`up to date` and stop — this one is **0**, it is not a refusal).

> **O-2 — the one exit code D-2b turned into a support surface, and the planner should confirm it.**
> *Recorded version not archived* is `notes@1.0`, i.e. **every KB in existence**. Returning
> `EXIT_FAILURE` there means `pnk upgrade` exits non-zero for 100% of today's users on its first
> run, which is a different thing from a rare refusal.
>
> **This plan takes non-zero**, on the grounds that the command could not do what was asked and
> silently exiting 0 with a "cannot compare" line is how a scripted caller learns nothing; `pnk
> doctor`'s `WARN` is the signal for a caller that wants a status rather than an action. **The
> alternative is defensible**: treat *cannot compare* as a report outcome (0) and reserve non-zero
> for a KB that is malformed. It is one line of code and one row in `docs/CLI.md`; it is flagged
> rather than buried because it is not recoverable once users have scripts.

**Nothing here is a migration.** Per the tension resolution above, the word does not appear in the
command's output, its `--help`, or its docs.

**Tests** — `tests/test_cli_upgrade.py`:

`::test_a_current_kb_prints_up_to_date_and_writes_nothing`;
`::test_a_drifted_kb_prints_the_template_diff` — **assert on content, never on a line count.**
**Against the synthetic two-version template**, not `notes`: D-2b leaves `notes` with one archived
version, so a test written against it would assert over an empty diff. The synthetic fixture
reproduces M3's shape deliberately — a pure-addition comment line and two `[budget]` values — so the
content assertions are the added comment line and **both** the old and the new cap. An earlier draft
asserted "the six comment lines of M3"; two commits later that was wrong on the count, on the
composition, and on their being comments;
`::test_a_hunk_already_present_in_theirs_is_reported_as_already_applied` — **not** clean, **not**
conflict. Assert the printed word and that `--apply` (T4) leaves those lines untouched.
**Unconditional and synthetic**: D-2b (taken) neither creates nor removes this outcome — a user who
hand-adopted a change produces it under every seeding answer — but it does make it unreachable from
`notes`, so the fixture is a two-version synthetic template. **Say that in the test's docstring**, or
a later reader deletes the fixture as over-engineering;
`::test_a_user_edited_region_is_reported_as_a_conflict_not_applied`;
`::test_a_kb_with_links_kb_entries_still_places_unambiguous_hunks` and
`::test_a_kb_with_an_uncommented_retrieval_confidence_table_conflicts_on_that_region` — the two
near-universal real-KB shapes;
`::test_a_user_edit_the_template_never_touched_appears_nowhere_in_the_output` — the counterpart, and
the one that fails if base/ours is ever replaced by manifest/ours;
`::test_an_unarchived_recorded_version_refuses_with_a_remedy`;
`::test_a_reordered_manifest_is_a_conflict_not_a_silent_success`;
`::test_a_hunk_whose_context_matches_twice_is_a_conflict`;
`::test_a_manifest_with_extra_tables_still_places_unambiguous_hunks` — the over-tightening
counterpart, so a later pass does not make every real KB a conflict;
`::test_nothing_under_the_kb_is_written` — snapshot every file's bytes **and** the set of paths under
the KB root before and after, assert both identical. **Snapshot the whole tree, not `pinakes.toml`
alone**: the claim is "writes nothing", and a test that watched one file would be satisfied by a
command that wrote a different one. Compare **bytes and the path set**, not mtimes — an mtime-only
comparison passes for a rewrite of identical content;
`::test_json_and_human_output_report_the_same_hunks`.

**Exit criteria.**

```bash
rm -rf /tmp/t3kb && uv run --frozen pnk init /tmp/t3kb
sed -i '' 's/^template = .*/template = "notes@1.0"/' /tmp/t3kb/pinakes.toml
# `shasum` is macOS; use `sha256sum` on GNU. `-exec … \;` runs one process per file, which is slow
# and correct; `-exec … +` batches and is also fine. `find` lists no directories here, so an
# emptied directory would not show — the *path set* is compared by the named test, not by this block.
before=$(cd /tmp/t3kb && find . -type f -exec shasum {} \; | sort)
# ✅ D-2b (taken): `notes@1.0` is not archived, so this is the *cannot compare* refusal — the only
# outcome `notes` can reach. The diff path has NO exit criterion reachable from the shipped
# template; it is block (2) below, against the synthetic template in the tests.
rc=0; uv run --frozen pnk upgrade --kb /tmp/t3kb >/tmp/t3.out 2>&1 || rc=$?
echo "cannot-compare exit code: $rc"
# ⚠ RECORDED, NOT ASSERTED — O-2 is open. This plan takes non-zero; once the planner confirms,
# replace the echo with `[ "$rc" -ne 0 ]` (or `-eq 0`) and make docs/CLI.md § Exit codes agree in
# the same commit. Leaving it recorded is deliberate: asserting a code this document chose on its
# own would make the criterion pass for a contract nobody agreed to.
test -s /tmp/t3.out    # NOT optional. `before = after` is also true of a command that printed
                       # nothing and did nothing, so the snapshot alone is satisfied by failure.
grep -qiF 'cannot compare' /tmp/t3.out   # and it is THAT refusal, not another guard: "non-zero"
                                          # is available from four refusals in this command
rc=0; uv run --frozen pnk upgrade --kb /tmp/t3kb --json >/tmp/t3.json 2>&1 || rc=$?
python3 -m json.tool </tmp/t3.json >/dev/null   # --json emits JSON on the refusal path too, or a
                                                 # scripted caller gets a traceback where a
                                                 # machine-readable outcome was promised
after=$(cd /tmp/t3kb && find . -type f -exec shasum {} \; | sort)
[ "$before" = "$after" ] && echo "wrote nothing"
./check.sh
```

```bash
# (2) the three placement outcomes, which `notes` cannot reach under D-2b. Run them and read the
# output; `./check.sh` going green is not evidence for a path nothing in it exercises.
# The collected count is asserted because a `-k` expression that selects nothing exits 5 and
# prints no "passed" line (measured at d001175 with `-k containment`: "no tests collected").
rc=0; uv run --frozen pytest -q tests/test_cli_upgrade.py \
  -k 'already_applied or conflict or twice or reordered' >/tmp/t3pytest.out 2>&1 || rc=$?
cat /tmp/t3pytest.out
grep -qE '^[1-9][0-9]* passed' /tmp/t3pytest.out   # verified: an empty selection prints
                                                    # "N deselected" with no "passed" line and
                                                    # exits 5, so this fails on zero collection
[ "$rc" -eq 0 ]
```

**Free-path coverage — a deliverable, not a note.** `pnk upgrade` is a new CLI entry point, so this
increment edits **both**: a `main(["upgrade", "--kb", str(root)])` call in
`tests/free_path_run.py`'s `_run_free_surfaces`, and `pinakes.upgrade` (or whatever the module is
named) in the surface list at `tests/test_paid_path.py:299-314`. Neither
`tools/paid_path_gate.py` nor `.paid-path-allowlist` changes — gates 1 and 2 scan `src/` wholesale.

**Docs:** `docs/CLI.md` — a `## pnk upgrade` section, the row moves out of *Planned — not built
yet*, and the `--kb` row in § Common flags; `docs/STATUS.md`; `docs/GUIDE.md` (a task section:
"adopting a template change"); `docs/VERIFICATION.md`; a `changelog.d/added-pnk-upgrade.md`
fragment. `docs/DESIGN.md` §6.1 **only** to correct F4's unimplementable sentence and drop
"migration" — that is a reasoning change, so it qualifies.

**Mutation targets.** Replace **base** with the KB's manifest and confirm
`::test_a_user_edit_the_template_never_touched_appears_nowhere…` fails. Make the clean/conflict split
always report "clean" and confirm `::test_a_user_edited_region_is_reported_as_a_conflict…` fails.
Drop the uniqueness requirement from the placement predicate (first match wins) and confirm
`::test_a_hunk_whose_context_matches_twice_is_a_conflict` fails **and** that the reordered-manifest
test fails too — if only one goes red, the other is asserting something weaker than it claims.
Collapse *already applied* into *clean* and confirm
`::test_a_hunk_already_present_in_theirs_is_reported_as_already_applied` fails.
Open the manifest for writing and confirm `::test_nothing_under_the_kb_is_written` fails.

---

### T4 — `pnk upgrade --apply`

**Depends on T3.** D-1 is settled as B by implication of D-10 and D-11 (both taken 20260804), so
this increment is in scope. If the planner overrules D-1 and stops at T3, T4 does not exist and the
release is T1–T3 + T7 — and D-10 and D-11 become moot rather than wrong.

**What lands.** `--apply` writes the **cleanly-applying hunks only**, after printing everything T3
prints. Rules, all testable:

- **Decides everything before it writes anything.** Hunk classification and the conflict check run
  over in-memory text; the first byte reaches the filesystem only once the command has committed to
  writing. **So a refusal provably leaves no `pinakes.toml.orig` behind** — which is a testable
  consequence, not an implementation detail, because a `.orig` left by a refused run makes the
  *next* run refuse on the `.orig` rule instead of on its real reason. **It is also half of the
  consent path D-10 rests on**: everything the user is shown is decided before anything is written,
  so the print cannot describe a different file from the one that lands.
- **Refuses outright if any hunk conflicts.** It never merges, never picks a side, never writes a
  conflict marker. The message **names the conflicting region** — the table and the first context
  line — and says to edit by hand. *Already applied* hunks are not conflicts and do not trigger this;
  they are skipped, counted, and named in the output.
- **✅ A `[budget]` hunk applies like any other hunk — D-10, taken 20260804.** The applier gets **no
  `[budget]` predicate**, no exclusion, no second flag. A later reader who adds one has reversed a
  decision, not tightened a rule.

  **What replaces the exclusion is the consent path, and it is three build requirements, not a
  disposition.** Each is a deliverable of this increment with its own test and its own exit
  criterion:

  1. **A money change is printed under its own labelled heading, naming every changed key with both
     values.** Not a `+`/`-` pair a reader has to find inside a unified diff: a heading whose text
     says a spending cap is changing, then `per_operation_eur: 0.05 → 0.30` and
     `monthly_eur: 5.00 → 30.00`, one line each. The heading is printed by **`pnk upgrade` and by
     `pnk upgrade --apply`** — the report is where a user decides, and it must not be the weaker of
     the two outputs.
  2. **The heading appears exactly when `--apply` would write a `[budget]` change, and never
     otherwise — one predicate, identical in both commands.** Under the all-or-nothing conflict
     rule that resolves to: *at least one hunk classified **clean** falls inside `[budget]`, **and**
     no hunk conflicts.* Spelling it out matters because three near-misses each announce a money
     change that is not happening, which trains a user to skip the one heading that must be read:
     an **already applied** budget hunk (the KB already has the value), a **conflicting** run
     (nothing is written at all, budget included), and a bump that touches no `[budget]` line.
     Its absence in those cases is also what makes requirement 1 testable at all — a heading
     printed unconditionally satisfies every positive assertion about it — so
     `::test_no_budget_heading_when_no_hunk_touches_budget` and its two siblings are the control,
     not a nicety.
  3. **The heading provably precedes the first byte written.** The rule above ("decides everything
     before it writes anything") makes this true of the *decision*; this makes it observable in the
     output stream, so it can be asserted by line position rather than by reading the code.

  **The keys are found structurally, not by name.** "Inside `[budget]`" is a property of the hunk's
  position between the `[budget]` header and the next `^\s*\[` line — the same bounded textual
  predicate the `[kb] template` rewrite uses below. **Do not hardcode `per_operation_eur` and
  `monthly_eur`**: they are today's two, `confirm_above_eur` is a third that exists now, and a
  future template may add a fourth. A name list would print a heading for the two the author
  remembered and stay silent on the rest, which is a consent path that fails exactly when it is
  new information.

  **What this does not do.** It does not spend, and it does not change `.paid-path-allowlist`. A
  raised cap is permission to spend that still requires a paid entry point to be invoked
  deliberately (`CLAUDE.md` § *The free path stays free*). T4 stays on the free path and its
  free-path coverage is a deliverable below.
- **The `--help` text and `docs/CLI.md` describe the write rule as it is: every hunk that applies
  cleanly is written, `[budget]` included.** The previous draft required documenting an exception;
  there is none to document, and inventing softening language ("budget changes are applied with
  care") would misdescribe the command. What the docs *must* carry is requirement 1 — that a money
  change is called out in the printed diff — because that is the behaviour a user relies on.
- **Names what the applied hunks invalidate.** If an applied hunk changes `[embedding] model`,
  `[embedding] dim`, `[embedding] revision`, `[chunking] strategy`, `[chunking] max_tokens` or
  `[chunking] overlap`, the existing `.pinakes/index.db` becomes incoherent and search refuses
  (drift axis 2, `docs/KB-UPDATES.md` §2). `--apply` must **print which applied keys invalidate
  derived state and name `pnk sync --rebuild`.** Refusing to sync (below) without saying so leaves
  the user with exactly the state they cannot search, and `::test_apply_does_not_run_a_sync` would
  otherwise lock that in as correct.
- **Writes `pinakes.toml.orig`** (D-5), refusing if one already exists. Then a rename-atomic write of
  the new manifest. **It prints the `.orig` path and says it is untracked**: `init.py:19-23` writes a
  `.gitignore` covering only `.pinakes/`, so in a KB under git the backup appears in `git status` and
  can be committed by accident. Adding a `.gitignore` line at `init` time would not help any existing
  KB, so the printed line is the mechanism; if the planner prefers, `init`'s `.gitignore` can gain
  the line *as well*, which is a one-line change in T1's blast radius.
- **Re-parses through `manifest.load()` immediately after writing.** On any `ManifestError`, restores
  from `.orig` and re-raises with the original error attached. A valid-TOML-but-invalid-manifest
  result must not survive the command.
- **Reads the sync lock and refuses if it is held — it does not claim it.** `pnk sync` holds
  `src/pinakes/lock.py`'s `SyncLock` as the KB's single writer, and an `--apply` that rewrote
  `pinakes.toml` mid-sync would leave that sync indexing under settings the file no longer states.
  But **claiming the lock would write a file under `.pinakes/`**, which contradicts this command's
  own "never touches `.pinakes/`" rule and its snapshot test. So: `lock.read_holder(root /
  ".pinakes")` — read-only — and refuse with the holder's description if one exists.
  **This is advisory and racy, and the plan says so**: a sync starting one millisecond later is not
  caught. It converts the common case (a sync is running right now) from silent corruption into a
  message, and it does not pretend to be mutual exclusion. If the planner wants real exclusion, that
  is a decision to relax the `.pinakes/` rule for a lock file, not something to slip in here.
- **Updates exactly one key outside the applied hunks: `[kb] template`, set to the installed
  reference.** It is rewritten in place by locating a line matching `^\s*template\s*=` in the text
  **between the `[kb]` header and the next line matching `^\s*\[`**. If there is not exactly one such
  line, **refuse** — do not append one. Guessing where a key belongs in a file the user owns is the
  thing this command exists not to do. Pinned by
  `::test_the_template_key_is_rewritten_only_inside_the_kb_table` with a fixture carrying a
  `template = …` line in a *later* table, which a whole-file regex would corrupt.
  - **This is the one key-level write, and it is why the "no `tomlkit`" claim is not free.** It is
    bounded — one line, one known shape, refusing rather than inventing — and that is the whole
    justification. If the planner would rather take the dependency, `tomlkit` is MIT and
    dependency-free (`docs/KB-UPDATES.md` §5 prices it), and the cost is a row in
    `pyproject.toml`'s core list against `CLAUDE.md`'s core-light rule.
  - **✅ `[kb] requires_pinakes` is never written — D-11, taken 20260804, option A.** `[kb] template`
    above is therefore **the only key `--apply` writes *outside the applied hunks***, and that
    sentence is the whole rule: a reviewer checks it by counting write sites. (The qualifier is not
    pedantry — the hunks themselves change values, `[budget]`'s included under D-10, so "the only
    key it writes" without it is simply false and would read as forbidding the feature.) The
    draft's original rule wrote
    `">=<current pinakes>"`, which contradicts D-6 — the key itself is unreadable by any build
    before 0.6.0, so writing it would make the KB unreadable by 0.5.x in order to record that it
    adopted a comment.

    **What is built instead is the recommendation, printed.** When the applied hunks introduce a key
    the manifest did not have, `--apply` prints a line naming those keys and saying that a KB using
    them may want `[kb] requires_pinakes` set by hand. It does not compute a version floor and does
    not suggest a number: **nothing in the repository maps a manifest key to the release that
    introduced it** (D-11 option C), so a printed `>=x.y.z` would be a guess wearing a decimal
    point. Name the keys; let the user decide the floor.

    **The operands are the part that is easy to get wrong, and they survive the decision.** The key
    set is `parse(base + applied hunks) − parse(base)`, **not** `parse(ours) − parse(base)` — hunks
    that conflicted were not applied, so a key they carried is not in the file and must not appear
    in the recommendation. **Today this set is always empty** (F2: no template change has ever added
    a key), which is why the negative test below is the load-bearing one.

    **An existing `requires_pinakes` is not touched, in either direction** — not raised, not
    lowered, not reformatted. It is a key the user owns and `--apply` has no opinion about it.
- **Never touches `docs/`, never touches `.pinakes/`, never re-chunks, re-embeds or re-extracts.** A
  changed `include` means new documents exist to index and that is `pnk sync`'s job, invoked
  separately (`docs/KB-UPDATES.md` §5).
- **Never renumbers or regenerates a ULID.**

**Amendments this increment forces, and they are not optional.**

* `src/pinakes/manifest.py:3-5` states *"Nothing in Pinakes rewrites it after `pnk init`, so this
  module only ever reads."* The second half stays true — the writer lives in the new module, not in
  `manifest.py` — but the first half becomes false and must be rewritten in the same commit.
* `docs/DESIGN.md` §2.1 gains the exception, stated as narrowly as the two existing sidecar
  exceptions in `CLAUDE.md`: *a user-invoked upgrade command writes the KB's own `pinakes.toml`,
  after printing the change, and only hunks that apply cleanly.*
* **Propose to the planner** a `CLAUDE.md` amendment under *Invariants*: the manifest is user-owned
  and Pinakes writes it in exactly one place. Without it the rule lives only in DESIGN and the next
  agent has no reason to look there. **Propose the D-10 half of it in the same breath** — that this
  one write may change `[budget]` values, and that what makes it acceptable is the printed diff and
  the separate `--apply`. `CLAUDE.md`'s budget section is otherwise entirely about the ledger and
  the paid-path allowlist, so a reader who finds a command that moves a cap has nothing there to
  tell them it was decided rather than overlooked. **This is a proposal in the commit message, never
  an edit** (`CLAUDE.md` § *Documentation has one owner*).

**Tests** — `tests/test_cli_upgrade.py`:

`::test_apply_writes_only_the_cleanly_applying_hunks`;
`::test_apply_refuses_entirely_when_any_hunk_conflicts` — asserts the manifest is byte-identical
afterwards, **that the message names the conflicting region**, and **that no `pinakes.toml.orig`
exists**. All three: a refusal that wrote a backup would make the next run refuse on the `.orig`
rule instead of on the conflict, which is a non-zero exit delivered by the wrong guard;
`::test_apply_leaves_an_orig_and_refuses_to_overwrite_an_existing_one`;
`::test_apply_prints_that_the_orig_is_untracked`;
`::test_apply_refuses_while_the_sync_lock_is_held` — names the holder, **and asserts nothing was
written under `.pinakes/`**, because the point of reading rather than claiming the lock is that the
check itself leaves no trace;
`::test_a_write_that_produces_an_unloadable_manifest_is_rolled_back` — inject a failure by
monkeypatching `manifest.load` to raise, assert the on-disk file is byte-identical to the pre-write
bytes and the exit code is non-zero;
`::test_the_template_key_is_rewritten_only_inside_the_kb_table` — fixture with a `template = …` line
in a later table; a whole-file regex corrupts it and this test is the only thing that notices;
**Four tests for D-10's consent path, and they only work as a set** — each of the first three is
satisfiable by something other than the property it names unless the fourth is there too:

`::test_a_budget_hunk_is_applied_like_any_other_hunk` — the taken rule. A synthetic bump moves a
`[budget]` value; assert the manifest carries the **new** value afterwards. Assert the *value*, not
the key's presence: `per_operation_eur` is in every manifest ever written;
`::test_a_budget_change_is_printed_with_both_values` — assert the **old** value and the **new** value
both appear in the output, under a heading that names spending. **What the old value rules out, and
what it does not**: it rules out an implementation that prints only the resulting state, only the new
value, or a bare list of changed keys. It does **not** rule out writing before printing — the
base→ours diff carries the old value whenever it is printed — and claiming otherwise would be this
project's recurring defect committed inside the test meant to prevent it. Ordering is the next
test's job. Assert this for **both** `pnk upgrade` and `pnk upgrade --apply`, because the report is
where the user decides;
`::test_the_budget_heading_precedes_the_first_write` — capture the `--apply` output as an ordered
sequence and assert the heading's index is **lower** than the index of the line reporting the write
(and of the `.orig` path line). Ordering, not membership: "both strings appear" is true of an
implementation that writes first and explains afterwards;
`::test_no_budget_heading_when_no_hunk_touches_budget` — **the one that makes the other three
mean anything.** A synthetic bump that changes only `[retrieval]`; assert the heading and the word
naming spending are **absent**. Without it, a heading printed unconditionally passes all three
positives, which is this project's recurring defect shape with money attached. **Two siblings, per
requirement 2**: `::test_no_budget_heading_when_the_budget_hunk_is_already_applied` and
`::test_no_budget_heading_when_the_run_refuses_on_a_conflict` — in both, no money moves, and a
heading that appeared anyway would be announcing a change that is not happening;
`::test_apply_names_the_rebuild_when_an_applied_hunk_changes_an_index_invalidating_key` — a synthetic
template whose bump moves `[chunking] max_tokens`; assert the output contains `pnk sync --rebuild`
and the key's name;
`::test_requires_pinakes_is_never_written` — **D-11's rule in its strongest form, and it is the
easier half to get right.** Run `--apply` over a synthetic bump that *does* add a manifest key, and
assert `requires_pinakes` is absent from the file afterwards. Assert absence from the **file**, not
from the diff: a write that appended the key outside every hunk is exactly what this forbids;
`::test_a_key_adding_hunk_prints_a_requires_pinakes_recommendation` — the positive half. Assert the
printed line **names the added key**, not merely that the string `requires_pinakes` appears — the
word is in `docs/MANIFEST.md`, in `--help` and plausibly in the diff itself, so its presence alone
discriminates nothing;
`::test_no_recommendation_when_no_applied_hunk_adds_a_key` — the negative control, and today it is
the *only* reachable case against a real template (F2: no template change has ever added a key). A
synthetic bump that changes a value only; assert no recommendation is printed;
`::test_a_key_carried_only_by_a_conflicting_hunk_is_not_recommended` — the operand test. The key set
is `parse(base + applied hunks) − parse(base)`, and the natural wrong implementation
(`parse(ours) − parse(base)`) passes both tests above and fails only this one;
`::test_an_existing_requires_pinakes_is_left_byte_identical` — in both directions: a floor higher
than the running build and one lower than it;
`::test_apply_writes_nothing_under_docs_or_pinakes_state` — snapshot both trees;
`::test_apply_does_not_run_a_sync` — assert no `.pinakes/index.db` appears and no existing one's mtime
moves. **This test is only honest alongside the rebuild-naming test above**; on its own it pins the
state a user cannot search;
`::test_the_comment_the_template_added_is_present_after_apply` — the end-to-end case that proves the
mechanism addresses the drift that exists. **Assert the PDF-glob comment line by content**
(`# Add "**/*.pdf" to \`include\` above to index PDFs`), never a line count. A key-level
implementation fails it, which is the point.

**Exit criteria.**

✅ **D-2b (taken) makes every positive path unreachable from `notes`** — one archived version, so no
diff exists — and the previous draft's blocks, which rendered `_versions/1.0/` of `notes`, would now
fail on a version that is deliberately never archived. **They are replaced, not weakened.** The
positive paths run against a **synthetic two-version template** built in a scratch copy of the
package, which is executable in a shell and not merely in pytest.

> **The mechanism, verified at `d06ef7e` with today's code.** A copy of `src/pinakes` placed on
> `PYTHONPATH` takes precedence over the editable install, for the `pnk` console script as well as
> for `python3 -c`:
>
> ```
> $ cp -R src/pinakes /tmp/t4pkg/pinakes
> $ PYTHONPATH=/tmp/t4pkg uv run --frozen python3 -c 'import pinakes; print(pinakes.__file__)'
> /tmp/t4pkg/pinakes/__init__.py
> $ PYTHONPATH=/tmp/t4pkg uv run --frozen pnk init /tmp/t4demo --template demo
> $ grep '^template' /tmp/t4demo/pinakes.toml
> template = "demo@9.9"
> ```
>
> **This is the whole reason a synthetic template does not go in the repository**: a second template
> under `src/` gets committed by accident, ships in the wheel, and fails T1's drift gate for having
> no archive.
>
> **The fixture script below was also run at `d06ef7e`** (with the `content_hash` line removed,
> since T1 has not landed). It builds, and `diff` between the two archived `.j2` files gives
> **exactly the shape M3 measured**: a pure addition at the PDF-glob comment line, and the two
> `[budget]` values. `pnk init --template demo` then stamped `template = "demo@1.1"`.
>
> What is *unrun* is everything T1–T4 add — `render_archived`, `render_context`, `pnk upgrade`, the
> gate's `content_hash`. The scaffolding is real and measured; the commands over it are predictions,
> and they are marked as such.

```bash
# ---- fixture: a synthetic template with TWO archived versions -------------------------------
# Run from the repository root. Nothing here writes into the repository.
set -e
rm -rf /tmp/t4pkg /tmp/t4kb /tmp/t4kb2 && mkdir -p /tmp/t4pkg
cp -R src/pinakes /tmp/t4pkg/pinakes
uv run --frozen python3 - <<'PY'
import pathlib, shutil, sys
sys.path.insert(0, "tools")
from template_drift_gate import content_hash   # T1's OWN hash. Never re-implement it here, or the
                                               # fixture and the gate drift and the gate wins.
tpl  = pathlib.Path("/tmp/t4pkg/pinakes/templates")
demo = tpl / "demo"
shutil.copytree(pathlib.Path("src/pinakes/templates/notes"), demo)  # start from a real template,
shutil.rmtree(demo / "_versions", ignore_errors=True)               # so it renders
demo.joinpath("template.toml").write_text(
    'name = "demo"\nversion = "1.1"\ndescription = "synthetic, for T4"\n', encoding="utf-8")

# 1.1 == the live files. 1.0 == the same, minus the PDF-glob comment line and with the OLD caps.
# That makes exactly two hunks: one PURE ADDITION (the comment) and one value change in [budget] —
# which is the shape of the real drift M3 measured, reproduced where it can be diffed.
new = demo.joinpath("pinakes.toml.j2").read_text(encoding="utf-8")
old = (new.replace("per_operation_eur = 0.30", "per_operation_eur = 0.05")
          .replace("monthly_eur       = 30.00", "monthly_eur       = 5.00"))
old = "".join(l for l in old.splitlines(keepends=True) if '**/*.pdf' not in l)
for version, body in (("1.0", old), ("1.1", new)):
    d = demo / "_versions" / version
    shutil.copytree(demo, d, ignore=shutil.ignore_patterns("_versions"))
    d.joinpath("pinakes.toml.j2").write_text(body, encoding="utf-8")
    d.joinpath("template.toml").write_text(
        f'name = "demo"\nversion = "{version}"\ndescription = "synthetic, for T4"\n',
        encoding="utf-8")
ledger = tpl / "_versions.toml"
ledger.write_text(ledger.read_text(encoding="utf-8") + "".join(
    f'\n[[template]]\nname = "demo"\nversion = "{v}"\nsha256 = "{content_hash(demo / "_versions" / v)}"\n'
    for v in ("1.0", "1.1")), encoding="utf-8")   # shape follows T1's ledger; match it exactly
print("fixture built")
PY

# a KB stamped from 1.0, with 1.0's CONTENT — not today's content relabelled.
# ⚠ Relabelling alone is the trap: `theirs` would already equal `ours`, every hunk would report
# *already applied*, `--apply` would write nothing, and the greps below would pass because the
# strings were there all along. So the manifest is rendered from the archived base:
PYTHONPATH=/tmp/t4pkg uv run --frozen pnk init /tmp/t4kb --template demo
sed -i '' 's/^template = .*/template = "demo@1.0"/' /tmp/t4kb/pinakes.toml
PYTHONPATH=/tmp/t4pkg uv run --frozen python3 - <<'PY'
import pathlib
from pinakes import manifest, template
root = pathlib.Path("/tmp/t4kb")
root.joinpath("pinakes.toml").write_text(
    template.render_archived("demo", "1.0", template.render_context(manifest.load(root))),
    encoding="utf-8")
PY
# the fixture's two preconditions, asserted rather than assumed — if either fails, every assertion
# after it is satisfied by the starting state instead of by the command:
! grep -qF '# Add "**/*.pdf"' /tmp/t4kb/pinakes.toml
grep -qF 'per_operation_eur = 0.05' /tmp/t4kb/pinakes.toml
```

```bash
# ---- (1) D-10's consent path: the report shows the money change and writes NOTHING ------------
cp /tmp/t4kb/pinakes.toml /tmp/t4kb.before
rc=0; PYTHONPATH=/tmp/t4pkg uv run --frozen pnk upgrade --kb /tmp/t4kb >/tmp/t4report.out 2>&1 || rc=$?
[ "$rc" -eq 0 ]                                     # a diff exists and is a report, not a refusal
diff -q /tmp/t4kb.before /tmp/t4kb/pinakes.toml    # the report is print-only. This is half of
                                                    # consent: the user sees it before choosing.
# BOTH values, and the OLD one is the discriminator. Measured at d06ef7e: `0.05` occurs ZERO times
# in a manifest rendered from today's template, so it can only reach this output from the base
# side of the comparison. It rules out an implementation that printed only the resulting state, or
# only the new value, or a bare list of changed keys. **It does NOT rule out write-before-print** —
# the base→ours diff carries `0.05` whenever it is printed. Ordering is block (2)'s job, and
# conflating the two is how a consent assertion ends up proving nothing about consent:
grep -qF '0.05' /tmp/t4report.out
grep -qF '0.30' /tmp/t4report.out
grep -qF '5.00' /tmp/t4report.out
grep -qF '30.00' /tmp/t4report.out
# …and the heading that says what those numbers are. ⚠ THIS ONE DOES NOT DISCRIMINATE on its own:
# the word `budget` is in the diff's own `[budget]` table header, so it is a smoke check, not the
# assertion. What discriminates is the negative control — a bump touching no [budget] line must
# print no heading — and that is `::test_no_budget_heading_when_no_hunk_touches_budget`, run in
# block (4). Replace the pattern with the exact heading text once it is written:
grep -qiE 'budget|spending cap' /tmp/t4report.out
```

```bash
# ---- (2) --apply: the numbers are printed BEFORE the first byte is written --------------------
rc=0
PYTHONPATH=/tmp/t4pkg uv run --frozen pnk upgrade --kb /tmp/t4kb --apply >/tmp/t4apply.out 2>&1 || rc=$?
[ "$rc" -eq 0 ]
# Ordering by line position, not membership: "both strings appear" is equally true of an
# implementation that writes first and explains afterwards. (Shape verified at d06ef7e on a
# hand-made file: `grep -n … | head -1 | cut -d: -f1` twice, then a numeric compare.)
#
# The write anchor is the `.orig` path, NOT a word like "wrote"/"applied": `applied` also occurs in
# the *already applied* outcome and plausibly in prose, so anchoring on it makes the comparison
# fire against whichever line happened to use the word first. `pinakes.toml.orig` is printed only
# when a backup is written, which is the moment the write begins.
shown=$(grep -nF '0.05' /tmp/t4apply.out | head -1 | cut -d: -f1)
wrote=$(grep -nF 'pinakes.toml.orig' /tmp/t4apply.out | head -1 | cut -d: -f1)
[ -n "$shown" ] && [ -n "$wrote" ] || { echo "a line is missing — the criterion is VOID"; exit 1; }
[ "$shown" -lt "$wrote" ] || { echo "the write was announced before the numbers"; exit 1; }
echo "the old cap was shown before the write began"

# the write itself — D-10 B: the cap DID move, which is the decision, stated as an assertion
grep -qF 'per_operation_eur = 0.30' /tmp/t4kb/pinakes.toml
grep -qF 'monthly_eur       = 30.00' /tmp/t4kb/pinakes.toml
# `-F`, not a regex: the string contains `*`, `.` and backticks, and a BRE spelling of it is a
# second thing to get wrong.
grep -qF '# Add "**/*.pdf" to `include` above to index PDFs' /tmp/t4kb/pinakes.toml
# D-11 A: never written, in any case. (`grep -c … # 0` would exit 1 and abort the block.)
! grep -q 'requires_pinakes' /tmp/t4kb/pinakes.toml
# the recovery half of consent: the backup must hold the OLD caps, or it is a copy of the new file
test -f /tmp/t4kb/pinakes.toml.orig
grep -qF 'per_operation_eur = 0.05' /tmp/t4kb/pinakes.toml.orig
# (its path was printed — already established: `$wrote` above is non-empty)
PYTHONPATH=/tmp/t4pkg uv run --frozen pnk doctor --kb /tmp/t4kb | grep '^OK   template'
#                                            ^ never the exit code: it is 1 for the absent [st] extra
```

```bash
# ---- (3) the conflicting case, on its own fresh KB -------------------------------------------
# Never a re-run of (2), whose `--apply` left a `pinakes.toml.orig`: a second run there refuses on
# the `.orig` rule, not on the conflict — a non-zero exit from the wrong guard.
PYTHONPATH=/tmp/t4pkg uv run --frozen pnk init /tmp/t4kb2 --template demo
sed -i '' 's/^template = .*/template = "demo@1.0"/' /tmp/t4kb2/pinakes.toml
PYTHONPATH=/tmp/t4pkg uv run --frozen python3 - <<'PY'
import pathlib
from pinakes import manifest, template
root = pathlib.Path("/tmp/t4kb2")
root.joinpath("pinakes.toml").write_text(
    template.render_archived("demo", "1.0", template.render_context(manifest.load(root))),
    encoding="utf-8")
PY
# a user edit inside the region the template changed. `exclude` is the line immediately above the
# added comment (pinakes.toml.j2:10-11 at d06ef7e), so it is a context line of that hunk —
# re-check that with `grep -n` before trusting this step.
sed -i '' 's|^exclude = .*|exclude = ["**/drafts/**"]  # mine|' /tmp/t4kb2/pinakes.toml
cp /tmp/t4kb2/pinakes.toml /tmp/t4kb2.before
# redirect rather than pipe: after a pipeline `$?` is the *last* command's status, and
# `PIPESTATUS`/`pipestatus` spell differently in bash and zsh
rc=0
PYTHONPATH=/tmp/t4pkg uv run --frozen pnk upgrade --kb /tmp/t4kb2 --apply >/tmp/t4kb2.out 2>&1 || rc=$?
[ "$rc" -ne 0 ]
cat /tmp/t4kb2.out
# The conflict message must NAME the region — and the two strings must be on the SAME line.
# `grep -qi conflict && grep -qF '[sources]'` is satisfied by a bare "conflict" plus the diff's own
# `[sources]` hunk header, which is printed anyway: two true greps and nothing established.
grep -i 'conflict' /tmp/t4kb2.out | grep -qF '[sources]'
diff /tmp/t4kb2.before /tmp/t4kb2/pinakes.toml && echo "refused without writing"
! test -e /tmp/t4kb2/pinakes.toml.orig && echo "refusal left no backup behind"
# ⚠ The [budget] hunk in this fixture applies cleanly. D-10 B has no exception, and the conflict
# rule is all-or-nothing, so the correct outcome is that the budget change is NOT written either:
grep -qF 'per_operation_eur = 0.05' /tmp/t4kb2/pinakes.toml
# …and no money heading, because no money moved (requirement 2). Fill in the EXACT heading text;
# do not use the word `budget` here — the diff prints `[budget]` anyway, so a negative assertion on
# it fails for a reason that has nothing to do with the heading:
# ! grep -qiF '<the exact heading text>' /tmp/t4kb2.out
```

```bash
# ---- (4) the paths no fixture above reaches, and the shipped template's own outcome ------------
# The negative controls (no budget heading, no recommendation) and the operand test are pytest's.
# `-k` can select nothing and still read as green: measured at d001175, `-k containment` printed
# "no tests collected (1288 deselected)" and exited 5. So assert the collected count.
rc=0; uv run --frozen pytest -q tests/test_cli_upgrade.py \
  -k 'budget or requires_pinakes or rollback or lock' >/tmp/t4pytest.out 2>&1 || rc=$?
cat /tmp/t4pytest.out
grep -qE '^[1-9][0-9]* passed' /tmp/t4pytest.out
[ "$rc" -eq 0 ]

# and what a real user gets on a real KB today: the cannot-compare refusal, writing nothing.
rm -rf /tmp/t4real && uv run --frozen pnk init /tmp/t4real
sed -i '' 's/^template = .*/template = "notes@1.0"/' /tmp/t4real/pinakes.toml
cp /tmp/t4real/pinakes.toml /tmp/t4real.before
rc=0; uv run --frozen pnk upgrade --kb /tmp/t4real --apply >/tmp/t4real.out 2>&1 || rc=$?
echo "cannot-compare exit code under --apply: $rc"   # recorded, not asserted — O-2
grep -qiF 'cannot compare' /tmp/t4real.out
diff -q /tmp/t4real.before /tmp/t4real/pinakes.toml
! test -e /tmp/t4real/pinakes.toml.orig
./check.sh
```

**Why the message assertion and not the exit code.** A non-zero exit here is available from at least
four guards — the conflict, an existing `.orig`, a held sync lock, and *cannot compare* — and three
of them would be the *wrong* reason for a criterion that claims to test conflict refusal. The exit
code is checked as well, but it is the message that says which guard fired.

**One thing these blocks cannot check, stated rather than faked.** They exercise the fixture's own
`[budget]` hunk, which was *constructed* to look like M3's. They do **not** prove the shipped
`notes` will ever produce one, because under D-2b nothing shipped can be diffed until the next
template bump. The first real `[budget]` hunk a user sees will be the one after that bump, and it
should be re-run through block (1) by hand at that time.

**Docs:** `docs/CLI.md` § `pnk upgrade` — **`--apply` writes every cleanly-applying hunk, `[budget]`
included (D-10), and a money change is called out in the printed diff**; the exit code for a refused
conflict and for *cannot compare* (O-2); the `--kb` row in § Common flags. `docs/MANIFEST.md`
(`requires_pinakes` — **that nothing in Pinakes ever writes it**, and that `--apply` only recommends
it, per D-11); `docs/DESIGN.md` §2.1 and §6.1; `docs/GUIDE.md` — the "adopting a template change"
task **must show the report step before the `--apply` step**, because the consent path is a
documented workflow and not only an implementation property; `docs/STATUS.md`;
`docs/VERIFICATION.md`; `changelog.d/`; a `retro.d/` fragment — **the durable lesson is F2 as
re-measured: the unit of template drift is the rendered text, not the key set; a design note
proposed a key-level remedy for a drift history that contains no key change at all; and a plan
asserted "zero values changed" over a history that changed two, one of them a spending cap.**

**`docs/KB-UPDATES.md` §8 contradicts D-11 and must be proposed for correction** (planner-owned, per
`CLAUDE.md`): it names `pnk upgrade --apply` as the thing that raises `requires_pinakes`, and after
D-11 nothing raises it. Propose the correction in this increment's commit message with a
`git diff <sha> -- docs/KB-UPDATES.md`; do not edit it.

**Free-path coverage.** `--apply` is a flag on an existing entry point, so `tests/free_path_run.py`
needs no *second* call — but the run must exercise the flag, not only the report. Add the
`--apply` invocation on a throwaway KB inside `_run_free_surfaces`, or state why the report path
alone is sufficient coverage. Do not leave it unsaid. **Say in the comment what that call actually
reaches**: a KB built by `pnk init` in that run records the installed reference, so `--apply` takes
the *up to date* path and writes nothing. It proves the flag imports and parses on the free path,
which is what the gate is for; it does **not** exercise the writer, and a later reader who assumes
it does will delete a test that matters.

**Mutation targets.** Remove the conflict refusal and confirm
`::test_apply_refuses_entirely_when_any_hunk_conflicts` fails. Move the `.orig` write ahead of the
conflict check and confirm that same test fails on the **no-`.orig`** assertion specifically — if it
fails on the byte-identity assertion instead, the ordering is not what is being pinned. Remove the
re-parse and confirm `::test_a_write_that_produces_an_unloadable_manifest_is_rolled_back` fails.
Drop the rebuild-naming line and confirm its test fails while `::test_apply_does_not_run_a_sync`
stays green — that pair is the whole point of finding it. Replace the hunk applier with a key-level
writer and confirm `::test_the_comment_the_template_added_is_present_after_apply` fails.

**D-10's four mutants, and each names what must *not* also fail** — that is where a consent-path
assertion usually turns out to be measuring something else:

* **Suppress the `[budget]` heading entirely.** `::test_a_budget_change_is_printed_with_both_values`
  and `::test_the_budget_heading_precedes_the_first_write` fail;
  `::test_a_budget_hunk_is_applied_like_any_other_hunk` **stays green** — the write is not what the
  heading tests are about, and if it goes red they are entangled.
* **Print the heading unconditionally**, for every upgrade. **Only**
  `::test_no_budget_heading_when_no_hunk_touches_budget` fails. If nothing fails, the negative
  control is not doing its job and the three positive tests are decorative.
* **Print the new value only** (drop the old one from the heading).
  `::test_a_budget_change_is_printed_with_both_values` fails on the *old* value's absence
  specifically — check the assertion that fired, because a test that passed on `0.30` alone would
  survive this mutant and still claim to prove consent.
* **Move the write ahead of all printing.** `::test_the_budget_heading_precedes_the_first_write`
  fails; the both-values test **stays green**, which is exactly why ordering needs its own test —
  membership assertions cannot see it.

**D-11's two mutants.** Write `requires_pinakes` with the running build's version and confirm
`::test_requires_pinakes_is_never_written` fails. Compute the recommendation as
`parse(ours) − parse(base)` and confirm **only**
`::test_a_key_carried_only_by_a_conflicting_hunk_is_not_recommended` fails — the other three
`requires_pinakes` tests pass under the wrong operands, which is what makes that one load-bearing.

---

### T5 — `vector_tier = "sqlite-vec"` stops lying

**Depends on nothing.** Standalone; ship it whenever the tree is free.

**✅ It ships as a PATCH with the break stated — D-12, taken 20260804.** The draft previously said
"PATCH" in one place, "MINOR or a clearly-stated PATCH" in another, and "the planner should take it"
in a third; that wobble is removed and the type is stated here and in D-12 and nowhere else. The
precedent is this project's own: **0.7.1** shipped a change that hard-errors on a manifest which
previously loaded, because the previous behaviour was the defect — and a manifest saying
`vector_tier = "sqlite-vec"` was never getting `sqlite-vec`.

**Three obligations the PATCH carries, and they are the whole reason it is defensible:**

1. **The CHANGELOG entry states the break in its own words** — the value that is refused, that a KB
   setting it stops loading *entirely* (every command, not only search), and the one-line fix
   (`vector_tier = "auto"`). It goes under `### Changed` or `### Fixed` with the break called out in
   the first sentence, never buried in a trailing clause.
2. **The refusal message names the accepted tiers**, so the fix is in the error the user actually
   sees — pinned by the exit criteria below.
3. **The check is never softened to make the PATCH feel smaller.** If the break is judged too large
   for a PATCH, the answer is D-4 option D (warn first, refuse in a later increment), not a warning
   that pretends to be a refusal. D-12 fixes the *type*; D-4 fixes the *timing*, and it is still
   open.

**Do not restate the release type anywhere else**, and do not write a version number for it: the
release it lands in is numbered when it is cut (`CLAUDE.md`, *unbuilt work is named, never
numbered*).

**What lands.** Per D-4 option A: `manifest.VECTOR_TIERS` becomes `("auto", "numpy")`, and a manifest
saying `sqlite-vec` raises a `ManifestError` naming the tier that is built and pointing at
`docs/STATUS.md`. `manifest.py:48` gains a comment saying the value is restored by the increment that
builds the tier, so the removal is not read as a decision against it.

**And the second half, which is the reason this is not a one-line change.** `sync.py:971` writes the
literal `"numpy"` into `meta` while `manifest.retrieval.vector_tier` is a parsed field nothing
consumes. Replace the literal with the tier actually used, resolved by one function
(`search.resolve_tier(manifest)`) that both `sync` and `search` call, so `meta`'s claim and the code
path cannot disagree. Today they cannot disagree only because there is one tier — which is a fact
about the corpus of tiers, not a property.

**Tests** — `tests/test_manifest.py`, `tests/test_search.py`:

`::test_an_unbuilt_vector_tier_is_refused_with_the_tier_that_is_built`;
`::test_the_manifest_error_names_docs_status`;
`::test_the_index_records_the_tier_that_ran` — **and here the plan has to admit something rather
than dress it up.** The draft's version of this test read `meta["vector_tier"]` after a sync and
asserted it equalled `resolve_tier(manifest)`'s return, *rejecting* `== "numpy"` on the grounds that
the literal "would pass under a build where the resolver was deleted". That is true, and the
replacement is worse: **both sides of the assertion are the same function**, so it holds even when
`resolve_tier` returns the wrong tier. It is a tautology introduced in the increment whose purpose
is to remove one. What the test actually does, in two parts:

  1. **assert `meta["vector_tier"] == "numpy"`** for the shipped case — the concrete fact, which is
     what a reader can check;
  2. **assert that `meta` follows the resolver**, by injecting a resolver that returns a different
     string (monkeypatch `search.resolve_tier`) and asserting `meta` changes with it. *This* is the
     part that fails when `sync.py` re-hardcodes the literal, and it is the only discriminating
     comparison available.

  **With exactly one real tier there is nothing else to discriminate**, and part 2 is a test against
  an injected value rather than against a second tier. Say so in the test's docstring. The real
  version of this property arrives in T6, where two tiers exist; until then the honest claim is
  "`meta` is written from the resolver's return", not "`meta` records the tier that ran".

**Exit criteria.**

```bash
rm -rf /tmp/t5kb && uv run --frozen pnk init /tmp/t5kb
sed -i '' 's/^vector_tier .*= .*/vector_tier           = "sqlite-vec"/' /tmp/t5kb/pinakes.toml
# `pnk doctor` already exits 1 on this repo's default sync (two FAIL lines for the absent [st]
# extra), so the exit code proves nothing here. Assert the message. Today's text is
# "`vector_tier` must be one of 'auto', 'numpy', 'sqlite-vec', found 'bogus'" — after T5 the
# accepted list must no longer contain sqlite-vec:
uv run --frozen pnk doctor --kb /tmp/t5kb 2>&1 | tee /tmp/t5.err
grep -q "must be one of 'auto', 'numpy'" /tmp/t5.err
# The trailing comma is the discriminator, not a typo: today the message reads
#   "must be one of 'auto', 'numpy', 'sqlite-vec', found 'bogus'"   ← sqlite-vec IS comma-followed
# after T5 it must read
#   "must be one of 'auto', 'numpy', found 'sqlite-vec'"            ← it is not
! grep -q "'sqlite-vec'," /tmp/t5.err          # the refused value is not in the accepted list
grep -q 'docs/STATUS.md' /tmp/t5.err            # and it points somewhere
# and the honest half. On a `[light]` dev install `provider` must be switched first, or `sync`
# fails on the missing sentence-transformers backend (docs/STATUS.md § the [light] caveat):
sed -i '' 's/^vector_tier .*= .*/vector_tier           = "auto"/' /tmp/t5kb/pinakes.toml
sed -i '' 's/^provider = "sentence-transformers"/provider = "fastembed"/' /tmp/t5kb/pinakes.toml
mkdir -p /tmp/t5kb/docs && echo "# hello" > /tmp/t5kb/docs/a.md
uv run --frozen --extra light pnk sync --kb /tmp/t5kb
sqlite3 /tmp/t5kb/.pinakes/index.db "select value from meta where key='vector_tier'"   # numpy
./check.sh
```

**The `sqlite3` line is a smoke check, not the assertion, and the plan says which is which.**
`== "numpy"` is true whether the resolver ran or the literal was restored — and, as the test list
above admits, comparing `meta` against `resolve_tier`'s own return is not a fix for that, because
both sides are the same function. The discriminating comparison is the **injected resolver**, and it
lives in the test, not here. Nothing in this block can distinguish a working resolver from a deleted
one; that is a property of having one tier, and it is stated rather than papered over.

**Docs:** `docs/MANIFEST.md:135` — the `vector_tier` row currently reads *"`auto`, `numpy` or
`sqlite-vec`. **Only the NumPy tier is built**"*, which is what makes this a documented value and
therefore a real contract break (D-4, D-12); `docs/STATUS.md`; `docs/DESIGN.md:277`'s *"with
`vector_tier = "numpy"` supported as a config override"* sentence, which currently implies three
settable values; `docs/VERIFICATION.md`; `changelog.d/fixed-*.md`.

**Mutation targets.** Restore `"sqlite-vec"` to `VECTOR_TIERS` and confirm the refusal test fails.
Re-hardcode `"numpy"` in `sync.py` and confirm **part 2** of `::test_the_index_records_the_tier_that_ran`
(the injected resolver) fails while part 1 (`== "numpy"`) stays green — that split is the whole
point, and if part 1 also goes red the injection is not doing what it claims.

---

### T6 — The `sqlite-vec` tier 🚫 gated

**Do not start this increment until its precondition is measured and passed.** The precondition is
stated here so that failing it is a cheap outcome rather than a discovered one — the same ordering
that made the graph release's negative result cost one release instead of a forced rebuild for every
KB in existence (`docs/STATUS.md` § *Can the graph release's gate be reached?*).

**The precondition — a corpus at which the tier's purpose is visible.**

`docs/DESIGN.md:262-264` places the NumPy tier's ceiling at 50k chunks and 77 MB, measured
20260725 13:49. `tests/demo-kb` is ~30 documents. **A tier whose entire claim is bounded memory
above 50k chunks cannot be evaluated on a corpus three orders of magnitude below the threshold.**
Before T6 starts:

1. A reproducible generator produces a ≥ 100k-chunk index (synthetic content is fine; the claim is
   about vectors, not prose). It is a committed tool, not a one-off script, because the numbers must
   be re-runnable when `sqlite-vec` bumps. **Reconcile it with `plans/20260801_0749-realism-corpus.md` before
   writing it**: that plan is already the graph release's blocking critical path and owns corpus
   generation. Two corpus generators in one repository is the shape that produces two answers to the
   same question. If realism-corpus's generator can be parameterised to emit this, do that.
2. Measured on it, and recorded in `docs/STATUS.md` with the date: NumPy-tier resident memory and
   ms/query, `sqlite-vec`-tier resident memory and ms/query, and index file size for both.
3. **The gate, every number stated before the run** — a threshold chosen after seeing the result is
   not a threshold.
   * **Latency:** at ≥ 100k chunks, the `sqlite-vec` tier's ms/query is **≤ 3×** NumPy's.
   * **Memory:** the `sqlite-vec` tier's resident memory is **≤ 200 MB** at 100k×384, against
     NumPy's ~154 MB *for the vectors alone*. **This leg is weaker than it looks and the plan says
     so**: NumPy's resident memory at *n* chunks is arithmetic — `n × dim × 4` bytes, which
     `docs/DESIGN.md:262-264` confirms at 77 MB for 50k×384 — so "materially below NumPy's" is a
     restatement of `sqlite-vec` not holding the array in RAM, which is true by construction. The
     number above is therefore an **absolute ceiling on the vec tier**, not a ratio against a
     quantity nobody needs to measure. An earlier draft left this leg to judgement while insisting
     the latency leg be fixed first; that asymmetry is the hole.
   * If the planner prefers to drop the memory leg entirely as arithmetic, that is defensible —
     what is not defensible is an unquantified "materially below".
4. **The equivalence measurement, which is separate and is the one that can refuse the tier
   outright:** the golden set scored on both tiers over the same index. `CLAUDE.md` — *"Any change to
   chunking, fusion weights, reranking or the confidence signal must be justified by the golden-set
   eval"* — and a vector tier that changes which passages are returned is such a change. Report
   `recall@k`, MRR, rerank precision, false-abstain and false-confidence for both, with the
   before/after in the commit message.

   **The two measurements cannot meet on one corpus, and that is a stated bound, not an oversight.**
   Performance runs on the ≥ 100k-chunk synthetic corpus, which has **no relevance labels** and so
   cannot be scored. Equivalence runs on `tests/demo-kb` (~30 documents), which is three orders of
   magnitude below `auto`'s threshold — **so it must force `vector_tier = "sqlite-vec"`
   explicitly**, never rely on `auto`. Under `auto` a 30-document KB selects NumPy and the
   "comparison" compares NumPy with NumPy: a measurement whose easiest way to pass is to have
   measured nothing. State the forced setting in the result, and state that equivalence is
   established **at demo-kb scale only** — nothing here shows the tiers agree at 100k. Closing that
   gap needs a labelled large corpus, which is `plans/20260801_0749-realism-corpus.md`'s territory, not T6's.

If any of these fails, T6 does not start and the outcome is recorded. That is a legitimate ending.

**What lands, if it starts.**

- A `[vec]` extra — `sqlite-vec` is **never** a core dependency (`pyproject.toml:21-27`; `CLAUDE.md`
  *"Core dependencies stay light"*). Verify its licence and record it, as `plans/20260801_0749-realism-corpus.md`
  does for the RFC text.
- A `vec0` virtual table alongside `embeddings`, and `SCHEMA_VERSION` bumped. **Never a migration** —
  the refusal at `store.py:197-206` and its `pnk sync --rebuild` remedy is the whole mechanism.
- `resolve_tier` (from T5) gains the real decision: `auto` chooses by chunk count against the
  documented threshold; `sqlite-vec` is honoured; the extra's absence is a refusal naming
  `uv add "pinakes[vec]"`, resolved through `importlib.util.find_spec` and **never** by importing the
  module — the same rule `is_backend_installed` follows for paid backends (`CLAUDE.md`).
- `doctor`'s `enable_load_extension` probe (`doctor.py:151-160`) stops being advisory: its remedy
  text loses "(the template release)" and becomes a `FAIL` when the manifest asks for the tier and
  the interpreter cannot load extensions.
- `tools/eval_reproducibility_gate.py` runs under **both** tiers. G1's total ordering on
  `(documents.path, chunks.ordinal)` (`store.py:263-269`) lives in `load_vectors`, which the vec tier
  does not use — so the property G1 established is **not inherited** and must be re-established for
  the new path, with its own row in the reproducibility matrix.

**`SCHEMA_VERSION` collides with the graph release.** `plans/20260729_0256-links-and-graph.md` § G3 says
`schema_version` → **3**. So does this increment if it lands first. **Neither plan may hardcode the
number**: whichever lands first takes 3, the other takes 4, and both must read `store.py:28` at
branch time. `tests/test_store.py:93` (`test_schema_version_is_2_for_i5s_page_and_backend_columns`)
hardcodes 2 and is the tripwire — it will fail, and that is correct.

**Tests** (sketch — this increment's full test list is written when its precondition passes, not
before): `tests/test_store_vec.py::test_the_vec_table_and_the_embeddings_table_agree_on_every_chunk`;
`::test_a_schema_version_mismatch_is_refused_with_the_rebuild_remedy`;
`::test_the_extra_is_probed_with_find_spec_and_never_imported`;
`tests/test_search.py::test_both_tiers_return_the_same_top_k_on_the_demo_kb`;
`tests/test_search_reproducibility.py::test_the_vec_tier_is_reproducible_across_a_rebuild`.

**Docs:** `docs/DESIGN.md` §3, §3.1; `docs/MANIFEST.md`; `docs/GUIDE.md` § Troubleshooting (the “Searches slow past ~50k chunks” row); `docs/STATUS.md`
(including the *Measured numbers* table); `docs/CLI.md`; `docs/VERIFICATION.md`; `changelog.d/`.

**Cross-plan dependency to record before starting.**
`docs/graph/PINAKES_APPROACH.md:196-203` states that under the `sqlite-vec` tier only the vector
scan's top-N carry cosine scores, which is *"precisely the top-k-only seeding HippoRAG 2 warns
against"*, and that all-chunk seeding *"must be re-evaluated on that tier, not assumed."* If T6 ships,
the staged PPR channel's gate acquires a second leg — see `20260804_1016-staged-channel-gates.md` beside this file.

---

### T7 — `pnk templates`, and a template declares its own files

**Depends on T1.** Independent of T3/T4.

> ⚠ **`pnk templates` is a command nobody has decided on.** `grep -rn 'pnk templates' docs/ plans/
> README.md src/` returns nothing at `d001175`, and `docs/CLI.md:398-406`'s *Planned — not built
> yet* table lists only `pnk ask --deep` and `pnk upgrade`. **This increment invents a CLI surface**,
> which is the planner's to accept or reject — flag it as new rather than presenting it as scheduled.
> If it is accepted, `docs/CLI.md`'s planned table gains a row **before** the increment lands, so the
> repository never contains a command with no prior decision record.

**What lands.**

1. `pnk templates` — lists every installed template with its version and description, `--json`
   available. Today `template.available()` (`template.py:49-54`) is reachable only through an error
   message when `pnk init --template` names something that does not exist
   (`template.py:41-45`). A user cannot ask what is installed.
2. `template.toml` gains `files = [...]`, a declared list of what `copy_extras` writes into a KB,
   replacing the hardcoded `("README.md", "eval/questions.yaml")` at `template.py:78`. Absent means
   today's two, so `notes` needs no change and no third-party template breaks.

   **This is where the version archive becomes reachable from a template's own declaration, and the
   rule lands here rather than in T1.** T1 has no way to write a test that fails: `copy_extras`
   iterates a hardcoded tuple, so no `_versions/` path is reachable whatever the archive contains,
   and an assertion there is satisfied by the hardcoding rather than by any rule. The moment
   `files = [...]` is read from `template.toml`, a template *can* declare `_versions/1.0/README.md`
   — and T7's containment check would pass it, because it lands **inside** the target. Containment is
   the wrong instrument for this: it validates escape, not provenance. **So the `files` validator
   additionally refuses any entry with `_versions` as a path component**, with
   `::test_a_files_entry_naming_the_version_archive_is_refused` declaring one and asserting the
   refusal. Without this the property T1 appeared to hold is silently lost in the increment after it.
3. Each entry is validated to land inside the target KB. **The predicate is not re-derived**, for the
   reason `plans/20260731_2128-source-walk-containment.md` gives: four attempts at it each got it wrong
   differently. But it also cannot simply be *called* — `manifest._check_include_containment`
   (`manifest.py:479-571`) is module-private, takes a `SourcesSection` and raises a `ManifestError`,
   and its glob-specific parts (dropping `**`, the `probe.name == ".."` exemption) do not apply to a
   literal relative path. **So: extract the landing test into one shared helper** —
   `paths.lands_inside(anchor: Path, base: Path, relative: str) -> bool`, implementing
   `probe.parent.resolve() / probe.name` with the `..` final-component exemption — and have
   `_check_include_containment` and `copy_extras` both call it. One predicate, two callers, and the
   existing containment tests keep passing unchanged (which is the check that the extraction was
   behaviour-preserving).

   A template is packaged data, but `pnk init --template` can name a template a user installed from
   elsewhere, so the input is not trusted.

**Why this is in the release at all.** It is the smallest thing that makes "more than one template"
a usable state rather than a code path — and it removes the hardcoded list that D-7 option B would
otherwise have had to edit.

**Tests** — `tests/test_init.py`, `tests/test_cli.py`:

`::test_pnk_templates_lists_notes_with_its_version`;
`::test_pnk_templates_json_matches_the_human_output`;
`::test_a_declared_file_list_is_copied_and_an_undeclared_file_is_not` — build a temporary template
with three files and declare two;
`::test_a_files_entry_naming_the_version_archive_is_refused` — the property moved here from T1,
where it could not fail. Declare `_versions/1.0/README.md` in a temporary template's `files` and
assert the refusal names the entry. **Assert on the archive rule's message, not merely on a
raise**: the containment check would let this through, so a test satisfied by any error would be
green under an implementation that has no archive rule at all;
`::test_a_template_file_entry_that_escapes_the_target_is_refused` — `../../evil.md`, and a symlinked
directory inside the template tree, **both**, because `plans/20260731_2128-source-walk-containment.md` measured that
neither layer covers the other. **Both cases need a filesystem-backed template**, not the packaged
one: `importlib.resources` hands back a `Traversable`, which for a zip-imported package has no
symlinks and no `resolve()`. Point the test at a `tmp_path` template directory and say in the test
why;
`::test_a_template_without_a_files_key_still_copies_the_historical_two`;
`::test_the_extracted_containment_helper_still_refuses_every_include_pattern_it_did_before` — the
behaviour-preserving check on the extraction. Not a new assertion: the existing `[sources] include`
containment tests must pass unchanged, and this row exists so the extraction is not landed with them
quietly edited.

**Exit criteria.**

```bash
uv run --frozen pnk templates                            # notes  <version>  Plain Markdown notes…
uv run --frozen pnk templates --json | python3 -m json.tool >/dev/null
rm -rf /tmp/t7kb && uv run --frozen pnk init /tmp/t7kb
# `ls` alone hides `.gitignore` — it is a dotfile. Verified at d001175: plain `ls` prints
# "docs eval pinakes.toml README.md" and nothing else.
ls -A /tmp/t7kb                                          # .gitignore docs eval pinakes.toml README.md
! test -e /tmp/t7kb/_versions                            # the archive never reaches a KB
# the containment extraction is behaviour-preserving — re-run the tests that owned the predicate
# before it moved. `-k containment` selects NOTHING (measured at d001175: "no tests collected,
# 1288 deselected", pytest exit 5); the real names are about escaping and staying inside:
uv run --frozen pytest -q -k 'inside or escape or dot_dot' \
  tests/test_sync.py tests/test_manifest.py             # must report a non-zero count, all passing
./check.sh
```

**Why that `-k` expression and not `-k containment`.** The draft pinned
`tests/test_sync.py -k containment`. Measured at `d001175`: **zero tests collected** — the word
appears in comments and docstrings, never in a test name. `pytest` exits **5** on an empty
collection, which some readings treat as a failure and `set -e` treats as one, but a criterion
written as `… || true` or read casually becomes "the containment tests still pass" satisfied by
having run none of them. The names that exist are
`test_source_roots_stay_inside_the_kb` (`tests/test_manifest.py:238`),
`test_a_dot_dot_pattern_that_stays_inside_the_kb_is_accepted`,
`test_the_escape_is_reported_once_per_pattern_not_once_per_file`,
`test_a_symlinked_escape_stops_the_walk_rather_than_enumerating_the_tree`
(`tests/test_sync.py:1507,1602,1715`). **Re-grep them at branch time and print the count.**

**Free-path coverage — a deliverable.** `pnk templates` is a new entry point: add
`main(["templates"])` to `tests/free_path_run.py`'s `_run_free_surfaces` and the module to the
surface list at `tests/test_paid_path.py:299-314`.

**Docs:** `docs/CLI.md` (`## pnk templates`; it takes no `--kb`, so no § Common flags row — say that
explicitly so a later reader does not "fix" the omission); `docs/STATUS.md`; `docs/GUIDE.md`;
`docs/VERIFICATION.md`; `changelog.d/`.

**Mutation targets.** Remove the containment check and confirm the escape test fails on its own
assertion. Remove the `_versions` rule and confirm
`::test_a_files_entry_naming_the_version_archive_is_refused` fails **while the escape test stays
green** — if both go red, one of them is not testing what it names. Make an absent `files` key copy
nothing and confirm the historical-two test fails.

---

### T8 — A second template 🚫 gated

**Do not write this increment until the gate passes.** Per D-7, and per `docs/DESIGN.md:1080` —
*"Generalisation, once real usage has shaped one template well."*

**The gate, so that it is a measurement and not a mood.** All three:

1. **`pinakes-kb` exists and has been used** (`plans/20260801_0749-realism-corpus.md` — the dogfooding KB, private,
   outside this repository), or a second real KB does.
2. **Its manifest diverges from a fresh `notes` stamp in at least three settings, each for a reason
   the KB's owner can state** — not three settings that could equally have been the template's
   default. The diff and the three reasons are recorded before the template is authored.
3. **At least one of those divergences is not expressible as a manifest value** — a different
   `eval/questions.yaml` shape, a different README, a different set of copied files. If every
   divergence is a manifest value, the honest answer is documentation of good defaults, not a second
   template: a template that differs only in numbers is a preset, and `pnk init` already lets a user
   edit numbers.

**Evidence that refuses it.** Two KBs whose manifests differ only in `[kb] name`; or a divergence
that turns out to be a *missing default* in `notes` — in which case the correct action is to change
`notes` (and bump it, T1) rather than to fork it.

**What it would land, if the gate passes.** Named only so the gate's outcome is actionable, not as a
plan: a second `templates/<name>/` with its own `template.toml`, `pinakes.toml.j2`, `README.md`,
`files`, and its `_versions/1.0/` archive; `docs/CLI.md`'s `pnk init --template` gains it. **No
`prompts/` directory** — `docs/DESIGN.md` §6.1's sketch includes one for `--deep`, and that belongs to
the deep release, which another agent owns.

---

## The release cut

Per D-9, expect more than one. Whichever combination is cut:

1. `python3 tools/shared_file_overlap.py --fetch --strict`, then read the merged state of everything
   it names.
2. `python3 tools/fragments.py --apply`.
3. Follow `docs/RELEASING.md` — it is the procedure, and it owns the three documents a release stales
   (`docs/STATUS.md`'s PyPI table, its roadmap, `README.md`'s install lines).
4. `make release-check` **before** pushing the tag. A tag publishes to PyPI and PyPI does not allow
   re-uploading a version.
5. **Verify the release happened** by querying the index, not by reading the CHANGELOG.
6. If the cut is not the final one for this release name, the name **stays** in `CLAUDE.md`'s
   unbuilt-work table and the roadmap row carries both tags.

## Verification — the *promises* this plan predicts

> ⚠ **The test names in this table are not binding, and neither are the ~40 above.**
> `docs/VERIFICATION.md:3-8` records what happens otherwise: `plans/20260727_1543-v0.2.md` named 98
> test paths and **61 did not resolve**, because the names were written before the tests existed and
> implementation renamed them. `tests/test_verification.py` asserts every name in
> `docs/VERIFICATION.md` resolves, so a predicted-then-renamed test turns the branch **red**.
> **The left-hand column is the contract; the right-hand column is a sketch.** Each increment adds
> `docs/VERIFICATION.md` rows for the tests it actually wrote, under the one narrow exception
> `CLAUDE.md` grants an implementer.

| Promise | Increment | Sketch of what should hold it |
|---|---|---|
| a template's content cannot change without its version changing | T1 | `tools/template_drift_gate.py` (a `check.sh` gate and a CI job with `fetch-depth: 0`), plus the comment-only test |
| an archived version cannot be edited after it is published | T1 | the ledger legs (iii)–(iv) **and** the git-history leg (vii); the gate prints which mode it ran in |
| ~~the version archive is never offered as a template~~ → **a template name is one path component, so nothing inside a template directory is reachable as a template** | T1 | the name-validation test. *The original promise was held by a test that could not fail* — `available()` never sees inside a template directory, so the assertion was true regardless of the rule |
| a template cannot declare a file inside the version archive | **T7** (not T1) | the `files` validator's `_versions` rule. In T1 there is no `files` key, so nothing could have declared one |
| a template-drift report never contains the user's own edits | T2 | the user-edited-value test |
| the KB identity block never produces a hunk | T2 | the `[kb]`-hunk test — without it, `--apply` refuses for every user who touched `[kb]` |
| `pnk upgrade` without `--apply` writes nothing anywhere in the KB | T3 | the whole-tree byte-and-path-set snapshot |
| a hunk already present in the manifest is neither clean nor a conflict | T3 | the already-applied test |
| `--apply` never merges a conflicting hunk, and a refusal leaves no backup | T4 | the conflict-refusal test, asserting the message, byte-identity **and** the absent `.orig` |
| **a spending cap is never widened without the user having been shown both numbers first** — D-10 (taken) applies the hunk, so the promise is about *consent*, not refusal | T4 | four tests as a set: both-values-printed (the **old** value is the discriminator — it exists only in the file being replaced), heading-precedes-the-write (by line position), applied-like-any-other, and the negative control that no heading appears when no hunk touches `[budget]`. **The negative control is what stops the other three being satisfied by an unconditional heading** |
| `--apply` never writes `[kb] requires_pinakes` — D-11 (taken) | T4 | the never-written test, asserting absence from the **file** after a key-adding bump; plus the operand test, which is the only one that fails under `parse(ours) − parse(base)` |
| `[kb] template` is the only key `--apply` writes **outside the applied hunks** | T4 | the in-`[kb]`-table rewrite test **and** the `requires_pinakes` tests together — the claim is a count of write sites, and one test cannot hold it. The qualifier is load-bearing: the hunks change values, `[budget]`'s included |
| `--apply` says when the index must be rebuilt | T4 | the rebuild-naming test, which is what makes "does not run a sync" honest |
| an unloadable result is rolled back | T4 | the monkeypatched-`load` test |
| `--apply` never touches `docs/` or `.pinakes/` | T4 | snapshots of both trees |
| a manifest cannot name a vector tier that is not built | T5 | the refusal test, asserting the accepted list in the message |
| `meta`'s `vector_tier` is written from the resolver's return | T5 | the injected-resolver half. **Not** "the index records the tier that ran" — with one tier there is nothing to discriminate, and the stronger promise waits for T6 |
| a template file entry cannot write outside the KB | T7 | the escape test, with both the `../..` and the symlink case |

## Risks

| Risk | Containment |
|---|---|
| The archive (D-2 A) is edited after release, so a diff lies about history | The `_versions.toml` ledger makes it a two-file edit visible in review, and gate leg (vii) fails on **any** post-publication commit to an archived directory. **Neither is tamper-proof, leg (vii) needs git history, and the gate's docstring says both.** |
| `--apply` writes a manifest a user did not want | T3 ships first and is a coherent stopping point. `--apply` refuses on any conflict, decides everything before it writes so a refusal leaves nothing behind, and leaves `pinakes.toml.orig` when it does write. |
| **`--apply` raises a spending cap the user did not intend** | **Not eliminated — D-10 (taken 20260804) applies `[budget]` hunks like any other.** Contained by consent, not by refusal: the report writes nothing, `--apply` is a separate act, a money change is printed under its own heading with both values, the print precedes the write, and `.orig` holds the old caps for recovery. **The residual risk is a user who runs `--apply` without reading**, and it is accepted rather than engineered away. The live case is concrete: the first `[budget]` hunk anyone sees raises two caps sixfold (0.8.0's `97309d8`, `e3685e1`). |
| **`pnk upgrade` is shipped and is useless for every KB that exists** | Real, and D-2b's **taken** answer accepts it: `notes@1.0` denotes six contents, so the honest report is *cannot compare*. The mitigation is the message — it must name what the user can do, not shrug — and O-2 (its exit code) is flagged for the planner because it fires for 100% of users. The alternative (guess a base) was refuted, not merely disliked. |
| **T4's positive paths are never exercised against anything shipped** | A consequence of D-2b, contained rather than hidden: the fixture is a synthetic two-version template, built in a scratch copy of the package via `PYTHONPATH` (mechanism verified at `d06ef7e`), and T4 states plainly that the first *real* `[budget]` hunk arrives with the next template bump and should be re-run by hand then. O-3 offers the planner the alternative. |
| A measurement in this plan goes stale and an increment is built on it | It already happened: "zero values changed" was true at `aae76fc` and false two commits later, and it was load-bearing for F2, D-3, T3 and T4. **Re-run M1–M7 at branch time**, and never assert a literal line count anywhere. |
| T6's precondition is failed and the `sqlite-vec` tier never ships | That is a legitimate outcome and costs nothing but the measurement, which is the ordering's point. `docs/STATUS.md` records it either way, and T5 has already made the config surface honest. |
| The template release cuts, the name leaves the table, and T6 or T8 later needs it back | D-9, and `CLAUDE.md`'s multi-cut rule — the churn that rule was written to prevent. |
| Two agents both bump `SCHEMA_VERSION` to 3 | Neither plan hardcodes it; `tests/test_store.py:93` fails loudly for whoever is second. |
| `docs/KB-UPDATES.md` keeps being cited as the design after F1–F3 refuted parts of it | T1's Docs list proposes the corrections to the planner in its own commit message, per `CLAUDE.md`'s documentation-ownership rule. |
