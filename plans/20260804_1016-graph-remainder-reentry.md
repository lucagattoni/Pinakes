# G3, G5, G6 — the re-entry checklist


> ## ✅ Decisions 1–3 taken by the user, 20260804 10:16
>
> **The `authored` weight: defer, and measure it as a G5 leg.** Not kept-and-risked, not damped, not
> capped — every one of those decides a frozen weight on an *argument*, which is what decision 13
> froze the table to prevent. G3 lands with the weight table carrying an explicit *measured at G5*
> marker. This satisfies the ⚠️'s intent (that the weight not be "discovered by a gate that passes")
> rather than its literal "re-decided before G3 is built", and that reading was put to the user.
>
> **A three-edge-kinds-absent corpus: run and restrict for G3; refuse for Gate 1 / PPR.** They are
> not the same question. For G3's precondition `shared-tag` and `authored` are both strong here and
> can carry a restricted claim. For PPR the absent input is not one edge kind of seven — it is
> **half the personalization vector** APPROACH §4B specifies, so the gate does not run on a corpus
> below the heading-coverage floor.
>
> **The thresholds are committed as written, recorded as proposals.** None is derived from a
> measurement and none can be before the run — that is what a committed threshold is. The
> alternative was prose (`"does not dominate"`), which both a null result and a decisive one satisfy
> at the reader's discretion. **A wrong number is arguable; no number is not.**

**Audience: the agent that picks the graph release back up. Goal: executor.**

**This is not a plan and it does not restate one.** G3, G5 and G6 are specified in
[`plans/20260729_0256-links-and-graph.md`](20260729_0256-links-and-graph.md) and
those specifications stand. What this file holds is the set of things that were **true when they
were written and may not be true when they are read** — because the specification body was written
on 20260729 against `main` before 0.5.0, it was blocked on 20260801 by a measurement it had not
anticipated failing, and **five releases have landed since** (0.5.0, 0.6.0, 0.7.0, 0.7.1, 0.8.0).

**Written 20260803 22:53 against `main` at `aae76fc`. Revised 20260804 08:51 against `main` at
`68084d3`, after an adversarial review** — 0.8.0 shipped, the RFC realism corpus was built, and the
`authored`-weight premise was falsified in between.

> **Every `plans/` path in this file changed on 20260804.** Commit `61f1975` gave every plan and
> fragment a `YYYYMMDD_HHMM-` prefix, retrospectively. `plans/links-and-graph.md` is now
> `plans/20260729_0256-links-and-graph.md`; `corpus-probe-run.md` is `20260803_2239-…`;
> `realism-corpus.md` is `20260801_0749-…`; `open-corrections.md` is `20260731_1202-…`. If a path
> in any older note does not resolve, this is why — check `ls plans/` before concluding a document
> was deleted. **Anything this file becomes, filed into `plans/`, takes a prefix too.**

**Citations re-confirmed at `d06ef7e`, 20260804 09:25.** The only commit since `68084d3` touches
`docs/STATUS.md`'s PyPI table, which is below every line this file cites; all four `STATUS` line
numbers here still resolve.

## The one precondition, restated so it cannot be skipped

G3 does not start until the headroom precondition is **measured and passed on a corpus that can
discriminate**. The first measurement failed on 20260801 12:14 (1 of 18 against ≥ 7 —
`docs/STATUS.md` § *Can the graph release's gate be reached?*, `docs/STATUS.md:383`). The second is
run against the RFC corpus by the procedure in
[`plans/20260803_2239-corpus-probe-run.md`](20260803_2239-corpus-probe-run.md), under
the conversion contract that keeps its frozen questions frozen.

**The corpus now exists.** `pinakes-corpus-rfc` — 300 RFCs, built 20260804 08:00, measured in
`docs/STATUS.md:342` § *The realism corpus exists, and it falsified a design premise*. Everything
below that used to read "when a corpus exists" is now a fact you can check, and two of those facts
are bad news that arrived with it (C8 and E8). **Nothing in that section licenses G3**: the corpus
existing is not the probe passing.

**Do not re-author G2's questions to change the number.** That is the circularity decision 14
removed once already and it is undetectable afterwards.

**A pass licenses G3 only.** G5's gate is separate, is computed twice (with and without authored
edges), and must pass in **both** runs
([`plans/20260729_0256-links-and-graph.md:690`](20260729_0256-links-and-graph.md)).

