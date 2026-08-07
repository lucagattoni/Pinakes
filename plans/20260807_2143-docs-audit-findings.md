# Documentation audit — the findings still open

**Audience: the planner. Goal: a worklist, not a plan.** Every item names the file, the line, what
the doc claims, what is actually true, the evidence, and the fix. Nothing here is a judgement call.
**This is not a build plan** — `docs/BUILDING.md` says to read the build order out of `plans/`, and
this file is not part of it.

Produced **20260807 21:15 UTC** by a 14-agent audit of every current-state document against the
code at `fc0fd41`. Each finding was written by one agent and independently re-verified by a second
prompted to *refute* it, with the evidence re-run rather than trusted. **75 findings survived; 11
were refuted.**

| Disposition | Count | Where |
|---|---|---|
| Falsified by the 0.17.0 release, fixed with it | 21 | `063dbe1`, `8b44aa8` |
| Actively misleading a reader, fixed straight after | 12 | `20260807_2138-docs-audit-acute-fixes` |
| **Still open — this file** | **40** | below |

**Severity here: 13 medium, 27 low. None high** — all four `high`
findings were in the first group and have shipped.

**Verdicts.** `CONFIRMED` — the refuter reproduced it. `ADJUSTED` — real, but restated or
re-scored by the refuter; the corrected wording is what appears below. `MISSED-BY-FINDER` — the
refuter found it while re-reading, and the original auditor had not.

**Out of scope by instruction, and *not* audited:** `docs/ROADMAP.md` (its full review is deferred
until after T2 — it got only the mechanical release sweep), `CHANGELOG.md`,
`docs/RETROSPECTIVES.md`, `plans/**`, and the third-party research notes under `docs/graph/`.

**Two things worth knowing before working the list.** First, **T2 rewrites `pnk doctor`'s output**,
and `docs/CLI.md` and `docs/GUIDE.md` both document it — so the doctor-adjacent items below are
cheaper after T2 than before. Second, the three currency headers (`GUIDE:3`, `MANIFEST:3`,
`DESIGN:5`) claim the file was verified against a version; **restamp those last**, because the
stamp is only worth writing once everything under it is true.

## Where they are

| File | Open | Medium | Low |
|---|---|---|---|
| `docs/CLI.md` | 9 | 1 | 8 |
| `docs/GUIDE.md` | 7 | 3 | 4 |
| `docs/DESIGN.md` | 7 | 4 | 3 |
| `docs/KB-UPDATES.md` | 4 | 1 | 3 |
| `docs/MANIFEST.md` | 3 | 1 | 2 |
| `docs/VERIFICATION.md` | 2 | 1 | 1 |
| `docs/README.md` | 2 | 1 | 1 |
| `docs/MEASUREMENT-RUN.md` | 2 | 0 | 2 |
| `docs/STATUS.md` | 1 | 0 | 1 |
| `README.md` | 1 | 0 | 1 |
| `docs/graph/PINAKES_APPROACH.md` | 1 | 1 | 0 |
| `docs/graph/README.md` | 1 | 0 | 1 |

---


# Medium — 13 findings

## `docs/CLI.md:26` — false · MISSED-BY-FINDER

**Claims.** Common flags table: "`--offline` | `sync`, `search`, `serve` | **Never reach out for model weights. Fails fast instead of downloading**".

**Actually.** That guarantee holds only for the `sentence-transformers` provider. With the `fastembed` provider (the `[light]` extra, and what both committed corpora are configured for), `--offline` degrades to "fail only if the entire HF cache *directory* is missing" — if the directory exists but the model is not in it, `pnk search --offline` downloads the weights.

**Evidence.** Measured, not read. `mkdir -p <scratch>/hfempty/hub` (so the dir exists but is empty), then `HF_HOME=<scratch>/hfempty uv run pnk search --kb <scratch>/offkb --offline "catalogue" -k 1` → the run printed `Fetching 5 files: 100%|...| 5/5 [00:14<00:00, 2.90s/it]` and `Warning: You are sending unauthenticated requests to the HF Hub`, and `du -sh <scratch>/hfempty` afterwards reported **81M**, with `<scratch>/hfempty/hub/models--qdrant--bge-small-en-v1.5-onnx-q/blobs/...` on disk. Source: src/pinakes/embed.py:183-189 `_fastembed_reranker` (and :174-180 `_fastembed_backend`) call `_require_online_or_cached(offline)` and then `module.TextCrossEncoder(model_name=..., cache_dir=str(hf_cache_dir()))` with no offline argument; src/pinakes/embed.py:192-199 `_require_online_or_cached` raises only `if offline and not hf_cache_dir().exists()`. Contrast src/pinakes/embed.py:152-157 and :164-170, where the sentence-transformers paths pass `local_files_only=offline` and are genuinely offline-safe. The <scratch>/offkb manifest is a copy of tests/demo-kb, which stamps `provider = "fastembed"` in both `[embedding]` and `[rerank]`.

**Fix.** Qualify the row: `--offline` is a hard guarantee on the `sentence-transformers` backend (`local_files_only`); on `fastembed` it only refuses when no model cache directory exists at all, because fastembed exposes no `local_files_only` — an existing cache missing this model still downloads. embed.py:192's own docstring already concedes the mechanism; CLI.md should not state a stronger contract than the code delivers.

## `docs/DESIGN.md:525` — false · CONFIRMED

