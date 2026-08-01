# A real corpus, and a real KB

**Audience: the agent building it. Goal: executor.** Decided with the user 20260801 07:19. This
closes decision 1's realism question and gives L8's step 8 — *"the ClaudeKB realism check is run, or
declined in writing"* — something it can actually be run against.

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
2. Documents under `docs/`, one `.txt` per RFC, named `rfcNNNN.txt`.
3. `pnk sync` to mint sidecars and ULIDs. **Commit the sidecars** — they are the truth layer, not
   generated state. **Never commit `.pinakes/`.**
4. Author the `links[]` entries from the headers (a script in the corpus repo, not in `pinakes`).
5. `pnk doctor` — expect WARNs, expect no FAIL.
6. A `README.md` recording: the licence finding, the selection rule, the retrieval date, the
   dropped-target count, and how to rebuild the whole thing from scratch.

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
