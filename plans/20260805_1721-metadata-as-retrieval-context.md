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

> ⚠️ **Re-checked 20260806 20:41 against `main` at `36f32ce`. Two rows are now false in substance,
> not merely in their pointers, and every `chunk.py` line has moved a second time.**
>
> **Pointers.** `sync.py:1940` → the embed call at **2005**; `sidecar.py:670` → `minted_title` at
> **666**; `chunk.py:254` → `_plain_blocks`'s `heading_path=None` at **631**; `chunk.py:131` → the
> block dispatch at **284-288**; `chunk.py:78` → `source_type` at **111**. `manifest.py:59` and
> `search.py:512` still hold.
>
> **The two substantive corrections are this plan's own steps 1 and 3** — *Heading detection is
> Markdown-only* and *Titles never come from content* — and both rows are rewritten below rather
> than annotated. **Locate by the symbol named in each row, never by its line.** Five releases
> (0.12.0–0.15.1) and three increments have landed since this table was written against `3a4fa9e`,
> and `chunk.py` was reshaped by 0.13.0 and again by 2b: a stale number is worse than no number in a
> section headed *"do not re-derive these"*.

| Fact | Evidence |
|---|---|
| **Neither `title` nor `heading_path` affects retrieval today** | FTS5 indexes `chunks.text` only (`store.py:87-92`); embeddings are computed over `chunk.text` only (`sync.py:1940`); the reranker scores `passage.text` (`search.py:512`). No `WHERE`, `ORDER BY` or filter touches either field |
| **`heading_path`'s only consumers** | Citations (`search.py:79`), the `in-section`/`parent`/`child` edges and the `heading` node key (G3), and the passage payload on CLI (`cli.py:209`) and MCP (`serve.py:421`) |
| **`title`'s only consumers** | Search-result display (`cli.py:208`, `serve.py:331`), link listings (`cli.py:804` — `label = row.get("title") or row["doc_id"]`), and graph presentation, where it **counts against the traversal token budget** (`present.py:69`, `provider.py:192`) |
| **Losing `heading_path` costs zero recall** | By design: DESIGN §4.6 puts the heading *line* into the first chunk beneath it, so heading words stay searchable through `text`. This is why a 106 806-chunk corpus with **zero** heading paths passed every eval while bounding the graph release's gate — recall could not see it |
| **Titles come from content for `markdown` only — everything else falls back to the filename stem** | Corrected 20260806 20:41: step 3 shipped in 0.15.0 and falsified the original row (*"titles never come from content, for any source type"*). `skeleton()` now takes `title=_title_from_content(...)` at the mint site (`sync.py:1397`), which returns `first_h1()` for `markdown` and `None` for everything else (`sync.py:1420`, `chunk.py:321`); the other `skeleton()` call — the `--sidecars-only` path — still passes no title. Titles are minted **only when a sidecar is created**, so no existing KB changed. **For this experiment the row's consequence is unchanged**: every `.txt` RFC still falls back to `minted_title` (§2, finding 5), which is why 2a mints them from the publisher instead |
| **`[chunking] strategy` is inert** | `CHUNK_STRATEGIES = ("structural",)` (`manifest.py:59`), validated by `table.choice` (`manifest.py:615`), and **never read at runtime** — grep across `src/` finds no consumer. Only `max_tokens` is used from `[chunking]`. What dispatches is `source_type` |
| **`source_type` is assigned by suffix, and `text` is a fallback** | `chunk.py:78`. `.md/.markdown` → `markdown`; ten code suffixes → `code`; `.pdf` → `pdf`; **everything else** → `text`. So `text` today includes `.rst`, `.adoc`, `.org`, `.tex`, `.csv`, `.json`, `.yaml`, `.log` and extensionless files |
| **Heading detection is Markdown-only unless `[chunking] headings = "numbered"`** | Corrected 20260806 20:41: step 1 shipped in 0.13.0 and made the dispatch three-way (`chunk.py:284-288`) — `_markdown_blocks` for `markdown`, `_numbered_blocks` for `text` when the numbered grammar is selected, `_plain_blocks` otherwise, which still sets `heading_path=None` unconditionally (`chunk.py:631`). **The original fact still describes every KB that has not opted in**, which is all of them: `headings` defaults to `"none"` and is never stamped into the template (§5.2). **Nothing failed to match because nothing was tried** — the superseded diagnosis said a grammar failed to match, which would have sent an implementer to fix a regex that never ran |

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
   to the text that is **embedded** and **indexed**, leaving `chunks.text` — what the user is shown,
   and what `char_start`/`char_end` index into — **unchanged**.

   **DECIDED 20260806 03:55 by the user: both channels, at `schema_version` 4.** The separation is
   *not* free, and the original "if that separation is feasible" understated it: the vector channel
   takes one call site, but the lexical channel cannot be reached without a new `chunks` column, a
   rewritten set of FTS5 triggers and a schema bump — **every existing KB rebuilds once**. The
   rejected alternatives, kept so they are not reopened: **vector-only** avoids the bump but leaves
   BM25 unchanged, so RRF fusion dilutes the effect and a null result is partly attributable to the
   dilution rather than to the hypothesis — which would waste the measurement. **Mutating
   `chunks.text`** is simplest and is refused outright: it desynchronises the character offsets from
   the source file and changes what `search` returns.

   **The obvious cheap alternative is blocked by the same invariant, and it was checked rather than
   assumed.** Repeating the heading *line* inside every continuation chunk would reach both channels
   with no schema change at all, since FTS and the embedder both read `chunks.text`. But
   `_markdown_blocks` and `_numbered_blocks` include the heading line **in the block's own character
   span** (`chunk.py:225-228`), so `chunks.text` is today exactly `text[char_start:char_end]`.
   Repeating a heading in a later chunk breaks that identity — the same defect as mutating
   `chunks.text`, wearing different clothes.

   **The cost this decision accepts, stated plainly: the schema bump is not reversible, but the
   feature is.** If the run shows no movement, the manifest option can be removed and the injection
   deleted — yet every KB has already rebuilt once at `schema_version` 4, and un-bumping is not a
   thing. That is the price of reaching the lexical channel, and it is why the screening question
   below is worth answering first.
2. **Rebuild** and run the golden-set eval.
3. **Report `recall@k`, MRR and false-abstain rate, before and after**, in the commit message.
   `CLAUDE.md` § *Changing retrieval* requires exactly this and forbids justifying it by intuition.

### The corpus problem — read this before planning the run

