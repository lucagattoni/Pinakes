# Pinakes documentation

**Everything in this directory is published** to
[lucagattoni.github.io/pinakes](https://lucagattoni.github.io/pinakes/) by
[`.github/workflows/docs.yml`](../.github/workflows/docs.yml) on every push to `main`. The site is a
*view* over these files, never a second copy — which is why nothing was moved to build it: these
filenames are load-bearing in code (`tools/fragments.py` writes `RETROSPECTIVES.md`,
`tools/status_header_gate.py` and CI parse `STATUS.md`, `tests/test_verification.py` reads
`VERIFICATION.md`). Chapter numbers live in `mkdocs.yml`'s `nav` and are applied by JavaScript, so
the Markdown here stays clean for GitHub. Two files sit outside the set above: `index.md` is the
site's landing page and nothing else links to it, and **this file is excluded from the site** — it
is the agent-facing routing table, and MkDocs will not accept it and `index.md` in one directory
anyway.

| Doc | Answers |
|---|---|
| [**GUIDE.md**](GUIDE.md) | *How do I use this?* Install, first KB, PDFs, search, hooks, MCP, troubleshooting |
| [**CLI.md**](CLI.md) | *What does this flag do?* Every command, every flag, exit codes |
| [**MANIFEST.md**](MANIFEST.md) | *What goes in `pinakes.toml`?* Every manifest and sidecar field, with defaults |
| [**MEASUREMENT-RUN.md**](MEASUREMENT-RUN.md) | *How were the paid extractor's quality numbers obtained, and how do I re-run them?* The runbook, its steps and its euros |
| [**STATUS.md**](STATUS.md) | *Does this exist yet?* Shipped vs planned, the increment ledger, measured numbers |
| [**VERIFICATION.md**](VERIFICATION.md) | *What holds this promise?* Every claimed property and the test that checks it — `tests/test_verification.py` asserts each one exists |
| [**DESIGN.md**](DESIGN.md) | *Why is it built this way?* Architecture, storage, sync semantics, concurrency, trade-offs |
| [**RETROSPECTIVES.md**](RETROSPECTIVES.md) | *What did we learn?* Per-increment findings, and the design's own review passes |
| [**KB-UPDATES.md**](KB-UPDATES.md) | *What happens to a KB somebody already has when Pinakes changes?* Design note — **mostly proposal**; its `requires_pinakes` half is built (G4), the rest is not |
| [**graph/**](graph/) | Graph-retrieval research shaping the links and graph releases — thirteen investigations plus the synthesis |

Build plans live in [`plans/`](../plans/); the release history is [`CHANGELOG.md`](../CHANGELOG.md).
`plans/` holds more than one kind of file, and only the first is a build order:

| File | What it is |
|---|---|
| [`20260729_0256-links-and-graph.md`](../plans/20260729_0256-links-and-graph.md) | **The current build order** — the links release (L*) and the graph release (G*) |
| [`20260801_0102-links-and-graph-log.md`](../plans/20260801_0102-links-and-graph-log.md) | That plan's iteration log: how it was reached, never what to do |
| [`20260731_2128-source-walk-containment.md`](../plans/20260731_2128-source-walk-containment.md) | A standalone increment, shipped in 0.7.1 — outside both releases above |
| [`20260731_1202-open-corrections.md`](../plans/20260731_1202-open-corrections.md) | Numbered corrections for the implementing agent; items are closed in place, never deleted |
| [`20260801_0749-realism-corpus.md`](../plans/20260801_0749-realism-corpus.md) | The RFC corpus and the dogfooding KB — both live **outside** this repo |
| [`20260804_1016-template-release.md`](../plans/20260804_1016-template-release.md) | The template release — the ecosystem, `pnk upgrade`, the `sqlite-vec` tier. Reviewed (36 findings) and revised; its four decisions taken 20260804 |
| [`20260804_1016-graph-remainder-reentry.md`](../plans/20260804_1016-graph-remainder-reentry.md) | What must be re-verified about G3/G5/G6 **if** the blocking measurement is ever passed — a re-entry checklist, not a plan |
| [`20260804_1016-staged-channel-gates.md`](../plans/20260804_1016-staged-channel-gates.md) | The **gates** for the PPR channel and the `[ner]` extra — what measurement would justify each, and what would refuse it. Deliberately not implementation plans |
| [`20260803_2239-corpus-probe-run.md`](../plans/20260803_2239-corpus-probe-run.md) | How the second headroom measurement is run against that corpus, and the conversion contract that keeps its frozen questions frozen |
| [`decision-*.md`](../plans/) | A decision record — rationale, not instructions |
| `20260725_1317-v0.1.md`, `20260727_1543-v0.2.md` | **Shipped.** Historical build orders, still cited by `check.sh` and `tools/paid_path_gate.py` |

**Two of these documents are written to indirectly.** `CHANGELOG.md` and `RETROSPECTIVES.md` are the
files every piece of work touches, so a change adds a fragment to
[`changelog.d/`](../changelog.d/README.md) or [`retro.d/`](../retro.d/README.md) and
`python3 tools/fragments.py --apply` splices them at release time. **Never edit either document
directly.** Reading them, note that anything unreleased is still sitting in its fragment directory.

---

## Where does a fact live?

**One fact, one home.** Each row is the *only* place that fact belongs; everywhere else links to it.
When an increment lands, this table says which file to edit — usually exactly one.

| Fact | Home | Everywhere else |
|---|---|---|
| Whether a feature is built yet | **STATUS.md** | links to it — never restates a version |
| What a command or flag does | **CLI.md** | `--help` is authoritative; CLI.md adds when and why |
| A manifest or sidecar field, its default, its validation | **MANIFEST.md** | DESIGN gives the rationale and links here |
| How to accomplish a task | **GUIDE.md** | README links to it |
| Why a design decision was taken, and what it costs | **DESIGN.md** | — |
| Which code paths are allowed to spend money | **`.paid-path-allowlist`** + CLAUDE.md's invariant | DESIGN §1 gives the rationale; `check.sh`, CI and `tests/test_paid_path.py` read the file itself |
| A measured number (recall, latency, false-confidence) | **STATUS.md** | cited with its date wherever quoted |
| What changed in a release | **CHANGELOG.md** | written as a `changelog.d/` fragment; spliced at release |
| What an increment taught us | **RETROSPECTIVES.md** | written as a `retro.d/` fragment; spliced at release |
| How to run the human-gated paid measurement | **MEASUREMENT-RUN.md** | STATUS carries the numbers it produced, with their date |
| What is going to be built, and in what order | **`plans/`** | STATUS.md carries the shipped/planned state only |
| How to cut a release, step by step | **[`RELEASING.md`](RELEASING.md)** | `CLAUDE.md` carries the *rules* about when and the traps; this is the procedure |
| Which test holds a given promise | **VERIFICATION.md** | a plan's own table records what was *predicted*, never what exists |

The README is deliberately **version-free**: it describes what Pinakes *is*, never what release you
are on. That is why it does not go stale.

## Landing a new increment

The docs are built so an increment touches few files. In rough order:

1. **STATUS.md** — flip the increment's row. Merged to `main` but not in a release is **"on `main`,
   unreleased"**, not "shipped": installing from a tag and installing from `main` are different
   answers to "can I use this yet". Move its capability out of "not built" only when a user can
   actually reach it. If it changed a measured number, update it *with the date you measured it*.
2. **CLI.md** — move the surface out of "Planned", or add its flags to the command's table.
3. **MANIFEST.md** — add any new manifest or sidecar key, with its default.
4. **GUIDE.md** — fill the stub if the increment made a task possible that wasn't before.
5. **DESIGN.md** — only if the *rationale* changed. A new flag alone is not a design change.
6. **A [`changelog.d/`](../changelog.d/README.md) fragment** — one file, named
   `<category>-<slug>.md`, in the same commit as the code. **Never an edit to `CHANGELOG.md`**:
   it is the one file every increment would otherwise touch, and two agents cannot conflict in
   separate files.
7. **VERIFICATION.md** — if the increment shipped a test that holds a promise, it gets a row. The
   gate walks from this table to the tests, so it catches a row naming a test that does not exist
   and **cannot** catch a shipped guarantee with no row: 0.7.1 shipped seventeen containment tests
   and added none (found 20260804, rows added then).
8. **A [`retro.d/`](../retro.d/README.md) fragment** if the increment's review found something
   worth keeping — a real defect, or a fact expensive to rediscover. Same reason, same rule:
   never edit `RETROSPECTIVES.md` directly. Trivia stays in the commit message.

`plans/20260727_1543-v0.2.md` carries a DESIGN.md amendment table assigning each spec edit to the increment that
makes it true. **Amendments land with their increment, never in advance** — a spec describing
unbuilt behaviour is the failure mode the project's README rule exists to prevent. DESIGN sections
still awaiting an amendment carry a dated note saying so.

**Before assigning a release number, check what has already landed on `main`** ([CLAUDE.md](../CLAUDE.md)).
Another session or worktree may have cut a release since your branch started, so the number you were
about to use — or the one a plan assumes — may already be taken. `plans/20260727_1543-v0.2.md` assumed it would cut
`0.2.0` at I9; `0.2.0` shipped after I5 and `0.2.1` after that.

And **do not write a number for the release after this one** — name it (see Conventions below). That
is what stops the next plan from assuming a number that a parallel session has already spent.

## Conventions

> ### 🚫 Unbuilt work is named, never numbered
>
> **A version number belongs to a release when it is cut — never before.** Refer to unbuilt work by
> name: **the graph release**, **the deep release**, **the template release**. (A name leaves this
> list at its release's *final* cut — the paid-extraction release became 0.3.0, the links release
> 0.5.0 + 0.6.0.) Never write `v0.4` for something that does not exist — not in docs, not in `--help`, not
> in an error message, not in a code comment.
>
> Decided 20260729 00:09, after `v0.3` came to mean two different releases at once and picking either
> meaning would have renumbered ~60 committed references. Full rationale and the current mapping:
> [STATUS.md § Release roadmap](STATUS.md#release-roadmap).
>
> Historical records (`CHANGELOG.md`, `RETROSPECTIVES.md`, `plans/`, the dated research in `graph/`)
> keep the numbers they were written with and carry a header note pointing at STATUS.md.

- **Every date carries a time**: `YYYYMMDD HH:MM`, local 24h. Several entries land per day, and a
  bare date loses their order and hides how fresh a "verified" claim is.
- **Read the clock; never compose a timestamp.** Run `date "+%Y%m%d %H:%M"` and paste the result.
- **Docs describe what ships.** Anything unbuilt is labelled with the increment or release that will
  bring it. Check by *running the commands a doc shows*, install line included — an audit at 0.1.2
  found four README claims contradicting the code while the CLI and CHANGELOG were correct.
- **Every change and every decision is audited for its neighbourhood, not its diff.** Before landing
  it, re-read what surrounded or depended on it and ask four questions of each: is it **consistent**
  with the other docs, does its **logic** still hold, has it been **superseded** by a decision taken
  since, and is it **outdated** against the code, the index or the clock. Whatever made the line you
  came to fix go stale almost certainly reached its neighbours too.

  **A decision's neighbourhood is not prose** — it is every table, increment body, release
  structure, roadmap row and invariant that assumed the decision it replaces. Superseding in the
  record and leaving the tables is how a plan comes to say two things at once. Measured 20260731:
  of nine decisions in the `ruamel.yaml` swap, three rippled into tables the deciding pass never
  opened, and an adversarial pass found them.
- **Name the audience and the goal before writing a line.** Audience: a **human**, an **agent**, or
  **both**. Goal: **reference** (answers "why" or "what is true") or **executor** (something acts on
  it). The two axes decide the form, and getting them wrong is the commonest defect here.

  | Doc | Audience | Goal |
  |---|---|---|
  | `README.md`, `GUIDE.md` | human | orientation / executor |
  | `CLI.md`, `MANIFEST.md`, `STATUS.md`, `VERIFICATION.md` | both | reference |
  | `DESIGN.md`, `plans/decision-*.md` | both | reference — rationale only |
  | `CLAUDE.md`, `plans/<plan>.md` | agent | **executor** |
  | `changelog.d/`, `retro.d/` fragments | agent | executor |

  An **executor** doc is imperative, self-sufficient, and names exact files, symbols and predicates:
  the agent reading it has no access to whoever wrote it. A **reference** doc may argue, measure and
  survey. **Rationale in an executor doc is noise; an instruction in a reference doc is a defect** —
  compacting L5b on 20260731 moved decision 23's resolver predicate into the decision record and
  left the increment unbuildable from its own text.
- **Rewrite to the current state; do not layer corrections.** A doc that grows by appending
  "actually, that was wrong" makes every reader traverse the archaeology to learn what is true now.
  State each claim correctly once and delete what it replaced — git holds the history. Measured
  20260731: `plans/20260731_0602-decision-ruamel-yaml.md` reached 297 lines, 156 of them three layers of
  correction, and collapsed to 110 with nothing load-bearing lost.
- **Compact on a schedule, not when it hurts.** Review every doc against these conventions monthly,
  alongside the `CLAUDE.md` hygiene pass. Cut recaps, summaries of other sections, superseded
  reasoning, and any sentence that re-argues what another file owns. Keep what a future
  implementation needs: decisions, measured numbers, and instructions. A section far larger than its
  siblings is the signal — L5b hit 247 lines against a 52-line median for other increments.

  The cost of skipping it, measured 20260729: a one-line PyPI correction was asked for, and the
  same sweep found five more — a release still listed as unbuilt in two tables, an install block
  missing the last two releases' headline capability, a README sentence implying a feature that is
  not built, a runbook still described as producing numbers the project "admits it lacks" after the
  run had happened, and a design note saying "no increment assigned" for work a plan had since
  assigned. Each was a single edit; none would have been found by reading the diff.
- `make check` formats Python **inside Markdown fences**, so a docs-only commit can fail the gate.
- **A link out of `docs/` is written absolute; a link inside it stays relative.** `plans/`,
  `CLAUDE.md`, `changelog.d/` and `tools/` have no page on the site, so a relative `../plans/x.md`
  renders on GitHub and dangles on the site. Write
  `https://github.com/lucagattoni/pinakes/blob/main/plans/x.md`, which works in both. `make docs`
  runs `--strict` and fails on the difference, and so does the `docs` workflow on every PR.
- **Heading anchors are GitHub's, on both surfaces.** `mkdocs_hooks.py` installs GitHub's slug
  algorithm because neither Python-Markdown's default nor pymdownx's matches it, and every
  cross-document anchor here was written against GitHub. Never renumber or rename a heading to fix
  a site link — that fixes the site by breaking the copy people already read.
