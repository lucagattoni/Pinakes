# A real corpus, and a real KB

**Audience: the agent building it. Goal: executor.** Decided with the user 20260801 07:19. This
closes decision 1's realism question and gives L8's step 8 — *"the ClaudeKB realism check is run, or
declined in writing"* — something it can actually be run against.

**Since 20260801 12:14 it has a second purpose, and it is now the critical path.** G2 measured that
the graph release's gate cannot be reached on `tests/demo-kb`, and both reasons are properties of the
corpus rather than of the code: the corpus has no tags and one directory, so exactly one derived edge
kind crosses a document boundary; and the retrieval funnel already returns every document, so no
channel can reach further than it already does. **G3, G5 and G6 do not start until a corpus exists
that can discriminate.** That raises this document's priority — and puts an honesty burden on it,
discharged in § *Why this is not the gate moving to fit the answer*.

**Two knowledge bases, not one**, because one name was covering two different needs:

| | Realism corpus | Dogfooding KB |
|---|---|---|
| Repo | **`pinakes-corpus-rfc`, public** | **`pinakes-kb`, private** |
| Content | RFCs — open-licence, real prose, **real authored links** | the user's own working material |
| Who reads it | any agent, any machine, no credentials | the user, locally |
| CI | **never** — no gate depends on it, by decision | never |
| Purpose | answer *"do the synthetic corpora resemble real usage?"* | find the friction a test never surfaces |

Making them one repo would force the open-licence half to inherit privacy it does not need, put a
deploy key in a public repo's CI, and leave forks unable to use it. Splitting means each gets the
constraints it actually has. They may declare each other as `[[links.kb]]` partners — which would
exercise cross-KB links against a real pair for the first time.

**Neither repo is ever committed into `pinakes`.** CLAUDE.md's first rule: the repo is the engine,
and the only KBs in it are the synthetic corpora under `tests/`.

---

## Precondition — settle the licence before fetching anything

**Do not commit a single RFC until this is written down.** RFCs are published under the IETF Trust's
Legal Provisions (BCP 78 / RFC 5378), which permit unlimited reproduction of the RFC text; that is
the *expectation*, not a verified fact, and it is the whole basis for a public repo. Read the current
Trust Legal Provisions, record the clause and the date in the corpus repo's `README.md`, and note any
RFC series or stream it does not cover. If it turns out reproduction is restricted, stop and re-decide
the corpus — do not fall back to "probably fine".

Fetch from `https://www.rfc-editor.org/rfc/rfcNNNN.txt`. Record the retrieval date; that file is the
canonical form and does not change.

## What to select — a connected cluster, never a random sample

~100–300 documents. The point is the **link graph**, so a random sample is worthless: most RFCs
update or obsolete nothing, and an unconnected set would measure only prose.

Take a genuinely cross-referenced family and follow its chains to closure. The HTTP/TLS/URI cluster
is the obvious candidate — RFC 9110–9114, 8446, 3986, and everything they obsolete back through
7230–7235, 2616, 2068 — but **the executor picks the exact set and records why**, with the closure
rule it used. State the rule before fetching: *follow `Obsoletes` and `Updates` edges transitively
from the seed set until the frontier is empty or the count reaches 300, whichever first.*

## Structure — the part demo-kb did not have, and the reason its gate failed

**As first written, this plan specified a flat `docs/` with one `.txt` per RFC and no tags. That
reproduces `tests/demo-kb`'s exact blindness at larger scale**, and would have produced a second
negative result that looked like a fact about graphs and was a fact about directory layout. The
corpus needs structure, and the constraint on it is arithmetic rather than preference.

**A hub whose degree is the corpus is not a signal.** G3's weights were frozen in decision 13,
committed before any of this: `co-located` is doc↔directory at 1/dir-size, `shared-tag` is doc↔tag
at 1/tag-degree, and composition across a hub is the product of both spokes. One directory holding
every document therefore connects every document to every other at an identical weight — a constant
added to every candidate, which changes no ordering. The same holds for a tag carried by everything.
**A hub discriminates only when its degree is small relative to the corpus**, and that is true no
matter which answer one is hoping for.