---

## Part 1 — What must be re-verified, and how

**Tables A–C are mechanical**: each row is a command to run or a file to read, and the answer goes
in the branch's first commit message. **Table D is arithmetic and measurement you must redo, table E
is a set of decisions you must take and record, and table F is a set of readings you must commit to
*before* the probe runs.** Run A–C first; do not treat D–F as ticked because A–C were.

### A. The baseline itself

| # | Check | Run this | Why it may have moved |
|---|---|---|---|
| A1 | The plan's stated baseline is older than `main` | `git log --oneline -1`, then `sed -n '49p' plans/20260729_0256-links-and-graph.md` — the plan says `main` at `d56bb35`, 20260803 22:18 | Every merge. The command answers it; do not carry any commit sha out of this file as current |
| A2 | CI on `main` is green | `gh run list --branch main --limit 1` | A broken build that never deployed looks identical to a good one in the log |
| A3 | No shared document is about to be silently merged | `python3 tools/shared_file_overlap.py --fetch --strict`, then **read** the merged state of what it names | `docs/STATUS.md` is touched by every increment and has none of `changelog.d/`'s protection |
| A4 | Unspliced findings exist that `docs/RETROSPECTIVES.md` does not carry | `ls retro.d/` | The newest findings live there until a release splices them |
| A5 | **Read the standalone-work queue; it is not empty, and it is now long.** At `68084d3` it carries **eleven live items** (`plans/20260731_1202-open-corrections.md`, header dated 20260804 08:30), ten of them raised by *using* pinakes on the RFC corpus. Decide, item by item, which must land before G3 | `cat plans/20260731_1202-open-corrections.md` | Item 3 (`strategy = "structural"` recognises no RFC heading) **changes what the probe can measure** — see E8. Item 2 (the sync lock's UTC timestamp) and item 5 (`pnk init` refuses a non-empty directory) bite anyone re-syncing that corpus. This row said "still empty" in the 20260803 draft and was wrong by eleven |

### B. `schema_version` — the number G3 hardcodes

| # | Check | Run this |
|---|---|---|
| B1 | **G3 says `schema_version` → 3. Read the current value instead of trusting it.** | `grep -n 'SCHEMA_VERSION' src/pinakes/store.py` — `store.py:28`, `SCHEMA_VERSION: Final = 2` at `68084d3` |
| B2 | The template release's `sqlite-vec` tier claims the same number | see [`20260804_1016-template-release.md`](20260804_1016-template-release.md) § T6 — **a sibling scratchpad proposal, not a repository plan**; if it has been filed since, it is under `plans/` with a `YYYYMMDD_HHMM-` prefix. **Whichever lands first takes 3; the other takes 4** |
| B3 | The tripwire fires for whoever is second | `tests/test_store.py:93::test_schema_version_is_2_for_i5s_page_and_backend_columns` hardcodes `2` and will fail. That is correct — update it, and keep the assertion exact rather than making it version-agnostic |
| B4 | Stale prose about earlier versions | `grep -rn 'schema_version 1\|pre-I5' src/ docs/` — one hit at `sync.py:1524` |

### C. The code G3 and G5 were specified against

Read each of these as it is **now**. The specification was written before five releases landed and
cites behaviour that has since been replaced.

| # | What the spec assumes | Read | What changed since |
|---|---|---|---|
| C1 | The sidecar reader/writer | `src/pinakes/sidecar.py` | L5b replaced `pyyaml` with `ruamel.yaml` in round-trip mode at YAML 1.2 (0.5.0). Any G3/G5 reasoning about how a sidecar's `tags` or `links[]` are read is against a different library now |
| C2 | Vector row order and tie-breaking | `src/pinakes/store.py:254-294` (`load_vectors`, `ORDER BY d.path, c.ordinal` at `:285`), `src/pinakes/search.py:234-274` (`_vector`, `np.argsort(-similarities, kind="stable")` at `:258`) | G1 made ordering total on `(documents.path, chunks.ordinal)` and the argsort stable. **G5's per-question sign test depends on this.** Confirm both are still in place before treating a per-question flip as signal |
| C3 | The manifest's `[retrieval]` table | `src/pinakes/manifest.py:620-669` (`_retrieval`) | `adjacent_k` landed (L3) with a `maximum` and a deliberate not-stamped-in-the-template comment at `:644-651`. G5 adds `graph_channel`, a **second** unstamped key — see item E3 |
| C4 | `[sources] include` handling | `src/pinakes/manifest.py:479-570` (`_check_include_containment`), `src/pinakes/sync.py` | 0.7.1 added two-layer containment. Any edge derivation walking source paths inherits it |
| C5 | The evaluation harness | `src/pinakes/eval.py` | G2 added `eval/outcomes.json`, stable question ids, a validated `kind`, and an empty-set skip. **G5's clause 4 enumerates `compare()`'s six metric families and their directions — re-read `compare()` (`eval.py:574-616`) and confirm the list and the directions still match** rather than trusting pass 7's reading of a file G2 then rewrote |
| C6 | `pnk doctor`'s checks | `src/pinakes/doctor.py` | 0.6.0 added link coverage as a ratio and cross-KB target resolution. G6 adds edge-hub reporting beside them. **`open-corrections` item 3 proposes a `heading_path`-coverage check here** — if it lands first, G6's additions sit beside it |
| C7 | The traversal surface G3 promises not to change | `src/pinakes/graph/traverse.py`, `src/pinakes/graph/present.py`, `src/pinakes/graph/provider.py`, `src/pinakes/link.py` | L6–L8 landed `pnk link`. Decision 16's "G3 changes no released surface" must be re-checked against the surface as it is now, not as it was at L5 |
| C8 | **`authored`'s weight is an open decision, not a frozen one — and the plan says it blocks G3.** | `plans/20260729_0256-links-and-graph.md:525-540` — the ⚠️ incorporated at `39f7802`, 20260804 04:45 | Decision 13 froze the weight table with `authored` at **2.0 undamped**, on APPROACH §3's premise that *"authored links are sparse, precious signal"*. The RFC corpus falsified it: **53.3% of documents carry a link** (160/300) against a 35% cap, and the **worst out-degree is 86** (RFC 8996) against a cap of 4 — `docs/STATUS.md:342`. The ⚠️ says, verbatim, that it *"must be re-decided before G3 is built rather than discovered by a gate that passes"*, and equally that it **does not license changing the weight now**. **Read the block, take the decision with the user, record it.** A with-authored G5 leg run at an undamped 2.0 measures a weight nobody stands behind |

> **A discrepancy to reconcile while you are in there (C8):** the ⚠️ block says *"54% of documents
> carry a link"*; `docs/STATUS.md:342`'s table says **53.3% (160/300)**. Same measurement, one
> rounded up. Neither changes the finding — both are past the 35% cap — but two numbers for one
> fact is how a reader learns to trust neither. It is the planner's to fix, in the document that
> owns it.

### D. The measurements the gate rests on

| # | Check | How | Why |
|---|---|---|---|
| D1 | **Re-run the probe at G3's own branch point**, not only at whatever commit the corpus probe ran on | `uv run python3 tools/reachable_ceiling_probe.py --kb <corpus> --json` | The probe answers "can the gate be reached *on this index, at this code*". Five releases changed retrieval ordering (G1), source walking (0.7.1) and the probe itself (0.8.0 made it refuse a golden set it cannot measure, +491 lines). A result from an earlier HEAD is evidence about that HEAD |
| D2 | Report both numbers — the corpus-probe-run result and the re-run — and reconcile them if they differ | both JSON blobs in the commit message | A silent difference between them is the most informative thing available and the easiest to lose |
| D3 | The probe's **in-repo** discrimination tests still pass | `uv run pytest tests/test_eval.py -k reachable_ceiling_probe` — two tests: `test_the_reachable_ceiling_probe_answers_to_the_edge_set` (`tests/test_eval.py:529`) and `test_the_reachable_ceiling_probe_needs_no_index_schema_change` (`:504`) | A probe answering "reachable" for everything is the failure mode it exists to avoid. `--drop` is the mechanism (`tools/reachable_ceiling_probe.py:917-922`, choices `ALL_KINDS` at `:141`) |
| D3b | **The `--drop` discrimination proof on the RFC corpus — it is not inheritable from D3** | `--drop co-located` and `--drop shared-tag` against the RFC corpus; **both must move `liftable`.** Record both deltas | `plans/20260803_2239-corpus-probe-run.md` states this in bold: *"per corpus, not inherited from demo-kb"*. D3's tests run against `tests/demo-kb`, which has **zero** `tags:` (verified) and could only ever exercise `co-located`. A probe that does not discriminate here produces a number that reads as a pass |
| D3c | **The per-kind edge census — and the fact that no tool emits it** | `plans/20260803_2239-corpus-probe-run.md` requires, verbatim: *"Required in the run report, beside the reachability figures: a per-kind edge census — how many edges each kind derived. A kind at zero is a fact about the corpus, and it must be visible without reading this section."* `tools/reachable_ceiling_probe.py` prints **six counts and no edge totals** (`Report.as_dict`, `:657-667`; `_render`, `:889-898`). The counts are derivable from `derive()`'s own structures — `heading_hub`, `dir_hub`, `tag_hub`, `authored`, `by_doc` (`:198-260`) — but nothing prints them | A requirement with no instrument gets improvised, and an improvised census is one nobody can reproduce. Either add the census to the probe's `--json` output **in the same commit as the run** (it is a tool, not a released surface, so this costs nothing) or write the ten-line script and commit it beside the report. Do not hand-count |
| D4 | **G5's clause-3 worked example is denominated in `len(answerable)`, not in question count** | `plans/20260729_0256-links-and-graph.md:714` — *"2/66 = 0.030 against `tolerance=0.02`"* | `66` is the demo KB's **answerable** count: 74 questions − 8 `no-answer`. `eval.py:430-432` divides `false_abstain` by `len(answerable)`, and `tests/demo-kb/eval/baseline.json`'s `false_abstain: 0.0152` = 1/66 is arithmetic proof at 74 questions. **It is current for the demo KB and needs no recomputation there.** On the RFC corpus recompute it, and **state the answerable count you divided by** — a reader who takes `66` for a question count will mis-date a clause that is not stale |
| D5 | **Which rows of G5's sign-test table are reachable at the class size you actually have** | `plans/20260729_0256-links-and-graph.md:690-702` | The `r`/`i` table is a property of the exact sign test and does not move. What moves is which rows are *available*: a row needs `i + r` discordant questions, so `r=5 / i=13` needs **18** — the demo KB's entire `multi-hop` class (verified: 18). **State the class size and enumerate the rows `i + r ≤ class size` admits, before running.** The p-values re-derive correctly: r=0/i=5 → 0.03125, r=1/i=7 → 0.0352, r=2/i=9 → 0.0327, r=3/i=10 → 0.0461, r=4/i=12 → 0.0384, r=5/i=13 → 0.0481 |
| D6 | The frozen-question provenance | `plans/20260803_2239-corpus-probe-run.md` rules 1–7 | The freezing sha is recorded, the conversion diff was reviewed by the planner, and both files stay committed |

### E. Couplings the specification does not carry

These are not corrections to G3/G5/G6; they are facts that arrived after them.

**E1 — The gate runs on one corpus and the CI baseline lives on another, and the plan does not say
what happens between them.**
`plans/20260801_0749-realism-corpus.md:22` states the RFC corpus is **never in CI** — *"no gate
depends on it, by decision."* But G5's clause 3 requires a **re-baseline in the same commit** that
turns the channel on, and the baseline `compare()` guards in CI is `tests/demo-kb/eval/baseline.json`
(`.github/workflows/ci.yml`, the golden-set job). So:

* the *licensing* measurement is on the RFC corpus (the only one that can discriminate);
* the *re-baseline* is of the demo KB (the only one CI runs);
* and turning the channel on by default moves the demo KB's numbers too — on a corpus whose funnel
  already returns every document (E9), so the movement there is not evidence of anything.

**Before G5 starts, decide and write down which corpus licenses the default and which corpus's
baseline is rewritten, and state that they are different.** Both sets of before/after numbers go in
`docs/STATUS.md`. A reader who sees one set will assume it is both.

**E2 — G3's exit criterion names a fixture "captured at G2's HEAD".**
`plans/20260729_0256-links-and-graph.md:588`. G2's HEAD is now five releases back. Capture the
`pnk links --json` fixture at **G3's own branch point** and say so in the commit; a fixture from an
older HEAD compares the channel against changes that are not the channel.

**E3 — `graph_channel` is the second manifest key that cannot be stamped into the template.**
`manifest.py:644-651` records why `adjacent_k` is not stamped: `_toml.py` hard-errors on an unknown
key, so any pinakes built before the key existed cannot read a manifest carrying it, and
`requires_pinakes` cannot help retroactively. G5's `graph_channel` inherits this exactly.
**If the template release's `pnk upgrade --apply` ships first** ([`20260804_1016-template-release.md`](20260804_1016-template-release.md)
§ T4 — a sibling scratchpad proposal, not a repository plan), there is finally a mechanism that
adopts a new key into an existing manifest *and* raises the compatibility floor in the same write —
at which point stamping either key becomes a deliberate, supported act rather than a break.
Note the dependency; do not schedule on it.