> **Corrected 20260806 03:55, by measurement.** The text this replaced said `tests/demo-kb` has
> **no continuation chunks** and that *"the mechanism has nothing to act on"*. **That is false**, and
> the reasoning behind it is the part worth not repeating: it inferred from document *size* (~7
> lines, which is correct) that a section fits in one chunk. `chunk.py` splits on **paragraph blocks
> first** — `Block` is "one paragraph under one heading path" — and only then fits token limits. A
> 7-line document with two paragraphs yields **two** chunks, of 27 and 31 tokens, under a 120-token
> budget. Measured with the real chunker and the real tokenizer over all 30 documents:
>
> | `tests/demo-kb` | |
> |---|---|
> | Documents / chunks | 30 / 60 |
> | `(doc, heading_path)` sections | 30 |
> | Sections spanning more than one chunk | **30 of 30** |
> | Continuation chunks not containing their own heading text | **29 of 30** |
>
> The demo KB carries the mechanism this experiment is about. It still cannot *license* the result —
> for two reasons, neither of them the one originally written.

**`tests/demo-kb` cannot license it. The RFC band can, since 2c:**

| Corpus | Verdict |
|---|---|
| `tests/demo-kb` | **Cannot — power.** 66 answerable questions, **4 misses**, and **56 of 62 hits already at rank 1**. On `recall@k` the entire improvable pool is 4, and the project's own `sign_test(4, 0)` returns **p = 0.0625** — a *perfect* result fails the p < 0.05 bar the graph channel was held to. Second and independent: scoring is **document-level over de-duplicated paths** — `eval._run_question` collapses the passages to first-seen document paths and takes `hit_rank` from that list — and every demo-kb document has a heading-bearing chunk 0, so injecting into chunk 1 changes an outcome only when it lifts that document past a *rival* document. Numbers re-measured 20260806 03:52 against a fresh index; all 74 rows match the committed artifact exactly |
| **The RFC band** — `build_rfc_corpus.py --era modern --count 200`, RFCs 8600-8799, **195 published**, ~43 500 chunks | **Can, since 2c.** Long sections; real `heading_path`s (0.13.0); published titles and a 96-token reserve (2a); and a frozen, blind-authored, calibrated **110-question golden set with an improvable pool of 15** (2c) — `tools/rfc_corpus/questions.yaml`, with the `before` leg at `tools/rfc_corpus/{baseline,outcomes}.json`. **It is not the 300-document corpus that bounded the graph gate** ([STATUS](../docs/STATUS.md#the-realism-corpus-exists-and-it-falsified-a-design-premise--built-20260804-0800)) — that one is larger, differently selected (a BFS cluster over `obsoletes`/`updates`, not a band), and still public at [`pinakes-corpus-rfc`](https://github.com/lucagattoni/pinakes-corpus-rfc) — documents, sidecars and manifest all committed, so its figures **are** re-derivable. ⚠️ **Its manifest has no `[chunking] headings` key**, and the grammar is opt-in at `"none"`, so a rebuild today still produces zero heading paths: to give that corpus sections you must add the key yourself |

**The experiment is blocked on neither.** Step 1 shipped in 0.13.0; the golden set was authored,
frozen and calibrated by 2c at `36f32ce`, **before any injection code existed**. What remains is
2d-2f (§3).

**Why the set was authored blind, in one sentence, because it is the thing that licenses every
number below.** Fitting a question set to the mechanism it will judge is the circularity this
project cut once before (STATUS: *"fitting the question set to the edge set is the circularity that
cutting cross-KB questions removed once already, and it is undetectable afterwards"*), so 2c's six
authors were forbidden from reading this repository and did not know what their questions would be
used to measure. The full argument travels with the instrument, in `tools/rfc_corpus/questions.yaml`'s
own header — including why the pool was **not** raised by authoring more paraphrase questions. Read
it before adding a question; **never reword or renumber one**, because `id` is what pairs a `before`
row with an `after` row.

### Six things the implementer must know before writing a line

Each measured 20260806 against `main` at `4ace8b0`, and each fails **silently** if missed. Three
are now **closed** — by 2a and 2b, marked below. They stay in the table because the *condition*
each names is a property of this pipeline that a differently-built corpus reintroduces; what
changed is that the RFC corpus no longer has it. (The heading said "four" while listing six from
the day it was written; corrected here rather than propagated.)

| | Finding | Evidence |
|---|---|---|
| **1** | ✅ **Closed by 2a.** The generated manifest now stamps `max_tokens = 414`, reserving 96 — and 2b refuses rather than truncates if a corpus exceeds it. **The condition, which any hand-written manifest reintroduces:** the RFC corpus had zero token headroom. Its manifest stamps no `max_tokens`, so the default **510** applies against a measured window of **512** with 2 special tokens. Prepending anything pushes every full chunk past the window | `build_rfc_corpus.py:118-120`, `manifest.py:632`, `ModelInfo(max_seq_length=512)` for `BAAI/bge-small-en-v1.5` |
| **2** | **Over-length input raises no warning and no error.** Measured: a 512-token string embedded with an empty `warnings` list. The truncation removes text from exactly the long chunks the hypothesis is about, so it biases toward **no movement** — a false negative that reads as a clean result | measured |
| **3** | ✅ **Closed by 2b.** `assert_chunkable` still validates `max_tokens` alone at `sync.py:1137`, before anything is chunked; `chunk.assert_prefix_fits` is the one that catches this, after chunking and before embedding. It is **dormant until 2d** wires it in | `sync.py:1137`, `chunk.py` |
| **4** | **The lexical channel cannot be injected without a schema change.** `chunks_fts` is FTS5 with `content='chunks'`, filled by triggers copying `new.text`; `SCHEMA_VERSION = 3` is enforced by a hard `IndexSchemaError` refusal | `store.py:87-105`, `store.py:28,258` |
| **6** | **The stage that sets the final rank never sees the injection.** `search()` re-sorts **entirely** by `rerank_score` — the fused score stops ordering anything — and the reranker scores `passage.text`, the *display* text (`search.py:511-517`). `rerank` defaults to `"local"` and the RFC manifest declares a reranker, so this is the configuration the run would use. **Confidence too**: `_confidence` reads `rerank_score` (`search.py:583-595`), so `false_abstain` — one of the three metrics §2 requires — is also produced blind to the injection | `search.py:511-517,583-595`, `manifest.py:670` |
| **5** | ✅ **Closed by 2a** for this corpus — the builder mints each sidecar with the title published at `rfc<N>.json`. **The condition, unchanged for any other `.txt` KB:** on an un-curated corpus, `title` is a filename. Content-derived titles are **Markdown only** — `if source_type(path) != "markdown": return None` — so every `.txt` RFC falls back to `minted_title`, the filename stem. The prefix would read `rfc9110 > 3.1. Semantics`, injecting the token `rfc9110` into every chunk of that document. That is the condition 0.14.0's `titles` check exists to detect, and it confounds the run in **both** directions: it can lift any question naming an RFC number (an artifact that reads as confirmation) or dilute the embedding | `sync.py:1417`, `sidecar.py:675` |

**Finding 6 bounds what this experiment measures. DECIDED 20260806 04:40 by the user: gate on
`rerank = "local"`, and run the `rerank = "none"` leg alongside as a declared diagnostic.** With
reranking `local`, injection changes an outcome only by changing **which chunks reach the
reranker** — `candidates_per_source` defaults to **50** and the RFC manifest declares no
`candidates_per_source` — since 2c its `[retrieval]` block carries only the
`[retrieval.confidence]` thresholds — so 50 it is. Over ~10⁵ chunks that is a real filter, and it is where
retrieval on a large corpus is won or lost — but it is a **candidate-recall** effect, and this plan
does not get to call it a ranking effect.

The diagnostic leg is one extra eval run from the **same binary and same index**, and it is not a
second chance at significance: the gate is fixed to `local` in advance. Its value is that it turns
one failure mode into information — if `local` fails while `none` moves, the finding is *"injection
improves fusion and the reranker erases it"*, which points somewhere. Without it that run is a flat
null that teaches nothing.

| Option | What it measures | Cost | |
|---|---|---|---|
| `rerank = "local"` | The shipped pipeline, end to end | Reranker churn is noise on the same scale as the effect; a real gain can be erased by a stage blind to it | **CHOSEN (gate)** |
| `rerank = "none"` | The fused ranking, isolating the injection | Measures a configuration nobody ships; a green gate here could not license a default | **CHOSEN (diagnostic only)** |
| Reranker sees injected text | The hypothesis in its strongest form | A third design change on a schema bump; re-opens what "displayed" means; and a cross-encoder fed metadata may degrade for reasons unrelated to the hypothesis, inseparably from it | rejected |

**How much does the reranker actually move things? Measured 20260806 04:35 on `tests/demo-kb`,
flipping `rerank` only (it is query-time, so the index is untouched): the rank of 13 of 66
answerable questions changes — 20%, 7 better without the reranker and 6 worse.** Four ranks in five
survive it, but the one in five it moves is the same order of magnitude as the whole improvable
pool. **This number does not transfer to the RFC corpus** and must be re-measured there: demo-kb
reranks with `BAAI/bge-reranker-base` and the RFC manifest declares
`Xenova/ms-marco-MiniLM-L-6-v2`. It is evidence that a reranker materially reorders, not a
prediction of by how much.

**And the `none` leg's error rates are a mirage — do not read them as improvements.** Measured on
the same flip: `false_abstain` 0.0152 → 0.0 and `false_confidence` 0.25 → 0.0, because every
confidence became `unknown` and `confidence_coverage` fell 1.0 → 0.0. `compare()` already treats
that fall as a regression, for the reason its own comment gives: *"the error rates would improve to
a meaningless zero while the system got quieter, not better."*

### The confidence metrics are calibrated — and must not be refitted

**Closed by 2c, 20260806.** The condition is worth keeping because any new corpus reintroduces it:
`build_rfc_corpus.py`'s manifest had **no `[retrieval]` section**, so `confidence` was `None`
(`manifest.py:659`) and `_confidence` returned `UNKNOWN` on its very first check
(`search.py:581-582`) — **whatever the rerank setting was**. `false_abstain` and `false_confidence`
were therefore vacuously 0.0, exactly the mirage described above, and §2 step 3's requirement to
report false-abstain could not have been met.

2c fitted `[retrieval.confidence]` against the 14 unanswerable questions and **stamped it into the
builder's manifest template** — not into a generated `pinakes.toml`, which lives outside the repo
and dies with the machine. Measured effect: `confidence_coverage` 0.0 → **1.0**, `false_abstain`
0.0 → **0.0104**, `false_confidence` 0.0 → **0.1429**.

**Two rules survive their increment, and both bind every leg from here on:**

* **Never refit.** Thresholds refitted after an injection would differ between legs, and every
  confidence comparison would then measure the refit rather than the change. Stamping them in the
  template makes both legs fitted identically **by construction** — a property to preserve through
  2d, 2e and 2f, not a step to repeat.
* **A golden set for this corpus keeps its no-answer questions.** `calibrate.py` fits both
  thresholds against the scores of the **unanswerable** ones, "because those are the ones whose
  correct outcome is known absolutely". The frozen set holds 14; a future set without them cannot be
  calibrated at all.

**Carry `calibrate.py`'s own caveat into whatever is reported**: the thresholds are fitted on the
same golden set the eval scores against, so the false-confidence rate "is partly a measurement of
the fit… treat calibration as a floor on quality, not a measurement of it." That is a reason to
report the confidence numbers with the caveat attached, never a reason to gate on them — and the
gate here is on rank, which is unaffected.

### What the corpus actually looks like — measured on RFC 9110, 20260806 04:55

Chunked at `max_tokens` 510, `overlap` 64, `headings = "numbered"` — **the default the RFC manifest
implied before 2a; it has stamped 414 since** (`build_rfc_corpus.py`, `CHUNK_MAX_TOKENS = 512 - 2 -
96`). The shape facts below (chunk share carrying a `heading_path`, sections spanning more than one
chunk, continuation-chunk count) are what this table is for and they survive the reserve; **the
`Largest token_count` row is a fact about 510 and must be re-derived before it is reused.** One
document:

| | |
|---|---|
| Chunks | **1 858**, of which **1 838 (99%)** carry a `heading_path` |
| Sections spanning more than one chunk | **233 of 271** |
| **Continuation chunks — the mechanism's target** | **1 567, in a single document** |
| Largest `token_count` | **510 — exactly the cap**, so finding 1's zero headroom is real on real text, not merely implied by a default |

For scale: the whole of `tests/demo-kb` offers **30** continuation chunks. One RFC offers 1 567.

**These are two different requirements and this plan conflated them once — corrected 20260806
05:25.** Continuation-chunk count is **mechanism surface**: how much material the injection has to
act on. Statistical power is a property of the **golden set**, not the corpus, and is governed by
the improvable-pool criterion below. A corpus with 1 567 continuation chunks and a golden set every
question of which already sits at rank 1 would have abundant surface and **no power at all**. Both
have to be satisfied, and satisfying one says nothing about the other.

**`heading_path` carries the section numbers, deliberately.** `chunk.py:404-405`: *"The number stays
in the label — unlike Markdown's `#`, which is syntax, `1.2` is content you would cite."* So a
verbatim prefix reads `HTTP Semantics > 7.  Routing HTTP Messages > 7.6.  Message Forwarding >
7.6.1.  Connection`. That choice was made **for citation**, and injection is about **embedding** —
which makes the form of the injected prefix a decision rather than a detail. Measured over the same
1 838 chunks:

| Prefix form | Mean tokens | Max | Reserve as a share of the 510 budget | |
|---|---|---|---|---|
| Verbatim | 21.4 | 45 | **8.8%** | rejected — numbers are 44% of the prefix and semantically empty for either encoder |
| Section numbers stripped | 11.9 | 30 | **5.9%** | **DECIDED 20260806 05:05 by the user** |
| Deepest heading only | 6.1 | 17 | **3.3%** | rejected — at mean depth 2.6 it discards most of the ancestor context the experiment exists to test |

> ⚠️ **Every number in that table is RFC 9110's, and the `Max` column does not generalise —
> measured 20260806 06:1x while building 2a.** Re-run over **195 documents** (RFCs 8600-8799, 5 of
> the 200 numbers unpublished), same prefix form, same tokeniser:
>
> | Section numbers stripped, corpus-wide | |
> |---|---|
> | Largest prefix in the corpus | **68 tokens** |
> | Per-document largest | median **31**, p95 **51**, p99 **61** |
> | Longest title alone | **32 tokens** |
>
> **RFC 9110 is an unrepresentative sample for one reason: its title is two tokens long.** The
> *median* document in the band exceeds this table's max of 30. The relative ranking of the three
> forms is unaffected — the decision stands — but **the `Max` column must not be used to size a
> reserve**, which is exactly what the first version of §3 did.

**The prefix has two separators, and neither was specified here — they are now decisions in code,
taken by 2b** (`chunk.py`, `fcabc02`). `HEADING_JOIN = " > "` joins `title` onto the path and each
label to the next; it is the one name for a format that is **persisted** in `chunks.heading_path`
and parsed back out by `graph/edges.HEADING_SEPARATOR`, where a disagreement empties three edge
kinds and reports nothing. `PREFIX_SEPARATOR = "\n\n"` separates prefix from text — a blank line,
the boundary the source already uses between blocks.

**The table above measures prefixes *without* a separator, so every row understates by whatever it
costs.** Zero under BERT's WordPiece, which drops newlines; one or two under a byte-level BPE. That
gap cannot reach the reserve, because `assert_prefix_fits` measures the separator **with the
prefix**. Anyone re-running the table should say which convention they used.

**The numbers live in `heading_path` for citation, and injection is an embedding change** — carrying
them across would inherit a choice made for a different purpose, at 44% of a budget that finding 1
makes the binding constraint. Stripping keeps every word that carries meaning. **What would have
reversed this was checked at 2c, as scheduled, and the decision stands.** If the authored questions
referenced section numbers (*"what does section 7.6 say about…"*), the numbers would be signal and
the verbatim form would win. **Zero of the 110 frozen questions do** — measured 20260806 20:41 over
`questions.yaml`'s `question` fields. The file's single `section` reference sits in an `evidence`
sentence quoted from a document, which is answer text and not a query. The check could not bias
anything: the questions were frozen before an injection number existed.

Heading depth is mean 2.6, max 4. **Numbers are stripped by construction, never by re-parsing** —
done in 2b: `_numbered_candidates` returns the label with and without its number from the *same*
match, so nothing runs a second regex over the joined string. Markdown keeps whatever number its
author typed (`## 1. Introduction` → `1. Introduction` in both forms), because nothing parsed a
number there and only the grammar that parsed one may remove it — the same rule, which is also what
keeps the `404` in `# 404 Not Found`.

**The graph channel is off, so nothing interacts with this today** — `adjacent_k` and the
`sibling`/`in-section` edges only run when `graph_channel = "expand"` (`manifest.py:57`,
`search.py:398`), and both corpora leave it `off`. **Worth recording for later:** those two edge
kinds partly duplicate the injection's mechanism, so any future run with the channel on would
confound the two.

**The vector channel, by contrast, has a single injection point**: `sync.py:2005`,
`backend.embed([chunk.text for chunk in chunks])`. `parsed.title` and `chunk.heading_path` are both
already in scope there. It is the only `.embed(` call on the indexing path — the others are
query-side. `_paid_rebuild_survivors` cannot carry stale un-injected vectors into a rebuild here: it
returns empty for a free backend (`sync.py:1657`), and neither corpus has a PDF.

**The instrument exists but its CLI does not fit.** `tools/graph_gate.py` requires three legs
(`--before`, `--after-without`, `--after-with`, all `required=True`) and is specific to the graph
channel's authored-edge drop. What is directly reusable is **`judge(before, after, *, kind,
tolerance)`** (line 269) and **`sign_test(improved, regressed)`** (line 90). Note also that the
committed `tests/demo-kb/eval/outcomes.json` has a **pre-G5 header** — no `graph_channel` or
`edge_kinds`, and `read_leg` reports its channel as `(absent)`. **Regenerate the `before` leg; never
use that file as one.**

### What each outcome licenses

* **Movement** → metadata is retrieval context; the claim is proven, and the expensive downstream
  work (PDF layout heuristics, paid title inference) becomes arguable on evidence.
* **No movement** → `title` and `heading_path` stay display-and-graph. **The expensive work dies
  cheaply, which is the point of running this first.**

**"Movement" now has a number. DECIDED 20260806 03:55 by the user: an exact one-sided sign test on
rank improvements, p < 0.05** — the same bar the graph channel was held to, so the two results are
comparable, and already implemented in `graph_gate.sign_test`. The alternatives and why they lost:
the graph gate's **full four clauses** are stricter and would also catch a change buying paraphrase
gains out of ordinary lookup, but they are written for a three-leg channel comparison and are
over-specified for a single injection change; **deciding after seeing the numbers** is refused
outright, because the anti-circularity rule below presupposes a threshold and choosing one
afterwards makes the result unfalsifiable.

**This clause was missing until now, and its absence was the defect.** The paragraph below has
always said *"a result short of the threshold is reported rather than retried"* while nothing in
this document ever said what the threshold was.

**Anti-circularity applies in full**, as it did to the graph gate: questions stay frozen, nothing is
tuned after seeing a number, and a result short of the threshold is reported rather than retried
with a different injection format.

---

## 3 · The agreed order of work

Decided by the user 20260805 after options with trade-offs. **Do not reorder without a reason
recorded here.**

| # | Step | Blocked on | Cost |
|---|---|---|---|
| 1 | **Numbered-heading grammar for `.txt`** | ✅ **Shipped 0.13.0.** All of §5 settled: the key and vocabulary (§5.2) and the full predicate, written before any corpus was consulted (§5.3) | Moderate |
| 2 | **The injection experiment** (§2) | **Steps 2d–2e below** — 2a shipped 20260806 06:17, 2b 08:33, 2c 11:56. Re-scoped 20260806 03:55, re-ordered 05:15, screen inserted 05:30 — see the notes | **Measured, not estimated:** `pnk sync --rebuild` over the ~43 500-chunk corpus takes **46 min**, and 2d and 2f need two legs each |
| 3 | **Markdown H1 → title** | ✅ **Shipped 0.15.0.** `first_h1()` in `chunk.py`, wired at mint time. Existing sidecars are never rewritten, so no migration | Small |
| 4 | **`pnk doctor` title check** (B3) | ✅ **Shipped 0.14.0** | Small |
| 5 | PDF layout heuristics + confidence scoring | **Step 2 showing movement** | High |
| 6 | Paid LLM title inference | **Step 2 showing movement** | High — the full paid-path apparatus |

**Step 2 is five increments and a run, not "~2 h rebuild + eval".** That estimate costed the run
alone, and neither the obligations in front of it nor the size of the corpus were visible when the
table was written. **2a, 2b and 2c have shipped; 2d and 2e remain, then the run.** Each is a
separate, bisectable landing:

| # | Increment | Why it is its own landing |
|---|---|---|
| **2a** | ✅ **Shipped 20260806 06:17, `86cd403`.** `tools/build_rfc_corpus.py` fetches each document's published title from `rfc<N>.json` and mints its sidecar before the first sync; the manifest stamps `max_tokens = 414`, reserving **96**. Verified by execution: two RFCs built and synced with the real `fastembed` backend index under their published titles, largest `token_count` exactly 414 | Without titles there is nothing to inject (finding 5); without the reduced `max_tokens` the two legs are chunked differently and the comparison is void (below) |
| **2b** | ✅ **Shipped 20260806 08:33, `fcabc02`.** `chunk.assert_prefix_fits` refuses a document whose longest prefix exceeds the reserve `max_tokens` left, naming that prefix and the value to lower to — after chunking, before embedding, per the decision below. It ships **with the prefix construction**, not just the check: `Chunk.unnumbered_heading_path` (numbers stripped by construction, from the `(number, label)` pair the grammar already parsed), `metadata_prefix` and `embedding_text`. Verified by execution against 195 RFCs — see the note below | Converts finding 2's silent truncation into a loud error. Code-only; it changes no existing KB, because the reserve lives in the corpus manifest |
| **2c** | ✅ **Shipped 20260806 11:56, `36f32ce`** (`a42d962`, review `5993521`). `tools/rfc_corpus/questions.yaml` freezes **110 questions** — 32 lexical, 32 simple-lookup, 32 paraphrase, 14 no-answer — one answerable question per document over **96 of the band's 195**, authored **blind** by six agents on disjoint slices and each verified against the sentence in its document that answers it (`tools/verify_rfc_golden_set.py`). `[retrieval.confidence]` fitted against the 14 unanswerable questions and stamped into the builder's manifest template. **Improvable pool 15**, against the ≥ 10 the criterion requires. The `before` leg is committed at `tools/rfc_corpus/{baseline,outcomes}.json`: **recall@k 0.9271, MRR 0.8767**, rerank_precision 0.8438, false_abstain 0.0104, false_confidence 0.1429, confidence_coverage 1.0; by_kind lexical 1.00, simple-lookup 1.00, paraphrase 0.7812, no-answer 1.00 — at `max_tokens = 414`, `k = 5`, `rerank = "local"`, `graph_channel = "off"` | Had to be on `main` **before any injection code existed**, or the questions could have been influenced by a number. **Ordered after 2a and 2b** because its exit criterion is measured on the chunking the experiment will actually use |
| **2d** | **The vector-only screen.** The manifest option `[chunking] metadata`, default `"off"`; the call to `assert_prefix_fits`; the switch to `embedding_text` at `sync.py:2005`. The prefix itself already exists. **No schema change.** Built as *What 2d builds* below | A **go/no-go on cost**, not a test of the hypothesis. See the pre-registration below. The option ships here, so a user who turns it on with the default `max_tokens` must meet 2b's refusal rather than silent truncation — which is why the refusal landed first, dormant |
| **2e** | **The injection: a new `chunks` column, rewritten FTS5 triggers, `schema_version` 4** | Only if 2d says go. A schema bump is breaking for every existing KB and is the landing a bisect must be able to isolate |
| **2f** | **The run** | Regenerate both legs from the same binary (never reuse the committed pre-G5 `tests/demo-kb` artifact as a `before`), rebuild, judge with `sign_test` at p < 0.05 — and **compare `[chunking]` before judging anything**: see *the identity gap* below |

#### 2d's pre-registration — written 20260806 05:30, **before the screen has been run**

**DECIDED 20260806 05:30 by the user.** The plan's own method is that *"the expensive work dies
cheaply, which is the point of running this first"* — argued in §2 for steps 5 and 6, and not, until
now, applied to step 2 itself. Everything in 2a–2c is needed either way; **the schema bump is the
only irreversible part of this plan**, and 2d is what puts evidence in front of it.

* **Criterion, fixed in advance: proceed to 2e if the vector-only leg shows strictly more rank
  improvements than regressions across all answerable questions.** No p-value. It is deliberately
  loose, because its job is to stop a bump that would buy nothing — not to decide the hypothesis.
* **The screen reads `rerank = "none"`, and that difference from the gate is deliberate
  (20260806 05:40).** A screen exists to avoid **false negatives**; the gate exists to avoid **false
  positives**; they should not share a configuration merely because they share a corpus. Under
  `local` a vector-only screen is attenuated three times over — injection reaches the vector channel
  only, RRF dilutes it against an unchanged BM25, and the reranker re-sorts everything blind to it
  (finding 6) — so a null would not distinguish *no mechanism* from *mechanism suppressed*, and the
  plan would abandon a real effect on a measurement that could not have found it. **The gate at 2f
  stays on `local`.** Rejected: a `local` screen, a faithful miniature whose null is
  uninformative for exactly that reason; and running both and proceeding on either, which stretches
  the two-looks problem further than one loose screen already does.
  **This is not the `none`-leg diagnostic approved for the gate phase** — that one explains a gate
  failure after the fact; this one decides whether the schema bump happens at all.
* **The screen's numbers are never cited as evidence for or against the claim**, in either
  direction, and never appear in the gate's report except as a note that a screen was run. **This
  is the whole anti-circularity cost of adding it**: seeing a number before the gated run is two
  looks at the data, and the only thing keeping that honest is that the two have different
  questions, different criteria, and this paragraph written before either.
* **The gate at 2f is unchanged and independent** — `sign_test` at p < 0.05, all answerable
  questions, `rerank = "local"`.
* **If the screen says no-go, that is a reportable result, and a weaker one than the gate would
  give:** *"injecting `title > heading_path` into the embedded text alone moved nothing on this
  corpus; the both-channel form was not tested."* Steps 5 and 6 stay unapproved, and the schema
  bump is not taken. Say what was and was not measured — the dilution objection that disqualified
  vector-only as a **gate** applies in full to a null here.

#### What 2d builds — written 20260806 20:41, with 2a, 2b and 2c on `main`

**Everything 2d needs already exists.** The prefix (`chunk.metadata_prefix`), the text it produces
(`chunk.embedding_text`), the refusal (`chunk.assert_prefix_fits`), the corpus settings
(`max_tokens = 414`, published titles, `[retrieval.confidence]` stamped), the frozen questions and
the committed `before` leg all landed in 2a–2c. What is missing is a switch, two call sites, two
eval runs — the first of which has to happen **before** the switch is flipped — and the comparison
that reads them.

1. **`[chunking] metadata`, enumerated, default `"off"`. DECIDED 20260806 20:41 by the user.**
   Accepted values `"off"` and `"prefix"`, parsed by `table.choice` beside `headings` in
   `manifest._chunking`, and **never stamped into the template** — §5.2's reason applies unchanged:
   `_toml.py` hard-errors on an unknown key, so a manifest carrying it cannot be read *at all* by a
   Pinakes built before it existed.

   **Why `[chunking]` and not `[retrieval]`, which §4's row names.** The key changes what is
   **embedded and indexed**, so it is a property of the build, not of a query — and the index
   already records the two build sections: `[embedding]`'s provider, model, revision and dim
   (`sync.py`, checked by `search.py` on every query — DESIGN §4.4) and `[chunking]`'s settings
   through `store.chunking_identity`, whose drift `pnk sync` and `doctor._chunking_drift` both
   report (0.13.0). **`[retrieval]` is the section nothing in the index records**, so the same flip
   there is **silent** — the user searches uninjected
   vectors with every command reporting success, which is the failure class this plan keeps
   guarding against. It also reaches `eval.header`'s `chunking` block for free (`5993521`), which is
   what 2f's identity check reads. §4's row settles that injection **is** an option defaulting to
   `off`; the table was not settled there, and `manifest.py:658,683` cite the default-and-`choice`
   mechanism, which is unchanged either way. Rejected: **`[retrieval] metadata_injection`**, for the
   silence above; and **a boolean**, for §5.1's reason — the prefix *form* is a decision this plan
   has already re-opened once, and a boolean cannot absorb a second form.

   Extend `store.chunking_identity` and `eval.header`'s `chunking` block with the new key in the
   same increment. Both are one line, and both are load-bearing at 2f.

2. **The refusal, called only when the option is on.** `assert_prefix_fits` shipped dormant. Call it
   after `chunk_document` and before `backend.embed`, once per document, with that document's own
   `parsed.title`; `model_max_tokens` is `backend.info().max_seq_length`, which `sync.py:1137`
   already reads for `assert_chunkable`. **Gate it on `metadata = "prefix"`** — with the option off
   nothing is prefixed, so refusing a corpus that is not at risk would turn an opt-in feature into a
   breaking change for every existing KB.

3. **The embedded text.** `sync.py:2005` — `backend.embed([chunk.text for chunk in chunks])` becomes
   `embedding_text(chunk, title=...)` under the option and `chunk.text` otherwise. `chunks.text`,
   `char_start` and `char_end` are untouched: that is §2 step 1's refusal, and it is what keeps the
   lexical channel out of 2d.

4. ⚠️ **The screen's own `before` leg — captured before the switch is flipped, or paid for twice.**
   The repository does not contain it. 2c's committed leg is `rerank = "local"`; the screen reads
   `rerank = "none"` (decided 20260806 05:40, and deliberately — §3's pre-registration). `rerank` is
   query-time, so that leg is **one eval run over the same uninjected index** — but only while that
   index exists. `pnk sync --rebuild` with the option on replaces it, and rebuilding costs 46
   minutes. **Order: build, sync, evaluate at `rerank = "none"`, and only then flip.**

5. **The reproduction check, free and worth taking first.** The same uninjected index also answers
   at `rerank = "local"`, and that run must reproduce `tools/rfc_corpus/baseline.json` exactly. If it
   does not, the corpus did not regenerate identically and nothing downstream means anything —
   `tools/eval_reproducibility_gate.py` exists because *one question in 41* moved across a rebuild.
   It costs one query pass and it is the only check that the instrument 2c froze is still reading the
   corpus 2c measured.

6. **The injected leg, and the comparison that answers the screen.** Flip `metadata = "prefix"`,
   `pnk sync --rebuild`, evaluate at `rerank = "none"` — that is the `after` leg. Then compute the
   pre-registered criterion: **pair the two legs on question `id`, and over the answerable rows
   count `hit_rank` decreases against increases**, ranking a miss as worse than any hit. Proceed to
   2e if improvements strictly exceed regressions. **`graph_gate.judge` does not supply this** — it
   is written around hit-flips within one `kind` — so 2d writes the comparison, and 2f can reuse it
   with `sign_test` layered on top. Refuse to compare at all if the two headers disagree on
   anything but the injection key (below).
7. **One correction 2d owes to code it does not otherwise touch.** `tools/build_rfc_corpus.py`'s
   reserve note says *"what catches a corpus that exceeds it even so: `assert_chunkable`, loudly"*.
   `assert_chunkable` cannot and never could — it validates `max_tokens` against the model window at
   `sync.py:1137`, before anything is chunked, so it never sees a prefix. That is why 2b exists.
   Correct it to name `assert_prefix_fits`, and say that it is dormant until this increment wires it
   in.

**Do not commit the screen's legs.** The pre-registration says the screen's numbers are never cited
as evidence in either direction and appear in the gate's report only as a note that a screen was
run. An artifact sitting in `tools/rfc_corpus/` beside the gate's own `before` leg would be read as
one. Report the go/no-go and its improved/regressed counts in the commit message, and nowhere else.

#### The identity gap 2f must close — recorded 20260806 20:41

`5993521` added `max_tokens`, `overlap` and `headings` to `eval.header`, so an artifact now
**records** what it was chunked at. Nothing **compares** it: `graph_gate.check_identity` checks only
`k`, `embedding`, `rerank`, `ranking` and `retrieval`, and it takes **three** legs shaped to the
graph channel's `off`/`expand`/`drop-authored` comparison. Two legs chunked differently therefore
still compare clean today, which is the exact defect 2a's reserve and 2b's refusal exist to prevent,
surviving one level up into the instrument.

2f needs a **two-leg** check that compares `chunking` **first**, excepting exactly the injection key
whose difference *is* the experiment, and pairs rows on question id as `check_identity` already
does. `check_baseline` guards the other half — that a baseline and its per-question rows came from
one run.

**Budget, measured 20260806.** The corpus is ~43 500 chunks and `pnk sync --rebuild` over it took
**46 minutes**. 2d needs two syncs (uninjected, then injected); 2e's schema bump invalidates both, so
2f needs two more. **Start the first rebuild in the background at the top of a session, never at the
end.**

**The ordering of 2a–2c was load-bearing and was wrong in the first revision of this table.** The
golden set's exit criterion is a *measured* improvable pool, and a pool measured against different
chunking than the run uses is not the pool the gate will see. So the corpus settings landed first,
the refusal that protects them second, and only then was the baseline captured.

**Three parameters the increments above must not leave to taste:**

* **Corpus band and size — `modern`.** §5.4 measured the heading grammar at **314 of 314** on the
  modern band and 644 of 980 overall; a corpus where a third of documents carry no `heading_path`
  would dilute the very thing being injected. Size is set by the criterion below, not by a
  round number.
* **2c's exit criterion was a measured pool, not a question count — met at 15.** The rule: author
  until the **improvable pool at baseline — misses plus hits below rank 1 — is at least 10**, and
  record it. It is executable, checkable before any injection exists, and it is the number that
  decides whether the gate can be reached at all: `sign_test(4, 0)` = 0.0625 **fails**,
  `sign_test(5, 0)` = 0.0312 passes, `sign_test(10, 0)` = 0.0010. **`tests/demo-kb`'s pool is 10 and
  its `recall@k` pool is 4** — which is exactly how this plan's original corpus assumption was
  caught, and why a pool measured up front is a precondition rather than a diagnostic.

  **Recorded, as the criterion required: 15**, over 96 answerable questions at `max_tokens = 414`,
  `k = 5`, `rerank = "local"`. **Where it lives matters as much as its size: 11 paraphrase, 2
  lexical, 2 simple-lookup**, because `lexical` and `simple-lookup` are **saturated at 1.00** on this
  corpus — a corpus of distinctive technical vocabulary, where BM25 with a reranker essentially
  solves them. **So any future question about statistical power here is a question about
  `paraphrase`** — and authoring more paraphrase questions to raise the pool is precisely the move 2c
  refused, since it fits the instrument to the hypothesis one step removed. **The rule outlives its
  increment:** a question added to the frozen set later re-opens this measurement.
* **The reserve is a corpus setting, not a per-document computation — corrected 20260806 05:15.**
  An earlier revision of this plan said to reserve the longest prefix *per document*. That is more
  frugal and it is the wrong shape, because it buries the reserve in code where the two legs must
  agree on it exactly. **The RFC corpus manifest stamps `max_tokens = 414` against the 512-token
  window, reserving 96 for the prefix, and both legs use it** (shipped in 2a). Chunk boundaries are
  then byte-identical across the legs by construction, and the only difference between them is the
  injected text — which is the entire requirement.

  **Why this is not optional.** Chunking the before leg at 510 and the after leg at 480 makes them
  different corpora. Measured on RFC 9110: **63 of 1 858 chunk texts differ (3%)**, 30 char spans
  move, and the chunk count changes by 3. `tools/eval_reproducibility_gate.py` exists because *one
  question in 41* moved across a rebuild, and its docstring states the standard this would breach:
  *"any per-question movement caused by anything else is not noise, it is a wrong answer."*

  **Where 414 and 96 come from — and what the earlier `e.g. 480 … max prefix of 30` got wrong.**
  That pair was RFC 9110's maximum, and RFC 9110's title is *two tokens* long. Measured over 195
  documents while building 2a, the largest prefix is **68 tokens** and the per-document largest has
  **median 31** (the table in §2 carries the full distribution). Reserving 30 would have truncated
  roughly half the corpus's longest chunks — silently, biasing the experiment toward **no
  movement**, a false negative that reads as a clean result. 96 is 41% above the measured maximum,
  because 200 numbers is under a third of the modern band.

  **What 2b owed in code was a refusal, not a reservation — and the site the first draft named
  cannot provide it.** `assert_chunkable` runs at `sync.py:1137`, **before anything is chunked**, so
  no `heading_path` exists yet and `max_prefix` is not knowable there. It is a property of the
  corpus, not of the manifest: 30 on RFC 9110, 68 across 195 RFCs of the same era.

  **DECIDED 20260806 07:39 by the user: refuse after chunking and before embedding**, computing the
  real largest prefix from the chunks in hand. Exact, needing no constant and no new manifest key —
  the refusal fires on the corpus that actually exceeds the reserve rather than on a prediction
  about it. Rejected: **a declared `[chunking] prefix_reserve` key**, because it is a third value
  the two legs must agree on — the shape this very bullet rejects — and a declared reserve smaller
  than the real one truncates silently again, reinstating the defect it exists to remove; and **a
  fixed constant in code**, which is an uncalibrated threshold fitted to one corpus, and 30-vs-68
  across two samples of the *same era* is how far it can miss. The accepted cost: a large corpus is
  chunked before it fails, which is seconds against a silently invalidated experiment.

  **What shipped, and the one thing this bullet left to the implementer.** `assert_prefix_fits`
  compares the document's longest prefix against **the reserve** — `budget - max_tokens` — not
  against the worst chunk in hand. Per-chunk pairing is more permissive and more exact, and it was
  rejected for this bullet's own reason: what has to be safe is the **setting**, since both legs
  must chunk under the same `max_tokens`, and a document passing only because none of today's
  chunks reaches the cap would begin truncating on the next edit, mid-experiment. Cost per
  document is one tokenisation per *distinct heading path*, not per chunk.

  **The additive estimate that makes it cheap was measured, not argued** (20260806, `fcabc02`):
  `count_tokens(prefix + separator) + chunk.token_count` was **exactly equal** — never merely
  bounding, never under — to the real concatenated count for all **43 503 chunk/prefix pairs of
  195 RFCs** under `BAAI/bge-small-en-v1.5`. The same run reproduced this bullet's own figures from
  an independent code path (largest prefix 68; per-document largest median 31, p95 51, p99 61;
  longest title 32) and confirmed the refusal fires for **195 of 195** documents at the default
  `max_tokens = 510` and for **none** at 414. **So the corpus is ~43 500 chunks** — one prefix is
  built per chunk, so 2b's pair count is the chunk count — and **`pnk sync --rebuild` over it took
  46 minutes** (measured 20260806 while capturing 2c's baseline). That is the figure to size 2d's
  and 2f's two legs each against.

**2a was a fetch, not a heuristic — which is what made it cheap and what kept it clear of a
rejected decision.** `https://www.rfc-editor.org/rfc/rfc<N>.json` returns the RFC's authoritative
metadata, including `title`, in ~1.5 KB from the host the corpus already downloads from, cacheable
exactly as the document is. **Measured 20260806 04:1x: `title` present and non-empty in 44 of 44
documents** — 24 modern (8600–8623), 10 classic (2000–2009), 10 early (760–769). So era does not
constrain it.

**Extraction from the document text was tried first and is rejected on the evidence.** A predicate
taking the single non-blank line between the header block and `Abstract` — refusing on zero or
several, in this plan's usual shape — accepted **6 of 24** modern documents and **0 of 4** early
ones, because multi-line titles are common and the early era has no `Abstract` marker at all.
More important than the low number: **a published `title` field is not inference**, so this does not
reopen the first-line heuristic that stays rejected (§2, 0.14.0, 0.15.0). Nothing is guessed; a
value is read from the publisher.

**How the title reaches the index.** `title` is the user's field and `sync` must never overwrite it,
so the corpus builder writes the sidecar itself — `sidecar.skeleton(document, title=...)` takes the
title at mint time — **before the first sync**. Sync then adopts it and leaves it alone. A document
whose JSON cannot be fetched keeps the filename fallback and **is reported**, never silently
minted: a corpus where an unknown share of titles are filenames measures something nobody can name.
**Confirmed by execution 20260806 06:14** — the claim above had never been run: two RFCs built and
synced index under their published titles, and `tests/test_sync.py::test_an_existing_sidecars_title_is_never_rewritten`
already owned the "leaves it alone" half. Two things 2a met that this paragraph did not anticipate:
real RFC titles carry **colons** (RFC 8713), which `ruamel` quotes correctly but which no committed
corpus had ever exercised; and an existing `pinakes.toml` must not be rewritten by a re-run, or the
`[retrieval.confidence]` thresholds **2c** fits onto this corpus are discarded while every command
reports success.

**Steps 5 and 6 were argued against on current evidence and are not approved**, and this re-scoping
does not touch them — they are still gated on step 2 showing movement. They are listed so
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
| **Where 2b's refusal gets `max_prefix`** | ✅ **Built as decided, `fcabc02`.** **Refuse after chunking, before embedding, computing the real largest prefix from the chunks in hand** (20260806 07:39). `assert_chunkable` runs before anything is chunked, so the site the first draft named cannot know the value — and `max_prefix` is a property of the *corpus*, not the manifest: 30 on RFC 9110, 68 across 195 RFCs of the same era. Rejected: a declared `[chunking] prefix_reserve` key, and a fixed constant. Full reasoning and the accepted cost: §3, the reserve bullet |
| **Screen before the schema bump** | **Yes — a vector-only screen at 2d, pre-registered as a go/no-go on cost** (20260806 05:30). The schema bump is the only irreversible step in this plan, and everything else in 2a–2c is needed either way, so evidence goes in front of it. Rejected: **straight to both channels**, which avoids the multiple-testing problem but rebuilds every KB on an unproven premise; **a strict p < 0.05 screen**, which would stop on a real effect that fusion dilution alone suppressed — the very objection that disqualified vector-only as a gate. Full pre-registration and its anti-circularity cost: §3, 2d |
| **Reranker configuration** | **Gate on `rerank = "local"`; run the `none` leg as a declared diagnostic; and the 2d screen reads `none`** (20260806 04:40, screen setting 05:40) — a screen avoids false negatives, a gate avoids false positives, so they deliberately differ. Argued with measurements in §2 — the reranker moves 13 of 66 demo-kb ranks, and the `none` leg's error rates are a mirage |
| **Prefix form** | **`title > heading_path` with section numbers stripped** (20260806 05:05). Measured token costs and the rejected alternatives: §2, the prefix-form table |
| **Which questions the gate scores** | **All answerable questions** (20260806 04:25). Rejected: **a labelled continuation-chunk subset**, which has more power per question but makes regressions *outside* the subset invisible — clause 1 of the graph gate without clause 2, and exactly the trade `simple-lookup` was created to expose; and **`multi-hop`**, which is the graph gate's class and not this mechanism's. Two facts decided it: scoring is **document-level** (`eval._run_question`) while the label is **chunk-level**, so the subset does not isolate the mechanism as cleanly as it appears; and with real titles (2a) the injection acts on **every** chunk, not only continuation chunks. A sign test runs on **discordant** pairs, so non-moving questions cost nothing — the objection that a wider class "dilutes" the signal does not apply. `compare()`'s per-class `by_kind` report is kept alongside as a free guard |
| **The `title` half of the prefix** | **Curate real titles for the corpus first, then inject both** (20260806 04:15). On `.txt` the title is the filename stem (finding 5), so injecting `title` unmodified would inject `rfc9110`. Rejected: **`heading_path` only**, which measures a clean signal but leaves `title` formally unmeasured; **two arms**, which creates a multiple-comparison problem against a fixed p < 0.05 bar and invites picking the better arm afterwards. **What made the chosen option cheap was discovering the titles are published** — the objection to it was the cost and risk of a heuristic, and there is no heuristic |
| **Is injection a shipped option?** | **Yes — a manifest option defaulting to `off`** (20260806 04:15), on `graph_channel`'s mechanism: enumerated, `table.choice` with a default, never stamped into the template (`manifest.py:658,683`). Rejected: **unconditional**, because the two legs could then only come from two different builds, and comparing across builds attributes every build-induced flip to the injection — the precise failure `graph_gate.check_identity` exists to refuse |
| **Which table the option lives in** | **`[chunking] metadata`, values `"off"` \| `"prefix"`** (20260806 20:41). It changes what is embedded and indexed, and the index records both build sections — `[embedding]`'s identity and `[chunking]`'s settings (`store.chunking_identity`) — so a flip without a rebuild is *reported* rather than silently serving uninjected vectors. Rejected: **`[retrieval] metadata_injection`**, which the row above reads as at a glance — `[retrieval]` is query-time and is the one section nothing in the index records, so the same flip is silent; and **a boolean**, for §5.1's reason, since the prefix form is a decision this plan has already re-opened once. Full argument and what it obliges: §3, *What 2d builds* |
| **Corpus for the experiment** | **The RFC corpus, with a golden set authored first** (20260806 03:55). `tests/demo-kb` was weighed and rejected: it carries the mechanism but cannot license a result — `sign_test(4, 0)` = p = 0.0625 on a 4-question improvable pool (§2). Running it there anyway was offered as a cheap smoke test and not taken |
| **Which channel is injected** | **Both, at `schema_version` 4** (20260806 03:55). Vector-only and mutating `chunks.text` were both weighed and rejected — see §2 *The experiment*, step 1 |
| **What licenses "movement"** | **Exact one-sided sign test on rank improvements, p < 0.05** (20260806 03:55) — see §2 *What each outcome licenses* |
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

**The instrument now exists and is correct, and the measurement it exists for was taken in 0.14.0**
(corrected 20260806 03:55 — this said the measurement was still outstanding, and named an open
correction that has since closed): the first sync is **not** single-core, at peak 5.0 and mean 4.8
of 10 cores under `fastembed`, so the document loop stays serial. `plans/20260731_1202-open-corrections.md`
has been empty since 20260805 22:18.

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