**Claims.** §4.6: "**Nothing filters or ranks on it** — FTS5 indexes `chunks.text` and embeddings are computed over `chunks.text`, so a chunk's recall is unaffected by whether it carries one" (and, line 523, that `heading_path`'s consumers are "not retrieval").

**Actually.** With `[chunking] metadata = "prefix"` — a shipped manifest key (0.16.0), default `"off"` — the embedded text is `title > heading path` + blank line + chunk text, built from the chunk's unnumbered `heading_path`. Embeddings are then computed over `chunk.embedding_text`, not `chunks.text`, and a chunk's vector recall *is* affected by whether it carries a heading path. The FTS half of the sentence remains true.

**Evidence.** `src/pinakes/manifest.py:73-76` → `CHUNK_METADATA = ("off", "prefix")` / `"""`[chunking] metadata` — whether `title > heading path` is prepended to the **embedded** text.` / `` `"prefix"` embeds `chunk.embedding_text` instead of `chunk.text` ``; `src/pinakes/manifest.py:658` `metadata=table.choice("metadata", CHUNK_METADATA, default="off")`; `src/pinakes/sync.py:1865` → `embedding_text(chunk, title=title) if inject else chunk.text for chunk in chunks` with `inject = manifest.chunking.metadata == "prefix"` (sync.py:1792); `src/pinakes/chunk.py:185` `path = chunk.unnumbered_heading_path`.

**Fix.** Qualify the claim: "With `[chunking] metadata = \"off\"` (the default) nothing filters or ranks on it … Setting it to `\"prefix\"` is the one exception — the vector channel then embeds `title > heading path` ahead of the chunk text, so a heading path does reach ranking." Cite the screened plan's no-go as why it ships off.

## `docs/DESIGN.md:699` — inconsistent · MISSED-BY-FINDER

**Claims.** §6.1's template tree annotates `eval/questions.yaml` as `# golden questions shipped with the template`.

**Actually.** A template ships no golden questions — it ships an empty scaffold. §7 of this same file says so in bold at line 988, and records that an earlier draft of §7 making exactly this claim was corrected.

**Evidence.** `grep -n "golden questions shipped with the template|A template ships no golden set" docs/DESIGN.md` → `699:├── eval/questions.yaml # golden questions shipped with the template` and `988:**A template ships no golden set**, and `make eval` **skips** with a printed reason rather than`. Line 989-993 continues: "an earlier version of this section said a golden set lives 'with each template' while every committed template shipped `questions: []` against a harness that rejected it, which made a freshly scaffolded KB fail its own evaluation by construction." The shipped template confirms §7, not §6.1: `cat src/pinakes/templates/notes/eval/questions.yaml` ends with `questions: []` and its header comment reads "This file ships empty on purpose, and `make eval` **skips** rather than fails while it is: the template scaffolds an empty `docs/`, so any question it shipped would name a document that does not exist." The archived copy at `src/pinakes/templates/notes/_versions/1.1/eval/questions.yaml` is the same. The §7 correction landed and §6.1's annotation was never updated with it.

**Fix.** Change the §6.1 tree comment to describe the scaffold rather than shipped content, e.g. `├── eval/questions.yaml # golden-set scaffold — ships empty, yours to fill (§7)`.

## `docs/DESIGN.md:711` — false · CONFIRMED

**Claims.** §6.1: "**This is one of four drift axes, and the only one with no mechanism.** … A manifest and a template drift *silently*, and the remedy touches a file the user owns"

**Actually.** A template does not drift silently: `pnk doctor` compares the KB's recorded `name@version` against the installed template and prints a WARN. The check has existed since I11 but could never fire while `notes` stayed at 1.0 across eleven different contents; T1's bump to 1.1 makes it fire on every KB in existence. Detection now exists — only the remedy (`pnk upgrade`) is missing. KB-UPDATES.md's own axis table (line 33) already rates axis 4 "◐ **half closed**", so DESIGN and the document it points at disagree.

**Evidence.** Ran against a scratch KB whose manifest records `notes@1.0`: `uv run pnk doctor --kb /private/tmp/.../scratchpad/kb1` → `WARN template: KB says notes@1.0, installed is notes@1.1` / `→ Templates version independently of the package; nothing is applied automatically.` Source: `src/pinakes/doctor.py:219-225`; `src/pinakes/templates/notes/template.toml` → `version = "1.1"`; docs/KB-UPDATES.md:33 `| 4 | **Manifest + template** | … | ◐ **half closed** |`.

**Fix.** Rewrite the axis-4 sentence to say detection exists and only adoption is missing — e.g. "a template's drift is *detected* (`pnk doctor` compares the recorded version against the installed one) but not *remedied*: the fix touches a file the user owns, so it cannot borrow axes 1-3's free-rebuild shape." Drop "the only one with no mechanism" and "drift *silently*".

## `docs/DESIGN.md:715` — false · CONFIRMED

**Claims.** §6.1: "[KB-UPDATES.md](KB-UPDATES.md) works the problem through and records what has been decided; none of it is built."

**Actually.** At fc0fd41 three of KB-UPDATES.md's decisions are built. (1) `[kb] requires_pinakes` — KB-UPDATES §4 "Decided" itself says "**built in G4**" — and DESIGN's own §2.1 (lines 129-140) describes it as live behaviour, so the document contradicts itself. (2) T1 built KB-UPDATES §9's first step, "Bump the `notes` template version whenever its content changes" (`notes` is now 1.1). (3) T1 built KB-UPDATES §6/§9's template-drift CI gate. What is genuinely still unbuilt is `pnk upgrade` (§5 of KB-UPDATES) — and DESIGN describes it in the present tense at line 707 with no ⏳ pending note, so once this sentence is corrected nothing in DESIGN says `pnk upgrade` does not exist.

**Evidence.** `grep -n "requires_pinakes" src/pinakes/manifest.py` → `282:REQUIRES_PINAKES = "requires_pinakes"` / `287:    """`[kb] requires_pinakes` — refuse a KB this build is too old to read (G4).`; docs/KB-UPDATES.md:83 `**`[kb]` gains `requires_pinakes`** — **built in G4**`; `git show fc0fd41 --stat` lists `tools/template_drift_gate.py | 629 +`, `src/pinakes/templates/_versions.toml | 12 +`, `src/pinakes/templates/notes/template.toml | 2 +-`; `check.sh:191` → `uv run --frozen python3 tools/template_drift_gate.py`; `.github/workflows/ci.yml:298` → job `template-drift`; `uv run pnk --help` lists no `upgrade` command.

**Fix.** Replace with what is actually built and what is not, e.g.: "[KB-UPDATES.md](KB-UPDATES.md) works the problem through. `[kb] requires_pinakes` (§2.1) and the template-version archive plus its drift gate are built; `pnk upgrade` is not — it belongs to the template release." Keep an explicit statement that `pnk upgrade` does not exist yet, since line 707 describes it in the present tense.

## `docs/GUIDE.md:3` — stale · CONFIRMED

**Claims.** "Every command here was run against 0.2.0 (20260728 16:40); the output shown is real."

**Actually.** The installed build is 0.16.0, and the guide documents commands that did not exist at 0.2.0 — `pnk budget` shipped 0.3.0, `pnk links` 0.5.0, `pnk link` 0.6.0, and the per-kind structural-graph line only exists since the graph release. Two of its fences (`:80`, `:114`) are now demonstrably not what the commands print, so the sentence licenses output it no longer covers.

**Evidence.** $ uv run pnk --version → `pinakes 0.16.0`; src/pinakes/__init__.py:7 `__version__ = "0.16.0"`. docs/STATUS.md:26-28 — "| `pnk budget` | shipped 0.3.0 |", "| `pnk links` | shipped 0.5.0 |", "| `pnk link` | shipped 0.6.0 |".

**Fix.** Re-run the walkthrough and restamp the line with the version and UTC timestamp actually used, e.g. "Every command here was run against 0.16.0 (YYYYMMDD HH:MM, UTC); the output shown is real." — and re-verify each fence at the same time.

## `docs/GUIDE.md:93` — false · CONFIRMED

**Claims.** The "You get:" tree after `pnk init` lists exactly three entries: `pinakes.toml`, `docs/`, `.gitignore`.

**Actually.** `pnk init` also creates `eval/questions.yaml` and `README.md`. The omission bites later in the same document: line 266 tells the reader to "write questions with known-correct sources in `eval/questions.yaml`" without the tree ever showing that the template already scaffolds that file.

**Evidence.** $ find $SC/my-kb | sort
…/my-kb/.gitignore
…/my-kb/docs
…/my-kb/eval
…/my-kb/eval/questions.yaml
…/my-kb/pinakes.toml
…/my-kb/README.md
Template source: src/pinakes/templates/notes/{README.md,eval/questions.yaml,pinakes.toml.j2,template.toml}

**Fix.** Add the two missing rows, e.g. `├── eval/questions.yaml  # a golden set to start; ships empty on purpose` and `├── README.md        # what the template is, and how to use it`.

## `docs/GUIDE.md:305` — false · CONFIRMED

**Claims.** "a second sync finding a live lock exits 0 quietly, and `pnk doctor` reports any held lock with its age."

**Actually.** `pnk doctor` reports the holder and the time the lock was taken — never a computed age. This also contradicts the same document's Troubleshooting row at line 457, which states the opposite and is the correct one: "`pnk doctor` reports the holder and the time the lock was taken, never a computed age".

**Evidence.** src/pinakes/lock.py:45-46 — `def describe(self) -> str: return f"pid {self.pid} on {self.host}, since {self.started}"`; src/pinakes/doctor.py:1232-1238 — `Check("sync lock", Status.WARN, f"held by {holder.describe()}", …)`. The "exits 0 quietly" half is correct: src/pinakes/cli.py:633,664 print `another sync is already running; nothing to do.`

**Fix.** Replace "with its age" with "naming the holder (pid, host) and the time it was taken", matching line 457.

## `docs/KB-UPDATES.md:24` — false · MISSED-BY-FINDER

**Claims.** "For the second there is one deferred command (`pnk upgrade`, the template release) and no detection at all — while v0.2 is actively changing what the template ships."

**Actually.** Detection exists on both sides at fc0fd41, and the release clause is fourteen minors out of date. Repo-side: tools/template_drift_gate.py runs from check.sh:191 and from its own `template-drift` CI job. KB-side: `pnk doctor` WARNs on a template version mismatch, and since T1 bumped notes to 1.1 it fires on every pre-T1 KB. The package is at 0.16.0, not v0.2.

**Evidence.** `grep -n template_drift check.sh .github/workflows/ci.yml` → `check.sh:191: uv run --frozen python3 tools/template_drift_gate.py`; `.github/workflows/ci.yml:324` inside the `template-drift:` job declared at ci.yml:298. `uv run --frozen pnk doctor --kb <scratch>` on a KB recording `notes@1.0` → `WARN template: KB says notes@1.0, installed is notes@1.1`. `grep -n __version__ src/pinakes/__init__.py` → `0.16.0`.

**Fix.** Rewrite §1's closing sentence: detection now exists (the repo-side drift gate and `pnk doctor`'s template WARN); what is still absent is adoption (`pnk upgrade`). Drop "while v0.2 is actively changing what the template ships" or restate it in the past tense.