**E4 — `tests/demo-kb`'s structural poverty is unchanged, and the RFC corpus does not fix it for
the tests.**
The demo KB has **zero** `tags:` and one flat directory (verified at `68084d3`), so exactly one
derived edge kind crosses a document boundary there. `tests/partner-kb` is the same shape. The RFC
corpus is outside the repository and **never in CI**. **G3's `tests/test_edges.py` therefore cannot
get its discrimination from either**: not from the demo KB (too flat) and not from the RFC corpus
(not available in CI). The tests need a small in-repo fixture corpus with tags, nested directories
and **headings the chunker actually recognises** (E8), built for the tests and asserted on directly.
Write it as part of G3 rather than discovering the gap when
`::test_a_shared_tag_produces_linear_not_quadratic_edges`
(`plans/20260729_0256-links-and-graph.md:576, :876`) has no shared tag to test.

**E5 — G5's edge-kind attribution requirement is the guard against the *second* circularity, and it
survives the corpus change.**
The with/without-authored split neutralises hand-authored links. It does not neutralise the fact
that the same author chose the directory layout and tag vocabulary. On the RFC corpus that guard
changes character in the direction the plan wants: the directories are IETF working-group acronyms
and the tags are **the RFC Editor's own `keywords`**, not a pinakes agent's inventions
(`plans/20260801_0749-realism-corpus.md`; `docs/STATUS.md:342`). **Re-read that reasoning and state,
in `docs/STATUS.md`, whether a result carried by `shared-tag`/`co-located` on this corpus is the
weaker claim the plan says it is on the demo KB.** The honest reading is that `shared-tag` is
*stronger* here (585 keywords, largest bucket 34, chosen by a third party) and `co-located` is
*weaker* (74 directories, median 1 document — most connect nothing). The point is that the plan's
sentence was written about a different corpus and must not be copied across unexamined.