**So the requirement is: many small buckets, not one large one** — and derived mechanically from a
field the documents or their editors already publish, never invented.

**The source is the RFC Editor's own index**, `https://www.rfc-editor.org/rfc-index.xml`. Its schema
(`rfc-index.xsd`, read 20260801 13:20) defines per entry: **`wg_acronym`**, **`area`**, **`stream`**,
**`keywords`**, **`current-status`**, **`publication-status`**, and the relation elements
`obsoletes` / `updates` (plus `obsoleted-by` / `updated-by`, which are the same edges from the other
end — see below). That is real, human-assigned metadata, which is what makes using it honest.

**Measure before choosing, and record the measurement.** For each candidate field, over the selected
set: how many documents carry it at all, how many distinct values, and the size of the largest
bucket. Then:

| | Use it as | Reject it if |
|---|---|---|
| `wg_acronym` | the **directory** — `docs/<wg>/rfcNNNN.txt` | its largest bucket is most of the corpus, or most entries are empty |
| `keywords` | **tags** in the sidecar | same test, per keyword |
| `area`, `stream`, `current-status` | fallback directory, if `wg_acronym` fails the test | an IETF-only cluster makes `stream` a single bucket by construction |

**Expect some of these to fail the test, and say so.** A cluster chosen for its `Obsoletes` chains is
likely to be mostly one area and mostly Standards Track — meaning `area` and `current-status` are
hubs, not discriminators. Reporting that is the measurement working. **What is not permitted is
inventing a directory split, or hand-assigning tags, to reach a bucket size that makes a later probe
pass.** The rule is the fixed thing: *the scheme is a mechanical function of a published field,
chosen and written down before the probe runs.*

## Links — derived from the documents, never invented

This is the whole reason for RFCs. Every RFC header carries real, human-authored relations:

| RFC header | `rel` | Direction |
|---|---|---|
| `Obsoletes: NNNN` | `supersedes` | this document → the older one |
| `Updates: NNNN` | `updates` | this document → the one it amends |

**Author the forward relations only.** `Obsoleted by:` and `Updated by:` are the same edges seen from
the other end; authoring both doubles the density and misrepresents what a human wrote. Traversal
reads both directions already (`--direction both`).

A target outside the selected set is **dropped, not authored** — a link to a document the KB does not
contain is a dangling link, and `pnk doctor` would rightly report it. Record how many were dropped:
that number is itself a finding about closure.

## The measurement — and a prediction to make before running it

Produce a written comparison in the corpus repo, and a summary in `pinakes`' own
`docs/STATUS.md` § *Measured numbers* (planner incorporates it):

| Measure | demo-kb | partner-kb | the RFC corpus |
|---|---|---|---|
| documents | 30 | 21 | ? |
| documents carrying an authored link | 27% | 29% | ? |
| worst out-degree | 2 | 3 | ? |
| relation vocabulary | 2 kinds | 4 kinds | ? |
| document length, chunks per document, heading depth | | | ? |

**The prediction, recorded now so the measurement can falsify it:** the RFC corpus will **exceed the
35% density cap** `tools/link_density_gate.py` enforces, and possibly the degree cap of 4. Those
numbers were fitted to two hand-written corpora on the argument that *authored links are sparse*
(APPROACH §3, from ClaudeKB). If real data exceeds them, **the cap is wrong, not the corpus** — and
that is the realism check doing its job rather than failing. Do not tune the corpus to fit the gate.
Report the number, and let the planner decide whether the cap moves.

The gate stays as it is for `tests/`'s corpora either way: it exists to stop *synthetic* corpora
being made unrealistically dense, and that argument is untouched by what real RFCs do.

## Setting it up