## `docs/MANIFEST.md:3` — stale · CONFIRMED

**Claims.** "Field-by-field, with defaults taken from `manifest.py` at 0.2.0 (20260728 16:40)."

**Actually.** The file documents keys and defaults that did not exist at 0.2.0, and the installed version is 0.16.0. `[chunking] headings` arrived at 0.13.0, `[chunking] metadata` at 0.16.0, `[retrieval] graph_channel` and `adjacent_k` later still, and `per_operation_eur`/`monthly_eur` were raised on 20260803 — all of which this same file describes. The provenance line understates the file by fourteen minor releases.

**Evidence.** `grep -n __version__ src/pinakes/__init__.py` → `0.16.0`. The file's own rows: `:133` "(0.13.0)", `:134` `metadata` (0.16.0 per docs/STATUS.md:67), `:190` "Raised from `0.05` on 20260803", `:192` "Raised from `5.00` on 20260803".

**Fix.** Restamp the provenance to the version and UTC timestamp at which the table was last verified against `manifest.py`.

## `docs/README.md:98` — inconsistent · MISSED-BY-FINDER

**Claims.** Landing-a-new-increment step 6: 'A [`changelog.d/`](../changelog.d/README.md) fragment — one file, named `<category>-<slug>.md`, in the same commit as the code.'

**Actually.** The required fragment filename carries a UTC timestamp prefix: `YYYYMMDD_HHMM-<category>-<slug>.md`. docs/README.md is the routing table an agent reads when landing an increment, and it gives the pre-20260804 form, so an agent following it writes a fragment that violates the convention its own linked owner-document states.

**Evidence.** `sed -n '97,98p' docs/README.md` → "6. **A [`changelog.d/`](../changelog.d/README.md) fragment** — one file, named / `<category>-<slug>.md`, in the same commit as the code." Against the fact's owner, `changelog.d/README.md` § Naming: "changelog.d/YYYYMMDD_HHMM-<category>-<slug>.md" … "`YYYYMMDD_HHMM` is when the fragment was written, **UTC** — **read the clock, never compose it** (`date -u "+%Y%m%d_%H%M"`) … `tools/fragments.py` strips it before reading the category". CLAUDE.md § Docs states the same rule for `plans/`, `changelog.d/` and `retro.d/`. The one unreleased fragment on disk follows the prefixed form: `ls changelog.d/` → `20260807_1929-added-template-version-archive.md`. Note the same superseded form also survives in `changelog.d/README.md`'s own two examples and in `tools/fragments.py --help` ('a change writes `changelog.d/<category>-<slug>.md`' … '`added-record-fixtures.md`'), so the docs/README.md line is one instance of an unswept rename rather than an isolated slip — but docs/README.md is the file an implementer is routed to.

**Fix.** Change step 6 to read `YYYYMMDD_HHMM-<category>-<slug>.md` (UTC, read off the clock), matching `changelog.d/README.md` § Naming. Sweeping the stale examples in `changelog.d/README.md` and `tools/fragments.py`'s help text at the same time would remove the rest of the class.

## `docs/VERIFICATION.md:28` — broken-reference · MISSED-BY-FINDER

**Claims.** "The gap is now four releases wide and is on [`plans/20260731_1202-open-corrections.md`](…)'s neighbourhood rather than lost." — i.e. the un-rowed 0.13.0–0.16.0 releases are tracked in that file.

**Actually.** `plans/20260731_1202-open-corrections.md` holds no such item, and by its own header it cannot: it says documentation items were removed from it when docs ownership moved to the planner, and that what remains is code and tooling only.

