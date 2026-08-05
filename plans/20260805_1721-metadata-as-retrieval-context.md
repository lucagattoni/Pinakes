# Is document metadata retrieval context? — the investigation, and what it gates

**Audience: the planner and the coder. Goal: executor.** Written 20260805 17:21 against `main` at
`3a4fa9e`, deliberately before a context compaction, so nothing below has to be rediscovered.

**The question.** Are `title` and `heading_path` *"fundamental context, useful for search and
retrieval"* (the user's claim, 20260805), or display-and-graph metadata? **Everything expensive
downstream — PDF layout heuristics, a paid title-inference call — is gated on the answer, and the
answer is one measurement nobody has run.**

---

## 1 · Facts established, with evidence — do not re-derive these

Each was verified against the code, not inferred. File references are `main` at `3a4fa9e`.

| Fact | Evidence |
|---|---|
| **Neither `title` nor `heading_path` affects retrieval today** | FTS5 indexes `chunks.text` only (`store.py:87-92`); embeddings are computed over `chunk.text` only (`sync.py:1940`); the reranker scores `passage.text` (`search.py:512`). No `WHERE`, `ORDER BY` or filter touches either field |
| **`heading_path`'s only consumers** | Citations (`search.py:79`), the `in-section`/`parent`/`child` edges and the `heading` node key (G3), and the passage payload on CLI (`cli.py:209`) and MCP (`serve.py:421`) |
| **`title`'s only consumers** | Search-result display (`cli.py:208`, `serve.py:331`), link listings (`cli.py:804` — `label = row.get("title") or row["doc_id"]`), and graph presentation, where it **counts against the traversal token budget** (`present.py:69`, `provider.py:192`) |
| **Losing `heading_path` costs zero recall** | By design: DESIGN §4.6 puts the heading *line* into the first chunk beneath it, so heading words stay searchable through `text`. This is why a 106 806-chunk corpus with **zero** heading paths passed every eval while bounding the graph release's gate — recall could not see it |
| **Titles never come from content, for any source type** | `skeleton()` is called without `title=` at both sites (`sync.py:1352`, `sync.py:1388`), so the filename-stem fallback (`sidecar.py:670`) always fires. Verified twice: a document whose H1 is `# Retrieval` synced to `title: retrieval`, and **all 30 `tests/demo-kb` titles equal their filename stem** — not one authored title in either committed corpus |
| **`[chunking] strategy` is inert** | `CHUNK_STRATEGIES = ("structural",)` (`manifest.py:59`), validated by `table.choice` (`manifest.py:615`), and **never read at runtime** — grep across `src/` finds no consumer. Only `max_tokens` is used from `[chunking]`. What dispatches is `source_type` |
| **`source_type` is assigned by suffix, and `text` is a fallback** | `chunk.py:78`. `.md/.markdown` → `markdown`; ten code suffixes → `code`; `.pdf` → `pdf`; **everything else** → `text`. So `text` today includes `.rst`, `.adoc`, `.org`, `.tex`, `.csv`, `.json`, `.yaml`, `.log` and extensionless files |
| **Heading detection is Markdown-only** | `chunk.py:131` — `blocks = _markdown_blocks(text) if kind == "markdown" else _plain_blocks(text)`; `_plain_blocks` sets `heading_path=None` unconditionally (`chunk.py:254`). **Nothing failed to match because nothing was tried** — the superseded diagnosis in the open corrections said a grammar failed to match, which would have sent an implementer to fix a regex that never ran |

---

## 2 · The critical-path measurement — step 2, and the reason the rest exists