1. `pnk init` in the corpus repo. `provider = "fastembed"` in **both** `[embedding]` and `[rerank]`
   (`pnk init` stamps `sentence-transformers`; see `docs/GUIDE.md`).
2. Documents under `docs/<bucket>/rfcNNNN.txt`, the bucket chosen by the rule above, with the
   measurement that chose it recorded. Tags into each sidecar from the same source.
3. `pnk sync` to mint sidecars and ULIDs. **Commit the sidecars** — they are the truth layer, not
   generated state. **Never commit `.pinakes/`.**
4. Author the `links[]` entries from the headers (a script in the corpus repo, not in `pinakes`).
5. `pnk doctor` — expect WARNs, expect no FAIL.
6. A `README.md` recording: the licence finding, the selection rule, the retrieval date, the
   dropped-target count, and how to rebuild the whole thing from scratch.

## Why this is not the gate moving to fit the answer

Designing a corpus after watching a gate fail on the old one is exactly the shape of fitting the
measurement to the desired result, and it has to be answered rather than waved past.

**The justification is independent and it is timestamped.** This document was decided with the user
at **20260801 07:19**, five hours before G2's probe ran at **12:14**, for a purpose that had nothing
to do with the graph gate — L8's declined realism check. It carries a falsifiable prediction made in
ignorance of the outcome (the density cap, below). And `docs/STATUS.md` has said since **20260729
03:23** that `multi-hop` sits at ceiling and *"nothing should be tuned against it until it is both
larger and harder"* — the same conclusion, reached two days earlier from the numbers alone.

**The structural constraint is derived from frozen weights, not from a wanted answer.** Decision 13
froze `1/dir-size` and `1/tag-degree` before G2's questions were authored. "A hub the size of the
corpus adds a constant" follows from those weights arithmetically; it would be equally true if the
graph release had already shipped.

**What the corpus licenses: nothing.** Building it does not restart G3. The sequence is unchanged and
each step can still say no:

1. Select, structure and author the corpus by the written rules — **before any question exists**.
2. Author a multi-hop question set against it, and **freeze it before the probe runs** (G2's trap 1).
3. Re-run `tools/reachable_ceiling_probe.py`. Report **both** numbers, with and without authored
   edges; only the **without** figure binds (G2's trap 2). **A different agent does this**, by
   [`corpus-probe-run.md`](corpus-probe-run.md) — which also owns the conversion from the frozen
   question file into the eval schema, because that conversion touches frozen material and is the
   one place this separation could quietly leak.
4. Report whichever answer comes back. **"Still cannot discriminate" is a publishable result**, and
   on this corpus it is a live possibility — a cluster whose documents all cite each other may be no
   more separable than thirty short disjoint notes, only longer.

**One thing is forbidden outright:** re-authoring questions, re-cutting buckets or re-selecting
documents *after* seeing a probe result, to move the number. If the probe fails twice, the honest
conclusion is that the expansion channel is not worth a `schema_version` bump — which is a finding,
not a failure.

## What this is not

- **Not a gate.** No `check.sh` step, no CI job, no scheduled run. A gate depending on data no
  runner has is a gate that skips silently, which this project's own rule calls a claim rather than
  a check.
- **Not a golden set.** It has no questions and no baseline. Whether it ever gets one is a separate
  decision — and G2's rule that a question set is frozen before the edge set is measured applies
  there too.
- **Not a PDF corpus.** DESIGN §9's caveat — the extraction quality numbers rest on synthetic
  rasters — stays open. Real scanned PDFs are a later, separate corpus; do not mix them in here,
  because that would confound the link-structure question with an extraction question.

## The dogfooding KB

Minimal by design: `pnk init` in a private repo, the user's own material, the same two-line backend
edit. No plan governs its content. Its output is not a measurement but a list of friction — record
it wherever the user prefers, and anything that becomes a durable finding reaches `pinakes` through
`retro.d/` like any other.