**Evidence.** `grep -n "neighbourhood|un-rowed|no rows|0\.13\.0 through|VERIFICATION" plans/20260731_1202-open-corrections.md` → no match for the gap; the only `verification` hit is line 101, a *closed* row ("The verification table named two tests that do not exist | Repointed; tests/test_verification.py green"), a different item. Lines 11-14 of that file: "**Documentation items are no longer here.** Since the ownership decision (20260801 01:24, `CLAUDE.md`) every `docs/**`, `plans/**`, `README.md`, `CLAUDE.md` and `CHANGELOG.md` correction is the planner's, and this file held six. … What remains below is code and tooling." Its `## Live` section (lines 31-71) holds exactly two items: `graph_gate.check_identity` is blind to `chunking`, and `--rebuild` never re-chunks a protected paid document.

**Fix.** Either drop the claim that the gap is tracked there and state plainly that it is untracked, or point at a file that actually holds it (the planner's own docs backlog), since open-corrections is by rule closed to documentation items.

## `docs/graph/PINAKES_APPROACH.md:7` — false · MISSED-BY-FINDER

**Claims.** The header banner's reconciliation: "[plans/20260729_0256-links-and-graph.md] sequences both and wins wherever it and §10 disagree about **what is built when**. The reasoning here is untouched and still governs *what* to build." (lines 6-8). It names exactly one thing that has since changed — §10's single "the graph release" splitting into the links release and the graph release.

**Actually.** The plan records nine departures from this document, in a section titled "## APPROACH amendments" (plans/20260729_0256-links-and-graph.md:265-278), and at least two of them are reversals of *what* to build rather than of *when*: decision 8 cut `pinakes_search`'s `entities`/`concepts` parameters outright ("not built", Lands-in column empty — they were never assigned to an increment), and decision 17 fixed traversal `confidence` at `unknown` unconditionally, the row itself annotated "L5, amending APPROACH §5". Four of the nine amend §5, one amends §3, one §9, one §10. So the sentence "the reasoning here is untouched and still governs what to build" is false, and the banner's "what is built when" scoping leaves a reader of §3, §5 and §9 with no pointer to the eight amendments the banner does not mention.

**Evidence.** `awk 'NR>=1 && NR<=12' docs/graph/PINAKES_APPROACH.md` → line 7-8: "> sequences both and wins wherever it and §10 disagree about what is built when. The reasoning here / > is untouched and still governs *what* to build." · `sed -n '265,278p' plans/20260729_0256-links-and-graph.md` → the "## APPROACH amendments" table, nine rows, including "| §5 | `confidence` on a traversal response is always `unknown` (decision 17) | L5 |", "| §5, §10 | `pinakes_search`'s `entities`/`concepts` parameters are not built (decision 8) | — |", "| §3 | The zero-link nudge is **KB-wide**, not \"warn on zero-link docs\" … | L7 |", "| §5 | The neighbour shape gains `kb_id` and loses `title` for cross-KB neighbours | L4 |", "| §3 | Weights are frozen, not fitted | G3 |", "| §9 | Its `expand` gate demands **false-abstain flat** … | G5 |". Confirmed in code: `grep -rn "concepts" src/pinakes/` returns nothing; src/pinakes/serve.py:279 returns `"confidence": "unknown"` unconditionally; src/pinakes/doctor.py:1027 gates the nudge on `if not authored:`.

**Fix.** Extend the banner to point at the plan's "APPROACH amendments" table as the authority for §3, §5 and §9 as well as §10 — e.g. replace "wins wherever it and §10 disagree about what is built when. The reasoning here is untouched and still governs *what* to build" with "wins wherever it and this document disagree; its **APPROACH amendments** table lists the nine departures taken since, four of them in §5. The reasoning here is left as written." Do not edit §3/§5/§9 themselves — "left as written" is the convention.

# Low — 27 findings

## `README.md:97` — false · ADJUSTED

**Claims.** ⚠️ Two things `pnk init` cannot know, **each needing one manifest edit**: on a `[light]` install set `provider = "fastembed"`, and to index PDFs add `"**/*.pdf"` to `[sources] include`.

**Actually.** README.md:97's "each needing one manifest edit" undercounts the `[light]` case: that edit changes `provider` in two blocks, `[embedding]` and `[rerank]` (docs/GUIDE.md:161-174, src/pinakes/errors.py:172). README does not name a block, so it misdirects nobody and links to the Guide section that is correct; the fix is wording, e.g. "each needing one manifest edit (the `[light]` one touches both `[embedding]` and `[rerank]`)".

**Evidence.** `docs/GUIDE.md:162-174`: "**On a `[light]` install, edit `pinakes.toml` before your first sync** — set `provider` in *both* blocks", with a fence showing `[embedding] provider = "fastembed"` and `[rerank] provider = "fastembed"  # this one too`. `docs/STATUS.md:124-125`: "set `provider = "fastembed"` in **both** `[embedding]` and `[rerank]`". `src/pinakes/errors.py:172`: `f'`provider = "{alternative}"` in both `[embedding]` and `[rerank]` in '`. Run on a fresh `pnk init` KB with only fastembed present, `pnk doctor` prints two separate failures — `FAIL embedding:` and `FAIL reranker:` — each with the remedy "Set `provider = "fastembed"` in both `[embedding]` and `[rerank]`".

**Fix.** Change to "…the first needing two manifest edits, the second one" and spell it out: "on a `[light]` install set `provider = "fastembed"` in **both** `[embedding]` and `[rerank]`, and to index PDFs add `"**/*.pdf"` to `[sources] include`."

## `docs/CLI.md:23` — missing · CONFIRMED

**Claims.** The file's scope is "Every command and flag on the `pnk` surface" (line 3), and the Common flags table lists only `--kb` and `--offline`.

**Actually.** `pnk --version` is a shipped top-level flag and appears nowhere in CLI.md; `pnk` with no command prints help and exits 0, also undocumented.

**Evidence.** `uv run pnk --version` → `pinakes 0.16.0`. Source: src/pinakes/cli.py:901 — `parser.add_argument("--version", action="version", version=f"pinakes {__version__}")`; cli.py:915-918 — no runner → `parser.print_help(); return EXIT_OK`.

**Fix.** Add a top-level row or a one-line note: `pnk --version` prints the installed package version; `pnk` alone prints help and exits 0.

## `docs/CLI.md:26` — inconsistent · CONFIRMED

**Claims.** Common flags table: "`--offline` | `sync`, `search`, `serve`"

**Actually.** `--offline` is also on `pnk links` — and CLI.md's own `pnk links` synopsis (line 415) lists `[--offline]`, so the file contradicts itself.

**Evidence.** `uv run pnk links --help` → `usage: pnk links [-h] [--kb PATH] [--rel REL] [--direction {out,in,both}] [--depth DEPTH] [--query QUERY] [--offline] [--json] document`. Source: src/pinakes/cli.py:743 in `_links_arguments`.

**Fix.** Change the `On` cell to `sync`, `search`, `links`, `serve`.

## `docs/CLI.md:76` — inconsistent · ADJUSTED

**Claims.** The `pnk sync` synopsis lists `[--offline]` twice — once on line 76 and again on line 77.

**Actually.** docs/CLI.md:76-77 prints `[--offline]` twice in the `pnk sync` synopsis; it is one flag. The differing flag order versus `pnk sync --help` is not a defect and should be dropped from the finding.

**Evidence.** docs/CLI.md:76 `pnk sync [--kb PATH] … [--offline] [--scan-links]` and :77 `[--offline] [--force-unlock] …`. `uv run pnk sync --help` → `usage: pnk sync [-h] [--kb PATH] [--rebuild] [--sidecars-only] [--index-only] [--stage] [--offline] [--scan-links] [--force-unlock] [--extract BACKEND] [--estimate-only] [--force] [--clear-cache [paid]] [--yes] [-q]`.

**Fix.** Delete the duplicate `[--offline]` on line 77 and match `--help`'s order.

## `docs/CLI.md:94` — inconsistent · CONFIRMED

**Claims.** `--extract BACKEND` … "an unknown name is a usage error before any extra could matter".

**Actually.** An unknown backend name is not a usage error: it is a `PinakesError` raised after parsing and exits 1. The exit-code table at line 17 says exactly that ("An unknown **backend name** is not one of these: it is caught after parsing and exits `1`"), so the two statements conflict.

**Evidence.** `uv run pnk sync --extract=bogus` → `error: no backend is registered for provider 'bogus'.` / `Known providers: claude-vision, fake, pypdfium2.` with exit status 1 (measured). Compare an argparse choices violation: `uv run pnk links docs/loans.md --direction sideways` → exit 2.

**Fix.** Reword line 94 to "…so an unknown name is refused before any extra could matter — as a `PinakesError`, exit 1, not an argparse usage error (see Exit codes)".

## `docs/CLI.md:179` — missing · ADJUSTED

**Claims.** `pnk doctor` "Reports environment …, backend and cached weights, template drift, index/model coherence, extraction coherence, calibration validity, orphaned sidecars, duplicate IDs, dangling links and link coverage, …" — an enumeration of every check.

**Actually.** docs/CLI.md:179-186 enumerates `pnk doctor`'s checks as though exhaustively, but seven of the 33 shipped checks are absent from it: `linked KBs`, `pdf extractor`, `sidecars`, `index`, `awaiting paid extraction`, `paid extraction not requested` and `paid extraction stale`. `model cache` is NOT missing — it is covered by "backend and cached weights".

**Evidence.** `uv run pnk doctor` on a scratch KB printed 33 check lines including `OK pdf extractor: pypdfium2 importable`, `OK sidecars: 1 readable`, `OK linked KBs: none declared`, `OK awaiting paid extraction: none`, `OK paid extraction not requested: none`, `OK paid extraction stale: none`, `OK index: 1 active documents, 2 chunks`, `OK model cache: weights resolve under …`. Sources: src/pinakes/doctor.py:274-305 (`pdf extractor`), :329 (`sidecars`), :426-439 (`_drift_check` trio), :463 (`index`), :256 (`model cache`), :1171-1222 (`linked KBs`).

**Fix.** Add the missing checks to the sentence (or state that the list is the notable subset, not the whole set).

## `docs/CLI.md:255` — false · CONFIRMED

**Claims.** "Every non-OK check carries a remedy."

**Actually.** One check yields a WARN with `remedy=None`: `calibration`, when `[retrieval.confidence]` thresholds exist but the reranker cannot be loaded offline to fingerprint it.

**Evidence.** src/pinakes/doctor.py:793 — `return Check("calibration", Status.WARN, f"fitted for {thresholds.fitted_for}", None)` (inside `_calibration`, the `except PinakesError` branch).

**Fix.** Either soften the sentence ("almost every non-OK check carries a remedy — the one exception is `calibration` when the reranker cannot be loaded to fingerprint it") or file the missing remedy as the bug the doc's own line 19 invites.

## `docs/CLI.md:298` — stale · CONFIRMED

**Claims.** "`monthly_eur` is per KB. Ten paid KBs have ten monthly allowances. v0.2 adds no global cap…"

**Actually.** The released version is 0.16.0, and the runtime line this paragraph describes says "There is no global cap in this release" — no version. CLI.md's own header (line 5) states "…which is why no version is quoted here", so both this `v0.2` and the `(0.2.2)` at line 107 break the file's stated rule and read as if 0.2 were current.

**Evidence.** `uv run pnk budget` prints: "`monthly_eur` is per KB: ten paid KBs have ten monthly allowances. There is no global cap in this release." (src/pinakes/cli.py:398-401). `src/pinakes/__init__.py` → `__version__ = "0.16.0"`. docs/CLI.md:5 — "whether a given surface is in a release yet is STATUS.md, which is why no version is quoted here". docs/CLI.md:107 — "named, not silently skipped (0.2.2)".

**Fix.** Drop the version: "Pinakes adds no global cap and says so rather than leaving a reader to assume one." Same for the `(0.2.2)` at line 107 — the release a behaviour landed in belongs in STATUS/CHANGELOG.

## `docs/CLI.md:468` — broken-reference · CONFIRMED

**Claims.** Planned table: "each names the increment that lands it ([STATUS](STATUS.md#v02-increment-ledger))".

**Actually.** The link resolves but does not hold what is claimed: `## v0.2 increment ledger` is the historical I1–I9 table for v0.2 and names neither the deep release nor the template release. Those live in `## Release roadmap` (STATUS.md:254, with the rows at 264-265 and 306-307) and in `## The surface you can use today` (STATUS.md:28, 43). The column is also labelled "Increment" while its values are release *names*, which is what the naming rule requires.

**Evidence.** `grep -n '^#\{1,3\} ' docs/STATUS.md` → `129:## v0.2 increment ledger`, `254:## Release roadmap`; `sed -n '129,160p' docs/STATUS.md` shows rows I1–I9 only; `grep -n 'the deep release\|the template release' docs/STATUS.md` → lines 28, 43, 264, 265, 306, 307 — none inside 129-187.

**Fix.** Point at `STATUS.md#release-roadmap` and reword to "each names the release that lands it".

## `docs/DESIGN.md:5` — stale · ADJUSTED

**Claims.** Header: "**Design date:** 20260725 09:52 (review pass 7) · **Last reviewed against the code:** 20260728 16:40"

**Actually.** docs/DESIGN.md:5's "Last reviewed against the code: 20260728 16:40" is the file's only currency signal and has not moved through 12 later amendments. It is not itself false, and its local-time format is permitted; the defect is that it advertises a currency the file demonstrably lacks — at fc0fd41 §4.6 (line 525), §6.1 (lines 711, 715) and §6.1-vs-§7 (line 699) each hold a claim the code contradicts.

**Evidence.** `git log -L 5,5:docs/DESIGN.md` → the line was introduced by `01c60db 2026-07-28 16:54:15 +0200` and never modified since; `git log --format="%h %ad %s" --date=short -8 -- docs/DESIGN.md` → 8 commits from 2026-07-28 through `54530e5 2026-08-06`; `src/pinakes/store.py:28` → `SCHEMA_VERSION: Final = 3`.

**Fix.** Refresh the stamp when a review actually happens (`date -u "+%Y%m%d %H:%M"`, and say UTC since the current value predates the 20260804 11:32 UTC switch), or drop the field and let STATUS.md carry currency.

## `docs/DESIGN.md:524` — broken-reference · CONFIRMED

**Claims.** §4.6 names "the **`in-section`, `parent` and `child` edges** derived from it".

**Actually.** There is no `parent` edge kind and no `child` edge kind. The single hierarchy kind is `parent-child`, which is what DESIGN's own §3.2 table (line 280) and the code both use. A reader who takes these as kind names — e.g. to pass `--drop parent` to the graph tools, which validate kind spellings — gets nothing.

**Evidence.** `grep -rn '"parent"|"child"|parent-child' src/pinakes/ --include="*.py"` → `store.py:40: "parent-child",`, `store.py:176: 'membership', 'sibling', 'parent-child', 'in-section', 'co-located', 'shared-tag'`, `graph/edges.py:106: SYMMETRIC_KINDS: Final = frozenset({"membership", "sibling", "parent-child", AUTHORED})`, `graph/channel.py:113: _CHUNK_PEER_KINDS: Final = frozenset({"sibling", "parent-child"})`; no match for a bare `parent` or `child` kind. docs/DESIGN.md:280 → `| `parent-child` | chunk ↔ chunk, `heading_path` prefix | parent → child | 1.0 |`.

**Fix.** Change to "the **`in-section`** and **`parent-child`** edges derived from it".

## `docs/DESIGN.md:763` — superseded · CONFIRMED

**Claims.** §6.2: "If it bites, federated query is the v2 answer." (Same pattern at line 63, "no fan-out query in v1", and line 213, "Mitigations, all v1".)

**Actually.** Federated / fan-out query is unbuilt, and the project's rule is that unbuilt work is named, never numbered ("Never write `v0.4` for something unbuilt — not in docs, `--help`, an error message or a code comment"; CHANGELOG, RETROSPECTIVES, plans/ and docs/graph/ are the only exemptions). DESIGN.md is also deliberately version-free. §8 of this same file states the rule explicitly at lines 1153-1155 — "The labels below are the names this project has long used for each body of work, not committed version numbers" — so the file contradicts its own stated convention. There has never been a v1 or v2; the latest release is 0.16.0.

**Evidence.** `grep -n "v0\.[0-9]|v1\b|v2\b" docs/DESIGN.md` → `63:| Federation | Cross-KB links you can follow (no fan-out query in v1) |`, `213:… Mitigations, all v1:`, `763:mysterious. If it bites, federated query is the v2 answer.`; docs/DESIGN.md:1153-1155 states the naming rule; `src/pinakes/__init__.py` → `__version__ = "0.16.0"`. The two named unbuilt releases in this project are "the deep release" and "the template release" (CLAUDE.md § Unbuilt work is named, never numbered).

**Fix.** Line 763: "If it bites, federated query is the answer, and it is not in scope here." Line 63: "(no fan-out query — cross-KB questions travel by link)". Line 213: name the mitigations as shipped rather than dating them to a release number.

## `docs/GUIDE.md:9` — inconsistent · CONFIRMED

**Claims.** The table of contents (lines 9-18) lists the guide's sections.

**Actually.** It lists 10 of the 12 `##` sections. Missing: "Watching what it costs" (line 307) and "Following links between two KBs" (line 465) — the latter is a destination the body links to at line 440.

**Evidence.** $ grep -n "^## " docs/GUIDE.md
22:## Install / 73:## Your first KB / 160:## Choosing a backend / 183:## Indexing PDFs / 225:## Searching / 273:## Keeping the index fresh / 307:## Watching what it costs / 338:## Using it from an agent / 411:## Health checks / 425:## Moving, sharing and publishing a KB / 442:## Troubleshooting / 465:## Following links between two KBs — TOC at 9-18 omits 307 and 465.

**Fix.** Add `- [Watching what it costs](#watching-what-it-costs)` after "Keeping the index fresh", and `- [Following links between two KBs](#following-links-between-two-kbs)` after "Troubleshooting".

## `docs/GUIDE.md:190` — false · CONFIRMED

**Claims.** The § Indexing PDFs fence shows `pnk sync` printing two lines: the counts line, then the `1 file(s) matched no `include` pattern: .pdf (1) — …` line.

**Actually.** `pnk sync` prints three lines — the structural-graph line sits between them. The counts line and the unmatched-pattern line are otherwise byte-exact.

**Evidence.** $ uv run pnk sync --kb $SC/pdfkb
0 indexed, 0 renamed, 0 metadata-only, 0 unchanged, 0 removed
0 edge(s) derived in 0.00s, 0 authored read from links: membership=0 sibling=0 parent-child=0 in-section=0 co-located=0 shared-tag=0 authored=0
1 file(s) matched no `include` pattern: .pdf (1) — add "**/*.pdf" to `[sources] include` to index them, or `exclude` them to silence this.

**Fix.** Insert the `0 edge(s) derived …` line between the two, as the first-sync fence at lines 142-145 already does.

## `docs/GUIDE.md:285` — false · CONFIRMED

**Claims.** The hook table's "Runs" column gives the literal commands: `pnk sync --sidecars-only --stage --extract=pypdfium2` (pre-commit) and `pnk sync --index-only --extract=pypdfium2` (post-commit, post-merge, lines 286-287).

**Actually.** Every installed hook also passes `--quiet`. The guide's own § Indexing PDFs (line 198) turns on that flag's behaviour ("`pnk sync --quiet` still prints it, on stderr"), so the omission hides why hooks are silent on success.

**Evidence.** $ uv run pnk install-hooks && cat .git/hooks/pre-commit | tail -1
exec pnk sync --sidecars-only --stage --quiet --extract=pypdfium2
$ cat .git/hooks/post-commit | tail -1
exec pnk sync --index-only --quiet --extract=pypdfium2
(install-hooks also prints the same command with --quiet in its foreign-hook message)

**Fix.** Add `--quiet` to all three cells.

## `docs/GUIDE.md:535` — false · CONFIRMED

**Claims.** The `$ pnk sync --scan-links` fence shows two output lines: `30 indexed, …` and `inbound links: museum 6`.

**Actually.** There is a third line — the structural-graph summary — after `inbound links`. The first two lines are byte-exact.

**Evidence.** $ cd $SC/kbs/archive && rm -rf .pinakes && uv run pnk sync --scan-links
30 indexed, 0 renamed, 0 metadata-only, 0 unchanged, 0 removed
inbound links: museum 6
180 edge(s) derived in 0.00s, 12 authored read from links: membership=60 sibling=30 parent-child=0 in-section=60 co-located=30 shared-tag=0 authored=12
(scratch copies of tests/demo-kb and tests/partner-kb, renamed archive/ and museum/ to match the prose)

**Fix.** Add the `180 edge(s) derived …` line to the fence.

## `docs/KB-UPDATES.md:30` — broken-reference · CONFIRMED

**Claims.** "`schema_version` mismatch → refuse to open, name `pnk sync --rebuild`. No migrations, by design (`store.py:205`)"

**Actually.** `store.py:205` is `raise StoreError(f"{path} already exists.", …)` inside `create()` — the "an index is already here" error. The schema-version refusal is `_check_schema_version` at `store.py:250`, comparing at line 258 and raising `IndexSchemaError` at 259.

**Evidence.** `grep -n "SCHEMA_VERSION" src/pinakes/store.py` → `250:def _check_schema_version`, `258:    if found != str(SCHEMA_VERSION):`, `259:        raise IndexSchemaError(...)`. `sed -n '201,210p' src/pinakes/store.py` shows `create()`'s already-exists raise at 205.

**Fix.** Cite `store.py:258` (or `store._check_schema_version` without a line number).

## `docs/KB-UPDATES.md:62` — broken-reference · ADJUSTED

**Claims.** §4's table cites `sidecar.py:35,106` for unknown keys preserved under `extra`, `_toml.py:184` for the manifest hard error, and `store.py:205` for `found != str(SCHEMA_VERSION)`.

**Actually.** docs/KB-UPDATES.md:62-64 — all three file:line citations in the §4 compatibility table point at unrelated code. `sidecar.py:35,106` are an `io` import and a blank line; `extra` is collected at sidecar.py:304 and written back at sidecar.py:564-565. `_toml.py:184` is inside `tables()`; the unknown-key hard error is `Table.done()` at _toml.py:194-204. `store.py:205` closes `create()`'s already-exists raise; the schema comparison quoted verbatim is store.py:258.

**Evidence.** `grep -n extra src/pinakes/sidecar.py` → `304:    extra = deepcopy({key: value for key, value in data.items() if key not in KNOWN_KEYS})`, `564-565` writing them back. `grep -n "unknown key\|def done" src/pinakes/_toml.py` → `194:    def done(self)`, `198: f"unknown key(s): {unknown}"`. `grep -n SCHEMA_VERSION src/pinakes/store.py` → `258:    if found != str(SCHEMA_VERSION):`.

**Fix.** Re-derive the three citations (`sidecar.py:304,564`, `_toml.py:194`, `store.py:258`), or drop line numbers for function names, which is what the rest of the repo's docs do.

## `docs/KB-UPDATES.md:88` — false · CONFIRMED

**Claims.** The illustrated refusal `error: this KB requires pinakes >= 0.3 (this build is 0.2.1)`

**Actually.** That line is unreachable as printed. The message interpolates the manifest's raw string, and a floor written with a space (`">= 0.3"`) is refused earlier as an unreadable version — `manifest.py` deliberately does not `.strip()`. The real output also carries the manifest path and the `[kb]:` table prefix.

**Evidence.** `src/pinakes/manifest.py:335` `required = _version_tuple(raw.removeprefix(REQUIRES_PREFIX))` with the comment "No `.strip()`. It would accept `\">= 0.9\"`…"; `:365` `message=(f"this KB requires pinakes {raw} (this build is {__version__})")`. Measured with `requires_pinakes = ">=99.0"`: `error: /…/pinakes.toml [kb]: this KB requires pinakes >=99.0 (this build is 0.16.0)`.

**Fix.** Show the message the code emits, without the space: `error: <path> [kb]: this KB requires pinakes >=0.3 (this build is 0.2.1)`.

## `docs/MANIFEST.md:111` — missing · CONFIRMED

**Claims.** `[extraction]` table row: "`model` | (blank Default) | Consulted only when `backend = \"claude-vision\"`" — in a file that states "This file is the reference — if a field's default is stated anywhere else in the repo, that copy is the stale one."

**Actually.** `[extraction] model` has a code default of `claude-opus-5`, applied both when the `[extraction]` table is absent and when the key is omitted from it. The reference's Default column is empty, so a reader cannot learn which model the paid path would use.

**Evidence.** `src/pinakes/manifest.py:98` `EXTRACTION_MODEL_DEFAULT = "claude-opus-5"`; `:638` `return ExtractionSection(backend=EXTRACTION_BACKEND_DEFAULT, model=EXTRACTION_MODEL_DEFAULT)`; `:643` `model=table.string_or("model", EXTRACTION_MODEL_DEFAULT)`. No other `docs/*.md` states this default — grep finds `claude-opus-5` only as an explicitly written value in docs/MEASUREMENT-RUN.md:95 and as measurement prose in docs/DESIGN.md/STATUS.md.

**Fix.** Fill the Default cell with `claude-opus-5`.

## `docs/MANIFEST.md:176` — missing · CONFIRMED

**Claims.** `[rerank]` table row: "`provider` | (blank Default) | `sentence-transformers` or `fastembed` — set this too on a `[light]` install", beside `model` whose default IS given.

**Actually.** `[rerank] provider` defaults to `sentence-transformers`, both when the `[rerank]` table is absent and when the key is omitted. The blank cell next to a populated one for `model` reads as "no default / required", which it is not. (`revision`'s blank cell is correct — it really has none.)

**Evidence.** `src/pinakes/manifest.py:765-766` `return RerankSection(provider="sentence-transformers", model="BAAI/bge-reranker-base", revision=None)`; `:769` `provider=table.string_or("provider", "sentence-transformers")`.

**Fix.** Put `sentence-transformers` in the Default cell for `[rerank] provider`.

## `docs/MEASUREMENT-RUN.md:168` — stale · ADJUSTED

**Claims.** The "## Afterwards" checklist is written as pending work — "`prices.toml` **gains** the measured per-page constant…", "DESIGN §9 **gains** the scanned-quality numbers", "STATUS.md **drops** 'output quality is not yet measured', and the release **can be cut** saying what it measured".

**Actually.** docs/MEASUREMENT-RUN.md:175-176, Afterwards item 5, is stale: it instructs the reader to drop 'output quality is not yet measured' from STATUS.md — a phrase `grep -n "output quality" docs/STATUS.md` no longer finds — and says 'the release can be cut', for a release already cut. Items 1-3 are valid re-run instructions and are not stale (item 3's section number is wrong, which is finding 7); item 4 is finding 4.

**Evidence.** `cat src/pinakes/budget/prices.toml` → `measured_on = "tests/pdf-corpus (synthetic), 20260729 03:17, claude-opus-5"` plus the measured input/output token comment block; `sed -n '1188p' docs/DESIGN.md` → the risk row with "1.000 char recall … measured 20260729 03:17, claude-opus-5, €0.11 spent"; `grep -n "output quality" docs/STATUS.md` → no match; `sed -n '206p' docs/STATUS.md` → "### The measurement run has been done — 20260729 03:17, €0.43".

**Fix.** Rewrite the section as what a *re-run* must update (per docs/README § Conventions: "Rewrite to the current state; do not layer corrections"), stating that the first run already landed items 1, 2 and 5 and naming what a second run would refresh.

## `docs/MEASUREMENT-RUN.md:172` — stale · CONFIRMED

**Claims.** Afterwards step 3: "**DESIGN §7.1** gains the free-vs-paid delta."

**Actually.** The free-vs-paid delta lives in DESIGN **§7.2**, a section created for it and titled "What bypassing `layout.py` on the paid path actually costs". §7.1 is "PDF extraction quality" — the free-path corpus scoring. STATUS.md links the delta to §7.2, not §7.1.

**Evidence.** `grep -n "^### " docs/DESIGN.md` → `1059:### 7.1 PDF extraction quality`, `1107:### 7.2 What bypassing \`layout.py\` on the paid path actually costs`; DESIGN.md:1109-1122 holds the measured per-fixture delta table; `docs/STATUS.md:215` → "([§7.2](DESIGN.md#72-what-bypassing-layoutpy-on-the-paid-path-actually-costs))".

**Fix.** Change "**DESIGN §7.1**" to "**DESIGN §7.2**" in step 3. (Step (c) at line 149 pointing the scanned-quality numbers at §9 is correct — they are in §9's PDF-extraction-quality risk row.)

## `docs/README.md:25` — missing · ADJUSTED

**Claims.** The doc table (lines 15-29) is presented as covering every file in `docs/`: "Two files sit outside the set above: `index.md` is the site's landing page … and **this file is excluded from the site**" (line 10-13).

**Actually.** The 'Where does a fact live?' routing table is complete for RELEASING.md (line 77), but the doc-inventory table at docs/README.md:17-29 omits a RELEASING.md row while including its extracted sibling BUILDING.md — an asymmetry, not a violation of the 'two files sit outside' sentence, which is about site membership rather than table coverage.

**Evidence.** `ls docs/` lists 14 `.md` files plus `graph/`; the table at docs/README.md:17-29 has rows for GUIDE, CLI, MANIFEST, MEASUREMENT-RUN, STATUS, ROADMAP, VERIFICATION, INVARIANTS, BUILDING, DESIGN, RETROSPECTIVES, KB-UPDATES and graph/ — thirteen rows, no RELEASING row. `grep -n "RELEASING" docs/README.md` → only lines 25 (inside the BUILDING row), 77 and 115.

**Fix.** Add a row after BUILDING.md, e.g. `| [**RELEASING.md**](RELEASING.md) | *How do I cut a release?* Fragments, version bump, tag, verification, and the three documents a release stales |`.

## `docs/STATUS.md:303` — inconsistent · MISSED-BY-FINDER

**Claims.** The release roadmap table lists `**0.15.1** ✅` after `**0.16.0** ✅`.

**Actually.** 0.15.1 was released before 0.16.0 (PyPI first uploads: 0.15.1 2026-08-06T00:56:59Z, 0.16.0 2026-08-07T11:52:31Z), and it is also lower in SemVer order. Every other ✅ row in the table is in release order, so this row is out of sequence on both readings.

**Evidence.** `grep -n "" docs/STATUS.md | sed -n '299,304p'` → 301 = `**0.15.0** ✅`, 302 = `**0.16.0** ✅`, 303 = `**0.15.1** ✅`. `curl -s https://pypi.org/pypi/pinakes/json` per-version first-upload times as above. Line 309-310 says "only the ✅ rows are facts", so the ordering of the ✅ rows is read as the release history.

**Fix.** Move the `0.15.1` row above the `0.16.0` row.

## `docs/VERIFICATION.md:27` — stale · ADJUSTED

**Claims.** "The scope began as `plans/20260727_1543-v0.2.md`'s promises … and has since taken in the links release, G1–G6, 0.7.1, and 0.12.0's five heading-coverage rows … **It stopped there: 0.13.0 through 0.16.0 added no rows.**"

**Actually.** The sentence `It stopped there: 0.13.0 through 0.16.0 added no rows` is true. The defect is the surrounding scope enumeration: it lists increment-level additions (G1–G6, 0.7.1) but not the T1 section added at :762, so the paragraph reads as a complete account of the table's growth when it is not.

**Evidence.** docs/VERIFICATION.md:762 `## The template version archive and its drift gate (T1)`, rows at :770-799. `git log --oneline -8 -- docs/VERIFICATION.md` → `b33414f T1 review fixes…`, `aa3cd53 T1: the template version archive…` sit on top of `5bc2df9 0.16.0 …`. `uv run pytest tests/test_verification.py -q` → `4 passed`, so every T1 row resolves.

**Fix.** Extend the enumeration to "…0.12.0's five heading-coverage rows, and T1's template-archive rows (merged to `main`, unreleased)", and rephrase "It stopped there" to state that the released gap is 0.13.0 through 0.16.0.

## `docs/graph/README.md:54` — broken-reference · MISSED-BY-FINDER

**Claims.** "Stated once in [PINAKES_APPROACH.md §\"License gate\"](PINAKES_APPROACH.md) and repeated here because the index is where someone starts." — cites a section of PINAKES_APPROACH.md named "License gate".

**Actually.** PINAKES_APPROACH.md has no section by that name. Its eleven `##` headings are §1 What the investigations changed, §2 The shape of the answer, §3 Sync time, §4 Query time, §5 The tool surface, §6 The paid path, §7 What Pinakes deliberately does not build, §8 ClaudeKB, §9 Eval gates, §10 Version mapping, §11 Summary. The licence text is a mid-paragraph sentence inside §1 (line 41, "License gate, stated once: LinearRAG and LogicRAG are GPL-3.0…"). The link resolves to the file, so mkdocs --strict stays green, but the § citation sends a reader hunting for a heading that has never existed.

**Evidence.** `grep -n 'License gate' docs/graph/README.md` → `54:[PINAKES_APPROACH.md §"License gate"](PINAKES_APPROACH.md) and repeated here because the index is`. `grep -n 'License gate\|Licence gate' docs/graph/PINAKES_APPROACH.md` → `41:License gate, stated once: LinearRAG and LogicRAG are GPL-3.0; Youtu-GraphRAG's LICENSE forbids`. `grep -n '^#' docs/graph/PINAKES_APPROACH.md` lists no "License gate" heading.

**Fix.** Cite the section that actually holds it: `[PINAKES_APPROACH.md §1](PINAKES_APPROACH.md#1-what-the-investigations-changed)`. Per docs/README.md:204, do not rename the APPROACH heading to make the citation true.