**Hypothesis (the user's, stated precisely enough to be falsifiable).** A chunk taken from the
*middle* of a long section carries none of that section's vocabulary, because only the **first**
chunk beneath a heading contains the heading line. Injecting `title` and `heading_path` into the
text that is embedded and indexed should therefore raise recall on questions whose evidence sits in
continuation chunks.

**This is the strongest form of the claim and it is mechanistic, not aesthetic.** It is also the
only part that could make metadata "fundamental for retrieval" true rather than aspirational.

### The experiment

1. **Prepend** `title > heading_path` (exact form is the implementer's, recorded in the increment)
   to the text that is **embedded** and **indexed**, leaving `chunks.text` as returned to the user
   unchanged if that separation is feasible — **and say explicitly which of the two was done**,
   because "what is embedded" and "what is displayed" diverging is itself a design change.
2. **Rebuild** and run the golden-set eval.
3. **Report `recall@k`, MRR and false-abstain rate, before and after**, in the commit message.
   `CLAUDE.md` § *Changing retrieval* requires exactly this and forbids justifying it by intuition.

### The corpus problem — read this before planning the run

**Neither committed corpus can measure it, for opposite reasons:**

| Corpus | Why it cannot answer |
|---|---|
| `tests/demo-kb` | Documents are ~7 lines (median). **No section spans multiple chunks**, so there are no continuation chunks to rescue. The mechanism has nothing to act on |
| RFC realism corpus | Has the long sections, but **`heading_path` is zero everywhere** — there is nothing to inject |

**So the experiment is blocked on step 1** (the numbered-heading grammar), which is what gives the
RFC corpus real heading paths. That dependency is the single most important scheduling fact in this
plan: **the grammar is not a nice-to-have, it is the enabler of the first promising retrieval
experiment since the expansion channel failed its gate.**

### What each outcome licenses

* **Movement** → metadata is retrieval context; the claim is proven, and the expensive downstream
  work (PDF layout heuristics, paid title inference) becomes arguable on evidence.
* **No movement** → `title` and `heading_path` stay display-and-graph. **The expensive work dies
  cheaply, which is the point of running this first.**

**Anti-circularity applies in full**, as it did to the graph gate: questions stay frozen, nothing is
tuned after seeing a number, and a result short of the threshold is reported rather than retried
with a different injection format.

---

## 3 · The agreed order of work

Decided by the user 20260805 after options with trade-offs. **Do not reorder without a reason
recorded here.**

| # | Step | Blocked on | Cost |
|---|---|---|---|
| 1 | **Numbered-heading grammar for `.txt`** | **Nothing — unblocked 20260805 18:40.** All of §5 is settled: the key and vocabulary (§5.2) and the full predicate, written before any corpus was consulted (§5.3) | Moderate |
| 2 | **The injection experiment** (§2) | Step 1 | ~2 h rebuild + eval |
| 3 | **Markdown H1 → title** | ✅ **Done 20260805 22:30.** `first_h1()` in `chunk.py`, wired at mint time. Existing sidecars are never rewritten, so no migration | Small |
| 4 | **`pnk doctor` title check** (B3) | Nothing | Small |
| 5 | PDF layout heuristics + confidence scoring | **Step 2 showing movement** | High |
| 6 | Paid LLM title inference | **Step 2 showing movement** | High — the full paid-path apparatus |

**Steps 5 and 6 were argued against on current evidence and are not approved.** They are listed so
the reasoning is not relitigated: a confidence-scored heuristic before anything calibrates it
repeats the constant-nobody-calibrated defect this project has already learned once
(`_text_yield`'s reasoning, and the heading check's threshold-free predicate), and opening a paid
entry point for a field whose retrieval value is unmeasured spends the project's two most expensive
currencies — permanent maintenance surface and paid-path trust — on an unproven premise.

---

## 4 · Decisions already taken — settled, not to be relitigated

Full records: [`20260805_1313-decisions-init-titles-and-grammar.md`](20260805_1313-decisions-init-titles-and-grammar.md).

| Decision | Verdict |
|---|---|
| Grammar scope | **`.txt` only** for now. Not `.csv`/`.json`/`.yaml` — they have no headings and a line beginning `1.` is *data*, so a numbered grammar would manufacture structure from noise. Not `.rst`/`.adoc`/`.org` — they carry their own conventions and a numbered grammar would half-work, which is worse than not working. Not `code` |
| **PDF** | **Disabled, never dismantled.** Nothing built for PDF is removed, narrowed or weakened — the `[pdf]` extra, both extractors, the cache, `path:page` citations, corpus fixtures and every test stay exactly as they are. The decision declines to extend *one new grammar* to `pdf`. **If implementing appears to require changing existing PDF behaviour, that is a spec defect — stop and report it** |
| `requires_pinakes` | The new value **sets a floor explicitly**, so an older build says *"this KB requires pinakes >= X"* rather than rejecting the value as a typo — the confusion G4 exists to prevent |
| `pnk init` (A1) | Refuse only what would actually be overwritten; drop the blanket emptiness test |
| Titles (B1 + B3) | Keep the filename fallback; add a doctor check. **The first-line heuristic is rejected** — an RFC's first line is `Internet Engineering Task Force (IETF)`, so it would mint confidently wrong titles at scale into sidecars the user then commits, and a wrong title is harder to notice than an obviously-wrong one |

---

## 5 · Step 1's blocking questions — **all three settled; step 1 is unblocked**

### 5.1 · A new `strategy` value, or its own key? **DECIDED 20260805 18:25 by the user**

**Its own key, taking an enumerated value — not a `strategy` value, and not a boolean.**

    [chunking]
    strategy = "structural"    # unchanged, still inert
    headings  = "numbered"     # new, opt-in, `text` only

**Why not a `strategy` value.** `strategy` is inert (§1): validated by `table.choice` and never read
at runtime. A second accepted value makes it live for the first time, which forces `structural` to
be *defined* — and every manifest ever written already carries that value, so whatever definition is
chosen applies **retroactively to KBs nobody will revisit**. Inventing a contract for existing data
in order to add an opt-in feature is the wrong trade.

**Why not a boolean.** A boolean does not extend. The PDF path is *disabled, never dismantled*
(§4), so a second grammar is expected eventually — and with a boolean that means either a second
boolean or a migration to a value, i.e. **this same decision again, but with an installed base**.
An enumerated key absorbs it as `headings = "pdf-structural"` and touches nothing.

**What this leaves untouched, deliberately:** `strategy` stays inert, `structural` gains no new
meaning, and no existing manifest changes behaviour.

### 5.2 · The vocabulary — **SETTLED 20260805 18:40, planner's**

    [chunking]
    headings = "numbered"      # accepted: "none" (default) | "numbered"

**Key absent means `"none"`**, and `"none"` is also accepted explicitly — a default, not an
ambiguity. Writing it lets a manifest say *"this was considered"* rather than *"this predates the
feature"*, which are different facts about a KB.

**Never stamped into the template.** This follows `adjacent_k` and `graph_channel`, and the reason
is in `manifest.py:653` verbatim: `_toml.py` hard-errors on an unknown key, so a manifest carrying
the key **cannot be read at all** by any Pinakes built before it existed. Settable-but-unstamped
until a release deliberately accepts that break.

**A correction to §4's framing, from reading the parser.** §4 said a floor is needed because an
older build would reject the new *value* as a typo. With a new **key** the mechanics are
**identical, not worse**: `table.choice` hard-errors on an unknown value and `table.done()`
hard-errors on an unknown key, and G4's `requires_pinakes` pre-pass runs **over the raw TOML before
either** (`manifest.py:18-22`, and `manifest.py:450-457` for why the field must be consumed again
afterwards so strictness does not reject the very field that explains it). So a build with the
pre-pass — G4 shipped in 0.6.0 — reports *"this KB requires pinakes >= X"* for the key exactly as it
would for a value. Choosing a key over a value costs nothing here.

**The floor's version is set at the release that ships it**, per `CLAUDE.md`: unbuilt work is named,
never numbered.

### 5.3 · The false-positive predicate — **SETTLED 20260805 18:40, written before any corpus was consulted**

`1.` at line start is also an ordered list. This is the rule, stated in full **first**; the RFC
corpus is measured against it **second**.

**Line-level candidate — every clause must hold:**

1. The line starts at **column 0** — no leading whitespace.
2. It matches `^(\d+(?:\.\d+)*)\.?[ \t]+(\S.*)$` — a dotted-decimal number, optional trailing
   dot, whitespace, then non-empty text.
3. The text contains **no run of three or more dots** (`\.{3,}`). A dot leader marks a
   table-of-contents entry, which would otherwise duplicate every real section number.
4. The text is **≤ 100 characters** and does not end in `.`, `,`, `;` or `:`. A heading is a label;
   a sentence is not.
5. It is preceded by a **blank line**, or is the first line of the document.

**Document-level acceptance — the part that does the real work:**

6. The candidates, in order, must form a valid outline walk: each number is a **sibling increment**
   (+1 on the last component), a **first child** (`X` → `X.1`), or a **return to an ancestor's next
   sibling**. No number repeats.
7. There must be **at least two** candidates — one is more likely a stray list item than an outline.
8. **If the walk fails anywhere, the document yields no headings at all.**

**Clause 8 is the whole design.** The failure mode is *exactly today's behaviour* — no
`heading_path` — never a wrong one. An ordered list restarting at `1.` breaks the walk and
disqualifies its document rather than minting confident nonsense. This is the same judgement the
title decision already made: a visibly absent value beats a plausible wrong one, because a wrong one
is harder to notice.

**Bounds, stated now rather than discovered later:**

* A document mixing a genuine numbered outline with an ordered list is **rejected whole**. Accepted:
  silence is the current state, and it is safe.
* Clause 3 comes from the general convention of tables of contents, not from the RFC corpus. It is
  the one clause written with a document format in mind, and it is flagged as such.
* Clauses 4 and 7 carry the only two constants (100, 2). Both are *shape* bounds, not thresholds
  fitted to a distribution — but they are constants, and this project has been bitten by an
  uncalibrated constant before, so they are named here to be argued with.

**How it is measured, second:** run over the RFC corpus and report documents accepted, documents
rejected, and — for a sample of ten accepted — whether the extracted `heading_path`s are actually
right. **A poor match is a finding to report, not a licence to loosen the rule.** Any change to a
clause after seeing the corpus is recorded *here*, with its reason, as a change made after the fact.
Otherwise the predicate is fitted to the answer and proves nothing.

### 5.4 · The measurement — **run 20260805, in doubling rounds, to 980 documents**

Corpus fetched by [`tools/build_rfc_corpus.py`](../tools/build_rfc_corpus.py) across three
rendering eras. **Each round doubled the previous one and re-ran every earlier fix**, on the
user's instruction — because a fix validated at one corpus size has been validated at one corpus
size, and clause 9 proved exactly that by surviving 66 documents and failing at 131.

| round | documents | accepted | early | classic | **modern** |
|---|---|---|---|---|---|
| 1 | 66 | 42 (64%) | 3/22 | 17/22 | **22/22** |
| 2 | 131 | 76 (58%) | 3/44 | 30/44 | **43/43** |
| 3 | 259 | 152 (59%) | 7/88 | 62/88 | **83/83** |
| 4 | 522 | 321 (61%) | 27/175 | 123/176 | **171/171** |
| 5 | **980** | **644 (66%)** | 92/332 | 238/334 | **314/314** |

**The headline is the last column: every modern-era RFC is accepted, 314 for 314, and the rate was
100% at every round size.** That is the era the grammar targets and the format current documents
use.

**Two thirds of all rejections are documents with no numbered sections at all** — 221 of 324 in the
final round. Those are *correct* rejections, not misses: an early RFC is frequently a memo with no
outline to find. The remaining 103 are step-breaks, and the causes are named below.

**What the corpus changed, both recorded as post-hoc in `chunk.py`:**

* **Clause 9 — an outline starts at section 1.** Found at round 1: RFC 769's facsimile command
  codes (`56 - SET-UP`, `57 - DATA`, `58 - END`) satisfied every clause and produced three headings
  that are not headings.
* **Clause 10 — a trailing `.0` is a style, not a depth.** Found at round 2: `1.0`/`2.0` numbering
  is a recurring convention, mixed freely with plain numbers.

**What the corpus *refused*, which is the more useful half:**

* **"A title must not begin with punctuation"** — killed the false positive and three genuine
  documents (`5.1.  /get`, `2.7.3.  "iprev"`, and RFC 2010's entire outline, which numbers real
  sections `1 - Rationale and Scope` — the identical shape as the false positive).
* **"A heading must be followed by a blank line"** — killed a second false positive and four
  genuine documents, because **real headings wrap**:
  `7.4.  The Network Information Center and` / `Requests for Comments Distribution Contact`.

**Known bounds, accepted rather than chased:**

| bound | why it is not fixed |
|---|---|
| **Early-era RFCs centre their top-level headings** (`␣␣␣␣2.  OVERVIEW`) while left-aligning subsections, so the walk breaks at `1.4 → 2.1`. This is most of the 14–28% early-era acceptance | Relaxing clause 1's column-0 rule to admit indented lines would match indented prose and table rows across every era. The cost is concentrated in documents from the 1980s; the risk is spread over all of them |
| **RFC 778 numbers a procedure** — `1. Connect to…`, `2. Send the command…` — and is accepted | Starting at 1 and consecutive, it is indistinguishable from an outline by any clause that does not also reject real headings. Labelling the steps of a numbered procedure as sections is defensible; `56 - SET-UP` was not |
| **A skipped number rejects the document** (`7 → 9`, `3.1.1 → 3.1.3`) | Almost always a heading the clauses missed rather than a genuine gap. Admitting gaps would weaken the walk, which is the only thing standing between this grammar and an ordered list |

**Every rejection costs nothing that existed before.** The document falls back to `_plain_blocks` —
exactly pre-grammar behaviour — so the measurement's floor is *today*, and 644 documents gained
structure they did not have.

---

## 6 · The permanent `code`/`pdf` WARN — **DECIDED 20260805 18:25 by the user**

**WARN only when `markdown` sits at 0%.** Other source types report OK with a note naming why they
carry none.

**The problem.** `_heading_coverage` (shipped in 0.12.0) returns `Status.WARN` when *any* source
type sits at 0%, and `code` and `pdf` can never carry a heading today. So a KB containing one `.py`
file or one PDF warned on **every `pnk doctor` run, forever**, with a remedy saying it is a limit of
the tool. It did not surface in verification because both committed corpora are pure Markdown at
100%.

**Why this way.** An un-actionable warning that cannot be cleared is how doctor output stops being
read *at all* — it costs the actionable warnings too, which is a larger loss than this one signal.
`markdown` at 0% is the opposite case: real, fixable, and exactly the defect the check was built
for — the chunker silently size-slicing a corpus whose files use a heading convention it does not
read.

**The accepted cost, stated:** the zero-heading-paths condition that bounds 0.11.0's gate becomes
quieter on `text` and `pdf` corpora. It is still *reported* — the percentage and the note are
printed — just not as a WARN. When `headings = "numbered"` (§5.1) ships, a `text` corpus becomes
fixable and can be re-judged then.

**Required:** the note must name the cause, not just the number — *"the chunker extracts headings
for `markdown` only"* — so a reader is not sent to edit documents that are not the problem.

---

## 7 · Work in flight — **none. Everything here has landed and shipped in 0.12.0**

Both branches this section used to track were reviewed, corrected and landed 20260805 17:31–17:36,
and 0.12.0 published them. What the review changed is worth carrying forward, because in both cases
the *code* was fine and the *test* was not:

| Branch | Landed | What the review found |
|---|---|---|
| `…-i2-light-backend-error` | `43cef55` | Nothing wrong with the fix. Its own retrospective is the value: the pre-existing test looked environment-independent and was not — it blocked only `sentence_transformers`, leaving this checkout's transitively-installed `fastembed` genuinely importable |
| `…-i6-sync-cpu-measurement` | `1511be4` | **A HIGH defect the tests could not see.** `sample_percent` watched the launched pid, so the tool's own documented invocation — `-- uv run pnk sync …` — measured `uv`, which burns nothing. Identical one-core load: **1.0 cores direct, 0.0 through `uv run`**. Every test ran a direct child that did the work itself, so code coverage was complete and coverage of the *invocation* was zero |

**The instrument now exists and is correct; the measurement it exists for has still not been taken.**
That remains open correction 3.

---

## 8 · Standing method for all of the above

* **Adversarial review loop until a pass finds nothing** — the user asked for this explicitly.
  Every increment: green `./check.sh`, then mutate the 3–5 most safety-critical assertions and
  confirm the *right* test fails for the *right reason*. **"Mutation-verified" is per-assertion,
  never per-commit.**
* **The failure class to hunt: an assertion satisfied by something other than the property it
  names.** It has appeared four times in two days — in a spec sentence, in a five-legs-from-six
  generalisation, in a `min`-for-`max`, and inside a test written to close it. Each time, mutation
  caught it and care did not.
* **A green `./check.sh` only proves the worktree's installed extras are green.** CI is a three-leg
  matrix over `[light]`, `[light,pdf]`, `[light,pdf,claude]`.
* **Documentation has one owner — the planner.** Implementers propose `git diff <sha> -- <file>`
  against a named commit; they write `changelog.d/` and `retro.d/` fragments and only the
  `docs/VERIFICATION.md` rows their own tests require.
* **Land with `python3 tools/land.py <branch> --cleanup`**, never `git merge` by hand.