**E6 — Nothing in G3/G5/G6 spends money, and that must still be shown, not assumed.**
`.paid-path-allowlist` byte-identical, and each increment extends the free-path gate's *coverage* to
whatever surface it adds. G6 step 5 already says this; it applies to G3 and G5 too, at each landing
rather than at the cut. (0.8.0 moved the paid key to `PINAKES_ANTHROPIC_API_KEY` with no fallback —
if anything in a G3 branch reads an environment variable, re-read that release note first.)

**E7 — G6's verification list is now a subset of a document that owns the subject.**
`docs/RELEASING.md` is the procedure for a cut. Read it and treat G6's steps 1–5 and 8
(`plans/20260729_0256-links-and-graph.md:794-812`) as the graph-specific additions to it, not as the
list.

**E8 — Three of G3's seven edge kinds derive zero edges on the corpus the gate will run on, and
that is a pinakes defect, not a corpus property.** ⚠️ **This is the newest and largest item here.**
Measured 20260804: the RFC corpus has **106 806 chunks and every one has an empty `heading_path`**
(`docs/STATUS.md:342`; `plans/20260731_1202-open-corrections.md` item 3). `strategy = "structural"`
uses a Markdown-shaped heading grammar; RFC section numbering does not match it, so the strategy
degrades to size-based chunking **in silence**. `heading_path` is what `in-section`, `parent` and
`child` derive from, so on this corpus:

| Kind | On the RFC corpus | Source |
|---|---|---|
| `in-section` | **zero edges** | `derive()` only fills `heading_hub` when `chunk.heading_path is not None` (`reachable_ceiling_probe.py:231-232`) |
| `parent` / `child` | **zero edges** | same input |
| `co-located` | weak — 74 directories, **median 1 document** | `corpus-probe-run.md` |
| `shared-tag` | strong — 585 keywords, largest bucket 34 | `corpus-probe-run.md` |
| `authored` | strong — 391 links, median out-degree 1, **one hub of 86** | `corpus-probe-run.md`, and see C8 |
| `sibling`, membership | intra-document; cannot bridge two evidence documents | by construction |

**What this obliges you to do, in order:**

1. **Report the census before the verdict** (D3c). *"So a null result here is not 'structure does
   not help'. It is 'two edge kinds were absent, one was weak, and two were tested'"* —
   `corpus-probe-run.md`, verbatim. A single headline number states the first and means the third.
2. **Do not fix the corpus, and do not fix the chunker mid-run.** Recognising RFC section numbering
   is a chunking change with its own decision and its own eval. `corpus-probe-run.md` forbids it
   inside this run, and it would also invalidate the freeze.
3. **Decide, with the user, what a pass or a fail on a three-kinds-absent corpus licenses**, and
   write it down *before* the numbers exist. Either answer is defensible; neither is defensible
   after the fact. The two readings are set out in F.
4. **G3's in-repo fixture (E4) must have headings the chunker recognises**, or its
   `in-section`/`parent`/`child` tests will assert on zero edges and pass vacuously — the same
   defect one level down.

**E9 — the demo KB's funnel returns the whole corpus, and the arithmetic that shows it is not the
one in `docs/STATUS.md`.**
`docs/STATUS.md:383` says *"`candidates_per_source` is 30 against ~30 chunks"*. The demo KB's index
holds **60 chunks over 30 active documents** (`sqlite3 tests/demo-kb/.pinakes/index.db 'select
count(*) from chunks'` → 60). The conclusion survives for a different reason: `candidates_per_source`
is applied **once per retrieval source** — `search.py:333` (lexical) and `:340` (vector) — so up to
30 + 30 = 60 of 60 chunks enter fusion. It matters here because it is the rule for sizing any
*replacement* corpus: **chunk count must exceed `sources × candidates_per_source`**, not merely
`candidates_per_source`. The RFC corpus clears this by three orders of magnitude. **The wrong figure
in `docs/STATUS.md` is the planner's to correct, independently of this file.**

### F. What would refuse re-entry even after a passing probe

**State these before the probe runs, not after.** Each row carries a number so that "high" and
"dominates" are not decided by whoever reads the output. The numbers are proposals to be confirmed
by the planner in the same act that records them — but they are committed *before* the run either
way.

| Signal | Threshold, committed in advance | What it means | Action |
|---|---|---|---|
| Reachable **only** with authored edges | the without-authored `liftable` is below the precondition floor while the with-authored one clears it | The corpus's authored links bridge the questions; derived structure is not doing the work | G3 may still land (the edge table is inert), but G5's gate cannot pass its without-authored leg. Record it and stop before G5 |
| The `at-seed` share is high | `at_seed_only ≥ 0.5 × liftable` | The questions were already among the fused candidates and traversed no edge — the probe counts them in `liftable` deliberately and reports them separately for exactly this reason (`reachable_ceiling_probe.py:772-782`) | The ceiling is an artefact of the retrieval funnel, not of the graph. Report `liftable − at_seed_only` as the channel headroom beside the raw figure, and treat *that* as the number G5 has to beat |
| Every reachable path is `co-located` through one directory | more than half of the liftable questions lose their reachability under `--drop co-located` alone | The demo KB's failure repeating on a new corpus. On the RFC corpus this is *less* likely than it was — 74 directories, median 1 document — which makes it more informative if it happens | Not fatal, but it makes any G5 result a claim about one directory. Say so where the number is reported |
| The beyond-2-hop share dominates | `beyond_depth ≥ liftable` | The 2-hop bound, not the channel, is the binding constraint. The three counts are **disjoint** (`reachable_ceiling_probe.py:772-786` is an `elif` chain), so this is a ratio between populations, not a share of one — say so wherever it is reported | PPR's territory, not `expand`'s — see [`20260804_1016-staged-channel-gates.md`](20260804_1016-staged-channel-gates.md). Before escalating, re-run at a higher hop bound: the probe already computes a `FAR_DEPTH = 6` reachability (`:146`), so this costs one run |
| **The probe passes, but `in-section` / `parent` / `child` derived zero edges** (E8) | any of the three at zero in the census | The result is a claim about `co-located` + `shared-tag` + `authored` and nothing else | **Not fatal and not a licence.** G3 may land — the edge table holds all seven kinds and three of them being empty on one corpus is a corpus fact. But **G5's gate cannot be read as "structural edges help"**; it can only be read as "these two structural kinds help". Write that sentence into `docs/STATUS.md` beside the number, before the number is known |
| **The probe passes, but the corpus's authored out-degree resembles the RFC corpus's** (C8) | worst out-degree > 4, or link density > 35% — both already true at 86 and 53.3% | The falsified-premise case is live on *this* corpus, not in the abstract | **Take the `authored`-weight decision before G5 runs either leg.** A with-authored result at an undamped 2.0 is a claim about a weight the plan has flagged as needing re-decision |

---

## Part 2 — Re-entry order

1. Run every check in Part 1 A–D. Record the answers in the branch's first commit message.
2. Run `plans/20260803_2239-corpus-probe-run.md`. **It has three outcomes, not two:**
   * **(a)** Both `--drop` runs move `liftable`, the census is reported, and the precondition
     passes → continue.
   * **(b)** Both `--drop` runs move `liftable`, the census is reported, and the precondition
     fails → stop and record it. **That is a complete outcome** — the plan's own words: *"the
     expansion channel is not worth a `schema_version` bump, and the graph release closes with that
     finding."*
   * **(c)** A `--drop` run does **not** move the count → **the measurement is void**, whatever the
     headline number says, because the probe is then measuring something other than this corpus's
     edge set. Fix the corpus wiring or the probe and re-run. **Do not read (c) as (a)**: a probe
     answering "reachable" for everything produces a large `liftable` that looks exactly like a pass.
3. If it passes: settle E1 (which corpus licenses, which corpus re-baselines), E4 (the in-repo edge
   fixture) and E8 step 3 (what a three-kinds-absent result licenses) **before** writing code,
   because all three change what G3's tests are and what its result means.
4. Re-review G5's clauses against `eval.py` as it is (C5, D4, D5).
   `plans/20260729_0256-links-and-graph.md` already requires this: *"G5's clauses are re-reviewed
   before G5 is built."*
5. **Take the `authored`-weight decision the ⚠️ at `plans/20260729_0256-links-and-graph.md:525`
   requires (C8), with the user.** It is a precondition of **G3**, not of G5, because the weight
   lives in G3's table — which is why it sits here and not after step 4. The plan says it *"must be
   re-decided before G3 is built rather than discovered by a gate that passes."*
6. Then, and only then, build G3 as specified.

## Part 3 — What this checklist does not do

It does not re-specify G3, G5 or G6, does not change their gates, and does not relax their
preconditions. Where it disagrees with `plans/20260729_0256-links-and-graph.md` about *what to
build*, that plan wins and this file has a bug.

Where it says a fact the plan states has since moved, **tables A–C give the command that checks it**
— the row is the claim, and it is checkable. **Tables D–F are not commands**: D is measurement and
arithmetic to redo, E is decisions to take and record, F is thresholds to commit to before the run.
Do not treat a D–F row as answered because you ran the A–C rows.
